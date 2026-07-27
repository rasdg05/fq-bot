/** Mide la oferta real: cuántos mercados relevantes para Latam existen. */
import { createPolymarketAdapter } from "../src/adapters/venues/polymarket";
import { createKalshiAdapter } from "../src/adapters/venues/kalshi";
import { isLatam } from "../src/adapters/venues/classify";

const poly = createPolymarketAdapter();
const all = [];
for (const limit of [500]) {
  all.push(...(await poly.listMarkets({ limit })));
}
console.log(`Polymarket: ${all.length} binarios usables de 500 pedidos`);
const latam = all.filter((m) => isLatam(m.question));
console.log(`  relevantes para Latam: ${latam.length}`);
for (const m of latam.slice(0, 8)) console.log(`   · ${m.question.slice(0, 72)} (vol ${Math.round(m.volume)})`);

const kalshi = createKalshiAdapter({ seriesTickers: ["KXBTCD", "KXCPIYOY", "KXFEDDECISION"] });
const km = await kalshi.listMarkets();
console.log(`\nKalshi curado por serie: ${km.length} mercados`);
for (const m of km.slice(0, 5)) console.log(`   · ${m.question.slice(0, 72)} p=${m.probability.toFixed(2)} cat=${m.category}`);
