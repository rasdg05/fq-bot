import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { defaultOracles } from "@/adapters/oracles/priceOracle";
import { seResuelveSolo, type OracleRule } from "@/domain/oracleRule";
import { OWN_MARKETS, type OwnMarketSeed } from "@/adapters/ownMarkets/catalog";
import { sismoSeed } from "@/adapters/ownMarkets/sismos";
import { Store } from "../server/store.mts";
import { reponer } from "../server/reposicion.mts";

/**
 * La promesa de los mercados rápidos: **lo que se genera solo se resuelve
 * solo**. Dos mitades, y las dos se prueban:
 *
 *  1. la lista de reglas «automáticas» es verdad — para cada una hay un
 *     oráculo por defecto que la reclama y que no es el de confirmación humana;
 *  2. la reposición no publica un candidato que no se resuelva solo.
 */

/** Una regla mínima de cada tipo. Si se agrega un tipo, el compilador pide su ejemplo aquí. */
const EJEMPLOS: Record<OracleRule["kind"], OracleRule> = {
  precio: { kind: "precio", par: "BTC/USD", umbral: 70000, comparacion: "arriba", modo: "cierre" },
  vela: { kind: "vela", par: "USD/MXN", intervalo: 15, inicio: 0, strike: 18.1 },
  serie: { kind: "serie" } as OracleRule,
  partido: { kind: "partido" } as OracleRule,
  partido_multiple: { kind: "partido_multiple" } as OracleRule,
  espejo: { kind: "espejo", fuente: "kalshi", evento: "X", respuestas: [] },
  tenis: { kind: "tenis", circuito: "atp", partido: "1", fecha: "2026-10-01", jugador: "A", rival: "B" },
  tendencia: { kind: "tendencia", fuente: "wikipedia", proyecto: "es.wikipedia", fecha: "2026-10-01", articulos: [] },
  sismo: { kind: "sismo", fuente: "usgs", region: "MX", magnitudMin: 5, desde: "a", hasta: "b" },
};

describe("Resolución automática y obligatoria", () => {
  it("cada regla declarada automática la reclama un oráculo que no es el humano", () => {
    const oraculos = defaultOracles().filter((o) => o.id !== "institucional");
    for (const [kind, rule] of Object.entries(EJEMPLOS)) {
      expect(seResuelveSolo(rule), kind).toBe(true);
      const quien = oraculos.find((o) => o.handles({ marketId: "x", spec: {} as never, rule, now: 0 }));
      expect(quien, `nadie resuelve «${kind}» en automático`).toBeDefined();
    }
  });

  it("sin regla, o con un tipo que nadie lee, no se resuelve solo", () => {
    expect(seResuelveSolo(undefined)).toBe(false);
    expect(seResuelveSolo({ kind: "mañanera" })).toBe(false);
  });

  it("la reposición no publica un candidato sin oráculo automático, y lo dice", async () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-auto-"));
    try {
      const store = new Store(dir);
      const ahora = Date.parse("2026-10-01T12:00:00Z");
      const conRegla = sismoSeed(Date.parse("2026-10-05T06:00:00Z"));
      const sinRegla: OwnMarketSeed = { ...conRegla, id: "a-mano-sin-oraculo", rule: undefined };
      const abiertos = Array.from({ length: 70 }, (_, i) => ({
        ...OWN_MARKETS[0],
        id: `abierto-${i}`,
        closesAt: new Date(ahora + 30 * 86_400_000).toISOString(),
      }));
      const r = await reponer(store, abiertos, ahora, {
        env: {},
        curados: async () => ({ seeds: [conRegla, sinRegla], errores: [] }),
      });
      expect(r.creados).toEqual([conRegla.id]);
      expect(r.errores.join()).toMatch(/a-mano-sin-oraculo: sin oráculo automático/);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
