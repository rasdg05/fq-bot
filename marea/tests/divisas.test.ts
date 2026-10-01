import { describe, expect, it, vi } from "vitest";
import {
  ACTIVOS_VIVOS,
  velaSeed,
  velasVigentes,
  type ActivoVivo,
} from "@/adapters/ownMarkets/cryptoLive";
import { createVelaOracle } from "@/adapters/oracles/velaOracle";
import { validateSeed } from "@/adapters/ownMarkets/catalog";
import { activoDeRegla, type VelaRule } from "@/domain/oracleRule";
import { pasoDeStrike, redondearStrike } from "@/domain/vela";
import { leerBitso } from "../server/precios.mts";

/**
 * El dólar en vivo: velas de 5 y 15 minutos de USD/MXN, USD/ARS y USD/BRL
 * resueltas con las velas públicas de Bitso. La forma de la respuesta es la
 * medida el 2026-10-01 (`/v3/ohlc?book=usd_mxn&time_bucket=900`).
 */

const MXN = ACTIVOS_VIVOS.find((a) => a.id === "usdmxn")!;
const ARS = ACTIVOS_VIVOS.find((a) => a.id === "usdars")!;
const BRL = ACTIVOS_VIVOS.find((a) => a.id === "usdbrl")!;
const INICIO = Date.parse("2026-10-01T15:00:00Z");

/** Una vela tal como la publica Bitso. */
const bucket = (inicio: number, cierre: string, trades = 40) => ({
  bucket_start_time: inicio,
  first_trade_time: inicio + 1_000,
  last_trade_time: inicio + 800_000,
  first_rate: cierre,
  last_rate: cierre,
  min_rate: cierre,
  max_rate: cierre,
  trade_count: trades,
  volume: "1000",
  vwap: cierre,
});

describe("Velas del dólar — la semilla", () => {
  it("USD/MXN: strike en centavos, criterio de Bitso en pesos, y pasa la validación de producción", () => {
    const seed = validateSeed(velaSeed({ activo: MXN, intervalo: 15, inicio: INICIO, spot: 18.1034 }));
    const rule = seed.rule as VelaRule;
    expect(rule.strike).toBe(18.1);
    // dos decimales fijos: «18.10», no «18.1»
    expect(seed.outcomes!.map((o) => o.label)).toEqual(["Arriba 18.10", "Abajo 18.10"]);
    expect(seed.resolution.criterion).toMatch(/USD\/MXN en Bitso.*18\.10 pesos mexicanos/);
    expect(seed.resolution.sourceUrl).toBe("https://api.bitso.com/v3/ohlc?book=usd_mxn&time_bucket=900");
    expect(seed.category).toBe("economia");
    expect(seed.country).toBe("MX");
    expect(seed.id).toBe("usdmxn-15m-20261001T1500");
  });

  it("el strike que se publica es el mismo número que se compara (sin 17.080000000000002)", () => {
    // 1708 × 0.01 y 1029 × 0.005 dan basura de coma flotante en JavaScript
    for (const [par, spot, esperado] of [
      ["USD/MXN", 17.0812, 17.08],
      ["USD/BRL", 5.1449, 5.145],
      ["USD/ARS", 1602.38, 1602],
    ] as const) {
      const strike = redondearStrike(spot, pasoDeStrike(par));
      expect(strike, par).toBe(esperado);
      expect(String(strike)).toBe(String(esperado));
      // el paso nunca pasa del 0.1 % del precio: la pregunta no viene contestada
      expect(pasoDeStrike(par) / spot).toBeLessThanOrEqual(0.001);
    }
  });

  it("USD/ARS y USD/BRL sólo a 15 minutos; USD/MXN a 5 y 15", () => {
    const velas = velasVigentes({
      ahora: INICIO + 1_000,
      precio: (par) => ({ "USD/MXN": 18.1, "USD/ARS": 1602, "USD/BRL": 5.2 })[par as string],
      activos: [MXN, ARS, BRL] as ActivoVivo[],
    });
    const porActivo = (id: string) => velas.filter((v) => v.activo.id === id).map((v) => v.intervalo);
    expect(porActivo("usdmxn")).toEqual([5, 15]);
    expect(porActivo("usdars")).toEqual([15]);
    expect(porActivo("usdbrl")).toEqual([15]);
  });

  it("el activo de una divisa es la moneda local: tres pares, tres activos", () => {
    const activos = [MXN, ARS, BRL].map((a) =>
      activoDeRegla(velaSeed({ activo: a, intervalo: 15, inicio: INICIO, spot: 10 }).rule),
    );
    expect(activos).toEqual(["MXN", "ARS", "BRL"]);
  });
});

describe("Velas del dólar — el oráculo lee Bitso", () => {
  const rule: VelaRule = { kind: "vela", par: "USD/MXN", intervalo: 15, inicio: INICIO, strike: 18.1 };
  const fin = INICIO + 15 * 60_000;
  const query = (now: number) => ({ marketId: "usdmxn-15m", spec: {} as never, rule, now });

  function bitso(cierre: string, conSiguiente = true) {
    return vi.fn(async (url: string | URL | Request) => {
      expect(String(url)).toMatch(/^https:\/\/api\.bitso\.com\/v3\/ohlc\?book=usd_mxn&time_bucket=900&start=/);
      const payload = [bucket(INICIO - 900_000, "18.090"), bucket(INICIO, cierre)];
      if (conSiguiente) payload.push(bucket(fin, cierre));
      return new Response(JSON.stringify({ success: true, payload }));
    });
  }

  it("cierre arriba del strike paga Arriba, y la evidencia cita la URL de Bitso", async () => {
    const fetchImpl = bitso("18.107");
    const r = await createVelaOracle({ fetchImpl: fetchImpl as never }).read(query(fin + 60_000));
    expect(r).toMatchObject({ status: "resuelto", outcome: "arriba" });
    expect(r.evidence).toMatch(/Bitso.*18\.107 MXN.*api\.bitso\.com/);
  });

  it("empate exacto paga Abajo, como dice el criterio", async () => {
    const r = await createVelaOracle({ fetchImpl: bitso("18.100") as never }).read(query(fin + 60_000));
    expect(r).toMatchObject({ status: "resuelto", outcome: "abajo" });
  });

  it("sin la vela siguiente publicada no se paga: la nuestra puede seguir abierta", async () => {
    const r = await createVelaOracle({ fetchImpl: bitso("18.130", false) as never }).read(query(fin + 60_000));
    expect(r.status).toBe("sin_dato");
  });
});

describe("Velas del dólar — el ticker", () => {
  it("lee los tres libros en una sola consulta e ignora los demás", async () => {
    const fetchImpl = vi.fn(async () =>
      new Response(
        JSON.stringify({
          success: true,
          payload: [
            { book: "btc_mxn", last: "2100000" },
            { book: "usd_mxn", last: "18.104" },
            { book: "usd_ars", last: "1602.38" },
            { book: "usd_brl", last: "5.198" },
            { book: "usd_cop", last: "3295.5" },
          ],
        }),
      ),
    );
    const lectura = await leerBitso(fetchImpl as never, 1_000);
    expect(lectura).toEqual({ "USD/MXN": 18.104, "USD/ARS": 1602.38, "USD/BRL": 5.198 });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
