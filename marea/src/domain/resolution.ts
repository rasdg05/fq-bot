/**
 * Resolución de mercados propios. Este es el punto que hace o rompe la
 * confianza: si el criterio no es transparente, perdemos lo único que
 * vendemos.
 *
 * Tres reglas que no se negocian (R-025):
 *  1. La fuente es pública y auditable, y se cita **antes** de apostar.
 *  2. La resolución nunca es discrecional: "porque Marea lo dice" no existe.
 *  3. Hay ventana de disputa antes de pagar.
 *
 * Un mercado propio sin especificación completa no se puede publicar. No es
 * una advertencia: `assertPublishable` lo rechaza.
 */

export interface ResolutionSpec {
  /** Quién publica el dato. Institución concreta, no "el mercado". */
  sourceName: string;
  /** Dónde se verifica, público. */
  sourceUrl: string;
  /** El criterio en una frase clara, en español. Es lo que ve el usuario. */
  criterion: string;
  /** Cuándo se publica el dato que resuelve. */
  settlesAt: string;
  /** Horas para disputar antes de pagar. */
  disputeWindowHours: number;
  /**
   * El resultado se lee de un dato que ya está publicado y que cualquiera
   * re-verifica con **una** consulta: el cierre de una vela concreta en un
   * endpoint público. Sólo estos mercados pueden bajar de las 12 h de disputa.
   *
   * La ventana de 12 h existe porque un dato institucional se corrige: el INEGI
   * revisa, el BCRA republica, y pagar antes de que el dato se asiente sería
   * pagar sobre algo que puede cambiar. El cierre de una vela de cinco minutos
   * no se revisa: o está en la respuesta de Kraken o no está. Bajar la ventana
   * ahí no afloja la promesa, la ajusta al tipo de dato — y por eso la excepción
   * es explícita y por mercado, no un mínimo global más bajo (R-025).
   *
   * Un mercado de cinco minutos con 12 h de disputa no es más honesto: es un
   * mercado que no se puede pagar.
   */
  liveVerification?: boolean;
}

import type { OutcomeId } from "./parimutuel";

export type ResolutionState =
  | { status: "abierto" }
  | { status: "esperando_fuente"; since: string }
  | { status: "en_disputa"; outcome: OutcomeId; until: string }
  | { status: "resuelto"; outcome: OutcomeId; at: string };

export const MIN_DISPUTE_HOURS = 12;

/**
 * Piso de la ventana de disputa para los mercados de verificación inmediata.
 * Sesenta segundos son suficientes para abrir la URL citada y mirar la vela; por
 * debajo de eso la ventana sería decorativa, y una ventana decorativa es peor
 * que no tenerla porque la nombra el copy.
 */
export const MIN_DISPUTE_SECONDS_LIVE = 60;

export class UnpublishableMarket extends Error {
  constructor(readonly reasons: string[]) {
    super(`Mercado no publicable: ${reasons.join("; ")}`);
    this.name = "UnpublishableMarket";
  }
}

/** Motivos por los que una especificación no puede salir a producción. */
export function publishProblems(spec: Partial<ResolutionSpec>): string[] {
  const problems: string[] = [];
  if (!spec.sourceName?.trim()) problems.push("falta la institución que publica el dato");
  if (!spec.sourceUrl?.trim()) problems.push("falta la URL pública de verificación");
  else if (!/^https:\/\//.test(spec.sourceUrl)) {
    problems.push("la fuente tiene que ser una URL pública sobre https");
  }
  if (!spec.criterion?.trim()) problems.push("falta el criterio de resolución");
  else if (spec.criterion.trim().length < 25) {
    problems.push("el criterio es demasiado corto para ser inequívoco");
  } else if (/marea (decide|determina|define)|a criterio de/i.test(spec.criterion)) {
    // la resolución discrecional es justo lo que promete no hacer la marca
    problems.push("el criterio es discrecional: la resolución no puede depender de Marea");
  }
  if (!spec.settlesAt) problems.push("falta la fecha en que se publica el dato");
  else if (Number.isNaN(new Date(spec.settlesAt).getTime())) {
    problems.push("la fecha de resolución no es válida");
  }
  if (spec.disputeWindowHours === undefined) problems.push("falta la ventana de disputa");
  else if (spec.liveVerification) {
    const segundos = spec.disputeWindowHours * 3_600;
    if (segundos < MIN_DISPUTE_SECONDS_LIVE) {
      problems.push(
        `la ventana de disputa de un mercado vivo no puede bajar de ${MIN_DISPUTE_SECONDS_LIVE} s`,
      );
    }
  } else if (spec.disputeWindowHours < MIN_DISPUTE_HOURS) {
    problems.push(`la ventana de disputa no puede bajar de ${MIN_DISPUTE_HOURS} h`);
  }
  return problems;
}

/** La ventana de disputa dicha en la unidad en que se entiende. */
export function ventanaDeDisputa(spec: ResolutionSpec): string {
  if (!spec.liveVerification) return `${spec.disputeWindowHours} h`;
  return `${Math.round(spec.disputeWindowHours * 3_600)} s`;
}

export function assertPublishable(spec: Partial<ResolutionSpec>): ResolutionSpec {
  const problems = publishProblems(spec);
  if (problems.length > 0) throw new UnpublishableMarket(problems);
  return spec as ResolutionSpec;
}

/** La frase que lee el usuario antes de apostar. Nunca se genera sola. */
export function resolutionSummary(spec: ResolutionSpec): string {
  return `${spec.criterion} Fuente: ${spec.sourceName}. Puedes disputar el resultado durante ${ventanaDeDisputa(
    spec,
  )} antes de que se pague.`;
}

export function disputeDeadline(settledAt: string, spec: ResolutionSpec): string {
  return new Date(
    new Date(settledAt).getTime() + spec.disputeWindowHours * 3_600_000,
  ).toISOString();
}

/** Sólo se paga cuando la ventana de disputa cerró. */
export function canPayout(state: ResolutionState, now: number = Date.now()): boolean {
  if (state.status === "resuelto") return true;
  if (state.status === "en_disputa") return new Date(state.until).getTime() <= now;
  return false;
}
