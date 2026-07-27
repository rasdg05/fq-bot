/**
 * Contratos de dominio. Cerrados por ARCH: los adapters se adaptan a estos
 * tipos, nunca al revés. La UI no conoce ninguna otra forma de dato.
 */

export type MarketStatus = "open" | "closing_soon" | "live" | "resolved";

export type MarketCategory =
  | "cripto"
  | "economia"
  | "deportes"
  | "politica"
  | "cultura"
  /** Sin señal clara para clasificar. Preferimos decirlo a inventar categoría. */
  | "otros";

export interface Market {
  id: string;
  title: string;
  /** Probabilidad del mercado, 0..1. Nodo tipográfico dominante (R-004). */
  probability: number;
  /** Volumen operado, en USD. */
  volume: number;
  status: MarketStatus;
  category: MarketCategory;
  /**
   * Edge en puntos porcentuales, ya filtrado por el umbral de dominio
   * (`>= EDGE_MIN_PP`). `null` significa "no hay edge que mostrar" (R-001).
   * Nunca lo calcula la UI: lo entrega el dominio vía `withEdge()`.
   */
  edge: number | null;
  /** Criterio de resolución, en una frase clara. Se muestra antes de operar. */
  resolution_summary: string;
  /** Probabilidad estimada por Marea, 0..1. Ausente => no hay lectura propia. */
  mareaProbability?: number;
  /** El porqué de esa lectura, mostrable. Sin base no se muestra Edge (R-019). */
  mareaBasis?: string;
  /**
   * Cómo se llama la lectura frente a la que se compara el precio. En mercados
   * propios la lectura viene de una casa global, no de un modelo nuestro, y
   * llamarla "Marea" sería mentir (R-027).
   */
  edgeLabel?: string;
  /** Etiqueta del precio propio en el detalle: "Mercado" o "Aquí". */
  priceLabel?: string;
  /** Estado del pozo, cuando el mercado es parimutuel propio. */
  pool?: { si: number; no: number; feeBps: number };
  /** Dónde se completa la operación cuando la ejecución es agregada. */
  venue?: { id: string; label: string; url?: string };
  /** Marca de tracción para el badge HOT. */
  hot?: boolean;
  /** Región del mercado, para el badge LATAM. */
  region?: "latam" | "global";
  /** País concreto. En un producto todo-Latam informa más que "LATAM". */
  country?: string;
  closesAt?: string;
}

export type PositionSide = "si" | "no";
export type PositionStatus = "open" | "won" | "lost" | "settled";

export interface Position {
  id: string;
  market_id: string;
  side: PositionSide;
  /** Tamaño en USD. */
  size: number;
  /** Precio de entrada, 0..1. */
  entry_price: number;
  /**
   * Resultado realizado. En parimutuel se queda en cero hasta que el mercado
   * resuelve: no hay marca a mercado porque no puedes salirte antes (R-029).
   */
  pnl: number;
  status: PositionStatus;
  marketTitle?: string;
  /** Lo que se cobra si el lado acierta, con el pozo de ahora. */
  toWin?: number;
  /** Cuánto paga cada unidad, con el pozo de ahora. */
  multiplier?: number;
}

export interface Wallet {
  address: string;
  /** Saldo disponible en USD. */
  balance: number;
  chain: string;
  /** Cómo llegó la wallet al usuario: creada por Marea o conectada por él. */
  origin: "embedded" | "connected";
}

export type AppErrorCode =
  | "E_WALLET_CREATE_FAILED"
  | "E_WALLET_CONNECT_FAILED"
  | "E_BALANCE_FETCH_FAILED"
  | "E_DEPOSIT_INIT_FAILED"
  | "E_DEPOSIT_PROVIDER_UNAVAILABLE"
  | "E_MARKETS_FETCH_FAILED"
  | "E_MARKET_DETAIL_FAILED"
  | "E_PORTFOLIO_FETCH_FAILED"
  | "E_TRADE_INIT_FAILED"
  | "E_NETWORK"
  | "E_UNKNOWN";

export interface AppError {
  code: AppErrorCode;
  /** Mensaje mostrable al usuario, español Latam. Nunca un stack trace (R-008). */
  user_message_es: string;
  retryable: boolean;
  context?: Record<string, unknown>;
}
