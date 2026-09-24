import { describe, expect, it } from "vitest";
import {
  ESCALERA,
  NIVELES,
  N2_CAP_USD_PROVISIONAL,
  capNivel,
  detectStructuring,
  effectiveCapForUser,
  effectiveCapUsd,
  type Retiro,
} from "@/domain/niveles";

const DIA = 24 * 60 * 60 * 1000;
const AHORA = 1_700_000_000_000;

const CAPS_PAIS = [0, 1, 50, 100, 1_000, 12_345, 1_000_000];
const CAPS_NIVEL: (number | null)[] = [0, 25, 500, 10_000, null];

describe("Escalera de verificación N0–N3", () => {
  it("cubre exactamente los cuatro niveles, en orden", () => {
    expect(NIVELES).toEqual(["N0", "N1", "N2", "N3"]);
    for (const n of NIVELES) {
      expect(ESCALERA[n].nivel).toBe(n);
    }
  });

  it("N0 y N1 nunca operan con dinero; N2 y N3 sí", () => {
    expect(ESCALERA.N0.operaConDinero).toBe(false);
    expect(ESCALERA.N1.operaConDinero).toBe(false);
    expect(ESCALERA.N2.operaConDinero).toBe(true);
    expect(ESCALERA.N3.operaConDinero).toBe(true);
  });

  it("N3 no impone tope de nivel (null); N2 usa el tope provisional pendiente P11", () => {
    expect(capNivel("N3")).toBeNull();
    expect(capNivel("N2")).toBe(N2_CAP_USD_PROVISIONAL);
    // N0/N1 no mueven dinero: su tope de nivel es 0.
    expect(capNivel("N0")).toBe(0);
    expect(capNivel("N1")).toBe(0);
  });
});

describe("Tope efectivo = min(país, nivel) (R-069 / L16)", () => {
  it("es exactamente el mínimo y nunca excede ninguno de los dos", () => {
    for (const pais of CAPS_PAIS) {
      for (const nivel of CAPS_NIVEL) {
        const eff = effectiveCapUsd(pais, nivel);
        const nivelNum = nivel ?? Number.POSITIVE_INFINITY;
        expect(eff).toBe(Math.min(pais, nivelNum));
        expect(eff).toBeLessThanOrEqual(pais);
        expect(eff).toBeLessThanOrEqual(nivelNum);
      }
    }
  });

  it("un nivel sin tope (null) deja mandar al país", () => {
    for (const pais of CAPS_PAIS) {
      expect(effectiveCapUsd(pais, null)).toBe(pais);
    }
  });

  it("con la puerta cerrada (país = 0) el tope efectivo es 0 en todo nivel", () => {
    for (const n of NIVELES) {
      expect(effectiveCapForUser(0, n)).toBe(0);
    }
  });

  it("effectiveCapForUser: N3 hereda el tope del país; N0/N1 no habilitan dinero", () => {
    const paisAbierto = 1_000; // hipotético, sólo para la aritmética
    expect(effectiveCapForUser(paisAbierto, "N3")).toBe(paisAbierto);
    expect(effectiveCapForUser(paisAbierto, "N0")).toBe(0);
    expect(effectiveCapForUser(paisAbierto, "N1")).toBe(0);
  });
});

describe("Anti-structuring por ventana móvil (R-070)", () => {
  it("varios retiros bajo umbral que sumados lo cruzan disparan como uno solo", () => {
    const retiros: Retiro[] = [
      { usd: 30, ts: AHORA - 1 * DIA, destino: "0xA" },
      { usd: 30, ts: AHORA - 2 * DIA, destino: "0xA" },
      { usd: 30, ts: AHORA - 3 * DIA, destino: "0xA" },
      { usd: 30, ts: AHORA - 4 * DIA, destino: "0xA" },
    ];
    const r = detectStructuring(retiros, { thresholdUsd: 100 }, AHORA);
    expect(r.acumuladoUsd).toBe(120);
    expect(r.triggered).toBe(true);
    expect(r.motivo).toBe("acumulado");
    // cada retiro individual está por debajo del umbral
    for (const x of retiros) expect(x.usd).toBeLessThan(100);
  });

  it("los mismos retiros, fuera de la ventana, no disparan", () => {
    const retiros: Retiro[] = [
      { usd: 30, ts: AHORA - 40 * DIA, destino: "0xA" },
      { usd: 30, ts: AHORA - 41 * DIA, destino: "0xA" },
      { usd: 30, ts: AHORA - 42 * DIA, destino: "0xA" },
      { usd: 30, ts: AHORA - 43 * DIA, destino: "0xA" },
    ];
    const r = detectStructuring(retiros, { thresholdUsd: 100, windowDays: 30 }, AHORA);
    expect(r.acumuladoUsd).toBe(0);
    expect(r.triggered).toBe(false);
    expect(r.motivo).toBeNull();
  });

  it("la rotación de destinos dispara aunque el acumulado no cruce el umbral", () => {
    const retiros: Retiro[] = [
      { usd: 10, ts: AHORA - 1 * DIA, destino: "0xA" },
      { usd: 10, ts: AHORA - 2 * DIA, destino: "0xB" },
      { usd: 10, ts: AHORA - 3 * DIA, destino: "0xC" },
    ];
    const r = detectStructuring(retiros, { thresholdUsd: 10_000 }, AHORA);
    expect(r.acumuladoUsd).toBe(30);
    expect(r.destinosDistintos).toBe(3);
    expect(r.triggered).toBe(true);
    expect(r.motivo).toBe("rotacion");
  });

  it("un retiro pequeño y solo no dispara nada", () => {
    const r = detectStructuring(
      [{ usd: 10, ts: AHORA - 1 * DIA, destino: "0xA" }],
      { thresholdUsd: 100 },
      AHORA,
    );
    expect(r.triggered).toBe(false);
    expect(r.motivo).toBeNull();
  });

  it("monotonía: sumar un retiro dentro de la ventana nunca baja el acumulado", () => {
    const base: Retiro[] = [
      { usd: 20, ts: AHORA - 1 * DIA, destino: "0xA" },
      { usd: 20, ts: AHORA - 2 * DIA, destino: "0xA" },
    ];
    const antes = detectStructuring(base, { thresholdUsd: 100 }, AHORA).acumuladoUsd;
    const despues = detectStructuring(
      [...base, { usd: 15, ts: AHORA - 3 * DIA, destino: "0xA" }],
      { thresholdUsd: 100 },
      AHORA,
    ).acumuladoUsd;
    expect(despues).toBeGreaterThanOrEqual(antes);
  });
});
