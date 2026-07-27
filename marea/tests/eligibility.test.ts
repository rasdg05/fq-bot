import { describe, expect, it } from "vitest";
import {
  COUNTRY_POLICY,
  canDeposit,
  eligibilityFor,
  type CountryCode,
} from "@/domain/eligibility";
import { FLAGS } from "@/lib/flags";

const ALL = Object.keys(COUNTRY_POLICY) as CountryCode[];

describe("Elegibilidad por país", () => {
  it("explorar nunca se bloquea, en ningún país (R-002)", () => {
    for (const country of [...ALL, undefined]) {
      expect(eligibilityFor(country).canExplore).toBe(true);
    }
  });

  it("ningún país arranca habilitado sin opinión legal escrita", () => {
    for (const country of ALL) {
      const eligibility = eligibilityFor(country);
      expect(eligibility.canDeposit, `${country} no debe permitir depósitos aún`).toBe(false);
    }
  });

  it("Estados Unidos está bloqueado, no pendiente", () => {
    expect(COUNTRY_POLICY.US.status).toBe("bloqueado");
    const decision = canDeposit("US", 10, { depositedUsd: 0 });
    expect(decision.allowed).toBe(false);
    if (!decision.allowed) {
      expect(decision.reason).toBe("pais");
      // el mensaje invita a seguir explorando, no cierra la puerta entera
      expect(decision.message).toMatch(/explorando/i);
    }
  });

  it("un país habilitado respeta el tope acumulado", () => {
    const policy = { ...COUNTRY_POLICY };
    // simulamos la fila que quedaría tras una opinión legal favorable
    const habilitado = { status: "permitido" as const, depositCapUsd: 200, note: "" };
    Object.assign(COUNTRY_POLICY, { MX: habilitado });
    try {
      expect(canDeposit("MX", 50, { depositedUsd: 0 })).toEqual({
        allowed: true,
        remainingUsd: 150,
      });
      const over = canDeposit("MX", 60, { depositedUsd: 180 });
      expect(over.allowed).toBe(false);
      if (!over.allowed) expect(over.reason).toBe("tope");
    } finally {
      Object.assign(COUNTRY_POLICY, { MX: policy.MX });
    }
  });

  it("el enfriamiento manda sobre el tope", () => {
    Object.assign(COUNTRY_POLICY, {
      MX: { status: "permitido" as const, depositCapUsd: 200, note: "" },
    });
    try {
      const decision = canDeposit("MX", 10, { depositedUsd: 0, cooldownUntil: 5_000 }, 1_000);
      expect(decision.allowed).toBe(false);
      if (!decision.allowed) expect(decision.reason).toBe("enfriamiento");
    } finally {
      Object.assign(COUNTRY_POLICY, {
        MX: { status: "pendiente" as const, depositCapUsd: 0, note: "Falta opinión legal local." },
      });
    }
  });

  it("un país desconocido cae en el camino conservador", () => {
    const decision = canDeposit(undefined, 10, { depositedUsd: 0 });
    expect(decision.allowed).toBe(false);
  });

  it("la build simulada no aplica el bloqueo, y eso está declarado", () => {
    // mientras no se mueva dinero real la puerta queda abierta a propósito;
    // encenderla es requisito para cualquier build con dinero (COMPLIANCE §4)
    expect(FLAGS.eligibility_enforced).toBe(false);
    expect(FLAGS.mock_data).toBe(true);
  });
});
