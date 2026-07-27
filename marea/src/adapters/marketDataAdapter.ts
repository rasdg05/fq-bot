import type { Market, Position } from "@/domain/types";
import { appError } from "@/domain/errors";
import { FLAGS } from "@/lib/flags";
import { MOCK_MARKETS, findMockMarket } from "./mock/markets";

/**
 * Puerto de datos de mercado. La UI habla con esta interfaz y con ninguna otra;
 * cambiar mock por agregación real es cambiar la implementación, no la vista.
 */
export interface MarketDataAdapter {
  listMarkets(): Promise<Market[]>;
  getMarket(id: string): Promise<Market>;
  listPositions(): Promise<Position[]>;
  /**
   * Prepara una operación. En modo agregación devuelve el destino donde se
   * completa; Marea no es la contraparte (R-011).
   */
  prepareTrade(input: {
    marketId: string;
    side: "si" | "no";
    size: number;
  }): Promise<{ positionId: string; venue: string; deepLink?: string }>;
}

/** Latencia simulada, corta para no falsear la medición de time-to-feed. */
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

interface MockOptions {
  failMarkets?: boolean;
  failDetail?: boolean;
  failPositions?: boolean;
  failTrade?: boolean;
  latencyMs?: number;
  positions?: Position[];
}

export function createMockMarketDataAdapter(
  options: MockOptions = {},
): MarketDataAdapter {
  const latency = options.latencyMs ?? 220;
  let positions: Position[] = options.positions ? [...options.positions] : [];

  return {
    async listMarkets() {
      await delay(latency);
      if (options.failMarkets) throw appError("E_MARKETS_FETCH_FAILED");
      return MOCK_MARKETS;
    },
    async getMarket(id) {
      await delay(latency / 2);
      if (options.failDetail) throw appError("E_MARKET_DETAIL_FAILED", { id });
      const market = findMockMarket(id);
      if (!market) throw appError("E_MARKET_DETAIL_FAILED", { id });
      return market;
    },
    async listPositions() {
      await delay(latency / 2);
      if (options.failPositions) throw appError("E_PORTFOLIO_FETCH_FAILED");
      return positions;
    },
    async prepareTrade({ marketId, side, size }) {
      await delay(latency);
      if (options.failTrade) throw appError("E_TRADE_INIT_FAILED", { marketId });
      const market = findMockMarket(marketId);
      if (!market) throw appError("E_TRADE_INIT_FAILED", { marketId });
      const entry = side === "si" ? market.probability : 1 - market.probability;
      const position: Position = {
        id: `pos-${marketId}-${positions.length + 1}`,
        market_id: marketId,
        side,
        size,
        entry_price: entry,
        pnl: 0,
        status: "open",
        marketTitle: market.title,
      };
      positions = [position, ...positions];
      return {
        positionId: position.id,
        venue: FLAGS.trade_execution_mode === "aggregated" ? "agregado" : "marea",
      };
    },
  };
}

export const marketDataAdapter: MarketDataAdapter = createMockMarketDataAdapter();
