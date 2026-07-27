/**
 * Feature flags. Único lugar donde se declara qué es real y qué es simulado
 * en esta build — el copy honesto se deriva de aquí, no de suposiciones (R-011).
 */
export type TradeExecutionMode = "aggregated" | "native";
/**
 * Qué motor de mercado corre.
 *  - `parimutuel_points`: mercados propios de Latam, apostando puntos. Es la
 *    Fase 1 del roadmap: cero custodia, cero riesgo regulatorio.
 *  - `parimutuel_money`: el mismo motor con dinero. Bloqueado hasta que exista
 *    opinión legal y contrato de custodia (ver vault/COMPLIANCE.md).
 *  - `aggregated`: ruteo a casas externas, sin mercado propio.
 */
export type MarketEngine = "parimutuel_points" | "parimutuel_money" | "aggregated";
export type DepositProvider = "onramp" | "transfer_only" | "none";

export interface Flags {
  /** Motor de mercado vigente. Define la unidad y el copy honesto. */
  market_engine: MarketEngine;
  /** Los mercados vienen del adapter mock, no de un agregador real. */
  mock_data: boolean;
  /** Qué caminos de depósito están disponibles. */
  deposit_provider: DepositProvider;
  /** Cómo se ejecuta una operación. En soft launch: agregación. */
  trade_execution_mode: TradeExecutionMode;
  /** Envío de errores a un servicio externo. */
  error_reporting: boolean;
  /**
   * Aplica la tabla de elegibilidad por país antes de depositar u operar.
   * Apagado en la build simulada (no se mueve dinero); encenderlo es requisito
   * para cualquier build con dinero real (ver vault/COMPLIANCE.md).
   */
  eligibility_enforced: boolean;
}

export const FLAGS: Flags = {
  market_engine: "parimutuel_points",
  mock_data: true,
  deposit_provider: "onramp",
  trade_execution_mode: "aggregated",
  error_reporting: false,
  eligibility_enforced: false,
};

/** Se juega con puntos: nada de esto se cambia por dinero (R-026). */
export function isPointsMode(flags: Flags = FLAGS): boolean {
  return flags.market_engine === "parimutuel_points";
}

/** Mercado propio con motor parimutuel, en cualquiera de sus dos unidades. */
export function isOwnMarketMode(flags: Flags = FLAGS): boolean {
  return flags.market_engine !== "aggregated";
}

/** Override para pruebas y para simular caídas de proveedor. */
export function withFlags(overrides: Partial<Flags>): Flags {
  return { ...FLAGS, ...overrides };
}
