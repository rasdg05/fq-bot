import { getJson } from "@/adapters/http";
import { classifyCategory } from "./classify";
import {
  clampProbability,
  matchKeyFor,
  type VenueAdapter,
  type VenueMarket,
} from "./types";

/** Respuesta de la API pública de Kalshi. Sólo lo que consumimos. */
interface KalshiMarket {
  ticker: string;
  event_ticker?: string;
  title: string;
  yes_bid_dollars?: string | number | null;
  yes_ask_dollars?: string | number | null;
  last_price_dollars?: string | number | null;
  volume_fp?: string | number | null;
  liquidity_dollars?: string | number | null;
  close_time?: string;
  status?: string;
  rules_primary?: string;
  market_type?: string;
  /** Presente en las combinadas multipierna: no son una pregunta binaria. */
  mve_collection_ticker?: string | null;
  /** El strike concreto: sin él, toda una escalera comparte el mismo título. */
  yes_sub_title?: string | null;
}

const BASE = "https://api.elections.kalshi.com/trade-api/v2";

function num(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Kalshi cotiza en dólares por contrato de $1: el precio ya es la probabilidad. */
function yesProbability(market: KalshiMarket): number | null {
  // exigimos libro de dos lados: un solo lado no es un precio, es una intención
  const bid = num(market.yes_bid_dollars);
  const ask = num(market.yes_ask_dollars);
  if (bid !== null && ask !== null && bid > 0 && ask > 0) {
    return clampProbability((bid + ask) / 2);
  }
  const last = num(market.last_price_dollars);
  const volume = num(market.volume_fp) ?? 0;
  // sin libro, sólo aceptamos el último precio si de verdad hubo operación
  if (last !== null && last > 0 && volume > 0) return clampProbability(last);
  return null;
}

/**
 * Pregunta completa. Kalshi reparte la pregunta entre `title` (el evento) y
 * `yes_sub_title` (el strike): unir ambos evita que toda una escalera de
 * strikes se colapse en un solo mercado al emparejar entre casas.
 */
function questionOf(market: KalshiMarket): string {
  const strike = market.yes_sub_title?.trim();
  if (!strike) return market.title;
  return `${market.title.replace(/\?$/, "")} ${strike}`.trim();
}

export function toVenueMarket(market: KalshiMarket): VenueMarket | null {
  const probability = yesProbability(market);
  if (probability === null || !market.title) return null;
  const question = questionOf(market);
  // las combinadas multipierna se declaran `binary` pero no son una pregunta
  // binaria: se reconocen por su colección MVE y por el título con varias patas
  if (market.market_type && market.market_type !== "binary") return null;
  if (market.mve_collection_ticker) return null;
  if (/,\s*(yes|no)\s/i.test(market.title)) return null;

  const closesAt = market.close_time;
  const closingSoon =
    closesAt !== undefined &&
    new Date(closesAt).getTime() - Date.now() < 48 * 3_600_000;

  return {
    venueMarketId: market.ticker,
    venueId: "kalshi",
    question,
    probability,
    volume: num(market.volume_fp) ?? 0,
    liquidity: num(market.liquidity_dollars) ?? 0,
    status:
      market.status === "settled" || market.status === "closed"
        ? "resolved"
        : closingSoon
          ? "closing_soon"
          : "open",
    category: classifyCategory(question, market.event_ticker, market.ticker),
    closesAt,
    resolutionSummary: market.rules_primary?.trim()
      ? market.rules_primary.trim().slice(0, 280)
      : "El mercado no publica su criterio de resolución. No operes sin leerlo en el sitio del mercado.",
    url: `https://kalshi.com/markets/${market.ticker}`,
    matchKey: matchKeyFor(question),
  };
}

export interface KalshiOptions {
  baseUrl?: string;
  limit?: number;
  /**
   * Series a consultar. El listado abierto de Kalshi viene dominado por
   * combinadas deportivas sin liquidez, así que curamos por serie en lugar de
   * pedir "lo que sea". Vacío = listado general.
   */
  seriesTickers?: string[];
}

export function createKalshiAdapter(options: KalshiOptions = {}): VenueAdapter {
  const base = options.baseUrl ?? BASE;
  const size = options.limit ?? 100;

  const fetchPage = async (query: string, signal?: AbortSignal) => {
    const payload = await getJson<{ markets?: KalshiMarket[] }>(
      `${base}/markets?limit=${size}&status=open${query}`,
      { signal, errorCode: "E_MARKETS_FETCH_FAILED" },
    );
    return payload.markets ?? [];
  };

  return {
    id: "kalshi",
    label: "Kalshi",
    async listMarkets({ signal } = {}) {
      const series = options.seriesTickers ?? [];
      const pages = series.length
        ? await Promise.all(
            series.map((ticker) => fetchPage(`&series_ticker=${ticker}`, signal)),
          )
        : [await fetchPage("", signal)];

      return pages
        .flat()
        .map(toVenueMarket)
        .filter((market): market is VenueMarket => market !== null);
    },
  };
}
