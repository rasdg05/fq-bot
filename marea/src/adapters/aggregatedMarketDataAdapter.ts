import type { Market, Position } from "@/domain/types";
import { withEdge } from "@/domain/edge";
import { appError } from "@/domain/errors";
import {
  noReadingProvider,
  type MareaProbabilityProvider,
} from "@/domain/probability";
import { isLatam } from "./venues/classify";
import type { VenueAdapter, VenueMarket } from "./venues/types";
import type { MarketDataAdapter } from "./marketDataAdapter";

/**
 * Adapter de agregación: la implementación de producción del mismo contrato que
 * cumple el mock. Compone varios venues, empareja la misma pregunta entre ellos
 * y deja que el dominio decida si hay Edge.
 *
 * Marea no crea mercado propio ni es contraparte: la operación se completa en
 * el venue con más liquidez, y el copy lo declara (R-011).
 */
export interface AggregatedOptions {
  venues: VenueAdapter[];
  /** De dónde sale la probabilidad de Marea. Por defecto: no hay lectura. */
  probability?: MareaProbabilityProvider;
  /** Cuántos mercados devolver al feed. */
  limit?: number;
  /** Se llama con los venues que fallaron, para observabilidad. */
  onVenueError?: (venueId: string, error: unknown) => void;
}

/** Agrupa por la misma pregunta entre casas. */
function groupByQuestion(markets: VenueMarket[]): VenueMarket[][] {
  const groups = new Map<string, VenueMarket[]>();
  for (const market of markets) {
    const group = groups.get(market.matchKey);
    if (group) group.push(market);
    else groups.set(market.matchKey, [market]);
  }
  return [...groups.values()];
}

/** El venue con más liquidez manda: es donde se va a ejecutar. */
function primaryOf(quotes: VenueMarket[]): VenueMarket {
  return [...quotes].sort((a, b) => b.liquidity - a.liquidity)[0];
}

export function buildMarkets(
  venueMarkets: VenueMarket[],
  provider: MareaProbabilityProvider,
  venueLabels: Map<string, string>,
): Market[] {
  return groupByQuestion(venueMarkets).map((quotes) => {
    const primary = quotes.find((quote) => quote.status !== "resolved")
      ? primaryOf(quotes.filter((quote) => quote.status !== "resolved"))
      : primaryOf(quotes);
    const reading = provider.read(quotes);

    return withEdge({
      id: `${primary.venueId}:${primary.venueMarketId}`,
      title: primary.question,
      probability: primary.probability,
      volume: quotes.reduce((sum, quote) => sum + quote.volume, 0),
      status: primary.status,
      category: primary.category,
      resolution_summary: primary.resolutionSummary,
      // sin lectura propia no se puebla nada: el dominio devolverá edge null
      mareaProbability: reading?.probability,
      mareaBasis: reading?.basis,
      venue: {
        id: primary.venueId,
        label: venueLabels.get(primary.venueId) ?? primary.venueId,
        url: primary.url,
      },
      region: isLatam(primary.question) ? "latam" : "global",
      // "hot" es tracción observada, no una etiqueta decorativa
      hot: quotes.some((quote) => quote.volume > 250_000),
      closesAt: primary.closesAt,
    });
  });
}

export function createAggregatedMarketDataAdapter(
  options: AggregatedOptions,
): MarketDataAdapter {
  const provider = options.probability ?? noReadingProvider;
  const labels = new Map(options.venues.map((venue) => [venue.id, venue.label]));
  let lastMarkets: Market[] = [];
  const positions: Position[] = [];

  return {
    async listMarkets() {
      const results = await Promise.allSettled(
        options.venues.map((venue) => venue.listMarkets()),
      );

      const collected: VenueMarket[] = [];
      let failures = 0;
      results.forEach((result, index) => {
        if (result.status === "fulfilled") collected.push(...result.value);
        else {
          failures += 1;
          options.onVenueError?.(options.venues[index].id, result.reason);
        }
      });

      // degradación parcial: con un venue vivo el feed sigue. Con ninguno, error.
      if (failures === options.venues.length) {
        throw appError("E_MARKETS_FETCH_FAILED", { venues: options.venues.length });
      }

      const markets = buildMarkets(collected, provider, labels)
        .sort((a, b) => b.volume - a.volume)
        .slice(0, options.limit ?? 60);
      lastMarkets = markets;
      return markets;
    },

    async getMarket(id) {
      const market = lastMarkets.find((candidate) => candidate.id === id);
      if (!market) throw appError("E_MARKET_DETAIL_FAILED", { id });
      return market;
    },

    async listPositions() {
      return positions;
    },

    async prepareTrade({ marketId, side, size }) {
      const market = lastMarkets.find((candidate) => candidate.id === marketId);
      if (!market?.venue) throw appError("E_TRADE_INIT_FAILED", { marketId });
      const entry = side === "si" ? market.probability : 1 - market.probability;
      const position: Position = {
        id: `${marketId}-${positions.length + 1}`,
        market_id: marketId,
        side,
        size,
        entry_price: entry,
        pnl: 0,
        status: "open",
        marketTitle: market.title,
      };
      positions.unshift(position);
      return {
        positionId: position.id,
        venue: market.venue.label,
        deepLink: market.venue.url,
      };
    },
  };
}
