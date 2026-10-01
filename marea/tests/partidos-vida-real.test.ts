import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { createMatchOracle, type EspnEvento } from "@/adapters/oracles/matchOracle";
import { partidosSeeds } from "@/adapters/ownMarkets/templates";
import { initialState, onRead } from "@/domain/settlement";
import type { MatchRule } from "@/domain/oracleRule";
import { Store } from "../server/store.mts";
import { correrCiclo } from "../server/ciclo.mts";
import { sembrarPozos } from "../server/mercados.mts";

/**
 * Lo que le pasa a un partido en la vida real y el oráculo no sabía manejar.
 * Los tres casos los encontró el revisor en producción el 2026-10-01 (`sin_leer`):
 * Yankees–Orioles **cancelado**, Phillies–Rays **a otra hora** el mismo día, y
 * Red Bull NY–St. Louis **reprogramado** del 26 al 30 de septiembre.
 */

const DIA = 86_400_000;
const evento = (fecha: string, estado: string, local: string, visitante: string, marcador = ["0", "0"]): EspnEvento => ({
  date: fecha,
  name: `${visitante} at ${local}`,
  competitions: [
    {
      status: { type: { name: estado, completed: estado === "STATUS_FINAL" || estado === "STATUS_FULL_TIME" } },
      competitors: [
        { homeAway: "home", score: marcador[0], team: { displayName: local } },
        { homeAway: "away", score: marcador[1], team: { displayName: visitante } },
      ],
    },
  ],
});
const spec = { sourceName: "ESPN", sourceUrl: "x", criterion: "x", settlesAt: "2026-09-27T23:00:00Z", disputeWindowHours: 12 };

describe("Cancelado: se anula ya, no a los 30 días", () => {
  const rule: MatchRule = { kind: "partido", liga: "mlb", fecha: "2026-09-27", inicio: "2026-09-27T17:05Z", equipo: "New York Yankees", resultado: "gana" };
  const oraculo = createMatchOracle({
    cargarPartidos: async () => [evento("2026-09-27T17:05Z", "STATUS_CANCELED", "New York Yankees", "Baltimore Orioles")],
  });

  it("el oráculo pide anular, y la liquidación lo marca incobrable", async () => {
    const r = await oraculo.read({ marketId: "x", spec, rule, now: Date.parse("2026-09-28T00:00:00Z") });
    expect(r).toMatchObject({ status: "sin_dato", anular: true });
    const estado = onRead({ marketId: "x", phase: "cerrado" }, r, spec, Date.parse("2026-09-28T00:00:00Z"));
    expect(estado).toMatchObject({ phase: "atorado", incobrable: true });
  });

  it("en el ciclo, se devuelve en la misma vuelta", async () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-cancelado-"));
    try {
      const [seed] = partidosSeeds(
        [{ inicio: "2026-09-27T17:05:00Z", local: "New York Yankees", visitante: "Baltimore Orioles", liga: "mlb" }],
        Date.parse("2026-09-26T00:00:00Z"),
      );
      const store = new Store(dir);
      sembrarPozos(store, [seed]);
      store.guardarLiquidacion(initialState(seed.id));
      await correrCiclo(store, [seed], [oraculo], Date.parse("2026-09-28T00:00:00Z"));
      expect(store.liquidacion(seed.id)?.phase).toBe("devuelto");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("Hora movida el mismo día: es el mismo partido", () => {
  const rule: MatchRule = { kind: "partido", liga: "mlb", fecha: "2026-09-27", inicio: "2026-09-27T17:05Z", equipo: "Philadelphia Phillies", resultado: "gana" };

  it("un solo partido cerca de la hora prometida: se resuelve con él", async () => {
    const oraculo = createMatchOracle({
      cargarPartidos: async () => [evento("2026-09-27T18:30Z", "STATUS_FINAL", "Philadelphia Phillies", "Tampa Bay Rays", ["5", "3"])],
    });
    expect(await oraculo.read({ marketId: "x", spec, rule, now: Date.parse("2026-09-28T00:00:00Z") })).toMatchObject({
      status: "resuelto",
      outcome: "si",
    });
  });

  it("dos partidos el mismo día (doble cartelera): no se adivina", async () => {
    const oraculo = createMatchOracle({
      cargarPartidos: async () => [
        evento("2026-09-27T16:00Z", "STATUS_FINAL", "Philadelphia Phillies", "Tampa Bay Rays", ["5", "3"]),
        evento("2026-09-27T22:00Z", "STATUS_FINAL", "Philadelphia Phillies", "Tampa Bay Rays", ["1", "3"]),
      ],
    });
    expect((await oraculo.read({ marketId: "x", spec, rule, now: Date.parse("2026-09-28T00:00:00Z") })).status).toBe("sin_dato");
  });
});

describe("Reprogramado a otro día: sólo si el mercado lo prometió (R-084)", () => {
  const base: MatchRule = { kind: "partido", liga: "usa.1", fecha: "2026-09-26", inicio: "2026-09-26T23:30Z", equipo: "Red Bull New York", resultado: "gana" };
  const jornadas: Record<string, EspnEvento[]> = {
    "2026-09-26": [evento("2026-09-26T23:30Z", "STATUS_POSTPONED", "Red Bull New York", "St. Louis CITY SC")],
    "2026-09-30": [evento("2026-09-30T23:30Z", "STATUS_FULL_TIME", "Red Bull New York", "St. Louis CITY SC", ["2", "1"])],
  };
  const oraculo = createMatchOracle({ cargarPartidos: async (r) => jornadas[r.fecha] ?? [] });
  const ahora = Date.parse("2026-10-01T19:00:00Z");

  it("con la cláusula, se resuelve con el partido reprogramado entre los mismos equipos", async () => {
    const r = await oraculo.read({ marketId: "x", spec, rule: { ...base, rival: "St. Louis CITY SC", reprogramacionDias: 7 }, now: ahora });
    expect(r).toMatchObject({ status: "resuelto", outcome: "si" });
  });

  it("sin la cláusula (mercados anteriores), no: queda pospuesto y el plazo devuelve", async () => {
    // con rival y todo: lo que decide es la promesa escrita, no que se pueda buscar
    const r = await oraculo.read({ marketId: "x", spec, rule: { ...base, rival: "St. Louis CITY SC" }, now: ahora });
    expect(r.status).toBe("sin_dato");
    expect(r.evidence).toMatch(/pospuesto/);
  });

  it("los partidos nuevos llevan el rival, la ventana y la cláusula escrita en su criterio", () => {
    const [seed] = partidosSeeds(
      [{ inicio: "2026-10-04T23:30:00Z", local: "Red Bull New York", visitante: "St. Louis CITY SC", liga: "usa.1" }],
      Date.parse("2026-10-01T00:00:00Z") - 0 * DIA,
    );
    expect(seed.rule).toMatchObject({ rival: "St. Louis CITY SC", reprogramacionDias: 7 });
    expect(seed.resolution.criterion).toMatch(/Si el partido se reprograma.*7 días.*se anula y se devuelve todo/);
  });
});
