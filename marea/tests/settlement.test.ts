import { describe, expect, it } from "vitest";
import {
  authorizePayout,
  dispute,
  initialState,
  isPayable,
  needsAttention,
  onClose,
  onRead,
  pay,
  readWithOracles,
  resolveByHand,
  type Oracle,
  type SettlementState,
} from "@/domain/settlement";
import type { ResolutionSpec } from "@/domain/resolution";
import { createPriceOracle, createInstitutionalOracle } from "@/adapters/oracles/priceOracle";
import { ruleProblems, type PriceRule } from "@/domain/oracleRule";
import {
  addStake,
  payoutMultiplier,
  settle as settleParimutuel,
  type Bet,
  type Pool,
} from "@/domain/parimutuel";
import {
  rollingSeeds,
  proximoCierreSemanal,
  partidosSeeds,
} from "@/adapters/ownMarkets/templates";
import { createMatchOracle, type EspnEvento } from "@/adapters/oracles/matchOracle";
import { activeSeeds, openSeeds, OWN_MARKETS } from "@/adapters/ownMarkets/catalog";

const DIA = 86_400_000;
const AHORA = Date.parse("2026-08-03T06:00:00Z");

const spec: ResolutionSpec = {
  sourceName: "Kraken (velas diarias públicas)",
  sourceUrl: "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440",
  criterion:
    "Se resuelve Sí si la vela diaria de BTC/USD en Kraken del domingo cierra por encima de 71,000 dólares.",
  settlesAt: "2026-08-02T23:59:00Z",
  disputeWindowHours: 12,
};

const rule: PriceRule = {
  kind: "precio",
  par: "BTC/USD",
  umbral: 71_000,
  comparacion: "arriba",
  modo: "cierre",
};

/** Velas falsas: la del domingo cierra en 72,500. */
const velas = [
  { inicio: Date.parse("2026-08-01T00:00:00Z"), alto: 70_500, bajo: 68_000, cierre: 70_100 },
  { inicio: Date.parse("2026-08-02T00:00:00Z"), alto: 73_000, bajo: 69_900, cierre: 72_500 },
];

function oracleDePrueba(candles = velas): Oracle {
  return createPriceOracle({ loadCandles: async () => candles });
}

describe("liquidación automática", () => {
  it("V25 lee la fuente, abre disputa y paga sólo cuando la ventana cierra", async () => {
    let state = onClose(initialState("btc"));
    expect(state.phase).toBe("cerrado");

    const { reading, oracleId } = await readWithOracles([oracleDePrueba()], {
      marketId: "btc",
      spec,
      rule,
      now: AHORA,
    });
    expect(oracleId).toBe("kraken-ohlc");
    expect(reading.status).toBe("resuelto");

    state = onRead(state, reading, spec, AHORA);
    expect(state.phase).toBe("en_disputa");
    expect(state.outcome).toBe("si");
    // la evidencia dice qué se leyó, no sólo el veredicto
    expect(state.evidence).toContain("72,500");

    // dentro de la ventana no se paga aunque el resultado ya se conozca
    expect(isPayable(state, AHORA)).toBe(false);
    expect(() => pay(state, { si: 100, no: 100, feeBps: 300 }, [], AHORA)).toThrow();

    const despues = AHORA + 13 * 3_600_000;
    expect(isPayable(state, despues)).toBe(true);
    state = authorizePayout(state, despues);
    expect(state.phase).toBe("pagado");
    expect(state.paidAt).toBeTruthy();
  });

  it("V26 reparte el pozo entre los que acertaron", async () => {
    const pool: Pool = { si: 600, no: 400, feeBps: 300 };
    const bets: Bet[] = [
      { id: "a", side: "si", stake: 300 },
      { id: "b", side: "si", stake: 300 },
      { id: "c", side: "no", stake: 400 },
    ];
    let state = onClose(initialState("btc"));
    const { reading } = await readWithOracles([oracleDePrueba()], {
      marketId: "btc",
      spec,
      rule,
      now: AHORA,
    });
    state = onRead(state, reading, spec, AHORA);

    const { settlement, state: pagado } = pay(state, pool, bets, AHORA + DIA);
    expect(pagado.phase).toBe("pagado");
    expect(settlement.payouts.c).toBe(0);
    // 1000 menos 3 % de comisión, a partes iguales entre dos apuestas iguales
    expect(settlement.payouts.a).toBeCloseTo(485, 5);
    expect(settlement.payouts.b).toBeCloseTo(485, 5);
  });

  it("V45 lo que reparte la liquidación es exactamente lo que prometió el multiplicador", () => {
    // el defecto que esto cierra: `settle` repartía sólo entre las apuestas de
    // usuarios e ignoraba la semilla, así que pagaba 10× lo que la pantalla
    // había prometido antes de entrar (R-044)
    const inicial: Pool = { si: 500, no: 500, feeBps: 300 };
    const stake = 100;
    const prometido = payoutMultiplier(inicial, "si", stake) * stake;

    const pool = addStake(inicial, "si", stake);
    const { payouts } = settleParimutuel(pool, [{ id: "a", side: "si", stake }], "si");
    expect(payouts.a).toBeCloseTo(prometido, 9);
  });

  it("V27 lo que no se puede leer por programa espera a una persona, no se inventa", async () => {
    const institucional: ResolutionSpec = {
      ...spec,
      sourceName: "INEGI",
      sourceUrl: "https://www.inegi.org.mx/temas/inpc/",
      criterion:
        "Se resuelve Sí si el INPC anual que publica el INEGI es menor a 4.00%, según el comunicado oficial.",
    };
    const { reading } = await readWithOracles(
      [oracleDePrueba(), createInstitutionalOracle()],
      { marketId: "mx", spec: institucional, now: AHORA },
    );
    expect(reading.status).toBe("requiere_humano");

    let state = onRead(onClose(initialState("mx")), reading, institucional, AHORA);
    expect(state.phase).toBe("atorado");
    expect(state.outcome).toBeUndefined();
    expect(needsAttention([state])).toHaveLength(1);

    // una persona lo confirma y el ciclo sigue, con la disputa abierta
    state = resolveByHand(state, "no", "INPC anual de 4.21 %", institucional, AHORA);
    expect(state.phase).toBe("en_disputa");
    expect(state.evidence).toContain("Confirmado a mano");
    expect(isPayable(state, AHORA)).toBe(false);
  });

  it("V28 una caída de la fuente no resuelve nada: se reintenta", async () => {
    const caido: Oracle = {
      id: "caido",
      handles: () => true,
      read: async () => {
        throw new Error("timeout");
      },
    };
    const { reading } = await readWithOracles([caido], {
      marketId: "btc",
      spec,
      rule,
      now: AHORA,
    });
    expect(reading.status).toBe("sin_dato");

    const state = onRead(onClose(initialState("btc")), reading, spec, AHORA);
    expect(state.phase).toBe("cerrado");
    expect(state.outcome).toBeUndefined();
  });

  it("V29 un mercado de toque resuelve en cuanto el precio llega, sin esperar al vencimiento", async () => {
    const toque: PriceRule = {
      kind: "precio",
      par: "BTC/USD",
      umbral: 72_000,
      comparacion: "arriba",
      modo: "toca",
      desde: "2026-08-01T00:00:00Z",
    };
    const specToque: ResolutionSpec = {
      ...spec,
      settlesAt: "2026-09-01T00:00:00Z",
      criterion:
        "Se resuelve Sí si BTC/USD alcanza 72,000 dólares en cualquier momento antes del 1 de septiembre.",
    };

    const { reading } = await readWithOracles([oracleDePrueba()], {
      marketId: "btc-toca",
      spec: specToque,
      rule: toque,
      now: AHORA,
    });
    expect(reading.status).toBe("resuelto");
    if (reading.status === "resuelto") expect(reading.outcome).toBe("si");

    // resolver estando abierto cierra el mercado: ya no se puede apostar
    const state = onRead(initialState("btc-toca"), reading, specToque, AHORA);
    expect(state.phase).toBe("en_disputa");
  });

  it("V30 un mercado de toque que no llegó sigue abierto, no resuelve que no", async () => {
    const toque: PriceRule = {
      kind: "precio",
      par: "BTC/USD",
      umbral: 90_000,
      comparacion: "arriba",
      modo: "toca",
      desde: "2026-08-01T00:00:00Z",
    };
    const { reading } = await readWithOracles([oracleDePrueba()], {
      marketId: "btc-toca",
      spec: { ...spec, settlesAt: "2026-09-01T00:00:00Z" },
      rule: toque,
      now: AHORA,
    });
    expect(reading.status).toBe("sin_dato");
  });

  it("una disputa detiene el pago y marca el mercado para revisión", () => {
    const state: SettlementState = {
      marketId: "btc",
      phase: "en_disputa",
      outcome: "si",
      disputeUntil: new Date(AHORA - 1000).toISOString(),
    };
    expect(isPayable(state, AHORA)).toBe(true);
    const disputado = dispute(state, "la fuente publicó una corrección");
    expect(disputado.phase).toBe("atorado");
    expect(isPayable(disputado, AHORA)).toBe(false);
  });
});

describe("catálogo que se repone solo", () => {
  it("V31 genera mercados con umbrales redondos a partir del precio de hoy", () => {
    const seeds = rollingSeeds({
      spot: { "BTC/USD": 63_659, "ETH/USD": 1_886.5 },
      now: AHORA,
    });
    expect(seeds).toHaveLength(4);

    const cierre = seeds.find((seed) => seed.id.startsWith("btc-cierre"));
    expect(cierre?.title).toContain("64,000");
    // el umbral de la regla y el del texto publicado dicen lo mismo
    expect(ruleProblems(cierre!.rule!, cierre!.resolution.criterion)).toEqual([]);
    // las apuestas cierran antes de que el resultado sea observable (R-043)
    expect(new Date(cierre!.closesAt).getTime()).toBeLessThan(
      new Date(cierre!.resolution.settlesAt).getTime(),
    );
  });

  it("V32 sin precio no inventa umbral: genera un mercado menos", () => {
    const seeds = rollingSeeds({ spot: { "BTC/USD": 63_659 }, now: AHORA });
    expect(seeds.every((seed) => seed.id.startsWith("btc"))).toBe(true);
    expect(rollingSeeds({ spot: {}, now: AHORA })).toEqual([]);
  });

  it("V33 correr el generador dos veces el mismo día no duplica mercados", () => {
    const spot = { "BTC/USD": 63_659, "ETH/USD": 1_886.5 };
    const a = rollingSeeds({ spot, now: AHORA });
    const b = rollingSeeds({ spot, now: AHORA + 3_600_000 });
    expect(b.map((seed) => seed.id)).toEqual(a.map((seed) => seed.id));
  });

  it("V34 un mercado vencido sale del feed", () => {
    const futuro = Date.parse("2027-01-01T00:00:00Z");
    expect(activeSeeds(futuro, OWN_MARKETS)).toEqual([]);
    expect(openSeeds(AHORA, OWN_MARKETS).length).toBeGreaterThan(0);
    // ninguno del catálogo estático está vencido al día de hoy
    expect(activeSeeds(Date.now(), OWN_MARKETS).length).toBe(OWN_MARKETS.length);
  });

  it("el cierre semanal cae siempre en domingo", () => {
    for (let dia = 0; dia < 14; dia += 1) {
      const cierre = new Date(proximoCierreSemanal(AHORA + dia * DIA));
      expect(cierre.getUTCDay()).toBe(0);
      expect(cierre.getTime()).toBeGreaterThan(AHORA + dia * DIA);
    }
  });
});

describe("futbol, que es lo que sí se comparte", () => {
  const partido: EspnEvento = {
    date: "2026-08-02T23:00Z",
    name: "Santos at América",
    competitions: [
      {
        status: { type: { name: "STATUS_FULL_TIME", completed: true } },
        competitors: [
          { homeAway: "home", score: "2", team: { displayName: "América" } },
          { homeAway: "away", score: "1", team: { displayName: "Santos" } },
        ],
      },
    ],
  };

  const specPartido = {
    sourceName: "ESPN (marcador oficial de la Liga MX)",
    sourceUrl: "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard",
    criterion:
      "Se resuelve Sí si América le gana a Santos en el partido del 2026-08-02, según el marcador final que publica ESPN. Un empate resuelve No.",
    settlesAt: "2026-08-03T02:00:00Z",
    disputeWindowHours: 12,
  };

  const regla = {
    kind: "partido" as const,
    liga: "mex.1" as const,
    fecha: "2026-08-02",
    equipo: "América",
    resultado: "gana" as const,
  };

  it("V58 un partido de Liga MX se resuelve solo con el marcador público", async () => {
    const oracle = createMatchOracle({ cargarPartidos: async () => [partido] });
    const { reading } = await readWithOracles([oracle], {
      marketId: "mx-america",
      spec: specPartido,
      rule: regla,
      now: Date.parse("2026-08-03T03:00:00Z"),
    });
    expect(reading.status).toBe("resuelto");
    if (reading.status === "resuelto") expect(reading.outcome).toBe("si");
    expect(reading.evidence).toContain("2 - 1");
  });

  it("V59 un partido en curso no resuelve: un marcador a medio tiempo no es resultado", async () => {
    const enJuego: EspnEvento = {
      ...partido,
      competitions: [
        {
          status: { type: { name: "STATUS_IN_PROGRESS", completed: false } },
          competitors: partido.competitions[0].competitors,
        },
      ],
    };
    const oracle = createMatchOracle({ cargarPartidos: async () => [enJuego] });
    const { reading } = await readWithOracles([oracle], {
      marketId: "mx-america",
      spec: specPartido,
      rule: regla,
      now: Date.parse("2026-08-03T00:00:00Z"),
    });
    expect(reading.status).toBe("sin_dato");
    expect(reading.evidence).toMatch(/no ha terminado/);
  });

  it("V60 el empate resuelve No cuando la pregunta es si gana", async () => {
    const empate: EspnEvento = {
      ...partido,
      competitions: [
        {
          status: { type: { name: "STATUS_FULL_TIME", completed: true } },
          competitors: [
            { homeAway: "home", score: "1", team: { displayName: "América" } },
            { homeAway: "away", score: "1", team: { displayName: "Santos" } },
          ],
        },
      ],
    };
    const oracle = createMatchOracle({ cargarPartidos: async () => [empate] });
    const { reading } = await readWithOracles([oracle], {
      marketId: "mx-america",
      spec: specPartido,
      rule: regla,
      now: Date.parse("2026-08-03T03:00:00Z"),
    });
    if (reading.status === "resuelto") expect(reading.outcome).toBe("no");
  });

  it("V61 los mercados de la jornada se generan solos y cierran al arrancar el partido", () => {
    const ahora = Date.parse("2026-07-30T00:00:00Z");
    const seeds = partidosSeeds(
      [
        { inicio: "2026-08-02T23:00:00Z", local: "América", visitante: "Santos" },
        // uno que ya empezó no se publica: no se apuesta con el marcador a la vista
        { inicio: "2026-07-29T23:00:00Z", local: "Toluca", visitante: "Necaxa" },
      ],
      ahora,
    );
    expect(seeds).toHaveLength(1);
    expect(seeds[0].title).toBe("¿América le gana a Santos?");
    expect(seeds[0].closesAt).toBe("2026-08-02T23:00:00Z");
    expect(new Date(seeds[0].resolution.settlesAt).getTime()).toBeGreaterThan(
      new Date(seeds[0].closesAt).getTime(),
    );
  });
});
