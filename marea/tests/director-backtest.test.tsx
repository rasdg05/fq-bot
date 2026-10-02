import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { backtest, brier, calificar, N_MINIMO, type Muestra } from "@/domain/calibracion";
import { sismoSeed } from "@/adapters/ownMarkets/sismos";
import { initialState } from "@/domain/settlement";
import type { OwnMarketSeed } from "@/adapters/ownMarkets/catalog";
import { Store } from "../server/store.mts";
import { sembrarPozos } from "../server/mercados.mts";
import { muestrasDe, trazaDe } from "../server/director.mts";
import { DirectorEnVivo } from "../server/agente.mts";
import { createFakeApi, renderApp, READY_NO_FUNDS } from "./helpers";
import { S } from "@/lib/strings";

/**
 * El director reporta su backtest y se deja depurar: ¿sus priors aciertan más
 * que un volado?, ¿qué hizo en cada vuelta?, ¿qué pasó con este mercado?
 */

const muestra = (director: Record<string, number>, ganador: string, i = 0, familia = "Partidos"): Muestra => ({
  id: `m${i}`,
  familia,
  apuestas: 0,
  director,
  gente: director,
  ganador,
});

describe("Brier y la comparación pareada", () => {
  it("Brier multiclase: 0 perfecto, 1−1/K parejo, 2 el peor", () => {
    expect(brier({ si: 1, no: 0 }, "si")).toBe(0);
    expect(brier({ si: 0.5, no: 0.5 }, "si")).toBeCloseTo(0.5);
    expect(brier({ local: 1 / 3, empate: 1 / 3, visita: 1 / 3 }, "empate")).toBeCloseTo(2 / 3);
    expect(brier({ si: 0, no: 1 }, "si")).toBe(2);
  });

  it("con n < 30 no concluye, aunque el director haya acertado todo", () => {
    const pocas = Array.from({ length: N_MINIMO - 1 }, (_, i) => muestra({ si: 0.9, no: 0.1 }, "si", i));
    expect(calificar(pocas).directorVsParejo.veredicto).toBe("no_concluye");
  });

  it("un prior que acierta de forma consistente sale «mejor» con su IC95 debajo de cero", () => {
    const muchas = Array.from({ length: 40 }, (_, i) => muestra({ si: 0.8, no: 0.2 }, i % 10 < 8 ? "si" : "no", i));
    const c = calificar(muchas);
    expect(c.directorVsParejo.veredicto).toBe("mejor");
    expect(c.directorVsParejo.ic95[1]).toBeLessThan(0);
    expect(c.conPrior).toBe(40);
  });

  it("un prior que se equivoca sale «peor»: el backtest no está para dar buenas noticias", () => {
    const muchas = Array.from({ length: 40 }, (_, i) => muestra({ si: 0.8, no: 0.2 }, i % 10 < 2 ? "si" : "no", i));
    expect(calificar(muchas).directorVsParejo.veredicto).toBe("peor");
  });

  it("un prior apenas mejor que el volado, con ruido: el IC cruza cero y no se le llama «mejor»", () => {
    // 60/40 que acierta el 60 %: la media favorece al director, pero no se distingue
    const ruidosas = Array.from({ length: 40 }, (_, i) => muestra({ si: 0.6, no: 0.4 }, i % 5 < 3 ? "si" : "no", i));
    const c = calificar(ruidosas).directorVsParejo;
    expect(c.media).toBeLessThan(0);
    expect(c.ic95[0]).toBeLessThan(0);
    expect(c.ic95[1]).toBeGreaterThan(0);
    expect(c.veredicto).toBe("indistinguible");
  });

  it("sembrar parejo no es «mejor» ni «peor»: es nada, y lo dice", () => {
    const parejas = Array.from({ length: 40 }, (_, i) => muestra({ si: 0.5, no: 0.5 }, i % 2 ? "si" : "no", i));
    const c = calificar(parejas);
    expect(c.directorVsParejo.veredicto).toBe("indistinguible");
    expect(c.conPrior).toBe(0);
  });

  it("calibración por tramos: lo que dijo 80 % pasó 80 % de las veces", () => {
    const muchas = Array.from({ length: 10 }, (_, i) => muestra({ si: 0.8, no: 0.2 }, i < 8 ? "si" : "no", i));
    const tramo = calificar(muchas).tramos.find((t) => t.desde === 0.8)!;
    expect(tramo).toMatchObject({ n: 10 });
    expect(tramo.predicho).toBeCloseTo(0.8);
    expect(tramo.observado).toBeCloseTo(0.8);
  });

  it("por familia y en total", () => {
    const r = backtest([muestra({ si: 0.6, no: 0.4 }, "si", 1, "Partidos"), muestra({ si: 0.5, no: 0.5 }, "no", 2, "Sismos")]);
    expect(r.total.n).toBe(2);
    expect(Object.keys(r.porFamilia).sort()).toEqual(["Partidos", "Sismos"]);
  });
});

const AHORA = Date.parse("2026-10-20T12:00:00Z");
function conStore<T>(fn: (store: Store) => Promise<T> | T): Promise<T> {
  const dir = mkdtempSync(join(tmpdir(), "marea-backtest-"));
  return Promise.resolve(fn(new Store(dir))).finally(() => rmSync(dir, { recursive: true, force: true }));
}

describe("Las muestras salen de lo que de verdad pagó", () => {
  it("el prior es la semilla con que nació; la gente, la semilla más lo apostado", () =>
    conStore((store) => {
      const base = sismoSeed(Date.parse("2026-10-05T06:00:00Z"));
      const seed: OwnMarketSeed = { ...base, pool: { ...base.pool, outcomes: { si: 300, no: 700 } } };
      const abierto: OwnMarketSeed = { ...base, id: "sin-pagar" };
      sembrarPozos(store, [seed, abierto]);
      store.crearUsuario({ id: "u1", usuario: "ana", hash: "h", salt: "s", creado: "2026-08-01", puntos: 1000 });
      store.apostar({ usuarioId: "u1", marketId: seed.id, side: "si", stake: 1000, precio: 0.3 });
      store.guardarLiquidacion({ ...initialState(seed.id), phase: "pagado", outcome: "si" });
      store.guardarLiquidacion({ ...initialState(abierto.id), phase: "en_disputa", outcome: "si" });

      const [m, ...resto] = muestrasDe(store, [seed, abierto]);
      expect(resto).toEqual([]);
      expect(m.director.si).toBeCloseTo(0.3);
      expect(m.gente.si).toBeCloseTo(1300 / 2000);
      expect(m).toMatchObject({ ganador: "si", familia: "Sismos", apuestas: 1 });
    }));

  it("la traza junta estado, hallazgos y cada decisión sobre el mercado", () =>
    conStore((store) => {
      const seed = sismoSeed(Date.parse("2026-10-05T06:00:00Z"));
      sembrarPozos(store, [seed]);
      store.guardarLiquidacion({ ...initialState(seed.id), phase: "cerrado", evidence: "USGS: sin sismos" });
      store.anotar(
        [
          { tipo: "publicar", sujeto: seed.id, motivo: "nace", autor: "reglas", reversible: true },
          { tipo: "publicar", sujeto: "otro", motivo: "x", autor: "reglas", reversible: true },
        ],
        AHORA,
      );
      const t = trazaDe(store, [seed], seed.id)!;
      expect(t.estado).toMatchObject({ phase: "cerrado", evidence: "USGS: sin sismos" });
      expect(t.decisiones.map((e) => e.sujeto)).toEqual([seed.id]);
      expect(t.mercado).toMatchObject({ familia: "Sismos", fuente: seed.resolution.sourceName });
      expect(trazaDe(store, [seed], "no-existe")).toBeNull();
    }));

  it("el historial guarda sólo las vueltas que hicieron algo, con su duración", () =>
    conStore(async (store) => {
      const director = new DirectorEnVivo(store, () => []);
      await director.vuelta({ catalogo: [], ahora: AHORA });
      expect(director.ultima).toMatchObject({ intentados: 0 });
      expect(director.ultima?.duracionMs).toBeGreaterThanOrEqual(0);
      expect(director.historial).toEqual([]);
    }));
});

describe("Pantalla: backtest, vueltas y traza", () => {
  afterEach(() => vi.unstubAllGlobals());

  const cal = (n: number, veredicto: string) => ({
    n,
    conPrior: n,
    conApuestas: 1,
    brier: { parejo: 0.5, director: 0.41, gente: 0.39 },
    directorVsParejo: { media: -0.09, ic95: [-0.15, -0.03], veredicto },
    genteVsDirector: { media: -0.02, ic95: [-0.06, 0.02], veredicto: n < 30 ? "no_concluye" : "indistinguible" },
    tramos: [],
  });
  const reporte = {
    catalogo: { abiertos: 1, porFamilia: {}, multiOpcion: 0 },
    resoluciones7d: { resueltos: 0, medianaHoras: null },
    salud: { atorados: 0, retenidos: 0, hallazgos: {} },
    hallazgos: [],
    decisiones: {
      total: 1,
      cadena: { ok: true, entradas: 1 },
      ultimas: [{ n: 1, at: "2026-10-01T12:00:00Z", tipo: "actuar", sujeto: "liga-mx-x", titulo: "Pumas vs. Chivas", motivo: "Releído en vivo (cerrado → en_disputa).", autor: "reglas", regla: "R-085" }],
    },
    juez: { activo: false, modelo: null },
    backtest: { total: cal(41, "mejor"), porFamilia: { Partidos: cal(12, "no_concluye") } },
    depuracion: {
      vueltas: [{ at: "2026-10-01T12:00:00Z", duracionMs: 840, intentados: 3, acciones: [{ id: "liga-mx-x", de: "cerrado", a: "en_disputa", como: "releer", motivo: "x" }], errores: ["espn: 503"] }],
    },
  };
  const traza = {
    mercado: { titulo: "Pumas vs. Chivas", fuente: "ESPN", criterio: "Gana Pumas en tiempo regular.", prior: { local: 0.45, empate: 0.27, visita: 0.28 } },
    estado: { phase: "en_disputa", outcome: "local", evidence: "ESPN: final 2-1" },
    apuestas: { n: 4, sinPagar: 4 },
    hallazgos: [],
    decisiones: [{ n: 1, at: "2026-10-01T12:00:00Z", tipo: "actuar", sujeto: "liga-mx-x", motivo: "Releído en vivo (cerrado → en_disputa).", autor: "reglas" }],
  };

  it("dice el veredicto con su n, enseña las vueltas y abre la traza al tocar", async () => {
    const pedidos: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        pedidos.push(url);
        return new Response(JSON.stringify(url.includes("/traza") ? traza : reporte));
      }),
    );
    renderApp({ api: createFakeApi({ puntos: 1000 }).api, overrides: { ...READY_NO_FUNDS, tab: "director" } });
    await waitFor(() => expect(screen.getByTestId("director-backtest")).toBeTruthy());

    const [total, partidos] = screen.getAllByTestId("director-backtest-fila").map((f) => f.textContent ?? "");
    expect(total).toMatch(/director acierta más que parejo · IC95 \[-0\.150, -0\.030\]/);
    expect(partidos).toContain(S.director.noConcluye(12));
    expect(screen.getByTestId("director-vuelta").textContent).toMatch(/3 intentos · 1 acción · 1 error.*840 ms.*cerrado → en_disputa.*espn: 503/);

    await userEvent.click(screen.getByTestId("director-decision").querySelector("button")!);
    await waitFor(() => expect(screen.getByTestId("director-traza")).toBeTruthy());
    expect(pedidos.at(-1)).toBe("/api/director/traza?id=liga-mx-x");
    expect(screen.getByTestId("director-traza").textContent).toMatch(/en_disputa · local.*ESPN: final 2-1.*nació en local 45 %/);
  });
});
