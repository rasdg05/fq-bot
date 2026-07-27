/**
 * Prueba de humo del adapter de agregación contra las APIs públicas reales.
 * No corre en CI (depende de red); se ejecuta a mano para verificar que el
 * mapeo sigue vigente cuando un venue cambia su payload.
 */
import { createPolymarketAdapter } from "../src/adapters/venues/polymarket";
import { createKalshiAdapter } from "../src/adapters/venues/kalshi";
import { createAggregatedMarketDataAdapter } from "../src/adapters/aggregatedMarketDataAdapter";
import { createConsensusProvider } from "../src/domain/probability";
import { matchKeyFor } from "../src/adapters/venues/types";

const venues = [
  createPolymarketAdapter({ limit: 300 }),
  createKalshiAdapter({ seriesTickers: ["KXBTCD", "KXETHD", "KXCPIYOY", "KXFEDDECISION", "KXPRESPARTY"] }),
];

const perVenue = await Promise.all(venues.map((v) => v.listMarkets()));
perVenue.forEach((markets, i) => {
  console.log(`${venues[i].label}: ${markets.length} mercados usables`);
});

// ¿cuántas preguntas coinciden entre casas? de ahí sale el Edge por consenso
const keys = perVenue.map((markets) => new Set(markets.map((m) => m.matchKey)));
const shared = [...keys[0]].filter((k) => keys[1].has(k));
console.log(`preguntas emparejadas entre casas: ${shared.length}`);

const adapter = createAggregatedMarketDataAdapter({
  venues,
  probability: createConsensusProvider(),
  limit: 200,
  onVenueError: (id, error) => console.error(`venue ${id} falló:`, error),
});

const markets = await adapter.listMarkets();
const withEdge = markets.filter((m) => m.edge !== null);
console.log(`\nagregado: ${markets.length} mercados · con Edge: ${withEdge.length}`);
for (const m of withEdge.slice(0, 6)) {
  console.log(`  ${m.edge! > 0 ? "+" : ""}${m.edge} pp · ${m.title.slice(0, 58)} · ${m.mareaBasis}`);
}
console.log("sin criterio de resolución publicado:", markets.filter((m) => m.resolution_summary.startsWith("El mercado no publica")).length);
console.log("marcados LATAM:", markets.filter((m) => m.region === "latam").length);
console.log("títulos en español:", markets.filter((m) => /[¿áéíóúñ]/.test(m.title)).length);
void matchKeyFor;
