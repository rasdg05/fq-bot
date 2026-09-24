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

// ─────────────────────────────────────────────────────────────────────────────
// Anti-structuring (R-070)
//
// El tope no sirve si se puede fragmentar. Se evalúan los retiros sobre una
// ventana móvil acumulada, no operación por operación: varios retiros que
// individualmente quedan bajo el umbral pero sumados lo cruzan disparan
// verificación como si fueran uno solo (smurfing). El cambio recurrente de
// dirección destino en ventana corta también dispara.
//
// Sin relojes de pared: `now` entra por parámetro (como todo el repo). La
// ventana de 30 días es valor de trabajo hasta que P15 la confirme, y va como
// default parametrizable, no como constante mágica.
// ─────────────────────────────────────────────────────────────────────────────

const DIA_MS = 24 * 60 * 60 * 1000;

/** Ventana móvil por defecto, en días. Valor de trabajo hasta P15. */
export const VENTANA_STRUCTURING_DIAS = 30;

/** Nº de destinos distintos en la ventana que se lee como rotación sospechosa. */
export const MAX_DESTINOS_VENTANA = 3;

export interface Retiro {
  /** Monto del retiro, en USD (se asume > 0). */
  usd: number;
  /** Marca de tiempo del retiro, epoch ms. */
  ts: number;
  /** Dirección destino, para la heurística de rotación. */
  destino: string;
}

export interface AntiStructuringConfig {
  /** Umbral acumulado, en USD, que dispara verificación. Lo fija el abogado (P15/P16). */
  thresholdUsd: number;
  /** Ventana móvil en días. Default `VENTANA_STRUCTURING_DIAS` (30, valor de trabajo). */
  windowDays?: number;
  /** Destinos distintos en la ventana que cuentan como rotación. Default `MAX_DESTINOS_VENTANA`. */
  maxDestinos?: number;
}

export type StructuringMotivo = "acumulado" | "rotacion" | null;

export interface StructuringResult {
  /** Si el patrón dispara verificación. */
  triggered: boolean;
  /** Suma de retiros dentro de la ventana, en USD. */
  acumuladoUsd: number;
  /** Nº de direcciones destino distintas dentro de la ventana. */
  destinosDistintos: number;
  /** Qué disparó, o null si nada. */
  motivo: StructuringMotivo;
}

/**
 * R-070 — evalúa la ventana móvil que termina en `now`. Dispara si el acumulado
 * cruza el umbral (aunque cada retiro quede debajo) o si hay rotación de destinos.
 * Los retiros anteriores a la ventana no cuentan.
 */
export function detectStructuring(
  retiros: readonly Retiro[],
  config: AntiStructuringConfig,
  now: number,
): StructuringResult {
  const windowDays = config.windowDays ?? VENTANA_STRUCTURING_DIAS;
  const maxDestinos = config.maxDestinos ?? MAX_DESTINOS_VENTANA;
  const desde = now - windowDays * DIA_MS;

  const enVentana = retiros.filter((r) => r.ts > desde && r.ts <= now);
  const acumuladoUsd = enVentana.reduce((suma, r) => suma + r.usd, 0);
  const destinosDistintos = new Set(enVentana.map((r) => r.destino)).size;

  const cruzaAcumulado = acumuladoUsd > config.thresholdUsd;
  const rotacion = destinosDistintos >= maxDestinos;
  const motivo: StructuringMotivo = cruzaAcumulado
    ? "acumulado"
    : rotacion
      ? "rotacion"
      : null;

  return {
    triggered: cruzaAcumulado || rotacion,
    acumuladoUsd,
    destinosDistintos,
    motivo,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Lista cerrada de disparadores de KYC (R-072)
//
// El KYC no aparece de forma arbitraria durante la experiencia. La lista es
// cerrada por el tipo de retorno: sólo estas tres condiciones lo disparan.
// Fuera de ellas, null — no se piden papeles (R-002).
// ─────────────────────────────────────────────────────────────────────────────

export type KycTrigger = "tope" | "structuring" | "voluntario";

export interface KycContext {
  /** El usuario cruzó (o cruzaría con esta operación) el tope de operación acumulada. */
  cruzoTope: boolean;
  /** El patrón de anti-structuring se disparó (R-070). */
  structuringDetectado: boolean;
  /** El usuario pidió subir de nivel voluntariamente. */
  subeVoluntario: boolean;
}

/**
 * R-072 — devuelve qué condición cerrada dispara el KYC, o null si ninguna.
 * Precedencia estable para el motivo que se muestra: tope > structuring >
 * voluntario. Añadir un disparador nuevo exige tocar este tipo y esta función,
 * a propósito: la lista no crece sola.
 */
export function kycTrigger(ctx: KycContext): KycTrigger | null {
  if (ctx.cruzoTope) return "tope";
  if (ctx.structuringDetectado) return "structuring";
  if (ctx.subeVoluntario) return "voluntario";
  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Screening de sanciones bidireccional (R-071)
//
// Rechaza en ambos sentidos (depósito y retiro), sin excepción por nivel — por
// eso esta función ni siquiera recibe el nivel: no hay forma de conceder una
// excepción. Rechazar es NO firmar, nunca retener: no toca saldo. El saldo sigue
// siendo del usuario, que puede reintentar hacia otra dirección que sí pase.
// ─────────────────────────────────────────────────────────────────────────────

export type SentidoTransferencia = "deposito" | "retiro";

export interface ScreeningResult {
  /** Si Marea firma esta transferencia. */
  firmar: boolean;
  /** Motivo mostrable, en español. */
  motivo: string;
}

/**
 * R-071 — decide si se firma una transferencia contra una dirección. El screening
 * (la fuente de la lista de sanciones) entra como predicado inyectado, para no
 * acoplar el dominio a ninguna fuente concreta.
 */
export function screenDestino(
  direccion: string,
  isSanctioned: (dir: string) => boolean,
  sentido: SentidoTransferencia = "retiro",
): ScreeningResult {
  if (isSanctioned(direccion)) {
    return {
      firmar: false,
      motivo:
        sentido === "retiro"
          ? "No podemos firmar un retiro hacia una dirección bloqueada. Tu saldo sigue siendo tuyo: puedes retirar a otra dirección."
          : "No podemos aceptar fondos desde una dirección bloqueada.",
    };
  }
  return { firmar: true, motivo: "ok" };
}

// ─────────────────────────────────────────────────────────────────────────────
// La compuerta de cumplimiento (composición de R-069…R-072)
//
// Un único punto de entrada que la app llama para una operación con dinero. No
// hornea política contestada (si cruzar el tope bloquea o sólo pide subir de
// nivel lo decide el llamador con estos datos); compone las cuatro reglas y
// deja el resultado explícito. Puro: `now` y el predicado de sanciones entran
// por parámetro.
// ─────────────────────────────────────────────────────────────────────────────

export interface OperacionCtx {
  nivel: Nivel;
  /** Tope del país (de `eligibility.ts`), USD. Con la puerta cerrada es 0. */
  countryCapUsd: number;
  /** Monto de esta operación, USD. */
  montoUsd: number;
  /** Ya operado en el periodo vigente, USD. */
  acumuladoPeriodoUsd: number;
  /** Dirección destino del retiro, para el screening. */
  destino?: string;
  /** Predicado de sanciones inyectado. Sin él, no se evalúa screening. */
  isSanctioned?: (dir: string) => boolean;
  /** Sentido de la transferencia para el mensaje de screening. */
  sentido?: SentidoTransferencia;
  /** Historial de retiros para el anti-structuring. */
  retiros?: readonly Retiro[];
  /** Config del anti-structuring; sin ella no se evalúa. */
  antiStructuring?: AntiStructuringConfig;
  /** El usuario pidió subir de nivel voluntariamente. */
  subeVoluntario?: boolean;
  /** Reloj, epoch ms. Requerido si se pasa historial de retiros. */
  now?: number;
}

export interface CompuertaResult {
  /** R-071 — ¿se puede firmar? Si es false, nada procede. */
  firmable: boolean;
  /** R-069/L16 — tope efectivo aplicable, USD. */
  capEfectivoUsd: number;
  /** R-069 — ¿la operación (acumulado + monto) cabe en el tope? */
  dentroDelTope: boolean;
  /** R-070 — resultado del anti-structuring, o null si no se evaluó. */
  structuring: StructuringResult | null;
  /** R-072 — qué KYC exige la operación, o null. */
  requiereKyc: KycTrigger | null;
  /** Conveniencia: firmable, dentro del tope y sin KYC pendiente. */
  puedeProcederSinKyc: boolean;
  /** Motivo mostrable si algo bloquea o exige acción; "ok" si nada. */
  mensaje: string;
}

/**
 * Evalúa una operación con dinero contra la compuerta completa. El screening es
 * el único bloqueo duro; el tope y el anti-structuring se traducen en un
 * disparador de KYC (R-072), no en un rechazo silencioso.
 */
export function evaluarOperacion(ctx: OperacionCtx): CompuertaResult {
  // R-071 — screening (bloqueo duro). Sin destino/predicado, no bloquea.
  const screening =
    ctx.destino !== undefined && ctx.isSanctioned !== undefined
      ? screenDestino(ctx.destino, ctx.isSanctioned, ctx.sentido ?? "retiro")
      : { firmar: true, motivo: "ok" };

  // R-069/L16 — tope efectivo.
  const capEfectivoUsd = effectiveCapForUser(ctx.countryCapUsd, ctx.nivel);
  const dentroDelTope = ctx.acumuladoPeriodoUsd + ctx.montoUsd <= capEfectivoUsd;

  // R-070 — anti-structuring (si hay datos).
  const structuring =
    ctx.retiros !== undefined && ctx.antiStructuring !== undefined && ctx.now !== undefined
      ? detectStructuring(ctx.retiros, ctx.antiStructuring, ctx.now)
      : null;

  // R-072 — lista cerrada de KYC.
  const requiereKyc = kycTrigger({
    cruzoTope: !dentroDelTope,
    structuringDetectado: structuring?.triggered ?? false,
    subeVoluntario: ctx.subeVoluntario ?? false,
  });

  const firmable = screening.firmar;
  const puedeProcederSinKyc = firmable && dentroDelTope && requiereKyc === null;

  const mensaje = !firmable
    ? screening.motivo
    : requiereKyc === "tope"
      ? "Esta operación supera tu tope actual. Sube de nivel para continuar."
      : requiereKyc === "structuring"
        ? "Necesitamos verificar tu identidad antes de continuar."
        : requiereKyc === "voluntario"
          ? "Verificación voluntaria en curso."
          : "ok";

  return {
    firmable,
    capEfectivoUsd,
    dentroDelTope,
    structuring,
    requiereKyc,
    puedeProcederSinKyc,
    mensaje,
  };
}
