import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { Juez, clienteAnthropic, requiereJuicio, type ClienteJuez } from "../server/juez.mts";
import { Store } from "../server/store.mts";
import { reponer } from "../server/reposicion.mts";
import { OWN_MARKETS, type OwnMarketSeed } from "@/adapters/ownMarkets/catalog";
import { dueloSeed } from "@/adapters/ownMarkets/tendencias";
import { sismoSeed } from "@/adapters/ownMarkets/sismos";
import { verificarCadena } from "@/domain/bitacora";

/**
 * El juez (Claude) con un cliente falso: lo que se prueba es la política, no
 * el modelo. Que sólo vete con confianza alta, que una duda o una caída no
 * frenen nada, que no gaste más llamadas de las que tiene, y que todo quede en
 * la bitácora con el modelo que decidió.
 */

const AHORA = Date.parse("2026-10-01T12:00:00Z");
const duelo = dueloSeed({
  numero: 1,
  fecha: "2026-10-02",
  a: { article: "Diego_Luna", views: 26185, rank: 9 },
  b: { article: "Jorge_Jesus", views: 11486, rank: 15 },
  diaReferencia: "2026-09-30",
});
const sismo = sismoSeed(Date.parse("2026-10-05T06:00:00Z"));

function cliente(respuestas: unknown[]): ClienteJuez & { juzgar: ReturnType<typeof vi.fn> } {
  const cola = [...respuestas];
  return {
    modelo: "claude-opus-5-5",
    juzgar: vi.fn(async () => {
      const r = cola.shift();
      if (r instanceof Error) throw r;
      return { datos: r ?? null, entrada: 100, salida: 20, rechazo: false };
    }),
  } as never;
}

describe("Juez — sólo juzga lo que una regla no alcanza", () => {
  it("lo que viene de plantilla no pasa por el modelo; lo que viene de afuera sí", () => {
    expect(requiereJuicio(sismo)).toBe(false);
    expect(requiereJuicio(duelo)).toBe(true);
  });

  it("sin llave de API se apaga, y todo se publica por las reglas", async () => {
    expect(clienteAnthropic({})).toBeUndefined();
    const juez = new Juez(undefined);
    juez.nuevoCiclo();
    expect(await juez.revisarTexto(duelo)).toMatchObject({ decision: "publicar", autor: "reglas" });
    expect(juez.estado()).toMatchObject({ activo: false, llamadas: 0 });
  });
});

describe("Juez — cuándo veta", () => {
  it("«no publicable» con confianza alta veta, y firma con el modelo", async () => {
    const juez = new Juez(cliente([{ publicable: false, problema: "sensible", confianza: "alta", motivo: "Es sobre una muerte." }]));
    juez.nuevoCiclo();
    expect(await juez.revisarTexto(duelo)).toEqual({
      decision: "vetar",
      motivo: "sensible: Es sobre una muerte.",
      autor: "claude:claude-opus-5-5",
    });
  });

  it("una duda (confianza media) no frena nada", async () => {
    const juez = new Juez(cliente([{ publicable: false, problema: "ambiguo", confianza: "media", motivo: "Quizá." }]));
    juez.nuevoCiclo();
    expect((await juez.revisarTexto(duelo)).decision).toBe("publicar");
  });

  it("si el modelo se cae, deciden las reglas y el error se cuenta", async () => {
    const juez = new Juez(cliente([new Error("529 overloaded")]));
    juez.nuevoCiclo();
    expect(await juez.revisarTexto(duelo)).toMatchObject({ decision: "publicar", autor: "reglas" });
    expect(juez.estado()).toMatchObject({ errores: 1, ultimoError: "529 overloaded" });
  });

  it("con las llamadas del ciclo agotadas, espera al siguiente; y no juzga dos veces lo mismo", async () => {
    const c = cliente([{ publicable: true, problema: "ninguno", confianza: "alta", motivo: "Clara." }]);
    const juez = new Juez(c, 1);
    juez.nuevoCiclo();
    await juez.revisarTexto(duelo);
    const otro = { ...duelo, id: "wiki-otro" };
    expect((await juez.revisarTexto(otro)).decision).toBe("diferir");
    // el ya juzgado sale de memoria, sin gastar
    await juez.revisarTexto(duelo);
    expect(c.juzgar).toHaveBeenCalledTimes(1);
  });
});

describe("Juez — resoluciones", () => {
  it("señala al revisor sólo con confianza alta, una vez por resultado, y nunca mira velas", async () => {
    const c = cliente([
      { sostiene: false, confianza: "alta", motivo: "La evidencia dice lo contrario." },
      { sostiene: false, confianza: "baja", motivo: "No estoy seguro." },
    ]);
    const juez = new Juez(c);
    juez.nuevoCiclo();
    const en = (id: string) => ({ marketId: id, phase: "en_disputa" as const, outcome: "a", evidence: "Diego Luna: 10 visitas" });
    await juez.revisarResoluciones([
      { seed: duelo, estado: en(duelo.id) },
      { seed: { ...duelo, id: "dudoso" }, estado: en("dudoso") },
      { seed: { ...duelo, id: "vela", rule: { kind: "vela", par: "BTC/USD", intervalo: 5, inicio: 0, strike: 1 } } as OwnMarketSeed, estado: en("vela") },
    ]);
    expect(Object.keys(juez.juiciosDeResolucion())).toEqual([duelo.id]);
    expect(c.juzgar).toHaveBeenCalledTimes(2);
    await juez.revisarResoluciones([{ seed: duelo, estado: en(duelo.id) }]);
    expect(c.juzgar).toHaveBeenCalledTimes(2);
  });
});

describe("Director — la bitácora de la reposición", () => {
  it("publica con su prior, veta con la firma del modelo, y no repite omisiones", async () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-director-"));
    try {
      const store = new Store(dir);
      const abiertos = Array.from({ length: 70 }, (_, i) => ({
        ...OWN_MARKETS[0],
        id: `abierto-${i}`,
        closesAt: new Date(AHORA + 30 * 86_400_000).toISOString(),
      }));
      const vetador = {
        revisarTexto: async (seed: OwnMarketSeed) =>
          seed.id === duelo.id
            ? { decision: "vetar" as const, motivo: "sensible: prueba", autor: "claude:claude-opus-5-5" as const }
            : { decision: "publicar" as const, motivo: "ok", autor: "reglas" as const },
      };
      const curados = async () => ({ seeds: [duelo, sismo], errores: [] });
      const r = await reponer(store, abiertos, AHORA, { env: {}, curados, juez: vetador });
      expect(r.creados).toEqual([sismo.id]);
      expect(r.vetados.map((v) => v.id)).toEqual([duelo.id]);

      const entradas = store.bitacora();
      const publicar = entradas.find((e) => e.tipo === "publicar")!;
      expect(publicar.motivo).toMatch(/nace en Al menos uno 34 % · Ninguno 66 %|nace en Ninguno 66 % · Al menos uno 34 %/);
      expect(entradas.find((e) => e.tipo === "vetar")).toMatchObject({ autor: "claude:claude-opus-5-5", regla: "R-081" });

      // otra vuelta: el vetado se vuelve a evaluar, pero su veto no se anota dos veces
      const n = entradas.length;
      await reponer(store, abiertos, AHORA + 60_000, { env: {}, curados, juez: vetador });
      expect(store.bitacora().length).toBe(n);
      expect(verificarCadena(store.bitacora()).ok).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
