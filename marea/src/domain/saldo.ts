import type { PointsLedger } from "@/domain/points";

/**
 * El saldo, en un solo sitio.
 *
 * Antes había tres campos que decían "saldo" y dos que se escribían encima:
 *
 *  - `points.balance`, el ledger local del motor de puntos;
 *  - `cuenta.puntos`, lo que dice el servidor;
 *  - `wallet.balance`, en dólares, para el motor con dinero.
 *
 * El reducer fusionaba los dos primeros —`case "cuenta"` pisaba `balance` con
 * `cuenta.puntos` conservando los `entries`— y por otro lado `creditSettlements`
 * sumaba los pagos al mismo campo. Como el servidor **ya** acredita esos pagos
 * a `usuario.puntos`, entrar al portafolio los sumaba por segunda vez y volver
 * al feed los borraba: el saldo saltaba entre 700 y 900 sin que nadie apostara.
 *
 * La regla ahora es una sola frase: **si hay cuenta, manda el servidor.** El
 * ledger local sigue existiendo, pero sólo para el modo sin servidor. Nadie
 * vuelve a escribir en los dos.
 *
 * Todo lo que muestra saldo llama aquí. No es por elegancia: mientras el header
 * y el portafolio calculaban cada uno lo suyo, podían diferir, y diferían.
 */

/**
 * Cuánto puede envejecer el saldo antes de volver a pedirlo al montar una
 * pantalla que lo enseña. Diez segundos: suficiente para que ir y volver entre
 * Mercados y Portafolio no dispare una petición por toque, y corto para que
 * nadie mire un número viejo sin darse cuenta.
 */
export const FRESCURA_SALDO_MS = 10_000;

/** Lo mínimo que hace falta para saber el saldo. Un trozo de `AppState`. */
export interface FuenteDeSaldo {
  cuenta: { puntos: number } | null;
  points: PointsLedger;
  wallet: { balance: number } | null;
  /** Movimientos confirmados por el usuario que el servidor todavía no acusa. */
  optimistas: MovimientoOptimista[];
}

/**
 * Un movimiento que ya se le enseñó a la persona y que el servidor aún no ha
 * confirmado. Se guarda como **delta con nombre**, no como una foto del saldo
 * anterior: con dos acciones en vuelo, la segunda foto captura el valor
 * optimista de la primera, y deshacer la primera restaura un número que ya no
 * era verdad. Sumar y restar deltas se comporta igual en cualquier orden.
 */
export interface MovimientoOptimista {
  id: string;
  /** Positivo suma, negativo resta. Es exactamente lo que el usuario confirmó. */
  delta: number;
}

/**
 * El saldo que se pinta, en puntos o en dólares según el motor.
 *
 * `puntos` es el modo del producto hoy (`parimutuel_points`). Con dinero, el
 * saldo vive en la wallet y los optimistas no aplican: ahí la confirmación es
 * on-chain y no la inventamos nosotros.
 */
export function saldoVisible(fuente: FuenteDeSaldo, puntos: boolean): number {
  if (!puntos) return fuente.wallet?.balance ?? 0;
  const base = fuente.cuenta ? fuente.cuenta.puntos : fuente.points.balance;
  const pendiente = fuente.optimistas.reduce((total, m) => total + m.delta, 0);
  // el saldo nunca se enseña en negativo: sin crédito, tampoco visualmente
  return Math.max(0, base + pendiente);
}
