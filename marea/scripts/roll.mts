/**
 * Reposición del catálogo. Escribe los mercados de la semana a partir del
 * precio de hoy, para que el feed no se vacíe cuando caduque lo que se escribió
 * a mano (R-041).
 *
 *   npm run roll             # genera y publica los mercados de hoy
 *   npm run roll -- --dry    # muestra qué generaría, sin escribir
 *
 * Sólo genera preguntas que el oráculo sabe resolver por programa. Un mercado
 * que se crea solo pero necesita a una persona para pagarse mueve el problema
 * de lugar en vez de resolverlo.
 *
 * Es idempotente: los ids llevan la fecha, así que correrlo dos veces el mismo
 * día no duplica nada. Los mercados vigentes de corridas anteriores se
 * conservan tal cual — reescribir un mercado con gente adentro cambiaría la
 * pregunta debajo de quien ya apostó.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  partidosSeeds,
  rollingSeeds,
  type PartidoDeLaLiga,
  type SpotPrices,
} from "../src/adapters/ownMarkets/templates";
import { cargarEspn } from "../src/adapters/oracles/matchOracle";
import { activeSeeds, OWN_MARKETS, validateSeed, type OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";
import {
  filtrarPorPresupuesto,
  mercadoVivoDe,
  topesDelEntorno,
} from "../src/domain/presupuesto";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DESTINO = join(ROOT, "public", "mercados.json");
const dry = process.argv.includes("--dry");
const now = Date.now();

/** Cuántos mercados abiertos consideramos un feed vivo. */
const MINIMO_ABIERTOS = 6;

async function spot(): Promise<SpotPrices> {
  const url = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD,ETHUSD";
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Kraken respondió ${response.status}`);
  const body = (await response.json()) as {
    error?: string[];
    result?: Record<string, { c: string[] }>;
  };
  if (body.error?.length) throw new Error(body.error.join("; "));

  const precios: SpotPrices = {};
  for (const [par, dato] of Object.entries(body.result ?? {})) {
    const ultimo = Number(dato.c?.[0]);
    if (!Number.isFinite(ultimo)) continue;
    if (/XBT|BTC/.test(par)) precios["BTC/USD"] = ultimo;
    if (/ETH/.test(par)) precios["ETH/USD"] = ultimo;
  }
  return precios;
}

/**
 * Los partidos de Liga MX de los próximos días. Es la categoría que la gente
 * comparte de verdad, y ESPN la publica sin llave — así que se generan solos.
 */
async function partidosDeLaSemana(dias = 7): Promise<PartidoDeLaLiga[]> {
  const partidos: PartidoDeLaLiga[] = [];
  for (let i = 0; i < dias; i += 1) {
    const dia = new Date(now + i * 86_400_000).toISOString().slice(0, 10);
    try {
      for (const evento of await cargarEspn(fetch, "mex.1", dia)) {
        const competidores = evento.competitions[0]?.competitors ?? [];
        const local = competidores.find((c) => c.homeAway === "home");
        const visitante = competidores.find((c) => c.homeAway === "away");
        if (!local || !visitante) continue;
        partidos.push({
          inicio: evento.date,
          local: local.team.displayName,
          visitante: visitante.team.displayName,
        });
      }
    } catch (error) {
      // un día que no responde no cancela la semana entera
      console.warn(`ESPN falló para ${dia}: ${(error as Error).message}`);
    }
  }
  return partidos;
}

function publicados(): OwnMarketSeed[] {
  if (!existsSync(DESTINO)) return [];
  try {
    const body = JSON.parse(readFileSync(DESTINO, "utf8")) as { seeds?: OwnMarketSeed[] };
    return (body.seeds ?? []).map(validateSeed);
  } catch (error) {
    console.warn(`No se pudo leer el catálogo publicado: ${(error as Error).message}`);
    return [];
  }
}

const precios = await spot();
console.log(
  `Precio de referencia: BTC ${precios["BTC/USD"] ?? "—"} · ETH ${precios["ETH/USD"] ?? "—"}`,
);

const partidos = await partidosDeLaSemana();
console.log(`Liga MX: ${partidos.length} partidos en los próximos 7 días`);

const nuevos = [
  ...rollingSeeds({ spot: precios, now }),
  ...partidosSeeds(partidos, now),
];
// los vigentes de antes se conservan; los vencidos se van solos
const vigentes = activeSeeds(now, publicados());
const porId = new Map(vigentes.map((seed) => [seed.id, seed]));

/**
 * El freno de L9, **antes** de escribir el catálogo.
 *
 * R-067 pide subsidio con tope, y un tope que se consulta después de haber
 * creado los mercados no es un tope: es un informe. La decisión vive en
 * `domain/presupuesto.ts` —pura, probada aparte— y aquí sólo se aplica.
 *
 * Los candidatos se filtran **en orden y contándose entre sí**: aprobar la
 * tanda entera contra el estado inicial dejaría pasar N mercados que juntos
 * cruzan el tope aunque ninguno lo cruce solo.
 *
 * Hoy no estorba: nada nace en modo subsidio, así que el subsidio de cada
 * candidato es cero y todos pasan. El día que alguien encienda el subsidio sin
 * presupuesto, esto se para solo — que es el orden que la regla exige.
 */
const topes = topesDelEntorno(process.env, (aviso) => console.warn(`⚠ ${aviso}`));
const { aceptados, rechazados } = filtrarPorPresupuesto({
  vivos: [...porId.values(), ...OWN_MARKETS].map(mercadoVivoDe),
  candidatos: nuevos.map(mercadoVivoDe),
  topes,
});
if (rechazados.length > 0) {
  console.warn(`\n⛔ ${rechazados.length} mercados NO se crean por presupuesto (L9):`);
  for (const { mercado, motivo } of rechazados) console.warn(`  · ${mercado.id} — ${motivo}`);
}
const permitidos = new Set(aceptados.map((m) => m.id));

for (const seed of nuevos) {
  if (!permitidos.has(seed.id)) continue;
  if (!porId.has(seed.id)) porId.set(seed.id, seed);
}

const seeds = [...porId.values()];
const abiertos =
  seeds.filter((seed) => new Date(seed.closesAt).getTime() > now).length +
  OWN_MARKETS.filter((seed) => new Date(seed.closesAt).getTime() > now).length;

console.log(`Catálogo generado: ${seeds.length} mercados · ${abiertos} abiertos en total`);
for (const seed of seeds) console.log(`  · ${seed.id} — ${seed.title}`);

if (abiertos < MINIMO_ABIERTOS) {
  // no es un fallo del script: es un aviso de que el feed se está quedando corto
  console.warn(
    `\n⚠ Sólo hay ${abiertos} mercados abiertos (mínimo sano: ${MINIMO_ABIERTOS}). ` +
      `Toca escribir mercados nuevos en src/adapters/ownMarkets/catalog.ts.`,
  );
}

if (dry) process.exit(0);

mkdirSync(dirname(DESTINO), { recursive: true });
writeFileSync(
  DESTINO,
  `${JSON.stringify({ generatedAt: new Date(now).toISOString(), seeds }, null, 2)}\n`,
);
console.log(`\nEscrito ${DESTINO}`);
