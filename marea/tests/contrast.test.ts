import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const css = readFileSync(resolve(process.cwd(), "src/styles/tokens.css"), "utf8");

/** Extrae el bloque de tokens de un selector concreto de tokens.css. */
function tokensOf(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  if (start === -1) throw new Error(`selector ausente: ${selector}`);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  const body = css.slice(open + 1, close);
  const out: Record<string, string> = {};
  for (const line of body.split("\n")) {
    const match = line.match(/--([a-z0-9-]+):\s*([^;]+);/i);
    if (match) out[match[1]] = match[2].trim();
  }
  return out;
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const clean = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(clean.slice(i, i + 2), 16));
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function ratio(fg: string, bg: string): number {
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

const THEMES = ['data-theme="dark"', 'data-theme="light"'];

describe("Accesibilidad de color", () => {
  it.each(THEMES)("contraste >= 4.5:1 sobre el fondo en %s", (selector) => {
    const t = tokensOf(`:root[${selector}]`);
    const pairs: [string, string][] = [
      ["text", "bg"],
      ["text2", "bg"],
      ["muted", "bg"],
      ["teal", "bg"],
      ["up", "bg"],
      ["dn", "bg"],
      ["hot", "bg"],
      ["live", "bg"],
      ["text", "panel"],
      ["text2", "panel"],
      ["muted", "panel"],
      // `panel2` faltaba entero, y es la superficie **más clara**: el texto que
      // menos contrasta vivía justo ahí (la zona de decisión del detalle y los
      // estados de error). Sin estos pares, la prueba daba verde sobre el caso
      // peor sin llegar a mirarlo
      ["text", "panel2"],
      ["text2", "panel2"],
      ["muted", "panel2"],
      ["dn", "panel2"],
      // y el bloque teal, donde viven las dos cifras protagonistas
      ["text", "teal-soft"],
      ["text2", "teal-soft"],
      ["teal", "teal-soft"],
    ];
    for (const [fg, bg] of pairs) {
      const value = ratio(t[fg], t[bg]);
      expect(
        value,
        `--${fg} sobre --${bg} en ${selector} = ${value.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  /**
   * El texto dominante —la pregunta del mercado y los porcentajes de las
   * pills— a 8:1, muy por encima del 4.5:1 de AA. Es el nodo que se lee a un
   * brazo de distancia, con sol de frente y el teléfono al 30 % de brillo, y
   * es donde un contraste "suficiente" se nota poco y cuesta caro.
   *
   * `--text2` y `--muted` **no** entran aquí a propósito: son etiquetas y
   * meta, y subirlas a 8:1 aplanaría la jerarquía —todo igual de fuerte es
   * todo igual de plano— además de mover tokens que el rediseño ya afinó.
   * Se quedan en el 4.5:1 que ya verifica el caso de arriba.
   */
  it.each(THEMES)("el texto dominante va a 8:1 o más en %s", (selector) => {
    const t = tokensOf(`:root[${selector}]`);
    for (const bg of ["bg", "panel", "panel2", "teal-soft"]) {
      const value = ratio(t.text, t[bg]);
      expect(
        value,
        `--text sobre --${bg} en ${selector} = ${value.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(8);
    }
  });

  /**
   * El color de categoría es un componente gráfico, no texto: el umbral que le
   * toca es 3:1. Se comprueba contra las **tres** superficies porque el
   * azulejo vive en la card (`--panel`), la raya de la pestaña sobre el fondo
   * (`--bg`), y el anillo de la pill sobre el relleno claro.
   *
   * Que el color cumpla no lo vuelve el portador del significado: al lado va
   * siempre la palabra, y el glifo y la forma cambian con él (R-005).
   */
  it.each(THEMES)("cada color de categoría llega a 3:1 en %s", (selector) => {
    const t = tokensOf(`:root[${selector}]`);
    const categorias = Object.keys(t).filter((name) => name.startsWith("cat-"));
    // si alguien añade una categoría y se olvida del token, esto lo caza antes
    // que el ojo: sin esta línea la prueba pasaría comprobando un conjunto vacío
    expect(categorias.length).toBe(8);
    for (const name of categorias) {
      for (const bg of ["bg", "panel", "panel2"]) {
        const value = ratio(t[name], t[bg]);
        expect(
          value,
          `--${name} sobre --${bg} en ${selector} = ${value.toFixed(2)}:1`,
        ).toBeGreaterThanOrEqual(3);
      }
    }
  });

  /** Dos categorías que se ven igual no son dos categorías. */
  it.each(THEMES)("ningún par de categorías comparte color en %s", (selector) => {
    const t = tokensOf(`:root[${selector}]`);
    const valores = Object.entries(t)
      .filter(([name]) => name.startsWith("cat-"))
      .map(([, value]) => value);
    expect(new Set(valores).size).toBe(valores.length);
  });

  it.each(THEMES)("el texto sobre el relleno teal también pasa en %s", (selector) => {
    const t = tokensOf(`:root[${selector}]`);
    expect(ratio(t["teal-ink"], t.teal)).toBeGreaterThanOrEqual(4.5);
  });

  it("los dos temas declaran exactamente los mismos tokens (cero drift, R-012)", () => {
    const dark = Object.keys(tokensOf(':root[data-theme="dark"]')).sort();
    const light = Object.keys(tokensOf(':root[data-theme="light"]')).sort();
    expect(dark).toEqual(light);
  });
});
