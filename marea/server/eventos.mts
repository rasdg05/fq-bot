import { appendFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

/**
 * Bitácora de eventos. Es lo que convierte un lanzamiento a ciegas en uno que
 * se puede medir: cuánta gente llega, cuánta crea cuenta, cuánta apuesta y
 * cuánta vuelve al día siguiente.
 *
 * Se guarda en casa, no en un tercero. Dos razones, las dos de peso: el
 * comportamiento de nuestros usuarios no se le regala a nadie, y ese registro
 * acumulado es del producto (ESTRATEGIA §3).
 *
 * Formato NDJSON, un archivo por día: se lee con `grep`, se cuenta con `wc` y
 * se procesa con cualquier cosa. Un formato aburrido es un formato que sigue
 * sirviendo en dos años.
 *
 * **Lista blanca de nombres y de campos.** El cliente ya filtra (R-020), pero
 * aquí se vuelve a filtrar: nunca se confía en lo que manda un navegador.
 */

const EVENTOS = new Set([
  "view_feed",
  "open_market_detail",
  "click_trade_cta",
  "trade_confirmed",
  "view_portfolio",
  "view_onboarding_step",
  "onboarding_completed",
  "explore_without_funds",
  "cuenta_creada",
  "cuenta_entrada",
  "market_settled",
  "country_detected",
  "eligibility_blocked",
  "web_vital",
  "click_deposit_cta",
  "deposit_method_selected",
  "deposit_started",
  "wallet_created",
  "wallet_connected",
]);

/** Campos que pueden acompañar a un evento. Nada más pasa. */
const CAMPOS = new Set([
  "market_id",
  "side",
  "size",
  "step",
  "reason",
  "count",
  "has_edge",
  "won",
  "country",
  "source",
  "kind",
  "name",
  "value",
  "rating",
  "release",
]);

export interface EventoGuardado {
  at: string;
  event: string;
  usuario?: string;
  props?: Record<string, unknown>;
}

export function limpiarEvento(
  bruto: Record<string, unknown>,
  usuario?: string,
): EventoGuardado | null {
  const nombre = typeof bruto.event === "string" ? bruto.event : "";
  if (!EVENTOS.has(nombre)) return null;

  const entrada = (bruto.props ?? {}) as Record<string, unknown>;
  const props: Record<string, unknown> = {};
  for (const [clave, valor] of Object.entries(entrada)) {
    if (!CAMPOS.has(clave)) continue;
    // sólo escalares: un objeto anidado puede traer cualquier cosa adentro
    if (typeof valor === "object" && valor !== null) continue;
    // y el texto se recorta: nadie necesita mandar un párrafo
    props[clave] = typeof valor === "string" ? valor.slice(0, 120) : valor;
  }

  return {
    at: new Date().toISOString(),
    event: nombre,
    // el usuario se toma de la sesión del servidor, nunca de lo que dice el
    // cliente: si no, cualquiera escribe eventos a nombre de otro
    ...(usuario ? { usuario } : {}),
    ...(Object.keys(props).length > 0 ? { props } : {}),
  };
}

export function createRegistroDeEventos(directorio: string) {
  mkdirSync(directorio, { recursive: true });

  return function registrarEventos(
    brutos: Record<string, unknown>[],
    usuario?: string,
  ): number {
    const limpios = brutos
      .slice(0, 50)
      .map((bruto) => limpiarEvento(bruto, usuario))
      .filter((evento): evento is EventoGuardado => evento !== null);
    if (limpios.length === 0) return 0;

    const archivo = join(directorio, `${new Date().toISOString().slice(0, 10)}.ndjson`);
    try {
      appendFileSync(archivo, `${limpios.map((e) => JSON.stringify(e)).join("\n")}\n`);
    } catch {
      // la analítica jamás rompe nada: si no se puede escribir, se pierde (R-009)
      return 0;
    }
    return limpios.length;
  };
}
