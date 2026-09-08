import { describe, expect, it } from "vitest";
import {
  binaryPool,
  addStake,
  bettorStake,
  declareSeed,
  formatMultiplier,
  impliedProbability,
  normalizePool,
  payoutMultiplier,
  quote,
  settle,
  totalPool,
  totalSeed,
  outlook,
  MAX_FEE_BPS,
  type Bet,
  type Pool,
  type SeedMode,
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

/**
 * La semilla como subsidio (R-067, U1).
 *
 * Lo que se prueba aquí no es que la fórmula nueva dé un número bonito, sino
 * dos cosas que se pueden romper por separado y que **no se pueden separar**:
 *
 *  1. Lo que promete la cotización es lo que paga la liquidación. Si sólo se
 *     mueve `settle()`, la app muestra menos de lo que paga — y mentir en la
 *     dirección generosa sigue siendo mentir (R-023, R-044).
 *  2. Un mercado nacido en modo `"apuesta"` paga **exactamente** lo de antes.
 *     No parecido: idéntico. Es lo que sostiene que no haya que migrar nada.
 */

/** Generador reproducible. Sin `Math.random`: un fallo que no se repite no se arregla. */
function aleatorio(semilla: number): () => number {
  let estado = semilla >>> 0;
  return () => {
    estado = (estado + 0x6d2b79f5) >>> 0;
    let t = estado;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

interface Escenario {
  pool: Pool;
  bets: Bet[];
  apuesta: Bet;
}

/**
 * Un mercado cualquiera: entre 2 y 4 resultados, semilla propia por resultado,
 * unas cuantas apuestas de gente encima, y una apuesta más que es la que se
 * examina. El pozo se construye **apostando**, no escribiéndolo a mano, para
 * que sea un estado alcanzable de verdad.
 */
function escenario(rnd: () => number, seedMode: SeedMode): Escenario {
  const nResultados = 2 + Math.floor(rnd() * 3);
  const ids = Array.from({ length: nResultados }, (_, i) => `r${i}`);
  const feeBps = [0, 100, 300, 500][Math.floor(rnd() * 4)];

  const semilla: Record<string, number> = {};
  for (const id of ids) semilla[id] = Math.floor(rnd() * 500);
  let pool = declareSeed({ outcomes: { ...semilla }, feeBps }, seedMode);

  const bets: Bet[] = [];
  const nApuestas = Math.floor(rnd() * 7);
  for (let i = 0; i < nApuestas; i += 1) {
    const side = ids[Math.floor(rnd() * ids.length)];
    const stake = 1 + Math.floor(rnd() * 900);
    bets.push({ id: `b${i}`, side, stake });
    pool = addStake(pool, side, stake);
  }

  const side = ids[Math.floor(rnd() * ids.length)];
  const stake = 1 + Math.floor(rnd() * 900);
  return { pool, bets, apuesta: { id: "examinada", side, stake } };
}

describe("La semilla como subsidio (R-067)", () => {
  it("propiedad: lo que promete la cotización es lo que paga la liquidación", () => {
    const rnd = aleatorio(20260908);
    for (const seedMode of ["apuesta", "subsidio"] as SeedMode[]) {
      for (let caso = 0; caso < 400; caso += 1) {
        const { pool, bets, apuesta } = escenario(rnd, seedMode);

        // lo que se le enseña al usuario ANTES de confirmar
        const cotizado = quote(pool, apuesta.side, apuesta.stake);

        // y lo que cobra cuando su lado gana
        const despues = addStake(pool, apuesta.side, apuesta.stake);
        const reparto = settle(despues, [...bets, apuesta], apuesta.side);

        expect(reparto.payouts[apuesta.id]).toBeCloseTo(cotizado.toWin, 6);
      }
    }
  });

  it("el reparto nunca entrega más colateral del que hay en el pozo", () => {
    const rnd = aleatorio(777);
    for (const seedMode of ["apuesta", "subsidio"] as SeedMode[]) {
      for (let caso = 0; caso < 200; caso += 1) {
        const { pool, bets, apuesta } = escenario(rnd, seedMode);
        const despues = addStake(pool, apuesta.side, apuesta.stake);
        const todas = [...bets, apuesta];
        const reparto = settle(despues, todas, apuesta.side);
        const repartido = Object.values(reparto.payouts).reduce((s, v) => s + v, 0);
        // pagos + comisión ≤ colateral. Con subsidio se reparte el pozo entero;
        // en modo "apuesta" sobra justo la parte de la semilla ganadora (L5)
        expect(repartido + reparto.fee).toBeLessThanOrEqual(totalPool(despues) + 1e-6);
      }
    }
  });

  it("un mercado en modo apuesta paga exactamente lo que pagaba antes de que el campo existiera", () => {
    const rnd = aleatorio(31415);
    for (let caso = 0; caso < 200; caso += 1) {
      const { pool, bets, apuesta } = escenario(rnd, "apuesta");
      // el mismo pozo tal como se escribía antes: sin semilla y sin modo
      const comoAntes: Pool = { outcomes: { ...pool.outcomes }, feeBps: pool.feeBps };

      expect(payoutMultiplier(pool, apuesta.side, apuesta.stake)).toBe(
        payoutMultiplier(comoAntes, apuesta.side, apuesta.stake),
      );
      const todas = [...bets, apuesta];
      const conCampo = settle(addStake(pool, apuesta.side, apuesta.stake), todas, apuesta.side);
      const sinCampo = settle(addStake(comoAntes, apuesta.side, apuesta.stake), todas, apuesta.side);
      // idénticos, no parecidos: es lo que sostiene que no haya que migrar nada
      expect(conCampo).toEqual(sinCampo);
    }
  });

  it("con subsidio el multiplicador sube, y sube exactamente lo que la semilla deja de cobrar", () => {
    const base = declareSeed(binaryPool(400, 400, 0), "apuesta");
    const conSubsidio = declareSeed(binaryPool(400, 400, 0), "subsidio");

    // 100 de un usuario contra un pozo de 400/400 sembrado entero por la casa
    const apostado = addStake(base, "si", 100);
    const apostadoSub = addStake(conSubsidio, "si", 100);

    // modo apuesta: 900 repartidos entre 500 del lado "si" ⇒ 1.8× por unidad
    expect(payoutMultiplier(base, "si", 100)).toBeCloseTo(900 / 500, 9);
    // subsidio: el mismo pozo de 900, pero sólo cobran los 100 del usuario ⇒ 9×
    expect(payoutMultiplier(conSubsidio, "si", 100)).toBeCloseTo(900 / 100, 9);

    expect(settle(apostado, [{ id: "u", side: "si", stake: 100 }], "si").payouts.u).toBeCloseTo(180, 9);
    expect(settle(apostadoSub, [{ id: "u", side: "si", stake: 100 }], "si").payouts.u).toBeCloseTo(900, 9);
  });

  it("si del lado ganador sólo queda semilla, se devuelve todo y la casa no cobra", () => {
    // la casa sembró los dos lados; el único usuario apostó al lado que pierde
    const pool = addStake(declareSeed(binaryPool(300, 300, 300), "subsidio"), "no", 200);
    const bets: Bet[] = [{ id: "u", side: "no", stake: 200 }];

    const reparto = settle(pool, bets, "si");
    expect(reparto.fee).toBe(0); // R-024: la casa no cobra de un mercado que nadie ganó
    expect(reparto.payouts.u).toBe(200); // le vuelve lo suyo, íntegro
    // y el subsidio que nadie reclamó se queda en el pozo, camino a tesorería
    expect(totalPool(pool) - reparto.distributed).toBe(600);
  });

  it("el modo sobrevive a releer el pozo, y un pozo viejo no gana semilla al pasar por ahí", () => {
    const conSubsidio = declareSeed(binaryPool(300, 200, 300), "subsidio");
    const releido = normalizePool(JSON.parse(JSON.stringify(conSubsidio)));
    expect(releido.seedMode).toBe("subsidio");
    expect(releido.seed).toEqual({ si: 300, no: 200 });
    // idempotente: releer lo que acabamos de escribir no lo vuelve a tocar
    expect(normalizePool(releido)).toEqual(releido);

    // el formato viejo de producción: sin semilla, y sigue sin ella
    const viejo = normalizePool({ si: 300, no: 200, feeBps: 300 });
    expect(viejo.seed).toBeUndefined();
    expect(viejo.seedMode).toBeUndefined();
    expect(bettorStake(viejo, "si")).toBe(300);
  });

  it("la semilla del catálogo está declarada, y estos mercados no se migran", () => {
    for (const seed of OWN_MARKETS) {
      // sin semilla declarada no hay presupuesto que sumar (L9)
      expect(totalSeed(seed.pool)).toBeGreaterThan(0);
      // nacieron cobrando y terminan cobrando: R-067 aplica a los que vengan
      expect(seed.pool.seedMode).toBe("apuesta");
    }
  });
});
