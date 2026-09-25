/**
 * Las ligas de las que Marea abre mercados solos.
 *
 * Todas se leen del mismo marcador público de ESPN (sin llave ni registro), así
 * que cada partido tiene camino de liquidación desde que nace (L1). Una liga que
 * esta semana no tiene partidos no rompe nada: aporta cero mercados.
 *
 * `empate` decide la forma del mercado. Donde el empate es un resultado normal
 * (el futbol) la pregunta natural es la de la quiniela —gana, empata o pierde—;
 * donde no existe o es rarísimo, basta con quién gana.
 */

export type Deporte = "soccer" | "football" | "baseball" | "basketball" | "hockey";

export interface Liga {
  /** Identificador de ESPN, tal como va en la URL. */
  id: string;
  deporte: Deporte;
  nombre: string;
  /** Lo que enseña el badge de la card: país o región. */
  pais: string;
  /** Prefijo de los ids de mercado. */
  prefijo: string;
  empate: boolean;
  /** Cuántos días hacia adelante se abren partidos. */
  dias: number;
  /** Tope de partidos abiertos a la vez por liga: el feed no es un calendario. */
  maximo: number;
}

export const LIGAS = [
  { id: "mex.1", deporte: "soccer", nombre: "Liga MX", pais: "MX", prefijo: "mx", empate: true, dias: 7, maximo: 12 },
  { id: "mex.2", deporte: "soccer", nombre: "Liga de Expansión MX", pais: "MX", prefijo: "mx2", empate: true, dias: 4, maximo: 6 },
  { id: "usa.1", deporte: "soccer", nombre: "MLS", pais: "US", prefijo: "mls", empate: true, dias: 4, maximo: 8 },
  { id: "col.1", deporte: "soccer", nombre: "Liga colombiana", pais: "CO", prefijo: "col", empate: true, dias: 4, maximo: 6 },
  { id: "arg.1", deporte: "soccer", nombre: "Liga argentina", pais: "AR", prefijo: "arg", empate: true, dias: 4, maximo: 6 },
  { id: "bra.1", deporte: "soccer", nombre: "Brasileirão", pais: "BR", prefijo: "bra", empate: true, dias: 4, maximo: 6 },
  { id: "per.1", deporte: "soccer", nombre: "Liga 1 de Perú", pais: "PE", prefijo: "per", empate: true, dias: 4, maximo: 4 },
  { id: "chi.1", deporte: "soccer", nombre: "Liga chilena", pais: "CL", prefijo: "chi", empate: true, dias: 4, maximo: 4 },
  { id: "uru.1", deporte: "soccer", nombre: "Liga uruguaya", pais: "UY", prefijo: "uru", empate: true, dias: 4, maximo: 4 },
  { id: "conmebol.libertadores", deporte: "soccer", nombre: "Copa Libertadores", pais: "LATAM", prefijo: "lib", empate: true, dias: 7, maximo: 6 },
  { id: "eng.1", deporte: "soccer", nombre: "Premier League", pais: "GB", prefijo: "epl", empate: true, dias: 4, maximo: 6 },
  { id: "esp.1", deporte: "soccer", nombre: "LaLiga", pais: "ES", prefijo: "esp", empate: true, dias: 4, maximo: 6 },
  { id: "ita.1", deporte: "soccer", nombre: "Serie A", pais: "IT", prefijo: "ita", empate: true, dias: 4, maximo: 4 },
  { id: "ger.1", deporte: "soccer", nombre: "Bundesliga", pais: "DE", prefijo: "ger", empate: true, dias: 4, maximo: 4 },
  { id: "fra.1", deporte: "soccer", nombre: "Ligue 1", pais: "FR", prefijo: "fra", empate: true, dias: 4, maximo: 4 },
  { id: "uefa.champions", deporte: "soccer", nombre: "Champions League", pais: "EU", prefijo: "ucl", empate: true, dias: 7, maximo: 8 },
  { id: "nfl", deporte: "football", nombre: "NFL", pais: "US", prefijo: "nfl", empate: false, dias: 7, maximo: 8 },
  { id: "mlb", deporte: "baseball", nombre: "MLB", pais: "US", prefijo: "mlb", empate: false, dias: 2, maximo: 6 },
  { id: "nba", deporte: "basketball", nombre: "NBA", pais: "US", prefijo: "nba", empate: false, dias: 2, maximo: 6 },
  { id: "wnba", deporte: "basketball", nombre: "WNBA", pais: "US", prefijo: "wnba", empate: false, dias: 3, maximo: 4 },
  { id: "nhl", deporte: "hockey", nombre: "NHL", pais: "US", prefijo: "nhl", empate: false, dias: 2, maximo: 4 },
] as const satisfies readonly Liga[];

export type LigaDef = (typeof LIGAS)[number];
export type LigaId = LigaDef["id"];

const POR_ID = new Map<string, LigaDef>(LIGAS.map((liga) => [liga.id, liga]));

/** La liga de un id; `mex.1` si el id no es conocido (los mercados viejos). */
export function ligaDe(id: string): LigaDef {
  return POR_ID.get(id) ?? LIGAS[0];
}

const ESPN = "https://site.api.espn.com/apis/site/v2/sports";

/** Marcador de una jornada. `fecha` es `YYYY-MM-DD`, en el calendario de ESPN. */
export function urlJornadaEspn(liga: string, fecha: string): string {
  const { deporte } = ligaDe(liga);
  return `${ESPN}/${deporte}/${liga}/scoreboard?dates=${fecha.replace(/-/g, "")}`;
}
