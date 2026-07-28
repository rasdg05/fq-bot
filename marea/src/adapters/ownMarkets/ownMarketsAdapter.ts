import type { Market, Position } from "@/domain/types";
import { withEdge } from "@/domain/edge";
import { appError } from "@/domain/errors";
import {
  addStake,
  BINARY_OUTCOMES,
  impliedProbability,
  isBinary,
  rankedOutcomes,
  quote,
  outlook,
  totalPool,
  type Bet,
  type Pool,
  type Side,
} from "@/domain/parimutuel";
import { resolutionSummary } from "@/domain/resolution";
import { settle } from "@/domain/parimutuel";
import type { SettlementState } from "@/domain/settlement";
import type { MarketDataAdapter } from "@/adapters/marketDataAdapter";
import { OWN_MARKETS, activeSeeds, findOwnMarket, type OwnMarketSeed } from "./catalog";

/**
 * Adapter de mercados propios. Cumple el mismo contrato que el mock y que la
 * agregación, así que la interfaz no cambia: lo que cambia por debajo es que
 * aquí Marea **sí** crea el mercado, con motor parimutuel y resolución citada.
 *
 * La probabilidad que ve el usuario es la del pozo: lo que apostó la gente, no
 * una opinión nuestra. Por eso el precio se etiqueta "Aquí" y no "Mercado", y
 * el Edge sólo aparece cuando existe una lectura independiente (R-027).
 */

export interface ReferenceQuote {
  probability: number;
  venue: string;
}

export interface OwnMarketsOptions {
  seeds?: OwnMarketSeed[];
  /** Precio de la misma pregunta en una casa global, por `referenceKey`. */
  reference?: Map<string, ReferenceQuote>;
  /**
   * Carga la referencia externa al listar. Es la **única** fuente de Edge
   * (R-038): si falla o si no hay pareja para la pregunta, no hay Edge, y eso
   * se ve como ausencia y no como un número viejo.
   */
  loadReference?: () => Promise<Map<string, ReferenceQuote>>;
  /** Cuánto vale una referencia antes de volver a pedirla. */
  referenceTtlMs?: number;
  /**
   * Cuánto se espera a la referencia antes de mostrar el feed sin ella. Los
   * mercados no dependen de la referencia — sólo el Edge — así que una casa
   * lenta no puede dejar la pantalla en blanco.
   */
  referenceTimeoutMs?: number;
  /** Se avisa cuando la referencia no se pudo cargar, para observabilidad. */
  onReferenceError?: (error: unknown) => void;
  /** Se llama cuando una apuesta se acepta, para descontar del ledger. */
  onStake?: (marketId: string, side: Side, stake: number) => void;
  /**
   * Mercados generados por el proceso de reposición. Se suman al catálogo
   * escrito a mano para que el feed no se vacíe cuando ése caduca (R-041).
   */
  loadSeeds?: () => Promise<OwnMarketSeed[]>;
  /**
   * Estado de liquidación publicado por el runner. Es lo que convierte un
   * mercado cerrado en un mercado pagado (R-040).
   */
  loadSettlements?: () => Promise<SettlementState[]>;
  now?: () => number;
}

interface LiveMarket {
  seed: OwnMarketSeed;
  pool: Pool;
  bets: Bet[];
}

/** Cuántos mercados pueden llevar HOT a la vez. Si lo lleva todo, no dice nada. */
const HOT_TOP_N = 3;

export function createOwnMarketsAdapter(
  options: OwnMarketsOptions = {},
): MarketDataAdapter & {
  quoteBet: (marketId: string, side: Side, stake: number) => ReturnType<typeof quote>;
  poolOf: (marketId: string) => Pool | undefined;
} {
  const now = options.now ?? (() => Date.now());
  const referenceTtl = options.referenceTtlMs ?? 60_000;
  const referenceTimeout = options.referenceTimeoutMs ?? 300;
  let reference = options.reference;
  let referenceAt = options.reference ? now() : 0;
  let cargando: Promise<void> | null = null;
  const listeners = new Set<() => void>();

  function avisar() {
    for (const listener of listeners) listener();
  }

  /**
   * Espera a la referencia, pero no para siempre. Si la casa externa tarda, el
   * feed sale sin Edge y el Edge se enciende cuando la lectura llega: esperar
   * en blanco por un adorno sería fabricar espera (R-021).
   */
  async function waitForReference(): Promise<void> {
    const carga = refreshReference();
    if (referenceTimeout <= 0) return carga;
    let tarde = false;
    await Promise.race([
      carga.then(() => {
        if (tarde) avisar();
      }),
      new Promise<void>((resolve) =>
        setTimeout(() => {
          tarde = true;
          resolve();
        }, referenceTimeout),
      ),
    ]);
  }

  /**
   * Refresca la referencia si venció. Una caída no rompe el feed: se descarta
   * la referencia vieja y los mercados quedan sin Edge, que es la verdad.
   */
  async function refreshReference(): Promise<void> {
    if (!options.loadReference) return;
    if (reference && now() - referenceAt < referenceTtl) return;
    if (cargando) return cargando;

    cargando = (async () => {
      try {
        reference = await options.loadReference!();
        referenceAt = now();
      } catch (error) {
        // sin referencia fresca no se muestra una vieja: se apaga el Edge
        reference = undefined;
        referenceAt = 0;
        options.onReferenceError?.(error);
      } finally {
        cargando = null;
      }
    })();
    return cargando;
  }

  const live = new Map<string, LiveMarket>(
    (options.seeds ?? OWN_MARKETS).map((seed) => [
      seed.id,
      { seed, pool: { ...seed.pool }, bets: [] },
    ]),
  );
  const positions: Position[] = [];
  const settlements = new Map<string, SettlementState>();
  let seedsCargados = false;

  /**
   * Suma los mercados generados por el proceso de reposición. Los ya conocidos
   * no se tocan: el pozo local de un mercado en curso no se reinicia porque el
   * archivo se haya vuelto a publicar.
   */
  async function refreshSeeds(): Promise<void> {
    if (!options.loadSeeds || seedsCargados) return;
    seedsCargados = true;
    try {
      for (const seed of await options.loadSeeds()) {
        if (!live.has(seed.id)) {
          live.set(seed.id, { seed, pool: { ...seed.pool }, bets: [] });
        }
      }
    } catch (error) {
      // el feed sigue con el catálogo estático: menos mercados, no menos verdad
      options.onReferenceError?.(error);
    }
  }

  async function refreshSettlements(): Promise<void> {
    if (!options.loadSettlements) return;
    try {
      for (const state of await options.loadSettlements()) {
        settlements.set(state.marketId, state);
      }
    } catch (error) {
      options.onReferenceError?.(error);
    }
  }

  /** Lo que se le pagó a cada apuesta de este mercado, si ya se liquidó. */
  function payoutsOf(entry: LiveMarket): Record<string, number> | undefined {
    const state = settlements.get(entry.seed.id);
    if (!state?.outcome) return undefined;
    if (state.phase !== "pagado" && state.phase !== "devuelto") return undefined;
    return settle(entry.pool, entry.bets, state.outcome).payouts;
  }

  /** Umbral relativo: HOT es el pelotón de arriba, no un número absoluto. */
  function hotThreshold(): number {
    const totals = [...live.values()]
      .map((entry) => totalPool(entry.pool))
      .sort((a, b) => b - a);
    return totals[Math.min(HOT_TOP_N, totals.length) - 1] ?? Infinity;
  }

  function toMarket(entry: LiveMarket, threshold = hotThreshold()): Market {
    const { seed, pool } = entry;
    const quote = seed.referenceKey ? reference?.get(seed.referenceKey) : undefined;
    const state = settlements.get(seed.id);
    // un mercado resuelto deja de aceptar apuestas aunque su fecha no haya
    // llegado: los de toque resuelven en cuanto el precio llega
    const resuelto = state !== undefined && state.phase !== "abierto";
    const closed = resuelto || new Date(seed.closesAt).getTime() <= now();

    // en binario el nodo dominante es el Sí; con N respuestas es la favorita,
    // y hay que decir de cuál se habla. Sin esto un mercado de tres opciones
    // mostraría 0 %, porque no tiene ningún lado llamado "si"
    const outcomes = seed.outcomes ?? [...BINARY_OUTCOMES];
    const binario = isBinary(pool);
    const lider = rankedOutcomes(pool, outcomes)[0];

    return withEdge({
      id: seed.id,
      title: seed.title,
      // la probabilidad es la del pozo: lo que la gente apostó
      probability: binario ? impliedProbability(pool) : (lider?.probability ?? 0),
      leadLabel: binario ? undefined : lider?.label,
      outcomes,
      volume: totalPool(pool),
      status: closed ? "resolved" : "open",
      category: seed.category,
      // el criterio se arma desde la especificación validada, nunca a mano
      resolution_summary: resolutionSummary(seed.resolution),
      outcome: state?.outcome,
      settlementEvidence: state?.evidence,
      // la lectura independiente viene de afuera; si no hay, no hay Edge
      mareaProbability: quote?.probability,
      mareaBasis: quote ? `Precio de la misma pregunta en ${quote.venue}.` : undefined,
      edgeLabel: quote?.venue,
      priceLabel: "Aquí",
      pool: { outcomes: { ...pool.outcomes }, feeBps: pool.feeBps },
      region: "latam",
      country: seed.country,
      hot: totalPool(pool) >= threshold,
      closesAt: seed.closesAt,
      venue: { id: "marea", label: "Marea" },
    });
  }

  return {
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },

    async listMarkets() {
      await Promise.all([refreshSeeds(), refreshSettlements(), waitForReference()]);
      const vigentes = new Set(
        activeSeeds(
          now(),
          [...live.values()].map((entry) => entry.seed),
        ).map((seed) => seed.id),
      );
      const threshold = hotThreshold();
      return [...live.values()]
        // un mercado vencido en el feed promete algo que ya no existe
        .filter((entry) => vigentes.has(entry.seed.id))
        .map((entry) => toMarket(entry, threshold))
        .sort((a, b) => b.volume - a.volume);
    },

    async getMarket(id) {
      await refreshReference();
      const entry = live.get(id);
      if (!entry) throw appError("E_MARKET_DETAIL_FAILED", { id });
      return toMarket(entry);
    },

    async listPositions() {
      await refreshSettlements();
      // el pago potencial se recalcula contra el pozo de ahora; el `pnl` queda
      // en cero porque en parimutuel no existe hasta que el mercado resuelve
      return positions.map((position) => {
        const entry = live.get(position.market_id);
        if (!entry) return position;
        const bet = entry.bets.find((candidate) => candidate.id === position.id);
        if (!bet) return position;

        const payouts = payoutsOf(entry);
        if (payouts) {
          // ya se pagó: aquí sí hay resultado, y viene con su evidencia
          const state = settlements.get(entry.seed.id)!;
          const payout = payouts[bet.id] ?? 0;
          return {
            ...position,
            status:
              state.phase === "devuelto"
                ? "settled"
                : bet.side === state.outcome
                  ? "won"
                  : "lost",
            payout,
            pnl: payout - position.size,
            evidence: state.evidence,
            toWin: undefined,
            multiplier: undefined,
          };
        }

        const view = outlook(entry.pool, bet);
        return { ...position, pnl: 0, toWin: view.toWin, multiplier: view.multiplier };
      });
    },

    async prepareTrade({ marketId, side, size }) {
      const entry = live.get(marketId);
      if (!entry) throw appError("E_TRADE_INIT_FAILED", { marketId });
      if (new Date(entry.seed.closesAt).getTime() <= now()) {
        throw appError("E_TRADE_INIT_FAILED", { marketId });
      }
      // un mercado que ya se leyó no acepta apuestas: el resultado existe
      const state = settlements.get(marketId);
      if (state && state.phase !== "abierto") {
        throw appError("E_TRADE_INIT_FAILED", { marketId });
      }
      if (size <= 0) throw appError("E_TRADE_INIT_FAILED", { marketId });

      const bet: Bet = { id: `${marketId}-${entry.bets.length + 1}`, side, stake: size };
      const priced = quote(entry.pool, side, size);

      // el pozo se mueve con la apuesta: el siguiente ve el precio nuevo
      entry.pool = addStake(entry.pool, side, size);
      entry.bets.push(bet);
      options.onStake?.(marketId, side, size);

      positions.unshift({
        id: bet.id,
        market_id: marketId,
        side,
        size,
        entry_price: priced.probability,
        pnl: 0,
        status: "open",
        marketTitle: entry.seed.title,
      });

      return { positionId: bet.id, venue: "Marea" };
    },

    quoteBet(marketId, side, stake) {
      const entry = live.get(marketId);
      if (!entry) throw appError("E_TRADE_INIT_FAILED", { marketId });
      return quote(entry.pool, side, stake);
    },

    poolOf(marketId) {
      const entry = live.get(marketId);
      return entry ? { ...entry.pool } : undefined;
    },
  };
}

/**
 * Construye el mapa de referencias externas a partir de los venues ya
 * implementados. Sólo se usa para las preguntas que existen en las dos partes;
 * las de Latam puro no tienen referencia y por eso no muestran Edge.
 */
export function referenceFromVenues(
  venueMarkets: { question: string; probability: number; venueId: string }[],
  labels: Record<string, string> = { polymarket: "Polymarket", kalshi: "Kalshi" },
): Map<string, ReferenceQuote> {
  const reference = new Map<string, ReferenceQuote>();
  for (const seed of OWN_MARKETS) {
    if (!seed.referenceKey) continue;
    const needle = seed.referenceKey.toLowerCase().split(/\s+/);
    const hit = venueMarkets.find((candidate) => {
      const haystack = candidate.question.toLowerCase();
      return needle.every((word) => haystack.includes(word));
    });
    if (hit) {
      reference.set(seed.referenceKey, {
        probability: hit.probability,
        venue: labels[hit.venueId] ?? hit.venueId,
      });
    }
  }
  return reference;
}

export { findOwnMarket };
