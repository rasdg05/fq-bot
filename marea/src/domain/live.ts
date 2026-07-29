import type { Market } from "./types";

/**
 * Qué se está definiendo **ahora**.
 *
 * El catálogo propio no emite `status: "live"` por su cuenta: lo emite el
 * oráculo de futbol cuando un partido está en juego, y eso pasa unas horas por
 * semana. Un contador que sólo cuente eso marca cero casi siempre, y una
 * pestaña que casi siempre está vacía deja de visitarse.
 *
 * Así que "vivo" son dos cosas distintas, dichas con nombres distintos:
 *
 *  - `en_juego`: el evento ya arrancó. Es literalmente en vivo.
 *  - `por_cerrar`: las apuestas cierran dentro de la ventana. No está en vivo,
 *    y por eso no se le llama así en pantalla — se le llama "se define pronto".
 *
 * Las dos suman al contador porque las dos responden a la misma pregunta del
 * usuario ("¿qué tengo que decidir hoy?"), pero nunca se presentan bajo la
 * misma etiqueta: llamar LIVE a un mercado que cierra en dos días sería
 * exactamente el tipo de exageración que R-011 prohíbe.
 */
export const VENTANA_VIVO_MS = 72 * 60 * 60 * 1000;

export type EstadoVivo = "en_juego" | "por_cerrar";

/** En qué sentido está vivo un mercado, o `null` si no lo está. */
export function estadoVivo(market: Market, ahora: number = Date.now()): EstadoVivo | null {
  if (market.status === "resolved") return null;
  if (market.status === "live") return "en_juego";
  if (!market.closesAt) return null;
  const falta = new Date(market.closesAt).getTime() - ahora;
  if (!Number.isFinite(falta) || falta <= 0) return null;
  return falta <= VENTANA_VIVO_MS ? "por_cerrar" : null;
}

export function esVivo(market: Market, ahora: number = Date.now()): boolean {
  return estadoVivo(market, ahora) !== null;
}

/**
 * Los vivos, con los que ya arrancaron primero y, dentro de cada grupo, lo que
 * cierra antes. El orden es la respuesta a "¿qué se me va a escapar?".
 */
export function mercadosVivos(markets: Market[], ahora: number = Date.now()): Market[] {
  const peso = (m: Market) => (estadoVivo(m, ahora) === "en_juego" ? 0 : 1);
  const cierre = (m: Market) =>
    m.closesAt ? new Date(m.closesAt).getTime() : Number.POSITIVE_INFINITY;
  return markets
    .filter((m) => esVivo(m, ahora))
    .sort((a, b) => peso(a) - peso(b) || cierre(a) - cierre(b));
}

/** Lo que va en el contador rojo de la pestaña. */
export function contarVivos(markets: Market[], ahora: number = Date.now()): number {
  let total = 0;
  for (const market of markets) if (esVivo(market, ahora)) total += 1;
  return total;
}
