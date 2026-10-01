import { describe, expect, it, vi } from "vitest";
import {
  COHERENCIA,
  etiquetaDe,
  fechaDeEvento,
  recurrenteDe,
  recurrentesPendientes,
  SERIES_RECURRENTES,
  type EventoKalshi,
} from "@/adapters/ownMarkets/recurrentes";
import { probabilidadKalshi, SPREAD_MAXIMO } from "@/adapters/ownMarkets/espejos";
import { OUTCOME_LABEL_MAX, validateSeed } from "@/adapters/ownMarkets/catalog";
import { rankedOutcomes } from "@/domain/parimutuel";
import type { MirrorRule } from "@/domain/oracleRule";

/**
 * Espejos recurrentes (Netflix, Billboard, Spotify, YouTube). Los libros de
 * prueba copian la forma de los medidos contra Kalshi el 2026-10-01.
 */

const AHORA = Date.parse("2026-10-01T12:00:00Z");
const NETFLIX = SERIES_RECURRENTES.find((s) => s.clave === "netflix-serie")!;

const mercado = (ticker: string, nombre: string, bid: string, ask: string, cierre = "2026-10-06T03:59:00Z") => ({
  ticker,
  status: "active",
  result: "",
  yes_sub_title: nombre,
  yes_bid_dollars: bid,
  yes_ask_dollars: ask,
  close_time: cierre,
});

function evento(
  sufijo: string,
  mercados: NonNullable<EventoKalshi["markets"]>,
  serie = "KXNETFLIXRANKSHOWGLOBAL",
): EventoKalshi {
  return { event_ticker: `${serie}-${sufijo}`, mutually_exclusive: true, markets: mercados };
}

const E = "KXNETFLIXRANKSHOWGLOBAL-26OCT05";
const SANO = evento("26OCT05", [
  mercado(`${E}-MON`, "Monster: The Lizzie Borden Story: Season 1", "0.55", "0.57"),
  mercado(`${E}-WED`, "Wednesday: Season 3", "0.27", "0.29"),
  mercado(`${E}-SQU`, "Squid Game: Season 4", "0.09", "0.11"),
  mercado(`${E}-ADI`, "A Different World: Season 1", "0.02", "0.04"),
  mercado(`${E}-WON`, "Wonka's The Golden Ticket: Season 1", "0.00", "0.01"),
]);

describe("Precio de Kalshi — sólo de un libro con gente adentro", () => {
  it("un libro vacío (0.01/0.99) no es un 50 %: no hay precio", () => {
    expect(probabilidadKalshi({ ticker: "x", status: "active", yes_bid_dollars: "0.01", yes_ask_dollars: "0.99" })).toBeUndefined();
  });
  it("0.00/0.01 sí dice algo: medio centavo", () => {
    expect(probabilidadKalshi({ ticker: "x", status: "active", yes_bid_dollars: "0.00", yes_ask_dollars: "0.01" })).toBeCloseTo(0.005);
  });
  it("un libro estrecho da su punto medio", () => {
    expect(probabilidadKalshi({ ticker: "x", status: "active", yes_bid_dollars: "0.56", yes_ask_dollars: "0.58" })).toBeCloseTo(0.57);
  });
  it("el último precio operado no sustituye a un libro vacío: puede ser de hace semanas", () => {
    expect(
      probabilidadKalshi({ ticker: "x", status: "active", yes_bid_dollars: "0", yes_ask_dollars: "0.90", last_price_dollars: "0.40" }),
    ).toBeUndefined();
    expect(SPREAD_MAXIMO).toBeLessThanOrEqual(0.1);
  });
});

describe("Recurrentes — la semilla", () => {
  it("un libro sano crea el espejo: tres con nombre más «Otra», cierre una hora antes que Kalshi", () => {
    const r = recurrenteDe(NETFLIX, SANO, AHORA);
    expect("seed" in r).toBe(true);
    if (!("seed" in r)) return;
    const seed = validateSeed(r.seed);
    expect(seed.id).toBe("k-netflix-serie-26oct05");
    expect(seed.outcomes!.map((o) => o.label)).toEqual([
      "Monster: The Lizzie Borde…",
      "Wednesday",
      "Squid Game",
      "Otra serie",
    ]);
    expect(seed.closesAt).toBe("2026-10-06T02:59:00.000Z");
    // el nombre entero, sin recortar, está en el criterio con su ticker
    expect(seed.resolution.criterion).toMatch(/«Monster: The Lizzie Borden Story: Season 1».*KXNETFLIXRANKSHOWGLOBAL-26OCT05-MON/);
    const [lider] = rankedOutcomes(seed.pool, seed.outcomes!);
    expect(lider.id).toBe("r1");
    expect((seed.rule as MirrorRule).respuestas.at(-1)).toEqual({ id: "otra", tickers: [] });
  });

  it("libro incoherente: si los excluyentes suman 0.35, no se infla al primero hasta 60 %", () => {
    const raro = evento("26OCT05", [
      mercado(`${E}-MON`, "Monster", "0.19", "0.21"),
      mercado(`${E}-ADI`, "A Different World", "0.00", "0.06"),
      mercado(`${E}-WON`, "Wonka", "0.00", "0.03"),
    ]);
    const r = recurrenteDe(NETFLIX, raro, AHORA);
    expect(r).toMatchObject({ motivo: expect.stringMatching(/incoherente/) });
    expect(COHERENCIA).toBeLessThanOrEqual(0.2);
  });

  it("un contendiente sin precio de verdad (0.00/0.90) no se esconde en «Otra»", () => {
    const e = "KXTOPSONG-26OCT10";
    const billboard = evento(
      "26OCT10",
      [
        mercado(`${e}-PAT`, "Patient Zero", "0.96", "0.99"),
        mercado(`${e}-CLE`, "Cleveland!", "0.00", "0.90"),
      ],
      "KXTOPSONG",
    );
    const serie = SERIES_RECURRENTES.find((s) => s.clave === "hot100")!;
    expect(recurrenteDe(serie, billboard, AHORA)).toMatchObject({ motivo: expect.stringMatching(/contendiente/) });
  });

  it("ni lo que cierra en menos de dos horas, ni lo que cierra en más de ocho días", () => {
    const pronto = evento("26OCT05", SANO.markets!.map((m) => ({ ...m, close_time: "2026-10-01T14:30:00Z" })));
    expect(recurrenteDe(NETFLIX, pronto, AHORA)).toMatchObject({ motivo: expect.stringMatching(/pronto/) });
    const lejos = evento("26OCT05", SANO.markets!.map((m) => ({ ...m, close_time: "2026-10-20T03:59:00Z" })));
    expect(recurrenteDe(NETFLIX, lejos, AHORA)).toMatchObject({ motivo: expect.stringMatching(/lejos/) });
  });

  it("las etiquetas caben y la fecha sale del ticker", () => {
    expect(etiquetaDe("Wednesday: Season 3")).toBe("Wednesday");
    expect(etiquetaDe("x".repeat(40)).length).toBe(OUTCOME_LABEL_MAX);
    expect(fechaDeEvento("KXTOPSONG-26OCT10")).toBe("2026-10-10");
    expect(fechaDeEvento("KXTOPSONG-26OCT10B")).toBeUndefined();
  });

  it("cada serie tiene títulos cortos que caben con cualquier fecha", () => {
    for (const serie of SERIES_RECURRENTES) {
      expect(serie.shortTitle("30 sep.").length, serie.clave).toBeLessThanOrEqual(32);
    }
  });
});

describe("Recurrentes — cuándo se le pregunta a Kalshi", () => {
  it("una serie con un recurrente abierto no se vuelve a pedir", async () => {
    const cargarSerie = vi.fn(async () => [SANO]);
    const r = await recurrentesPendientes({
      ahora: AHORA,
      existentes: new Set(["k-netflix-serie-26oct05"]),
      abiertos: new Set(["k-netflix-serie-26oct05"]),
      cargarSerie,
      series: [NETFLIX],
      pausaMs: 0,
    });
    expect(cargarSerie).not.toHaveBeenCalled();
    expect(r.seeds).toEqual([]);
  });

  it("elige el evento que cierra primero por fecha real, no por orden alfabético", async () => {
    const abril = evento("27APR05", SANO.markets!.map((m) => ({ ...m, ticker: m.ticker.replace("26OCT05", "27APR05") })));
    const r = await recurrentesPendientes({
      ahora: AHORA,
      existentes: new Set(),
      cargarSerie: async () => [abril, SANO],
      series: [NETFLIX],
      pausaMs: 0,
    });
    expect(r.seeds.map((s) => s.id)).toEqual(["k-netflix-serie-26oct05"]);
  });

  it("una serie caída queda en errores y no tapa a las demás", async () => {
    const hot100 = SERIES_RECURRENTES.find((s) => s.clave === "hot100")!;
    const r = await recurrentesPendientes({
      ahora: AHORA,
      existentes: new Set(),
      cargarSerie: async (serie) => {
        if (serie === "KXTOPSONG") throw new Error("Kalshi respondió 429");
        return [SANO];
      },
      series: [hot100, NETFLIX],
      pausaMs: 0,
    });
    expect(r.errores.join()).toMatch(/hot100.*429/);
    expect(r.seeds.map((s) => s.id)).toEqual(["k-netflix-serie-26oct05"]);
  });
});
