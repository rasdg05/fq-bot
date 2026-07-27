import { describe, expect, it } from "vitest";
import {
  applyCalibration,
  isUsable,
  logit,
  normalCdf,
  priceBasis,
  priceProbability,
  realizedVolatility,
  sigmoid,
  terminalProbability,
  touchProbability,
  MAX_USABLE_ECE_PP,
  TRADING_DAYS,
} from "@/domain/priceModel";
import { createPriceModelProvider } from "@/domain/probability";
import CALIBRATION from "../vault/calibration.lock.json";
import type { VenueMarket } from "@/adapters/venues/types";

const question = (over: Partial<Parameters<typeof terminalProbability>[0]> = {}) => ({
  spot: 100,
  strike: 100,
  direction: "above" as const,
  daysToResolve: 30,
  annualVolatility: 0.5,
  ...over,
});

describe("Modelo de precio", () => {
  it("la normal acumulada da los valores conocidos", () => {
    expect(normalCdf(0)).toBeCloseTo(0.5, 6);
    expect(normalCdf(1.645)).toBeCloseTo(0.95, 3);
    expect(normalCdf(-1.96)).toBeCloseTo(0.025, 3);
  });

  it("en el umbral, sin deriva, la respuesta es 50 %", () => {
    expect(terminalProbability(question())).toBeCloseTo(0.5, 6);
  });

  it("más lejos del umbral, menos probable", () => {
    const cerca = terminalProbability(question({ strike: 105 }));
    const lejos = terminalProbability(question({ strike: 130 }));
    expect(lejos).toBeLessThan(cerca);
    expect(cerca).toBeLessThan(0.5);
  });

  it("más volatilidad acerca cualquier umbral al 50 %", () => {
    const tranquilo = terminalProbability(question({ strike: 120, annualVolatility: 0.2 }));
    const agitado = terminalProbability(question({ strike: 120, annualVolatility: 1.5 }));
    expect(agitado).toBeGreaterThan(tranquilo);
    expect(agitado).toBeLessThan(0.5);
  });

  it("'abajo de' es el complemento de 'arriba de'", () => {
    const arriba = terminalProbability(question({ strike: 110 }));
    const abajo = terminalProbability(question({ strike: 110, direction: "below" }));
    expect(arriba + abajo).toBeCloseTo(1, 6);
  });

  it("tocar siempre es al menos tan probable como cerrar arriba", () => {
    for (const strike of [90, 100, 110, 140]) {
      const q = question({ strike });
      expect(touchProbability(q)).toBeGreaterThanOrEqual(terminalProbability(q));
    }
  });

  it("vencido, el modelo se calla y manda el precio", () => {
    expect(terminalProbability(question({ daysToResolve: 0, spot: 120 }))).toBe(1);
    expect(terminalProbability(question({ daysToResolve: 0, spot: 80 }))).toBe(0);
  });

  it("nunca muestra 0 % ni 100 % con el mercado abierto", () => {
    expect(priceProbability(question({ strike: 10_000 }))).toBe(0.01);
    expect(priceProbability(question({ strike: 0.01 }))).toBe(0.99);
  });

  it("la volatilidad realizada escala con la raíz del tiempo", () => {
    // serie con un 1 % diario alternado: volatilidad diaria conocida
    const closes = Array.from({ length: 60 }, (_, i) => 100 * (i % 2 === 0 ? 1 : 1.01));
    const vol = realizedVolatility(closes);
    expect(vol).not.toBeNull();
    expect(vol!).toBeGreaterThan(0.1 * Math.sqrt(TRADING_DAYS) * 0.01);
    expect(realizedVolatility([100, 101])).toBeNull();
  });

  it("la base explica el cálculo con datos verificables", () => {
    const basis = priceBasis(question({ annualVolatility: 0.42, daysToResolve: 12 }));
    expect(basis).toContain("42%");
    expect(basis).toContain("12 días");
    // no promete nada: describe una cuenta
    expect(basis).not.toMatch(/garantiz|seguro|va a subir/i);
  });
});

describe("Recalibración", () => {
  it("logit y sigmoide se deshacen", () => {
    for (const p of [0.05, 0.3, 0.5, 0.87]) {
      expect(sigmoid(logit(p))).toBeCloseTo(p, 6);
    }
  });

  it("la identidad no mueve la probabilidad", () => {
    expect(applyCalibration(0.7, { a: 1, b: 0, eceOutOfSample: 0 })).toBeCloseTo(0.7, 4);
  });

  it("la puerta se abre sólo si el error medido baja del máximo", () => {
    expect(isUsable({ a: 1, b: 0, eceOutOfSample: MAX_USABLE_ECE_PP })).toBe(true);
    expect(isUsable({ a: 1, b: 0, eceOutOfSample: MAX_USABLE_ECE_PP + 0.01 })).toBe(false);
  });
});

describe("Puerta de calibración en producción", () => {
  const quotes: VenueMarket[] = [
    {
      venueMarketId: "1",
      venueId: "polymarket",
      question: "¿sube?",
      probability: 0.5,
      volume: 0,
      liquidity: 0,
      status: "open",
      category: "cripto",
      resolutionSummary: "r",
      matchKey: "k",
    },
  ];
  const questions = new Map([["k", question({ strike: 130 })]]);

  it("la calibración medida está por encima del máximo: hoy no hay lectura propia", () => {
    // esto es un hecho medido, no una decisión de diseño: ver
    // vault/calibration.lock.json y `npm run calibrate`
    expect(CALIBRATION.cierre.usable).toBe(false);
    expect(CALIBRATION.cierre.eceOutOfSample).toBeGreaterThan(MAX_USABLE_ECE_PP);

    const provider = createPriceModelProvider(questions, () => "k");
    expect(provider.read(quotes)).toBeNull();
  });

  it("con una calibración que sí pasa, el proveedor entrega lectura y su porqué", () => {
    const buena = { a: 1, b: 0, eceOutOfSample: 1.2 };
    const provider = createPriceModelProvider(questions, () => "k", {
      cierre: buena,
      toca: buena,
    });
    const reading = provider.read(quotes);
    expect(reading).not.toBeNull();
    expect(reading!.probability).toBeGreaterThan(0);
    expect(reading!.probability).toBeLessThan(0.5);
    expect(reading!.basis).toContain("volatilidad");
  });

  it("sin pregunta de precio asociada no inventa nada", () => {
    const provider = createPriceModelProvider(new Map(), () => "k", {
      cierre: { a: 1, b: 0, eceOutOfSample: 0.5 },
      toca: { a: 1, b: 0, eceOutOfSample: 0.5 },
    });
    expect(provider.read(quotes)).toBeNull();
  });
});
