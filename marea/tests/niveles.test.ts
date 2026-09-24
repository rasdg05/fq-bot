import { describe, expect, it } from "vitest";
import {
  ESCALERA,
  NIVELES,
  N2_CAP_USD_PROVISIONAL,
  capNivel,
  effectiveCapForUser,
  effectiveCapUsd,
} from "@/domain/niveles";

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
