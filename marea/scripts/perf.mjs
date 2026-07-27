#!/usr/bin/env node
/**
 * Medición de rendimiento en laboratorio.
 *
 * Levanta la build de producción en un Chromium headless con throttling de CPU
 * y de red parecido a un teléfono de gama media en 4G lenta, recorre el camino
 * real y mide LCP, CLS, INP y TTFB contra presupuesto.
 *
 * Esto es medición de laboratorio, no de campo: sirve para detectar
 * regresiones y para saber si el presupuesto es alcanzable. Los números de
 * usuarios reales sólo salen del sink de analítica en producción.
 */
import { chromium } from "playwright";
import { writeFileSync } from "node:fs";

const BASE = process.env.PERF_BASE ?? "http://localhost:4173";
const OUT = process.env.PERF_OUT ?? "perf-report.json";

/** Presupuesto: los mismos umbrales que declara `src/lib/vitals.ts`. */
const BUDGET = { LCP: 2_500, INP: 200, CLS: 0.1, TTFB: 800 };

/** Gama media en 4G lenta: 4x de ralentización de CPU y latencia real. */
const THROTTLE = {
  cpuSlowdown: 4,
  downloadKbps: 1_600,
  uploadKbps: 750,
  latencyMs: 150,
};

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });

/**
 * Dos recorridos, porque son dos productos distintos en rendimiento:
 * el usuario nuevo paga el splash del onboarding, el recurrente entra al feed.
 */
async function measure({ returning }) {
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true,
});
const page = await context.newPage();
const cdp = await context.newCDPSession(page);

await cdp.send("Emulation.setCPUThrottlingRate", { rate: THROTTLE.cpuSlowdown });
await cdp.send("Network.enable");
await cdp.send("Network.emulateNetworkConditions", {
  offline: false,
  latency: THROTTLE.latencyMs,
  downloadThroughput: (THROTTLE.downloadKbps * 1024) / 8,
  uploadThroughput: (THROTTLE.uploadKbps * 1024) / 8,
});

if (returning) {
  // segunda sesión: el onboarding ya quedó cerrado en el almacenamiento
  await context.addInitScript(() =>
    localStorage.setItem("marea.onboarding_completed", "true"),
  );
}

// las métricas se recogen en la página, con la misma lógica que usa la app
await page.addInitScript(() => {
  const state = { lcp: 0, cls: 0, inp: 0 };
  window.__perf = state;
  new PerformanceObserver((list) => {
    const entries = list.getEntries();
    state.lcp = entries[entries.length - 1].startTime;
  }).observe({ type: "largest-contentful-paint", buffered: true });
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      if (!entry.hadRecentInput) state.cls += entry.value;
    }
  }).observe({ type: "layout-shift", buffered: true });
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      if (entry.duration > state.inp) state.inp = entry.duration;
    }
  }).observe({ type: "event", buffered: true, durationThreshold: 16 });
});

const started = Date.now();
await page.goto(BASE, { waitUntil: "load" });

// recorrido real: la interacción es lo que hace medible el INP
if (!returning) {
  await page.getByTestId("onboarding-start").waitFor({ timeout: 15_000 });
  await page.getByTestId("onboarding-start").click();
  await page.getByTestId("onboarding-create-wallet").click();
  await page.getByTestId("onboarding-explore").waitFor();
  await page.getByTestId("onboarding-explore").click();
}
await page.getByTestId("home-screen").waitFor({ timeout: 15_000 });
const timeToFeedMs = Date.now() - started;

await page.locator("[data-testid=market-card] button").first().click();
await page.getByTestId("market-detail").waitFor();
await page.getByTestId("side-no").click();
await page.getByTestId("detail-deposit-cta").click();
await page.getByTestId("deposit-sheet").waitFor();
await page.waitForTimeout(600);

const raw = await page.evaluate(() => {
  const [navigation] = performance.getEntriesByType("navigation");
  return {
    lcp: window.__perf.lcp,
    cls: window.__perf.cls,
    inp: window.__perf.inp,
    ttfb: navigation ? navigation.responseStart : 0,
    transferredKb:
      performance
        .getEntriesByType("resource")
        .reduce((sum, entry) => sum + (entry.transferSize ?? 0), 0) / 1024,
  };
});

await context.close();

const measured = {
  LCP: Math.round(raw.lcp),
  INP: Math.round(raw.inp),
  CLS: Math.round(raw.cls * 1000) / 1000,
  TTFB: Math.round(raw.ttfb),
};

const rows = Object.entries(BUDGET).map(([metric, budget]) => ({
  metric,
  value: measured[metric],
  budget,
  ok: measured[metric] <= budget,
}));

  return { rows, timeToFeedMs, transferredKb: Math.round(raw.transferredKb) };
}

const runs = {
  "usuario nuevo": await measure({ returning: false }),
  "usuario recurrente": await measure({ returning: true }),
};
await browser.close();

const report = {
  measuredAt: new Date().toISOString(),
  environment: "laboratorio (headless, CPU 4x, 4G lenta)",
  viewport: "390x844",
  throttle: THROTTLE,
  runs,
  /** El TTFB no es representativo: el servidor es local, sin red de verdad. */
  caveats: [
    "Medición de laboratorio, no de campo: no sustituye datos de usuarios reales.",
    "TTFB no es representativo porque el servidor corre en la misma máquina.",
  ],
};
writeFileSync(OUT, `${JSON.stringify(report, null, 2)}\n`);

console.log("PERF_REPORT (laboratorio, no campo)");
console.log("===================================");
console.log(`throttling: CPU ${THROTTLE.cpuSlowdown}x · ${THROTTLE.downloadKbps} kbps · ${THROTTLE.latencyMs} ms de latencia\n`);

let failures = 0;
for (const [name, run] of Object.entries(runs)) {
  console.log(`${name}:`);
  for (const row of run.rows) {
    const unit = row.metric === "CLS" ? "" : " ms";
    if (!row.ok) failures += 1;
    console.log(
      `  ${row.ok ? "✓" : "✗"} ${row.metric.padEnd(5)} ${String(row.value).padStart(6)}${unit}  (presupuesto ${row.budget}${unit})`,
    );
  }
  console.log(`  · al feed en ${(run.timeToFeedMs / 1000).toFixed(1)} s · ${run.transferredKb} kB transferidos\n`);
}

console.log(`verdict: ${failures === 0 ? "PASS" : "FAIL"}`);
process.exit(failures === 0 ? 0 : 1);
