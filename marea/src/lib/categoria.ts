import type { MarketCategory } from "@/domain/types";

/**
 * Marca visual de categoría.
 *
 * Objetivo: que se distingan **de reojo**, antes de leer la palabra. Un feed
 * donde todas las categorías se ven igual obliga a leer seis veces por
 * pantalla para saber de qué va cada mercado.
 *
 * Tres reglas que lo acotan:
 *
 *  - El color **nunca** es el único portador: la palabra sigue ahí al lado
 *    (R-005). Esto acelera el reconocimiento, no lo sustituye.
 *  - No se inventan tokens. Se reusan los seis acentos que ya existen y que ya
 *    pasaron contraste, así que `tokens.lock.json` no se mueve por esto.
 *  - Un color declarado como `var(--x)` no admite modificador de opacidad en
 *    Tailwind: la declaración se descarta y la superficie queda transparente
 *    (R-017). Los tintes se arman con `color-mix()` en estilo en línea, que sí
 *    resuelve la variable.
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
 * Cuánto acento lleva un relleno de categoría.
 *
 * El 14 % es el número que salió de medir, no de gustar: por encima del 18 %
 * el texto del propio acento deja de pasar 4.5:1 sobre el relleno en el tema
 * claro, y por debajo del 10 % el badge vuelve a leerse gris. Lo verifica
 * `tests/contrast.test.ts` sobre los seis acentos y los dos temas.
 */
export const TINTE_RELLENO = 14;
export const TINTE_BORDE = 34;

/**
 * `otros` no lleva relleno de acento, y no es un caso especial: es la única
 * categoría cuyo color es `--muted`, que no es un acento sino la ausencia de
 * uno. Medido, además, no aguanta el tinte —`--muted` sobre su propio relleno
 * al 14 % da 4.02:1 en oscuro, por debajo de AA— porque el token ya vive al
 * filo sobre `--panel`. Las dos razones apuntan al mismo sitio: la categoría
 * que significa "sin señal clara para clasificar" no puede gritar como las que
 * sí dicen algo.
 */
export function tieneAcento(category: MarketCategory): boolean {
  return COLOR_CATEGORIA[category] !== "var(--muted)";
}

/** El estilo en línea de un relleno de acento, listo para cualquier token. */
export function rellenoAcento(color: string) {
  return {
    color,
    backgroundColor: `color-mix(in srgb, ${color} ${TINTE_RELLENO}%, var(--panel))`,
    borderColor: `color-mix(in srgb, ${color} ${TINTE_BORDE}%, transparent)`,
  };
}
