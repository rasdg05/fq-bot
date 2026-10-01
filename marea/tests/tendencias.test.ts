import { describe, expect, it, vi } from "vitest";
import {
  createTrendOracle,
  resolverTendencia,
} from "@/adapters/oracles/trendOracle";
import {
  dueloSeed,
  esCandidato,
  nombreLegible,
  tendenciasPendientes,
  type ArticuloTop,
  type FuentesTendencias,
} from "@/adapters/ownMarkets/tendencias";
import { validateSeed } from "@/adapters/ownMarkets/catalog";
import { rankedOutcomes } from "@/domain/parimutuel";
import { ruleProblems, type TrendRule } from "@/domain/oracleRule";

/**
 * Duelos de tendencias contra la API pública de Wikimedia. Los resúmenes y las
 * cifras son los medidos el 2026-10-01 (top de Wikipedia en español del 30 de
 * septiembre; Diego Luna 416 contra Bad Bunny 1,259 el 29).
 */

const RULE: TrendRule = {
  kind: "tendencia",
  fuente: "wikipedia",
  proyecto: "es.wikipedia",
  fecha: "2026-09-29",
  articulos: [
    { id: "a", titulo: "Diego_Luna" },
    { id: "b", titulo: "Bad_Bunny" },
  ],
};
const dias = (pares: Record<string, number>) => new Map(Object.entries(pares));

describe("Oráculo de tendencias — cuándo se paga", () => {
  it("gana quien tuvo más visitas ese día, y la evidencia cita la URL de Wikimedia", () => {
    const r = resolverTendencia(RULE, [dias({ "2026-09-29": 416 }), dias({ "2026-09-29": 1259 })]);
    expect(r).toMatchObject({ status: "resuelto", outcome: "b" });
    expect(r.evidence).toMatch(/416.*1,259.*wikimedia\.org.*Diego_Luna/);
    // la fecha del dato es el final de ese día, no la de la consulta (L8)
    if (r.status === "resuelto") expect(r.observedAt).toBe("2026-09-29T23:59:59.000Z");
  });

  it("empate exacto: decide el día anterior", () => {
    const r = resolverTendencia(RULE, [
      dias({ "2026-09-28": 900, "2026-09-29": 500 }),
      dias({ "2026-09-28": 300, "2026-09-29": 500 }),
    ]);
    expect(r).toMatchObject({ status: "resuelto", outcome: "a" });
  });

  it("un día sin visitas cuenta como cero, pero sólo si el día ya está publicado", () => {
    expect(resolverTendencia(RULE, [dias({}), dias({ "2026-09-29": 3 })])).toMatchObject({
      status: "resuelto",
      outcome: "b",
    });
    // ninguno de los dos tiene el día: no está publicado, no «ganó el cero»
    expect(resolverTendencia(RULE, [dias({ "2026-09-28": 5 }), dias({})]).status).toBe("sin_dato");
  });

  it("no lee nada antes de que termine el día UTC (más una hora de gracia)", async () => {
    const cargarVisitas = vi.fn(async () => dias({}));
    const oraculo = createTrendOracle({ cargarVisitas });
    const r = await oraculo.read({ marketId: "x", spec: {} as never, rule: RULE, now: Date.parse("2026-09-30T00:30:00Z") });
    expect(r.status).toBe("sin_dato");
    expect(cargarVisitas).not.toHaveBeenCalled();
  });
});

const RESUMENES: Record<string, { type: string; description: string; extract: string }> = {
  // medidos el 2026-10-01 en es.wikipedia.org/api/rest_v1/page/summary
  Christa_Pike: { type: "standard", description: "Asesina juvenil", extract: "Christa Gail Pike fue una asesina convicta estadounidense condenada a muerte." },
  Otto_Sirgo: { type: "standard", description: "actor cubano-mexicano", extract: "Otto Sirgo Haller fue un actor y director escénico cubano, nacionalizado mexicano." },
  Lizzie_Borden: { type: "standard", description: "mujer estadounidense sospechosa de asesinato", extract: "Lizzie Andrew Borden, fue la única sospechosa de los asesinatos de su padre." },
  Diego_Luna: { type: "standard", description: "actor y director mexicano", extract: "Diego Dionisio Luna Alexander es un actor y director mexicano de televisión, teatro y cine." },
  "La_bola_negra_(película)": { type: "standard", description: "película de 2026 dirigida por Los Javis", extract: "La bola negra es una película dramática dirigida por Javier Ambrossi y Javier Calvo." },
  Jorge_Jesus: { type: "standard", description: "entrenador portugués", extract: "Jorge Fernando Pinheiro de Jesus es un exjugador y entrenador de fútbol portugués." },
  ChatGPT: { type: "standard", description: "bot de charla", extract: "ChatGPT es una aplicación de chatbot de inteligencia artificial generativa." },
};

describe("Tendencias — lo que no se pregunta", () => {
  it("ni la atención a una muerte, ni a un crimen, ni lo que no es un artículo", () => {
    expect(esCandidato("Christa_Pike", RESUMENES.Christa_Pike)).toBe(false);
    expect(esCandidato("Otto_Sirgo", RESUMENES.Otto_Sirgo)).toBe(false);
    expect(esCandidato("Lizzie_Borden", RESUMENES.Lizzie_Borden)).toBe(false);
    expect(esCandidato("Wikipedia:Portada", { type: "standard" })).toBe(false);
    expect(esCandidato("Especial:Buscar", { type: "standard" })).toBe(false);
    expect(esCandidato("Mercurio", { type: "disambiguation" })).toBe(false);
    expect(esCandidato("Diego_Luna", RESUMENES.Diego_Luna)).toBe(true);
    // sin resumen legible no se adivina: fuera
    expect(esCandidato("Diego_Luna", undefined)).toBe(false);
  });
});

const TOP: ArticuloTop[] = [
  { article: "Wikipedia:Portada", views: 469816, rank: 1 },
  { article: "Christa_Pike", views: 86255, rank: 2 },
  { article: "Especial:Buscar", views: 83716, rank: 3 },
  { article: "Otto_Sirgo", views: 61446, rank: 5 },
  { article: "Lizzie_Borden", views: 32652, rank: 6 },
  { article: "La_bola_negra_(película)", views: 27967, rank: 8 },
  { article: "Diego_Luna", views: 26185, rank: 9 },
  { article: "Jorge_Jesus", views: 11486, rank: 15 },
  { article: "ChatGPT", views: 8627, rank: 22 },
];

function fuentes(): FuentesTendencias & { top: ReturnType<typeof vi.fn> } {
  return {
    top: vi.fn(async (dia: string) => (dia === "2026-09-30" ? TOP : undefined)),
    resumen: async (titulo: string) => RESUMENES[titulo],
  };
}

describe("Tendencias — los duelos de mañana", () => {
  const AHORA = Date.parse("2026-10-01T12:00:00Z");

  it("empareja por rangos vecinos lo que pasa el filtro, y cada duelo pasa la validación de producción", async () => {
    const r = await tendenciasPendientes({ ahora: AHORA, existentes: new Set(), fuentes: fuentes() });
    expect(r.seeds.map((s) => s.id)).toEqual(["wiki-2026-10-02-1", "wiki-2026-10-02-2"]);
    const [uno, dos] = r.seeds.map(validateSeed);
    expect(uno.outcomes!.map((o) => o.label)).toEqual(["La bola negra", "Diego Luna"]);
    expect(dos.outcomes!.map((o) => o.label)).toEqual(["Jorge Jesus", "ChatGPT"]);
    // cierra al empezar el día que se mide
    expect(uno.closesAt).toBe("2026-10-02T00:00:00.000Z");
    expect(ruleProblems(uno.rule as TrendRule, uno.resolution.criterion)).toEqual([]);
  });

  it("la semilla sigue las visitas del día de referencia, con piso del 15 %", () => {
    const parejo = dueloSeed({
      numero: 1,
      fecha: "2026-10-02",
      a: TOP[5],
      b: TOP[6],
      diaReferencia: "2026-09-30",
    });
    const [lider] = rankedOutcomes(parejo.pool, parejo.outcomes!);
    expect(lider.probability).toBeCloseTo(27967 / (27967 + 26185), 1);
    const disparejo = dueloSeed({ numero: 2, fecha: "2026-10-02", a: TOP[0], b: TOP[8], diaReferencia: "2026-09-30" });
    for (const o of rankedOutcomes(disparejo.pool, disparejo.outcomes!)) expect(o.probability).toBeGreaterThanOrEqual(0.14);
  });

  it("si los duelos de mañana ya existen, no se le pregunta nada a Wikimedia", async () => {
    const f = fuentes();
    await tendenciasPendientes({ ahora: AHORA, existentes: new Set(["wiki-2026-10-02-1"]), fuentes: f });
    expect(f.top).not.toHaveBeenCalled();
  });

  it("a menos de tres horas de medianoche no se abre: no daría tiempo de entrar", async () => {
    const r = await tendenciasPendientes({ ahora: Date.parse("2026-10-01T22:00:00Z"), existentes: new Set(), fuentes: fuentes() });
    expect(r.seeds).toEqual([]);
  });

  it("los nombres se leen sin guiones bajos ni la aclaración entre paréntesis", () => {
    expect(nombreLegible("La_bola_negra_(película)")).toBe("La bola negra");
  });
});
