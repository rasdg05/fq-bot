import type { SettlementState } from "@/domain/settlement";
import { validateSeed, type OwnMarketSeed } from "./catalog";

/**
 * Dos archivos publicados por el proceso que corre en la máquina del operador:
 *
 *  - `mercados.json`    — los mercados que se generan solos cada semana (B2)
 *  - `resoluciones.json` — el estado de liquidación de cada mercado (B1)
 *
 * La app los lee como datos, no como código. Si no existen, el producto sigue
 * funcionando con el catálogo estático y sin resoluciones: degradar es correcto,
 * fingir no.
 *
 * Lo que llega por archivo **se valida igual** que lo que está en el código: un
 * mercado mal formado se descarta y se avisa, nunca se publica a medias.
 */

export interface PublishedCatalog {
  generatedAt: string;
  seeds: OwnMarketSeed[];
}

export interface PublishedSettlements {
  generatedAt: string;
  states: SettlementState[];
}

async function loadJson<T>(url: string, fetchImpl: typeof fetch): Promise<T | null> {
  const response = await fetchImpl(url, { cache: "no-store" });
  if (!response.ok) return null;
  return (await response.json()) as T;
}

export async function loadPublishedSeeds(input: {
  url?: string;
  fetchImpl?: typeof fetch;
  onRejected?: (id: string, reason: string) => void;
}): Promise<OwnMarketSeed[]> {
  const body = await loadJson<PublishedCatalog>(
    input.url ?? "mercados.json",
    input.fetchImpl ?? fetch,
  );
  if (!body?.seeds?.length) return [];

  const valid: OwnMarketSeed[] = [];
  for (const seed of body.seeds) {
    try {
      valid.push(validateSeed(seed));
    } catch (error) {
      input.onRejected?.(
        seed?.id ?? "sin id",
        error instanceof Error ? error.message : String(error),
      );
    }
  }
  return valid;
}

export async function loadPublishedSettlements(input: {
  url?: string;
  fetchImpl?: typeof fetch;
}): Promise<SettlementState[]> {
  const body = await loadJson<PublishedSettlements>(
    input.url ?? "resoluciones.json",
    input.fetchImpl ?? fetch,
  );
  return body?.states ?? [];
}
