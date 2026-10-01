import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { createMatchOracle, type EspnEvento } from "@/adapters/oracles/matchOracle";
import { partidosSeeds } from "@/adapters/ownMarkets/templates";
import type { OwnMarketSeed } from "@/adapters/ownMarkets/catalog";
import { verificarCadena } from "@/domain/bitacora";
import { irresoluble, porActuar, REINTENTO_MS } from "@/domain/remediacion";
import type { Hallazgo } from "@/domain/revisor";
import { anular, initialState, type Oracle } from "@/domain/settlement";
import type { MatchRule } from "@/domain/oracleRule";
import { Store } from "../server/store.mts";
import { sembrarPozos } from "../server/mercados.mts";
import { DirectorEnVivo, Turno } from "../server/agente.mts";
import { correrCiclo } from "../server/ciclo.mts";
import { directores, esDirector } from "../server/director.mts";
import { createFakeApi, renderApp, READY_NO_FUNDS } from "./helpers";

/**
 * El director en tiempo real (R-085): lo que el revisor encuentra se arregla en
 * la misma vuelta, no al ciclo siguiente ni a los 30 días. Y el panel donde se
 * ve es interno.
 */

const H = 3_600_000;
const INICIO = "2026-09-27T17:05:00Z";
const [YANKEES] = partidosSeeds(
  [{ inicio: INICIO, local: "New York Yankees", visitante: "Baltimore Orioles", liga: "mlb" }],
  Date.parse("2026-09-26T00:00:00Z"),
);
// dos días después del partido: el revisor ya lo ve `sin_leer`
const AHORA = Date.parse("2026-09-29T19:00:00Z");

const evento = (estado: string, marcador = ["0", "0"]): EspnEvento => ({
  date: INICIO,
  name: "Baltimore Orioles at New York Yankees",
  competitions: [
    {
      status: { type: { name: estado, completed: estado === "STATUS_FINAL" } },
      competitors: [
        { homeAway: "home", score: marcador[0], team: { displayName: "New York Yankees" } },
        { homeAway: "away", score: marcador[1], team: { displayName: "Baltimore Orioles" } },
      ],
    },
  ],
});

function conStore<T>(fn: (store: Store) => Promise<T> | T): Promise<T> {
  const dir = mkdtempSync(join(tmpdir(), "marea-director-"));
  return Promise.resolve(fn(new Store(dir))).finally(() => rmSync(dir, { recursive: true, force: true }));
}

function conApuesta(store: Store, seed: OwnMarketSeed) {
  sembrarPozos(store, [seed]);
  store.crearUsuario({ id: "u1", usuario: "ana", hash: "h", salt: "s", creado: "2026-08-01", puntos: 100 });
  const lado = seed.outcomes?.[0]?.id ?? "si";
  store.apostar({ usuarioId: "u1", marketId: seed.id, side: lado, stake: 40, precio: 0.5 });
}

describe("irresoluble: sólo lo que demostrablemente no se va a resolver", () => {
  const rule = YANKEES.rule as MatchRule;
  const base = { id: YANKEES.id, closesAt: YANKEES.closesAt };
  const pospuesto = { ...initialState(YANKEES.id), phase: "cerrado" as const, evidence: "ESPN: pospuesto" };

  it("rival por definir, ya empezado: no hay a quién pagar", () => {
    const tbd = { ...rule, rival: "TBD" };
    expect(irresoluble({ ...base, rule: tbd }, Date.parse(INICIO) + H)).toMatch(/rival/);
    // antes de su hora todavía puede definirse
    expect(irresoluble({ ...base, rule: tbd }, Date.parse(INICIO) - H)).toBeUndefined();
  });

  it("pospuesto sin cláusula: a las 72 h, no antes", () => {
    // los mercados anteriores a R-084 no llevan la cláusula
    const { reprogramacionDias: _, ...sinClausula } = rule;
    const rule2 = sinClausula as MatchRule;
    expect(irresoluble({ ...base, rule: rule2, estado: pospuesto }, Date.parse(INICIO) + 71 * H)).toBeUndefined();
    expect(irresoluble({ ...base, rule: rule2, estado: pospuesto }, Date.parse(INICIO) + 73 * H)).toMatch(/no prometía/);
  });

  it("pospuesto con cláusula de 7 días: espera los 7 días más uno", () => {
    const conClausula = { ...rule, reprogramacionDias: 7 };
    expect(irresoluble({ ...base, rule: conClausula, estado: pospuesto }, Date.parse(INICIO) + 7 * 24 * H)).toBeUndefined();
    expect(irresoluble({ ...base, rule: conClausula, estado: pospuesto }, Date.parse(INICIO) + 8 * 24 * H + H)).toMatch(/7 días/);
  });

  it("sin evidencia de que no se jugó, no se anula aunque pase el tiempo", () => {
    const sinDato = { ...pospuesto, evidence: "ESPN no contestó" };
    expect(irresoluble({ ...base, rule, estado: sinDato }, Date.parse(INICIO) + 30 * 24 * H)).toBeUndefined();
  });

  it("nunca toca lo que ya tiene resultado, lo pagado ni lo retenido", () => {
    const tarde = Date.parse(INICIO) + 10 * 24 * H;
    for (const estado of [
      { ...pospuesto, phase: "en_disputa" as const },
      { ...pospuesto, phase: "pagado" as const },
      { ...pospuesto, retenidoPor: "revisor" },
    ]) {
      expect(irresoluble({ ...base, rule, estado }, tarde)).toBeUndefined();
    }
  });

  it("anular no pisa un resultado en disputa", () => {
    const enDisputa = { ...initialState("x"), phase: "en_disputa" as const, outcome: "si" };
    expect(anular(enDisputa, "x")).toEqual(enDisputa);
  });
});

describe("porActuar: qué se intenta en esta vuelta", () => {
  const h = (codigo: Hallazgo["codigo"], sujeto: string): Hallazgo => ({
    clave: `${codigo}:${sujeto}`,
    codigo,
    severidad: "grave",
    sujeto,
    detalle: "x",
  });

  it("sólo lo accionable, sin repetir y respetando el reintento", () => {
    const hallazgos = [h("sin_leer", "a"), h("atorado", "a"), h("titulo_largo", "b"), h("abierto_tras_cierre", "c"), h("atorado", "d")];
    const intentos = new Map([["d", AHORA - REINTENTO_MS + 1]]);
    expect(porActuar(hallazgos, intentos, AHORA)).toEqual(["a", "c"]);
    expect(porActuar(hallazgos, new Map([["d", AHORA - REINTENTO_MS]]), AHORA)).toEqual(["a", "c", "d"]);
    expect(porActuar(hallazgos, new Map(), AHORA, 1)).toEqual(["a"]);
  });
});

describe("Director en vivo: audita y actúa en la misma vuelta", () => {
  it("un partido ya terminado que nadie leyó: se lee y entra a disputa en esta vuelta", () =>
    conStore(async (store) => {
      conApuesta(store, YANKEES);
      store.guardarLiquidacion({ ...initialState(YANKEES.id), phase: "cerrado", evidence: "ESPN: no ha terminado" });
      const lecturas = vi.fn(async () => [evento("STATUS_FINAL", ["5", "3"])]);
      const director = new DirectorEnVivo(store, () => [createMatchOracle({ cargarPartidos: lecturas })]);

      const vuelta = await director.vuelta({ catalogo: [YANKEES], ahora: AHORA });
      expect(store.liquidacion(YANKEES.id)?.phase).toBe("en_disputa");
      expect(vuelta.acciones).toEqual([expect.objectContaining({ id: YANKEES.id, de: "cerrado", a: "en_disputa", como: "releer" })]);

      const actuar = store.bitacora().filter((e) => e.tipo === "actuar");
      expect(actuar).toHaveLength(1);
      expect(actuar[0]).toMatchObject({ regla: "R-085", autor: "reglas", reversible: true });
      expect(verificarCadena(store.bitacora()).ok).toBe(true);
      // y el hallazgo se cerró en la misma vuelta
      expect(store.hallazgos().some((x) => x.sujeto === YANKEES.id && x.codigo === "sin_leer")).toBe(false);
    }));

  it("un rival por definir: se anula y se devuelve lo apostado, íntegro, ya", () =>
    conStore(async (store) => {
      const tbd: OwnMarketSeed = { ...YANKEES, rule: { ...(YANKEES.rule as MatchRule), rival: "TBD" } };
      conApuesta(store, tbd);
      // una fuente caída no detiene la devolución: lo anulado ya no se lee
      const oraculo: Oracle = { id: "caido", handles: () => true, read: async () => Promise.reject(new Error("503")) };
      const director = new DirectorEnVivo(store, () => [oraculo]);

      const vuelta = await director.vuelta({ catalogo: [tbd], ahora: AHORA });
      expect(vuelta.errores).toEqual([]);
      expect(store.liquidacion(tbd.id)?.phase).toBe("devuelto");
      expect(store.usuarioPorId("u1")?.puntos).toBe(100);
      expect(vuelta.acciones[0]).toMatchObject({ como: "anular", a: "devuelto" });
      const [entrada] = store.bitacora().filter((e) => e.tipo === "actuar");
      expect(entrada).toMatchObject({ regla: "R-085", reversible: false });
      expect(entrada.motivo).toMatch(/rival definido/);
    }));

  it("una lectura tardía con resultado no convierte una anulación en un pago", () =>
    conStore(async (store) => {
      conApuesta(store, YANKEES);
      store.guardarLiquidacion(anular({ ...initialState(YANKEES.id), phase: "cerrado" }, "No se jugó en su fecha."));
      const tarde = createMatchOracle({ cargarPartidos: async () => [evento("STATUS_FINAL", ["5", "3"])] });
      await correrCiclo(store, [YANKEES], [tarde], AHORA);
      expect(store.liquidacion(YANKEES.id)?.phase).toBe("devuelto");
      expect(store.usuarioPorId("u1")?.puntos).toBe(100);
    }));

  it("no martilla: un mismo mercado se reintenta como mucho cada cinco minutos", () =>
    conStore(async (store) => {
      conApuesta(store, YANKEES);
      store.guardarLiquidacion({ ...initialState(YANKEES.id), phase: "cerrado", evidence: "ESPN: no ha terminado" });
      const lecturas = vi.fn(async () => [evento("STATUS_IN_PROGRESS")]);
      const director = new DirectorEnVivo(store, () => [createMatchOracle({ cargarPartidos: lecturas })]);

      await director.vuelta({ catalogo: [YANKEES], ahora: AHORA });
      const tras1 = lecturas.mock.calls.length;
      expect(tras1).toBeGreaterThan(0);
      await director.vuelta({ catalogo: [YANKEES], ahora: AHORA + 60_000 });
      expect(lecturas.mock.calls.length).toBe(tras1);
      await director.vuelta({ catalogo: [YANKEES], ahora: AHORA + REINTENTO_MS });
      expect(lecturas.mock.calls.length).toBeGreaterThan(tras1);
      // sin cambio de fase no se escribe nada: la bitácora no es un log
      expect(store.bitacora().filter((e) => e.tipo === "actuar")).toHaveLength(0);
    }));

  it("el turno serializa: dos trabajos nunca se pisan", async () => {
    const turno = new Turno();
    const orden: string[] = [];
    const lento = turno.correr(async () => {
      orden.push("a:entra");
      await new Promise((r) => setTimeout(r, 20));
      orden.push("a:sale");
    });
    const rapido = turno.correr(async () => {
      orden.push("b:entra");
    });
    await Promise.all([lento, rapido]);
    expect(orden).toEqual(["a:entra", "a:sale", "b:entra"]);
    // y una falla no tranca la cola
    await expect(turno.correr(async () => Promise.reject(new Error("x")))).rejects.toThrow("x");
    await expect(turno.correr(async () => 1)).resolves.toBe(1);
  });
});

describe("El panel del director es interno", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("MAREA_ADMINS manda, sin distinguir mayúsculas; sin ella, sólo la cuenta más antigua", () =>
    conStore((store) => {
      store.crearUsuario({ id: "u2", usuario: "Beto", hash: "h", salt: "s", creado: "2026-09-01", puntos: 0 });
      store.crearUsuario({ id: "u1", usuario: "RasDG", hash: "h", salt: "s", creado: "2026-07-01", puntos: 0 });
      expect([...directores(store, {})]).toEqual(["rasdg"]);
      expect(esDirector(store, { usuario: "Beto" }, {})).toBe(false);
      expect(esDirector(store, { usuario: "beto" }, { MAREA_ADMINS: " BETO , otra" })).toBe(true);
      expect(esDirector(store, { usuario: "RasDG" }, { MAREA_ADMINS: "beto" })).toBe(false);
      expect(esDirector(store, null, { MAREA_ADMINS: "beto" })).toBe(false);
    }));

  it("la puerta en el perfil sólo aparece para quien opera Marea", async () => {
    const cuenta = { usuario: "ana", puntos: 1000, recargaDisponible: 0, posiciones: [] };
    const vista = renderApp({ api: createFakeApi({ puntos: 1000 }).api, overrides: { ...READY_NO_FUNDS, tab: "profile", cuenta } });
    await waitFor(() => expect(screen.getByTestId("profile-cartera")).toBeTruthy());
    expect(screen.queryByTestId("profile-director")).toBeNull();
    vista.unmount();

    renderApp({
      api: createFakeApi({ puntos: 1000, director: true }).api,
      overrides: { ...READY_NO_FUNDS, tab: "profile", cuenta: { ...cuenta, director: true } },
    });
    await waitFor(() => expect(screen.getByTestId("profile-director")).toBeTruthy());
  });

  it("sin permiso, la pantalla dice que es interno, no que falló", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 403 })));
    renderApp({ api: createFakeApi({ puntos: 1000 }).api, overrides: { ...READY_NO_FUNDS, tab: "director" } });
    await waitFor(() => expect(screen.getByTestId("director-interno")).toBeTruthy());
  });
});
