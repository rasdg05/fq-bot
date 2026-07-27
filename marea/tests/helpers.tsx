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

export interface Harness {
  events: RecordedEvent[];
  eventNames(): string[];
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
} = {}) {
  FLAGS.market_engine = options.engine ?? "aggregated";
  const ownMarkets = FLAGS.market_engine !== "aggregated";
  const analytics = createMemoryAnalytics();
  const errors = createMemoryErrorReporter();
  const adapters = {
    marketData:
      options.marketDataAdapter ??
      (ownMarkets
        ? createOwnMarketsAdapter()
        : createMockMarketDataAdapter({ latencyMs: 0, ...options.marketData })),
    wallet:
      options.walletAdapter ??
      createMockWalletAdapter({ latencyMs: 0, ...options.wallet }),
    analytics,
    errors,
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
