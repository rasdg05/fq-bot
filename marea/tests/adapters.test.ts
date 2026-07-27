import { describe, expect, it, vi, afterEach } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { getJson } from "@/adapters/http";
import { toVenueMarket as polyToVenue, createPolymarketAdapter } from "@/adapters/venues/polymarket";
import { toVenueMarket as kalshiToVenue, createKalshiAdapter } from "@/adapters/venues/kalshi";
import { matchKeyFor, clampProbability, type VenueMarket } from "@/adapters/venues/types";
import { classifyCategory, isLatam } from "@/adapters/venues/classify";
import { buildMarkets, createAggregatedMarketDataAdapter } from "@/adapters/aggregatedMarketDataAdapter";
import { createConsensusProvider, noReadingProvider } from "@/domain/probability";
import { EDGE_MIN_PP } from "@/domain/edge";
import type { AppError } from "@/domain/types";

const fixture = (name: string) =>
  JSON.parse(readFileSync(resolve(process.cwd(), `tests/fixtures/${name}.json`), "utf8"));

/** Payloads reales, grabados de las APIs públicas de cada casa. */
const POLY = fixture("polymarket");
const KALSHI = fixture("kalshi");

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Cliente HTTP", () => {
  it("reintenta ante 5xx y termina devolviendo el dato", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      if (calls < 3) return new Response("", { status: 503 });
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    });
    await expect(getJson<{ ok: boolean }>("https://x.test/a")).resolves.toEqual({ ok: true });
    expect(calls).toBe(3);
  });

  it("no reintenta ante 4xx y normaliza a AppError sin filtrar la excepción", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      return new Response("", { status: 404 });
    });
    await expect(
      getJson("https://x.test/a", { errorCode: "E_MARKETS_FETCH_FAILED" }),
    ).rejects.toMatchObject({
      code: "E_MARKETS_FETCH_FAILED",
      user_message_es: expect.stringContaining("No pudimos cargar los mercados"),
    });
    expect(calls).toBe(1);
  });

  it("un fallo de red termina en AppError, nunca en la excepción cruda", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("Failed to fetch");
    });
    const error = (await getJson("https://x.test/a", { retries: 0 }).catch(
      (e) => e,
    )) as AppError;
    expect(error.code).toBe("E_NETWORK");
    expect(error.user_message_es).not.toContain("Failed to fetch");
  });
});

describe("Venue: Polymarket", () => {
  it("mapea un payload real al contrato de dominio", () => {
    const markets = POLY.map(polyToVenue).filter(Boolean) as VenueMarket[];
    expect(markets.length).toBeGreaterThan(0);
    for (const market of markets) {
      expect(market.venueId).toBe("polymarket");
      expect(market.probability).toBeGreaterThan(0);
      expect(market.probability).toBeLessThan(1);
      expect(market.question.length).toBeGreaterThan(3);
      expect(market.resolutionSummary.length).toBeGreaterThan(10);
      expect(market.matchKey).not.toBe("");
    }
  });

  it("usa el punto medio del libro como probabilidad", () => {
    const market = polyToVenue({
      id: "1",
      question: "¿Sube?",
      outcomes: '["Yes","No"]',
      bestBid: 0.4,
      bestAsk: 0.5,
      lastTradePrice: 0.9,
    } as never);
    expect(market?.probability).toBeCloseTo(0.45, 5);
  });

  it("descarta lo que no es binario y lo que no tiene precio", () => {
    expect(polyToVenue({ id: "1", question: "q", outcomes: '["A","B","C"]', bestBid: 0.4, bestAsk: 0.5 } as never)).toBeNull();
    expect(polyToVenue({ id: "1", question: "q", outcomes: '["Yes","No"]' } as never)).toBeNull();
  });

  it("nunca inventa criterio de resolución", () => {
    const market = polyToVenue({
      id: "1",
      question: "q",
      outcomes: '["Yes","No"]',
      bestBid: 0.4,
      bestAsk: 0.5,
    } as never);
    expect(market?.resolutionSummary).toContain("no publica su criterio");
  });

  it("pagina cuando se piden más de 100", async () => {
    const pages: string[] = [];
    vi.stubGlobal("fetch", async (url: string) => {
      pages.push(url);
      // la primera página vuelve llena (100): sólo así hay una segunda
      const full = Array.from({ length: 100 }, (_, i) => ({ ...POLY[i % POLY.length], id: `p${i}` }));
      return new Response(JSON.stringify(pages.length === 1 ? full : POLY), { status: 200 });
    });
    await createPolymarketAdapter().listMarkets({ limit: 150 });
    expect(pages).toHaveLength(2);
    expect(pages[1]).toContain("offset=100");
  });
});

describe("Venue: Kalshi", () => {
  it("mapea un payload real e incluye el strike en la pregunta", () => {
    const markets = KALSHI.map(kalshiToVenue).filter(Boolean) as VenueMarket[];
    // sin el subtítulo, toda la escalera de strikes compartiría clave
    const keys = new Set(markets.map((market) => market.matchKey));
    expect(keys.size).toBe(markets.length);
    for (const market of markets) {
      expect(market.venueId).toBe("kalshi");
      expect(market.question).toMatch(/\$|above|below|\d/);
    }
  });

  it("descarta las combinadas multipierna", () => {
    expect(
      kalshiToVenue({
        ticker: "T",
        title: "yes Philadelphia,yes Washington",
        yes_bid_dollars: "0.4",
        yes_ask_dollars: "0.5",
        mve_collection_ticker: "KXMVE-R",
      } as never),
    ).toBeNull();
  });

  it("exige libro de dos lados o volumen real", () => {
    // un solo lado no es precio
    expect(
      kalshiToVenue({ ticker: "T", title: "q", yes_bid_dollars: "0", yes_ask_dollars: "0.01" } as never),
    ).toBeNull();
    // último precio sin volumen tampoco
    expect(
      kalshiToVenue({ ticker: "T", title: "q", last_price_dollars: "0.5", volume_fp: "0" } as never),
    ).toBeNull();
    expect(
      kalshiToVenue({ ticker: "T", title: "q", last_price_dollars: "0.5", volume_fp: "12" } as never)
        ?.probability,
    ).toBeCloseTo(0.5, 5);
  });

  it("consulta una página por serie curada", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", async (url: string) => {
      urls.push(url);
      return new Response(JSON.stringify({ markets: KALSHI }), { status: 200 });
    });
    await createKalshiAdapter({ seriesTickers: ["KXBTCD", "KXCPIYOY"] }).listMarkets();
    expect(urls).toHaveLength(2);
    expect(urls.join(" ")).toContain("series_ticker=KXCPIYOY");
  });
});

describe("Normalización", () => {
  it("empareja la misma pregunta escrita distinto", () => {
    expect(matchKeyFor("Will Bitcoin close above $71,000?")).toBe(
      matchKeyFor("bitcoin close above 71000"),
    );
    expect(matchKeyFor("¿La inflación de México cierra julio abajo de 4.0%?")).toBe(
      matchKeyFor("inflacion Mexico cierra julio abajo 4 0"),
    );
  });

  it("no empareja preguntas distintas", () => {
    expect(matchKeyFor("Will BTC close above 71000?")).not.toBe(
      matchKeyFor("Will ETH close above 4500?"),
    );
  });

  it("recorta probabilidades imposibles", () => {
    expect(clampProbability(0)).toBe(0.01);
    expect(clampProbability(1)).toBe(0.99);
    expect(clampProbability(Number.NaN)).toBe(0.5);
  });

  it("clasifica por texto y cae en otros sin señal", () => {
    expect(classifyCategory("Will Bitcoin hit 100k?")).toBe("cripto");
    expect(classifyCategory("¿La inflación de México cierra abajo de 4%?")).toBe("economia");
    expect(classifyCategory("Who wins the presidential election?")).toBe("politica");
    expect(classifyCategory("asdf qwerty")).toBe("otros");
    expect(isLatam("¿El dólar cierra abajo de 19 pesos en México?")).toBe(true);
    expect(isLatam("Will the Fed cut rates?")).toBe(false);
  });
});

describe("Agregación", () => {
  const labels = new Map([
    ["polymarket", "Polymarket"],
    ["kalshi", "Kalshi"],
  ]);

  const quote = (over: Partial<VenueMarket>): VenueMarket => ({
    venueMarketId: "1",
    venueId: "polymarket",
    question: "¿Sube?",
    probability: 0.5,
    volume: 1000,
    liquidity: 1000,
    status: "open",
    category: "cripto",
    resolutionSummary: "Se resuelve con el cierre publicado.",
    matchKey: "sube",
    ...over,
  });

  it("sin lectura propia no hay Edge, por más casas que haya", () => {
    const markets = buildMarkets(
      [quote({}), quote({ venueId: "kalshi", probability: 0.7, venueMarketId: "2" })],
      noReadingProvider,
      labels,
    );
    expect(markets).toHaveLength(1);
    expect(markets[0].edge).toBeNull();
    expect(markets[0].mareaProbability).toBeUndefined();
  });

  it("con una sola casa el consenso no opina: comparar un precio consigo mismo daría cero", () => {
    const markets = buildMarkets([quote({})], createConsensusProvider(), labels);
    expect(markets[0].edge).toBeNull();
    expect(markets[0].mareaBasis).toBeUndefined();
  });

  it("con dos casas el consenso pondera por liquidez y produce Edge explicable", () => {
    const markets = buildMarkets(
      [
        quote({ probability: 0.5, liquidity: 1000 }),
        quote({ venueId: "kalshi", venueMarketId: "2", probability: 0.8, liquidity: 1000 }),
      ],
      createConsensusProvider(),
      labels,
    );
    // consenso 0.65 contra el primario 0.5 (o 0.8): supera el umbral
    expect(markets[0].mareaProbability).toBeCloseTo(0.65, 5);
    expect(Math.abs(markets[0].edge as number)).toBeGreaterThanOrEqual(EDGE_MIN_PP);
    expect(markets[0].mareaBasis).toContain("Consenso");
  });

  it("ejecuta en el venue con más liquidez y lo declara", async () => {
    const adapter = createAggregatedMarketDataAdapter({
      venues: [
        { id: "polymarket", label: "Polymarket", listMarkets: async () => [quote({ liquidity: 10 })] },
        {
          id: "kalshi",
          label: "Kalshi",
          listMarkets: async () => [
            quote({ venueId: "kalshi", venueMarketId: "2", liquidity: 9000, url: "https://kalshi.com/x" }),
          ],
        },
      ],
    });
    const markets = await adapter.listMarkets();
    expect(markets[0].venue?.label).toBe("Kalshi");
    const trade = await adapter.prepareTrade({ marketId: markets[0].id, side: "si", size: 10 });
    expect(trade.venue).toBe("Kalshi");
    expect(trade.deepLink).toBe("https://kalshi.com/x");
  });

  it("degrada con un venue caído y sólo falla si caen todos", async () => {
    const failing = {
      id: "kalshi" as const,
      label: "Kalshi",
      listMarkets: async () => {
        throw new Error("502");
      },
    };
    const working = {
      id: "polymarket" as const,
      label: "Polymarket",
      listMarkets: async () => [quote({})],
    };

    const errors: string[] = [];
    const partial = createAggregatedMarketDataAdapter({
      venues: [working, failing],
      onVenueError: (id) => errors.push(id),
    });
    await expect(partial.listMarkets()).resolves.toHaveLength(1);
    expect(errors).toEqual(["kalshi"]);

    const total = createAggregatedMarketDataAdapter({ venues: [failing] });
    await expect(total.listMarkets()).rejects.toMatchObject({
      code: "E_MARKETS_FETCH_FAILED",
    });
  });
});
