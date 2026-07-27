import { getJson } from "@/adapters/http";
import { classifyCategory } from "./classify";
import {
  clampProbability,
  matchKeyFor,
  type VenueAdapter,
  type VenueMarket,
} from "./types";

/** Respuesta de la API pública Gamma. Sólo declaramos lo que consumimos. */
interface GammaMarket {
  id: string;
  question: string;
  slug?: string;
  description?: string;
  resolutionSource?: string;
  outcomes?: string;
  outcomePrices?: string;
  lastTradePrice?: number;
  bestBid?: number;
  bestAsk?: number;
  volumeNum?: number;
  liquidityNum?: number;
  endDate?: string;
  closed?: boolean;
  active?: boolean;
  acceptingOrders?: boolean;
  events?: { title?: string; slug?: string }[];
}

const BASE = "https://gamma-api.polymarket.com";

/**
 * Precio de "Sí". Preferimos el punto medio del libro (bid/ask) porque es el
 * precio al que realmente se opera; el último trade sólo entra como respaldo.
 */
function yesProbability(market: GammaMarket): number | null {
  const bid = market.bestBid;
  const ask = market.bestAsk;
  if (typeof bid === "number" && typeof ask === "number" && ask > 0) {
    return clampProbability((bid + ask) / 2);
  }
  if (typeof market.lastTradePrice === "number") {
    return clampProbability(market.lastTradePrice);
  }
  // `outcomePrices` llega como string JSON, alineado con `outcomes`
  try {
    const outcomes = JSON.parse(market.outcomes ?? "[]") as string[];
    const prices = JSON.parse(market.outcomePrices ?? "[]") as string[];
    const index = outcomes.findIndex((o) => /^(yes|s[ií])$/i.test(o.trim()));
    if (index >= 0 && prices[index] !== undefined) {
      return clampProbability(Number(prices[index]));
    }
  } catch {
    /* payload inesperado: el mercado se descarta más abajo */
  }
  return null;
}

/** El criterio de resolución nunca se inventa: si el venue no lo publica, se dice. */
function resolutionOf(market: GammaMarket): string {
  const source = market.resolutionSource?.trim();
  const description = market.description?.trim();
  if (source) return `Se resuelve con la fuente que publica el mercado: ${source}.`;
  if (description) {
    const firstSentence = description.split(/(?<=\.)\s/)[0];
    return firstSentence.length > 20 ? firstSentence : description.slice(0, 240);
  }
  return "El mercado no publica su criterio de resolución. No operes sin leerlo en el sitio del mercado.";
}

export function toVenueMarket(market: GammaMarket): VenueMarket | null {
  const probability = yesProbability(market);
  if (probability === null || !market.question) return null;
  // sólo mercados binarios Sí/No: el resto no encaja en nuestro contrato
  try {
    const outcomes = JSON.parse(market.outcomes ?? '["Yes","No"]') as string[];
    if (outcomes.length !== 2) return null;
  } catch {
    return null;
  }

  const eventTitle = market.events?.[0]?.title;
  const closesAt = market.endDate;
  const closingSoon =
    closesAt !== undefined &&
    new Date(closesAt).getTime() - Date.now() < 48 * 3_600_000;

  return {
    venueMarketId: market.id,
    venueId: "polymarket",
    question: market.question,
    probability,
    volume: market.volumeNum ?? 0,
    liquidity: market.liquidityNum ?? 0,
    status: market.closed
      ? "resolved"
      : closingSoon
        ? "closing_soon"
        : market.acceptingOrders === false
          ? "closing_soon"
          : "open",
    category: classifyCategory(market.question, eventTitle, market.slug),
    closesAt,
    resolutionSummary: resolutionOf(market),
    url: market.slug ? `https://polymarket.com/market/${market.slug}` : undefined,
    matchKey: matchKeyFor(market.question),
  };
}

export function createPolymarketAdapter(
  options: { baseUrl?: string; limit?: number } = {},
): VenueAdapter {
  const base = options.baseUrl ?? BASE;
  return {
    id: "polymarket",
    label: "Polymarket",
    async listMarkets({ limit, signal } = {}) {
      const wanted = limit ?? options.limit ?? 60;
      // Gamma topa cada página en 100: paginamos con offset hasta completar
      const PAGE = 100;
      const collected: VenueMarket[] = [];
      for (let offset = 0; offset < wanted; offset += PAGE) {
        const size = Math.min(PAGE, wanted - offset);
        const url =
          `${base}/markets?closed=false&active=true&archived=false` +
          `&limit=${size}&offset=${offset}&order=volume24hr&ascending=false`;
        const payload = await getJson<GammaMarket[]>(url, {
          signal,
          errorCode: "E_MARKETS_FETCH_FAILED",
        });
        if (payload.length === 0) break;
        for (const raw of payload) {
          const market = toVenueMarket(raw);
          if (market) collected.push(market);
        }
        if (payload.length < size) break;
      }
      return collected;
    },
  };
}
