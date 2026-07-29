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

/** Cuentas del sistema. Las de usuario y pozo se derivan por id. */
export const CUENTAS_SISTEMA = {
  /** Por dónde entra el dinero del mundo exterior. */
  entrada: "entrada",
  /** Por dónde sale. */
  salida: "salida",
  /** Lo que se queda la casa, en comisiones. */
  tesoreria: "tesoreria",
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
  | "semilla"
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
