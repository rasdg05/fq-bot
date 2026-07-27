import { describe, expect, it } from "vitest";
import { EDGE_MIN_PP, computeEdge, formatEdgePp, hasEdge, withEdge } from "@/domain/edge";
import { ERROR_CODES, appError, toAppError } from "@/domain/errors";
import { MOCK_MARKETS } from "@/adapters/mock/markets";
import { S } from "@/lib/strings";

describe("Edge", () => {
  it("V4 — el Edge sólo existe si la diferencia llega a 4 pp", () => {
    expect(EDGE_MIN_PP).toBe(4);
    // por debajo del umbral: no hay Edge (R-001)
    expect(computeEdge(0.5, 0.53)).toBeNull();
    expect(computeEdge(0.5, 0.539)).toBeNull();
    expect(computeEdge(0.5, 0.47)).toBeNull();
    // justo en el umbral: sí
    expect(computeEdge(0.5, 0.54)).toBe(4);
    expect(computeEdge(0.5, 0.46)).toBe(-4);
    // sin lectura propia no hay Edge
    expect(computeEdge(0.5, undefined)).toBeNull();
  });

  it("V4 — ningún mercado del adapter expone un Edge por debajo del umbral", () => {
    for (const market of MOCK_MARKETS) {
      if (market.edge !== null) {
        expect(Math.abs(market.edge)).toBeGreaterThanOrEqual(EDGE_MIN_PP);
      }
      if (market.mareaProbability !== undefined) {
        const diff = Math.abs(market.mareaProbability - market.probability) * 100;
        if (diff < EDGE_MIN_PP) expect(market.edge).toBeNull();
      } else {
        expect(market.edge).toBeNull();
      }
    }
    // el set de prueba contiene ambos casos, si no la validación no probaría nada
    expect(MOCK_MARKETS.some((m) => m.edge !== null)).toBe(true);
    expect(MOCK_MARKETS.some((m) => m.edge === null)).toBe(true);
  });

  it("el signo del Edge se lee sin depender del color (R-005)", () => {
    expect(formatEdgePp(7)).toBe("+7");
    expect(formatEdgePp(-5.5)).toBe("−5.5");
    expect(S.market.edgeCard(formatEdgePp(7))).toBe("Marea +7%");
    expect(S.market.edgeDetail("62", "69", "+7")).toBe(
      "Mercado 62% · Marea 69% · Edge +7%",
    );
  });

  it("withEdge es el único camino al campo edge", () => {
    const market = withEdge({
      id: "x",
      title: "t",
      probability: 0.4,
      volume: 1,
      status: "open",
      category: "cripto",
      resolution_summary: "r",
      mareaProbability: 0.5,
    });
    expect(market.edge).toBe(10);
    expect(hasEdge(market)).toBe(true);
  });
});

describe("Catálogo de errores", () => {
  it("V23 — todo error del catálogo trae mensaje en español y bandera de reintento", () => {
    expect(ERROR_CODES).toHaveLength(11);
    for (const code of ERROR_CODES) {
      const error = appError(code);
      expect(error.user_message_es.length).toBeGreaterThan(15);
      expect(typeof error.retryable).toBe("boolean");
      // el mensaje es prosa, no un código ni un stack (R-008)
      expect(error.user_message_es).not.toMatch(/E_[A-Z_]+|Error:|at\s+\w+\s+\(/);
      expect(error.user_message_es).toMatch(/[áéíóúñ¿¡]|[a-z]{3,}\s[a-z]{2,}/i);
    }
  });

  it("V23 — el proveedor caído no es reintentable y ofrece alternativa", () => {
    const error = appError("E_DEPOSIT_PROVIDER_UNAVAILABLE");
    expect(error.retryable).toBe(false);
    expect(error.user_message_es).toMatch(/transferencia/i);
  });

  it("cualquier excepción cruda se normaliza antes de llegar a la vista", () => {
    const error = toAppError(new Error("boom at line 42"), "E_MARKETS_FETCH_FAILED");
    expect(error.code).toBe("E_MARKETS_FETCH_FAILED");
    expect(error.user_message_es).not.toContain("boom");
    expect(error.context?.cause).toBe("boom at line 42");
  });
});
