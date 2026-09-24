import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Store } from "../server/store.mts";
import { MINIMO_ABIERTOS, reponer } from "../server/reposicion.mts";
import { OWN_MARKETS } from "@/adapters/ownMarkets/catalog";

/**
 * La reposición dentro del servidor.
 *
 * El catálogo se reponía con `npm run roll`, disparado por un cron instalado en
 * la máquina de alguien. Nadie lo corrió desde principios de agosto y el 10 de
 * septiembre la app tenía **cuatro** mercados duraderos: la pantalla que ve
 * quien llega estaba prácticamente vacía.
 *
 * *Un proceso que depende de que alguien se acuerde no existe* (AGENTE §2).
 */

const AHORA = Date.parse("2026-09-10T12:00:00Z");
const SPOT = () => ({ "BTC/USD": 68_000, "ETH/USD": 3_400 });

function conStore() {
  const dir = mkdtempSync(join(tmpdir(), "marea-reponer-"));
  return { dir, store: new Store(dir) };
}

describe("Reposición — el feed deja de depender de una laptop", () => {
  it("con el feed vacío, crea mercados y los guarda en disco", async () => {
    const { dir, store } = conStore();
    try {
      const r = await reponer(store, [], AHORA, { spot: SPOT, env: {} });
      expect(r.abiertosAntes).toBe(0);
      expect(r.creados.length).toBeGreaterThan(0);
      expect(r.errores).toEqual([]);
      // y quedan guardados: sobreviven al reinicio del proceso
      expect(new Store(dir).seedsGeneradas().map((s) => s.id).sort()).toEqual(r.creados.sort());
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("es idempotente: cien vueltas en la misma ventana no crean cien mercados", async () => {
    const { dir, store } = conStore();
    try {
      const primera = await reponer(store, [], AHORA, { spot: SPOT, env: {} });
      const segunda = await reponer(store, [], AHORA, { spot: SPOT, env: {} });
      const tercera = await reponer(store, [], AHORA + 60_000, { spot: SPOT, env: {} });
      expect(primera.creados.length).toBeGreaterThan(0);
      expect(segunda.creados).toEqual([]);
      expect(tercera.creados).toEqual([]);
      expect(store.seedsGeneradas().length).toBe(primera.creados.length);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("con el feed sano no crea por crear", async () => {
    const { dir, store } = conStore();
    try {
      // un catálogo con mercados abiertos de sobra
      const abiertos = Array.from({ length: MINIMO_ABIERTOS + 2 }, (_, i) => ({
        ...OWN_MARKETS[0],
        id: `abierto-${i}`,
        closesAt: new Date(AHORA + 30 * 86_400_000).toISOString(),
      }));
      const r = await reponer(store, abiertos, AHORA, { spot: SPOT, env: {} });
      expect(r.abiertosAntes).toBe(abiertos.length);
      expect(r.creados).toEqual([]);
      expect(store.seedsGeneradas()).toEqual([]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("sin precio no inventa un umbral: se genera un mercado menos, no uno falso", async () => {
    const { dir, store } = conStore();
    try {
      const r = await reponer(store, [], AHORA, { spot: () => ({}), env: {} });
      expect(r.creados).toEqual([]);
      expect(r.errores).toEqual([]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("si ESPN no contesta, los de cripto se crean igual: el feed queda corto, no vacío", async () => {
    const { dir, store } = conStore();
    try {
      const r = await reponer(store, [], AHORA, {
        spot: SPOT,
        partidos: async () => {
          throw new Error("ESPN respondió 403");
        },
        env: {},
      });
      expect(r.creados.length).toBeGreaterThan(0);
      expect(r.errores.join(" ")).toContain("403");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("pasa por el freno de presupuesto antes de escribir nada (L9)", async () => {
    const { dir, store } = conStore();
    try {
      // los mercados nacen en modo "apuesta", así que su subsidio es cero y el
      // tope por defecto no los frena. Con un tope de exposición y mercados
      // opacos vivos, sí se para — y lo dice
      const r = await reponer(store, [{ ...OWN_MARKETS[0], id: "opaco", pool: { outcomes: { si: 1, no: 1 }, feeBps: 300 } }], AHORA, {
        spot: SPOT,
        topes: { porMercado: 0, abierto: 0, exposicion: 10_000 },
      });
      expect(r.creados).toEqual([]);
      expect(r.frenados.length).toBeGreaterThan(0);
      expect(r.frenados[0].motivo).toContain("sin semilla declarada");
      expect(store.seedsGeneradas()).toEqual([]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("un mercado que no se puede publicar no se guarda, y lo dice", async () => {
    const { dir, store } = conStore();
    try {
      const r = await reponer(store, [], AHORA, { spot: SPOT, env: {} });
      // todos los creados pasaron `validateSeed`: fuente pública, criterio
      // inequívoco y ventana de disputa (R-025)
      for (const seed of store.seedsGeneradas()) {
        expect(seed.resolution.sourceUrl).toMatch(/^https:\/\//);
        expect(seed.resolution.criterion.length).toBeGreaterThan(20);
      }
      expect(r.errores).toEqual([]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

/**
 * Lo que la suite no vio y sí vio el proceso real.
 */
describe("Reposición — las velas no cuentan como feed lleno", () => {
  const vela = (i: number) => ({
    ...OWN_MARKETS[0],
    id: `btc-5m-2026091012${i}0`,
    closesAt: new Date(AHORA + 5 * 60_000).toISOString(),
    rule: {
      kind: "vela" as const,
      par: "BTC/USD" as const,
      intervalo: 5 as const,
      inicio: AHORA,
      strike: 68_000,
    },
  });

  it("cuatro velas abiertas y tres mercados duraderos NO son un feed sano", async () => {
    /**
     * Es exactamente el estado en el que estaba producción, y con el que la
     * primera versión de esto decidió no reponer nada: 4 + 3 = 7, por encima
     * del mínimo de 6, con la pantalla igual de vacía.
     */
    const { dir, store } = conStore();
    try {
      const catalogo = [
        ...[0, 1, 2, 3].map(vela),
        ...[0, 1, 2].map((i) => ({
          ...OWN_MARKETS[0],
          id: `duradero-${i}`,
          closesAt: new Date(AHORA + 20 * 86_400_000).toISOString(),
        })),
      ];
      const r = await reponer(store, catalogo, AHORA, { spot: SPOT, env: {} });
      expect(r.abiertosAntes).toBe(3); // los duraderos, no los siete
      expect(r.creados.length).toBeGreaterThan(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
