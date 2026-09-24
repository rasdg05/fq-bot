import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Store } from "../server/store.mts";
import { correrCiclo } from "../server/ciclo.mts";
import { MercadosVivos } from "../server/vivos.mts";
import { crearTicker, type Ticker } from "../server/precios.mts";
import { construirMercado, listarMercados } from "../server/mercados.mts";
import {
  bloqueoDeVentana,
  cuentaRegresiva,
  deltaPp,
  finDeVentana,
  inicioDeVentana,
  pasoDeStrike,
  redondearStrike,
  BLOQUEO_MS,
} from "@/domain/vela";
import {
  ABAJO,
  ARRIBA,
  ACTIVOS_VIVOS,
  idDeVela,
  velaSeed,
  velasVigentes,
} from "@/adapters/ownMarkets/cryptoLive";
import { createVelaOracle } from "@/adapters/oracles/velaOracle";
import { publishProblems } from "@/domain/resolution";
import { MarketCard } from "@/components/MarketCard";
import type { Market } from "@/domain/types";
import type { VelaRule } from "@/domain/oracleRule";

/**
 * Cripto en vivo. Lo que se prueba aquí es lo que se rompe en producción: que
 * siempre haya un mercado abierto, que el strike no se mueva debajo de quien ya
 * apostó, que la vela se pague con el cierre que se prometió, y que la card se
 * congele cuando alguien toca una pill.
 */

const BTC = ACTIVOS_VIVOS[0];

/** Un momento cualquiera dentro de una vela de cinco minutos. */
const DENTRO = Date.parse("2026-07-29T16:37:12Z");

function tickerFalso(precios: Record<string, number>, at = DENTRO): Ticker {
  return {
    precio: (par) =>
      precios[par] !== undefined
        ? { precio: precios[par], at, fuente: "kraken" as const }
        : undefined,
    refrescar: async () => {},
    arrancar: () => {},
    detener: () => {},
    estado: () => ({
      fuente: "kraken",
      motorDegradado: false,
      ultimaLatenciaMs: null,
      pares: {},
    }),
  };
}

describe("Ventanas de vela — el reloj es el mismo para todos", () => {
  it("alinea la ventana al reloj, no al momento en que se preguntó", () => {
    expect(new Date(inicioDeVentana(DENTRO, 5)).toISOString()).toBe(
      "2026-07-29T16:35:00.000Z",
    );
    expect(new Date(inicioDeVentana(DENTRO, 15)).toISOString()).toBe(
      "2026-07-29T16:30:00.000Z",
    );
  });

  it("dos preguntas dentro de la misma vela dan la misma ventana", () => {
    const a = inicioDeVentana(Date.parse("2026-07-29T16:35:00Z"), 5);
    const b = inicioDeVentana(Date.parse("2026-07-29T16:39:59Z"), 5);
    expect(a).toBe(b);
  });

  it("las apuestas cierran antes que la vela, nunca al mismo tiempo (R-043)", () => {
    const inicio = inicioDeVentana(DENTRO, 5);
    expect(finDeVentana(inicio, 5) - bloqueoDeVentana(inicio, 5)).toBe(BLOQUEO_MS);
    expect(bloqueoDeVentana(inicio, 5)).toBeLessThan(finDeVentana(inicio, 5));
  });

  it("redondea el strike a un número que se dice en voz alta", () => {
    expect(redondearStrike(71_183, pasoDeStrike("BTC/USD"))).toBe(71_200);
    expect(redondearStrike(4_502.4, pasoDeStrike("ETH/USD"))).toBe(4_500);
  });

  it("el redondeo del strike no pasa del 0.1 % del precio", () => {
    for (const [par, precio] of [
      ["BTC/USD", 71_183],
      ["ETH/USD", 4_502],
    ] as const) {
      const strike = redondearStrike(precio, pasoDeStrike(par));
      expect(Math.abs(strike - precio) / precio).toBeLessThan(0.001);
    }
  });

  it("la variación se mide contra el strike, que es contra lo que se liquida", () => {
    expect(deltaPp(71_272, 71_200)).toBeCloseTo(0.101, 3);
    expect(deltaPp(71_128, 71_200)).toBeCloseTo(-0.101, 3);
  });

  it("la cuenta regresiva nunca se va a negativo", () => {
    expect(cuentaRegresiva(161_000)).toBe("02:41");
    expect(cuentaRegresiva(-5_000)).toBe("00:00");
  });
});

describe("Generación de velas — sin precio no hay mercado", () => {
  it("genera una vela de 5 y una de 15 por activo con precio", () => {
    const velas = velasVigentes({
      ahora: DENTRO,
      precio: (par) => ({ "BTC/USD": 71_183, "ETH/USD": 4_502 })[par],
    });
    expect(velas).toHaveLength(4);
    expect(velas.map((v) => v.intervalo).sort((a, b) => a - b)).toEqual([5, 5, 15, 15]);
  });

  it("un par sin lectura fresca genera un mercado menos, no un strike inventado", () => {
    const velas = velasVigentes({
      ahora: DENTRO,
      precio: (par) => (par === "BTC/USD" ? 71_183 : undefined),
    });
    expect(velas.every((v) => v.activo.par === "BTC/USD")).toBe(true);
    expect(velas).toHaveLength(2);
  });

  it("en los últimos diez segundos ya siembra la vela siguiente", () => {
    const inicio = inicioDeVentana(DENTRO, 5);
    const enElBloqueo = bloqueoDeVentana(inicio, 5) + 1_000;
    const velas = velasVigentes({
      ahora: enElBloqueo,
      precio: () => 71_183,
      intervalos: [5],
      activos: [BTC],
    });
    expect(velas.map((v) => v.inicio)).toEqual([inicio, finDeVentana(inicio, 5)]);
  });
});

describe("El mercado de una vela — publicable antes de existir", () => {
  const inicio = inicioDeVentana(DENTRO, 5);
  const seed = velaSeed({ activo: BTC, intervalo: 5, inicio, spot: 71_183 });

  it("pasa la puerta de publicación con su ventana de disputa viva", () => {
    expect(publishProblems(seed.resolution)).toEqual([]);
    expect(seed.resolution.liveVerification).toBe(true);
    expect(seed.resolution.disputeWindowHours * 3_600).toBeGreaterThanOrEqual(60);
  });

  it("una vela sin `liveVerification` sigue exigiendo las 12 h de siempre", () => {
    const problemas = publishProblems({
      ...seed.resolution,
      liveVerification: undefined,
    });
    expect(problemas.join(" ")).toMatch(/12 h/);
  });

  it("nombra los dos resultados con el strike, sin Sí ni No", () => {
    expect(seed.outcomes?.map((o) => o.id)).toEqual([ARRIBA, ABAJO]);
    expect(seed.outcomes?.[0].label).toBe("Arriba 71.2k");
    expect(seed.outcomes?.[1].label).toBe("Abajo 71.2k");
  });

  it("el criterio publicado dice el strike, la ventana y qué pasa con el empate", () => {
    expect(seed.resolution.criterion).toContain("71,200");
    expect(seed.resolution.criterion).toContain("16:35 UTC");
    expect(seed.resolution.criterion).toContain("16:40 UTC");
    expect(seed.resolution.criterion).toMatch(/igual al strike resuelve Abajo/i);
  });

  it("cita el endpoint de la vela que de verdad se lee, no el diario", () => {
    expect(seed.resolution.sourceUrl).toContain("interval=5");
    expect(seed.resolution.sourceUrl).toContain("XBTUSD");
  });

  it("las apuestas cierran antes de que se lea el resultado", () => {
    expect(new Date(seed.closesAt).getTime()).toBeLessThan(
      new Date(seed.resolution.settlesAt).getTime(),
    );
  });

  it("el id sale del reloj: la misma vela genera el mismo mercado", () => {
    const otra = velaSeed({ activo: BTC, intervalo: 5, inicio, spot: 71_950 });
    expect(otra.id).toBe(seed.id);
    expect(idDeVela(BTC, 5, inicio)).toBe("btc-5m-20260729T1635");
  });
});

describe("Oráculo de vela — se paga con el cierre que se prometió", () => {
  const inicio = inicioDeVentana(DENTRO, 5);
  const fin = finDeVentana(inicio, 5);
  const seed = velaSeed({ activo: BTC, intervalo: 5, inicio, spot: 71_183 });
  const rule = seed.rule as VelaRule;
  const query = (now: number) => ({
    marketId: seed.id,
    spec: seed.resolution,
    rule,
    now,
  });

  function oraculo(cierre: number, opciones: { conSiguiente?: boolean } = {}) {
    return createVelaOracle({
      cargarVelas: async () => [
        { inicio: inicio - 300_000, cierre: 71_000 },
        { inicio, cierre },
        ...(opciones.conSiguiente === false ? [] : [{ inicio: fin, cierre }]),
      ],
    });
  }

  it("no lee nada antes de que la vela cierre", async () => {
    const lectura = await oraculo(71_400).read(query(fin - 1_000));
    expect(lectura.status).toBe("sin_dato");
  });

  it("tampoco lee en los segundos de gracia: la vela sigue en curso", async () => {
    const lectura = await oraculo(71_400).read(query(fin + 5_000));
    expect(lectura.status).toBe("sin_dato");
  });

  it("resuelve Arriba con cierre por encima del strike", async () => {
    const lectura = await oraculo(71_400).read(query(fin + 60_000));
    expect(lectura.status).toBe("resuelto");
    expect(lectura).toMatchObject({ outcome: ARRIBA });
    expect(lectura.evidence).toContain("71,400");
    expect(lectura.evidence).toContain("api.kraken.com");
  });

  it("resuelve Abajo con cierre por debajo", async () => {
    const lectura = await oraculo(71_050).read(query(fin + 60_000));
    expect(lectura).toMatchObject({ status: "resuelto", outcome: ABAJO });
  });

  it("el empate exacto resuelve Abajo, como dice el criterio publicado", async () => {
    const lectura = await oraculo(71_200).read(query(fin + 60_000));
    expect(lectura).toMatchObject({ status: "resuelto", outcome: ABAJO });
  });

  it("sin la vela siguiente no da por cerrada la nuestra", async () => {
    const lectura = await oraculo(71_400, { conSiguiente: false }).read(
      query(fin + 60_000),
    );
    expect(lectura.status).toBe("sin_dato");
  });

  it("una caída de Kraken no inventa un resultado", async () => {
    const roto = createVelaOracle({
      cargarVelas: async () => {
        throw new Error("Kraken respondió 503");
      },
    });
    await expect(roto.read(query(fin + 60_000))).rejects.toThrow();
  });

  it("varios mercados del mismo par comparten una sola consulta", async () => {
    const cargar = vi.fn(async () => [
      { inicio, cierre: 71_400 },
      { inicio: fin, cierre: 71_400 },
    ]);
    const compartido = createVelaOracle({ cargarVelas: cargar });
    await compartido.read(query(fin + 60_000));
    await compartido.read(query(fin + 61_000));
    expect(cargar).toHaveBeenCalledTimes(1);
  });
});

describe("Ticker de spot — el motor primero, el respaldo cuando hace falta", () => {
  it("usa el motor FQ cuando responde a tiempo", async () => {
    const ticker = crearTicker({
      urlFq: "https://fq.example/precios",
      fetchImpl: (async () =>
        new Response(JSON.stringify({ "BTC/USD": 71_183 }))) as typeof fetch,
    });
    await ticker.refrescar();
    expect(ticker.precio("BTC/USD")).toMatchObject({ precio: 71_183, fuente: "fq" });
  });

  it("cae a Kraken si el motor falla, y lo declara", async () => {
    const fetchImpl = (async (url: string | URL) => {
      if (String(url).includes("fq.example")) throw new Error("caído");
      return new Response(JSON.stringify({ result: { XXBTZUSD: { c: ["71183.0"] } } }));
    }) as unknown as typeof fetch;

    const ticker = crearTicker({ urlFq: "https://fq.example/precios", fetchImpl });
    await ticker.refrescar();
    expect(ticker.precio("BTC/USD")).toMatchObject({ precio: 71_183, fuente: "kraken" });
    expect(ticker.estado().motorDegradado).toBe(true);
  });

  it("una lectura vieja deja de servirse: no se enseña como si fuera de ahora", async () => {
    let reloj = 1_000;
    const ticker = crearTicker({
      fetchImpl: (async () =>
        new Response(JSON.stringify({ result: { XXBTZUSD: { c: ["71183.0"] } } }))) as typeof fetch,
      now: () => reloj,
      frescuraMs: 10_000,
    });
    await ticker.refrescar();
    expect(ticker.precio("BTC/USD")?.precio).toBe(71_183);
    reloj += 30_000;
    expect(ticker.precio("BTC/USD")).toBeUndefined();
  });

  it("sin ninguna fuente no pisa la última lectura con basura", async () => {
    let falla = false;
    const ticker = crearTicker({
      fetchImpl: (async () => {
        if (falla) throw new Error("sin red");
        return new Response(JSON.stringify({ result: { XXBTZUSD: { c: ["71183.0"] } } }));
      }) as typeof fetch,
    });
    await ticker.refrescar();
    falla = true;
    await ticker.refrescar();
    expect(ticker.precio("BTC/USD")?.precio).toBe(71_183);
  });
});

describe("Planificador — siempre hay una vela abierta", () => {
  let dir: string;
  let store: Store;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "marea-vivos-"));
    store = new Store(dir);
  });
  afterEach(() => rmSync(dir, { recursive: true, force: true }));

  it("mantiene abierta una de 5 y una de 15 por activo", () => {
    const vivos = new MercadosVivos(store, tickerFalso({ "BTC/USD": 71_183, "ETH/USD": 4_502 }));
    vivos.tick(DENTRO);
    const seeds = vivos.seeds();
    expect(seeds).toHaveLength(4);
    for (const seed of seeds) {
      expect(new Date(seed.closesAt).getTime()).toBeGreaterThan(DENTRO);
    }
  });

  it("es idempotente: cien vueltas no crean cien mercados", () => {
    const vivos = new MercadosVivos(store, tickerFalso({ "BTC/USD": 71_183 }));
    for (let i = 0; i < 100; i += 1) vivos.tick(DENTRO + i * 10);
    expect(vivos.seeds()).toHaveLength(2);
  });

  it("el strike no se mueve aunque el precio sí: la pregunta ya se hizo", () => {
    const precios = { "BTC/USD": 71_183 };
    const ticker: Ticker = {
      ...tickerFalso(precios),
      precio: (par) =>
        precios[par as "BTC/USD"] !== undefined
          ? { precio: precios[par as "BTC/USD"], at: DENTRO, fuente: "kraken" as const }
          : undefined,
    };
    const vivos = new MercadosVivos(store, ticker);
    vivos.tick(DENTRO);
    const antes = (vivos.seeds()[0].rule as VelaRule).strike;

    precios["BTC/USD"] = 75_000;
    vivos.tick(DENTRO + 30_000);
    const despues = (vivos.seed(vivos.seeds()[0].id)!.rule as VelaRule).strike;
    expect(despues).toBe(antes);
  });

  it("no deja hueco: al bloquear la vela ya está abierta la siguiente", () => {
    const vivos = new MercadosVivos(store, tickerFalso({ "BTC/USD": 71_183 }), {
      intervalos: [5],
      activos: [BTC],
    });
    const inicio = inicioDeVentana(DENTRO, 5);
    const enElBloqueo = bloqueoDeVentana(inicio, 5) + 2_000;
    vivos.tick(DENTRO);
    vivos.tick(enElBloqueo);

    const abiertos = vivos
      .seeds()
      .filter((seed) => new Date(seed.closesAt).getTime() > enElBloqueo);
    expect(abiertos.length).toBeGreaterThanOrEqual(1);
  });

  it("no crea una vela que ya nace bloqueada", () => {
    const vivos = new MercadosVivos(store, tickerFalso({ "BTC/USD": 71_183 }), {
      intervalos: [5],
      activos: [BTC],
    });
    const inicio = inicioDeVentana(DENTRO, 5);
    // justo en el bloqueo: la actual ya no acepta apuestas, sólo nace la que viene
    vivos.tick(bloqueoDeVentana(inicio, 5) + 1);
    const ids = vivos.seeds().map((s) => s.id);
    expect(ids).toEqual([idDeVela(BTC, 5, finDeVentana(inicio, 5))]);
  });

  it("olvida las velas vencidas que nadie tocó", () => {
    const vivos = new MercadosVivos(store, tickerFalso({ "BTC/USD": 71_183 }), {
      intervalos: [5],
      activos: [BTC],
    });
    vivos.tick(DENTRO);
    expect(vivos.seeds()).toHaveLength(1);
    vivos.tick(DENTRO + 30 * 60_000);
    // la vieja se fue y sólo queda la de ahora
    expect(vivos.seeds()).toHaveLength(1);
    expect(vivos.seeds()[0].id).not.toBe(idDeVela(BTC, 5, inicioDeVentana(DENTRO, 5)));
  });

  it("no siembra pozo en disco hasta que alguien apuesta", () => {
    const vivos = new MercadosVivos(store, tickerFalso({ "BTC/USD": 71_183 }));
    vivos.tick(DENTRO);
    expect(store.pozos()).toHaveLength(0);
    expect(store.seedsVivas()).toHaveLength(0);
  });

  it("una vela con dinero adentro sobrevive a un reinicio", () => {
    const vivos = new MercadosVivos(store, tickerFalso({ "BTC/USD": 71_183 }), {
      intervalos: [5],
      activos: [BTC],
    });
    vivos.tick(DENTRO);
    const id = vivos.seeds()[0].id;
    vivos.persistir(id);

    // otro proceso, mismo disco
    const otro = new MercadosVivos(new Store(dir), tickerFalso({}), {
      intervalos: [5],
      activos: [BTC],
    });
    expect(otro.seed(id)).toBeDefined();
    expect((otro.seed(id)!.rule as VelaRule).strike).toBe(71_200);
  });
});

describe("De la apuesta al pago — la vela se liquida sola", () => {
  let dir: string;
  let store: Store;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), "marea-vela-"));
    store = new Store(dir);
  });
  afterEach(() => rmSync(dir, { recursive: true, force: true }));

  it("paga a quien acertó y deja la comisión asentada", async () => {
    const ticker = tickerFalso({ "BTC/USD": 71_183 });
    const vivos = new MercadosVivos(store, ticker, { intervalos: [5], activos: [BTC] });
    vivos.tick(DENTRO);
    const seed = vivos.seeds()[0];
    const rule = seed.rule as VelaRule;
    const fin = finDeVentana(rule.inicio, 5);

    store.asegurarPozo({
      marketId: seed.id,
      outcomes: { ...seed.pool.outcomes },
      feeBps: seed.pool.feeBps,
    });
    vivos.persistir(seed.id);

    const ana = store.crearUsuario({
      id: "ana",
      usuario: "ana",
      hash: "h",
      salt: "s",
      creado: new Date(DENTRO).toISOString(),
      puntos: 500,
    });
    const beto = store.crearUsuario({
      id: "beto",
      usuario: "beto",
      hash: "h",
      salt: "s",
      creado: new Date(DENTRO).toISOString(),
      puntos: 500,
    });
    store.apostar({ usuarioId: ana.id, marketId: seed.id, side: ARRIBA, stake: 100, precio: 0.5 });
    store.apostar({ usuarioId: beto.id, marketId: seed.id, side: ABAJO, stake: 100, precio: 0.5 });

    const oraculos = [
      createVelaOracle({
        cargarVelas: async () => [
          { inicio: rule.inicio, cierre: rule.strike + 50 },
          { inicio: fin, cierre: rule.strike + 50 },
        ],
      }),
    ];

    // la vela cerró: se lee y se abre la ventana de disputa
    await correrCiclo(store, [seed], oraculos, fin + 30_000);
    expect(store.liquidacion(seed.id)?.phase).toBe("en_disputa");
    expect(store.liquidacion(seed.id)?.outcome).toBe(ARRIBA);

    // cerrada la ventana, se paga
    await correrCiclo(store, [seed], oraculos, fin + 120_000);
    expect(store.liquidacion(seed.id)?.phase).toBe("pagado");
    expect(store.usuarioPorId(ana.id)!.puntos).toBeGreaterThan(400);
    expect(store.usuarioPorId(beto.id)!.puntos).toBe(400);
    expect(store.tesoreria()).toBeGreaterThan(0);
    // y la contabilidad cuadra: cero, o hay dinero perdido
    expect(store.cuadre()).toBeCloseTo(0, 6);
  });

  it("no se paga mientras la ventana de disputa siga abierta", async () => {
    const vivos = new MercadosVivos(store, tickerFalso({ "BTC/USD": 71_183 }), {
      intervalos: [5],
      activos: [BTC],
    });
    vivos.tick(DENTRO);
    const seed = vivos.seeds()[0];
    const rule = seed.rule as VelaRule;
    const fin = finDeVentana(rule.inicio, 5);
    const oraculos = [
      createVelaOracle({
        cargarVelas: async () => [
          { inicio: rule.inicio, cierre: rule.strike + 50 },
          { inicio: fin, cierre: rule.strike + 50 },
        ],
      }),
    ];
    await correrCiclo(store, [seed], oraculos, fin + 30_000);
    // treinta segundos después de leer, con ventana de sesenta: todavía no
    expect(store.liquidacion(seed.id)?.phase).toBe("en_disputa");
  });

  it("una vela abierta se lista como LIVE y con su bloque vivo", () => {
    const ticker = tickerFalso({ "BTC/USD": 71_272 });
    const vivos = new MercadosVivos(store, ticker, { intervalos: [5], activos: [BTC] });
    vivos.tick(DENTRO);
    const [mercado] = listarMercados(store, vivos.seeds(), DENTRO, ticker);

    expect(mercado.status).toBe("live");
    expect(mercado.live?.strike).toBe(71_300);
    expect(mercado.live?.spot).toBe(71_272);
    expect(mercado.live?.fuente).toBe("kraken");
    expect(mercado.live?.deltaPp).toBeLessThan(0);
  });

  it("sin lectura fresca, el bloque vivo va sin precio en vez de con uno viejo", () => {
    const vivos = new MercadosVivos(store, tickerFalso({ "BTC/USD": 71_183 }), {
      intervalos: [5],
      activos: [BTC],
    });
    vivos.tick(DENTRO);
    const mercado = construirMercado(store, vivos.seeds()[0], Infinity, DENTRO, {
      precio: () => undefined,
    });
    expect(mercado.live).toBeDefined();
    expect(mercado.live?.spot).toBeUndefined();
    expect(mercado.live?.deltaPp).toBeUndefined();
  });

  it("una vela bloqueada que nadie tocó se va del feed en el acto", () => {
    const ticker = tickerFalso({ "BTC/USD": 71_183 });
    const vivos = new MercadosVivos(store, ticker, { intervalos: [5], activos: [BTC] });
    vivos.tick(DENTRO);
    const seed = vivos.seeds()[0];
    const despues = new Date(seed.closesAt).getTime() + 1_000;
    expect(listarMercados(store, [seed], despues, ticker)).toHaveLength(0);
  });

  it("pero si alguien apostó se queda hasta que se vea el resultado", () => {
    const ticker = tickerFalso({ "BTC/USD": 71_183 });
    const vivos = new MercadosVivos(store, ticker, { intervalos: [5], activos: [BTC] });
    vivos.tick(DENTRO);
    const seed = vivos.seeds()[0];
    store.asegurarPozo({
      marketId: seed.id,
      outcomes: { ...seed.pool.outcomes },
      feeBps: seed.pool.feeBps,
    });
    const despues = new Date(seed.closesAt).getTime() + 1_000;
    expect(listarMercados(store, [seed], despues, ticker)).toHaveLength(1);
  });

  it("una vela cerrada deja de encabezar el feed", () => {
    const ticker = tickerFalso({ "BTC/USD": 71_183 });
    const vivos = new MercadosVivos(store, ticker, { intervalos: [5, 15], activos: [BTC] });
    vivos.tick(DENTRO);
    const [corta, larga] = vivos.seeds();
    store.asegurarPozo({
      marketId: corta.id,
      outcomes: { ...corta.pool.outcomes },
      feeBps: corta.pool.feeBps,
    });
    const despues = new Date(corta.closesAt).getTime() + 1_000;
    const lista = listarMercados(store, [corta, larga], despues, ticker);
    expect(lista[0].id).toBe(larga.id);
    expect(lista[0].status).toBe("live");
  });

  it("lo vivo va primero en el feed, aunque tenga menos pozo", () => {
    const ticker = tickerFalso({ "BTC/USD": 71_183 });
    const vivos = new MercadosVivos(store, ticker, { intervalos: [5], activos: [BTC] });
    vivos.tick(DENTRO);
    const gordo = {
      ...vivos.seeds()[0],
      id: "mercado-gordo",
      rule: undefined,
      pool: { outcomes: { arriba: 50_000, abajo: 50_000 }, feeBps: 300 },
      closesAt: new Date(DENTRO + 86_400_000).toISOString(),
      resolution: {
        ...vivos.seeds()[0].resolution,
        settlesAt: new Date(DENTRO + 86_400_000).toISOString(),
      },
    };
    const lista = listarMercados(store, [gordo, ...vivos.seeds()], DENTRO, ticker);
    expect(lista[0].live).toBeDefined();
    expect(lista[lista.length - 1].id).toBe("mercado-gordo");
  });

  it("el pulso lleva sólo lo que cambia, no el mercado entero", () => {
    const ticker = tickerFalso({ "BTC/USD": 71_272 });
    const vivos = new MercadosVivos(store, ticker, { intervalos: [5], activos: [BTC] });
    vivos.tick(DENTRO);
    const [pulso] = vivos.vista(DENTRO);

    expect(Object.keys(pulso).sort()).toEqual(
      [
        "bloqueaAt",
        "cierraAt",
        "deltaPp",
        "fuente",
        "id",
        "jugando",
        "multiplicadores",
        "pozo",
        "probabilidades",
        "spot",
        "spotAt",
        "strike",
      ].sort(),
    );
    expect(pulso.probabilidades[ARRIBA] + pulso.probabilidades[ABAJO]).toBeCloseTo(1, 6);
  });
});

/* ------------------------------ la interfaz ------------------------------ */

function mercadoVivo(overrides: Partial<Market> = {}): Market {
  const inicio = inicioDeVentana(Date.now(), 5);
  return {
    id: "btc-5m-prueba",
    title: "Bitcoin en 5 min: ¿arriba o abajo de 71,200?",
    probability: 0.5,
    volume: 400,
    status: "live",
    category: "cripto",
    edge: null,
    resolution_summary: "Se resuelve con la vela de 5 minutos de Kraken.",
    pool: { outcomes: { arriba: 200, abajo: 200 }, feeBps: 300 },
    outcomes: [
      { id: ARRIBA, label: "Arriba 71.2k" },
      { id: ABAJO, label: "Abajo 71.2k" },
    ],
    participantes: 8,
    live: {
      par: "BTC/USD",
      activo: "Bitcoin",
      intervalo: 5,
      abreAt: new Date(inicio).toISOString(),
      cierraAt: new Date(Date.now() + 170_000).toISOString(),
      bloqueaAt: new Date(Date.now() + 160_000).toISOString(),
      strike: 71_200,
      spot: 71_272,
      deltaPp: 0.101,
      fuente: "kraken",
      spotAt: new Date().toISOString(),
    },
    ...overrides,
  };
}

describe("Card viva — el congelado es sagrado", () => {
  it("pinta el badge LIVE con su cuenta regresiva", () => {
    render(<MarketCard market={mercadoVivo()} onOpen={() => {}} />);
    const badge = screen.getByTestId("live-countdown");
    expect(badge.textContent).toMatch(/LIVE/);
    expect(badge.textContent).toMatch(/\d\d:\d\d/);
  });

  it("enseña el precio de ahora y su variación desde el strike", () => {
    render(<MarketCard market={mercadoVivo()} onOpen={() => {}} />);
    expect(screen.getByTestId("live-spot").textContent).toMatch(/71[.,]272/);
    expect(screen.getByTestId("live-delta").textContent).toBe("+0.10%");
  });

  it("sin precio dice que no hay, en vez de repetir el último", () => {
    const market = mercadoVivo();
    render(
      <MarketCard
        market={{ ...market, live: { ...market.live!, spot: undefined, deltaPp: undefined } }}
        onOpen={() => {}}
      />,
    );
    expect(screen.getByTestId("live-sin-precio")).toBeInTheDocument();
    expect(screen.queryByTestId("live-spot")).toBeNull();
  });

  it("los dos lados van nombrados, con su pago y su barra", () => {
    render(<MarketCard market={mercadoVivo()} onOpen={() => {}} />);
    const pills = screen.getAllByTestId("live-pill");
    expect(pills).toHaveLength(2);
    expect(pills[0].textContent).toContain("Arriba 71.2k");
    expect(pills[1].textContent).toContain("Abajo 71.2k");
    expect(pills[0].textContent).toMatch(/×/);
    // una sola barra con los dos segmentos, como en la card normal: dos barras
    // separadas eran dos maneras de pintar el mismo dato en el mismo feed
    const barra = screen.getByTestId("live-barra");
    expect(barra.children).toHaveLength(2);
  });

  it("los lados conservan su orden aunque uno se ponga favorito", () => {
    const market = mercadoVivo({
      pool: { outcomes: { arriba: 100, abajo: 900 }, feeBps: 300 },
    });
    render(<MarketCard market={market} onOpen={() => {}} />);
    const pills = screen.getAllByTestId("live-pill");
    expect(pills[0].dataset.outcomeId).toBe(ARRIBA);
    expect(pills[1].dataset.outcomeId).toBe(ABAJO);
  });

  it("al tocar una pill los números se congelan", async () => {
    const market = mercadoVivo();
    const { rerender } = render(<MarketCard market={market} onOpen={() => {}} />);
    expect(screen.getByTestId("live-spot").textContent).toMatch(/71[.,]272/);

    // el dedo baja sobre la pill
    const pill = screen.getAllByTestId("live-pill")[0];
    await act(async () => {
      pill.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }));
    });
    expect(screen.getByTestId("market-card").dataset.congelado).toBe("true");

    // llega un latido nuevo mientras el dedo sigue abajo: no se aplica
    rerender(
      <MarketCard
        market={market}
        pulso={{
          id: market.id,
          strike: 71_200,
          spot: 99_999,
          deltaPp: 40,
          bloqueaAt: market.live!.bloqueaAt,
          cierraAt: market.live!.cierraAt,
          probabilidades: { arriba: 0.9, abajo: 0.1 },
          multiplicadores: { arriba: 1.07, abajo: 9.7 },
          pozo: 4_000,
          jugando: 40,
        }}
        onOpen={() => {}}
      />,
    );
    expect(screen.getByTestId("live-spot").textContent).toMatch(/71[.,]272/);
    expect(screen.getByTestId("live-spot").textContent).not.toMatch(/99[.,]999/);
  });

  it("un mercado sin bloque vivo sigue usando la card de siempre", () => {
    const market = mercadoVivo({ live: undefined, status: "open" });
    render(<MarketCard market={market} onOpen={() => {}} />);
    expect(screen.queryByTestId("live-pill")).toBeNull();
    expect(screen.getByTestId("market-card").dataset.variant).toBe("default");
  });

  it("tocar una pill abre el detalle del mercado", async () => {
    const abrir = vi.fn();
    render(<MarketCard market={mercadoVivo()} onOpen={abrir} />);
    await userEvent.click(screen.getAllByTestId("live-pill")[0]);
    expect(abrir).toHaveBeenCalledTimes(1);
    expect(abrir.mock.calls[0][0].id).toBe("btc-5m-prueba");
  });

  it("cada pill es un target táctil de 44 px (R-010)", () => {
    render(<MarketCard market={mercadoVivo()} onOpen={() => {}} />);
    for (const pill of screen.getAllByTestId("live-pill")) {
      // la pill mide 36 px y su zona tocable 44, expandida con un
      // pseudo-elemento que no ocupa fila
      expect(pill.className).toContain("after:-inset-y-1");
    }
  });
});

describe("Presupuesto de la card viva", () => {
  /**
   * La altura de verdad la mide `npm run densidad` en un navegador real: jsdom
   * no hace layout y cualquier número que se afirme aquí sería inventado. Lo
   * que sí se puede sostener desde aquí es lo que rompió el presupuesto en
   * silencio las dos veces que se rompió.
   */
  it("mantiene las cinco filas que caben junto al esqueleto del feed", () => {
    render(<MarketCard market={mercadoVivo()} onOpen={() => {}} />);
    const card = screen.getByTestId("market-card");
    // reloj · activo+precio · pills · barra · pie. La barra salió de dentro de
    // las pills para ser una sola, igual que en la card normal; a cambio ocupa
    // fila propia. Una fila **más** que éstas es la forma en que se pasa del
    // alto de la card normal sin darse cuenta
    expect(card.querySelector("div > div")?.children.length).toBe(5);
  });

  it("el porcentaje conserva su escala después de `twMerge` (R-004)", () => {
    render(<MarketCard market={mercadoVivo()} onOpen={() => {}} />);
    // `twMerge` mete el tamaño y el color en el mismo grupo `text-*` y se queda
    // con el último: con el orden al revés el porcentaje salía en 16 px y sólo
    // lo cazaba el navegador. Esto lo caza aquí. El líder va en la escala de la
    // pill (30 px) y el rival en la del rival (20), igual que la card normal
    const escalas = screen
      .getAllByTestId("live-pill")
      .map((nodo) => nodo.querySelector('[data-role="probability"]')?.className ?? "");
    expect(escalas.some((clase) => clase.includes("text-prob-pill"))).toBe(true);
    for (const clase of escalas) {
      expect(clase).toMatch(/text-prob-(pill|riv)/);
    }
  });
});
