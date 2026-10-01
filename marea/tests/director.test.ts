import { describe, expect, it } from "vitest";
import { conNombre, MAX_CON_NOMBRE, PISO_SOLIDA } from "@/domain/director";

/**
 * Opciones sólidas (R-079): más de dos respuestas cuando hay más de dos
 * opciones sólidas; lo demás a «Otra».
 */
const c = (pares: [string, number][]) => pares.map(([item, p]) => ({ item, p }));

describe("Director — opciones sólidas", () => {
  it("ofrece con nombre todas las sólidas, de mayor a menor: más de dos si las hay", () => {
    expect(conNombre(c([["b", 0.2], ["a", 0.5], ["c", 0.12], ["d", 0.06], ["e", 0.03]]))).toEqual(["a", "b", "c", "d"]);
  });

  it("nunca más de cuatro con nombre", () => {
    const muchas = c(Array.from({ length: 8 }, (_, i) => [`o${i}`, 0.12] as [string, number]));
    expect(conNombre(muchas)).toHaveLength(MAX_CON_NOMBRE);
  });

  it("una opción por debajo del piso no se ofrece con nombre: no se rellena la tarjeta", () => {
    expect(conNombre(c([["a", 0.9], ["b", PISO_SOLIDA - 0.001]]))).toEqual(["a"]);
  });

  it("si ninguna es sólida, la favorita sola, siempre que alguien la cotice", () => {
    expect(conNombre(c([["a", 0.03], ["b", 0.02]]))).toEqual(["a"]);
    expect(conNombre(c([["a", 0.005]]))).toEqual([]);
  });
});

import { rollingSeeds } from "@/adapters/ownMarkets/templates";
import { SHORT_TITLE_IDEAL } from "@/adapters/ownMarkets/catalog";

describe("Hallazgo → prueba: los títulos de las plantillas caben en la tarjeta", () => {
  it("toda plantilla de cripto, con los precios más largos de cada par", () => {
    const seeds = rollingSeeds({
      spot: { "BTC/USD": 185_000, "ETH/USD": 12_700, "SOL/USD": 1_180, "XRP/USD": 12.5, "DOGE/USD": 0.195 },
      now: Date.parse("2026-10-01T12:00:00Z"),
    });
    expect(seeds.length).toBeGreaterThan(0);
    for (const seed of seeds) expect(seed.shortTitle.length, seed.shortTitle).toBeLessThanOrEqual(SHORT_TITLE_IDEAL);
  });
});

import { implicitaDeMomio, pozoDesdePrior, probabilidadesDeMomios } from "@/domain/director";
import { momiosDeEspn, type EspnEvento } from "@/adapters/oracles/matchOracle";
import { partidosSeeds } from "@/adapters/ownMarkets/templates";
import { rankedOutcomes } from "@/domain/parimutuel";
import { validateSeed } from "@/adapters/ownMarkets/catalog";

describe("Market maker — el prior con que nace un partido", () => {
  it("momios americanos a probabilidad implícita", () => {
    expect(implicitaDeMomio("-270")).toBeCloseTo(270 / 370);
    expect(implicitaDeMomio("+380")).toBeCloseTo(100 / 480);
    expect(implicitaDeMomio("EVEN")).toBeCloseTo(0.5);
    expect(implicitaDeMomio("OFF")).toBeUndefined();
    expect(implicitaDeMomio("-50")).toBeUndefined();
  });

  it("quita la comisión, y rechaza un libro incoherente: un prior malo es peor que ninguno", () => {
    const p = probabilidadesDeMomios({ local: "-270", visitante: "+700", empate: "+380", proveedor: "x" }, true)!;
    expect(p.local + p.visitante + (p.empate ?? 0)).toBeCloseTo(1);
    expect(p.local).toBeGreaterThan(0.65);
    // dos favoritos a -500: suman 1.67, no es un libro
    expect(probabilidadesDeMomios({ local: "-500", visitante: "-500", proveedor: "x" }, false)).toBeUndefined();
  });

  it("el pozo respeta el prior con un piso del 5 %", () => {
    const pozo = pozoDesdePrior({ a: 0.97, b: 0.03 }, 1000);
    expect(pozo.b / (pozo.a + pozo.b)).toBeGreaterThanOrEqual(0.045);
  });

  it("lee los momios de ESPN saltando las entradas nulas, con el cierre o la apertura", () => {
    const evento = {
      date: "2026-10-04T14:00Z",
      name: "x",
      competitions: [
        {
          status: { type: { name: "STATUS_SCHEDULED" } },
          competitors: [],
          odds: [
            null,
            {
              provider: { name: "DraftKings" },
              moneyline: { home: { close: { odds: "-108" } }, away: { open: { odds: "-112" } } },
            },
          ],
        },
      ],
    } as EspnEvento;
    expect(momiosDeEspn(evento)).toEqual({ local: "-108", visitante: "-112", proveedor: "DraftKings vía ESPN" });
  });

  it("un partido con momios nace con ese prior y lo dice en el criterio; sin momios, parejo", () => {
    const base = { inicio: "2026-10-04T14:00:00Z", local: "Arsenal", visitante: "West Ham United", liga: "eng.1" as const };
    const ahora = Date.parse("2026-10-01T12:00:00Z");
    const [con] = partidosSeeds([{ ...base, momios: { local: "-270", visitante: "+700", empate: "+380", proveedor: "DraftKings vía ESPN" } }], ahora);
    const valido = validateSeed(con);
    const [lider] = rankedOutcomes(valido.pool, valido.outcomes!);
    expect(lider.id).toBe("gana");
    expect(lider.probability).toBeGreaterThan(0.6);
    expect(valido.resolution.criterion).toMatch(/momios de DraftKings vía ESPN.*no intervienen en el resultado/);
    const [sin] = partidosSeeds([base], ahora);
    expect(sin.resolution.criterion).not.toMatch(/momios/);
  });
});
