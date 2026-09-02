/**
 * Cámara de compensación. El pozo **no es un jugador**: es la caja donde se
 * cruzan dos partes y donde el colateral espera hasta que el oráculo hable.
 *
 * La pieza es vieja y aburrida a propósito, que es lo que uno quiere en la capa
 * que guarda dinero ajeno:
 *
 *     1 unidad de colateral  ⇄  1 contrato de CADA resultado
 *
 * A eso se le llama un *conjunto completo*. De ahí sale la única propiedad que
 * importa: al resolver, **exactamente un resultado paga 1** y los demás pagan 0,
 * así que la obligación máxima del pozo es siempre igual al colateral que
 * retiene, con cualquier ganador. El resultado del mercado no entra en la
 * ecuación del pozo (R-065).
 *
 *     colateral      C = conjuntos
 *     obligación     O = conjuntos          (uno de cada resultado; uno paga 1)
 *     P&L del pozo   C − O = 0              ∀ resultado
 *
 * ## Lo que este módulo deliberadamente NO sabe
 *
 * - **Precios.** Quién paga cuánto por un contrato es la capa de precio
 *   (parimutuel hoy, libro maker/taker después). La cámara sólo cuenta
 *   contratos. Por eso el mismo compensador sirve para los dos motores y no hay
 *   dos matemáticas de dinero (R-044).
 * - **Comisiones.** El fee y el colateral no comparten cuenta (R-066, L3). Si
 *   este archivo supiera de fees, tarde o temprano uno saldría del colateral.
 * - **La hora.** No hay relojes aquí: las mismas entradas dan las mismas
 *   salidas, siempre.
 *
 * ## La unidad
 *
 * Es agnóstico: puntos o dinero, lo decide `FLAGS.market_engine`, no este
 * archivo. En cadena, un conjunto es una unidad entera del ERC-1155 y el
 * colateral son unidades mínimas de USDC; aquí se admiten números con la misma
 * tolerancia de coma flotante que usa el libro contable.
 */

export type OutcomeId = string;

/** Quién tiene un contrato. Un usuario, o la casa cuando pone subsidio. */
export type TenedorId = string;

/** Ruido de coma flotante admisible. Un descuadre real nunca es 1e-13. */
const EPSILON = 1e-9;

export interface Pozo {
  readonly marketId: string;
  /** Los resultados posibles. Al menos dos, sin repetir. */
  readonly outcomes: readonly OutcomeId[];
  /** Conjuntos completos vivos = colateral retenido. */
  readonly conjuntos: number;
  /** `contratos[outcomeId][tenedorId]`. Cada resultado suma exactamente `conjuntos`. */
  readonly contratos: Readonly<Record<OutcomeId, Readonly<Record<TenedorId, number>>>>;
}

/** Reparto de una acuñación: por resultado, quién recibe cuántos de los `q`. */
export type Asignacion = Record<OutcomeId, Record<TenedorId, number>>;

/**
 * Se lanza cuando una operación dejaría el pozo en un estado que viola la
 * neutralidad. Se lanza **al escribir**, no en un reporte al final del mes: un
 * pozo torcido contamina todo lo que venga después.
 */
export class PozoInconsistente extends Error {
  constructor(readonly motivo: string) {
    super(`Pozo inconsistente: ${motivo}`);
    this.name = "PozoInconsistente";
  }
}

function esFinitoNoNegativo(n: number): boolean {
  return Number.isFinite(n) && n >= 0;
}

function limpiar(n: number): number {
  return Math.abs(n) < EPSILON ? 0 : n;
}

/** Abre un pozo vacío. Sin colateral y sin contratos: la casa no pone nada. */
export function abrir(marketId: string, outcomes: readonly OutcomeId[]): Pozo {
  if (outcomes.length < 2) {
    throw new PozoInconsistente("un mercado necesita al menos dos resultados");
  }
  if (new Set(outcomes).size !== outcomes.length) {
    throw new PozoInconsistente("hay resultados repetidos");
  }
  const contratos: Record<OutcomeId, Record<TenedorId, number>> = {};
  for (const id of outcomes) contratos[id] = {};
  return { marketId, outcomes: [...outcomes], conjuntos: 0, contratos };
}

/** El colateral retenido. Por construcción, es el número de conjuntos vivos. */
export function colateral(pozo: Pozo): number {
  return pozo.conjuntos;
}

export function contratosDe(pozo: Pozo, outcome: OutcomeId, tenedor: TenedorId): number {
  return pozo.contratos[outcome]?.[tenedor] ?? 0;
}

/** Cuántos contratos de un resultado hay repartidos, sumando a todos los tenedores. */
export function emitidos(pozo: Pozo, outcome: OutcomeId): number {
  const porTenedor = pozo.contratos[outcome];
  if (!porTenedor) return 0;
  let total = 0;
  for (const cantidad of Object.values(porTenedor)) total += cantidad;
  return limpiar(total);
}

/**
 * Lo que el pozo debería pagar si ganara `outcome`, menos lo que retiene.
 *
 * **Tiene que ser cero para todos los resultados, siempre.** Es la forma
 * ejecutable de "el pozo nunca es contraparte" (L2): si alguna vez sale
 * distinto de cero, el pozo tiene posición y dejó de ser una cámara.
 */
export function exposicionNeta(pozo: Pozo, outcome: OutcomeId): number {
  return limpiar(emitidos(pozo, outcome) - pozo.conjuntos);
}

/**
 * Revisa el pozo entero y devuelve los problemas encontrados. Vacío = sano.
 *
 * Se expone a propósito en vez de dejarlo dentro de las operaciones: el
 * vigilante externo (L14) corre esto mismo contra el estado en cadena, y una
 * prueba puede llamarlo después de **cada** paso de una secuencia.
 */
export function auditar(pozo: Pozo): string[] {
  const problemas: string[] = [];
  if (!esFinitoNoNegativo(pozo.conjuntos)) {
    problemas.push(`conjuntos inválidos: ${pozo.conjuntos}`);
  }
  for (const outcome of pozo.outcomes) {
    if (!pozo.contratos[outcome]) {
      problemas.push(`falta el resultado ${outcome} en los contratos`);
      continue;
    }
    for (const [tenedor, cantidad] of Object.entries(pozo.contratos[outcome])) {
      if (!esFinitoNoNegativo(cantidad)) {
        problemas.push(`contratos inválidos de ${tenedor} en ${outcome}: ${cantidad}`);
      }
    }
    const exposicion = exposicionNeta(pozo, outcome);
    if (exposicion !== 0) {
      problemas.push(
        `exposición neta en ${outcome}: ${exposicion} (emitidos ${emitidos(pozo, outcome)} vs colateral ${pozo.conjuntos})`,
      );
    }
  }
  const extra = Object.keys(pozo.contratos).filter((id) => !pozo.outcomes.includes(id));
  for (const id of extra) problemas.push(`resultado desconocido en los contratos: ${id}`);
  return problemas;
}

/** Copia profunda del mapa de contratos, para no mutar el pozo de entrada. */
function copiar(
  contratos: Pozo["contratos"],
): Record<OutcomeId, Record<TenedorId, number>> {
  const salida: Record<OutcomeId, Record<TenedorId, number>> = {};
  for (const [outcome, porTenedor] of Object.entries(contratos)) {
    salida[outcome] = { ...porTenedor };
  }
  return salida;
}

function sumar(mapa: Record<TenedorId, number>): number {
  let total = 0;
  for (const valor of Object.values(mapa)) total += valor;
  return total;
}

/**
 * Acuña `q` conjuntos completos y reparte los contratos según `asignacion`.
 *
 * Entra `q` de colateral y salen `q` contratos de **cada** resultado. Por eso
 * la asignación de cada resultado tiene que sumar exactamente `q`: repartir de
 * menos dejaría contratos sin dueño (y colateral que nadie reclama), repartir
 * de más crearía obligación sin respaldo. Las dos cosas son la misma falla —
 * el pozo tomando posición— y por eso se rechazan al escribir.
 */
export function acunar(pozo: Pozo, q: number, asignacion: Asignacion): Pozo {
  if (!esFinitoNoNegativo(q) || q <= 0) {
    throw new PozoInconsistente(`acuñación inválida: ${q}`);
  }
  for (const outcome of pozo.outcomes) {
    const reparto = asignacion[outcome];
    if (!reparto) {
      throw new PozoInconsistente(`la acuñación no reparte el resultado ${outcome}`);
    }
    for (const [tenedor, cantidad] of Object.entries(reparto)) {
      if (!esFinitoNoNegativo(cantidad)) {
        throw new PozoInconsistente(`reparto inválido a ${tenedor} en ${outcome}: ${cantidad}`);
      }
    }
    if (Math.abs(sumar(reparto) - q) > EPSILON) {
      throw new PozoInconsistente(
        `el reparto de ${outcome} suma ${sumar(reparto)} y debería sumar ${q}`,
      );
    }
  }
  const desconocidos = Object.keys(asignacion).filter((id) => !pozo.outcomes.includes(id));
  if (desconocidos.length > 0) {
    throw new PozoInconsistente(`la acuñación menciona resultados que no existen: ${desconocidos.join(", ")}`);
  }

  const contratos = copiar(pozo.contratos);
  for (const outcome of pozo.outcomes) {
    for (const [tenedor, cantidad] of Object.entries(asignacion[outcome])) {
      if (cantidad === 0) continue;
      contratos[outcome][tenedor] = (contratos[outcome][tenedor] ?? 0) + cantidad;
    }
  }
  return { ...pozo, conjuntos: pozo.conjuntos + q, contratos };
}

/**
 * Atajo para el cruce de dos partes, que es el caso normal: `comprador` se
 * queda los `q` contratos de `outcome` y `contraparte` los de todo lo demás.
 * En el binario es exactamente "yo tomo SÍ, tú tomas NO".
 */
export function cruce(
  pozo: Pozo,
  q: number,
  outcome: OutcomeId,
  comprador: TenedorId,
  contraparte: TenedorId,
): Pozo {
  if (!pozo.outcomes.includes(outcome)) {
    throw new PozoInconsistente(`resultado desconocido: ${outcome}`);
  }
  const asignacion: Asignacion = {};
  for (const id of pozo.outcomes) {
    asignacion[id] = { [id === outcome ? comprador : contraparte]: q };
  }
  return acunar(pozo, q, asignacion);
}

/**
 * Lo contrario de acuñar: quien tiene `q` contratos de **todos** los resultados
 * tiene un conjunto completo, y un conjunto completo vale 1 pase lo que pase.
 * Puede devolverlo y recuperar su colateral sin esperar al oráculo.
 *
 * Es la salida honesta de una posición antes de que resuelva el mercado, y la
 * razón por la que el colateral nunca queda atrapado.
 */
export function fusionar(
  pozo: Pozo,
  q: number,
  tenedor: TenedorId,
): { pozo: Pozo; colateralLiberado: number } {
  if (!esFinitoNoNegativo(q) || q <= 0) {
    throw new PozoInconsistente(`fusión inválida: ${q}`);
  }
  for (const outcome of pozo.outcomes) {
    const tiene = contratosDe(pozo, outcome, tenedor);
    if (tiene + EPSILON < q) {
      throw new PozoInconsistente(
        `${tenedor} no tiene un conjunto completo: le faltan ${q - tiene} de ${outcome}`,
      );
    }
  }
  const contratos = copiar(pozo.contratos);
  for (const outcome of pozo.outcomes) {
    contratos[outcome][tenedor] = limpiar(contratos[outcome][tenedor] - q);
    if (contratos[outcome][tenedor] === 0) delete contratos[outcome][tenedor];
  }
  return {
    pozo: { ...pozo, conjuntos: limpiar(pozo.conjuntos - q), contratos },
    colateralLiberado: q,
  };
}

/**
 * Mueve contratos de un tenedor a otro. No toca el colateral: es el mercado
 * secundario, no una entrada ni una salida de dinero del pozo.
 */
export function transferir(
  pozo: Pozo,
  outcome: OutcomeId,
  de: TenedorId,
  a: TenedorId,
  q: number,
): Pozo {
  if (!pozo.outcomes.includes(outcome)) {
    throw new PozoInconsistente(`resultado desconocido: ${outcome}`);
  }
  if (!esFinitoNoNegativo(q) || q <= 0) {
    throw new PozoInconsistente(`transferencia inválida: ${q}`);
  }
  const tiene = contratosDe(pozo, outcome, de);
  if (tiene + EPSILON < q) {
    throw new PozoInconsistente(`${de} sólo tiene ${tiene} de ${outcome}`);
  }
  if (de === a) return pozo;

  const contratos = copiar(pozo.contratos);
  contratos[outcome][de] = limpiar(contratos[outcome][de] - q);
  if (contratos[outcome][de] === 0) delete contratos[outcome][de];
  contratos[outcome][a] = (contratos[outcome][a] ?? 0) + q;
  return { ...pozo, contratos };
}

export interface Liquidacion {
  /** Lo que cobra cada tenedor: 1 por contrato del resultado ganador. */
  pagos: Record<TenedorId, number>;
  /** Lo que sale del pozo. Igual al colateral que retenía, siempre. */
  pagado: number;
  /** El pozo después: sin colateral y sin contratos. */
  pozo: Pozo;
}

/**
 * Quema los conjuntos y paga. Cada contrato del resultado ganador vale 1; los
 * demás valen 0.
 *
 * `pagado` es igual a `colateral(pozo)` **con cualquier ganador**, y no porque
 * lo comprobemos al final: es que los contratos del ganador son exactamente los
 * conjuntos acuñados. Ésa es toda la neutralidad del pozo, y es aritmética, no
 * una promesa.
 *
 * Lo que este módulo **no** hace: descontar comisión (R-066) ni repartir la
 * parte de la semilla entre quienes acertaron (R-067). Eso vive en la capa que
 * conoce el precio y el subsidio; aquí sólo se quema y se paga.
 */
export function liquidar(pozo: Pozo, ganador: OutcomeId): Liquidacion {
  if (!pozo.outcomes.includes(ganador)) {
    throw new PozoInconsistente(`el ganador ${ganador} no es un resultado de este mercado`);
  }
  const problemas = auditar(pozo);
  if (problemas.length > 0) {
    throw new PozoInconsistente(`no se liquida un pozo torcido: ${problemas[0]}`);
  }

  const pagos: Record<TenedorId, number> = {};
  let pagado = 0;
  for (const [tenedor, cantidad] of Object.entries(pozo.contratos[ganador])) {
    if (cantidad === 0) continue;
    pagos[tenedor] = (pagos[tenedor] ?? 0) + cantidad;
    pagado += cantidad;
  }

  const vacio: Record<OutcomeId, Record<TenedorId, number>> = {};
  for (const id of pozo.outcomes) vacio[id] = {};
  return {
    pagos,
    pagado: limpiar(pagado),
    pozo: { ...pozo, conjuntos: 0, contratos: vacio },
  };
}
