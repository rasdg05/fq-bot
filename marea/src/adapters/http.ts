import { appError } from "@/domain/errors";
import type { AppErrorCode } from "@/domain/types";

/**
 * Cliente HTTP único de los adapters. Nadie llama `fetch` directo: aquí viven
 * el timeout, el reintento con backoff y la normalización a AppError, para que
 * ninguna excepción cruda de red llegue nunca a la vista (R-008).
 */
export interface HttpOptions {
  /** Corta la petición y la marca como red caída. */
  timeoutMs?: number;
  /** Reintentos ante 5xx, 429 y fallos de red. No aplica a 4xx. */
  retries?: number;
  /** Código de AppError para el fallo final. */
  errorCode?: AppErrorCode;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

const DEFAULTS = { timeoutMs: 8_000, retries: 2 } as const;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** 5xx, 429 y errores de transporte son transitorios; 4xx no. */
function isTransient(status: number | null): boolean {
  if (status === null) return true;
  return status === 429 || status >= 500;
}

export async function getJson<T>(url: string, options: HttpOptions = {}): Promise<T> {
  const timeoutMs = options.timeoutMs ?? DEFAULTS.timeoutMs;
  const retries = options.retries ?? DEFAULTS.retries;
  const errorCode = options.errorCode ?? "E_NETWORK";

  let lastStatus: number | null = null;
  let lastCause = "";

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    // el consumidor puede cancelar por su cuenta (cambio de pantalla)
    const onAbort = () => controller.abort();
    options.signal?.addEventListener("abort", onAbort, { once: true });

    try {
      const response = await fetch(url, {
        signal: controller.signal,
        headers: { accept: "application/json", ...options.headers },
      });
      lastStatus = response.status;

      if (!response.ok) {
        lastCause = `HTTP ${response.status}`;
        if (!isTransient(response.status)) break;
      } else {
        return (await response.json()) as T;
      }
    } catch (error) {
      lastStatus = null;
      lastCause = error instanceof Error ? error.message : String(error);
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", onAbort);
    }

    if (attempt < retries) {
      // backoff exponencial con jitter, para no sincronizar reintentos
      const backoff = 250 * 2 ** attempt;
      await sleep(backoff + Math.random() * 120);
    }
  }

  throw appError(errorCode, { status: lastStatus, cause: lastCause, url });
}
