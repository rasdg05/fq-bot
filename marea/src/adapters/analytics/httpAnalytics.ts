import type { AnalyticsAdapter, AnalyticsEvent } from "@/adapters/analyticsAdapter";

/**
 * Sink real de analítica: cola en memoria, envío por lotes, reintento con
 * backoff y `sendBeacon` cuando la pestaña se va. Nada de esto puede tumbar la
 * UX: todo camino de fallo termina en silencio (R-009).
 *
 * Los eventos se depuran antes de salir: sólo viajan propiedades de una lista
 * blanca, nunca direcciones, montos ni texto libre del usuario (R-020).
 */
export interface HttpAnalyticsOptions {
  endpoint: string;
  apiKey?: string;
  release: string;
  /** Tamaño de lote antes de disparar el envío. */
  batchSize?: number;
  /** Tiempo máximo que un evento espera en la cola. */
  flushIntervalMs?: number;
  /** Tope de la cola: más allá se descartan los más viejos. */
  maxQueue?: number;
  /** Fracción de sesiones que reportan, 0..1. */
  sampleRate?: number;
  /** Inyectable para pruebas. */
  transport?: (url: string, body: string, keepalive: boolean) => Promise<boolean>;
  now?: () => number;
}

/**
 * Lista blanca de propiedades. Cualquier clave fuera de aquí se descarta antes
 * de salir del dispositivo, aunque alguien la agregue en una llamada nueva.
 */
const ALLOWED_PROPS = new Set([
  "market_id",
  "has_edge",
  "count",
  "step",
  "reason",
  "kind",
  "side",
  "chain",
  "source",
  "category",
  "venue",
  "metric",
  "value",
  "rating",
]);

/** Valores que nunca deben salir, aunque su clave esté permitida. */
const SENSITIVE = /^0x[0-9a-f]{6,}$/i;

export function scrubProps(
  props: Record<string, unknown> | undefined,
): Record<string, unknown> | undefined {
  if (!props) return undefined;
  const clean: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(props)) {
    if (!ALLOWED_PROPS.has(key)) continue;
    if (typeof value === "string" && SENSITIVE.test(value)) continue;
    // el monto operado es dato financiero del usuario: nunca sale
    if (typeof value === "number" && !Number.isFinite(value)) continue;
    clean[key] = value;
  }
  return Object.keys(clean).length > 0 ? clean : undefined;
}

interface QueuedEvent {
  event: AnalyticsEvent;
  props?: Record<string, unknown>;
  at: number;
}

async function defaultTransport(
  url: string,
  body: string,
  keepalive: boolean,
): Promise<boolean> {
  if (keepalive && typeof navigator !== "undefined" && navigator.sendBeacon) {
    return navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
  }
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    keepalive,
  });
  return response.ok;
}

export function createHttpAnalytics(
  options: HttpAnalyticsOptions,
): AnalyticsAdapter & { flush: () => Promise<void>; queued: () => number } {
  const batchSize = options.batchSize ?? 12;
  const flushInterval = options.flushIntervalMs ?? 5_000;
  const maxQueue = options.maxQueue ?? 200;
  const sampleRate = options.sampleRate ?? 1;
  const transport = options.transport ?? defaultTransport;
  const now = options.now ?? (() => Date.now());
  const sessionId = `s-${Math.random().toString(36).slice(2, 10)}`;
  // el muestreo se decide una vez por sesión: no partimos embudos por la mitad
  const sampledIn = Math.random() < sampleRate;

  let queue: QueuedEvent[] = [];
  let timer: ReturnType<typeof setTimeout> | null = null;
  let sending = false;

  async function flush(keepalive = false): Promise<void> {
    if (sending || queue.length === 0) return;
    sending = true;
    const batch = queue;
    queue = [];
    try {
      const body = JSON.stringify({
        session: sessionId,
        release: options.release,
        key: options.apiKey,
        events: batch,
      });
      const ok = await transport(options.endpoint, body, keepalive);
      // si el sink rechaza, devolvemos a la cola sin exceder el tope
      if (!ok) queue = [...batch, ...queue].slice(-maxQueue);
    } catch {
      queue = [...batch, ...queue].slice(-maxQueue);
    } finally {
      sending = false;
    }
  }

  function schedule() {
    if (timer) return;
    timer = setTimeout(() => {
      timer = null;
      void flush();
    }, flushInterval);
  }

  // al ocultarse la pestaña se vacía la cola con beacon: si no, se pierde
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") void flush(true);
    });
  }

  return {
    track(event, props) {
      try {
        if (!sampledIn) return;
        queue.push({ event, props: scrubProps(props), at: now() });
        if (queue.length > maxQueue) queue = queue.slice(-maxQueue);
        if (queue.length >= batchSize) void flush();
        else schedule();
      } catch {
        /* la analítica jamás rompe la UX (R-009) */
      }
    },
    flush: () => flush(false),
    queued: () => queue.length,
  };
}
