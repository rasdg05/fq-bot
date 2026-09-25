import { describe, expect, it } from "vitest";
import { partidoSeed, partidosSeeds, rollingSeeds } from "@/adapters/ownMarkets/templates";
import { validateSeed } from "@/adapters/ownMarkets/catalog";
import { createMatchOracle, type EspnEvento } from "@/adapters/oracles/matchOracle";
import { velaSeed, ACTIVOS_VIVOS } from "@/adapters/ownMarkets/cryptoLive";
import { LIGAS, urlJornadaEspn } from "@/domain/ligas";
import {
  KRAKEN_PAR,
  PARES_CRIPTO,
  parDeClaveKraken,
  type MatchRule,
} from "@/domain/oracleRule";
import type { OracleQuery } from "@/domain/settlement";

/**
 * El catálogo ampliado: cinco pares de cripto y veinte ligas. Lo que se fija
 * aquí no es que haya más mercados —eso lo dice el feed— sino que **cada uno
 * nace con camino de liquidación**: una regla que un oráculo sabe leer, una
 * fuente citada que es la que se lee, y un criterio que dice la misma cifra.
 */

const AHORA = Date.UTC(2026, 8, 25, 12, 0, 0);

describe("Cripto: cinco pares, todos publicables", () => {
  const spot = {
    "BTC/USD": 84_380,
    "ETH/USD": 2_687.9,
    "SOL/USD": 117.12,
    "XRP/USD": 1.5332,
    "DOGE/USD": 0.0957,
  };
  const seeds = rollingSeeds({ spot, now: AHORA });

  it("salen dos mercados por par: cierre semanal y toque en 30 días", () => {
    expect(seeds).toHaveLength(PARES_CRIPTO.length * 2);
    for (const par of PARES_CRIPTO) {
      expect(seeds.filter((s) => s.rule?.kind === "precio" && s.rule.par === par)).toHaveLength(2);
    }
  });

  it("cada uno pasa la validación del catálogo", () => {
    for (const seed of seeds) expect(() => validateSeed(seed)).not.toThrow();
  });

  it("el umbral no arrastra colas de coma flotante al criterio", () => {
    for (const seed of seeds) {
      if (seed.rule?.kind !== "precio") continue;
      expect(String(seed.rule.umbral)).not.toMatch(/\d{6,}/);
      expect(seed.resolution.criterion).toContain(seed.rule.umbral.toLocaleString("en-US"));
    }
  });

  it("la fuente citada es la URL de Kraken del mismo par", () => {
    for (const seed of seeds) {
      if (seed.rule?.kind !== "precio") continue;
      expect(seed.resolution.sourceUrl).toContain(`pair=${KRAKEN_PAR[seed.rule.par]}`);
    }
  });

  it("las claves del ticker de Kraken se reconocen todas", () => {
    expect(parDeClaveKraken("XXBTZUSD")).toBe("BTC/USD");
    expect(parDeClaveKraken("XETHZUSD")).toBe("ETH/USD");
    expect(parDeClaveKraken("SOLUSD")).toBe("SOL/USD");
    expect(parDeClaveKraken("XXRPZUSD")).toBe("XRP/USD");
    expect(parDeClaveKraken("XDGUSD")).toBe("DOGE/USD");
    expect(parDeClaveKraken("ADAUSD")).toBeUndefined();
  });

  it("la vela viva de Solana lleva un strike con decimales, igual en etiqueta y criterio", () => {
    const sol = ACTIVOS_VIVOS.find((a) => a.id === "sol")!;
    const seed = velaSeed({ activo: sol, intervalo: 5, inicio: AHORA, spot: 117.3 });
    expect(seed.rule?.kind === "vela" && seed.rule.strike).toBe(117.5);
    expect(seed.outcomes?.[0].label).toContain("117.5");
    expect(seed.resolution.criterion).toContain("117.5");
  });
});

describe("Deportes: la forma del mercado sigue a la liga", () => {
  const inicio = "2026-09-27T03:05:00.000Z";

  it("Liga MX conserva su sí/no y sus ids de siempre", () => {
    const seed = partidoSeed({ inicio, local: "América", visitante: "Santos", liga: "mex.1" });
    expect(seed.id).toBe("mx-america-santos-2026-09-27");
    expect(seed.outcomes?.map((o) => o.id)).toEqual(["si", "no"]);
    expect(seed.rule).toMatchObject({ kind: "partido", liga: "mex.1", inicio });
  });

  it("el resto del futbol es la quiniela: gana, empata o pierde", () => {
    const seed = partidoSeed({ inicio, local: "Arsenal", visitante: "Chelsea", liga: "eng.1" });
    expect(seed.id.startsWith("epl-")).toBe(true);
    expect(seed.outcomes?.map((o) => o.id)).toEqual(["gana", "empata", "pierde"]);
    expect(seed.rule).toMatchObject({ kind: "partido_multiple", mercado: "1x2", liga: "eng.1" });
    expect(seed.country).toBe("GB");
    expect(seed.liga).toBe("Premier League");
  });

  it("sin empate (NFL) se pregunta quién gana, con los dos nombres", () => {
    const seed = partidoSeed({ inicio, local: "Chiefs", visitante: "Bills", liga: "nfl" });
    expect(seed.outcomes?.map((o) => o.label)).toEqual(["Gana Chiefs", "Gana Bills"]);
    expect(seed.resolution.criterion).toMatch(/empate/);
    expect(seed.resolution.sourceUrl).toContain("/football/nfl/");
  });

  it("todas las ligas producen un mercado que pasa la validación", () => {
    for (const liga of LIGAS) {
      const [seed] = partidosSeeds(
        [{ inicio, local: "Local FC", visitante: "Visita FC", liga: liga.id }],
        AHORA,
      );
      expect(() => validateSeed(seed), liga.id).not.toThrow();
      expect(seed.resolution.sourceUrl).toBe(urlJornadaEspn(liga.id, "2026-09-27"));
    }
  });

  it("nombres largos caben: se usa el corto de ESPN y la validación pasa", () => {
    for (const liga of ["uru.1", "col.1", "nfl", "mex.1"] as const) {
      const seed = partidoSeed({
        inicio,
        local: "Montevideo City Torque",
        visitante: "Deportivo Maldonado",
        localCorto: "MC Torque",
        visitanteCorto: "Maldonado",
        liga,
      });
      expect(() => validateSeed(seed), liga).not.toThrow();
    }
    // sin nombre corto tampoco se cae: se recorta con puntos suspensivos
    const sinCorto = partidoSeed({
      inicio,
      local: "Independiente Santa Fe de Bogotá",
      visitante: "Atlético Junior de Barranquilla",
      liga: "col.1",
    });
    expect(() => validateSeed(sinCorto)).not.toThrow();
  });

  it("el escudo viaja con el equipo", () => {
    const seed = partidoSeed({
      inicio,
      local: "América",
      visitante: "Santos",
      liga: "mex.1",
      escudoLocal: "https://a.espncdn.com/i/teamlogos/soccer/500/227.png",
    });
    expect(seed.equipos?.[0]).toEqual({
      nombre: "América",
      escudo: "https://a.espncdn.com/i/teamlogos/soccer/500/227.png",
    });
  });
});

describe("El oráculo encuentra el partido aunque ESPN lo liste en el día de EE. UU.", () => {
  const evento = (date: string, local: string, goles: [string, string]): EspnEvento => ({
    date,
    name: `${local} vs Visita`,
    competitions: [
      {
        status: { type: { name: "STATUS_FINAL", completed: true } },
        competitors: [
          { homeAway: "home", score: goles[0], team: { displayName: local } },
          { homeAway: "away", score: goles[1], team: { displayName: "Visita" } },
        ],
      },
    ],
  });

  const leer = (rule: MatchRule, porDia: Record<string, EspnEvento[]>) =>
    createMatchOracle({ cargarPartidos: async (r) => porDia[r.fecha] ?? [] }).read({
      rule,
    } as unknown as OracleQuery);

  it("un partido nocturno de CDMX (03:05 UTC) se lee de la jornada anterior", async () => {
    const rule: MatchRule = {
      kind: "partido",
      liga: "mex.1",
      fecha: "2026-09-27",
      inicio: "2026-09-27T03:05:00Z",
      equipo: "América",
      resultado: "gana",
    };
    const reading = await leer(rule, {
      "2026-09-26": [evento("2026-09-27T03:05Z", "América", ["2", "0"])],
    });
    expect(reading.status).toBe("resuelto");
    if (reading.status === "resuelto") expect(reading.outcome).toBe("si");
  });

  it("con el arranque no confunde el partido de hoy con el de ayer (MLB)", async () => {
    const rule: MatchRule = {
      kind: "partido",
      liga: "mlb",
      fecha: "2026-09-26",
      inicio: "2026-09-26T23:10:00Z",
      equipo: "Yankees",
      resultado: "gana",
    };
    const reading = await leer(rule, {
      "2026-09-26": [evento("2026-09-26T23:10Z", "Yankees", ["1", "4"])],
      "2026-09-25": [evento("2026-09-25T23:10Z", "Yankees", ["9", "0"])],
    });
    expect(reading.status).toBe("resuelto");
    if (reading.status === "resuelto") expect(reading.outcome).toBe("no");
  });

  it("si el partido no aparece en ninguna de las dos jornadas, no inventa un resultado", async () => {
    const rule: MatchRule = {
      kind: "partido",
      liga: "nfl",
      fecha: "2026-09-28",
      inicio: "2026-09-28T00:20:00Z",
      equipo: "Chiefs",
      resultado: "gana",
    };
    const reading = await leer(rule, {});
    expect(reading.status).toBe("sin_dato");
  });
});
