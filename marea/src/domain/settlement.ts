import { canPayout, disputeDeadline, type ResolutionSpec } from "./resolution";
import { settle, type Bet, type Pool, type Settlement, type Side } from "./parimutuel";
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
  /** Resultado leído de la fuente. */
  outcome?: Side;
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
}

/** Lo que devuelve un oráculo al consultar la fuente citada. */
export type OracleReading =
  | { status: "resuelto"; outcome: Side; evidence: string }
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
 * Registra la lectura de la fuente y abre la ventana de disputa.
 * Una lectura sin dato no avanza el ciclo: se vuelve a intentar más tarde.
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

  const at = new Date(now).toISOString();
  return {
    ...state,
    phase: "en_disputa",
    outcome: reading.outcome,
    readAt: at,
    evidence: reading.evidence,
    disputeUntil: disputeDeadline(at, spec),
  };
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
  const outcome = state.outcome as Side;
  const settlement = settle(pool, bets, outcome);
  // "nadie acertó" es que el lado ganador esté vacío del todo, semilla incluida
  const nadieAcerto = (outcome === "si" ? pool.si : pool.no) <= 0;

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
  outcome: Side,
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
