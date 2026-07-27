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

  it("los dos temas declaran exactamente los mismos tokens (cero drift, R-012)", () => {
    const dark = Object.keys(tokensOf(':root[data-theme="dark"]')).sort();
    const light = Object.keys(tokensOf(':root[data-theme="light"]')).sort();
    expect(dark).toEqual(light);
  });
});
