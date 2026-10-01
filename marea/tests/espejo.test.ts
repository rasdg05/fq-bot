import { describe, expect, it } from "vitest";
import { createMirrorOracle, resolverEspejo, type EstadoKalshi } from "@/adapters/oracles/mirrorOracle";
import { ESPEJOS, espejoSeed, espejosPendientes, POZO_ESPEJO } from "@/adapters/ownMarkets/espejos";
import { SHORT_TITLE_IDEAL, validateSeed } from "@/adapters/ownMarkets/catalog";
import { ruleProblems, type MirrorRule } from "@/domain/oracleRule";
import { initialState, onRead } from "@/domain/settlement";
import { rankedOutcomes, totalPool } from "@/domain/parimutuel";

/**
 * Mercados espejo: política, elecciones y geopolítica resueltos con la
 * liquidación pública de Kalshi. Los estados y la forma de la respuesta son
 * los medidos contra la API real el 2026-10-01 (active → closed → determined →
 * finalized; Banxico de septiembre: HOLD liquidado en «yes» a las 19:35 UTC).
 */

const m = (ticker: string, status: string, result = "", extra: Partial<EstadoKalshi> = {}): EstadoKalshi => ({
  ticker,
  status,
  result,
  ...extra,
});
const mapa = (...ms: EstadoKalshi[]) => new Map(ms.map((x) => [x.ticker, x]));

const CAMARA: MirrorRule = {
  kind: "espejo",
  fuente: "kalshi",
  evento: "CONTROLH-2026",
  respuestas: [
    { id: "dem", tickers: ["CONTROLH-2026-D"] },
    { id: "rep", tickers: ["CONTROLH-2026-R"] },
  ],
};
const BINARIO: MirrorRule = {
  kind: "espejo",
  fuente: "kalshi",
  evento: "KXUSAIRANAGREEMENT-27",
  respuestas: [
    { id: "si", tickers: ["KXUSAIRANAGREEMENT-27"], resultado: "yes" },
    { id: "no", tickers: ["KXUSAIRANAGREEMENT-27"], resultado: "no" },
  ],
};
const CON_OTRO: MirrorRule = {
  kind: "espejo",
  fuente: "kalshi",
  evento: "KXVENEZUELALEADER-26DEC31",
  respuestas: [
    { id: "maduro", tickers: ["KXVENEZUELALEADER-26DEC31-NMAD"] },
    { id: "delcy", tickers: ["KXVENEZUELALEADER-26DEC31-DROD"] },
    { id: "otro", tickers: [] },
  ],
};

describe("Oráculo espejo — cuándo se paga", () => {
  it("paga sólo con `finalized`: el ganador y la fecha del dato salen de Kalshi", () => {
    const r = resolverEspejo(
      CAMARA,
      mapa(
        m("CONTROLH-2026-D", "finalized", "yes", { settlement_ts: "2026-11-05T03:00:00Z" }),
        m("CONTROLH-2026-R", "finalized", "no"),
      ),
    );
    expect(r.status).toBe("resuelto");
    if (r.status !== "resuelto") return;
    expect(r.outcome).toBe("dem");
    // la fecha del dato, no la de la consulta (L8)
    expect(r.observedAt).toBe("2026-11-05T03:00:00Z");
    expect(r.evidence).toMatch(/api\.elections\.kalshi\.com.*CONTROLH-2026-D/);
  });

  it("con `determined` todavía no paga, pero deja de aceptar apuestas", () => {
    const r = resolverEspejo(
      CAMARA,
      mapa(m("CONTROLH-2026-D", "determined", "yes"), m("CONTROLH-2026-R", "determined", "no")),
    );
    expect(r).toMatchObject({ status: "sin_dato", detenerApuestas: true });
  });

  it("binario de un solo mercado: «no» liquidado paga «no»", () => {
    const r = resolverEspejo(BINARIO, mapa(m("KXUSAIRANAGREEMENT-27", "finalized", "no")));
    expect(r).toMatchObject({ status: "resuelto", outcome: "no" });
  });

  it("«ninguno de los anteriores» gana sólo cuando todos los nombrados liquidaron en «no»", () => {
    const abierta = resolverEspejo(
      CON_OTRO,
      mapa(m("KXVENEZUELALEADER-26DEC31-NMAD", "finalized", "no"), m("KXVENEZUELALEADER-26DEC31-DROD", "active")),
    );
    expect(abierta.status).toBe("sin_dato");
    const cerrada = resolverEspejo(
      CON_OTRO,
      mapa(m("KXVENEZUELALEADER-26DEC31-NMAD", "finalized", "no"), m("KXVENEZUELALEADER-26DEC31-DROD", "finalized", "no")),
    );
    expect(cerrada).toMatchObject({ status: "resuelto", outcome: "otro" });
  });

  it("una pata descartada no detiene las apuestas de las demás", () => {
    // un candidato que se baja: Kalshi lo liquida en «no» y los otros siguen operando
    const r = resolverEspejo(
      CON_OTRO,
      mapa(m("KXVENEZUELALEADER-26DEC31-NMAD", "active"), m("KXVENEZUELALEADER-26DEC31-DROD", "finalized", "no")),
    );
    expect(r.status).toBe("sin_dato");
    expect("detenerApuestas" in r && r.detenerApuestas).toBeFalsy();
  });

  it("todas las patas cerradas detienen las apuestas aunque no haya resultado", () => {
    const r = resolverEspejo(
      CAMARA,
      mapa(m("CONTROLH-2026-D", "closed"), m("CONTROLH-2026-R", "closed")),
    );
    expect(r).toMatchObject({ status: "sin_dato", detenerApuestas: true });
  });

  it("nada se adivina: liquidado sin ganador reconocible no paga a nadie", () => {
    const r = resolverEspejo(
      CAMARA,
      mapa(m("CONTROLH-2026-D", "finalized", "void"), m("CONTROLH-2026-R", "finalized", "void")),
    );
    expect(r.status).toBe("sin_dato");
  });

  it("un ticker que falta no decide nada", () => {
    expect(resolverEspejo(CAMARA, mapa(m("CONTROLH-2026-D", "finalized", "yes"))).status).toBe(
      "sin_dato",
    );
  });

  it("con Kalshi caído, el oráculo responde sin dato y no detiene", async () => {
    const oraculo = createMirrorOracle({
      cargarEventoKalshi: async () => {
        throw new Error("Kalshi respondió 503");
      },
    });
    const r = await oraculo.read({ marketId: "x", spec: {} as never, rule: CAMARA, now: 0 });
    expect(r).toMatchObject({ status: "sin_dato" });
    expect("detenerApuestas" in r && r.detenerApuestas).toBeFalsy();
  });
});

describe("Liquidación — `detenerApuestas` cierra un mercado abierto", () => {
  it("abierto → cerrado, sin resultado todavía", () => {
    const estado = onRead(
      initialState("pol"),
      { status: "sin_dato", evidence: "ya se conoce", detenerApuestas: true },
      {} as never,
      0,
    );
    expect(estado.phase).toBe("cerrado");
    expect(estado.outcome).toBeUndefined();
  });

  it("un `sin_dato` normal no cierra nada", () => {
    const estado = onRead(initialState("pol"), { status: "sin_dato", evidence: "abierto" }, {} as never, 0);
    expect(estado.phase).toBe("abierto");
  });
});

/** Precios de Kalshi de prueba para todos los tickers curados. */
function preciosDe(curado: (typeof ESPEJOS)[number], status = "active") {
  const tickers = [...new Set(curado.respuestas.flatMap((r) => r.tickers))];
  return mapa(
    ...tickers.map((t, i) =>
      m(t, status, "", { yes_bid_dollars: (0.6 / (i + 1)).toFixed(3), yes_ask_dollars: (0.62 / (i + 1)).toFixed(3) }),
    ),
  );
}

describe("Espejos curados — la semilla", () => {
  it("cada espejo curado pasa la validación de producción", () => {
    for (const curado of ESPEJOS) {
      const seed = espejoSeed(curado, preciosDe(curado));
      expect(seed, curado.id).not.toBeNull();
      expect(() => validateSeed(seed!), curado.id).not.toThrow();
      // se cierra antes del evento, nunca después de liquidar
      expect(Date.parse(seed!.closesAt)).toBeLessThan(Date.parse(seed!.resolution.settlesAt));
    }
  });

  it("cada título corto cabe entero en la línea de la tarjeta (medido, no estimado)", () => {
    for (const curado of ESPEJOS) {
      expect(curado.shortTitle.length, curado.shortTitle).toBeLessThanOrEqual(SHORT_TITLE_IDEAL);
    }
  });

  it("el pozo nace con la probabilidad de Kalshi, no en 50/50", () => {
    const camara = ESPEJOS.find((c) => c.id === "pol-eeuu-camara-2026")!;
    const seed = espejoSeed(
      camara,
      mapa(
        m("CONTROLH-2026-D", "active", "", { yes_bid_dollars: "0.914", yes_ask_dollars: "0.915" }),
        m("CONTROLH-2026-R", "active", "", { yes_bid_dollars: "0.085", yes_ask_dollars: "0.087" }),
      ),
    )!;
    const [lider] = rankedOutcomes(seed.pool, seed.outcomes!);
    expect(lider.id).toBe("dem");
    expect(lider.probability).toBeGreaterThan(0.88);
    expect(totalPool(seed.pool)).toBeGreaterThanOrEqual(POZO_ESPEJO - 2);
  });

  it("ninguna respuesta nace con el pozo vacío: piso del 3 %", () => {
    const congreso = ESPEJOS.find((c) => c.id === "pol-eeuu-congreso-2026")!;
    const precios = mapa(
      ...congreso.respuestas.map((r, i) =>
        m(r.tickers[0], "active", "", { yes_bid_dollars: i === 0 ? "0.99" : "0.001", yes_ask_dollars: i === 0 ? "0.99" : "0.002" }),
      ),
    );
    const seed = espejoSeed(congreso, precios)!;
    for (const valor of Object.values(seed.pool.outcomes)) {
      expect(valor / totalPool(seed.pool)).toBeGreaterThanOrEqual(0.025);
    }
  });

  it("sin precio o con el evento ya sin operar, no se crea: nunca un 50/50 inventado", () => {
    const camara = ESPEJOS.find((c) => c.id === "pol-eeuu-camara-2026")!;
    expect(espejoSeed(camara, mapa(m("CONTROLH-2026-D", "active"), m("CONTROLH-2026-R", "active")))).toBeNull();
    expect(espejoSeed(camara, preciosDe(camara, "closed"))).toBeNull();
  });

  it("la regla no acepta un ticker de otro evento ni un criterio que no nombre la fuente", () => {
    const ajeno: MirrorRule = { ...CAMARA, respuestas: [...CAMARA.respuestas, { id: "x", tickers: ["CONTROLS-2026-D"] }] };
    expect(ruleProblems(ajeno, "Se resuelve con Kalshi.").join()).toMatch(/no pertenece/);
    expect(ruleProblems(CAMARA, "Se resuelve con el marcador.").join()).toMatch(/Kalshi/);
  });

  it("los pendientes: sólo los que faltan y siguen abiertos; un evento caído no tapa a los demás", async () => {
    const ahora = Date.parse("2026-10-01T12:00:00Z");
    const { seeds, errores } = await espejosPendientes({
      ahora,
      existentes: new Set(["pol-eeuu-camara-2026"]),
      cargarEvento: async (evento) => {
        if (evento === "CONTROLS-2026") throw new Error("Kalshi respondió 429");
        const curado = ESPEJOS.find((c) => c.evento === evento)!;
        return [...preciosDe(curado).values()];
      },
    });
    const ids = seeds.map((s) => s.id);
    expect(ids).not.toContain("pol-eeuu-camara-2026"); // ya existía
    expect(ids).not.toContain("pol-eeuu-senado-2026"); // su evento falló
    expect(errores.join()).toMatch(/pol-eeuu-senado-2026.*429/);
    expect(ids.length).toBe(ESPEJOS.length - 2);
  });
});
