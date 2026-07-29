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

/**
 * `color-mix(in srgb, a p%, b)` sobre dos colores opacos es la interpolación
 * lineal de sus canales sRGB. Se replica aquí para poder medir el contraste de
 * un relleno que el navegador calcula en tiempo de pintado.
 */
function mix(a: string, b: string, percent: number): string {
  const canales = (hex: string) => {
    const clean = hex.replace("#", "");
    return [0, 2, 4].map((i) => parseInt(clean.slice(i, i + 2), 16));
  };
  const [ra, ga, ba] = canales(a);
  const [rb, gb, bb] = canales(b);
  const p = percent / 100;
  const round = (x: number, y: number) =>
    Math.round(x * p + y * (1 - p))
      .toString(16)
      .padStart(2, "0");
  return `#${round(ra, rb)}${round(ga, gb)}${round(ba, bb)}`;
}

/** El tinte del azulejo de categoría (ver `ui/categoria-icono.tsx`). */
const TINTE_AZULEJO = 20;

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

  it.each(THEMES)("el texto sobre el relleno teal también pasa en %s", (selector) => {
    const t = tokensOf(`:root[${selector}]`);
    expect(ratio(t["teal-ink"], t.teal)).toBeGreaterThanOrEqual(4.5);
  });

  /**
   * El azulejo de categoría se pinta con un relleno hecho de su propio color
   * —`color-mix(in srgb, --acento 20%, transparent)` sobre `--panel`— y lleva
   * el glifo en el acento puro encima. Es el caso más apretado del sistema:
   * mezclar el acento dentro del fondo acerca los dos.
   *
   * Sin esta prueba el tinte es un número elegido a ojo, y se puede subir al
   * 40 % en un rediseño sin que nadie se entere hasta que el glifo de
   * `Deportes` deje de verse. El umbral es 3:1 y no 4.5:1 a propósito: es un
   * glifo, no texto, y WCAG pide 3:1 para componentes gráficos (1.4.11).
   */
  it.each(THEMES)("el glifo de acento pasa sobre su propio azulejo en %s", (selector) => {
    const t = tokensOf(`:root[${selector}]`);
    for (const acento of ["teal", "hot", "live", "up", "dn", "muted"]) {
      const relleno = mix(t[acento], t.panel, TINTE_AZULEJO);
      const value = ratio(t[acento], relleno);
      expect(
        value,
        `--${acento} sobre su azulejo al ${TINTE_AZULEJO}% en ${selector} = ${value.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(3);
    }
  });

  it("los dos temas declaran exactamente los mismos tokens (cero drift, R-012)", () => {
    const dark = Object.keys(tokensOf(':root[data-theme="dark"]')).sort();
    const light = Object.keys(tokensOf(':root[data-theme="light"]')).sort();
    expect(dark).toEqual(light);
  });
});
