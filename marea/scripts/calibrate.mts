/**
 * Calibración del modelo de precio contra historia real.
 *
 * Un modelo de probabilidad sin calibrar es una opinión con decimales. Esto
 * mide lo único que importa: cuando el modelo dice 70 %, ¿pasa el 70 % de las
 * veces? Se corre a mano contra velas diarias públicas.
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

interface Sample {
  predicted: number;
  actual: 0 | 1;
  horizon: number;
  /** Posición de la vela: la partición train/test es temporal, por activo. */
  t: number;
  /** Fracción de la historia del activo, 0..1. */
  frac: number;
}

/** Kraken devuelve hasta 720 velas diarias, sin credenciales. */
async function fetchCloses(pair: string): Promise<number[]> {
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
    .map((candle) => Number(candle[4]))
    .filter((close) => Number.isFinite(close) && close > 0);
}

function collect(closes: number[], touch: boolean): Sample[] {
  const samples: Sample[] = [];
  for (const horizon of HORIZONS) {
    for (let i = VOL_WINDOW; i + horizon < closes.length; i += 1) {
      const window = closes.slice(i - VOL_WINDOW, i + 1);
      const vol = realizedVolatility(window);
      if (vol === null || vol <= 0) continue;
      const spot = closes[i];

      for (const offset of OFFSETS) {
        const strike = spot * (1 + offset);
        const question = {
          spot,
          strike,
          direction: "above" as const,
          daysToResolve: horizon,
          annualVolatility: vol,
        };
        const predicted = touch
          ? touchProbability(question)
          : terminalProbability(question);

        const future = closes.slice(i + 1, i + horizon + 1);
        const happened = touch
          ? future.some((close) => close > strike)
          : closes[i + horizon] > strike;

        samples.push({
          predicted,
          actual: happened ? 1 : 0,
          horizon,
          t: i,
          frac: i / closes.length,
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
    const index = Math.min(9, Math.floor(sample.predicted * 10));
    buckets[index].push(sample);
  }
  return buckets
    .map((bucket, index) => {
      if (bucket.length === 0) return null;
      const predicho =
        bucket.reduce((sum, s) => sum + s.predicted, 0) / bucket.length;
      const real = bucket.reduce((sum, s) => sum + s.actual, 0) / bucket.length;
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
  const rate = 0.05;
  for (let epoch = 0; epoch < 400; epoch += 1) {
    let gradA = 0;
    let gradB = 0;
    for (const sample of samples) {
      const x = logit(sample.predicted);
      const error = sigmoid(a * x + b) - sample.actual;
      gradA += error * x;
      gradB += error;
    }
    a -= (rate * gradA) / samples.length;
    b -= (rate * gradB) / samples.length;
  }
  return { a, b };
}

const brier = (samples: Sample[]) =>
  samples.reduce((sum, s) => sum + (s.predicted - s.actual) ** 2, 0) / samples.length;

/** Error de calibración esperado: la brecha media, ponderada por muestras. */
function ece(buckets: Bucket[], total: number): number {
  return buckets.reduce(
    (sum, bucket) => sum + (bucket.n / total) * Math.abs(bucket.brecha),
    0,
  );
}

const PAIRS = [
  { name: "BTC", pair: "XBTUSD" },
  { name: "ETH", pair: "ETHUSD" },
];

const report: Record<string, unknown> = { medidoEl: new Date().toISOString() };
console.log("CALIBRATION_REPORT — modelo de precio contra historia real");
console.log("=========================================================\n");

for (const kind of ["cierre", "toca"] as const) {
  const all: Sample[] = [];
  for (const { name, pair } of PAIRS) {
    const closes = await fetchCloses(pair);
    const samples = collect(closes, kind === "toca");
    all.push(...samples);
    console.log(`${name}: ${closes.length} velas diarias → ${samples.length} predicciones (${kind})`);
  }

  // partición temporal **por activo**: se ajusta con la primera parte de la
  // historia de cada uno y se mide con la última. Partir por posición en el
  // arreglo separaría por activo, no por tiempo, y el número saldría inflado.
  const train = all.filter((sample) => sample.frac < 0.7);
  const test = all.filter((sample) => sample.frac >= 0.7);

  const crudo = reliability(test);
  const eceCrudo = ece(crudo, test.length);
  const { a, b } = fitPlatt(train);

  const calibration: Calibration = { a, b, eceOutOfSample: 0 };
  const corregido = test.map((sample) => ({
    ...sample,
    predicted: applyCalibration(sample.predicted, calibration),
  }));
  const buckets = reliability(corregido);
  calibration.eceOutOfSample = Math.round(ece(buckets, corregido.length) * 100) / 100;

  const brierCrudo = brier(test);
  const brierCorregido = brier(corregido);
  const baseline =
    test.reduce((sum, s) => sum + (0.5 - s.actual) ** 2, 0) / test.length;

  console.log(`\nfiabilidad fuera de muestra (${kind}), n=${test.length}:`);
  console.log("  rango        n     predicho   real    brecha");
  for (const bucket of buckets) {
    console.log(
      `  ${bucket.rango.padEnd(10)} ${String(bucket.n).padStart(6)}  ${String(bucket.predicho).padStart(7)}% ${String(bucket.real).padStart(6)}%  ${bucket.brecha > 0 ? "+" : ""}${bucket.brecha} pp`,
    );
  }
  console.log(`\n  error de calibración: ${eceCrudo.toFixed(2)} pp crudo → ${calibration.eceOutOfSample.toFixed(2)} pp corregido`);
  console.log(`  Brier: ${brierCrudo.toFixed(4)} crudo → ${brierCorregido.toFixed(4)} corregido (decir 50% siempre: ${baseline.toFixed(4)})`);
  console.log(`  ajuste: a=${a.toFixed(3)} b=${b.toFixed(3)}`);
  const usable = calibration.eceOutOfSample <= MAX_USABLE_ECE_PP;
  console.log(`  ¿sirve para mostrar Edge? ${usable ? "SÍ" : `NO — ${calibration.eceOutOfSample.toFixed(2)} pp supera el máximo de ${MAX_USABLE_ECE_PP} pp`}\n`);

  report[kind] = {
    calibration,
    usable,
    eceCrudo,
    brierCrudo,
    brierCorregido,
    baseline,
    buckets,
    nTest: test.length,
  };
}

writeFileSync("calibration-report.json", `${JSON.stringify(report, null, 2)}\n`);
console.log("escrito en calibration-report.json");
