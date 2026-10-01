import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { createFakeApi, renderApp, READY_NO_FUNDS } from "./helpers";
import { Store } from "../server/store.mts";
import { reporteDirector } from "../server/director.mts";
import { sismoSeed } from "@/adapters/ownMarkets/sismos";
import { S } from "@/lib/strings";

/**
 * El panel del director: transparencia de un agente que decide solo
 * (MEMORY/FILOSOFIA.md, principio 9). Que el reporte diga la verdad sobre la
 * cadena, y que la pantalla la enseñe.
 */

const AHORA = Date.parse("2026-10-01T12:00:00Z");
const sismo = sismoSeed(Date.parse("2026-10-05T06:00:00Z"));
const JUEZ_APAGADO = { activo: false, modelo: null, llamadas: 0, tokensEntrada: 0, tokensSalida: 0, vetos: 0, senales: 0, errores: 0 };

describe("Reporte del director", () => {
  it("cuenta lo abierto por familia, verifica la cadena y pone el título legible", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-panel-"));
    try {
      const store = new Store(dir);
      store.anotar(
        [{ tipo: "publicar", sujeto: sismo.id, motivo: "x", autor: "reglas", reversible: true }],
        AHORA,
      );
      const r = reporteDirector({ store, seeds: [sismo], juez: JUEZ_APAGADO, ahora: AHORA });
      expect(r.catalogo).toMatchObject({ abiertos: 1, porFamilia: { Sismos: 1 } });
      expect(r.decisiones.cadena).toEqual({ ok: true, entradas: 1 });
      expect(r.decisiones.ultimas[0].titulo).toBe(sismo.shortTitle);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("Pantalla del director", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("enseña cifras, la cadena verificada, el juez y las decisiones con quién las tomó", async () => {
    const reporte = {
      catalogo: { abiertos: 76, porFamilia: { Partidos: 41, Sismos: 1 }, multiOpcion: 32 },
      resoluciones7d: { resueltos: 3, medianaHoras: 2.5 },
      salud: { atorados: 0, retenidos: 0, hallazgos: { critico: 0, grave: 0, aviso: 0, info: 1 } },
      hallazgos: [{ clave: "categoria_dominante:catalogo", severidad: "info", sujeto: "catalogo", detalle: "deportes es el 64 %" }],
      decisiones: {
        total: 77,
        cadena: { ok: true, entradas: 77 },
        ultimas: [
          { n: 77, at: new Date(AHORA).toISOString(), tipo: "vetar", sujeto: "wiki-x", titulo: "Duelo X", motivo: "sensible: es sobre una muerte", autor: "claude:claude-opus-5-5", regla: "R-081" },
        ],
      },
      juez: { activo: true, modelo: "claude-opus-5-5" },
    };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(reporte))));
    renderApp({ api: createFakeApi({ puntos: 1000 }).api, overrides: { ...READY_NO_FUNDS, tab: "director" } });

    await waitFor(() => expect(screen.getByTestId("director-screen")).toBeTruthy());
    expect(screen.getByTestId("director-cadena").textContent).toBe(S.director.cadenaOk(77));
    expect(screen.getByTestId("director-juez").textContent).toBe(S.director.juezActivo("claude-opus-5-5"));
    const decision = screen.getByTestId("director-decision").textContent ?? "";
    expect(decision).toMatch(/Vetó.*Duelo X/);
    expect(decision).toMatch(/claude:claude-opus-5-5 · R-081/);
    expect(screen.getAllByTestId("director-hallazgo")).toHaveLength(1);
  });

  it("una cadena rota se dice en rojo, con el número donde se rompe", async () => {
    const reporte = {
      catalogo: { abiertos: 0, porFamilia: {}, multiOpcion: 0 },
      resoluciones7d: { resueltos: 0, medianaHoras: null },
      salud: { atorados: 0, retenidos: 0, hallazgos: {} },
      hallazgos: [],
      decisiones: { total: 9, cadena: { ok: false, en: 4 }, ultimas: [] },
      juez: { activo: false, modelo: null },
    };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(reporte))));
    renderApp({ api: createFakeApi({ puntos: 1000 }).api, overrides: { ...READY_NO_FUNDS, tab: "director" } });
    await waitFor(() => expect(screen.getByTestId("director-cadena").textContent).toBe(S.director.cadenaRota(4)));
    expect(screen.getByTestId("director-juez").textContent).toBe(S.director.juezApagado);
  });
});
