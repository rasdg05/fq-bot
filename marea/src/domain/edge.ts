import type { Market } from "./types";

/**
 * Umbral de Edge, en puntos porcentuales. Decisión de producto cerrada:
 * por debajo de esto la diferencia es ruido y no se muestra (R-001).
 * Vive en el dominio, no en la vista: ningún componente lo re-implementa.
 */
export const EDGE_MIN_PP = 4;

/**
 * Edge en puntos porcentuales, o `null` si no supera el umbral.
 * Ambas probabilidades entran en 0..1.
 */
export function computeEdge(
  marketProbability: number,
  mareaProbability: number | undefined,
): number | null {
  if (mareaProbability === undefined || Number.isNaN(mareaProbability)) {
    return null;
  }
  const pp = (mareaProbability - marketProbability) * 100;
  const rounded = Math.round(pp * 10) / 10;
  return Math.abs(rounded) >= EDGE_MIN_PP ? rounded : null;
}

/** Aplica la regla de Edge a un mercado crudo. Único camino legal al campo `edge`. */
export function withEdge(market: Omit<Market, "edge">): Market {
  return {
    ...market,
    edge: computeEdge(market.probability, market.mareaProbability),
  };
}

export function hasEdge(market: Market): boolean {
  return market.edge !== null && Math.abs(market.edge) >= EDGE_MIN_PP;
}

/** `+7` / `-5` — el signo siempre visible, para que el Edge no dependa del color (R-005). */
export function formatEdgePp(edgePp: number): string {
  const value = Math.abs(edgePp) % 1 === 0 ? Math.abs(edgePp).toFixed(0) : Math.abs(edgePp).toFixed(1);
  return `${edgePp > 0 ? "+" : "−"}${value}`;
}
