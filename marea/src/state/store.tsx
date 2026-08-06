import * as React from "react";
import type { AppError, Market, Position, PulsoVivo, Wallet } from "@/domain/types";
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
import type { MovimientoOptimista } from "@/domain/saldo";
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
import { addStake, quote, type OutcomeId } from "@/domain/parimutuel";

export type TabId = "markets" | "search" | "portfolio" | "wallet" | "tabla" | "profile";
export type OnboardingStep = "p0" | "p1" | "p2" | "p3" | "done";
/**
 * Con qué cara abre la hoja de cuenta. `recuperar` no está aquí a propósito:
 * es un desvío que sólo se toma desde dentro de la hoja, nunca una entrada.
 */
export type ModoCuenta = "registro" | "entrar";

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
  /**
   * Lo que se ve es lo último que se pudo cargar y la recarga falló. Se dice en
   * voz alta en vez de mostrarlo como fresco: si la referencia se cae, se
   * apaga; no se muestra vieja (AGENTE §10).
   */
  datosViejos: boolean;
  postTrade: {
    side: OutcomeId;
    /** El texto del resultado, para no decir "Sí" en un mercado de siete. */
    sideLabel?: string;
    size: number;
    title: string;
    /** Lo que cobra si acierta. Es la promesa que el sistema tiene que cumplir. */
    toWin: number;
    multiplier: number;
    /** A qué probabilidad entró, que es a qué precio compró. */
    probability: number;
    marketId: string;
  } | null;
  /**
   * El pulso de las velas vivas, por id de mercado. Se refresca cada pocos
   * segundos y sólo mientras haya velas en pantalla: un mercado que resuelve en
   * septiembre no tiene por qué pagar el costo de un reloj de tres segundos.
   */
  vivos: Record<string, PulsoVivo>;
  /** País declarado o inferido: define elegibilidad para depositar y operar. */
  country?: CountryCode;
  /** De dónde salió el país. Inferido se puede corregir; declarado manda. */
  countrySource: CountrySource;
  /**
   * Ledger de puntos. Sólo manda **cuando no hay cuenta de servidor**: con
   * cuenta, el saldo bueno es `cuenta.puntos` y este ledger deja de tocarse.
   * Antes los dos escribían el mismo número y por eso saltaba (ver
   * `domain/saldo.ts`). Nadie lo lee directo: se lee por `saldoVisible`.
   */
  points: PointsLedger;
  /**
   * Movimientos que la persona ya confirmó y el servidor todavía no acusa. Se
   * suman al saldo para que la interfaz responda al instante, y se quitan por
   * id —tanto al confirmar como al fallar— para que nunca quede un número que
   * nadie respalda.
   */
  optimistas: MovimientoOptimista[];
  /**
   * Cuenta en el servidor. `null` significa que estás explorando sin entrar,
   * que es un estado legítimo y completo: mirar nunca pide cuenta (R-002).
   */
  cuenta: Cuenta | null;
  /**
   * Cuándo se supo de la cuenta por última vez (`Date.now()`). Existe para no
   * volver a pedirla en cada montaje: al cambiar de pestaña las pantallas se
   * desmontan, y `cargarCuenta()` sin guarda disparaba una petición por visita.
   */
  cuentaAt: number | null;
  /** La hoja de cuenta está abierta. Se abre al querer apostar sin sesión. */
  cuentaAbierta: boolean;
  /**
   * Con qué cara abre la hoja. Quien vuelve entra por "Entrar" y no tiene por
   * qué pasar por un formulario de registro que no es el suyo.
   */
  cuentaModo: ModoCuenta;
  cuentaBusy: boolean;
  cuentaError: string | null;
  /**
   * Código de recuperación recién entregado. Se muestra una sola vez y no se
   * guarda en ningún lado: es lo único que devuelve la cuenta si se olvida la
   * contraseña, y sólo el usuario lo tiene.
   */
  codigoRecuperacion: string | null;
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
  | { type: "frescura"; viejo: boolean }
  | { type: "vivos"; pulsos: PulsoVivo[] }
  | { type: "balance"; balance: number }
  | { type: "points"; ledger: PointsLedger }
  | { type: "optimista"; movimiento: MovimientoOptimista }
  | { type: "optimista_cerrar"; id: string }
  | { type: "country"; country: CountryCode; source: CountrySource }
  | { type: "cuenta"; cuenta: Cuenta | null }
  | { type: "cuenta_abierta"; abierta: boolean; modo?: ModoCuenta }
  | { type: "cuenta_busy"; busy: boolean }
  | { type: "cuenta_error"; error: string | null }
  | { type: "codigo_recuperacion"; codigo: string | null };

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
    datosViejos: false,
    postTrade: null,
    vivos: {},
    country: guess.country,
    countrySource: guess.source,
    cuenta: null,
    cuentaAt: null,
    optimistas: [],
    cuentaAbierta: false,
    cuentaModo: "registro",
    cuentaBusy: false,
    cuentaError: null,
    codigoRecuperacion: null,
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
    case "frescura":
      if (state.datosViejos === action.viejo) return state;
      return { ...state, datosViejos: action.viejo };
    case "vivos": {
      // se reemplaza entero: una vela que ya no viene es una vela que ya cerró,
      // y dejar su último latido en el mapa la pintaría viva para siempre
      const vivos: Record<string, PulsoVivo> = {};
      for (const pulso of action.pulsos) vivos[pulso.id] = pulso;
      return { ...state, vivos };
    }
    case "points":
      return { ...state, points: action.ledger };
    case "optimista":
      return { ...state, optimistas: [...state.optimistas, action.movimiento] };
    case "optimista_cerrar":
      // sirve para confirmar y para deshacer: en los dos casos el movimiento
      // deja de estar en el aire. Al confirmar, el saldo base ya lo incluye
      return {
        ...state,
        optimistas: state.optimistas.filter((m) => m.id !== action.id),
      };
    case "country":
      return { ...state, country: action.country, countrySource: action.source };
    case "cuenta":
      return {
        ...state,
        cuenta: action.cuenta,
        cuentaAt: action.cuenta ? Date.now() : null,
        cuentaBusy: false,
        cuentaError: null,
        // `points` ya NO se toca aquí. Escribir `balance` desde la cuenta y
        // dejar los `entries` como estaban rompía el invariante del ledger
        // (`balance === Σ entries`) y ponía a dos escritores sobre el mismo
        // número. Con cuenta manda `cuenta.puntos` y punto; sin cuenta manda
        // el ledger. Quien decide cuál se ve es `saldoVisible`, no el reducer
      };
    case "cuenta_abierta":
      return {
        ...state,
        cuentaAbierta: action.abierta,
        // al cerrar se conserva el modo: cambiarlo aquí haría parpadear el
        // título mientras la hoja se va
        cuentaModo: action.modo ?? state.cuentaModo,
        cuentaError: null,
      };
    case "cuenta_busy":
      return { ...state, cuentaBusy: action.busy, cuentaError: null };
    case "cuenta_error":
      return { ...state, cuentaError: action.error, cuentaBusy: false };
    case "codigo_recuperacion":
      return { ...state, codigoRecuperacion: action.codigo };
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
  /**
   * Cable por el que el adapter empuja la cuenta fresca que viene dentro de
   * cada respuesta del servidor. Sin él, el saldo bueno llegaba y se tiraba.
   */
  alRecibirCuenta?: (fn: (cuenta: Cuenta) => void) => void;
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

  /**
   * Ids de los movimientos optimistas. Se cuenta y no se sella con la hora:
   * dos apuestas dentro del mismo milisegundo compartirían `Date.now()` y
   * cerrar una cerraría la otra — el mismo defecto que el doble tap (R-016).
   */
  let secuencia = 0;
  const contador = () => (secuencia += 1);

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
    // Con servidor **no se acredita nada aquí**: `store.mts` ya sumó el pago a
    // `usuario.puntos` al liquidar, y volver a sumarlo en el cliente era la
    // causa del saldo que saltaba entre 700 y 900. Esta rama existe sólo para
    // el modo sin servidor, donde el ledger local es la única contabilidad
    if (adapters.api) return;
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

  /**
   * Carga las posiciones. Vive fuera del objeto de acciones porque `submitTrade`
   * también la necesita: al confirmar, la lista del servidor reemplaza a la
   * posición pendiente que se pintó de forma optimista, y así el portafolio no
   * se queda con una copia fantasma marcada como "pendiente" para siempre.
   */
  const cargarPosiciones = async () => {
    // volver al portafolio no vacía la lista para volver a llenarla: lo que
    // ya se cargó sigue siendo válido mientras llega lo nuevo. Ese parpadeo
    // era gratis y se notaba en cada cambio de pestaña
    if (getState().positions.status !== "data") {
      dispatch({ type: "positions", value: { status: "loading" } });
    }
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

    /**
     * ¿Hay sesión viva? Explorar no depende de la respuesta.
     *
     * Se llama al montar cualquier pantalla que enseñe saldo, y por eso lleva
     * guarda de frescura: sin ella, cambiar de pestaña disparaba una petición
     * por visita —las pantallas se desmontan, no hay router— y el saldo
     * parpadeaba mientras iba y volvía. Con `maxEdadMs` el dato reciente se
     * reusa y el viejo se vuelve a pedir, que es lo que hace que el header y el
     * portafolio partan siempre del mismo número.
     */
    async cargarCuenta(maxEdadMs = 0) {
      if (!adapters.api) return;
      const { cuentaAt, optimistas } = getState();
      if (maxEdadMs > 0 && cuentaAt !== null && Date.now() - cuentaAt < maxEdadMs) {
        return;
      }
      // con un movimiento en el aire, la respuesta del servidor todavía no lo
      // incluye: pedirla ahora haría parpadear el saldo al valor de antes
      if (optimistas.length > 0) return;
      try {
        dispatch({ type: "cuenta", cuenta: await adapters.api.yo() });
      } catch {
        /* sin servidor se sigue explorando: la cuenta no bloquea el feed */
      }
    },

    abrirCuenta(abierta: boolean, modo?: ModoCuenta) {
      dispatch({ type: "cuenta_abierta", abierta, modo });
    },

    async registrar(datos: { usuario: string; password: string; correo?: string }) {
      if (!adapters.api || inFlight.cuenta) return false;
      inFlight.cuenta = true;
      dispatch({ type: "cuenta_busy", busy: true });
      try {
        const cuenta = await adapters.api.registro(datos);
        dispatch({ type: "cuenta", cuenta });
        // no se cierra la hoja: primero tiene que guardar su código
        dispatch({ type: "codigo_recuperacion", codigo: cuenta.codigoRecuperacion });
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

    async recuperarCuenta(datos: { usuario: string; codigo: string; password: string }) {
      if (!adapters.api || inFlight.cuenta) return false;
      inFlight.cuenta = true;
      dispatch({ type: "cuenta_busy", busy: true });
      try {
        dispatch({ type: "cuenta", cuenta: await adapters.api.recuperar(datos) });
        dispatch({ type: "cuenta_abierta", abierta: false });
        return true;
      } catch (error) {
        dispatch({ type: "cuenta_error", error: fallaCuenta(error) });
        return false;
      } finally {
        inFlight.cuenta = false;
      }
    },

    /** El usuario dice que ya guardó su código: recién ahí se cierra la hoja. */
    codigoGuardado() {
      dispatch({ type: "codigo_recuperacion", codigo: null });
      dispatch({ type: "cuenta_abierta", abierta: false });
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
    /**
     * Sigue el pulso de las velas vivas mientras haya alguna en pantalla.
     *
     * Es un reloj propio y no una recarga del feed: pedir el catálogo entero
     * cada tres segundos mandaría el título, el criterio de resolución y la
     * fuente de cada mercado veinte veces por minuto para enterarse de que el
     * precio se movió dos dólares (R-047).
     *
     * Devuelve la función que lo apaga. Sin llamarla, el reloj sigue corriendo
     * con la pestaña en segundo plano gastando la batería de alguien.
     */
    seguirVivos(cadaMs = 3_000): () => void {
      if (!adapters.api) return () => {};
      let vivo = true;
      let temporizador: ReturnType<typeof setTimeout> | null = null;

      const latir = async () => {
        if (!vivo) return;
        try {
          const { mercados } = await adapters.api!.vivos();
          if (vivo) dispatch({ type: "vivos", pulsos: mercados });
        } catch {
          // un latido perdido no rompe nada: la card sigue con el último que
          // recibió y su reloj local, que corre solo
        }
        if (vivo) temporizador = setTimeout(() => void latir(), cadaMs);
      };

      void latir();
      return () => {
        vivo = false;
        if (temporizador) clearTimeout(temporizador);
      };
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
      // si ya hay mercados en pantalla no se vuelve a "cargando": vaciar el
      // feed para volver a llenarlo es un parpadeo, y con la red caída sería
      // cambiar contenido bueno por una pantalla en blanco
      if (getState().markets.status !== "data") {
        dispatch({ type: "markets", value: { status: "loading" } });
      }
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
        dispatch({ type: "frescura", viejo: false });
      } catch (error) {
        // lo último que se cargó se sigue viendo, marcado como viejo. Un feed
        // en blanco es peor que un feed de hace un minuto, siempre que se diga
        // que es de hace un minuto (R-047)
        if (getState().markets.status === "data") {
          dispatch({ type: "frescura", viejo: true });
          return;
        }
        dispatch({
          type: "markets",
          value: { status: "error", error: fail(error, "E_MARKETS_FETCH_FAILED") },
        });
      }
    },
    loadPositions: cargarPosiciones,
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
    async submitTrade(market: Market, side: OutcomeId, size: number) {
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

      // Apuesta optimista: el saldo y el pozo se mueven al instante y el
      // servidor manda después. Con la red lenta, esperar el viaje de ida y
      // vuelta hacía que la app pareciera trabada justo en el momento que más
      // importa.
      //
      // El descuento entra como movimiento con id, no como foto del saldo
      // anterior. Con la foto, dos apuestas seguidas se pisaban: la segunda
      // retrataba el valor ya descontado por la primera, y deshacer la primera
      // restauraba un número que ya no era verdad. Restar `size` y luego
      // quitar ese movimiento da igual en cualquier orden de respuesta.
      const movimiento = { id: `apuesta-${market.id}-${contador()}`, delta: -size };
      const antesMercados = getState().markets;
      const antesPosiciones = getState().positions;
      const optimista = market.pool
        ? {
            ...market,
            pool: addStake(market.pool, side, size),
          }
        : market;
      dispatch({ type: "optimista", movimiento });
      // la posición entra a "Abiertas" ya, marcada como pendiente. Apostar y
      // que el portafolio siga vacío hasta que responda el servidor es la
      // forma más rápida de que alguien crea que su apuesta se perdió
      if (antesPosiciones.status === "data") {
        const cotiza = market.pool ? quote(market.pool, side, size) : null;
        dispatch({
          type: "positions",
          value: {
            status: "data",
            data: [
              {
                id: movimiento.id,
                market_id: market.id,
                side,
                sideLabel: market.outcomes?.find((o) => o.id === side)?.label,
                size,
                entry_price: cotiza?.probability ?? market.probability,
                pnl: 0,
                status: "open",
                marketTitle: market.title,
                toWin: cotiza?.toWin,
                multiplier: cotiza?.multiplier,
                pendiente: true,
              },
              ...antesPosiciones.data,
            ],
          },
        });
      }
      if (antesMercados.status === "data" && market.pool) {
        dispatch({
          type: "markets",
          value: {
            status: "data",
            data: antesMercados.data.map((m) => (m.id === market.id ? optimista : m)),
          },
        });
      }

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
          // Se pide la cuenta explícitamente en vez de confiar en el aviso que
          // el adapter emite al vuelo: mientras hay un movimiento en el aire
          // ese aviso se ignora —no se puede distinguir de una respuesta
          // anterior a la apuesta, y aplicarla haría saltar el saldo al valor
          // de antes—, así que aquí hace falta el dato bueno de forma
          // inequívoca antes de cerrar el movimiento. Es un viaje de más que
          // el usuario no espera: el saldo ya se movió hace rato
          dispatch({ type: "cuenta", cuenta: await adapters.api.yo() });
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
        // la cotización que se le mostró antes de entrar es exactamente la que
        // se le confirma después: el número que se enseña es el que se cobra
        // (I3). Recalcularla con otra fórmula aquí sería abrir la puerta a que
        // las dos se separen
        const cotizado = market.pool
          ? quote(market.pool, side, size)
          : { toWin: size, multiplier: 1, probability: market.probability };
        dispatch({
          type: "post_trade",
          value: {
            side,
            sideLabel: market.outcomes?.find((o) => o.id === side)?.label,
            size,
            title: market.title,
            marketId: market.id,
            toWin: cotizado.toWin,
            multiplier: cotizado.multiplier,
            probability: cotizado.probability,
          },
        });
        // un golpecito donde exista; donde no, no pasa nada
        try {
          (globalThis.navigator as Navigator & { vibrate?: (p: number) => boolean })
            ?.vibrate?.(12);
        } catch {
          /* sin vibración no se rompe nada */
        }
        if (!isPointsMode()) {
          // con dinero el saldo vive en la wallet y es ella la que baja
          const balance = getState().wallet?.balance ?? 0;
          dispatch({ type: "balance", balance: Math.max(0, balance - size) });
        }
        // el saldo base ya trae el descuento: el movimiento deja de estar en el
        // aire. Va después del `cuenta` a propósito, y React agrupa los dos en
        // una sola pintada, así que el número no baja de más ni por un cuadro
        dispatch({ type: "optimista_cerrar", id: movimiento.id });
        // la lista de verdad reemplaza a la posición pendiente. Sin esto se
        // quedaría marcada como pendiente hasta la siguiente carga, con un id
        // que el servidor no conoce
        if (antesPosiciones.status === "data") void cargarPosiciones();
        return true;
      } catch (error) {
        // el servidor no lo aceptó: se devuelve la pantalla a como estaba. Un
        // saldo descontado por una apuesta que no existe es exactamente el
        // estado mentiroso que la apuesta optimista no puede dejar
        dispatch({ type: "optimista_cerrar", id: movimiento.id });
        if (antesMercados.status === "data") {
          dispatch({ type: "markets", value: antesMercados });
        }
        // y la posición que se pintó pendiente se va con ella: dejarla sería
        // enseñar una apuesta que no existe en ningún lado
        if (antesPosiciones.status === "data") {
          dispatch({ type: "positions", value: antesPosiciones });
        }
        dispatch({ type: "trade_error", error: fail(error, "E_TRADE_INIT_FAILED") });
        return false;
      } finally {
        inFlight.trade = false;
      }
    },
    /** Marca lo que hay en pantalla como lo ultimo que se pudo cargar. */
    marcarDatosViejos(viejo: boolean) {
      dispatch({ type: "frescura", viejo });
    },
    dismissPostTrade() {
      dispatch({ type: "post_trade", value: null });
    },
    setBalance(balance: number) {
      dispatch({ type: "balance", balance });
    },
    /**
     * Recarga diaria contra el servidor.
     *
     * También optimista: los puntos aparecen al tocar y se retiran si el
     * servidor dice que no. El monto es el que el propio servidor declara
     * disponible (`recargaDisponible`), no uno que inventemos aquí.
     */
    async recargarEnServidor() {
      if (!adapters.api) return false;
      const cuenta = getState().cuenta;
      const disponible = cuenta?.recargaDisponible ?? 0;
      const movimiento = { id: `recarga-${contador()}`, delta: disponible };
      if (disponible > 0) dispatch({ type: "optimista", movimiento });
      try {
        dispatch({ type: "cuenta", cuenta: await adapters.api.recargar() });
        dispatch({ type: "optimista_cerrar", id: movimiento.id });
        return true;
      } catch (error) {
        dispatch({ type: "optimista_cerrar", id: movimiento.id });
        dispatch({ type: "cuenta_error", error: fallaCuenta(error) });
        return false;
      }
    },

    /**
     * Recarga diaria: existe para el que se quedó en cero, no como ingreso.
     *
     * Con servidor delega en él. Antes sumaba siempre al ledger local, y como
     * el saldo bueno venía de la cuenta, la recarga se deshacía sola en la
     * siguiente visita al feed: el botón parecía funcionar y no funcionaba.
     */
    topUpPoints(): boolean | Promise<boolean> {
      if (adapters.api) return this.recargarEnServidor();
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

  /**
   * La cuenta que el servidor mete en cada respuesta entra directo al store.
   * Con un movimiento optimista en el aire se ignora: esa respuesta todavía no
   * lo incluye y aplicarla haría parpadear el saldo al valor de antes.
   */
  React.useEffect(() => {
    adapters.alRecibirCuenta?.((cuenta) => {
      if (stateRef.current.optimistas.length > 0) return;
      dispatch({ type: "cuenta", cuenta });
    });
  }, [adapters]);

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
