import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { Market, Position } from "../src/domain/types";
import { withEdge } from "../src/domain/edge";
import {
  BINARY_OUTCOMES,
  impliedProbability,
  isBinary,
  rankedOutcomes,
  outlook,
  quote,
  totalPool,
  type OutcomeId,
  type Pool,
} from "../src/domain/parimutuel";
import { resolutionSummary } from "../src/domain/resolution";
import {
  OWN_MARKETS,
  activeSeeds,
  validateSeed,
  type OwnMarketSeed,
} from "../src/adapters/ownMarkets/catalog";
import { referenceFromVenues, type ReferenceQuote } from "../src/adapters/ownMarkets/ownMarketsAdapter";
import { createPolymarketAdapter } from "../src/adapters/venues/polymarket";
import { createKalshiAdapter } from "../src/adapters/venues/kalshi";
import type { Store } from "./store.mts";

/**
 * Los mercados, vistos desde el servidor. La diferencia con la versión que
 * corría en el navegador es la que importa: **el pozo es uno solo para todos**.
 * Lo que apuesta uno mueve el precio del siguiente, que es lo que hace que esto
 * sea un mercado y no un simulador de un jugador.
 */

const HOT_TOP_N = 3;
const REFERENCIA_TTL_MS = 60_000;

let referencia: Map<string, ReferenceQuote> | undefined;
let referenciaAt = 0;

/**
 * La referencia externa se pide desde el servidor, una vez cada minuto para
 * todos, en vez de una vez por dispositivo. Si la casa se cae, no hay Edge:
 * nunca una lectura vieja disfrazada de fresca (R-038).
 */
export async function refrescarReferencia(): Promise<void> {
  if (referencia && Date.now() - referenciaAt < REFERENCIA_TTL_MS) return;
  try {
    const venues = [
      createPolymarketAdapter({ limit: 200 }),
      createKalshiAdapter({ seriesTickers: process.env.VITE_KALSHI_SERIES?.split(",") }),
    ];
    const resueltos = await Promise.allSettled(venues.map((v) => v.listMarkets()));
    const quotes = resueltos.flatMap((r) => (r.status === "fulfilled" ? r.value : []));
    referencia = referenceFromVenues(quotes);
    referenciaAt = Date.now();
  } catch {
    referencia = undefined;
    referenciaAt = 0;
  }
}

/** Catálogo escrito a mano más el que se repone solo. */
export function todosLosSeeds(root: string): OwnMarketSeed[] {
  const seeds = [...OWN_MARKETS];
  const publicado = join(root, "public", "mercados.json");
  if (existsSync(publicado)) {
    try {
      const { seeds: generados = [] } = JSON.parse(readFileSync(publicado, "utf8"));
      for (const bruto of generados as OwnMarketSeed[]) {
        try {
          const seed = validateSeed(bruto);
          if (!seeds.some((s) => s.id === seed.id)) seeds.push(seed);
        } catch (error) {
          console.error(`mercado publicado inválido, se ignora: ${String(error)}`);
        }
      }
    } catch (error) {
      console.error(`no se pudo leer mercados.json: ${String(error)}`);
    }
  }
  return seeds;
}

/** Siembra en el store los pozos de los mercados que aún no existían. */
export function sembrarPozos(store: Store, seeds: OwnMarketSeed[]): void {
  for (const seed of seeds) {
    store.asegurarPozo({
      marketId: seed.id,
      outcomes: { ...seed.pool.outcomes },
      feeBps: seed.pool.feeBps,
    });
  }
}

function poolDe(store: Store, seed: OwnMarketSeed): Pool {
  const guardado = store.pozo(seed.id);
  return guardado
    ? { outcomes: guardado.outcomes, feeBps: guardado.feeBps }
    : { outcomes: { ...seed.pool.outcomes }, feeBps: seed.pool.feeBps };
}

export function construirMercado(
  store: Store,
  seed: OwnMarketSeed,
  umbralHot: number,
  ahora = Date.now(),
): Market {
  const pool = poolDe(store, seed);
  const estado = store.liquidacion(seed.id);
  const cita = seed.referenceKey ? referencia?.get(seed.referenceKey) : undefined;
  const resuelto = estado !== undefined && estado.phase !== "abierto";
  const cerrado = resuelto || new Date(seed.closesAt).getTime() <= ahora;

  const outcomes = seed.outcomes ?? [...BINARY_OUTCOMES];
  const binario = isBinary(pool);
  // en binario el nodo dominante es la probabilidad del Sí; con N respuestas
  // es la de la favorita, y hay que decir de cuál se habla o el número no
  // significa nada
  const lider = rankedOutcomes(pool, outcomes)[0];

  return withEdge({
    id: seed.id,
    title: seed.title,
    shortTitle: seed.shortTitle,
    probability: binario ? impliedProbability(pool) : (lider?.probability ?? 0),
    leadLabel: binario ? undefined : lider?.label,
    volume: totalPool(pool),
    status: cerrado ? "resolved" : "open",
    category: seed.category,
    resolution_summary: resolutionSummary(seed.resolution),
    outcome: estado?.outcome,
    settlementEvidence: estado?.evidence,
    mareaProbability: cita?.probability,
    mareaBasis: cita ? `Precio de la misma pregunta en ${cita.venue}.` : undefined,
    edgeLabel: cita?.venue,
    priceLabel: "Aquí",
    pool: { outcomes: { ...pool.outcomes }, feeBps: pool.feeBps },
    outcomes,
    // cuánta gente distinta hay dentro: es lo que dice si el mercado está vivo
    participantes: store.participantesDe(seed.id),
    equipos: seed.equipos,
    region: "latam",
    country: seed.country,
    hot: totalPool(pool) >= umbralHot,
    closesAt: seed.closesAt,
    venue: { id: "marea", label: "Marea" },
  });
}

export function listarMercados(
  store: Store,
  seeds: OwnMarketSeed[],
  ahora = Date.now(),
): Market[] {
  const vigentes = activeSeeds(ahora, seeds);
  const totales = vigentes
    .map((seed) => totalPool(poolDe(store, seed)))
    .sort((a, b) => b - a);
  const umbral = totales[Math.min(HOT_TOP_N, totales.length) - 1] ?? Infinity;
  return vigentes
    .map((seed) => construirMercado(store, seed, umbral, ahora))
    .sort((a, b) => b.volume - a.volume);
}

/** Cotiza sin mover nada: lo que se le muestra al usuario antes de decidir. */
export function cotizar(store: Store, seed: OwnMarketSeed, side: OutcomeId, stake: number) {
  return quote(poolDe(store, seed), side, stake);
}

/**
 * Las posiciones de un usuario, con su pago potencial contra el pozo de ahora,
 * o con lo que ya cobró si el mercado se liquidó.
 */
export function posicionesDe(
  store: Store,
  usuarioId: string,
  seeds: OwnMarketSeed[],
): Position[] {
  const porId = new Map(seeds.map((seed) => [seed.id, seed]));
  return store
    .apuestasDe(usuarioId)
    .slice()
    .reverse()
    .map((apuesta) => {
      const seed = porId.get(apuesta.marketId);
      const estado = store.liquidacion(apuesta.marketId);
      const etiqueta = (seed?.outcomes ?? BINARY_OUTCOMES).find(
        (o) => o.id === apuesta.side,
      )?.label;
      const base: Position = {
        id: apuesta.id,
        market_id: apuesta.marketId,
        side: apuesta.side,
        sideLabel: etiqueta,
        size: apuesta.stake,
        entry_price: apuesta.precio,
        pnl: 0,
        status: "open",
        marketTitle: seed?.title,
      };

      if (apuesta.pagado !== undefined) {
        return {
          ...base,
          status:
            estado?.phase === "devuelto"
              ? "settled"
              : apuesta.side === estado?.outcome
                ? "won"
                : "lost",
          payout: apuesta.pagado,
          pnl: apuesta.pagado - apuesta.stake,
          evidence: estado?.evidence,
        };
      }

      if (!seed) return base;
      const vista = outlook(poolDe(store, seed), {
        id: apuesta.id,
        side: apuesta.side,
        stake: apuesta.stake,
      });
      return { ...base, toWin: vista.toWin, multiplier: vista.multiplier };
    });
}
