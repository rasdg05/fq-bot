import type { AppError } from "@/domain/types";
import type { ErrorReporter } from "@/adapters/errorReporter";

/**
 * Reporter real de errores. Depura el contexto, deduplica ráfagas del mismo
 * fallo y se limita a sí mismo para no convertir una caída en una tormenta de
 * peticiones. Igual que la analítica: si falla, el usuario no se entera (R-009).
 */
export interface HttpErrorReporterOptions {
  endpoint: string;
  apiKey?: string;
  release: string;
  /** Máximo de reportes por ventana. */
  maxPerWindow?: number;
  windowMs?: number;
  /** Ventana en la que un mismo código no se repite. */
  dedupeMs?: number;
  transport?: (url: string, body: string) => Promise<boolean>;
  now?: () => number;
}

/** Nada que identifique al usuario o a su dinero sale del dispositivo (R-020). */
const CONTEXT_ALLOWED = new Set(["status", "url", "venues", "id", "market_id", "kind"]);
const ADDRESS = /0x[0-9a-fA-F]{6,}/g;

export function scrubContext(
  context: Record<string, unknown> | undefined,
): Record<string, unknown> | undefined {
  if (!context) return undefined;
  const clean: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(context)) {
    if (!CONTEXT_ALLOWED.has(key)) continue;
    clean[key] =
      typeof value === "string" ? value.replace(ADDRESS, "0x…") : value;
  }
  return Object.keys(clean).length > 0 ? clean : undefined;
}

async function defaultTransport(url: string, body: string): Promise<boolean> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
    keepalive: true,
  });
  return response.ok;
}

export function createHttpErrorReporter(
  options: HttpErrorReporterOptions,
): ErrorReporter & { sent: () => number } {
  const maxPerWindow = options.maxPerWindow ?? 10;
  const windowMs = options.windowMs ?? 60_000;
  const dedupeMs = options.dedupeMs ?? 10_000;
  const transport = options.transport ?? defaultTransport;
  const now = options.now ?? (() => Date.now());

  let windowStart = now();
  let inWindow = 0;
  let total = 0;
  const lastSeen = new Map<string, number>();

  return {
    report(error: AppError) {
      try {
        const time = now();
        if (time - windowStart > windowMs) {
          windowStart = time;
          inWindow = 0;
        }
        // un fallo repetido no se reporta mil veces: la primera ya lo dice todo
        const previous = lastSeen.get(error.code);
        if (previous !== undefined && time - previous < dedupeMs) return;
        if (inWindow >= maxPerWindow) return;

        lastSeen.set(error.code, time);
        inWindow += 1;
        total += 1;

        const body = JSON.stringify({
          release: options.release,
          key: options.apiKey,
          code: error.code,
          retryable: error.retryable,
          context: scrubContext(error.context),
          at: time,
        });
        void transport(options.endpoint, body).catch(() => {
          /* silencio deliberado (R-009) */
        });
      } catch {
        /* silencio deliberado (R-009) */
      }
    },
    sent: () => total,
  };
}
