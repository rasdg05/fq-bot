import { describe, expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Store } from "../server/store.mts";
import { logroDe, tarjetaPng } from "../server/tarjeta.mts";
import { metaDeLogro } from "../server/compartir.mts";

/**
 * Tarjeta de resultado. Sólo datos propios y agregados (R-058): el nombre que
 * el usuario eligió, cuántas le atinó y su racha. Quién apostó qué no sale.
 */

function conApuestas(pagos: number[]) {
  const dir = mkdtempSync(join(tmpdir(), "marea-tarjeta-"));
  const store = new Store(dir);
  store.crearUsuario({
    id: "u1",
    usuario: "rasdg05",
    hash: "x",
    salt: "y",
    creado: new Date().toISOString(),
    puntos: 5000,
  });
  pagos.forEach((pago, i) => {
    const m = `m${i}`;
    store.asegurarPozo({ marketId: m, outcomes: { si: 100, no: 100 }, feeBps: 300 });
    const apuesta = store.apostar({
      usuarioId: "u1",
      marketId: m,
      side: "si",
      stake: 50,
      precio: 0.5,
    });
    store.pagarMercado(m, { [apuesta.id]: pago });
  });
  return { store, dir };
}

describe("Logro del usuario", () => {
  it("cuenta aciertos y racha sobre lo ya liquidado", () => {
    // pagó más de lo apostado = acertó. Las tres últimas seguidas
    const { store, dir } = conApuestas([120, 0, 130, 0, 140, 110, 125]);
    try {
      const logro = logroDe(store, "rasdg05")!;
      expect(logro.resueltos).toBe(7);
      expect(logro.aciertos).toBe(5);
      expect(logro.racha).toBe(3);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("una apuesta que no pagó más de lo puesto no es un acierto", () => {
    // devolver exactamente lo apostado es un mercado anulado, no un acierto
    const { store, dir } = conApuestas([50, 50]);
    try {
      const logro = logroDe(store, "rasdg05")!;
      expect(logro.aciertos).toBe(0);
      expect(logro.racha).toBe(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("quien no existe no tiene tarjeta", () => {
    const { store, dir } = conApuestas([]);
    try {
      expect(logroDe(store, "fantasma")).toBeNull();
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("no se cuentan las apuestas que siguen abiertas", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-abierta-"));
    try {
      const store = new Store(dir);
      store.crearUsuario({
        id: "u1", usuario: "rasdg05", hash: "x", salt: "y",
        creado: new Date().toISOString(), puntos: 1000,
      });
      store.asegurarPozo({ marketId: "m1", outcomes: { si: 100, no: 100 }, feeBps: 300 });
      store.apostar({ usuarioId: "u1", marketId: "m1", side: "si", stake: 50, precio: 0.5 });
      const logro = logroDe(store, "rasdg05")!;
      // apostada pero sin liquidar: no es ni acierto ni fallo todavía (R-029)
      expect(logro.resueltos).toBe(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("La imagen se genera sin navegador", () => {
  it("produce un PNG de 1200×630 que pesa poco", async () => {
    const png = await tarjetaPng(
      { usuario: "rasdg05", resueltos: 9, aciertos: 7, racha: 5 },
      process.cwd(),
    );
    // firma PNG
    expect(png.subarray(0, 8)).toEqual(
      Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    );
    // ancho y alto viven en el chunk IHDR, bytes 16..24
    expect(png.readUInt32BE(16)).toBe(1200);
    expect(png.readUInt32BE(20)).toBe(630);
    // una vista previa que tarda en cargar no se ve
    expect(png.length).toBeLessThan(400_000);
  });

  it("un nombre con caracteres raros no rompe el SVG", async () => {
    // el nombre lo elige el usuario: si entra sin escapar, rompe la imagen
    const png = await tarjetaPng(
      { usuario: '<script>&"x', resueltos: 3, aciertos: 2, racha: 1 },
      process.cwd(),
    );
    expect(png.length).toBeGreaterThan(1000);
  });

  it("sin mercados resueltos también hay tarjeta", async () => {
    const png = await tarjetaPng(
      { usuario: "nuevo", resueltos: 0, aciertos: 0, racha: 0 },
      process.cwd(),
    );
    expect(png.readUInt32BE(16)).toBe(1200);
  });
});

describe("Vista previa de la tarjeta", () => {
  const html = "<html><head><title>x</title></head><body></body></html>";

  it("apunta a la imagen del usuario, no a la de marca", () => {
    const meta = metaDeLogro(
      html,
      { usuario: "rasdg05", resueltos: 9, aciertos: 7, racha: 5 },
      "https://marea.test",
    );
    expect(meta).toContain("https://marea.test/tarjeta/rasdg05.png");
    expect(meta).toContain("summary_large_image");
    expect(meta).toContain("7 de 9");
  });

  it("no filtra a qué apostó ni cuánto (R-058)", () => {
    const meta = metaDeLogro(
      html,
      { usuario: "rasdg05", resueltos: 9, aciertos: 7, racha: 5 },
      "https://marea.test",
    );
    expect(meta).not.toMatch(/pts|puntos|apost|pozo/i);
  });

  it("escapa el nombre antes de meterlo al HTML", () => {
    const meta = metaDeLogro(
      html,
      { usuario: '<img src=x>', resueltos: 1, aciertos: 1, racha: 1 },
      "https://marea.test",
    );
    expect(meta).not.toContain("<img src=x>");
    expect(meta).toContain("&lt;img");
  });
});
