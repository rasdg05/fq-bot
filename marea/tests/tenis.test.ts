import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  createTennisOracle,
  resolverTenis,
  type EspnPartidoTenis,
} from "@/adapters/oracles/tennisOracle";
import {
  LIGA_TENIS,
  rondaEnEspanol,
  tenisSeed,
  tenisSeeds,
  type PartidoTenis,
} from "@/adapters/ownMarkets/templates";
import { SHORT_TITLE_IDEAL, validateSeed } from "@/adapters/ownMarkets/catalog";
import type { TennisRule } from "@/domain/oracleRule";
import { Store } from "../server/store.mts";
import { MINIMO_ABIERTOS, reponer } from "../server/reposicion.mts";
import { OWN_MARKETS } from "@/adapters/ownMarkets/catalog";

/**
 * Tenis ATP contra el marcador de ESPN. La forma de los datos es la medida el
 * 2026-10-01 (Japan Open y China Open): torneo → `mens-singles` → partido con
 * `winner` por jugador y una nota legible del resultado.
 */

const AHORA = Date.parse("2026-10-01T00:00:00Z");

const RULE: TennisRule = {
  kind: "tenis",
  circuito: "atp",
  partido: "186248",
  fecha: "2026-10-01",
  jugador: "Stefanos Tsitsipas",
  rival: "Yoshihito Nishioka",
};

function partido(parcial: Partial<EspnPartidoTenis> & { ganador?: 1 | 2 } = {}): EspnPartidoTenis {
  const { ganador, ...resto } = parcial;
  return {
    id: "186248",
    date: "2026-10-01T03:00Z",
    round: { displayName: "Round 1" },
    notes: ganador ? [{ text: "Stefanos Tsitsipas (GRE) bt Yoshihito Nishioka (JPN) 7-5 6-2" }] : [],
    status: { type: { name: ganador ? "STATUS_FINAL" : "STATUS_SCHEDULED", state: ganador ? "post" : "pre", completed: Boolean(ganador) } },
    competitors: [
      { id: "1", order: 1, winner: ganador ? ganador === 1 : null, athlete: { displayName: "Stefanos Tsitsipas", shortName: "S. Tsitsipas" } },
      { id: "2", order: 2, winner: ganador ? ganador === 2 : null, athlete: { displayName: "Yoshihito Nishioka", shortName: "Y. Nishioka" } },
    ],
    ...resto,
  };
}

describe("Oráculo de tenis — cuándo se paga", () => {
  it("terminado con ganador: paga al ganador y cita la nota de ESPN", () => {
    const r = resolverTenis(RULE, partido({ ganador: 1 }));
    expect(r).toMatchObject({ status: "resuelto", outcome: "si" });
    expect(r.evidence).toMatch(/bt Yoshihito Nishioka.*7-5 6-2/);
    const rival = resolverTenis(RULE, partido({ ganador: 2 }));
    expect(rival).toMatchObject({ status: "resuelto", outcome: "no" });
  });

  it("en juego: no paga, pero detiene las apuestas aunque falte su hora", () => {
    const r = resolverTenis(
      RULE,
      partido({ status: { type: { name: "STATUS_IN_PROGRESS", state: "in", completed: false } } }),
    );
    expect(r).toMatchObject({ status: "sin_dato", detenerApuestas: true });
  });

  it("programado: ni paga ni detiene", () => {
    const r = resolverTenis(RULE, partido());
    expect(r.status).toBe("sin_dato");
    expect("detenerApuestas" in r && r.detenerApuestas).toBeFalsy();
  });

  it("terminado sin un único ganador (cancelado): no paga a nadie y cierra", () => {
    const r = resolverTenis(
      RULE,
      partido({ status: { type: { name: "STATUS_CANCELED", state: "post", completed: true } } }),
    );
    expect(r).toMatchObject({ status: "sin_dato", detenerApuestas: true });
  });

  it("un ganador que no es ninguno de los dos no se acepta", () => {
    const raro = partido({ ganador: 1 });
    raro.competitors[0].athlete!.displayName = "Otro Jugador";
    expect(resolverTenis(RULE, raro).status).toBe("sin_dato");
  });

  it("busca en la jornada anterior (ESPN agrupa por día de EE.UU.) y pide una vez por jornada", async () => {
    const pedidas: string[] = [];
    const oraculo = createTennisOracle({
      cargarTenis: async (fecha) => {
        pedidas.push(fecha);
        return fecha === "2026-09-30" ? [{ torneo: "Japan Open", partido: partido({ ganador: 2 }) }] : [];
      },
    });
    const r = await oraculo.read({ marketId: "atp-186248", spec: {} as never, rule: RULE, now: AHORA });
    expect(r).toMatchObject({ status: "resuelto", outcome: "no" });
    expect(pedidas).toEqual(["2026-10-01", "2026-09-30"]);
    // la segunda lectura de la misma jornada sale de la memoria corta
    await oraculo.read({ marketId: "atp-186248", spec: {} as never, rule: RULE, now: AHORA });
    expect(pedidas).toEqual(["2026-10-01", "2026-09-30"]);
  });
});

const PARTIDO: PartidoTenis = {
  id: "186250",
  inicio: "2026-10-02T05:00:00Z",
  torneo: "China Open",
  ronda: "Quarterfinal",
  jugador: "Alejandro Davidovich Fokina",
  rival: "Nikoloz Basilashvili",
  jugadorCorto: "A. Davidovich Fokina",
  rivalCorto: "N. Basilashvili",
  banderaJugador: "https://a.espncdn.com/i/teamlogos/countries/500/esp.png",
};

describe("Tenis — la semilla", () => {
  it("pasa la validación de producción, con títulos que caben y la bandera de la misma fuente", () => {
    const seed = validateSeed(tenisSeed(PARTIDO));
    expect(seed.shortTitle.length).toBeLessThanOrEqual(SHORT_TITLE_IDEAL);
    expect(seed.outcomes!.map((o) => o.label)).toEqual(["Gana Davidovich Fokina", "Gana Basilashvili"]);
    expect(seed.title).toMatch(/China Open, cuartos de final/);
    expect(seed.liga).toBe(LIGA_TENIS);
    expect(seed.equipos?.[0].escudo).toMatch(/espncdn/);
    // se cierra al arrancar y se resuelve después
    expect(seed.closesAt).toBe("2026-10-02T05:00:00.000Z");
    expect(Date.parse(seed.resolution.settlesAt)).toBeGreaterThan(Date.parse(seed.closesAt));
  });

  it("las rondas se dicen en español", () => {
    expect(rondaEnEspanol("Round 2")).toBe("2.ª ronda");
    expect(rondaEnEspanol("Semifinal")).toBe("semifinal");
    expect(rondaEnEspanol("Final")).toBe("final");
  });

  it("las rondas finales van primero; lo empezado y lo indefinido no entra", () => {
    const seeds = tenisSeeds(
      [
        { ...PARTIDO, id: "1", ronda: "Round 1", inicio: "2026-10-02T01:00:00Z" },
        { ...PARTIDO, id: "2", ronda: "Semifinal", inicio: "2026-10-03T01:00:00Z" },
        { ...PARTIDO, id: "3", ronda: "Round 1", inicio: "2026-09-30T01:00:00Z" }, // ya empezó
        { ...PARTIDO, id: "4", ronda: "Round 2", rival: "TBD", inicio: "2026-10-02T03:00:00Z" },
      ],
      AHORA,
    );
    expect(seeds.map((s) => s.id)).toEqual(["atp-2", "atp-1"]);
  });
});

describe("Tenis — cupo propio en la reposición", () => {
  it("entra aunque el feed esté sano, y nunca pasa de su máximo", async () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-tenis-"));
    try {
      const store = new Store(dir);
      const abiertos = Array.from({ length: MINIMO_ABIERTOS + 5 }, (_, i) => ({
        ...OWN_MARKETS[0],
        id: `abierto-${i}`,
        closesAt: new Date(AHORA + 30 * 86_400_000).toISOString(),
      }));
      const cargar = async () =>
        Array.from({ length: 12 }, (_, i) => ({
          ...PARTIDO,
          id: String(500 + i),
          inicio: new Date(AHORA + (i + 2) * 3_600_000).toISOString(),
        }));
      const r = await reponer(store, abiertos, AHORA, { env: {}, tenis: { maximo: 8, cargar } });
      expect(r.creados.filter((id) => id.startsWith("atp-"))).toHaveLength(8);
      const otra = await reponer(store, abiertos, AHORA + 60_000, { env: {}, tenis: { maximo: 8, cargar } });
      expect(otra.creados).toEqual([]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
