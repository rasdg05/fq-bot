import { MIN_APOSTADORES, settle, type Bet } from "../src/domain/parimutuel";
import {
  authorizePayout,
  initialState,
  isPayable,
  onClose,
  onRead,
  readWithOracles,
  type Oracle,
} from "../src/domain/settlement";
import { defaultOracles } from "../src/adapters/oracles/priceOracle";
import type { OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";
import type { Store } from "./store.mts";

/**
 * El ciclo de vida, corriendo dentro del servidor. Cierra mercados, lee las
 * fuentes, abre la ventana de disputa y paga a **todos** los usuarios del pozo
 * compartido — no a la copia local de nadie.
 *
 * La matemática es la misma del dominio, probada aparte: aquí sólo se decide
 * cuándo tocarla y dónde queda guardado el resultado.
 */

export interface ResumenCiclo {
  at: string;
  leidos: number;
  pagados: number;
  /** Mercados anulados por falta de participación, con todo devuelto. */
  anulados: number;
  /** Comisión cobrada en esta corrida, ya asentada en tesorería. */
  comision: number;
  atorados: string[];
  acreditado: number;
  errores: string[];
}

function debeLeerse(seed: OwnMarketSeed, fase: string, ahora: number): boolean {
  if (fase === "cerrado" || fase === "leido") return true;
  if (fase !== "abierto") return false;
  // un mercado de toque puede resolver antes de su fecha: se consulta vivo
  if (seed.rule?.kind === "precio" && seed.rule.modo === "toca") {
    return !seed.rule.desde || new Date(seed.rule.desde).getTime() <= ahora;
  }
  return false;
}

export async function correrCiclo(
  store: Store,
  seeds: OwnMarketSeed[],
  oracles: Oracle[] = defaultOracles(),
  ahora = Date.now(),
): Promise<ResumenCiclo> {
  const resumen: ResumenCiclo = {
    at: new Date(ahora).toISOString(),
    leidos: 0,
    pagados: 0,
    anulados: 0,
    comision: 0,
    atorados: [],
    acreditado: 0,
    errores: [],
  };

  for (const seed of seeds) {
    try {
      let estado = store.liquidacion(seed.id) ?? initialState(seed.id);
      const antes = JSON.stringify(estado);

      if (estado.phase === "abierto" && new Date(seed.closesAt).getTime() <= ahora) {
        estado = onClose(estado);
      }

      if (debeLeerse(seed, estado.phase, ahora)) {
        const { reading } = await readWithOracles(oracles, {
          marketId: seed.id,
          spec: seed.resolution,
          rule: seed.rule,
          now: ahora,
        });
        const siguiente = onRead(estado, reading, seed.resolution, ahora);
        if (siguiente.phase !== estado.phase) resumen.leidos += 1;
        estado = siguiente;
      }

      if (estado.phase === "atorado") resumen.atorados.push(seed.id);

      if (estado.phase === "en_disputa" && isPayable(estado, ahora)) {
        const pozo = store.pozo(seed.id);
        const apuestas: Bet[] = store
          .apuestasDeMercado(seed.id)
          .map((a) => ({ id: a.id, side: a.side, stake: a.stake }));

        /**
         * Un mercado con un solo apostador no es un mercado: el pozo perdedor
         * sería la semilla de la casa, y esa persona estaría ganándole a
         * nadie. Se anula y se devuelve lo apostado, íntegro (R-059).
         */
        const distintos = new Set(
          store.apuestasDeMercado(seed.id).map((apuesta) => apuesta.usuarioId),
        ).size;
        const sinMercado = distintos > 0 && distintos < MIN_APOSTADORES;

        if (pozo && estado.outcome) {
          const reparto = sinMercado
            ? { payouts: Object.fromEntries(apuestas.map((a) => [a.id, a.stake])) }
            : settle(
                { si: pozo.si, no: pozo.no, feeBps: pozo.feeBps },
                apuestas,
                estado.outcome,
              );
          // pagar primero, marcar después: si el proceso muere en medio, el
          // dinero ya está acreditado y el estado se recalcula solo
          resumen.acreditado += store.pagarMercado(seed.id, reparto.payouts);
          // y la comisión va a la tesorería con su asiento: si se resta del
          // reparto tiene que llegar a algún lado (R-064)
          if (!sinMercado && "fee" in reparto && reparto.fee > 0) {
            resumen.comision += reparto.fee;
            store.acumularComision(seed.id, reparto.fee);
          }
        }

        const nadieAcerto =
          pozo !== undefined && (estado.outcome === "si" ? pozo.si : pozo.no) <= 0;
        estado = {
          ...authorizePayout(estado, ahora),
          phase: sinMercado || nadieAcerto ? "devuelto" : "pagado",
          ...(sinMercado
            ? {
                stuckReason: `Anulado: hizo falta gente. Sólo ${distintos} de ${MIN_APOSTADORES} apostadores, se devolvió todo.`,
              }
            : {}),
        };
        if (sinMercado) resumen.anulados += 1;
        else resumen.pagados += 1;
      }

      if (JSON.stringify(estado) !== antes) store.guardarLiquidacion(estado);
    } catch (error) {
      resumen.errores.push(`${seed.id}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return resumen;
}
