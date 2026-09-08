import { describe, expect, it } from "vitest";
import {
  addStake,
  declareSeed,
  settle,
  totalPool,
  type Bet,
  type Pool,
  type SeedMode,
} from "@/domain/parimutuel";
import { auditar, exposicionNeta, PozoInconsistente } from "@/domain/pozo";
import { asignacionDe, compensar, TESORERIA, type Reparto } from "@/domain/compensacion";

/**
 * El puente entre el precio y la cámara. Lo que se prueba no es que el
 * compensador sepa sumar, sino que **el camino por el que se mueve el dinero
 * sea el mismo** que el que calcula el reparto, y que un reparto imposible se
 * detenga al escribir en vez de acreditarse y descuadrar después.
 */

function prng(semilla: number): () => number {
  let s = (Math.imul(semilla ^ 0x9e37_79b9, 0x85eb_ca6b) >>> 0) || 1;
  const siguiente = (): number => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 0x1_0000_0000;
  };
  // se descartan las primeras salidas: un LCG recién sembrado devuelve valores
  // correlacionados, y la primera decisión aquí es cuántos resultados hay
  for (let i = 0; i < 8; i += 1) siguiente();
  return siguiente;
}

interface Mercado {
  pool: Pool;
  bets: Bet[];
  ids: string[];
}

function mercado(rnd: () => number, seedMode: SeedMode): Mercado {
  const ids = Array.from({ length: 2 + Math.floor(rnd() * 3) }, (_, i) => `r${i}`);
  const feeBps = [0, 100, 300, 500][Math.floor(rnd() * 4)];
  const semilla: Record<string, number> = {};
  for (const id of ids) semilla[id] = Math.floor(rnd() * 400);

  let pool = declareSeed({ outcomes: { ...semilla }, feeBps }, seedMode);
  const bets: Bet[] = [];
  for (let i = 0; i < Math.floor(rnd() * 8); i += 1) {
    const side = ids[Math.floor(rnd() * ids.length)];
    const stake = 1 + Math.floor(rnd() * 900);
    bets.push({ id: `b${i}`, side, stake });
    pool = addStake(pool, side, stake);
  }
  return { pool, bets, ids };
}

function repartos(pool: Pool, bets: Bet[], ids: string[]): Record<string, Reparto> {
  const salida: Record<string, Reparto> = {};
  for (const id of ids) salida[id] = settle(pool, bets, id);
  return salida;
}

/** Los pagos sin los ceros: `liquidar` no emite tenedores con cero contratos. */
function sinCeros(pagos: Record<string, number>): Record<string, number> {
  return Object.fromEntries(Object.entries(pagos).filter(([, v]) => v !== 0));
}

describe("Compensador — el reparto se mueve por la cámara", () => {
  it("propiedad: lo que acredita el compensador es lo que produjo el reparto, y sale todo el colateral", () => {
    const rnd = prng(20260908);
    for (const seedMode of ["apuesta", "subsidio"] as SeedMode[]) {
      for (let caso = 0; caso < 300; caso += 1) {
        const { pool, bets, ids } = mercado(rnd, seedMode);
        const porResultado = repartos(pool, bets, ids);
        const colateral = totalPool(pool);

        for (const ganador of ids) {
          const c = compensar({
            marketId: `m${caso}`,
            outcomes: ids,
            colateral,
            repartoPorResultado: porResultado,
            ganador,
          });

          // 1. lo que se acredita es exactamente lo que dijo `settle`
          expect(sinCeros(c.pagosDeApuestas)).toEqual(sinCeros(porResultado[ganador].payouts));

          // 2. sale del pozo exactamente el colateral que retenía, con
          //    cualquier ganador. Ésa es toda la neutralidad (L1, L5)
          expect(c.pagado).toBeCloseTo(colateral, 6);

          // 3. y no se queda nada sin dueño: pagos + casa == colateral
          const aApuestas = Object.values(c.pagosDeApuestas).reduce((s, v) => s + v, 0);
          expect(aApuestas + c.aTesoreria).toBeCloseTo(colateral, 6);
        }
      }
    }
  });

  it("la exposición neta del pozo es cero en TODOS los resultados, no sólo en el que salió", () => {
    const rnd = prng(4242);
    for (let caso = 0; caso < 100; caso += 1) {
      const { pool, bets, ids } = mercado(rnd, "subsidio");
      const c = compensar({
        marketId: `m${caso}`,
        outcomes: ids,
        colateral: totalPool(pool),
        repartoPorResultado: repartos(pool, bets, ids),
        ganador: ids[0],
      });
      // el pozo queda vacío tras quemar, y sano en todos los resultados
      expect(auditar(c.pozo)).toEqual([]);
      for (const id of ids) expect(exposicionNeta(c.pozo, id)).toBe(0);
    }
  });

  it("un reparto que paga más colateral del que hay no se acredita: se para", () => {
    const goloso: Reparto = { payouts: { a: 600, b: 600 }, fee: 0 };
    expect(() => asignacionDe(1000, goloso)).toThrow(PozoInconsistente);

    // y no es sólo la función suelta: la liquidación entera no ocurre
    expect(() =>
      compensar({
        marketId: "m",
        outcomes: ["si", "no"],
        colateral: 1000,
        repartoPorResultado: { si: goloso, no: { payouts: {}, fee: 0 } },
        ganador: "no", // el sobrepago está en el OTRO resultado, y aun así para
      }),
    ).toThrow(PozoInconsistente);
  });

  it("un pago negativo se rechaza al escribir, no se compensa contra otro", () => {
    expect(() => asignacionDe(1000, { payouts: { a: 1200, b: -200 }, fee: 0 })).toThrow(
      PozoInconsistente,
    );
  });

  it("falta el reparto de un resultado: no se liquida a medias", () => {
    expect(() =>
      compensar({
        marketId: "m",
        outcomes: ["si", "no", "tal_vez"],
        colateral: 300,
        repartoPorResultado: { si: { payouts: { a: 300 }, fee: 0 }, no: { payouts: {}, fee: 0 } },
        ganador: "si",
      }),
    ).toThrow(PozoInconsistente);
  });

  it("en modo apuesta, lo que sobra para la casa es la parte de la semilla ganadora", () => {
    // 400/400 de semilla, un usuario pone 100 al "si", sin comisión
    const pool = addStake(declareSeed({ outcomes: { si: 400, no: 400 }, feeBps: 0 }, "apuesta"), "si", 100);
    const bets: Bet[] = [{ id: "u", side: "si", stake: 100 }];
    const c = compensar({
      marketId: "m",
      outcomes: ["si", "no"],
      colateral: 900,
      repartoPorResultado: repartos(pool, bets, ["si", "no"]),
      ganador: "si",
    });
    // el usuario cobra 900 × 100/500 = 180; los otros 720 son de la semilla
    expect(c.pagosDeApuestas.u).toBeCloseTo(180, 9);
    expect(c.aTesoreria).toBeCloseTo(720, 9);
  });

  it("con subsidio no le sobra nada a la casa: lo que la semilla no cobra se reparte", () => {
    const pool = addStake(declareSeed({ outcomes: { si: 400, no: 400 }, feeBps: 0 }, "subsidio"), "si", 100);
    const bets: Bet[] = [{ id: "u", side: "si", stake: 100 }];
    const c = compensar({
      marketId: "m",
      outcomes: ["si", "no"],
      colateral: 900,
      repartoPorResultado: repartos(pool, bets, ["si", "no"]),
      ganador: "si",
    });
    expect(c.pagosDeApuestas.u).toBeCloseTo(900, 9);
    expect(c.aTesoreria).toBe(0); // R-067: la casa nunca cobra de lo que puso
  });

  it("la comisión aterriza en tesorería, no desaparece del reparto (R-064)", () => {
    const pool = addStake(
      addStake(declareSeed({ outcomes: { si: 0, no: 0 }, feeBps: 300 }, "apuesta"), "si", 500),
      "no",
      500,
    );
    const bets: Bet[] = [
      { id: "a", side: "si", stake: 500 },
      { id: "b", side: "no", stake: 500 },
    ];
    const c = compensar({
      marketId: "m",
      outcomes: ["si", "no"],
      colateral: 1000,
      repartoPorResultado: repartos(pool, bets, ["si", "no"]),
      ganador: "si",
    });
    expect(c.pagosDeApuestas.a).toBeCloseTo(970, 9);
    expect(c.pagos[TESORERIA]).toBeCloseTo(30, 9);
    expect(c.pagado).toBeCloseTo(1000, 9);
  });

  it("un mercado sin colateral se liquida sin repartir nada, y no es un error", () => {
    const c = compensar({
      marketId: "m",
      outcomes: ["si", "no"],
      colateral: 0,
      repartoPorResultado: { si: { payouts: {}, fee: 0 }, no: { payouts: {}, fee: 0 } },
      ganador: "si",
    });
    expect(c.pagado).toBe(0);
    expect(c.pagosDeApuestas).toEqual({});
  });
});
