import {
  MIN_APOSTADORES,
  bettorStake,
  normalizePool,
  settle,
  totalPool,
  type Bet,
} from "../src/domain/parimutuel";
import { compensar, type Reparto } from "../src/domain/compensacion";
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
          // el pozo entra por `normalizePool`, no campo por campo: escribir
          // `{ outcomes, feeBps }` a mano tira la semilla y su modo, y un
          // mercado con subsidio liquidaría como los de antes sin avisar
          const pool = normalizePool(pozo);

          /**
           * `settle()` produce el reparto; **no** mueve saldos. Se le pide el
           * de cada resultado, no sólo el del ganador: es lo que convierte «el
           * pozo cuadra con este ganador» en «cuadra pase lo que pase», que es
           * lo único que se puede llamar neutralidad (R-065).
           *
           * Un mercado anulado por falta de gente reparte lo apostado, íntegro
           * y sin comisión, gane quien gane: es el mismo reparto para todos los
           * resultados (R-059).
           */
          const devolucion: Reparto = {
            payouts: Object.fromEntries(apuestas.map((a) => [a.id, a.stake])),
            fee: 0,
          };
          const outcomes = Object.keys(pool.outcomes);
          const repartoPorResultado: Record<string, Reparto> = {};
          for (const id of outcomes) {
            repartoPorResultado[id] = sinMercado ? devolucion : settle(pool, apuestas, id);
          }

          /**
           * Y el compensador es quien mueve el dinero. Acuña el mercado entero,
           * lo quema con el ganador, y lo que sale es lo que se acredita. Si el
           * reparto quisiera pagar más colateral del que hay, esto lanza y la
           * liquidación **no ocurre** — antes se habría acreditado y el
           * descuadre aparecía semanas después (L5).
           */
          const compensacion = compensar({
            marketId: seed.id,
            outcomes,
            colateral: totalPool(pool),
            repartoPorResultado,
            ganador: estado.outcome,
          });

          /**
           * Y el libro lo cierra de una vez: lo que cobra cada quien, la
           * comisión a `tesoreria` y lo que nadie reclamó de vuelta a
           * `capital`, en **un solo asiento** (L3). Antes eran dos, y entre los
           * dos había un instante en que el pozo seguía teniendo la comisión
           * dentro; morir ahí la dejaba atrapada para siempre.
           *
           * La cámara devuelve las dos juntas —sólo cuenta contratos, y no debe
           * saber la diferencia— y es aquí donde se parten: ingreso contra
           * principal que vuelve (R-066).
           *
           * Pagar primero y marcar después: si el proceso muere en medio, el
           * dinero ya está acreditado y el estado se recalcula solo.
           */
          const fee = sinMercado ? 0 : (repartoPorResultado[estado.outcome]?.fee ?? 0);
          const cierre = store.liquidarMercado({
            marketId: seed.id,
            pagos: compensacion.pagosDeApuestas,
            fee,
            aCapital: compensacion.aLaCasa - fee,
          });
          resumen.acreditado += cierre.acreditado;
          resumen.comision += cierre.comision;
        }

        // "nadie acertó" es nadie **que cobre**: con subsidio, un lado ganador
        // que sólo tiene semilla no tiene ganadores, aunque el pozo no esté
        // vacío. Se devuelve todo y el subsidio vuelve a tesorería (R-024)
        const nadieAcerto =
          pozo !== undefined &&
          bettorStake(normalizePool(pozo), estado.outcome as string) <= 0;
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
