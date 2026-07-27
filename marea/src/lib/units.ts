import { FLAGS, isPointsMode } from "./flags";
import { usd } from "./format";

/**
 * Unidad en la que se apuesta. Sale del flag del motor, no de suposiciones:
 * si la build corre con puntos, en ningún lugar de la interfaz aparece un
 * símbolo de moneda (R-026).
 */
export function unitLabel(plural = true): string {
  if (isPointsMode()) return plural ? "puntos" : "punto";
  return "USD";
}

export function formatStake(amount: number): string {
  if (isPointsMode()) {
    return `${new Intl.NumberFormat("es-MX").format(Math.round(amount))} pts`;
  }
  return usd(amount);
}

/** Montos preestablecidos del selector, acordes a la unidad. */
export function stakePresets(): number[] {
  return isPointsMode() ? [50, 100, 250, 500] : [5, 10, 25, 50];
}

/** ¿Hay que declarar que esto no es dinero? */
export function needsPointsDisclaimer(): boolean {
  return isPointsMode();
}

export { FLAGS };
