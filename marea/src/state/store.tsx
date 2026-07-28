import * as React from "react";
import type { AppError, Market, Position, Wallet } from "@/domain/types";
import type { CountryCode } from "@/domain/eligibility";
import { detectCountry, type CountrySource } from "@/domain/geo";
import type { ApiClient, Cuenta } from "@/adapters/http/apiAdapter";
import {
  apply as applyPoints,
  dailyTopUp,
  emptyLedger,
  grantWelcome,
  canStake,
  type PointsLedger,
} from "@/domain/points";
import { isPointsMode } from "@/lib/flags";
import { appError as appErrorFor, toAppError } from "@/domain/errors";
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

export type TabId = "markets" | "search" | "portfolio" | "wallet" | "tabla" | "profile";
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
  /** País declarado o inferido: define elegibilidad para depositar y operar. */
  country?: CountryCode;
  /** De dónde salió el país. Inferido se puede corregir; declarado manda. */
  countrySource: CountrySource;
  /** Ledger de puntos. Sólo vive en el motor de puntos. */
  points: PointsLedger;
  /**
   * Cuenta en el servidor. `null` significa que estás explorando sin entrar,
   * que es un estado legítimo y completo: mirar nunca pide cuenta (R-002).
   */
  cuenta: Cuenta | null;
  /** La hoja de cuenta está abierta. Se abre al querer apostar sin sesión. */
  cuentaAbierta: boolean;
  cuentaBusy: boolean;
  cuentaError: string | null;
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
  | { type: "balance"; balance: number }
  | { type: "points"; ledger: PointsLedger }
  | { type: "country"; country: CountryCode; source: CountrySource }
  | { type: "cuenta"; cuenta: Cuenta | null }
  | { type: "cuenta_abierta"; abierta: boolean }
  | { type: "cuenta_busy"; busy: boolean }
  | { type: "cuenta_error"; error: string | null };

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

/**
 * Un enlace compartido (`/m/<id>`) abre ese mercado directo, saltandose la
 * bienvenida. Quien llega por el mensaje de un amigo viene a ver **ese**
 * mercado; hacerle pasar por el onboarding es perderlo (R-002).
 */
function mercadoCompartido(): string | null {
  try {
    const match = /^\/m\/(.+)$/.exec(globalThis.location?.pathname ?? "");
    return match ? decodeURIComponent(match[1]) : null;
  } catch {
    return null;
  }
}

export function initialState(overrides: Partial<AppState> = {}): AppState {
  const compartido = mercadoCompartido();
  const completed = overrides.onboardingCompleted ?? readOnboarding();
  // el país se infiere del dispositivo, sin red y sin dato personal: sirve para
  // hablarle a la gente de su mercado, no como control de cumplimiento
  const guess = detectCountry();
  const state: AppState = {
    tab: "markets",
    openMarketId: compartido,
    // reabrir con onboarding hecho entra directo al feed (RT/6); un enlace
    // compartido entra directo al mercado que le mandaron
    onboardingStep: completed || compartido ? "done" : "p0",
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
    country: guess.country,
    countrySource: guess.source,
    cuenta: null,
    cuentaAbierta: false,
    cuentaBusy: false,
    cuentaError: null,
    // la bienvenida se entrega al arrancar: explorar y jugar no cuestan nada
    points: isPointsMode() ? grantWelcome(emptyLedger()) : emptyLedger(),
    ...overrides,
  };

  // un país puesto a mano manda sobre la inferencia, siempre
  if (overrides.country && !overrides.countrySource) state.countrySource = "declarado";
  return state;
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
    case "points":
      return { ...state, points: action.ledger };
    case "country":
      return { ...state, country: action.country, countrySource: action.source };
    case "cuenta":
      return {
        ...state,
        cuenta: action.cuenta,
        cuentaBusy: false,
        cuentaError: null,
        // el saldo que manda es el del servidor: el ledger local sólo lo espeja
        points: action.cuenta
          ? { balance: action.cuenta.puntos, entries: state.points.entries }
          : state.points,
      };
    case "cuenta_abierta":
      return { ...state, cuentaAbierta: action.abierta, cuentaError: null };
    case "cuenta_busy":
      return { ...state, cuentaBusy: action.busy, cuentaError: null };
    case "cuenta_error":
      return { ...state, cuentaError: action.error, cuentaBusy: false };
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
  /** Presente sólo con servidor: es lo que habilita cuentas y saldo real. */
  api?: ApiClient;
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
  const inFlight = { wallet: false, trade: false, deposit: false, cuenta: false };

  /**
   * Pagos ya acreditados, marcados de forma síncrona. El ledger es la guarda
   * durable, pero dos cargas del portafolio en el mismo tick lo leen sin
   * actualizar y pagarían dos veces — mismo defecto que el doble tap (R-016).
   */
  const acreditados = new Set<string>();
  let suscrito = false;

  const fail = (error: unknown, fallback: Parameters<typeof toAppError>[1]) => {
    const appErr = toAppError(error, fallback);
    adapters.errors.report(appErr);
    return appErr;
  };

  /**
   * Acredita lo que pagaron los mercados ya liquidados. Es la mitad que faltaba
   * del ciclo: apostar descontaba puntos y nada los devolvía nunca (R-040).
   *
   * Idempotente por diseño: el id del asiento es el de la posición, así que
   * recargar el portafolio veinte veces paga una sola vez.
   */
  const creditSettlements = (positions: Position[]) => {
    if (!isPointsMode()) return;
    let ledger = getState().points;
    let cambio = false;

    for (const position of positions) {
      const payout = position.payout ?? 0;
      if (payout <= 0) continue;
      const id = `s-${position.id}`;
      if (acreditados.has(id)) continue;
      if (ledger.entries.some((entry) => entry.id === id)) continue;
      acreditados.add(id);
      ledger = applyPoints(ledger, {
        id,
        amount: Math.round(payout),
        reason: position.status === "settled" ? "devolucion" : "liquidacion",
        at: new Date().toISOString(),
        marketId: position.market_id,
      });
      cambio = true;
      adapters.analytics.track("market_settled", {
        market_id: position.market_id,
        won: position.status === "won",
      });
    }

    if (cambio) dispatch({ type: "points", ledger });
  };

  /** Los errores del servidor ya vienen en español: se muestran tal cual. */
  const fallaCuenta = (error: unknown): string => {
    if (error && typeof error === "object" && "mensaje" in error) {
      return String((error as { mensaje: unknown }).mensaje);
    }
    if (error && typeof error === "object" && "user_message_es" in error) {
      return String((error as { user_message_es: unknown }).user_message_es);
    }
    return "No pudimos conectar. Revisa tu conexión e intenta de nuevo.";
  };

  return {
    creditSettlements,

    /** Al abrir la app: ¿hay sesión viva? Explorar no depende de la respuesta. */
    async cargarCuenta() {
      if (!adapters.api) return;
      try {
        dispatch({ type: "cuenta", cuenta: await adapters.api.yo() });
      } catch {
        /* sin servidor se sigue explorando: la cuenta no bloquea el feed */
      }
    },

    abrirCuenta(abierta: boolean) {
      dispatch({ type: "cuenta_abierta", abierta });
    },

    async registrar(datos: { usuario: string; password: string; correo?: string }) {
      if (!adapters.api || inFlight.cuenta) return false;
      inFlight.cuenta = true;
      dispatch({ type: "cuenta_busy", busy: true });
      try {
        const cuenta = await adapters.api.registro(datos);
        dispatch({ type: "cuenta", cuenta });
        dispatch({ type: "cuenta_abierta", abierta: false });
        adapters.analytics.track("cuenta_creada");
        return true;
      } catch (error) {
        dispatch({ type: "cuenta_error", error: fallaCuenta(error) });
        return false;
      } finally {
        inFlight.cuenta = false;
      }
    },

    async entrar(datos: { usuario: string; password: string }) {
      if (!adapters.api || inFlight.cuenta) return false;
      inFlight.cuenta = true;
      dispatch({ type: "cuenta_busy", busy: true });
      try {
        const cuenta = await adapters.api.entrar(datos);
        dispatch({ type: "cuenta", cuenta });
        dispatch({ type: "cuenta_abierta", abierta: false });
        adapters.analytics.track("cuenta_entrada");
        return true;
      } catch (error) {
        dispatch({ type: "cuenta_error", error: fallaCuenta(error) });
        return false;
      } finally {
        inFlight.cuenta = false;
      }
    },

    async salir() {
      if (!adapters.api) return;
      try {
        await adapters.api.salir();
      } finally {
        // salir siempre limpia de este lado, aunque el servidor no conteste
        dispatch({ type: "cuenta", cuenta: null });
        dispatch({ type: "positions", value: { status: "data", data: [] } });
      }
    },
    setTab(tab: TabId) {
      dispatch({ type: "set_tab", tab });
      if (tab === "portfolio") adapters.analytics.track("view_portfolio");
      if (tab === "markets") adapters.analytics.track("view_feed");
    },
    setCategory(category: AppState["category"]) {
      dispatch({ type: "set_category", category });
    },
    /** El usuario corrige el país inferido. Su palabra vence al dispositivo. */
    setCountry(country: CountryCode) {
      dispatch({ type: "country", country, source: "declarado" });
      adapters.analytics.track("country_detected", { country, source: "declarado" });
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
      // el dato que llega tarde (la referencia que enciende el Edge) repinta el
      // feed una vez; no se espera a él para mostrar los mercados
      if (!suscrito && adapters.marketData.subscribe) {
        suscrito = true;
        adapters.marketData.subscribe(() => {
          void adapters.marketData
            .listMarkets()
            .then((data) => dispatch({ type: "markets", value: { status: "data", data } }))
            .catch(() => {
              /* el feed ya mostrado sigue siendo válido: no se rompe por esto */
            });
        });
      }
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
        creditSettlements(data);
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
      // con servidor, apostar exige cuenta: se ofrece crearla en contexto,
      // nunca un muro previo ni un error seco (RT/4)
      if (adapters.api && !getState().cuenta) {
        inFlight.trade = false;
        dispatch({ type: "cuenta_abierta", abierta: true });
        return false;
      }
      dispatch({ type: "trade_busy", busy: true });
      dispatch({ type: "trade_error", error: null });
      try {
        if (!adapters.api && isPointsMode() && !canStake(getState().points, size)) {
          throw appErrorFor("E_TRADE_INIT_FAILED", { market_id: market.id });
        }
        await adapters.marketData.prepareTrade({
          marketId: market.id,
          side,
          size,
        });
        adapters.analytics.track("trade_confirmed", { market_id: market.id, side });
        if (adapters.api) {
          // el saldo nuevo ya vino en la respuesta del servidor
          const cuenta = await adapters.api.yo();
          dispatch({ type: "cuenta", cuenta });
        } else if (isPointsMode()) {
          dispatch({
            type: "points",
            ledger: applyPoints(getState().points, {
              id: `b-${Date.now()}`,
              amount: -size,
              reason: "apuesta",
              at: new Date().toISOString(),
              marketId: market.id,
            }),
          });
        }
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
    /** Recarga diaria contra el servidor, cuando hay cuenta. */
    async recargarEnServidor() {
      if (!adapters.api) return false;
      try {
        dispatch({ type: "cuenta", cuenta: await adapters.api.recargar() });
        return true;
      } catch (error) {
        dispatch({ type: "cuenta_error", error: fallaCuenta(error) });
        return false;
      }
    },

    /** Recarga diaria: existe para el que se quedó en cero, no como ingreso. */
    topUpPoints() {
      const ledger = getState().points;
      const amount = dailyTopUp(ledger);
      if (amount <= 0) return false;
      dispatch({
        type: "points",
        ledger: applyPoints(ledger, {
          id: `t-${Date.now()}`,
          amount,
          reason: "recarga_diaria",
          at: new Date().toISOString(),
        }),
      });
      return true;
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
