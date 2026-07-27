/**
 * Elegibilidad por país y juego responsable.
 *
 * Esto NO es asesoría legal: es la tabla operativa que traduce una decisión
 * legal ya tomada en comportamiento de producto. Cada país arranca en
 * `pendiente` y sólo pasa a `permitido` cuando hay opinión legal local escrita
 * (ver `vault/COMPLIANCE.md`). Mientras tanto, el producto se comporta de la
 * forma más conservadora posible.
 *
 * Regla que no se negocia: la elegibilidad limita **depositar y operar**,
 * nunca explorar. Mirar mercados no cuesta ni requiere permiso (R-002).
 */
export type CountryCode =
  | "MX" | "AR" | "BR" | "CL" | "CO" | "PE" | "UY" | "EC" | "BO" | "PY"
  | "VE" | "CR" | "PA" | "DO" | "GT" | "US" | "ES" | "OTRO";

export type LegalStatus =
  /** Hay opinión legal local escrita y el producto puede operar. */
  | "permitido"
  /** Sin opinión legal todavía: se explora, no se deposita. */
  | "pendiente"
  /** Opinión legal negativa o riesgo inaceptable: bloqueado. */
  | "bloqueado";

export interface CountryPolicy {
  status: LegalStatus;
  /** Tope de depósito acumulado, en USD, para contener el riesgo inicial. */
  depositCapUsd: number;
  /** Motivo mostrable, en español. */
  note: string;
}

/**
 * Estado de partida. Todo `pendiente` hasta que exista la opinión legal del
 * país: preferimos crecer despacio y limpio que rápido y turbio.
 */
export const COUNTRY_POLICY: Record<CountryCode, CountryPolicy> = {
  MX: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  AR: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  BR: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  CL: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  CO: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  PE: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  UY: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  EC: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  BO: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  PY: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  VE: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  CR: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  PA: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  DO: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  GT: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  // Estados Unidos exige registro ante la CFTC para mercados de eventos:
  // sin esa licencia no hay camino, y la decisión ya está tomada.
  US: { status: "bloqueado", depositCapUsd: 0, note: "Requiere registro ante el regulador de derivados." },
  ES: { status: "bloqueado", depositCapUsd: 0, note: "Fuera del alcance de este lanzamiento." },
  OTRO: { status: "pendiente", depositCapUsd: 0, note: "País fuera de la tabla de lanzamiento." },
};

export interface Eligibility {
  /** Explorar siempre está permitido: es el corazón de value-first. */
  canExplore: true;
  canDeposit: boolean;
  canTrade: boolean;
  status: LegalStatus;
  depositCapUsd: number;
  reason: string;
}

export function eligibilityFor(country: CountryCode | undefined): Eligibility {
  const policy = COUNTRY_POLICY[country ?? "OTRO"] ?? COUNTRY_POLICY.OTRO;
  const allowed = policy.status === "permitido";
  return {
    canExplore: true,
    canDeposit: allowed && policy.depositCapUsd > 0,
    canTrade: allowed,
    status: policy.status,
    depositCapUsd: policy.depositCapUsd,
    reason: policy.note,
  };
}

/**
 * Juego responsable. Nunca hay crédito ni apalancamiento, y el tope acumulado
 * se aplica antes de que el dinero se mueva, no después.
 */
export interface ResponsibleLimits {
  /** Depositado en la ventana vigente, en USD. */
  depositedUsd: number;
  /** Marca de tiempo del fin del enfriamiento, si el usuario lo activó. */
  cooldownUntil?: number;
}

export type DepositDecision =
  | { allowed: true; remainingUsd: number }
  | { allowed: false; reason: "pais" | "tope" | "enfriamiento"; message: string };

export function canDeposit(
  country: CountryCode | undefined,
  amountUsd: number,
  limits: ResponsibleLimits,
  now: number = Date.now(),
): DepositDecision {
  const eligibility = eligibilityFor(country);
  if (!eligibility.canDeposit) {
    return {
      allowed: false,
      reason: "pais",
      message:
        eligibility.status === "bloqueado"
          ? "Todavía no podemos recibir depósitos desde tu país. Puedes seguir explorando los mercados."
          : "Aún no abrimos depósitos en tu país. Te avisamos en cuanto estemos listos; mientras tanto puedes explorar todo.",
    };
  }
  if (limits.cooldownUntil !== undefined && limits.cooldownUntil > now) {
    return {
      allowed: false,
      reason: "enfriamiento",
      message:
        "Tienes activo un periodo de enfriamiento. Vas a poder depositar cuando termine.",
    };
  }
  const remaining = eligibility.depositCapUsd - limits.depositedUsd;
  if (amountUsd > remaining) {
    return {
      allowed: false,
      reason: "tope",
      message: `Por ahora el tope de depósito es de ${eligibility.depositCapUsd} USD. Te quedan ${Math.max(0, remaining)} USD.`,
    };
  }
  return { allowed: true, remainingUsd: remaining - amountUsd };
}
