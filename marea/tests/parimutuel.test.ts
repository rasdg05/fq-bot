import { describe, expect, it } from "vitest";
import {
  binaryPool,
  addStake,
  formatMultiplier,
  impliedProbability,
  payoutMultiplier,
  quote,
  settle,
  totalPool,
  outlook,
  MAX_FEE_BPS,
  type Bet,
  type Pool,
} from "@/domain/parimutuel";
import {
  assertPublishable,
  canPayout,
  disputeDeadline,
  publishProblems,
  resolutionSummary,
  MIN_DISPUTE_HOURS,
  UnpublishableMarket,
} from "@/domain/resolution";
import {
  apply,
  canCashOut,
  canStake,
  dailyTopUp,
  emptyLedger,
  grantWelcome,
  DAILY_GRANT,
  WELCOME_GRANT,
} from "@/domain/points";
import { OWN_MARKETS } from "@/adapters/ownMarkets/catalog";

const pool = (si: number, no: number, feeBps = 300): Pool =>
  binaryPool(si, no, feeBps);

describe("Motor parimutuel", () => {
  it("la probabilidad es la fracción del pozo, y 50 % cuando no hay pozo", () => {
    expect(impliedProbability(pool(600, 400))).toBeCloseTo(0.6, 5);
    expect(impliedProbability(pool(0, 0))).toBe(0.5);
  });

  it("el pago incluye la apuesta que se está por hacer", () => {
    // sin la apuesta, el pago se ve mejor de lo que va a ser (R-023)
    const before = payoutMultiplier(pool(500, 500), "si");
    const after = payoutMultiplier(pool(500, 500), "si", 500);
    expect(after).toBeLessThan(before);
    expect(after).toBeCloseTo((1500 * 0.97) / 1000, 5);
  });

  it("la comisión sale del pozo, nunca contra el jugador", () => {
    const q = quote(pool(500, 500, 300), "si", 100);
    // 1100 en el pozo, 3 % de comisión, 600 del lado Sí
    expect(q.fee).toBeCloseTo(33, 5);
    expect(q.multiplier).toBeCloseTo((1100 * 0.97) / 600, 5);
    expect(q.toWin).toBeCloseTo(100 * q.multiplier, 5);
  });

  it("recorta una comisión abusiva en lugar de aplicarla", () => {
    const abusive = quote(pool(500, 500, 9_000), "si", 100);
    const capped = quote(pool(500, 500, MAX_FEE_BPS), "si", 100);
    expect(abusive.multiplier).toBeCloseTo(capped.multiplier, 5);
  });

  it("apostar al lado flaco paga más", () => {
    const flaco = payoutMultiplier(pool(900, 100), "no", 10);
    const gordo = payoutMultiplier(pool(900, 100), "si", 10);
    expect(flaco).toBeGreaterThan(gordo);
    expect(gordo).toBeLessThan(1.2);
  });

  it("liquida repartiendo el pozo perdedor en proporción", () => {
    const bets: Bet[] = [
      { id: "a", side: "si", stake: 100 },
      { id: "b", side: "si", stake: 300 },
      { id: "c", side: "no", stake: 400 },
    ];
    const p = pool(400, 400, 0);
    const result = settle(p, bets, "si");
    expect(result.payouts.a).toBeCloseTo(200, 5);
    expect(result.payouts.b).toBeCloseTo(600, 5);
    expect(result.payouts.c).toBe(0);
    // nada se pierde en el camino
    expect(result.payouts.a + result.payouts.b).toBeCloseTo(totalPool(p), 5);
  });

  it("si nadie acertó, se devuelve todo y la casa no cobra", () => {
    const bets: Bet[] = [
      { id: "a", side: "no", stake: 100 },
      { id: "b", side: "no", stake: 200 },
    ];
    const result = settle(pool(0, 300, 300), bets, "si");
    expect(result.fee).toBe(0);
    expect(result.payouts.a).toBe(100);
    expect(result.payouts.b).toBe(200);
  });

  it("el pozo se mueve con cada apuesta y el siguiente ve otro precio", () => {
    let p = pool(500, 500);
    const antes = impliedProbability(p);
    p = addStake(p, "si", 500);
    expect(impliedProbability(p)).toBeGreaterThan(antes);
  });

  it("no inventa resultado a mitad de camino: da lo que cobras y lo que arriesgas", () => {
    const bet: Bet = { id: "a", side: "si", stake: 100 };
    // apostado al lado gordo: cobras poco más de lo que pusiste
    const gordo = outlook(pool(1000, 100, 0), bet);
    expect(gordo.toWin).toBeCloseTo(110, 5);
    expect(gordo.toLose).toBe(100);
    // apostado al lado flaco: cobras mucho más
    const flaco = outlook(pool(100, 1000, 0), bet);
    expect(flaco.toWin).toBeCloseTo(1100, 5);
    // lo que se arriesga es siempre lo apostado, nunca más
    expect(flaco.toLose).toBe(100);
  });

  it("formatea el pago como lo lee la gente", () => {
    expect(formatMultiplier(1.8)).toBe("1.8×");
    expect(formatMultiplier(2.05)).toBe("2.05×");
  });
});

describe("Resolución", () => {
  const valid = {
    sourceName: "INEGI",
    sourceUrl: "https://www.inegi.org.mx/temas/inpc/",
    criterion:
      "Se resuelve Sí si el INPC anual publicado el 7 de agosto es menor a 4.00%.",
    settlesAt: "2026-08-07T13:00:00Z",
    disputeWindowHours: 24,
  };

  it("acepta una especificación completa", () => {
    expect(publishProblems(valid)).toEqual([]);
    expect(assertPublishable(valid)).toBe(valid);
  });

  it("rechaza un mercado sin fuente pública verificable", () => {
    expect(publishProblems({ ...valid, sourceUrl: "" })).toContain(
      "falta la URL pública de verificación",
    );
    expect(publishProblems({ ...valid, sourceUrl: "http://inseguro.test" })).toContain(
      "la fuente tiene que ser una URL pública sobre https",
    );
  });

  it("rechaza la resolución discrecional: 'porque Marea lo dice' no existe", () => {
    const problems = publishProblems({
      ...valid,
      criterion: "Se resuelve Sí cuando Marea decide que el dato salió favorable.",
    });
    expect(problems.some((problem) => problem.includes("discrecional"))).toBe(true);
  });

  it("exige ventana de disputa mínima", () => {
    expect(publishProblems({ ...valid, disputeWindowHours: 1 })).toContain(
      `la ventana de disputa no puede bajar de ${MIN_DISPUTE_HOURS} h`,
    );
  });

  it("un mercado no publicable lanza, no advierte", () => {
    expect(() => assertPublishable({ ...valid, criterion: "" })).toThrow(
      UnpublishableMarket,
    );
  });

  it("el resumen cita la fuente y la ventana de disputa", () => {
    const summary = resolutionSummary(valid);
    expect(summary).toContain("INEGI");
    expect(summary).toContain("24 h");
  });

  it("no se paga antes de que cierre la ventana de disputa", () => {
    const until = disputeDeadline("2026-08-07T13:00:00Z", valid);
    expect(canPayout({ status: "en_disputa", outcome: "si", until }, Date.parse(until) - 1)).toBe(false);
    expect(canPayout({ status: "en_disputa", outcome: "si", until }, Date.parse(until))).toBe(true);
    expect(canPayout({ status: "abierto" })).toBe(false);
  });

  it("todo el catálogo publicado pasa la validación", () => {
    expect(OWN_MARKETS.length).toBeGreaterThan(8);
    for (const seed of OWN_MARKETS) {
      expect(publishProblems(seed.resolution), seed.id).toEqual([]);
      // la fuente es una institución concreta, no "el mercado"
      expect(seed.resolution.sourceName).not.toMatch(/^(el mercado|marea)$/i);
      expect(seed.title).toMatch(/^¿.+\?$/);
    }
  });

  it("el catálogo es de Latam de verdad, no global traducido", () => {
    const latam = OWN_MARKETS.filter((seed) => seed.country !== "LATAM");
    expect(latam.length).toBeGreaterThanOrEqual(7);
    const paises = new Set(OWN_MARKETS.map((seed) => seed.country));
    expect(paises.size).toBeGreaterThanOrEqual(5);
  });
});

describe("Puntos", () => {
  it("la bienvenida se entrega una sola vez", () => {
    const once = grantWelcome(emptyLedger());
    expect(once.balance).toBe(WELCOME_GRANT);
    expect(grantWelcome(once).balance).toBe(WELCOME_GRANT);
  });

  it("no hay crédito: el saldo nunca baja de cero", () => {
    const ledger = grantWelcome(emptyLedger());
    expect(() =>
      apply(ledger, {
        id: "x",
        amount: -(WELCOME_GRANT + 1),
        reason: "apuesta",
        at: new Date().toISOString(),
      }),
    ).toThrow(/insuficiente/i);
  });

  it("los puntos no se cambian por dinero, y está en el código", () => {
    expect(canCashOut()).toBe(false);
  });

  it("la recarga diaria es para quien se quedó sin puntos", () => {
    const rico = grantWelcome(emptyLedger());
    expect(dailyTopUp(rico)).toBe(0);

    const pobre = apply(rico, {
      id: "b",
      amount: -(WELCOME_GRANT - 20),
      reason: "apuesta",
      at: new Date().toISOString(),
    });
    expect(dailyTopUp(pobre)).toBe(DAILY_GRANT - 20);
  });

  it("no se recarga dos veces el mismo día", () => {
    const now = new Date("2026-07-27T10:00:00Z");
    let ledger = emptyLedger();
    ledger = apply(ledger, {
      id: "t",
      amount: DAILY_GRANT,
      reason: "recarga_diaria",
      at: now.toISOString(),
    });
    expect(dailyTopUp(ledger, now)).toBe(0);
  });

  it("sólo se puede apostar lo que se tiene", () => {
    const ledger = grantWelcome(emptyLedger());
    expect(canStake(ledger, WELCOME_GRANT)).toBe(true);
    expect(canStake(ledger, WELCOME_GRANT + 1)).toBe(false);
    expect(canStake(ledger, 0)).toBe(false);
  });
});
