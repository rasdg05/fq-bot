import { render } from "@testing-library/react";
import { App } from "@/App";
import {
  createMockMarketDataAdapter,
  type MarketDataAdapter,
} from "@/adapters/marketDataAdapter";
import { createMockWalletAdapter, type WalletAdapter } from "@/adapters/walletAdapter";
import {
  createMemoryAnalytics,
  type RecordedEvent,
} from "@/adapters/analyticsAdapter";
import { createMemoryErrorReporter } from "@/adapters/errorReporter";
import { createOwnMarketsAdapter } from "@/adapters/ownMarkets/ownMarketsAdapter";
import type { AppState } from "@/state/store";
import { FLAGS, type MarketEngine } from "@/lib/flags";
import type { ApiClient } from "@/adapters/http/apiAdapter";
import { createApiMarketDataAdapter } from "@/adapters/http/apiAdapter";
import type { Market, Position } from "@/domain/types";
import type { OutcomeId } from "@/domain/parimutuel";
import type { Cuenta } from "@/adapters/http/apiAdapter";

export interface Harness {
  events: RecordedEvent[];
  eventNames(): string[];
}

/**
 * Un servidor de mentira que se comporta como el de verdad en lo único que
 * importa aquí: **`puntos` ya trae acreditado el pago de lo liquidado**
 * (`server/store.mts` suma `usuario.puntos += monto` al liquidar), y ese mismo
 * pago viaja además en `posiciones[].payout`.
 *
 * Sin esto no había forma de ejercer el camino con cuenta: `renderApp`
 * construía los adapters sin `api`, así que **ninguna prueba de interfaz
 * pasaba jamás por `case "cuenta"` del reducer** — que es exactamente donde
 * vivía el saldo que saltaba entre 700 y 900. La suite daba verde sobre el
 * caso que producción rompía.
 */
export function createFakeApi(inicial: {
  puntos: number;
  posiciones?: Position[];
  recargaDisponible?: number;
  usuario?: string;
  /** El catálogo que sirve `/mercados`. Sin él, el feed sale vacío. */
  mercados?: Market[];
}) {
  const estado = {
    usuario: inicial.usuario ?? "rasdg",
    puntos: inicial.puntos,
    recargaDisponible: inicial.recargaDisponible ?? 0,
    posiciones: inicial.posiciones ?? [],
  };
  /** Cuántas veces se preguntó por la cuenta. Sirve para medir la frescura. */
  const llamadas = { yo: 0, apostar: 0, recargar: 0 };
  /** Cuando está puesto, apostar falla con este error. */
  let fallaApostar: Error | null = null;

  const perfil = () => ({
    usuario: estado.usuario,
    puntos: estado.puntos,
    recargaDisponible: estado.recargaDisponible,
    posiciones: [...estado.posiciones],
  });

  const api = {
    async yo() {
      llamadas.yo += 1;
      return perfil() as never;
    },
    async apostar({ marketId, side, size }: { marketId: string; side: OutcomeId; size: number }) {
      llamadas.apostar += 1;
      if (fallaApostar) throw fallaApostar;
      estado.puntos -= size;
      const positionId = `srv-${estado.posiciones.length + 1}`;
      estado.posiciones = [
        {
          id: positionId,
          market_id: marketId,
          side,
          size,
          entry_price: 0.5,
          pnl: 0,
          status: "open",
        },
        ...estado.posiciones,
      ];
      return { ...perfil(), positionId } as never;
    },
    async recargar() {
      llamadas.recargar += 1;
      estado.puntos += estado.recargaDisponible;
      estado.recargaDisponible = 0;
      return perfil() as never;
    },
    async registro() {
      return perfil() as never;
    },
    async entrar() {
      return perfil() as never;
    },
    async recuperar() {
      return perfil() as never;
    },
    async salir() {},
    async mercados() {
      return { mercados: inicial.mercados ?? [] } as never;
    },
    async mercado(id: string) {
      return (inicial.mercados ?? []).find((m) => m.id === id) as never;
    },
    async vivos() {
      return { at: new Date().toISOString(), mercados: [] } as never;
    },
  };

  return {
    api: api as unknown as ApiClient,
    llamadas,
    estado,
    /** Hace fallar la siguiente apuesta, para ejercer el rollback. */
    romperApuesta(error: Error | null) {
      fallaApostar = error;
    },
  };
}

export function renderApp(options: {
  marketData?: Partial<Parameters<typeof createMockMarketDataAdapter>[0]>;
  wallet?: Partial<Parameters<typeof createMockWalletAdapter>[0]>;
  overrides?: Partial<AppState>;
  marketDataAdapter?: MarketDataAdapter;
  walletAdapter?: WalletAdapter;
  /**
   * Motor bajo prueba. El default es `aggregated` porque las suites V1–V24 y
   * de red-team cubren la superficie con dinero y wallet; el motor propio de
   * puntos, que hoy es el default de producto, tiene su propia suite.
   */
  engine?: MarketEngine;
  /**
   * Servidor de mentira. Con él, la app corre por el mismo camino que en
   * producción: cuenta, saldo del servidor y `alRecibirCuenta` cableado.
   */
  api?: ApiClient;
} = {}) {
  FLAGS.market_engine = options.engine ?? "aggregated";
  const ownMarkets = FLAGS.market_engine !== "aggregated";
  const analytics = createMemoryAnalytics();
  const errors = createMemoryErrorReporter();

  // mismo cable que arma `resolveAdapters`: la cuenta que el servidor mete en
  // cada respuesta llega al store en vez de tirarse
  let avisarCuenta: ((cuenta: Cuenta) => void) | undefined;

  const adapters = {
    marketData:
      options.marketDataAdapter ??
      (options.api
        ? createApiMarketDataAdapter(options.api, (cuenta) => avisarCuenta?.(cuenta))
        : ownMarkets
          ? createOwnMarketsAdapter()
          : createMockMarketDataAdapter({ latencyMs: 0, ...options.marketData })),
    api: options.api,
    wallet:
      options.walletAdapter ??
      createMockWalletAdapter({ latencyMs: 0, ...options.wallet }),
    analytics,
    errors,
    alRecibirCuenta: options.api
      ? (fn: (cuenta: Cuenta) => void) => {
          avisarCuenta = fn;
        }
      : undefined,
  };

  const utils = render(<App adapters={adapters} overrides={options.overrides} />);

  return {
    ...utils,
    adapters,
    events: analytics.events,
    eventNames: () => analytics.events.map((event) => event.event),
    reportedErrors: errors.errors,
  };
}

/** Estado de alguien que ya pasó el onboarding y tiene wallet sin saldo. */
export const READY_NO_FUNDS: Partial<AppState> = {
  onboardingCompleted: true,
  onboardingStep: "done",
  wallet: {
    address: "0x7Ac4e1f0B2d93C5a4E8b19Fd0c6A2b31D5e70F84",
    balance: 0,
    chain: "Polygon",
    origin: "embedded",
  },
};

export const READY_WITH_FUNDS: Partial<AppState> = {
  ...READY_NO_FUNDS,
  wallet: { ...READY_NO_FUNDS.wallet!, balance: 120 },
};
