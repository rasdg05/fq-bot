import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { LiveCandle, Market, Position } from "../src/domain/types";
import type { VelaRule } from "../src/domain/oracleRule";
import { deltaPp } from "../src/domain/vela";
import { ACTIVOS_VIVOS, esVelaViva } from "../src/adapters/ownMarkets/cryptoLive";
import { withEdge } from "../src/domain/edge";
import {
  BINARY_OUTCOMES,
  impliedProbability,
  isBinary,
  normalizePool,
  rankedOutcomes,
  outlook,
  quote,
  totalPool,
  type OutcomeId,
  type Pool,
} from "../src/domain/parimutuel";
import { resolutionSummary } from "../src/domain/resolution";
import { FLAGS } from "../src/lib/flags";
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
    // el pozo se siembra con la semilla y su modo tal como los declaró el
    // catálogo: es el único momento en que se pueden saber, porque en cuanto
    // entre la primera apuesta `outcomes` deja de ser sólo lo de la casa
    store.asegurarPozo({ marketId: seed.id, ...normalizePool(seed.pool) });
  }
}

function poolDe(store: Store, seed: OwnMarketSeed): Pool {
  const guardado = store.pozo(seed.id);
  // el pozo guardado manda: trae las apuestas de la gente además de la semilla.
  // En los dos caminos se pasa por `normalizePool` para no perder `seedMode`
  // por el camino — un mercado no cambia de reglas por reiniciar el proceso
  return normalizePool(guardado ?? seed.pool);
}

/**
 * Lo que hace falta para pintar una vela viva: de dónde sale el precio de
 * ahora. Es opcional porque el catálogo normal no lo necesita, y un mercado que
 * cierra el domingo no debe empezar a depender de un ticker de tres segundos.
 */
export interface ContextoVivo {
  precio(par: string): { precio: number; at: number; fuente: string } | undefined;
}

/** El bloque vivo de un mercado de vela, o nada si no es uno. */
function bloqueVivo(
  seed: OwnMarketSeed,
  contexto: ContextoVivo | undefined,
): LiveCandle | undefined {
  if (!esVelaViva(seed)) return undefined;
  const rule: VelaRule = seed.rule;
  const activo = ACTIVOS_VIVOS.find((candidato) => candidato.par === rule.par);
  const tick = contexto?.precio(rule.par);

  return {
    par: rule.par,
    activo: activo?.nombre ?? rule.par,
    intervalo: rule.intervalo,
    abreAt: new Date(rule.inicio).toISOString(),
    cierraAt: seed.resolution.settlesAt,
    bloqueaAt: seed.closesAt,
    strike: rule.strike,
    // sin lectura fresca la card enseña ausencia, no un precio de hace un rato
    spot: tick?.precio,
    deltaPp: tick ? deltaPp(tick.precio, rule.strike) : undefined,
    fuente: tick?.fuente,
    spotAt: tick ? new Date(tick.at).toISOString() : undefined,
  };
}

export function construirMercado(
  store: Store,
  seed: OwnMarketSeed,
  umbralHot: number,
  ahora = Date.now(),
  contexto?: ContextoVivo,
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
  const vivo = bloqueVivo(seed, contexto);

  return withEdge({
    id: seed.id,
    title: seed.title,
    shortTitle: seed.shortTitle,
    probability: binario ? impliedProbability(pool) : (lider?.probability ?? 0),
    leadLabel: binario ? undefined : lider?.label,
    volume: totalPool(pool),
    /**
     * Dos maneras de estar vivo, y ninguna se inventa:
     *
     *  - una **vela abierta** (`vivo`), que es dato real del ticker;
     *  - un **partido con marcador**, que hoy viaja sembrado en la semilla y
     *    sólo en builds simuladas, hasta que el oráculo de partidos esté en
     *    línea (R-022).
     */
    status: cerrado
      ? "resolved"
      : vivo || (seed.vivoDemo && FLAGS.mock_data)
        ? "live"
        : "open",
    live: vivo,
    marcadorVivo: FLAGS.mock_data ? seed.vivoDemo?.marcador : undefined,
    eventoReciente: FLAGS.mock_data ? seed.vivoDemo?.evento : undefined,
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
    // `hot` es una invitación a apostar, así que un mercado cerrado nunca lo
    // es por grande que sea su pozo. Antes competía por el hueco con los
    // abiertos y salía arriba del feed diciendo «Cerrado», que es enseñar una
    // puerta con el candado puesto
    hot: !cerrado && totalPool(pool) >= umbralHot,
    closesAt: seed.closesAt,
    venue: { id: "marea", label: "Marea" },
  });
}

export function listarMercados(
  store: Store,
  seeds: OwnMarketSeed[],
  ahora = Date.now(),
  contexto?: ContextoVivo,
): Market[] {
  const vigentes = activeSeeds(ahora, seeds).filter((seed) => {
    /**
     * Una vela que ya bloqueó y en la que nadie apostó se va del feed en el
     * acto. Nacen cada cinco minutos: dejar las muertas los mismos dos días que
     * a un mercado normal llenaría la pantalla de preguntas que ya no se pueden
     * contestar ni le importan a nadie.
     *
     * La que sí tiene gente adentro se queda hasta que se paga: quien apostó
     * tiene derecho a ver en qué terminó, y el pozo guardado es exactamente la
     * señal de que hay alguien esperando ese resultado.
     */
    if (!esVelaViva(seed)) return true;
    if (new Date(seed.closesAt).getTime() > ahora) return true;
    return store.pozo(seed.id) !== undefined;
  });



  /**
   * El umbral de `hot` se calcula **sólo entre los que siguen aceptando
   * apuestas**. Si un mercado cerrado con un pozo grande entra en la cuenta se
   * lleva uno de los tres huecos y, peor, sube el listón para los que sí se
   * pueden jugar: los pozos viejos son siempre los más grandes, así que los
   * mercados nuevos —que nacen chicos— no llegaban nunca.
   */
  const abiertos = vigentes.filter((seed) => new Date(seed.closesAt).getTime() > ahora);
  const totales = abiertos.map((seed) => totalPool(poolDe(store, seed))).sort((a, b) => b - a);
  const umbral = totales[Math.min(HOT_TOP_N, totales.length) - 1] ?? Infinity;

  return (
    vigentes
      .map((seed) => construirMercado(store, seed, umbral, ahora, contexto))
      /**
       * Lo vivo primero, y entre lo vivo el que cierra antes.
       *
       * Ordenar por pozo dejaba las velas al final del feed: nacen cada cinco
       * minutos y nunca acumulan lo que lleva un mercado de una semana, así que
       * lo único que pasa ahora mismo quedaba enterrado bajo lo que pasa en
       * septiembre.
       */
      .sort((a, b) => {
        // lo que manda es que esté **corriendo**, no que sea de tipo vela: una
        // vela que ya cerró no puede seguir encabezando el feed
        const viva = (m: Market) => m.status === "live" && m.live !== undefined;
        if (viva(a) !== viva(b)) return viva(a) ? -1 : 1;
        if (viva(a) && viva(b)) return a.live!.cierraAt.localeCompare(b.live!.cierraAt);
        /**
         * Y los resueltos al final, por grandes que sean. Se dejan visibles un
         * par de días para que quien apostó vea cómo quedó (R-041), pero
         * mezclarlos por tamaño hace que lo primero que ve quien llega sea un
         * mercado en el que ya no puede entrar.
         */
        const cerrado = (m: Market) => m.status === "resolved";
        if (cerrado(a) !== cerrado(b)) return cerrado(a) ? 1 : -1;
        return b.volume - a.volume;
      })
  );
}

/**
 * Lo que este visitante concreto puede ver: el feed **menos los resultados
 * ajenos**.
 *
 * Un mercado que ya resolvió se queda un par de días en el catálogo «para que
 * quien apostó vea el resultado». El catálogo hace bien en dejarlo; lo que no
 * hacía nadie era preguntar **a quién** se le enseña. A quien no entró, un
 * mercado resuelto es ruido: la primera pantalla del producto ocupada por
 * preguntas que ya no se pueden contestar, que es justo lo que el comentario de
 * `VENTANA_POST_RESOLUCION_MS` llama «peor que un feed corto».
 *
 * Explorar sigue sin pedir cuenta (I1, R-002). Sin sesión se ve todo lo que
 * acepta apuestas, que es el feed de verdad; lo único que no se ve es el
 * resultado de una apuesta que no es tuya.
 */
export function visiblesPara(
  mercados: readonly Market[],
  apostados: ReadonlySet<string>,
): Market[] {
  return mercados.filter(
    (mercado) => mercado.status !== "resolved" || apostados.has(mercado.id),
  );
}

/**
 * Todos los mercados, vencidos incluidos. Es lo que necesita quien abre una
 * posición vieja desde su portafolio: el feed los esconde (R-041), pero un
 * mercado deja de **mostrarse**, no deja de existir para quien puso dinero.
 */
export function todosLosMercados(
  store: Store,
  seeds: OwnMarketSeed[],
  ahora = Date.now(),
  contexto?: ContextoVivo,
): Market[] {
  return seeds.map((seed) => construirMercado(store, seed, Infinity, ahora, contexto));
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
