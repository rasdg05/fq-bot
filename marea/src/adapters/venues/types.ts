import type { MarketCategory, MarketStatus } from "@/domain/types";

/**
 * Un venue es una fuente de liquidez externa (Polymarket, Kalshi, …).
 * Marea agrega, no crea mercado propio: cada venue expone sus preguntas
 * normalizadas a esta forma y el agregador se encarga del resto.
 */
export interface VenueMarket {
  /** Identificador dentro del venue. */
  venueMarketId: string;
  venueId: VenueId;
  /** Pregunta tal como la publica el venue, en su idioma original. */
  question: string;
  /** Probabilidad implícita de "Sí", 0..1. */
  probability: number;
  /** Volumen operado en USD. */
  volume: number;
  /** Liquidez disponible en USD: pondera el consenso entre venues. */
  liquidity: number;
  status: MarketStatus;
  category: MarketCategory;
  closesAt?: string;
  /** Criterio de resolución publicado por el venue. */
  resolutionSummary: string;
  /** Enlace profundo al mercado en el venue, para ejecutar allá. */
  url?: string;
  /**
   * Clave de emparejamiento entre venues: dos mercados con la misma clave son
   * la misma pregunta en distintas casas. Se deriva del texto normalizado.
   */
  matchKey: string;
}

export type VenueId = "polymarket" | "kalshi";

export interface VenueAdapter {
  readonly id: VenueId;
  /** Nombre mostrable, para el copy honesto de ejecución. */
  readonly label: string;
  listMarkets(options?: { limit?: number; signal?: AbortSignal }): Promise<VenueMarket[]>;
}

/**
 * Clave de emparejamiento. Baja a minúsculas, quita acentos, signos y palabras
 * vacías, y ordena los términos restantes: dos redacciones distintas de la
 * misma pregunta caen en la misma clave sin depender del orden.
 */
const STOPWORDS = new Set([
  "the", "a", "an", "of", "in", "on", "at", "to", "for", "by", "will", "be",
  "is", "are", "does", "do", "before", "after", "than", "and", "or",
  "el", "la", "los", "las", "un", "una", "de", "del", "en", "por", "para",
  "que", "se", "y", "o", "antes", "despues", "mas", "menos",
]);

export function matchKeyFor(question: string): string {
  return (
    question
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      // los separadores de millar se quitan ANTES de trocear: si no, "71,000"
      // se parte en "71" y "000" y deja de emparejar con "71000"
      .replace(/(\d)[,\u202f\s](?=\d{3}\b)/g, "$1")
      // decimales sin información ("4.0" y "4" son el mismo strike)
      .replace(/(\d)\.(\d*?)0+\b/g, (_, head, tail) => (tail ? `${head}.${tail}` : head))
      .replace(/[^a-z0-9\s]/g, " ")
      .split(/\s+/)
      .filter((word) => word.length > 1 && !STOPWORDS.has(word))
      .sort()
      .join("-")
  );
}

/** Recorta una probabilidad a un rango operable: 0 y 1 no son precios reales. */
export function clampProbability(value: number): number {
  if (!Number.isFinite(value)) return 0.5;
  return Math.min(0.99, Math.max(0.01, value));
}
