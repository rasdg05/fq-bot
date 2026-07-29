import type { Market, Position } from "@/domain/types";
import { appError } from "@/domain/errors";
import type { MarketDataAdapter } from "@/adapters/marketDataAdapter";
import type { OutcomeId } from "@/domain/parimutuel";

/**
 * Cliente del servidor de Marea. Aquí el pozo es compartido y el saldo vive en
 * una cuenta: lo que apuestas sigue existiendo cuando cierras la app, que es
 * lo mínimo que se le puede pedir a un producto donde la gente arriesga algo.
 *
 * Los mensajes de error que muestra la UI vienen del servidor ya escritos en
 * español y accionables (R-008): aquí no se traduce nada ni se inventa.
 */

export interface Cuenta {
  usuario: string;
  puntos: number;
  correo?: string;
  recargaDisponible: number;
  posiciones: Position[];
}

export interface ApiOptions {
  base?: string;
  fetchImpl?: typeof fetch;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly mensaje: string,
  ) {
    super(mensaje);
    this.name = "ApiError";
  }
}

export function createApiClient(options: ApiOptions = {}) {
  const base = (options.base ?? "/api").replace(/\/$/, "");
  const doFetch = options.fetchImpl ?? fetch;

  async function pedir<T>(ruta: string, init: RequestInit = {}): Promise<T> {
    let respuesta: Response;
    try {
      respuesta = await doFetch(`${base}${ruta}`, {
        ...init,
        // la cookie de sesión viaja sola; no manejamos tokens a mano
        credentials: "include",
        headers: init.body ? { "content-type": "application/json" } : undefined,
      });
    } catch (causa) {
      throw appError("E_NETWORK", { ruta, causa: String(causa) });
    }

    if (!respuesta.ok) {
      const cuerpo = (await respuesta.json().catch(() => ({}))) as { error?: string };
      throw new ApiError(respuesta.status, cuerpo.error ?? "Algo salió mal. Vuelve a intentar.");
    }
    return (await respuesta.json()) as T;
  }

  return {
    /** Quién soy. `null` si no hay sesión — explorar no la necesita (R-002). */
    async yo(): Promise<Cuenta | null> {
      const cuerpo = await pedir<{ usuario: string | null } & Cuenta>("/yo");
      return cuerpo.usuario ? cuerpo : null;
    },

    registro(datos: { usuario: string; password: string; correo?: string }) {
      // el código de recuperación viaja una sola vez, aquí
      return pedir<Cuenta & { codigoRecuperacion: string }>("/cuenta/registro", {
        method: "POST",
        body: JSON.stringify(datos),
      });
    },

    entrar(datos: { usuario: string; password: string }) {
      return pedir<Cuenta>("/cuenta/entrar", {
        method: "POST",
        body: JSON.stringify(datos),
      });
    },

    recuperar(datos: { usuario: string; codigo: string; password: string }) {
      return pedir<Cuenta>("/cuenta/recuperar", {
        method: "POST",
        body: JSON.stringify(datos),
      });
    },

    async salir(): Promise<void> {
      await pedir("/cuenta/salir", { method: "POST" });
    },

    recargar() {
      return pedir<Cuenta>("/cuenta/recarga", { method: "POST" });
    },

    apostar(datos: { marketId: string; side: OutcomeId; size: number }) {
      return pedir<Cuenta & { positionId: string }>("/apostar", {
        method: "POST",
        body: JSON.stringify(datos),
      });
    },

    mercados() {
      return pedir<{ mercados: Market[] }>("/mercados");
    },

    mercado(id: string) {
      return pedir<Market>(`/mercados/${encodeURIComponent(id)}`);
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;

/**
 * El adapter de datos hablando con el servidor. Mantiene el mismo contrato que
 * el mock y que los mercados propios locales: la UI no se entera del cambio.
 */
export function createApiMarketDataAdapter(
  api: ApiClient,
  onCuenta?: (cuenta: Cuenta) => void,
): MarketDataAdapter {
  return {
    async listMarkets() {
      try {
        return (await api.mercados()).mercados;
      } catch (error) {
        if (error instanceof ApiError) throw appError("E_MARKETS_FETCH_FAILED");
        throw error;
      }
    },

    async getMarket(id) {
      try {
        return await api.mercado(id);
      } catch (error) {
        if (error instanceof ApiError) throw appError("E_MARKET_DETAIL_FAILED", { id });
        throw error;
      }
    },

    async listPositions() {
      const cuenta = await api.yo();
      // sin sesión no hay posiciones que mostrar, y eso no es un error
      if (!cuenta) return [];
      onCuenta?.(cuenta);
      return cuenta.posiciones;
    },

    async prepareTrade({ marketId, side, size }) {
      const cuenta = await api.apostar({ marketId, side, size });
      onCuenta?.(cuenta);
      return { positionId: cuenta.positionId, venue: "Marea" };
    },
  };
}
