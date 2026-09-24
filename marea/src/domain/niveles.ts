/**
 * Verificación por niveles (tiered KYC) — dominio puro.
 *
 * Esto NO es asesoría legal. Aquí vive la **estructura** de la escalera de
 * verificación y la compuerta de cumplimiento; los **números** (el tope de N2,
 * la ventana del anti-structuring, los umbrales fiscales) los fija el abogado
 * (preguntas P11 y P15–P18 del encargo) y entran por parámetro o por una
 * constante marcada provisional. La estructura no depende de esos números.
 *
 * Reglas que este módulo hace cumplir (`vault/RULINGS.md`):
 * - **R-069 / L16** — el tope por nivel se hace cumplir donde vive el dinero;
 *   el tope efectivo es `min(cap_país, cap_nivel)`.
 * - **R-070** — anti-structuring: los retiros se evalúan sobre una ventana
 *   móvil acumulada, no operación por operación. (ver `anti-structuring` abajo)
 * - **R-071** — el screening de sanciones rechaza en ambos sentidos; rechazar
 *   no es confiscar.
 * - **R-072** — el KYC sólo lo disparan tres condiciones cerradas.
 *
 * Diseño de campo: `vault/NIVELES_VERIFICACION.md` y el Plano 07 de
 * `vault/planos-construccion.html`.
 */

export type Nivel = "N0" | "N1" | "N2" | "N3";

export const NIVELES: readonly Nivel[] = ["N0", "N1", "N2", "N3"] as const;

/**
 * Tope acumulado propio del nivel N2, en USD. **Provisional, pendiente P11.**
 *
 * No es una cifra de ley: es un marcador conservador. Mientras el abogado no dé
 * el número del régimen simplificado, N2 no habilita dinero por sí solo (0). El
 * día que P11 conteste, se cambia aquí una constante — no una arquitectura.
 */
export const N2_CAP_USD_PROVISIONAL = 0;

export interface NivelInfo {
  nivel: Nivel;
  /** Nombre corto del rol, en español. */
  etiqueta: string;
  /** Qué se le pide para estar en este nivel. */
  seLePide: string;
  /** Qué puede hacer en este nivel. */
  puede: string;
  /**
   * Tope acumulado que impone el propio nivel, en USD.
   * `null` = el nivel no impone tope; sólo manda el del país (caso N3).
   */
  capNivelUsd: number | null;
  /** Si el nivel permite mover dinero (USDC), o sólo puntos / explorar. */
  operaConDinero: boolean;
}

/**
 * La escalera N0–N3 como estructura de datos. Una columna, no una arquitectura
 * nueva: encaja sobre el tope por país que ya tiene `eligibility.ts`.
 */
export const ESCALERA: Record<Nivel, NivelInfo> = {
  N0: {
    nivel: "N0",
    etiqueta: "visitante",
    seLePide: "nada",
    puede: "explorar catálogo, precios y resultados",
    capNivelUsd: 0,
    operaConDinero: false,
  },
  N1: {
    nivel: "N1",
    etiqueta: "jugador",
    seLePide: "alias + código de recuperación",
    puede: "jugar con puntos",
    capNivelUsd: 0,
    operaConDinero: false,
  },
  N2: {
    nivel: "N2",
    etiqueta: "operador",
    seLePide: "wallet propia + screening de sanciones + país declarado",
    puede: "operar con USDC bajo tope, sin documento de identidad",
    capNivelUsd: N2_CAP_USD_PROVISIONAL,
    operaConDinero: true,
  },
  N3: {
    nivel: "N3",
    etiqueta: "verificado",
    seLePide: "identidad verificada, voluntaria",
    puede: "operar sin tope de nivel; insignia y funciones de confianza",
    capNivelUsd: null,
    operaConDinero: true,
  },
};

/** Tope propio del nivel, en USD. `null` → el nivel no impone tope. */
export function capNivel(nivel: Nivel): number | null {
  return ESCALERA[nivel].capNivelUsd;
}

/**
 * R-069 / L16 — el tope efectivo es `min(cap_país, cap_nivel)`.
 *
 * `nivelCapUsd === null` significa que el nivel no impone tope (N3): entonces
 * manda el del país. Se implementa tratando null como +∞ para que el `min` sea
 * exacto. Ambos topes se asumen en USD y ≥ 0.
 */
export function effectiveCapUsd(countryCapUsd: number, nivelCapUsd: number | null): number {
  const nivelCap = nivelCapUsd ?? Number.POSITIVE_INFINITY;
  return Math.min(countryCapUsd, nivelCap);
}

/**
 * Tope efectivo para un usuario en un nivel dado, contra el tope de su país.
 * El tope de país lo provee quien llama (típicamente `eligibility.ts`), para no
 * acoplar este dominio a la tabla de países ni rozar la puerta de elegibilidad.
 */
export function effectiveCapForUser(countryCapUsd: number, nivel: Nivel): number {
  return effectiveCapUsd(countryCapUsd, capNivel(nivel));
}
