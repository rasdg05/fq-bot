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
  onDeadline,
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
  /** Los que ya pasaron el plazo largo: se anularon y se devolvió lo apostado. */
  incobrables: string[];
  /** Mercados que desaparecieron del catálogo con apuestas dentro. Se devolvió. */
  huerfanos: string[];
  acreditado: number;
  errores: string[];
}

function debeLeerse(seed: OwnMarketSeed, fase: string, ahora: number): boolean {
  // `atorado` se sigue intentando: estar atorado es una señal para que alguien
  // mire, no una condena. Un 403 pasajero de la fuente no congela un mercado
  if (fase === "cerrado" || fase === "leido" || fase === "atorado") return true;
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
    incobrables: [],
    huerfanos: [],
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

      /**
       * El plazo. Un mercado que cerró y no se resolvió no se queda callado
       * para siempre: a los 7 días se marca `atorado` —y **aparece** en el
       * resumen— y a los 30 se da por incobrable y se devuelve todo.
       *
       * Va **después** de intentar leer, no antes: si la fuente contestó en
       * esta misma corrida, el mercado se resolvió y no hay atasco que marcar.
       */
      estado = onDeadline(estado, seed.resolution, ahora);
      if (estado.phase === "atorado") {
        resumen.atorados.push(seed.id);
        if (estado.incobrable) resumen.incobrables.push(seed.id);
      }

      /**
       * Y lo incobrable se devuelve, por el mismo camino que cualquier otra
       * devolución. Quedarse con el pozo de un mercado que nadie pudo ganar es
       * exactamente lo que hace una casa (R-024), y dejarlo congelado no es más
       * prudente: es sólo más callado.
       */
      if (estado.incobrable && estado.phase === "atorado") {
        const pozo = store.pozo(seed.id);
        const apuestas = store.apuestasDeMercado(seed.id);
        if (pozo && apuestas.length > 0) {
          const pool = normalizePool(pozo);
          const devolucion: Reparto = {
            payouts: Object.fromEntries(apuestas.map((a) => [a.id, a.stake])),
            fee: 0,
          };
          const outcomes = Object.keys(pool.outcomes);
          const repartoPorResultado: Record<string, Reparto> = {};
          for (const id of outcomes) repartoPorResultado[id] = devolucion;
          const compensacion = compensar({
            marketId: seed.id,
            outcomes,
            colateral: totalPool(pool),
            repartoPorResultado,
            ganador: outcomes[0],
          });
          const cierre = store.liquidarMercado({
            marketId: seed.id,
            pagos: compensacion.pagosDeApuestas,
            fee: 0,
            aCapital: compensacion.aLaCasa,
          });
          resumen.acreditado += cierre.acreditado;
          if (cierre.acreditado > 0 || apuestas.every((a) => a.pagado !== undefined)) {
            resumen.anulados += 1;
            estado = { ...estado, phase: "devuelto" };
          }
        } else {
          // sin apuestas no hay a quién devolver: se cierra y se deja dicho
          estado = { ...estado, phase: "devuelto" };
        }
      }

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

  /**
   * Y al final, las **huérfanas**: apuestas sin pagar cuyo mercado ya no está
   * en el catálogo.
   *
   * El bucle de arriba no puede verlas — itera sobre las semillas, y la semilla
   * es justo lo que falta. Se vio en producción: el portafolio de alguien
   * mostraba `latam-libertadores-br` con su apuesta dentro, sin título siquiera,
   * y ninguna corrida del ciclo iba a mirarla nunca.
   *
   * Si el mercado desapareció, nadie puede acertar: se devuelve íntegro y sin
   * comisión, que es lo mismo que se hace con un mercado que nadie ganó
   * (R-024). Quedarse con esos puntos porque el mercado se perdió por el camino
   * sería cobrar por nuestro propio error.
   */
  for (const [marketId, _total] of Object.entries(store.apuestasHuerfanas(seeds.map((s) => s.id)))) {
    try {
      const apuestas = store.apuestasDeMercado(marketId);
      if (apuestas.length === 0) continue;
      const pozo = store.pozo(marketId);
      const pool = pozo ? normalizePool(pozo) : undefined;
      const cierre = store.liquidarMercado({
        marketId,
        pagos: Object.fromEntries(apuestas.map((a) => [a.id, a.stake])),
        fee: 0,
        // lo que quede del pozo después de devolver era semilla nuestra
        aCapital: pool
          ? Math.max(0, totalPool(pool) - apuestas.reduce((t, a) => t + a.stake, 0))
          : 0,
      });
      if (cierre.acreditado > 0) {
        resumen.acreditado += cierre.acreditado;
        resumen.anulados += 1;
        resumen.huerfanos.push(marketId);
      }
    } catch (error) {
      resumen.errores.push(
        `huérfana ${marketId}: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  return resumen;
}
