import { Bitcoin, Circle, Film, Landmark, Trophy, Vote } from "lucide-react";
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
 *  - No se inventan tokens. Se reusan los seis acentos que ya existen y que ya
 *    pasaron contraste, así que `tokens.lock.json` no se mueve por esto.
 */
export const COLOR_CATEGORIA: Record<MarketCategory, string> = {
  // cripto es lo más "mercado": el teal de la marca
  cripto: "var(--teal)",
  // economía es el dato institucional, el mismo ámbar de lo que está caliente
  economia: "var(--hot)",
  // deportes es lo que se juega en vivo
  deportes: "var(--live)",
  // política sube o baja como un resultado
  politica: "var(--up)",
  cultura: "var(--dn)",
  otros: "var(--muted)",
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
  otros: Circle,
};
