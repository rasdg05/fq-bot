import {
  Bitcoin,
  Circle,
  CloudSun,
  Film,
  Landmark,
  Trophy,
  Vote,
  Wheat,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { MarketCategory } from "@/domain/types";

/**
 * Marca visual de categoría.
 *
 * Objetivo: que se distingan **de reojo**, antes de leer la palabra. Un feed
 * donde todas las categorías se ven igual obliga a leer seis veces por
 * pantalla para saber de qué va cada mercado.
 *
 * Dos reglas que lo acotan:
 *
 *  - El color **nunca** es el único portador: la palabra sigue ahí al lado
 *    (R-005). Esto acelera el reconocimiento, no lo sustituye.
 *  - Los colores viven en `tokens.css` y en `tokens.lock.json`, como todo lo
 *    demás (V1, V24). Aquí sólo se nombran.
 */

/**
 * Antes esto reusaba los seis acentos del sistema —teal, ámbar, rojo, verde,
 * naranja, gris— y era la razón de que el feed se viera "todo teal plano":
 * cultura (naranja) y deportes (rojo) casi no se separaban, y no había un solo
 * azul ni violeta en toda la app. Ahora cada categoría tiene tono propio, y
 * ninguno baja de 3:1 contra las tres superficies en los dos temas.
 */
/**
 * Las que salen como pestaña, en orden.
 *
 * Vive aquí y no en cada pantalla porque antes estaba duplicada en `HomeScreen`
 * y en `SearchScreen`, y dos listas que tienen que decir lo mismo terminan
 * diciendo cosas distintas. `materias-primas` y `clima` **no** están: existen en
 * el tipo, con su color y su glifo, pero todavía no tienen catálogo, y una
 * pestaña que filtra a cero mercados es un callejón sin salida (R-006).
 */
export const CATEGORIAS_VISIBLES: MarketCategory[] = [
  "cripto",
  "economia",
  "deportes",
  "politica",
  "cultura",
  "otros",
];

export const COLOR_CATEGORIA: Record<MarketCategory, string> = {
  // cripto se queda con el teal de la marca: es la categoría que **es** Marea
  cripto: "var(--cat-cripto)",
  // índigo institucional, que es como se ve un dato de banco central
  economia: "var(--cat-economia)",
  // verde de cancha
  deportes: "var(--cat-deportes)",
  // violeta a propósito: ni el rojo ni el azul de ningún partido
  politica: "var(--cat-politica)",
  cultura: "var(--cat-cultura)",
  "materias-primas": "var(--cat-materias-primas)",
  clima: "var(--cat-clima)",
  // gris: "otros" no es un tema, es la ausencia de uno. Que no compita
  otros: "var(--cat-otros)",
};

/**
 * Forma, además del color: quien no distingue rojo de verde sigue viendo dos
 * cosas distintas. Es el mismo principio de R-005 aplicado a la marca.
 */
export const FORMA_CATEGORIA: Record<MarketCategory, string> = {
  cripto: "rounded-full",
  economia: "rounded-[2px]",
  deportes: "rounded-full",
  politica: "rounded-[2px] rotate-45",
  cultura: "rounded-full",
  "materias-primas": "rounded-[2px]",
  clima: "rounded-full",
  otros: "rounded-[2px]",
};

/**
 * El glifo de cada categoría, para el azulejo de la card.
 *
 * Es la tercera pista, después del color y la forma: a 16 px un icono no se
 * lee en detalle, pero su silueta sí se reconoce, y eso basta para saber de qué
 * va la card antes de leer una palabra. La palabra sigue al lado — el icono
 * nunca es el único portador (R-005).
 */
export const ICONO_CATEGORIA: Record<MarketCategory, LucideIcon> = {
  cripto: Bitcoin,
  economia: Landmark,
  deportes: Trophy,
  politica: Vote,
  cultura: Film,
  "materias-primas": Wheat,
  clima: CloudSun,
  otros: Circle,
};
