/**
 * Feature flags. Único lugar donde se declara qué es real y qué es simulado
 * en esta build — el copy honesto se deriva de aquí, no de suposiciones (R-011).
 */
export type TradeExecutionMode = "aggregated" | "native";
export type DepositProvider = "onramp" | "transfer_only" | "none";

export interface Flags {
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
  mock_data: true,
  deposit_provider: "onramp",
  trade_execution_mode: "aggregated",
  error_reporting: false,
  eligibility_enforced: false,
};

/** Override para pruebas y para simular caídas de proveedor. */
export function withFlags(overrides: Partial<Flags>): Flags {
  return { ...FLAGS, ...overrides };
}
