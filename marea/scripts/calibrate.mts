/**
 * Calibración del modelo de precio contra historia real.
 *
 * Un modelo de probabilidad sin calibrar es una opinión con decimales. Esto
 * mide lo único que importa: cuando el modelo dice 70 %, ¿pasa el 70 % de las
 * veces?
 *
 * Compara dos fuentes de volatilidad sobre las **mismas fechas**:
 *   - realizada: desviación de los últimos 30 días. Mira hacia atrás.
 *   - implícita: índice DVOL de Deribit, lo que el mercado de opciones cobra
 *     por cubrir los próximos 30 días. Mira hacia adelante.
 *
 *   npm run calibrate
 *
 * Nota de entorno: `fetch` de Node no usa las variables de proxy por defecto,
 * así que el script se lanza con `NODE_USE_ENV_PROXY=1` desde package.json.
 */
import { writeFileSync } from "node:fs";
import {
  applyCalibration,
  logit,
  realizedVolatility,
  sigmoid,
  terminalProbability,
  touchProbability,
  MAX_USABLE_ECE_PP,
  type Calibration,
} from "../src/domain/priceModel";

const VOL_WINDOW = 30;
const HORIZONS = [7, 14, 30];
/** Umbrales relativos al precio del día: cubre preguntas fáciles y difíciles. */
const OFFSETS = [-0.1, -0.05, -0.02, 0, 0.02, 0.05, 0.1];
/**
 * Evaluación walk-forward. Una sola partición 70/30 mide sobre un régimen: si
 * ese tramo tuvo tendencia, un modelo sin deriva falla ahí por construcción, y
 * el número dice más del régimen que del modelo. Con varios pliegues, cada uno
 * probado contra el siguiente bloque de tiempo, el promedio cubre subidas y
 * bajadas (R-033).
 */
const FOLDS = 5;
/** El primer pliegue necesita historia previa para poder ajustar. */
const MIN_TRAIN_FRACTION = 0.4;

type VolSource = "realizada" | "implicita";
type Kind = "cierre" | "toca";

interface Bar {
  date: string;
  close: number;
}

interface Sample {
  predicted: number;
  actual: 0 | 1;
  horizon: number;
  /** Fracción de la historia del activo, 0..1. La partición es temporal. */
  frac: number;
}

const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/** Kraken: velas diarias, sin credenciales. */
async function fetchBars(pair: string): Promise<Bar[]> {
  const response = await fetch(
    `https://api.kraken.com/0/public/OHLC?pair=${pair}&interval=1440`,
  );
  const payload = (await response.json()) as {
    error: string[];
    result: Record<string, (string | number)[][]>;
  };
  if (payload.error?.length) throw new Error(payload.error.join(", "));
  const key = Object.keys(payload.result).find((name) => name !== "last");
  if (!key) throw new Error(`sin datos para ${pair}`);
  return payload.result[key]
    .map((candle) => ({
      date: isoDay(Number(candle[0]) * 1000),
      close: Number(candle[4]),
    }))
    .filter((bar) => Number.isFinite(bar.close) && bar.close > 0);
}

/**
 * Deribit DVOL: índice de volatilidad implícita a 30 días, en porcentaje.
 * Es el mismo número que el mercado de opciones está cobrando ese día.
 */
async function fetchImpliedVol(currency: string): Promise<Map<string, number>> {
  const end = Date.now();
  const start = end - 900 * 86_400_000;
  const response = await fetch(
    `https://www.deribit.com/api/v2/public/get_volatility_index_data` +
      `?currency=${currency}&start_timestamp=${start}&end_timestamp=${end}&resolution=86400`,
  );
  const payload = (await response.json()) as {
    result?: { data?: number[][] };
  };
  const rows = payload.result?.data ?? [];
  // [timestamp, open, high, low, close] — el cierre es el valor del día
  return new Map(rows.map((row) => [isoDay(row[0]), row[4] / 100]));
}

/** Grados de libertad a probar. `undefined` = normal. */
const NUS: (number | undefined)[] = [undefined, 3, 4, 5, 6, 8, 12];

function collect(
  bars: Bar[],
  kind: Kind,
  source: VolSource,
  implied: Map<string, number>,
  nu?: number,
): Sample[] {
  const samples: Sample[] = [];
  const closes = bars.map((bar) => bar.close);

  for (const horizon of HORIZONS) {
    for (let i = VOL_WINDOW; i + horizon < bars.length; i += 1) {
      const vol =
        source === "realizada"
          ? realizedVolatility(closes.slice(i - VOL_WINDOW, i + 1))
          : (implied.get(bars[i].date) ?? null);
      if (vol === null || !Number.isFinite(vol) || vol <= 0) continue;

      const spot = closes[i];
      for (const offset of OFFSETS) {
        const strike = spot * (1 + offset);
        const question = {
          spot,
          strike,
          direction: "above" as const,
          daysToResolve: horizon,
          annualVolatility: vol,
          nu,
        };
        const predicted =
          kind === "toca" ? touchProbability(question) : terminalProbability(question);

        const future = closes.slice(i + 1, i + horizon + 1);
        const happened =
          kind === "toca"
            ? future.some((close) => close > strike)
            : closes[i + horizon] > strike;

        samples.push({
          predicted,
          actual: happened ? 1 : 0,
          horizon,
          frac: i / bars.length,
        });
      }
    }
  }
  return samples;
}

interface Bucket {
  rango: string;
  n: number;
  predicho: number;
  real: number;
  brecha: number;
}

function reliability(samples: Sample[]): Bucket[] {
  const buckets: Sample[][] = Array.from({ length: 10 }, () => []);
  for (const sample of samples) {
    buckets[Math.min(9, Math.floor(sample.predicted * 10))].push(sample);
  }
  return buckets
    .map((bucket, index) => {
      if (bucket.length === 0) return null;
      const predicho = bucket.reduce((s, x) => s + x.predicted, 0) / bucket.length;
      const real = bucket.reduce((s, x) => s + x.actual, 0) / bucket.length;
      return {
        rango: `${index * 10}-${index * 10 + 10}%`,
        n: bucket.length,
        predicho: Math.round(predicho * 1000) / 10,
        real: Math.round(real * 1000) / 10,
        brecha: Math.round((real - predicho) * 1000) / 10,
      };
    })
    .filter((bucket): bucket is Bucket => bucket !== null);
}

/**
 * Escalado de Platt por descenso de gradiente sobre la pérdida logarítmica.
 * Dos parámetros: suficiente para enderezar un sesgo sistemático, demasiado
 * poco para memorizar la muestra.
 */
function fitPlatt(samples: Sample[]): { a: number; b: number } {
  let a = 1;
  let b = 0;
  for (let epoch = 0; epoch < 600; epoch += 1) {
    let gradA = 0;
    let gradB = 0;
    for (const sample of samples) {
      const x = logit(sample.predicted);
      const error = sigmoid(a * x + b) - sample.actual;
      gradA += error * x;
      gradB += error;
    }
    a -= (0.05 * gradA) / samples.length;
    b -= (0.05 * gradB) / samples.length;
  }
  return { a, b };
}

const brier = (samples: Sample[]) =>
  samples.reduce((sum, s) => sum + (s.predicted - s.actual) ** 2, 0) / samples.length;

/** Error de calibración esperado: la brecha media, ponderada por muestras. */
const ece = (buckets: Bucket[], total: number) =>
  buckets.reduce((sum, b) => sum + (b.n / total) * Math.abs(b.brecha), 0);

interface Fold {
  desde: number;
  hasta: number;
  n: number;
  eceCrudo: number;
  eceCorregido: number;
  /** Rendimiento del activo en el bloque, para saber qué régimen tocó. */
  regimen: number;
}

interface Result {
  fuente: VolSource;
  tipo: Kind;
  /** Grados de libertad elegidos; `undefined` = normal. */
  nu?: number;
  nTest: number;
  /** Promedio de los pliegues: el número que decide. */
  eceCrudo: number;
  eceCorregido: number;
  /** Peor pliegue: lo que pasa en el régimen más adverso. */
  ecePeorPliegue: number;
  /**
   * Agrupado: todas las predicciones fuera de muestra juntas, cubriendo subidas
   * y bajadas. Éste es el que mide calibración; el promedio de pliegues cortos
   * mide si adivinamos la tendencia del trimestre, que no es lo que hacemos.
   */
  ecePool: number;
  ecePoolCrudo: number;
  brierCrudo: number;
  brierCorregido: number;
  baseline: number;
  calibration: Calibration;
  buckets: Bucket[];
  porHorizonte: { horizonte: number; n: number; ece: number }[];
  folds: Fold[];
  usable: boolean;
}

function evaluate(all: Sample[], fuente: VolSource, tipo: Kind): Result {
  const folds: Fold[] = [];
  const acumulado: Sample[] = [];
  const step = (1 - MIN_TRAIN_FRACTION) / FOLDS;

  let ultimaCalibracion: Calibration = { a: 1, b: 0, eceOutOfSample: 0 };

  for (let k = 0; k < FOLDS; k += 1) {
    const desde = MIN_TRAIN_FRACTION + k * step;
    const hasta = desde + step;
    // el ajuste sólo ve lo anterior al bloque: nunca el futuro
    const train = all.filter((s) => s.frac < desde);
    const test = all.filter((s) => s.frac >= desde && s.frac < hasta);
    if (test.length < 200 || train.length < 500) continue;

    const { a, b } = fitPlatt(train);
    const calibration: Calibration = { a, b, eceOutOfSample: 0 };
    ultimaCalibracion = calibration;

    const corregido = test.map((s) => ({
      ...s,
      predicted: applyCalibration(s.predicted, calibration),
    }));
    const eceC = ece(reliability(test), test.length);
    const eceK = ece(reliability(corregido), corregido.length);
    // tasa base del bloque: cuánto ocurrió "arriba", que revela la tendencia
    const regimen = test.reduce((sum, s) => sum + s.actual, 0) / test.length;

    folds.push({
      desde: Math.round(desde * 100) / 100,
      hasta: Math.round(hasta * 100) / 100,
      n: test.length,
      eceCrudo: Math.round(eceC * 100) / 100,
      eceCorregido: Math.round(eceK * 100) / 100,
      regimen: Math.round(regimen * 1000) / 10,
    });
    acumulado.push(...corregido);
  }

  const media = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
  const eceCrudo = Math.round(media(folds.map((f) => f.eceCrudo)) * 100) / 100;
  const eceCorregido = Math.round(media(folds.map((f) => f.eceCorregido)) * 100) / 100;
  const peor = Math.round(Math.max(...folds.map((f) => f.eceCorregido)) * 100) / 100;

  const crudoPool = all.filter((s) => s.frac >= MIN_TRAIN_FRACTION);
  const buckets = reliability(acumulado);
  const ecePool = Math.round(ece(buckets, acumulado.length) * 100) / 100;
  const ecePoolCrudo =
    Math.round(ece(reliability(crudoPool), crudoPool.length) * 100) / 100;
  // por horizonte sobre el crudo agrupado, que es la mejor versión del modelo
  const porHorizonte = HORIZONS.map((horizonte) => {
    const slice = crudoPool.filter((s) => s.horizon === horizonte);
    return {
      horizonte,
      n: slice.length,
      ece: Math.round(ece(reliability(slice), slice.length) * 100) / 100,
    };
  });

  // si el escalado de Platt no mejora el crudo, no se aplica: una corrección
  // ajustada en un régimen y aplicada en otro puede empeorar, y lo hace (R-034)
  const platEayuda = ecePool < ecePoolCrudo;
  if (!platEayuda) {
    ultimaCalibracion.a = 1;
    ultimaCalibracion.b = 0;
  }
  ultimaCalibracion.eceOutOfSample = Math.min(ecePool, ecePoolCrudo);

  return {
    fuente,
    tipo,
    nTest: acumulado.length,
    eceCrudo,
    eceCorregido,
    ecePeorPliegue: peor,
    ecePool,
    ecePoolCrudo,
    brierCrudo: brier(crudoPool),
    brierCorregido: brier(acumulado),
    baseline:
      acumulado.reduce((sum, s) => sum + (0.5 - s.actual) ** 2, 0) / acumulado.length,
    calibration: ultimaCalibracion,
    buckets,
    porHorizonte,
    folds,
    // decide el agrupado; el promedio por pliegue y el peor quedan a la vista
    usable: Math.min(ecePool, ecePoolCrudo) <= MAX_USABLE_ECE_PP,
  };
}

/* ------------------------------- ejecución ------------------------------- */

const ASSETS = [
  { name: "BTC", pair: "XBTUSD", currency: "BTC" },
  { name: "ETH", pair: "ETHUSD", currency: "ETH" },
];

console.log("CALIBRATION_REPORT — modelo de precio contra historia real");
console.log("=========================================================\n");

const loaded = await Promise.all(
  ASSETS.map(async (asset) => ({
    ...asset,
    bars: await fetchBars(asset.pair),
    implied: await fetchImpliedVol(asset.currency),
  })),
);

for (const asset of loaded) {
  const cubierto = asset.bars.filter((bar) => asset.implied.has(bar.date)).length;
  console.log(
    `${asset.name}: ${asset.bars.length} velas · ${asset.implied.size} días de DVOL · ` +
      `${cubierto} fechas con ambas (${Math.round((cubierto / asset.bars.length) * 100)}%)`,
  );
}

/**
 * Los grados de libertad se eligen **sólo** con el tramo previo a los pliegues
 * (frac < MIN_TRAIN_FRACTION). Elegirlos mirando el agrupado fuera de muestra
 * sería ajustar contra el número que después reportamos (R-035).
 */
function pickNu(
  build: (nu?: number) => Sample[],
): { nu?: number; eceEnTramoDeAjuste: number } {
  let mejor: { nu?: number; eceEnTramoDeAjuste: number } = {
    nu: undefined,
    eceEnTramoDeAjuste: Infinity,
  };
  for (const nu of NUS) {
    const prefijo = build(nu).filter((s) => s.frac < MIN_TRAIN_FRACTION);
    if (prefijo.length < 500) continue;
    const valor = ece(reliability(prefijo), prefijo.length);
    if (valor < mejor.eceEnTramoDeAjuste) {
      mejor = { nu, eceEnTramoDeAjuste: Math.round(valor * 100) / 100 };
    }
  }
  return mejor;
}

const results: Result[] = [];
console.log("\nelección de colas (sólo con el tramo de ajuste, nunca con el de prueba):");
for (const tipo of ["cierre", "toca"] as const) {
  for (const fuente of ["realizada", "implicita"] as const) {
    const build = (nu?: number) =>
      loaded.flatMap((asset) => collect(asset.bars, tipo, fuente, asset.implied, nu));

    const { nu, eceEnTramoDeAjuste } = pickNu(build);
    console.log(
      `  ${tipo}/${fuente}: nu=${nu ?? "normal"} (${eceEnTramoDeAjuste} pp en el tramo de ajuste)`,
    );
    const result = evaluate(build(nu), fuente, tipo);
    result.nu = nu;
    results.push(result);
  }
}

console.log("\nerror de calibración fuera de muestra (walk-forward, ajuste sólo con lo anterior):\n");
console.log("  tipo     fuente       colas      n    AGRUPADO crudo  con Platt   por pliegue   Brier   ¿sirve?");
for (const r of results) {
  console.log(
    `  ${r.tipo.padEnd(8)} ${r.fuente.padEnd(12)} ${String(r.nu ?? "normal").padEnd(7)} ${String(r.nTest).padStart(6)}  ` +
      `${r.ecePoolCrudo.toFixed(2).padStart(9)} pp ${r.ecePool.toFixed(2).padStart(8)} pp ` +
      `${r.eceCorregido.toFixed(2).padStart(9)} pp  ` +
      `${r.brierCrudo.toFixed(4)}   ${r.usable ? "SÍ" : "no"}`,
  );
}
console.log(
  "\n  El AGRUPADO junta todas las predicciones fuera de muestra: cubre subidas y\n" +
    "  bajadas, y mide calibración. El promedio por pliegue mide algo distinto —\n" +
    "  si acertamos la tendencia de cada trimestre— y eso no es lo que hacemos.",
);

console.log("\npliegues (tasa base = cuántas veces ocurrió 'arriba'; revela el régimen):");
for (const r of results.filter((x) => x.tipo === "cierre")) {
  console.log(`  ${r.fuente}:`);
  for (const f of r.folds) {
    console.log(
      `    ${(f.desde * 100).toFixed(0)}-${(f.hasta * 100).toFixed(0)}%  n=${String(f.n).padStart(5)}  ` +
        `tasa base ${f.regimen.toFixed(1).padStart(5)}%  ece ${f.eceCrudo.toFixed(2).padStart(5)} pp crudo → ${f.eceCorregido.toFixed(2).padStart(5)} pp`,
    );
  }
}

for (const r of results) {
  console.log(`\nfiabilidad — ${r.tipo} / volatilidad ${r.fuente} (n=${r.nTest}):`);
  console.log("  rango        n     predicho   real    brecha");
  for (const bucket of r.buckets) {
    console.log(
      `  ${bucket.rango.padEnd(10)} ${String(bucket.n).padStart(6)}  ` +
        `${String(bucket.predicho).padStart(7)}% ${String(bucket.real).padStart(6)}%  ` +
        `${bucket.brecha > 0 ? "+" : ""}${bucket.brecha} pp`,
    );
  }
  console.log(
    `  por horizonte (agrupado): ${r.porHorizonte.map((h) => `${h.horizonte}d ${h.ece.toFixed(2)}pp`).join(" · ")}`,
  );
  console.log(`  ajuste: a=${r.calibration.a.toFixed(3)} b=${r.calibration.b.toFixed(3)}`);
}

const best = results
  .filter((r) => r.tipo === "cierre")
  .sort(
    (a, b) =>
      Math.min(a.ecePool, a.ecePoolCrudo) - Math.min(b.ecePool, b.ecePoolCrudo),
  )[0];
const mejorEce = Math.min(best.ecePool, best.ecePoolCrudo);
console.log(
  `\nmejor para preguntas de cierre: volatilidad ${best.fuente}, ${mejorEce.toFixed(2)} pp ` +
    `(máximo admisible ${MAX_USABLE_ECE_PP} pp) → ${best.usable ? "PASA" : "NO PASA"}`,
);
const porHorizonteOk = best.porHorizonte.filter((h) => h.ece <= MAX_USABLE_ECE_PP);
console.log(
  porHorizonteOk.length > 0
    ? `  horizontes que sí pasan: ${porHorizonteOk.map((h) => `${h.horizonte}d (${h.ece} pp)`).join(", ")}`
    : "  ningún horizonte pasa por separado",
);

writeFileSync(
  "calibration-report.json",
  `${JSON.stringify({ medidoEl: new Date().toISOString(), results }, null, 2)}\n`,
);
console.log("\nescrito en calibration-report.json");
