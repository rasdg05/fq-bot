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
import { createSeriesOracle } from "@/adapters/oracles/seriesOracle";
import { createPriceOracle } from "@/adapters/oracles/priceOracle";
import { createMatchOracle } from "@/adapters/oracles/matchOracle";

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

/**
 * El otro lado de L8: que el margen no sea tan APRETADO que atasque el mercado.
 *
 * Se descubrió midiendo, al verificar una afirmación que en U5 se dio por buena
 * leyendo el código: «para las series, que estén al día ya lo comprueba la
 * propia regla». La regla existe — pero **siete de las nueve series usaban el
 * margen por defecto de 1.5 días**, y para una serie mensual el dato correcto
 * llega fechado ~35 días antes de resolver. Tres mercados no podían resolverse
 * **nunca** por programa: se apuesta y no se cobra, que es el agujero que vence
 * a cualquier otra cosa (AGENTE §0.1).
 *
 * Esto es lo que impide que vuelva al escribir el siguiente mercado.
 */
describe("L8 al revés — un margen demasiado apretado atasca el mercado", () => {
  const DIA = 86_400_000;

  /** El desfase típico de la observación respecto al día en que resuelve. */
  const DESFASE: Record<string, number> = {
    // series mensuales: la observación va fechada al periodo, no a la
    // publicación, así que llega con un mes largo de retraso
    "br-ipca-5": 35,
    "pe-inflacion-lima": 35,
    "cl-imacec": 35,
    // la meta Selic sólo cambia en las reuniones del COPOM, cada ~45 días
    "br-selic-corte": 50,
    // series diarias: el dato es de ayer
    "mx-dolar-19": 1,
    "co-dolar-trm": 1,
    "ar-badlar-tasa": 1,
    "mx-inpc-anual": 35,
    "mx-banxico-tasa": 1,
  };

  it("toda serie del catálogo acepta un dato fechado a su cadencia real", async () => {
    const series = OWN_MARKETS.filter((seed) => seed.rule?.kind === "serie");
    expect(series.length).toBeGreaterThan(4);

    for (const seed of series) {
      const desfase = DESFASE[seed.id];
      expect(desfase, `falta la cadencia de ${seed.id} en el test`).toBeDefined();
      const settlesAt = Date.parse(seed.resolution.settlesAt);
      const oracle = createSeriesOracle({
        cargar: async () => [
          { fecha: settlesAt - (desfase + 30) * DIA, valor: 3.5 },
          { fecha: settlesAt - desfase * DIA, valor: 3.2 },
        ],
        banxicoToken: "prueba",
        inegiToken: "prueba",
      });
      const lectura = await oracle.read({
        marketId: seed.id,
        spec: seed.resolution,
        rule: seed.rule,
        now: settlesAt + DIA,
      });
      // `requiere_humano` es legítimo (falta el token de INEGI/Banxico y el
      // mercado lo declara, R-022). Lo que NO puede pasar es `sin_dato` con el
      // dato correcto delante: eso es un mercado que no resuelve nunca
      expect(lectura.status, `${seed.id} descarta su propio dato por viejo`).not.toBe("sin_dato");
    }
  });

  it("y sigue rechazando un dato de verdad viejo: el margen no es una puerta abierta", () => {
    // el margen se ensancha para la cadencia de la fuente, no para siempre.
    // Una serie parada tres veces su periodo sigue sin resolver
    const seed = OWN_MARKETS.find((s) => s.id === "br-ipca-5")!;
    const settlesAt = Date.parse(seed.resolution.settlesAt);
    const oracle = createSeriesOracle({
      cargar: async () => [{ fecha: settlesAt - 200 * DIA, valor: 3.2 }],
      banxicoToken: "prueba",
      inegiToken: "prueba",
    });
    return oracle
      .read({ marketId: seed.id, spec: seed.resolution, rule: seed.rule, now: settlesAt + DIA })
      .then((lectura) => {
        expect(lectura.status).toBe("sin_dato");
        expect(lectura.evidence).toContain("último dato publicado");
      });
  });
});

/**
 * La forma general del agujero que apareció en las series: **todo mercado
 * publicado tiene que poder resolverse por programa cuando su fuente contesta
 * lo que se espera**.
 *
 * No se comprueba que el resultado sea uno u otro —eso depende del dato— sino
 * que no salga `sin_dato` teniendo delante exactamente lo que la regla pide. Un
 * mercado que acepta apuestas y contesta `sin_dato` para siempre es alguien que
 * apostó y no cobra, que es el agujero que vence a todo lo demás (AGENTE §0.1).
 */
describe("Ciclo de vida — todo mercado publicado se puede resolver por programa", () => {
  const DIA = 86_400_000;

  function velas(desde: number, hasta: number, precio: number) {
    const salida = [];
    for (let t = Math.floor(desde / DIA) * DIA; t <= hasta; t += DIA) {
      salida.push({ inicio: t, apertura: precio, alto: precio * 1.5, bajo: precio * 0.5, cierre: precio });
    }
    return salida;
  }

  it("los mercados de precio resuelven con las velas que su regla pide", async () => {
    const precio = OWN_MARKETS.filter((seed) => seed.rule?.kind === "precio");
    expect(precio.length).toBeGreaterThan(0);
    for (const seed of precio) {
      const settlesAt = Date.parse(seed.resolution.settlesAt);
      const now = settlesAt + DIA;
      const umbral = (seed.rule as { umbral: number }).umbral;
      const oracle = createPriceOracle({
        loadCandles: async (_par, desde) => velas(desde, now, umbral * 1.2),
      });
      const lectura = await oracle.read({
        marketId: seed.id, spec: seed.resolution, rule: seed.rule, now,
      });
      expect(lectura.status, `${seed.id} no resuelve con sus propias velas`).toBe("resuelto");
    }
  });

  it("los mercados de partido resuelven con el marcador final que su regla pide", async () => {
    const partidos = OWN_MARKETS.filter((seed) => seed.rule?.kind.startsWith("partido"));
    expect(partidos.length).toBeGreaterThan(0);
    for (const seed of partidos) {
      const settlesAt = Date.parse(seed.resolution.settlesAt);
      const equipo = (seed.rule as { equipo: string }).equipo;
      const oracle = createMatchOracle({
        cargarPartidos: async () =>
          [
            {
              date: new Date(settlesAt - 2 * 3_600_000).toISOString(),
              name: `${equipo} vs Rival`,
              competitions: [
                {
                  status: { type: { completed: true, name: "STATUS_FULL_TIME" } },
                  competitors: [
                    { homeAway: "home", score: "2", team: { displayName: equipo, abbreviation: "L", shortDisplayName: "L" } },
                    { homeAway: "away", score: "1", team: { displayName: "Rival", abbreviation: "R", shortDisplayName: "R" } },
                  ],
                },
              ],
            },
          ] as never,
      });
      const lectura = await oracle.read({
        marketId: seed.id, spec: seed.resolution, rule: seed.rule, now: settlesAt + DIA,
      });
      expect(lectura.status, `${seed.id} no resuelve con su propio marcador`).toBe("resuelto");
    }
  });

  it("no queda ningún mercado del catálogo sin regla que lo resuelva sola", () => {
    // un mercado sin regla se resuelve con confirmación humana, y R-062 limita
    // eso a tres a la vez: no es un fallo, pero tiene que ser una excepción
    // contada, no el estado por omisión al que se llega sin querer
    const sinRegla = OWN_MARKETS.filter((seed) => !seed.rule);
    expect(sinRegla.map((s) => s.id)).toEqual([]);
  });
});
