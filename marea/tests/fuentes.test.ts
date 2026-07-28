import { describe, expect, it } from "vitest";
import { createSeriesOracle, type Observacion } from "@/adapters/oracles/seriesOracle";
import { readWithOracles } from "@/domain/settlement";
import type { SeriesRule } from "@/domain/oracleRule";
import { OWN_MARKETS } from "@/adapters/ownMarkets/catalog";

/**
 * Fuentes nuevas: BCRA (Argentina), BCRP (Perú) e INEGI (México).
 *
 * Las tres se agregaron porque **existen y responden**. Antes de decir que un
 * mercado necesita a una persona se busca el endpoint (R-051); estos tres
 * estaban a un `curl` de distancia, y mientras tanto el catálogo llevaba seis
 * mercados dependiendo de que alguien se sentara a mirarlos, con un tope de
 * tres que nadie verificaba (R-062).
 */

const spec = {
  sourceName: "fuente",
  sourceUrl: "https://ejemplo.test/serie",
  criterion: "Se resuelve Sí si el dato queda por debajo de 3.00 por ciento.",
  settlesAt: "2026-08-10T12:00:00Z",
  disputeWindowHours: 24,
};

const AHORA = Date.parse("2026-08-10T13:00:00Z");

async function leer(rule: SeriesRule, datos: Observacion[], opciones = {}) {
  const oracle = createSeriesOracle({ cargar: async () => datos, ...opciones });
  const { reading } = await readWithOracles([oracle], {
    marketId: "m",
    spec,
    rule,
    now: AHORA,
  });
  return reading;
}

describe("Fuentes que no necesitaban a una persona", () => {
  it("BCRA · una tasa que baja resuelve Sí, y una que sube resuelve No", async () => {
    const rule: SeriesRule = {
      kind: "serie",
      fuente: "bcra",
      serie: "7",
      comparacion: "baja",
      etiqueta: "Tasa BADLAR de bancos privados",
    };
    const bajando = await leer(rule, [
      { fecha: Date.parse("2026-08-08T00:00:00Z"), valor: 24.5 },
      { fecha: Date.parse("2026-08-10T00:00:00Z"), valor: 22.0 },
    ]);
    expect(bajando.status).toBe("resuelto");
    if (bajando.status === "resuelto") {
      expect(bajando.outcome).toBe("si");
      // la evidencia dice de dónde salió: un pago no es un acto de fe
      expect(bajando.evidence).toContain("BADLAR");
      expect(bajando.evidence).toContain("22");
    }

    const subiendo = await leer(rule, [
      { fecha: Date.parse("2026-08-08T00:00:00Z"), valor: 22.0 },
      { fecha: Date.parse("2026-08-10T00:00:00Z"), valor: 24.5 },
    ]);
    if (subiendo.status === "resuelto") expect(subiendo.outcome).toBe("no");
    else throw new Error("no resolvió");
  });

  it("BCRP · compara la inflación contra su umbral", async () => {
    const rule: SeriesRule = {
      kind: "serie",
      fuente: "bcrp",
      serie: "PN01279PM",
      comparacion: "menor",
      umbral: 3,
      etiqueta: "Inflación anual de Lima Metropolitana",
    };
    const abajo = await leer(rule, [
      { fecha: Date.parse("2026-08-10T00:00:00Z"), valor: 2.53 },
    ]);
    if (abajo.status === "resuelto") {
      expect(abajo.outcome).toBe("si");
      expect(abajo.evidence).toContain("2.53");
    } else throw new Error("no resolvió");

    const arriba = await leer(rule, [
      { fecha: Date.parse("2026-08-10T00:00:00Z"), valor: 3.4 },
    ]);
    if (arriba.status === "resuelto") expect(arriba.outcome).toBe("no");
    else throw new Error("no resolvió");
  });

  it("INEGI sin token no inventa: dice exactamente qué falta (R-022)", async () => {
    const rule: SeriesRule = {
      kind: "serie",
      fuente: "inegi",
      serie: "628194",
      comparacion: "menor",
      umbral: 4,
      etiqueta: "INPC anual",
    };
    const oracle = createSeriesOracle({ inegiToken: "" });
    const { reading } = await readWithOracles([oracle], {
      marketId: "m",
      spec,
      rule,
      now: AHORA,
    });
    expect(reading.status).toBe("requiere_humano");
    expect(reading.evidence).toMatch(/INEGI_TOKEN/);
    // y dice dónde se saca, para que la instrucción sea accionable
    expect(reading.evidence).toMatch(/inegi\.org\.mx/);
  });

  it("INEGI con token resuelve solo", async () => {
    const rule: SeriesRule = {
      kind: "serie",
      fuente: "inegi",
      serie: "628194",
      comparacion: "menor",
      umbral: 4,
      etiqueta: "INPC anual",
    };
    const reading = await leer(
      rule,
      [{ fecha: Date.parse("2026-08-10T00:00:00Z"), valor: 3.71 }],
      { inegiToken: "un-token" },
    );
    if (reading.status === "resuelto") expect(reading.outcome).toBe("si");
    else throw new Error("no resolvió");
  });

  it("un dato viejo no resuelve un mercado nuevo (R-052)", async () => {
    const rule: SeriesRule = {
      kind: "serie",
      fuente: "bcrp",
      serie: "PN01279PM",
      comparacion: "menor",
      umbral: 3,
      etiqueta: "Inflación anual de Lima Metropolitana",
    };
    // el último dato es de un mes antes de que el mercado resuelva
    const viejo = await leer(rule, [
      { fecha: Date.parse("2026-07-01T00:00:00Z"), valor: 2.5 },
    ]);
    expect(viejo.status).toBe("sin_dato");
  });
});

describe("R-062 · cero confirmación humana", () => {
  it("ningún mercado del catálogo depende de que alguien lo mire", () => {
    // El tope dejó de ser tres y pasó a ser cero. Un mercado que hay que
    // confirmar a mano no dice quién lo confirma, ni cuándo, ni cómo: sin nadie
    // de guardia es una promesa que no se puede cumplir, y publicar mercados
    // sin proceso de resolución rompe lo único que sostiene el producto (R-040).
    const aMano = OWN_MARKETS.filter((seed) => !seed.rule);
    expect(
      aMano.length,
      `dependen de una persona: ${aMano.map((s) => s.id).join(", ") || "ninguno"}`,
    ).toBe(0);
  });

  it("cada regla apunta a una fuente que el oráculo sabe leer", () => {
    const conocidas = new Set([
      "bcb", "banxico", "bcra", "bcrp", "inegi", "mindicador", "datosgov",
    ]);
    for (const seed of OWN_MARKETS) {
      if (seed.rule?.kind === "serie") {
        expect(conocidas.has(seed.rule.fuente), `${seed.id}: ${seed.rule.fuente}`).toBe(true);
      }
    }
  });

  it("cada mercado con fuente automatizable la usa, no espera a un humano", () => {
    // las tres fuentes que se enchufaron en esta unidad
    const automatizados = OWN_MARKETS.filter((seed) =>
      [
        "ar-badlar-tasa",
        "pe-inflacion-lima",
        "mx-inpc-anual",
        "cl-imacec",
        "co-dolar-trm",
      ].includes(seed.id),
    );
    expect(automatizados).toHaveLength(5);
    for (const seed of automatizados) {
      expect(seed.rule, `${seed.id} sigue sin regla`).toBeDefined();
      expect(seed.rule!.kind).toBe("serie");
    }
  });
});
