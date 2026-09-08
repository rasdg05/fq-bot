/**
 * El puente entre la capa que fija precio (parimutuel) y la cámara de
 * compensación (`pozo.ts`). Es la pieza que faltaba para que `settle()` deje de
 * mover dinero y pase a ser lo que su nombre promete: **un productor de
 * reparto**. Quien mueve saldos es el compensador.
 *
 * ## Por qué existe un archivo aparte
 *
 * `pozo.ts` no sabe de precios ni de comisiones, y no debe saberlo: el día que
 * la cámara conozca el fee, tarde o temprano uno sale del colateral (R-066).
 * `parimutuel.ts` no sabe de conjuntos completos, y tampoco debe: es la capa de
 * precio, y mañana puede ser un libro maker/taker encima del mismo compensador.
 * La traducción entre los dos tiene que vivir en algún sitio, y ese sitio es
 * éste — explícito, puro y con nombre.
 *
 * ## La traducción, que es más literal de lo que parece
 *
 * Un mercado parimutuel con pozo `T` es exactamente `T` conjuntos completos. Lo
 * que no es obvio: **cada resultado tiene su reparto, no sólo el que gana**. Si
 * gana `o`, el pozo entero se va a alguien —quienes acertaron, la tesorería por
 * la comisión, y lo que sobre— y eso suma `T`. Repetido para cada `o`, eso es
 * literalmente la definición de conjunto completo:
 *
 *     contratos del resultado o  =  quién cobraría si ganara o
 *     Σ contratos de o           =  T                          ∀ o
 *
 * De ahí sale gratis lo que R-065 promete: la exposición neta del pozo es cero
 * en **todos** los resultados, no sólo en el que salió. Y es aritmética, no una
 * comprobación al final.
 *
 * ## Lo que esto atrapa y antes no se veía
 *
 * El resto (`T − Σ pagos − comisión`) se calcula, no se supone. Si sale
 * **negativo**, el reparto está pagando más colateral del que hay, y `acunar()`
 * lo rechaza al escribir con `PozoInconsistente`. Eso es L5 con dientes: no un
 * informe a fin de mes, sino una liquidación que no ocurre. Y como se construye
 * el reparto de todos los resultados, un sobrepago **en cualquiera** se detecta
 * el día de la liquidación, no el día en que ese resultado por fin sale.
 */

import {
  abrir,
  acunar,
  liquidar,
  PozoInconsistente,
  type OutcomeId,
  type Asignacion,
  type Pozo,
  type TenedorId,
} from "./pozo";

/**
 * La casa, como tenedor de contratos. No es un jugador: es donde aterrizan la
 * comisión y el colateral que nadie reclamó, para que **todo** el pozo tenga
 * dueño. Un colateral sin dueño es colateral que se pierde de vista.
 */
export const TESORERIA: TenedorId = "tesoreria";

/** Lo que produce la capa de precio para un resultado concreto. */
export interface Reparto {
  /** Lo que cobra cada apuesta, por id de apuesta. Lo que devuelve `settle`. */
  payouts: Record<string, number>;
  /** Lo que se lleva la casa de comisión si gana ese resultado. */
  fee: number;
}

/** Ruido de coma flotante admisible, el mismo que usa el compensador. */
const EPSILON = 1e-9;

/**
 * Traduce el reparto de un resultado a la asignación de sus contratos.
 *
 * El resto va a tesorería **por construcción**, no por redondeo: es lo que
 * queda del colateral después de pagar a quien acertó y de la comisión. En un
 * mercado en modo `"apuesta"` ese resto es la parte de la semilla que le tocaba
 * cobrar a la casa; con subsidio es cero salvo que nadie acertara.
 */
export function asignacionDe(colateral: number, reparto: Reparto): Record<TenedorId, number> {
  const salida: Record<TenedorId, number> = {};
  let repartido = 0;
  for (const [id, monto] of Object.entries(reparto.payouts)) {
    if (monto === 0) continue;
    if (!Number.isFinite(monto) || monto < 0) {
      throw new PozoInconsistente(`pago inválido a ${id}: ${monto}`);
    }
    salida[id] = (salida[id] ?? 0) + monto;
    repartido += monto;
  }
  const aTesoreria = colateral - repartido - reparto.fee;
  if (aTesoreria < -EPSILON) {
    // el reparto quiere pagar más de lo que hay: no se liquida, se para
    throw new PozoInconsistente(
      `el reparto entrega ${repartido + reparto.fee} con ${colateral} de colateral`,
    );
  }
  const restoLimpio = Math.abs(aTesoreria) < EPSILON ? 0 : aTesoreria;
  const casa = reparto.fee + restoLimpio;
  if (casa > 0) salida[TESORERIA] = (salida[TESORERIA] ?? 0) + casa;
  return salida;
}

export interface Compensacion {
  /** Lo que cobra cada tenedor: apuestas por su id, y `tesoreria`. */
  pagos: Record<TenedorId, number>;
  /** Lo que sale del pozo. Igual al colateral que retenía, siempre (L5). */
  pagado: number;
  /** Sólo lo de las apuestas, listo para acreditar. Sin la casa. */
  pagosDeApuestas: Record<string, number>;
  /** Lo que le toca a la casa: comisión más el colateral que nadie reclamó. */
  aTesoreria: number;
  /** El pozo después de quemar: sin colateral y sin contratos. */
  pozo: Pozo;
}

/**
 * Acuña el mercado entero, lo quema con el ganador y devuelve lo que hay que
 * acreditar. Es el único camino por el que un reparto se convierte en saldos.
 *
 * `repartoPorResultado` tiene que traer **todos** los resultados: es lo que
 * convierte «el pozo cuadra con este ganador» en «el pozo cuadra pase lo que
 * pase», que es lo único que se puede llamar neutralidad (R-065, L2).
 */
export function compensar(input: {
  marketId: string;
  outcomes: readonly OutcomeId[];
  colateral: number;
  repartoPorResultado: Record<OutcomeId, Reparto>;
  ganador: OutcomeId;
}): Compensacion {
  const { marketId, outcomes, colateral, repartoPorResultado, ganador } = input;

  const vacio = abrir(marketId, outcomes);
  if (colateral <= 0) {
    // un mercado sin colateral no reparte nada, y liquidarlo no es un error
    return {
      pagos: {},
      pagado: 0,
      pagosDeApuestas: {},
      aTesoreria: 0,
      pozo: liquidar(vacio, ganador).pozo,
    };
  }

  const asignacion: Asignacion = {};
  for (const outcome of outcomes) {
    const reparto = repartoPorResultado[outcome];
    if (!reparto) {
      throw new PozoInconsistente(`falta el reparto del resultado ${outcome}`);
    }
    asignacion[outcome] = asignacionDe(colateral, reparto);
  }

  const { pagos, pagado, pozo } = liquidar(acunar(vacio, colateral, asignacion), ganador);
  const pagosDeApuestas: Record<string, number> = {};
  for (const [tenedor, monto] of Object.entries(pagos)) {
    if (tenedor !== TESORERIA) pagosDeApuestas[tenedor] = monto;
  }
  return { pagos, pagado, pagosDeApuestas, aTesoreria: pagos[TESORERIA] ?? 0, pozo };
}
