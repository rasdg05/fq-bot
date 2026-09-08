import { describe, expect, it } from "vitest";
import {
  frescuraDe,
  initialState,
  onClose,
  onRead,
  resueltosSinFrescura,
  FRESCURA_MAX_HORAS,
  type OracleReading,
  type SettlementState,
} from "@/domain/settlement";
import type { ResolutionSpec } from "@/domain/resolution";
import { OWN_MARKETS } from "@/adapters/ownMarkets/catalog";

/**
 * L8 — frescura del oráculo. La deuda que arrastraba `onRead`: aceptaba una
 * lectura sin comprobar de cuándo era el dato.
 *
 * El fallo que previene no se parece a una caída. Una fuente parada contesta al
 * instante y con un 200; lo que la delata es que el dato que devuelve sigue
 * siendo el de anteayer. Es el mismo que en el bot obligó a cablear
 * `cvd_confirmation`.
 */

const HORA = 3_600_000;
const AHORA = Date.UTC(2026, 8, 8, 12, 0, 0);

const spec = (maxAgeHours?: number): ResolutionSpec => ({
  sourceName: "Kraken (velas diarias públicas)",
  sourceUrl: "https://api.kraken.com/0/public/OHLC?pair=XBTUSD",
  criterion: "Se resuelve Sí si la vela diaria de XBTUSD en Kraken cierra arriba de 1 dólar.",
  settlesAt: new Date(AHORA).toISOString(),
  disputeWindowHours: 12,
  ...(maxAgeHours !== undefined ? { maxAgeHours } : {}),
});

const lectura = (horasDeAntiguedad?: number): OracleReading => ({
  status: "resuelto",
  outcome: "si",
  evidence: "cierre 72,500 USD",
  ...(horasDeAntiguedad !== undefined
    ? { observedAt: new Date(AHORA - horasDeAntiguedad * HORA).toISOString() }
    : {}),
});

const cerrado = (): SettlementState => onClose(initialState("m1"));

describe("L8 — frescura del oráculo", () => {
  it("la antigüedad entra por parámetro: no hay reloj de pared aquí dentro", () => {
    const f = frescuraDe(lectura(10), spec(48), AHORA);
    expect(f.horas).toBeCloseTo(10, 9);
    // el mismo dato, juzgado desde otro momento, da otra antigüedad — y eso es
    // lo que permite que un replay no herede la hora del click
    expect(frescuraDe(lectura(10), spec(48), AHORA + 100 * HORA).horas).toBeCloseTo(110, 9);
  });

  it("una lectura más vieja que el umbral NO avanza de fase, y lo declara", () => {
    const estado = onRead(cerrado(), lectura(72), spec(48), AHORA);
    expect(estado.phase).toBe("cerrado"); // no avanzó
    expect(estado.outcome).toBeUndefined(); // ni se quedó con el resultado
    expect(estado.evidence).toContain("NO se usa");
    expect(estado.evidence).toContain("72.0 h");
    expect(estado.evidence).toContain("48");
    expect(estado.evidence).toContain("Se reintenta");
  });

  it("se reintenta: la corrida siguiente con dato fresco sí resuelve", () => {
    const atorado = onRead(cerrado(), lectura(72), spec(48), AHORA);
    const resuelto = onRead(atorado, lectura(2), spec(48), AHORA + HORA);
    expect(resuelto.phase).toBe("en_disputa");
    expect(resuelto.outcome).toBe("si");
    expect(resuelto.frescuraVerificada).toBe(true);
  });

  it("no se atora ni llama a una persona: una fuente retrasada se pone al día sola", () => {
    const estado = onRead(cerrado(), lectura(72), spec(48), AHORA);
    expect(estado.phase).not.toBe("atorado");
    expect(estado.stuckReason).toBeUndefined();
  });

  it("justo en el umbral pasa; una hora más, no", () => {
    expect(onRead(cerrado(), lectura(48), spec(48), AHORA).phase).toBe("en_disputa");
    expect(onRead(cerrado(), lectura(49), spec(48), AHORA).phase).toBe("cerrado");
  });

  it("sin umbral declarado no se bloquea, pero la antigüedad se mide igual", () => {
    // 9 de los 13 mercados del catálogo son series mensuales: su observedAt
    // tiene semanas por construcción, y un umbral de reloj los atascaría
    const estado = onRead(cerrado(), lectura(30 * 24), spec(), AHORA);
    expect(estado.phase).toBe("en_disputa");
    expect(estado.frescuraVerificada).toBe(true); // medida, aunque no se exija
    expect(estado.observedAt).toBe(new Date(AHORA - 30 * 24 * HORA).toISOString());
  });

  it("no saber no es lo mismo que saber que está mal: sin fecha no se bloquea, se marca", () => {
    const estado = onRead(cerrado(), lectura(), spec(48), AHORA);
    expect(estado.phase).toBe("en_disputa"); // no atasca el catálogo
    expect(estado.frescuraVerificada).toBe(false); // pero queda dicho
    expect(resueltosSinFrescura([estado])).toEqual(["m1"]);
  });

  it("una fecha ilegible se trata como no verificable, no como antigüedad rara", () => {
    const f = frescuraDe(
      { status: "resuelto", outcome: "si", evidence: "x", observedAt: "ayer por la tarde" },
      spec(48),
      AHORA,
    );
    expect(f.verificable).toBe(false);
    expect(f.utilizable).toBe(true);
    expect(f.horas).toBeUndefined();
  });

  it("un reloj adelantado en la fuente no rejuvenece nada ni bloquea nada", () => {
    const f = frescuraDe(lectura(-10), spec(48), AHORA); // dato del futuro
    expect(f.horas).toBe(0);
    expect(f.utilizable).toBe(true);
  });

  it("el auditor sólo señala lo que ya se resolvió, no lo que sigue esperando", () => {
    const esperando = onRead(cerrado(), { status: "sin_dato", evidence: "aún no" }, spec(48), AHORA);
    const sinFecha = onRead(cerrado(), lectura(), spec(48), AHORA);
    const conFecha = onRead(cerrado(), lectura(2), spec(48), AHORA);
    expect(resueltosSinFrescura([esperando, sinFecha, conFecha])).toEqual(["m1"]);
  });
});

describe("L8 — el catálogo declara umbral donde el reloj sirve", () => {
  it("los mercados de precio y de partido declaran su umbral", () => {
    // sin esto, la regla dependería de que alguien se acuerde al escribir el
    // siguiente mercado — y un proceso que depende de acordarse no existe
    const conReloj = OWN_MARKETS.filter(
      (seed) => seed.rule?.kind === "precio" || seed.rule?.kind.startsWith("partido"),
    );
    expect(conReloj.length).toBeGreaterThan(0);
    for (const seed of conReloj) {
      expect(seed.resolution.maxAgeHours, seed.id).toBe(FRESCURA_MAX_HORAS);
    }
  });

  it("los de serie mensual NO lo declaran, y es a propósito", () => {
    // su observedAt es la fecha del periodo observado: tiene semanas cuando el
    // dato se publica. Un umbral de reloj no los protegería, los atascaría —
    // que la serie esté al día lo comprueba la propia regla con `sin_dato`
    const series = OWN_MARKETS.filter((seed) => seed.rule?.kind === "serie");
    expect(series.length).toBeGreaterThan(4);
    for (const seed of series) {
      expect(seed.resolution.maxAgeHours, seed.id).toBeUndefined();
    }
  });
});
