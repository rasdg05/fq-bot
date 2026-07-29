/**
 * Liquidador. Es el proceso que convierte un mercado cerrado en un mercado
 * pagado — la mitad del ciclo que faltaba y sin la cual el producto no existe
 * (R-040).
 *
 *   npm run settle              # lee las fuentes y avanza el ciclo
 *   npm run settle -- --dry     # dice qué haría, sin escribir nada
 *
 * Corre solo, es idempotente y no inventa resultados: lo que no se puede leer
 * por programa queda marcado como `atorado` para que una persona lo confirme
 * contra la fuente citada, con la liga a la mano.
 *
 * Escribe dos archivos:
 *   data/settlements.json   — estado completo, historia del liquidador
 *   public/resoluciones.json — lo que la app necesita para pagar
 *
 * El reparto del pozo lo hace cada cliente sobre sus propias apuestas: aquí
 * sólo se dicta el resultado y desde cuándo se puede cobrar.
 */
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { OWN_MARKETS, validateSeed, type OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";
import { defaultOracles } from "../src/adapters/oracles/priceOracle";
import {
  authorizePayout,
  initialState,
  isPayable,
  needsAttention,
  onClose,
  onRead,
  readWithOracles,
  type SettlementState,
} from "../src/domain/settlement";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const ESTADO = join(ROOT, "data", "settlements.json");
const PUBLICO = join(ROOT, "public", "resoluciones.json");
const CATALOGO = join(ROOT, "public", "mercados.json");
const LOG = join(ROOT, "data", "settle.log");

const dry = process.argv.includes("--dry");
const now = Date.now();

function log(line: string) {
  const text = `${new Date().toISOString()} ${line}`;
  console.log(text);
  if (dry) return;
  try {
    mkdirSync(dirname(LOG), { recursive: true });
    appendFileSync(LOG, `${text}\n`);
  } catch {
    /* sin bitácora seguimos: el estado importa más */
  }
}

function leerJson<T>(ruta: string): T | null {
  if (!existsSync(ruta)) return null;
  try {
    return JSON.parse(readFileSync(ruta, "utf8")) as T;
  } catch (error) {
    log(`no se pudo leer ${ruta}: ${(error as Error).message}`);
    return null;
  }
}

/** El catálogo escrito a mano más el que se genera solo. */
function todosLosMercados(): OwnMarketSeed[] {
  const seeds = [...OWN_MARKETS];
  const publicado = leerJson<{ seeds: OwnMarketSeed[] }>(CATALOGO);
  for (const seed of publicado?.seeds ?? []) {
    try {
      const valido = validateSeed(seed);
      if (!seeds.some((existente) => existente.id === valido.id)) seeds.push(valido);
    } catch (error) {
      log(`mercado publicado inválido, se ignora: ${(error as Error).message}`);
    }
  }
  return seeds;
}

/**
 * ¿Toca leer la fuente? Un mercado abierto sólo se consulta si su regla puede
 * resolver antes de tiempo (los de toque). Preguntar por uno que sigue abierto
 * y sin regla lo marcaría como atorado sin motivo.
 */
function debeLeerse(seed: OwnMarketSeed, state: SettlementState): boolean {
  if (state.phase === "cerrado" || state.phase === "leido") return true;
  if (state.phase !== "abierto") return false;
  if (seed.rule?.kind === "precio" && seed.rule.modo === "toca") {
    return !seed.rule.desde || new Date(seed.rule.desde).getTime() <= now;
  }
  return false;
}

const oracles = defaultOracles();
const previos = new Map<string, SettlementState>(
  (leerJson<{ states: SettlementState[] }>(ESTADO)?.states ?? []).map((state) => [
    state.marketId,
    state,
  ]),
);

const estados: SettlementState[] = [];
let cambios = 0;

for (const seed of todosLosMercados()) {
  const antes = previos.get(seed.id) ?? initialState(seed.id);
  let state = antes;

  if (state.phase === "abierto" && new Date(seed.closesAt).getTime() <= now) {
    state = onClose(state);
  }

  if (debeLeerse(seed, state)) {
    const { reading, oracleId } = await readWithOracles(oracles, {
      marketId: seed.id,
      spec: seed.resolution,
      rule: seed.rule,
      now,
    });
    const siguiente = onRead(state, reading, seed.resolution, now);
    if (siguiente.phase !== state.phase) {
      log(`${seed.id}: ${state.phase} → ${siguiente.phase} (${oracleId}) · ${reading.evidence}`);
    }
    state = siguiente;
  }

  if (state.phase === "en_disputa" && isPayable(state, now)) {
    state = authorizePayout(state, now);
    log(`${seed.id}: ventana de disputa cerrada, se autoriza el pago (${state.outcome})`);
  }

  if (JSON.stringify(state) !== JSON.stringify(antes)) cambios += 1;
  estados.push(state);
}

const pendientes = needsAttention(estados);
const resumen = {
  mercados: estados.length,
  abiertos: estados.filter((state) => state.phase === "abierto").length,
  enDisputa: estados.filter((state) => state.phase === "en_disputa").length,
  pagados: estados.filter((state) => state.phase === "pagado" || state.phase === "devuelto").length,
  atorados: pendientes.length,
  cambios,
};

log(
  `resumen: ${resumen.mercados} mercados · ${resumen.abiertos} abiertos · ` +
    `${resumen.enDisputa} en disputa · ${resumen.pagados} pagados · ` +
    `${resumen.atorados} esperando confirmación humana`,
);

for (const state of pendientes) {
  log(`  ⚠ ${state.marketId}: ${state.stuckReason ?? "cerrado sin leer"} · ${state.evidence ?? ""}`);
}

if (dry) {
  console.log(JSON.stringify({ resumen, estados }, null, 2));
  process.exit(0);
}

mkdirSync(dirname(ESTADO), { recursive: true });
writeFileSync(
  ESTADO,
  `${JSON.stringify({ generatedAt: new Date(now).toISOString(), states: estados }, null, 2)}\n`,
);

// la app sólo necesita lo que ya salió de `abierto`: publicar lo demás sería
// filtrar ruido a todos los dispositivos
mkdirSync(dirname(PUBLICO), { recursive: true });
writeFileSync(
  PUBLICO,
  `${JSON.stringify(
    {
      generatedAt: new Date(now).toISOString(),
      states: estados.filter((state) => state.phase !== "abierto"),
    },
    null,
    2,
  )}\n`,
);

log(`escrito ${ESTADO} y ${PUBLICO}`);
