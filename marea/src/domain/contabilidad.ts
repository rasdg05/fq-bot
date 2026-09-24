/**
 * Contabilidad de partida doble.
 *
 * Sin esto no hay auditoría, y sin auditoría no hay dinero. Ya nos pasó una vez
 * en chico: `settle()` calculaba la comisión y **nadie la recibía** — se
 * restaba del reparto y desaparecía. Con puntos no se nota; con dinero es la
 * forma exacta de perderle la pista al dinero (R-064).
 *
 * La idea es vieja y por eso funciona: **todo movimiento tiene dos patas y la
 * suma de todas es cero**. Si algún día `cuadre()` no da cero, hay dinero
 * perdido y el sistema lo dice solo, en vez de que lo descubra alguien
 * revisando a mano seis meses después.
 *
 * Sirve igual en las dos arquitecturas de custodia que quedan en pie: el libro
 * es nuestro registro de qué le debemos a quién, viva el pozo en un contrato o
 * en la cuenta de la operación. Por eso se puede construir hoy sin esperar a la
 * opinión legal — ningún trabajo se tira.
 */

/**
 * Cuentas del sistema. Las de usuario y pozo se derivan por id.
 *
 * `tesoreria` y `capital` son **dos cuentas y nunca se netean** (R-066, L3). La
 * distinción no es burocracia: `tesoreria` dice *cuánto hemos ganado* y
 * `capital` dice *cuánto de lo nuestro está fuera o volvió*. Sumadas en una
 * sola caja, la casa se sentiría solvente con el principal que puso ella misma
 * — que es exactamente cómo quiebra un intermediario.
 *
 * Y ninguna de las dos comparte cuenta con `pozo:<id>`, que es colateral de
 * terceros. Un pozo con saldo después de liquidar es dinero de gente que no
 * llegó a su dueño.
 */
export const CUENTAS_SISTEMA = {
  /** Por dónde entra el dinero del mundo exterior. */
  entrada: "entrada",
  /** Por dónde sale. */
  salida: "salida",
  /** Lo que se queda la casa, en comisiones. Ingreso, no principal. */
  tesoreria: "tesoreria",
  /**
   * El capital propio de la casa. De aquí sale la semilla de cada mercado, y
   * aquí vuelve el colateral que al liquidar no reclamó nadie. Nunca recibe
   * comisiones: eso es `tesoreria`.
   */
  capital: "capital",
} as const;

export type CuentaSistema = (typeof CUENTAS_SISTEMA)[keyof typeof CUENTAS_SISTEMA];

/** `usuario:<id>` — lo que le debemos a una persona. */
export function cuentaUsuario(usuarioId: string): string {
  return `usuario:${usuarioId}`;
}

/** `pozo:<marketId>` — lo que está comprometido en un mercado. */
export function cuentaPozo(marketId: string): string {
  return `pozo:${marketId}`;
}

export type TipoAsiento =
  | "deposito"
  | "apuesta"
  | "liquidacion"
  | "devolucion"
  | "retiro"
  /** Semilla que la casa puede recuperar: es una posición pequeña. */
  | "semilla"
  /**
   * Semilla que la casa **no** puede recuperar: es un coste, no una posición
   * (R-067). Se distingue al escribir y no por un campo aparte porque es lo
   * que permite sumar el subsidio comprometido leyendo el libro — que es
   * justo lo que necesita el presupuesto de L9.
   */
  | "subsidio"
  | "prueba";

/** Una pata del asiento: a qué cuenta y cuánto. Positivo entra, negativo sale. */
export interface Pata {
  cuenta: string;
  monto: number;
}

export interface Asiento {
  tipo: TipoAsiento;
  patas: Pata[];
  at: string;
  /** Referencia al hecho que lo originó: mercado, apuesta, solicitud. */
  ref?: string;
}

export class LibroDesbalanceado extends Error {
  constructor(readonly diferencia: number) {
    super(`El asiento no cuadra: sobra ${diferencia}`);
    this.name = "LibroDesbalanceado";
  }
}

/**
 * Crea un asiento y **se niega a crearlo si no cuadra**. La validación va aquí,
 * al escribir, no en un reporte al final del mes: un asiento torcido que entra
 * al libro contamina todo lo que venga después.
 */
export function asiento(
  tipo: TipoAsiento,
  patas: Pata[],
  ref?: string,
  at: string = new Date().toISOString(),
): Asiento {
  if (patas.length < 2) {
    throw new LibroDesbalanceado(0);
  }
  const suma = patas.reduce((s, p) => s + p.monto, 0);
  // se admite el error de coma flotante, no un descuadre real
  if (Math.abs(suma) > 1e-9) throw new LibroDesbalanceado(suma);
  return { tipo, patas, at, ref };
}

/** Suma de todas las patas de todos los asientos. Tiene que ser cero. */
export function cuadre(libro: Asiento[]): number {
  let total = 0;
  for (const entrada of libro) {
    for (const pata of entrada.patas) total += pata.monto;
  }
  // se redondea el ruido de coma flotante: 1e-13 no es un descuadre
  return Math.abs(total) < 1e-9 ? 0 : total;
}

export function saldoDe(libro: Asiento[], cuenta: string): number {
  let total = 0;
  for (const entrada of libro) {
    for (const pata of entrada.patas) {
      if (pata.cuenta === cuenta) total += pata.monto;
    }
  }
  return Math.abs(total) < 1e-9 ? 0 : total;
}

/** Todos los saldos, por cuenta. Es la foto que se audita. */
export function saldos(libro: Asiento[]): Record<string, number> {
  const salida: Record<string, number> = {};
  for (const entrada of libro) {
    for (const pata of entrada.patas) {
      salida[pata.cuenta] = (salida[pata.cuenta] ?? 0) + pata.monto;
    }
  }
  for (const cuenta of Object.keys(salida)) {
    if (Math.abs(salida[cuenta]) < 1e-9) salida[cuenta] = 0;
  }
  return salida;
}

/**
 * Lo que la casa dice tener contra lo que el libro dice que se llevó. Si no
 * coinciden, la tesorería está contando algo que no pasó por contabilidad.
 */
export function conciliarTesoreria(
  libro: Asiento[],
  tesoreriaReportada: number,
): { cuadra: boolean; libro: number; reportado: number; diferencia: number } {
  const enLibro = saldoDe(libro, CUENTAS_SISTEMA.tesoreria);
  const diferencia = tesoreriaReportada - enLibro;
  return {
    cuadra: Math.abs(diferencia) < 1e-6,
    libro: enLibro,
    reportado: tesoreriaReportada,
    diferencia,
  };
}

/** La comisión de un mercado, tal como quedó asentada. */
export function comisionDeMercado(libro: Asiento[], marketId: string): number {
  let total = 0;
  for (const entrada of libro) {
    if (entrada.ref !== marketId) continue;
    for (const pata of entrada.patas) {
      if (pata.cuenta === CUENTAS_SISTEMA.tesoreria) total += pata.monto;
    }
  }
  return total;
}

/* -------------------------------------------------------------------------
 * Los asientos del ciclo de un mercado.
 *
 * Se construyen aquí, puros, y no a mano en el servidor. Un asiento escrito a
 * mano en cada sitio es un asiento que en el tercer sitio se escribe distinto,
 * y el día que se separan el descuadre no tiene autor.
 * ---------------------------------------------------------------------- */

/** Cómo se comporta la semilla de un mercado, visto desde el libro. */
export type ModoSemilla = "apuesta" | "subsidio";

/**
 * La casa siembra un mercado. El dinero sale de **su capital**, no de
 * `entrada`: una semilla no es dinero que llegó del mundo exterior, es
 * principal propio que se pone a trabajar (R-066).
 *
 * El tipo del asiento dice si vuelve o no vuelve. Un `subsidio` es un coste
 * comprometido desde el momento en que se escribe, y por eso se puede sumar
 * leyendo el libro en vez de fiándose de un contador aparte.
 */
export function asientoSemilla(
  marketId: string,
  monto: number,
  modo: ModoSemilla = "apuesta",
  at?: string,
): Asiento {
  return asiento(
    modo === "subsidio" ? "subsidio" : "semilla",
    [
      { cuenta: CUENTAS_SISTEMA.capital, monto: -monto },
      { cuenta: cuentaPozo(marketId), monto },
    ],
    marketId,
    at,
  );
}

export interface CierreDeMercado {
  marketId: string;
  /** Lo que cobra cada usuario, por id de usuario. */
  pagos: Record<string, number>;
  /** La comisión de la casa. Va a `tesoreria`. */
  fee: number;
  /** El colateral que no reclamó nadie. Vuelve a `capital`. */
  aCapital: number;
  at?: string;
}

/**
 * **Un solo asiento** para toda la liquidación: lo que sale del pozo, lo que
 * cobra cada quien, la comisión y lo que vuelve al capital.
 *
 * Que sea uno y no cuatro es la parte importante. Antes el pago y la comisión
 * eran asientos separados, y entre los dos existía un instante en que el libro
 * decía que el pozo todavía tenía la comisión dentro. Si el proceso moría ahí,
 * esa comisión se quedaba en el pozo **para siempre**: nadie la reclamaba,
 * nadie la echaba de menos, y el saldo del mercado no volvía a cero nunca. Con
 * un asiento, ese instante no existe.
 *
 * Y como `asiento()` se niega a construir lo que no cuadra, un cierre que no
 * vacíe el pozo exacto no llega a escribirse (L3).
 */
export function asientoLiquidacion(cierre: CierreDeMercado): Asiento {
  const patas: Pata[] = [];
  let total = 0;
  for (const [usuarioId, monto] of Object.entries(cierre.pagos)) {
    if (monto === 0) continue;
    patas.push({ cuenta: cuentaUsuario(usuarioId), monto });
    total += monto;
  }
  if (cierre.fee > 0) {
    patas.push({ cuenta: CUENTAS_SISTEMA.tesoreria, monto: cierre.fee });
    total += cierre.fee;
  }
  if (cierre.aCapital > 0) {
    patas.push({ cuenta: CUENTAS_SISTEMA.capital, monto: cierre.aCapital });
    total += cierre.aCapital;
  }
  patas.unshift({ cuenta: cuentaPozo(cierre.marketId), monto: -total });
  return asiento("liquidacion", patas, cierre.marketId, cierre.at);
}

/**
 * El subsidio que la casa tiene comprometido en un mercado, leído del libro.
 *
 * Es la cifra que el presupuesto de L9 tiene que sumar, y se lee del registro
 * auditable en vez de un contador aparte a propósito: un contador aparte es una
 * segunda fuente de verdad, y el día que se separen no se sabe cuál miente.
 */
export function subsidioComprometido(libro: Asiento[], marketId?: string): number {
  let total = 0;
  for (const entrada of libro) {
    if (entrada.tipo !== "subsidio") continue;
    if (marketId !== undefined && entrada.ref !== marketId) continue;
    for (const pata of entrada.patas) {
      if (pata.cuenta === CUENTAS_SISTEMA.capital) total -= pata.monto;
    }
  }
  return Math.abs(total) < 1e-9 ? 0 : total;
}

/**
 * Los mercados que ya se liquidaron y **aún tienen saldo en su pozo**.
 *
 * Es el auditor de L3, y existe porque la regla escrita recuerda pero sólo la
 * verificación impide: un saldo que se queda en `pozo:<id>` después de pagar es
 * colateral de terceros que no llegó a nadie, y no lo detecta `cuadre()` —el
 * libro sigue sumando cero, sólo que con dinero atrapado en la cuenta
 * equivocada—. Vacío = sano.
 */
export function pozosSinVaciar(libro: Asiento[], marketIds: string[]): Record<string, number> {
  const salida: Record<string, number> = {};
  for (const marketId of marketIds) {
    const saldo = saldoDe(libro, cuentaPozo(marketId));
    if (saldo !== 0) salida[marketId] = saldo;
  }
  return salida;
}
