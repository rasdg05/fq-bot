import { canPayout, disputeDeadline, type ResolutionSpec } from "./resolution";
import {
  bettorStake,
  settle,
  type Bet,
  type OutcomeId,
  type Pool,
  type Settlement,
} from "./parimutuel";
import type { OracleRule } from "./oracleRule";

/**
 * Ciclo de liquidación. Es la parte del producto que la gente olvida y la que
 * sostiene la confianza: un mercado que cierra tiene que resolverse y pagar
 * (R-040).
 *
 * El ciclo completo, con sus puertas:
 *
 *   abierto → cerrado → leído → en_disputa → pagado
 *
 * Cada paso es explícito y ninguno se salta. En particular **no se paga
 * mientras la ventana de disputa siga abierta**, aunque el resultado ya se
 * conozca: esa espera es la promesa, no una demora.
 */

export type SettlementPhase =
  | "abierto"
  | "cerrado"
  | "leido"
  | "en_disputa"
  | "pagado"
  | "devuelto"
  | "atorado";

export interface SettlementState {
  marketId: string;
  phase: SettlementPhase;
  /**
   * Resultado leído de la fuente: el id del resultado ganador. Con dos
   * respuestas es `si` o `no`; con N, uno de los ids que declaró el mercado.
   */
  outcome?: OutcomeId;
  /** Cuándo se leyó la fuente. */
  readAt?: string;
  /** Qué se leyó exactamente, para poder auditarlo después. */
  evidence?: string;
  /** Hasta cuándo se puede disputar. */
  disputeUntil?: string;
  /** Cuándo se pagó. */
  paidAt?: string;
  /** Por qué se atoró, si se atoró. */
  stuckReason?: string;
  /**
   * De cuándo era el dato con el que se resolvió, y si su antigüedad se pudo
   * comprobar. `false` no es un fallo: es la diferencia entre «está fresco» y
   * «no sé si está fresco», y confundirlas es cómo una fuente parada pasa por
   * una viva.
   */
  observedAt?: string;
  frescuraVerificada?: boolean;
}

/** Lo que devuelve un oráculo al consultar la fuente citada. */
export type OracleReading =
  | {
      status: "resuelto";
      outcome: OutcomeId;
      evidence: string;
      /**
       * De cuándo es el **dato**, no cuándo lo pedimos.
       *
       * Es la diferencia entera. Una fuente parada contesta al instante y con
       * un 200: lo que delata que dejó de medir no es la latencia, es que el
       * dato que devuelve sigue siendo el de anteayer. Sin este campo, un
       * colector detenido resuelve mercados con la misma cara que uno vivo —
       * que es exactamente el fallo que en el bot obligó a cablear
       * `cvd_confirmation`.
       *
       * Opcional porque no todos los oráculos lo reportan todavía. Cuando
       * falta, la frescura **no se puede verificar** y el estado lo dice; no
       * se finge que sí.
       */
      observedAt?: string;
    }
  /** La fuente aún no publicó el dato. Se reintenta. */
  | { status: "sin_dato"; evidence: string }
  /** La fuente no se puede leer por programa: necesita a una persona. */
  | { status: "requiere_humano"; evidence: string };

export interface OracleQuery {
  marketId: string;
  spec: ResolutionSpec;
  /** La misma condición, escrita para que un programa la ejecute. */
  rule?: OracleRule;
  now: number;
}

export interface Oracle {
  readonly id: string;
  /** ¿Este oráculo sabe leer esta fuente? */
  handles(query: OracleQuery): boolean;
  read(query: OracleQuery): Promise<OracleReading>;
}

/**
 * Pregunta al primer oráculo que sepa leer la fuente. Si ninguno sabe, la
 * respuesta honesta es que hace falta una persona: nunca un resultado inventado
 * ni un silencio que deje el mercado colgado.
 */
export async function readWithOracles(
  oracles: Oracle[],
  query: OracleQuery,
): Promise<{ reading: OracleReading; oracleId: string }> {
  const oracle = oracles.find((candidate) => candidate.handles(query));
  if (!oracle) {
    return {
      oracleId: "ninguno",
      reading: {
        status: "requiere_humano",
        evidence: `Ningún oráculo sabe leer ${query.spec.sourceName}. Verificar en ${query.spec.sourceUrl}`,
      },
    };
  }
  try {
    return { oracleId: oracle.id, reading: await oracle.read(query) };
  } catch (error) {
    // una caída de red no es un resultado: se reintenta en la próxima corrida
    return {
      oracleId: oracle.id,
      reading: {
        status: "sin_dato",
        evidence: `No se pudo leer ${query.spec.sourceName}: ${
          error instanceof Error ? error.message : String(error)
        }`,
      },
    };
  }
}

export function initialState(marketId: string): SettlementState {
  return { marketId, phase: "abierto" };
}

/** Un mercado cuya fecha de cierre ya pasó deja de aceptar apuestas. */
export function onClose(state: SettlementState): SettlementState {
  if (state.phase !== "abierto") return state;
  return { ...state, phase: "cerrado" };
}

/**
 * Umbral de referencia para las fuentes que laten a diario o más rápido —
 * velas de Kraken, marcadores de ESPN. Dos días: holgado para una fuente que se
 * retrasa, apretado para que un colector detenido no pase de la segunda corrida.
 *
 * **No es un default global**, y eso se decidió midiendo. De los 13 mercados del
 * catálogo, **9 se resuelven con series mensuales** (INPC, IPCA, IMACEC, Selic).
 * Su `observedAt` es la fecha del **periodo observado**, que por construcción
 * tiene semanas cuando el dato se publica: un umbral de 48 horas no los
 * protegería, los **atascaría a todos**. Y para ellos el reloj de pared es la
 * herramienta equivocada de todos modos — que la serie esté al día ya lo
 * comprueba la propia regla, que devuelve `sin_dato` cuando la última
 * observación es anterior al periodo que el mercado pide.
 *
 * De ahí la forma que tiene esto: **la antigüedad se mide siempre; se hace
 * cumplir sólo donde el reloj es la herramienta correcta**, y eso lo declara
 * cada mercado en `maxAgeHours`. Medir siempre importa: aunque no bloquee, un
 * `observedAt` congelado queda escrito en el estado y se puede ver.
 */
export const FRESCURA_MAX_HORAS = 48;

export interface Frescura {
  /** ¿Se pudo comprobar la antigüedad? `false` = la lectura no la declaró. */
  verificable: boolean;
  /** Horas de antigüedad del dato. `undefined` si no se pudo saber. */
  horas?: number;
  /** El umbral del mercado. `undefined` = no se hace cumplir en este mercado. */
  umbralHoras?: number;
  /**
   * ¿Se puede usar? Sólo es `false` cuando el mercado puso umbral **y** la
   * antigüedad se pudo medir **y** lo cruza. Sin umbral no se bloquea nada; sin
   * fecha tampoco, porque no saber no es lo mismo que saber que está mal.
   */
  utilizable: boolean;
}

/**
 * Cuán viejo es el dato de una lectura, **por parámetro**: la antigüedad sale
 * de `now` menos `observedAt`, los dos entrando desde fuera. Ni un reloj de
 * pared aquí dentro, o el replay heredaría la hora del click.
 *
 * Una fecha futura cuenta como antigüedad cero, no negativa: un reloj adelantado
 * en la fuente no debe poder «rejuvenecer» nada, pero tampoco es motivo para
 * bloquear un mercado.
 */
export function frescuraDe(
  reading: OracleReading,
  spec: ResolutionSpec,
  now: number,
): Frescura {
  const umbralHoras = spec.maxAgeHours;
  // sólo una lectura resuelta trae fecha; las otras no tienen dato que fechar
  const declarado = "observedAt" in reading ? reading.observedAt : undefined;
  const at = declarado ? Date.parse(declarado) : NaN;
  if (!Number.isFinite(at)) {
    // no se puede comprobar. No es lo mismo que estar fresca, y no se dice que
    // sí — pero tampoco se bloquea por no saber: eso atascaría el catálogo
    return { verificable: false, umbralHoras, utilizable: true };
  }
  const horas = Math.max(0, (now - at) / 3_600_000);
  return {
    verificable: true,
    horas,
    umbralHoras,
    utilizable: umbralHoras === undefined || horas <= umbralHoras,
  };
}

/**
 * Registra la lectura de la fuente y abre la ventana de disputa.
 * Una lectura sin dato no avanza el ciclo: se vuelve a intentar más tarde.
 *
 * **Y una lectura vieja tampoco.** Una fuente parada contesta al instante y con
 * un 200; lo que la delata es que el dato que devuelve es el de anteayer. Sin
 * esta puerta, un colector detenido resuelve mercados con la misma cara que uno
 * vivo — el mismo fallo que en el bot obligó a cablear `cvd_confirmation`. No se
 * atora el mercado: se **reintenta**, porque una fuente que se retrasó suele
 * ponerse al día sola, y atorarla llamaría a una persona sin necesidad.
 */
export function onRead(
  state: SettlementState,
  reading: OracleReading,
  spec: ResolutionSpec,
  now: number,
): SettlementState {
  // `abierto` entra a propósito: un mercado de toque resuelve en cuanto el
  // precio llega, y seguir aceptando apuestas después sería dejar apostar
  // sobre un resultado que ya ocurrió.
  const legible =
    state.phase === "abierto" || state.phase === "cerrado" || state.phase === "leido";
  if (!legible) return state;

  if (reading.status === "sin_dato") {
    return { ...state, evidence: reading.evidence };
  }
  if (reading.status === "requiere_humano") {
    // no se inventa un resultado: se marca para que alguien lo confirme
    return {
      ...state,
      phase: "atorado",
      evidence: reading.evidence,
      stuckReason: "la fuente necesita confirmación humana",
    };
  }

  const frescura = frescuraDe(reading, spec, now);
  if (!frescura.utilizable) {
    // no avanza de fase, y lo declara: la próxima corrida lo vuelve a intentar.
    // No se atora: una fuente que se retrasó suele ponerse al día sola, y
    // atorarla llamaría a una persona sin necesidad
    return {
      ...state,
      evidence: `${reading.evidence} — NO se usa: el dato es de hace ${frescura.horas!.toFixed(1)} h y el máximo de esta fuente son ${frescura.umbralHoras} h. Se reintenta.`,
      observedAt: reading.observedAt,
      frescuraVerificada: true,
    };
  }

  const at = new Date(now).toISOString();
  return {
    ...state,
    phase: "en_disputa",
    outcome: reading.outcome,
    readAt: at,
    evidence: reading.evidence,
    disputeUntil: disputeDeadline(at, spec),
    ...(reading.observedAt ? { observedAt: reading.observedAt } : {}),
    frescuraVerificada: frescura.verificable,
  };
}

/**
 * Los mercados que se resolvieron **sin poder comprobar** la antigüedad de su
 * fuente. Vacío = todas las resoluciones fueron auditables.
 *
 * Existe porque la regla escrita recuerda y sólo la verificación impide: un
 * oráculo que no reporta `observedAt` no rompe nada hoy, y por eso mismo nadie
 * se enteraría de que su fuente lleva una semana parada. Esto lo hace visible
 * en vez de dejarlo a que alguien se acuerde de mirar.
 */
export function resueltosSinFrescura(estados: readonly SettlementState[]): string[] {
  return estados
    .filter(
      (e) =>
        (e.phase === "en_disputa" || e.phase === "pagado" || e.phase === "devuelto") &&
        e.frescuraVerificada !== true,
    )
    .map((e) => e.marketId);
}

/** ¿Ya se puede pagar? Sólo con la ventana de disputa cerrada. */
export function isPayable(state: SettlementState, now: number): boolean {
  if (state.phase !== "en_disputa" || !state.outcome || !state.disputeUntil) {
    return false;
  }
  return canPayout(
    { status: "en_disputa", outcome: state.outcome, until: state.disputeUntil },
    now,
  );
}

/**
 * Cierra la ventana de disputa y autoriza el pago. El reparto concreto lo hace
 * cada cliente con `pay()` sobre su propio pozo — el runner no conoce las
 * apuestas, sólo dicta que ya se puede cobrar.
 */
export function authorizePayout(state: SettlementState, now: number): SettlementState {
  if (!isPayable(state, now)) return state;
  return { ...state, phase: "pagado", paidAt: new Date(now).toISOString() };
}

export interface Payout {
  state: SettlementState;
  settlement: Settlement;
}

/**
 * Paga. Devuelve el reparto y el estado nuevo. Si nadie acertó, el motor
 * devuelve el pozo íntegro y la fase queda como `devuelto` para que se vea
 * distinto en el portafolio (R-024).
 */
export function pay(
  state: SettlementState,
  pool: Pool,
  bets: Bet[],
  now: number,
): Payout {
  if (!isPayable(state, now)) {
    throw new Error(`no se puede pagar ${state.marketId} en fase ${state.phase}`);
  }
  const outcome = state.outcome as OutcomeId;
  const settlement = settle(pool, bets, outcome);
  // "nadie acertó" es que no haya nadie **que cobre** del lado ganador. En modo
  // "apuesta" eso es el lado vacío del todo, semilla incluida, como siempre; con
  // subsidio, un lado que sólo tiene semilla tampoco tiene ganadores. Es el
  // mismo `bettorStake` que decide el reparto, y por eso no se pueden separar
  const nadieAcerto = bettorStake(pool, outcome) <= 0;

  return {
    settlement,
    state: {
      ...state,
      phase: nadieAcerto ? "devuelto" : "pagado",
      paidAt: new Date(now).toISOString(),
    },
  };
}

/**
 * Una disputa marca el mercado para revisión humana. No revierte un pago ya
 * hecho: por eso la ventana existe antes de pagar y no después.
 */
export function dispute(state: SettlementState, motivo: string): SettlementState {
  if (state.phase === "pagado" || state.phase === "devuelto") return state;
  return { ...state, phase: "atorado", stuckReason: motivo };
}

/** Resolución manual, para lo que el oráculo no puede leer. */
export function resolveByHand(
  state: SettlementState,
  outcome: OutcomeId,
  evidence: string,
  spec: ResolutionSpec,
  now: number,
): SettlementState {
  const at = new Date(now).toISOString();
  return {
    ...state,
    phase: "en_disputa",
    outcome,
    readAt: at,
    evidence: `Confirmado a mano: ${evidence}`,
    disputeUntil: disputeDeadline(at, spec),
    stuckReason: undefined,
  };
}

/** Lo que hay que atender: cerrados sin leer, y atorados. */
export function needsAttention(states: SettlementState[]): SettlementState[] {
  return states.filter(
    (state) => state.phase === "cerrado" || state.phase === "atorado",
  );
}
