import { describe, expect, it, vi } from "vitest";
import { createQuakeOracle, enMexico, resolverSismo, type SismoUsgs } from "@/adapters/oracles/quakeOracle";
import {
  MAGNITUD,
  TASA_BASE_SEMANAL,
  proximoLunesCdmx,
  sismoSeed,
  sismosPendientes,
} from "@/adapters/ownMarkets/sismos";
import { validateSeed } from "@/adapters/ownMarkets/catalog";
import { rankedOutcomes } from "@/domain/parimutuel";
import type { QuakeRule } from "@/domain/oracleRule";

/**
 * Sismos en México contra el catálogo del USGS. Lugares y estados copiados de
 * respuestas reales del 2026-10-01 (incluido el M5.3 frente a Michoacán del 14
 * de septiembre, us7000thgs).
 */

const LUNES = Date.parse("2026-09-14T06:00:00Z");
const RULE = sismoSeed(LUNES).rule as QuakeRule;
const H = 3_600_000;

const sismo = (place: string, mag: number, time: number, status = "reviewed"): SismoUsgs => ({
  id: `us${time}`,
  properties: { mag, place, time, status },
});

describe("Sismos — qué cuenta como «en México»", () => {
  it("lo que el USGS termina en «Mexico» o «MX», nunca «New Mexico»", () => {
    expect(enMexico(sismo("off the coast of Michoacan, Mexico", 5, 0))).toBe(true);
    expect(enMexico(sismo("9 km NNW of Delta, B.C., MX", 5, 0))).toBe(true);
    expect(enMexico(sismo("20 km S of Socorro, New Mexico", 5, 0))).toBe(false);
    expect(enMexico(sismo("Gulf of California", 5, 0))).toBe(false);
    expect(enMexico(sismo("60 km SSW of Ocós, Guatemala", 5, 0))).toBe(false);
  });
});

describe("Sismos — cuándo se paga", () => {
  const martes = LUNES + 36 * H;

  it("un M5.3 revisado dentro de la semana paga «sí» en cuanto aparece", () => {
    const r = resolverSismo(RULE, [sismo("off the coast of Michoacan, Mexico", 5.3, martes)], martes + H);
    expect(r).toMatchObject({ status: "resuelto", outcome: "si" });
    expect(r.evidence).toMatch(/M5\.3.*Michoacan.*reviewed/);
  });

  it("uno sin revisar todavía no paga, pero detiene; pasadas 72 h de la semana, vale lo publicado", () => {
    const auto = [sismo("off the coast of Guerrero, Mexico", 5.1, martes, "automatic")];
    expect(resolverSismo(RULE, auto, martes + H)).toMatchObject({ status: "sin_dato", detenerApuestas: true });
    const fin = Date.parse(RULE.hasta);
    expect(resolverSismo(RULE, auto, fin + 73 * H)).toMatchObject({ status: "resuelto", outcome: "si" });
  });

  it("un 4.9, uno en Guatemala o uno fuera de la semana no cuentan", () => {
    const fin = Date.parse(RULE.hasta);
    const ruido = [
      sismo("off the coast of Michoacan, Mexico", 4.9, martes),
      sismo("60 km SSW of Ocós, Guatemala", 6.1, martes),
      sismo("off the coast of Michoacan, Mexico", 6.0, fin + H),
    ];
    expect(resolverSismo(RULE, ruido, fin + 2 * H).status).toBe("sin_dato"); // falta el día de margen
    expect(resolverSismo(RULE, ruido, fin + 25 * H)).toMatchObject({ status: "resuelto", outcome: "no" });
  });

  it("antes de que empiece la semana no se consulta nada", async () => {
    const cargarSismos = vi.fn(async () => []);
    const r = await createQuakeOracle({ cargarSismos }).read({ marketId: "x", spec: {} as never, rule: RULE, now: LUNES - H });
    expect(r.status).toBe("sin_dato");
    expect(cargarSismos).not.toHaveBeenCalled();
  });
});

describe("Sismos — el mercado de la semana que viene", () => {
  it("abre la semana que viene y cierra al empezar: nadie apuesta con la alerta en el celular", () => {
    // miércoles 1 de octubre, 12:00 UTC → lunes 5 de octubre, 00:00 CDMX
    expect(new Date(proximoLunesCdmx(Date.parse("2026-10-01T12:00:00Z"))).toISOString()).toBe("2026-10-05T06:00:00.000Z");
    // domingo 4 a las 23:00 CDMX (05:00 UTC del lunes) → todavía es el lunes 5
    expect(new Date(proximoLunesCdmx(Date.parse("2026-10-05T05:00:00Z"))).toISOString()).toBe("2026-10-05T06:00:00.000Z");
    // lunes 5 a las 00:30 CDMX → ya es la del 12
    expect(new Date(proximoLunesCdmx(Date.parse("2026-10-05T06:30:00Z"))).toISOString()).toBe("2026-10-12T06:00:00.000Z");
  });

  it("pasa la validación de producción y nace con la tasa medida, no en 50/50", () => {
    const seed = validateSeed(sismoSeed(Date.parse("2026-10-05T06:00:00Z")));
    expect(seed.shortTitle).toBe("Sismo M5+ en México (5–11 oct.)");
    expect(seed.closesAt).toBe("2026-10-05T06:00:00.000Z");
    const si = rankedOutcomes(seed.pool, seed.outcomes!).find((o) => o.id === "si")!;
    expect(si.probability).toBeCloseTo(TASA_BASE_SEMANAL, 1);
    expect(MAGNITUD).toBe(5);
  });

  it("idempotente: si ya existe la de la semana que viene, no se crea otra", () => {
    const ahora = Date.parse("2026-10-01T12:00:00Z");
    expect(sismosPendientes({ ahora, existentes: new Set() }).map((s) => s.id)).toEqual(["sismo-mx-2026-10-05"]);
    expect(sismosPendientes({ ahora, existentes: new Set(["sismo-mx-2026-10-05"]) })).toEqual([]);
  });
});
