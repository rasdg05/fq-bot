import type { AnalyticsAdapter } from "@/adapters/analyticsAdapter";

/**
 * Medición de Web Vitals en el dispositivo real: LCP, CLS, INP y TTFB.
 *
 * Implementado sobre `PerformanceObserver` sin dependencias, porque el camino
 * crítico del feed tiene que seguir siendo liviano. Los umbrales son los de
 * Core Web Vitals; el reporte viaja por el mismo sink de analítica.
 */
export type VitalName = "LCP" | "CLS" | "INP" | "TTFB";
export type VitalRating = "good" | "needs-improvement" | "poor";

export interface VitalReport {
  metric: VitalName;
  value: number;
  rating: VitalRating;
}

/** Umbrales objetivo declarados en el handoff. */
export const THRESHOLDS: Record<VitalName, [good: number, poor: number]> = {
  LCP: [2_500, 4_000],
  INP: [200, 500],
  CLS: [0.1, 0.25],
  TTFB: [800, 1_800],
};

export function rate(metric: VitalName, value: number): VitalRating {
  const [good, poor] = THRESHOLDS[metric];
  if (value <= good) return "good";
  if (value <= poor) return "needs-improvement";
  return "poor";
}

type Emit = (report: VitalReport) => void;

function observe(
  type: string,
  callback: (entries: PerformanceEntry[]) => void,
  options: PerformanceObserverInit = {},
): PerformanceObserver | null {
  try {
    const observer = new PerformanceObserver((list) => callback(list.getEntries()));
    observer.observe({ type, buffered: true, ...options });
    return observer;
  } catch {
    // navegador sin soporte para esta métrica: se omite, no se rompe nada
    return null;
  }
}

/**
 * Arranca la medición. Devuelve una función para detenerla.
 * LCP y CLS se reportan al ocultarse la página, que es cuando su valor final
 * está fijado; INP reporta la peor interacción observada hasta ese momento.
 */
export function startVitals(emit: Emit): () => void {
  if (typeof PerformanceObserver === "undefined") return () => {};

  let lcp = 0;
  let cls = 0;
  let inp = 0;
  let reported = false;
  const observers: (PerformanceObserver | null)[] = [];

  observers.push(
    observe("largest-contentful-paint", (entries) => {
      const last = entries[entries.length - 1];
      if (last) lcp = last.startTime;
    }),
  );

  observers.push(
    observe("layout-shift", (entries) => {
      for (const entry of entries as (PerformanceEntry & {
        value: number;
        hadRecentInput: boolean;
      })[]) {
        // los saltos provocados por el propio usuario no cuentan
        if (!entry.hadRecentInput) cls += entry.value;
      }
    }),
  );

  observers.push(
    observe(
      "event",
      (entries) => {
        for (const entry of entries as (PerformanceEntry & { duration: number })[]) {
          if (entry.duration > inp) inp = entry.duration;
        }
      },
      { durationThreshold: 16 } as PerformanceObserverInit,
    ),
  );

  const ttfb = (() => {
    try {
      const [navigation] = performance.getEntriesByType(
        "navigation",
      ) as PerformanceNavigationTiming[];
      return navigation ? navigation.responseStart : 0;
    } catch {
      return 0;
    }
  })();

  function report() {
    if (reported) return;
    reported = true;
    const values: [VitalName, number][] = [
      ["LCP", Math.round(lcp)],
      ["CLS", Math.round(cls * 1000) / 1000],
      ["INP", Math.round(inp)],
      ["TTFB", Math.round(ttfb)],
    ];
    for (const [metric, value] of values) {
      if (metric !== "CLS" && value <= 0) continue;
      emit({ metric, value, rating: rate(metric, value) });
    }
  }

  const onHidden = () => {
    if (document.visibilityState === "hidden") report();
  };
  document.addEventListener("visibilitychange", onHidden);
  // `pagehide` cubre el cierre en Safari móvil, donde `visibilitychange` falla
  window.addEventListener("pagehide", report, { once: true });

  return () => {
    document.removeEventListener("visibilitychange", onHidden);
    for (const observer of observers) observer?.disconnect();
  };
}

/** Conecta la medición al sink de analítica. */
export function reportVitalsTo(analytics: AnalyticsAdapter): () => void {
  return startVitals((report) => {
    analytics.track("web_vital", {
      metric: report.metric,
      value: report.value,
      rating: report.rating,
    });
  });
}

/**
 * Expone las métricas para medición en laboratorio (`scripts/perf.mjs`), que
 * las lee desde el navegador headless sin depender del sink.
 */
declare global {
  interface Window {
    __mareaVitals?: VitalReport[];
  }
}

export function collectVitalsForLab(): () => void {
  window.__mareaVitals = [];
  return startVitals((report) => {
    window.__mareaVitals?.push(report);
  });
}
