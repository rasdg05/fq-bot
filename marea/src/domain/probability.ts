import type { VenueMarket } from "@/adapters/venues/types";
import CALIBRATION from "../../vault/calibration.lock.json";
import {
  applyCalibration,
  isUsable,
  priceBasis,
  priceProbability,
  type Calibration,
  type PriceQuestion,
} from "./priceModel";


/**
 * De dónde sale la probabilidad de Marea.
 *
 * El Edge es la diferencia entre el precio del mercado y **nuestra** lectura.
 * Si no tenemos lectura propia, no hay Edge — y eso es lo correcto, no una
 * carencia que haya que disimular (R-001). Este puerto existe para que la
 * lectura sea explícita y auditable, nunca un número inventado por la vista.
 */
export interface MareaReading {
  /** Probabilidad estimada por Marea, 0..1. */
  probability: number;
  /** El porqué, en una frase mostrable al usuario. */
  basis: string;
  /** Cuántas fuentes independientes la sostienen. */
  sources: number;
}

export interface MareaProbabilityProvider {
  readonly id: string;
  read(quotes: VenueMarket[]): MareaReading | null;
}

/**
 * Default honesto: sin modelo propio no hay lectura, y por lo tanto no hay
 * Edge en ninguna card. Es el proveedor que se usa mientras no haya una
 * segunda fuente o un modelo validado detrás.
 */
export const noReadingProvider: MareaProbabilityProvider = {
  id: "sin-lectura",
  read: () => null,
};

/**
 * Lectura por referencia externa: para un mercado propio, la casa global con
 * liquidez profunda es una opinión independiente sobre la misma pregunta.
 * La diferencia contra nuestro pozo es un Edge real y explicable — pero la
 * lectura **no es nuestra**, y el copy tiene que decirlo (R-027).
 */
export function createReferenceProvider(
  reference: Map<string, { probability: number; venue: string }>,
  keyOf: (quotes: VenueMarket[]) => string | undefined,
): MareaProbabilityProvider {
  return {
    id: "referencia-externa",
    read(quotes) {
      const key = keyOf(quotes);
      if (!key) return null;
      const hit = reference.get(key);
      if (!hit) return null;
      return {
        probability: hit.probability,
        basis: `Precio de la misma pregunta en ${hit.venue}.`,
        sources: 1,
      };
    },
  };
}

/**
 * Consenso entre casas, ponderado por liquidez.
 *
 * Cuando la misma pregunta cotiza en dos venues, el consenso ponderado es una
 * estimación mejor que cualquiera de los dos precios sueltos, y la diferencia
 * contra el venue donde vas a operar es un Edge real y explicable. Con una sola
 * fuente devuelve `null`: comparar un precio consigo mismo daría siempre cero
 * y fingir lo contrario sería inventar.
 */
export function createConsensusProvider(
  options: { minSources?: number } = {},
): MareaProbabilityProvider {
  const minSources = options.minSources ?? 2;
  return {
    id: "consenso-entre-casas",
    read(quotes) {
      const venues = new Set(quotes.map((quote) => quote.venueId));
      if (venues.size < minSources) return null;

      // liquidez como peso, con piso 1 para que un venue sin dato no desaparezca
      const weights = quotes.map((quote) => Math.max(1, quote.liquidity));
      const total = weights.reduce((sum, weight) => sum + weight, 0);
      const probability =
        quotes.reduce(
          (sum, quote, index) => sum + quote.probability * weights[index],
          0,
        ) / total;

      const names = [...venues].join(" y ");
      return {
        probability,
        basis: `Consenso ponderado por liquidez entre ${names}.`,
        sources: venues.size,
      };
    },
  };
}

/* ---------------------------------------------------------------------------
   Lectura propia por modelo de precio
--------------------------------------------------------------------------- */

/**
 * Proveedor de lectura propia para preguntas de precio.
 *
 * La puerta es la calibración medida fuera de muestra, no la elegancia del
 * modelo: si el error esperado no baja del máximo, **no devuelve lectura** y
 * por lo tanto no hay Edge (R-031). Hoy la puerta está cerrada, y eso está
 * medido en `vault/calibration.lock.json`, no supuesto.
 */
export function createPriceModelProvider(
  questions: Map<string, PriceQuestion>,
  keyOf: (quotes: VenueMarket[]) => string | undefined,
  calibrations: { cierre: Calibration; toca: Calibration } = {
    cierre: CALIBRATION.cierre,
    toca: CALIBRATION.toca,
  },
): MareaProbabilityProvider {
  return {
    id: "modelo-de-precio",
    read(quotes) {
      const key = keyOf(quotes);
      if (!key) return null;
      const question = questions.get(key);
      if (!question) return null;

      const calibration = question.touch ? calibrations.toca : calibrations.cierre;
      // un modelo descalibrado no produce Edge: produce ruido con decimales
      if (!isUsable(calibration)) return null;

      return {
        probability: applyCalibration(priceProbability(question), calibration),
        basis: priceBasis(question),
        sources: 1,
      };
    },
  };
}
