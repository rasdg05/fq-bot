import type { Market } from "./types";
import { hasEdge } from "./edge";
import { totalPool } from "./parimutuel";

/**
 * Qué mercados van al carrusel de destacados.
 *
 * ## El defecto que corrige
 *
 * El carrusel llevaba «todo lo caliente», y caliente era `pozo >= umbral`.
 * Todo mercado nace con su semilla por encima del umbral, así que **todos**
 * eran calientes: con el catálogo lleno, las cincuenta tarjetas iban a una
 * fila horizontal y debajo no quedaba ninguna sección. Con pocos mercados no
 * se notaba; con veinte ligas, el feed se quedaba vacío debajo del carrusel.
 *
 * ## La regla
 *
 * Un carrusel de destacados es una selección, no un listado (el patrón de
 * Kalshi y Polymarket): pocos, variados y lo más vivo arriba.
 *
 *  - **Tope** de `max` (5): más de eso ya no se ve que es una selección.
 *  - **Variedad**: como mucho `porCategoria` (2) de una misma categoría, y una
 *    sola vela en vivo por activo — Bitcoin a 5 y a 15 minutos son la misma
 *    noticia contada dos veces.
 *  - **Orden** por un puntaje determinista: lo que está pasando ahora, lo que
 *    tiene gente adentro, lo que tiene Edge, lo que cierra pronto y el pozo.
 *    Determinista para que dos personas vean lo mismo y una prueba lo fije.
 *
 * Lo que no entra al carrusel sigue en su sección: nada se pierde (la prueba
 * del carrusel lo exige) y nada sale dos veces.
 */

export interface OpcionesDestacados {
  max?: number;
  porCategoria?: number;
  /** Reloj, para «cierra pronto». Por parámetro: sin relojes de pared. */
  ahora: number;
  /**
   * Respuestas máximas de un destacado. El carrusel pasa 2: es una fila de
   * una sola forma. Una tarjeta de quiniela (tres filas, 176 px) junto a una
   * de dos lados (121 px) deja 55 px de aire bajo la corta, porque la pista
   * mide lo que la más alta. Las de tres respuestas siguen en su sección.
   */
  maxRespuestas?: number;
}

const DIA_MS = 86_400_000;

/** El puntaje de un mercado para el carrusel. Mayor es mejor. */
export function puntajeDestacado(market: Market, ahora: number): number {
  let puntaje = 0;
  if (market.status === "live" || market.live) puntaje += 4;
  // gente real apostando es la mejor señal de interés: el pozo sembrado no lo
  // es, porque lo pone la casa
  puntaje += Math.log2(1 + (market.participantes ?? 0)) * 1.5;
  if (hasEdge(market)) puntaje += 2;
  if (market.closesAt) {
    const falta = Date.parse(market.closesAt) - ahora;
    if (falta > 0 && falta < DIA_MS) puntaje += 1.5;
  }
  if (market.pool) puntaje += Math.log10(1 + totalPool(market.pool)) * 0.5;
  return puntaje;
}

function abierto(market: Market, ahora: number): boolean {
  // lo que ya no acepta apuestas no se destaca: invitar a entrar donde no se puede
  if (market.status === "resolved" || market.status === "settling") return false;
  if (!market.closesAt) return true;
  return Date.parse(market.closesAt) > ahora;
}

export function elegirDestacados(markets: readonly Market[], opciones: OpcionesDestacados): Market[] {
  const max = opciones.max ?? 5;
  const porCategoria = opciones.porCategoria ?? 2;
  const candidatos = markets
    .filter((market) => abierto(market, opciones.ahora))
    .filter(
      (market) =>
        opciones.maxRespuestas === undefined ||
        (market.outcomes?.length ?? 2) <= opciones.maxRespuestas,
    )
    .map((market, indice) => ({ market, indice, puntaje: puntajeDestacado(market, opciones.ahora) }))
    // desempate por el orden de llegada: estable y sin azar
    .sort((a, b) => b.puntaje - a.puntaje || a.indice - b.indice);

  const elegidos: Market[] = [];
  const porCat = new Map<string, number>();
  const activosVivos = new Set<string>();
  for (const { market } of candidatos) {
    if (elegidos.length >= max) break;
    const enCategoria = porCat.get(market.category) ?? 0;
    if (enCategoria >= porCategoria) continue;
    const activo = market.live ? (market.activo ?? market.id) : undefined;
    if (activo && activosVivos.has(activo)) continue;
    elegidos.push(market);
    porCat.set(market.category, enCategoria + 1);
    if (activo) activosVivos.add(activo);
  }
  return elegidos;
}
