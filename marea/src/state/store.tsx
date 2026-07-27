import * as React from "react";
import type { AppError, Market, Position, Wallet } from "@/domain/types";
import { toAppError } from "@/domain/errors";
import {
  marketDataAdapter,
  type MarketDataAdapter,
} from "@/adapters/marketDataAdapter";
import { walletAdapter, type WalletAdapter } from "@/adapters/walletAdapter";
import {
  analyticsAdapter,
  safeAnalytics,
  type AnalyticsAdapter,
} from "@/adapters/analyticsAdapter";
import {
  errorReporter,
  safeErrorReporter,
  type ErrorReporter,
} from "@/adapters/errorReporter";

export type TabId = "markets" | "search" | "portfolio" | "wallet" | "profile";
export type OnboardingStep = "p0" | "p1" | "p2" | "p3" | "done";

export type Async<T> =
  | { status: "loading" }
  | { status: "data"; data: T }
  | { status: "error"; error: AppError };

export interface AppState {
  tab: TabId;
  openMarketId: string | null;
  onboardingStep: OnboardingStep;
  onboardingCompleted: boolean;
  wallet: Wallet | null;
  walletBusy: "create" | "connect" | null;
  walletError: AppError | null;
  markets: Async<Market[]>;
  positions: Async<Position[]>;
  category: Market["category"] | "all";
  depositOpen: boolean;
  depositError: AppError | null;
  depositBusy: boolean;
  tradeBusy: boolean;
  tradeError: AppError | null;
  postTrade: { side: "si" | "no"; size: number; title: string } | null;
}

type Action =
  | { type: "set_tab"; tab: TabId }
  | { type: "open_market"; id: string }
  | { type: "close_market" }
  | { type: "set_category"; category: AppState["category"] }
  | { type: "onboarding_step"; step: OnboardingStep }
  | { type: "onboarding_done" }
  | { type: "wallet_busy"; busy: AppState["walletBusy"] }
  | { type: "wallet_ready"; wallet: Wallet }
  | { type: "wallet_error"; error: AppError }
  | { type: "markets"; value: Async<Market[]> }
  | { type: "positions"; value: Async<Position[]> }
  | { type: "deposit_open"; open: boolean }
  | { type: "deposit_busy"; busy: boolean }
  | { type: "deposit_error"; error: AppError | null }
  | { type: "trade_busy"; busy: boolean }
  | { type: "trade_error"; error: AppError | null }
  | { type: "post_trade"; value: AppState["postTrade"] }
  | { type: "balance"; balance: number };

const ONBOARDING_KEY = "marea.onboarding_completed";

function readOnboarding(): boolean {
  try {
    return globalThis.localStorage?.getItem(ONBOARDING_KEY) === "true";
  } catch {
    return false;
  }
}

function persistOnboarding() {
  try {
    globalThis.localStorage?.setItem(ONBOARDING_KEY, "true");
  } catch {
    /* almacenamiento bloqueado: la sesión sigue igual (R-009) */
  }
}

export function initialState(overrides: Partial<AppState> = {}): AppState {
  const completed = overrides.onboardingCompleted ?? readOnboarding();
  return {
    tab: "markets",
    openMarketId: null,
    // reabrir con onboarding hecho entra directo al feed (RT/6)
    onboardingStep: completed ? "done" : "p0",
    onboardingCompleted: completed,
    wallet: null,
    walletBusy: null,
    walletError: null,
    markets: { status: "loading" },
    positions: { status: "loading" },
    category: "all",
    depositOpen: false,
    depositError: null,
    depositBusy: false,
    tradeBusy: false,
    tradeError: null,
    postTrade: null,
    ...overrides,
  };
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "set_tab":
      return { ...state, tab: action.tab, openMarketId: null };
    case "open_market":
      return { ...state, openMarketId: action.id };
    case "close_market":
      return { ...state, openMarketId: null, tradeError: null };
    case "set_category":
      return { ...state, category: action.category };
    case "onboarding_step":
      return { ...state, onboardingStep: action.step };
    case "onboarding_done":
      // sólo al llegar al feed (P4) se marca como completo (R-015)
      return { ...state, onboardingStep: "done", onboardingCompleted: true };
    case "wallet_busy":
      return { ...state, walletBusy: action.busy, walletError: null };
    case "wallet_ready":
      return { ...state, wallet: action.wallet, walletBusy: null, walletError: null };
    case "wallet_error":
      return { ...state, walletBusy: null, walletError: action.error };
    case "markets":
      return { ...state, markets: action.value };
    case "positions":
      return { ...state, positions: action.value };
    case "deposit_open":
      return { ...state, depositOpen: action.open, depositError: null };
    case "deposit_busy":
      return { ...state, depositBusy: action.busy };
    case "deposit_error":
      return { ...state, depositError: action.error, depositBusy: false };
    case "trade_busy":
      return { ...state, tradeBusy: action.busy };
    case "trade_error":
      return { ...state, tradeError: action.error, tradeBusy: false };
    case "post_trade":
      return { ...state, postTrade: action.value, tradeBusy: false };
    case "balance":
      return {
        ...state,
        wallet: state.wallet ? { ...state.wallet, balance: action.balance } : null,
      };
    default:
      return state;
  }
}

export interface Adapters {
  marketData: MarketDataAdapter;
  wallet: WalletAdapter;
  analytics: AnalyticsAdapter;
  errors: ErrorReporter;
}

export const defaultAdapters: Adapters = {
  marketData: marketDataAdapter,
  wallet: walletAdapter,
  analytics: safeAnalytics(analyticsAdapter),
  errors: safeErrorReporter(errorReporter),
};

interface AppContextValue {
  state: AppState;
  adapters: Adapters;
  actions: ReturnType<typeof createActions>;
}

const AppContext = React.createContext<AppContextValue | null>(null);

function createActions(
  dispatch: React.Dispatch<Action>,
  adapters: Adapters,
  getState: () => AppState,
) {
  /**
   * Candado de acciones en vuelo. No puede vivir en el estado de React: dos
   * taps dentro del mismo tick leen el estado anterior y la acción se dispara
   * dos veces. Este ref se marca de forma síncrona (R-016, red-team RT/5).
   */
  const inFlight = { wallet: false, trade: false, deposit: false };

  const fail = (error: unknown, fallback: Parameters<typeof toAppError>[1]) => {
    const appErr = toAppError(error, fallback);
    adapters.errors.report(appErr);
    return appErr;
  };

  return {
    setTab(tab: TabId) {
      dispatch({ type: "set_tab", tab });
      if (tab === "portfolio") adapters.analytics.track("view_portfolio");
      if (tab === "markets") adapters.analytics.track("view_feed");
    },
    setCategory(category: AppState["category"]) {
      dispatch({ type: "set_category", category });
    },
    openMarket(market: Market) {
      dispatch({ type: "open_market", id: market.id });
      adapters.analytics.track("open_market_detail", {
        market_id: market.id,
        has_edge: market.edge !== null,
      });
    },
    closeMarket() {
      dispatch({ type: "close_market" });
    },
    async loadMarkets() {
      dispatch({ type: "markets", value: { status: "loading" } });
      try {
        const data = await adapters.marketData.listMarkets();
        dispatch({ type: "markets", value: { status: "data", data } });
        adapters.analytics.track("view_feed", { count: data.length });
      } catch (error) {
        dispatch({
          type: "markets",
          value: { status: "error", error: fail(error, "E_MARKETS_FETCH_FAILED") },
        });
      }
    },
    async loadPositions() {
      dispatch({ type: "positions", value: { status: "loading" } });
      try {
        const data = await adapters.marketData.listPositions();
        dispatch({ type: "positions", value: { status: "data", data } });
      } catch (error) {
        dispatch({
          type: "positions",
          value: { status: "error", error: fail(error, "E_PORTFOLIO_FETCH_FAILED") },
        });
      }
    },
    goToOnboardingStep(step: OnboardingStep) {
      dispatch({ type: "onboarding_step", step });
      if (step !== "done") {
        adapters.analytics.track("view_onboarding_step", { step });
      }
    },
    /** P4: entrar al feed es lo único que cierra el onboarding (R-015). */
    finishOnboarding(reason: "deposit" | "explore") {
      dispatch({ type: "onboarding_done" });
      persistOnboarding();
      adapters.analytics.track("onboarding_completed", { reason });
      if (reason === "explore") {
        adapters.analytics.track("explore_without_funds");
      }
    },
    async createWallet() {
      // doble tap no crea dos wallets (R-016)
      if (inFlight.wallet) return;
      inFlight.wallet = true;
      dispatch({ type: "wallet_busy", busy: "create" });
      try {
        const wallet = await adapters.wallet.createEmbedded();
        dispatch({ type: "wallet_ready", wallet });
        adapters.analytics.track("wallet_created", { chain: wallet.chain });
        return wallet;
      } catch (error) {
        dispatch({ type: "wallet_error", error: fail(error, "E_WALLET_CREATE_FAILED") });
        return null;
      } finally {
        inFlight.wallet = false;
      }
    },
    async connectWallet() {
      if (inFlight.wallet) return;
      inFlight.wallet = true;
      dispatch({ type: "wallet_busy", busy: "connect" });
      try {
        const wallet = await adapters.wallet.connectExternal();
        dispatch({ type: "wallet_ready", wallet });
        adapters.analytics.track("wallet_connected", { chain: wallet.chain });
        return wallet;
      } catch (error) {
        dispatch({ type: "wallet_error", error: fail(error, "E_WALLET_CONNECT_FAILED") });
        return null;
      } finally {
        inFlight.wallet = false;
      }
    },
    openDeposit(source: string) {
      dispatch({ type: "deposit_open", open: true });
      adapters.analytics.track("click_deposit_cta", { source });
    },
    closeDeposit() {
      dispatch({ type: "deposit_open", open: false });
    },
    async startDeposit(kind: "onramp" | "transfer") {
      const wallet = getState().wallet;
      if (!wallet || inFlight.deposit) return;
      inFlight.deposit = true;
      dispatch({ type: "deposit_busy", busy: true });
      adapters.analytics.track("deposit_method_selected", { kind });
      try {
        await adapters.wallet.startDeposit({ kind, address: wallet.address });
        dispatch({ type: "deposit_busy", busy: false });
        dispatch({ type: "deposit_error", error: null });
        adapters.analytics.track("deposit_started", { kind });
        return true;
      } catch (error) {
        dispatch({
          type: "deposit_error",
          error: fail(error, "E_DEPOSIT_INIT_FAILED"),
        });
        return false;
      } finally {
        inFlight.deposit = false;
      }
    },
    async submitTrade(market: Market, side: "si" | "no", size: number) {
      if (inFlight.trade) return;
      inFlight.trade = true;
      adapters.analytics.track("click_trade_cta", {
        market_id: market.id,
        side,
        size,
      });
      dispatch({ type: "trade_busy", busy: true });
      dispatch({ type: "trade_error", error: null });
      try {
        await adapters.marketData.prepareTrade({
          marketId: market.id,
          side,
          size,
        });
        adapters.analytics.track("trade_confirmed", { market_id: market.id, side });
        dispatch({
          type: "post_trade",
          value: { side, size, title: market.title },
        });
        const balance = getState().wallet?.balance ?? 0;
        dispatch({ type: "balance", balance: Math.max(0, balance - size) });
        return true;
      } catch (error) {
        dispatch({ type: "trade_error", error: fail(error, "E_TRADE_INIT_FAILED") });
        return false;
      } finally {
        inFlight.trade = false;
      }
    },
    dismissPostTrade() {
      dispatch({ type: "post_trade", value: null });
    },
    setBalance(balance: number) {
      dispatch({ type: "balance", balance });
    },
  };
}

export function AppProvider({
  children,
  adapters = defaultAdapters,
  overrides,
}: {
  children: React.ReactNode;
  adapters?: Adapters;
  overrides?: Partial<AppState>;
}) {
  const [state, dispatch] = React.useReducer(
    reducer,
    overrides,
    (init) => initialState(init ?? {}),
  );
  const stateRef = React.useRef(state);
  stateRef.current = state;

  const actions = React.useMemo(
    () => createActions(dispatch, adapters, () => stateRef.current),
    [adapters],
  );

  const value = React.useMemo(
    () => ({ state, adapters, actions }),
    [state, adapters, actions],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const value = React.useContext(AppContext);
  if (!value) throw new Error("useApp fuera de AppProvider");
  return value;
}
