/**
 * Configuración de entorno. Ningún secreto vive en el código: todo entra por
 * variables `VITE_*` y lo que falta se declara ausente, no se adivina.
 *
 * Regla: si una integración no está configurada, la app degrada a su camino
 * simulado y lo dice. Nunca finge que habló con un proveedor real.
 */
type Env = Record<string, string | undefined>;

function env(): Env {
  // `import.meta.env` en la app, `process.env` en scripts y pruebas
  const meta = (import.meta as unknown as { env?: Env }).env ?? {};
  const proc = typeof process !== "undefined" ? (process.env as Env) : {};
  return { ...proc, ...meta };
}

function str(key: string): string | undefined {
  const value = env()[key];
  return value && value.trim() !== "" ? value.trim() : undefined;
}

function bool(key: string, fallback: boolean): boolean {
  const value = str(key);
  if (value === undefined) return fallback;
  return value === "true" || value === "1";
}

export type DataSource = "mock" | "aggregated";

export interface AppConfig {
  /**
   * Base del servidor de Marea. Con esto encendido hay cuentas, saldo que
   * persiste y un pozo compartido entre todos; sin esto, la app corre sola en
   * el dispositivo y lo que apuestas se pierde al recargar.
   */
  apiBase?: string;
  /** De dónde salen los mercados. */
  dataSource: DataSource;
  /** Series de Kalshi que curamos; vacío = listado general. */
  kalshiSeries: string[];
  /** Endpoint del sink de analítica. Ausente => sink en memoria. */
  analyticsEndpoint?: string;
  analyticsKey?: string;
  /** Muestreo de eventos, 0..1. */
  analyticsSampleRate: number;
  /** Endpoint del reporter de errores. Ausente => reporter en memoria. */
  errorEndpoint?: string;
  errorKey?: string;
  /** Proveedor de wallet embebida. Ausente => wallet simulada. */
  walletProvider?: "privy" | "turnkey";
  walletAppId?: string;
  /** Proveedor de on-ramp. Ausente => sólo transferencia. */
  onrampProvider?: string;
  /** Versión que acompaña a cada evento y error. */
  release: string;
  /** Envío de métricas de rendimiento al sink. */
  vitalsEnabled: boolean;
}

export function readConfig(): AppConfig {
  const source = str("VITE_DATA_SOURCE");
  return {
    // por defecto la app habla con su propio servidor: no depende de que
    // alguien recuerde poner una variable en el panel de un hosting. Para una
    // build estática sin servidor se pone `off` explícitamente.
    apiBase: (str("VITE_API_BASE") ?? "/api") === "off" ? undefined : str("VITE_API_BASE") ?? "/api",
    dataSource: source === "aggregated" ? "aggregated" : "mock",
    kalshiSeries: (str("VITE_KALSHI_SERIES") ?? "")
      .split(",")
      .map((ticker) => ticker.trim())
      .filter(Boolean),
    // el sink propio también es el default: lanzar a ciegas no puede ser lo
    // que pasa cuando nadie configura nada
    analyticsEndpoint: str("VITE_ANALYTICS_ENDPOINT") ?? "/api/eventos",
    analyticsKey: str("VITE_ANALYTICS_KEY"),
    analyticsSampleRate: Number(str("VITE_ANALYTICS_SAMPLE_RATE") ?? "1") || 1,
    errorEndpoint: str("VITE_ERROR_ENDPOINT"),
    errorKey: str("VITE_ERROR_KEY"),
    walletProvider: str("VITE_WALLET_PROVIDER") as AppConfig["walletProvider"],
    walletAppId: str("VITE_WALLET_APP_ID"),
    onrampProvider: str("VITE_ONRAMP_PROVIDER"),
    release: str("VITE_RELEASE") ?? "dev",
    vitalsEnabled: bool("VITE_VITALS", true),
  };
}

export const CONFIG = readConfig();
