import { settle, type Bet } from "../src/domain/parimutuel";
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

        if (pozo && estado.outcome) {
          const reparto = settle(
            { si: pozo.si, no: pozo.no, feeBps: pozo.feeBps },
            apuestas,
            estado.outcome,
          );
          // pagar primero, marcar después: si el proceso muere en medio, el
          // dinero ya está acreditado y el estado se recalcula solo
          resumen.acreditado += store.pagarMercado(seed.id, reparto.payouts);
        }
        const nadieAcerto =
          pozo !== undefined && (estado.outcome === "si" ? pozo.si : pozo.no) <= 0;
        estado = { ...authorizePayout(estado, ahora), phase: nadieAcerto ? "devuelto" : "pagado" };
        resumen.pagados += 1;
      }

      if (JSON.stringify(estado) !== antes) store.guardarLiquidacion(estado);
    } catch (error) {
      resumen.errores.push(`${seed.id}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return resumen;
}
