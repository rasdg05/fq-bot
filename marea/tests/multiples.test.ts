import { describe, expect, it } from "vitest";
import { mkdtempSync, rmSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  addStake,
  impliedProbability,
  isBinary,
  normalizePool,
  outcomeStake,
  payoutMultiplier,
  probabilities,
  quote,
  settle,
  totalPool,
  type Bet,
  type Pool,
} from "@/domain/parimutuel";
import { Store, VERSION_DATOS } from "../server/store.mts";
import { createMatchOracle, type EspnEvento } from "@/adapters/oracles/matchOracle";
import { readWithOracles } from "@/domain/settlement";
import { ruleProblems, type MatchOutcomeRule } from "@/domain/oracleRule";
import { publishProblems } from "@/domain/resolution";
import {
  OWN_MARKETS,
  validateSeed,
} from "@/adapters/ownMarkets/catalog";

/**
 * Mercados de N resultados. El binario deja de ser el motor y pasa a ser el
 * caso particular con los ids `si` y `no` — dos motores para la misma
 * matemática de dinero serían dos fuentes de verdad, y tarde o temprano una de
 * las dos paga distinto de lo que prometió.
 */

const pool = (outcomes: Record<string, number>, feeBps = 300): Pool => ({
  outcomes,
  feeBps,
});

describe("Pozo de N resultados", () => {
  it("el binario es el caso particular de dos ids, no otro motor", () => {
    const binario = pool({ si: 600, no: 400 });
    expect(isBinary(binario)).toBe(true);
    expect(totalPool(binario)).toBe(1000);
    expect(impliedProbability(binario)).toBeCloseTo(0.6, 5);
    expect(isBinary(pool({ a: 1, b: 1, c: 1 }))).toBe(false);
  });

  it("las probabilidades de todos los resultados suman exactamente 1", () => {
    const cuatro = pool({ a: 700, b: 300, c: 550, d: 450 });
    const p = probabilities(cuatro);
    const suma = Object.values(p).reduce((s, v) => s + v, 0);
    expect(suma).toBeCloseTo(1, 10);
    expect(p.a).toBeCloseTo(700 / 2000, 10);

    // y también con números que no dividen redondo
    const feo = pool({ a: 1, b: 1, c: 1 });
    const q = probabilities(feo);
    expect(Object.values(q).reduce((s, v) => s + v, 0)).toBeCloseTo(1, 10);
  });

  it("el multiplicador incluye la apuesta que se está por hacer, con N lados", () => {
    const p = pool({ a: 400, b: 300, c: 300 }, 300);
    const antes = payoutMultiplier(p, "a");
    const despues = payoutMultiplier(p, "a", 200);
    expect(despues).toBeLessThan(antes);
    // (1000 + 200) × 0.97 / (400 + 200)
    expect(despues).toBeCloseTo((1200 * 0.97) / 600, 10);
  });

  it("un mercado de 4 opciones reparte exactamente lo que prometió", () => {
    // el número que se muestra es el que se cobra (R-044, I3)
    const p = pool({ a: 500, b: 250, c: 150, d: 100 }, 300);
    const stake = 200;
    const prometido = quote(p, "c", stake);

    const conApuesta = addStake(p, "c", stake);
    const bets: Bet[] = [{ id: "mia", side: "c", stake }];
    const reparto = settle(conApuesta, bets, "c");

    expect(reparto.payouts.mia).toBeCloseTo(prometido.toWin, 8);
    // y el reparto completo no crea ni destruye puntos
    expect(reparto.distributed + reparto.fee).toBeCloseTo(totalPool(conApuesta), 8);
  });

  it("el denominador del reparto es todo el lado ganador, semilla incluida", () => {
    // sin la semilla en el denominador se pagaría más de lo prometido (R-044)
    const p = pool({ a: 300, b: 400, c: 300 }, 0);
    const bets: Bet[] = [
      { id: "x", side: "a", stake: 100 },
      { id: "y", side: "b", stake: 200 },
    ];
    const conApuestas = addStake(addStake(p, "a", 100), "b", 200);
    const reparto = settle(conApuestas, bets, "a");
    // lado `a` vale 400 (300 de semilla + 100 de x); total 1300
    expect(reparto.payouts.x).toBeCloseTo((100 / 400) * 1300, 8);
    expect(reparto.payouts.y).toBe(0);
    // la semilla se queda con su parte: no todo el pozo va a los usuarios
    expect(reparto.payouts.x).toBeLessThan(totalPool(conApuestas));
  });

  it("los perdedores de N lados cobran cero, no proporcional", () => {
    const p = pool({ a: 100, b: 100, c: 100, d: 100 }, 0);
    const bets: Bet[] = [
      { id: "a1", side: "a", stake: 50 },
      { id: "b1", side: "b", stake: 50 },
      { id: "c1", side: "c", stake: 50 },
    ];
    const reparto = settle(p, bets, "a");
    expect(reparto.payouts.b1).toBe(0);
    expect(reparto.payouts.c1).toBe(0);
    expect(reparto.payouts.a1).toBeGreaterThan(0);
  });

  it("si el lado ganador está vacío se devuelve todo y la casa no cobra", () => {
    const p = pool({ a: 0, b: 300, c: 200 }, 300);
    const bets: Bet[] = [
      { id: "x", side: "b", stake: 100 },
      { id: "y", side: "c", stake: 200 },
    ];
    const reparto = settle(p, bets, "a");
    expect(reparto.fee).toBe(0);
    expect(reparto.payouts.x).toBe(100);
    expect(reparto.payouts.y).toBe(200);
  });

  it("apostar al lado flaco paga más, con N lados", () => {
    const p = pool({ favorito: 900, medio: 200, tapado: 50 }, 0);
    expect(payoutMultiplier(p, "tapado", 10)).toBeGreaterThan(
      payoutMultiplier(p, "medio", 10),
    );
    expect(payoutMultiplier(p, "medio", 10)).toBeGreaterThan(
      payoutMultiplier(p, "favorito", 10),
    );
  });

  it("un id que no existe en el pozo no inventa un pago", () => {
    const p = pool({ a: 100, b: 100 });
    expect(outcomeStake(p, "fantasma")).toBe(0);
    expect(payoutMultiplier(p, "fantasma")).toBe(0);
  });

  it("la suma de lo repartido más la comisión es el pozo entero, siempre", () => {
    // propiedad: con cualquier reparto no se crea ni se pierde un punto
    for (let caso = 0; caso < 200; caso += 1) {
      const n = 2 + (caso % 5);
      const outcomes: Record<string, number> = {};
      for (let i = 0; i < n; i += 1) {
        outcomes[`o${i}`] = Math.floor(Math.random() * 900) + 100;
      }
      const p = pool(outcomes, 300);
      const bets: Bet[] = Object.keys(outcomes).map((id, i) => ({
        id: `b${i}`,
        side: id,
        stake: 10,
      }));
      let conApuestas = p;
      for (const bet of bets) conApuestas = addStake(conApuestas, bet.side, bet.stake);
      const ganador = `o${caso % n}`;
      const reparto = settle(conApuestas, bets, ganador);
      expect(reparto.distributed + reparto.fee).toBeCloseTo(
        totalPool(conApuestas),
        6,
      );
    }
  });
});

describe("Migración del pozo viejo", () => {
  it("lee el formato binario viejo y lo entiende igual", () => {
    const viejo = { si: 420, no: 260, feeBps: 300 } as unknown;
    const migrado = normalizePool(viejo);
    expect(migrado.outcomes).toEqual({ si: 420, no: 260 });
    expect(migrado.feeBps).toBe(300);
    expect(totalPool(migrado)).toBe(680);
    expect(impliedProbability(migrado)).toBeCloseTo(420 / 680, 10);
  });

  it("un pozo ya migrado se queda como está", () => {
    const nuevo = { outcomes: { a: 1, b: 2, c: 3 }, feeBps: 200 };
    expect(normalizePool(nuevo)).toEqual(nuevo);
  });

  it("el Store lee el volumen de producción viejo sin perder un pozo ni una apuesta", () => {
    // datos reales del volumen de Railway, en formato viejo
    const produccion = JSON.parse(
      readFileSync(join(process.cwd(), "data", "servidor", "marea.json"), "utf8"),
    );
    expect(produccion.version).toBe(1);
    expect(produccion.pozos.length).toBeGreaterThan(20);
    // el archivo de producción está en formato viejo: si esto deja de ser
    // cierto, la prueba de migración ya no está probando la migración
    expect(produccion.pozos[0]).toHaveProperty("si");

    const dir = mkdtempSync(join(tmpdir(), "marea-migracion-"));
    try {
      writeFileSync(join(dir, "marea.json"), JSON.stringify(produccion));
      const store = new Store(dir);

      // ni un pozo perdido
      expect(store.pozos().length).toBe(produccion.pozos.length);
      for (const viejo of produccion.pozos) {
        const migrado = store.pozo(viejo.marketId);
        expect(migrado, viejo.marketId).toBeDefined();
        expect(migrado!.outcomes.si).toBe(viejo.si);
        expect(migrado!.outcomes.no).toBe(viejo.no);
        expect(migrado!.feeBps).toBe(viejo.feeBps);
      }

      // ni una apuesta, ni un usuario, ni un punto
      const totalPuntos = (u: { puntos: number }[]) =>
        u.reduce((s, x) => s + x.puntos, 0);
      expect(store.usuarios().length).toBe(produccion.usuarios.length);
      expect(totalPuntos(store.usuarios())).toBe(totalPuntos(produccion.usuarios));
      for (const usuario of produccion.usuarios) {
        expect(store.apuestasDe(usuario.id).length).toBe(
          produccion.apuestas.filter(
            (a: { usuarioId: string }) => a.usuarioId === usuario.id,
          ).length,
        );
      }

      // y lo que escribe ya es formato nuevo
      const escrito = JSON.parse(readFileSync(join(dir, "marea.json"), "utf8"));
      expect(escrito.version).toBe(VERSION_DATOS);
      expect(escrito.pozos[0]).toHaveProperty("outcomes");
      expect(escrito.pozos[0]).not.toHaveProperty("si");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("migrar dos veces no cambia nada: releer lo escrito da lo mismo", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-idempotente-"));
    try {
      writeFileSync(
        join(dir, "marea.json"),
        JSON.stringify({
          version: 1,
          usuarios: [],
          apuestas: [],
          pozos: [{ marketId: "m", si: 10, no: 20, feeBps: 300 }],
          liquidaciones: [],
          comisiones: [],
        }),
      );
      const primero = new Store(dir);
      const antes = JSON.stringify(primero.pozos());
      const segundo = new Store(dir);
      expect(JSON.stringify(segundo.pozos())).toBe(antes);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("apostar a un id nuevo crece ese lado y deja los demás quietos", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-apostar-n-"));
    try {
      const store = new Store(dir);
      store.crearUsuario({
        id: "u1",
        usuario: "prueba",
        hash: "x",
        salt: "y",
        creado: new Date().toISOString(),
        puntos: 1000,
      });
      store.asegurarPozo({
        marketId: "cuatro",
        outcomes: { a: 100, b: 100, c: 100, d: 100 },
        feeBps: 300,
      });
      store.apostar({
        usuarioId: "u1",
        marketId: "cuatro",
        side: "c",
        stake: 250,
        precio: 0.25,
      });
      const pozo = store.pozo("cuatro")!;
      expect(pozo.outcomes).toEqual({ a: 100, b: 100, c: 350, d: 100 });
      expect(store.usuarioPorId("u1")!.puntos).toBe(750);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

/* ------------------------- oráculo de N respuestas ------------------------ */

describe("Oráculo de partido con N respuestas", () => {
  const spec = {
    sourceName: "ESPN (marcador de la Liga MX)",
    sourceUrl:
      "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard?dates=20260802",
    criterion:
      "Se resuelve con el marcador final del América contra Santos: Gana el América, Empatan o Gana Santos.",
    settlesAt: "2026-08-03T04:00:00Z",
    disputeWindowHours: 12,
  };

  const partido = (local: string, visita: string): EspnEvento => ({
    date: "2026-08-02T23:00Z",
    name: "Santos at América",
    competitions: [
      {
        status: { type: { name: "STATUS_FULL_TIME", completed: true } },
        competitors: [
          { homeAway: "home", score: local, team: { displayName: "América" } },
          { homeAway: "away", score: visita, team: { displayName: "Santos" } },
        ],
      },
    ],
  });

  const regla1x2: MatchOutcomeRule = {
    kind: "partido_multiple",
    liga: "mex.1",
    fecha: "2026-08-02",
    equipo: "América",
    mercado: "1x2",
  };

  async function leer(evento: EspnEvento, rule: MatchOutcomeRule) {
    const oracle = createMatchOracle({ cargarPartidos: async () => [evento] });
    const { reading } = await readWithOracles([oracle], {
      marketId: "m",
      spec,
      rule,
      now: Date.parse("2026-08-03T03:00:00Z"),
    });
    return reading;
  }

  it("el empate deja de plegarse dentro del No: es su propio resultado", async () => {
    const reading = await leer(partido("1", "1"), regla1x2);
    expect(reading.status).toBe("resuelto");
    if (reading.status === "resuelto") expect(reading.outcome).toBe("empata");
  });

  it("distingue los tres resultados del 1X2", async () => {
    for (const [local, visita, esperado] of [
      ["2", "0", "gana"],
      ["1", "1", "empata"],
      ["0", "3", "pierde"],
    ] as const) {
      const reading = await leer(partido(local, visita), regla1x2);
      if (reading.status === "resuelto") expect(reading.outcome).toBe(esperado);
      else throw new Error(`no resolvió ${local}-${visita}`);
    }
  });

  it("los tramos de goles caen en el que les toca, bordes incluidos", async () => {
    const reglaGoles: MatchOutcomeRule = {
      kind: "partido_multiple",
      liga: "mex.1",
      fecha: "2026-08-02",
      equipo: "América",
      mercado: "goles",
      cortes: [2, 4],
    };
    for (const [local, visita, esperado] of [
      ["0", "0", "goles_0_1"],
      ["1", "0", "goles_0_1"],
      ["1", "1", "goles_2_3"], // 2 goles: primer valor del tramo de en medio
      ["2", "1", "goles_2_3"],
      ["2", "2", "goles_4_mas"], // 4 goles: primer valor del tramo de arriba
      ["5", "2", "goles_4_mas"],
    ] as const) {
      const reading = await leer(partido(local, visita), reglaGoles);
      if (reading.status === "resuelto") {
        expect(reading.outcome, `${local}-${visita}`).toBe(esperado);
      } else throw new Error(`no resolvió ${local}-${visita}`);
    }
  });

  it("un partido sin terminar no resuelve, tenga el marcador que tenga", async () => {
    const enJuego: EspnEvento = {
      date: "2026-08-02T23:00Z",
      name: "Santos at América",
      competitions: [
        {
          status: { type: { name: "STATUS_IN_PROGRESS", completed: false } },
          competitors: [
            { homeAway: "home", score: "2", team: { displayName: "América" } },
            { homeAway: "away", score: "0", team: { displayName: "Santos" } },
          ],
        },
      ],
    };
    expect((await leer(enJuego, regla1x2)).status).toBe("sin_dato");
  });

  it("los tramos publicados tienen que aparecer en el criterio (R-042)", () => {
    const conCortes: MatchOutcomeRule = {
      kind: "partido_multiple",
      liga: "mex.1",
      fecha: "2026-08-03",
      equipo: "Toluca",
      mercado: "goles",
      cortes: [2, 4],
    };
    expect(
      ruleProblems(
        conCortes,
        "Se resuelve con los goles del Toluca: 0-1 goles, 2-3 goles, o 4 o más goles.",
      ),
    ).toEqual([]);
    // si el criterio publicado no dice los mismos cortes, no se publica
    expect(
      ruleProblems(conCortes, "Se resuelve con los goles del Toluca."),
    ).not.toEqual([]);
  });
});

describe("Catálogo de N respuestas", () => {
  it("hay mercados culturales reales de más de dos respuestas", () => {
    const multiples = OWN_MARKETS.filter((seed) => (seed.outcomes?.length ?? 2) > 2);
    expect(multiples.length).toBeGreaterThanOrEqual(2);
    for (const seed of multiples) {
      // fuente pública y criterio inequívoco, igual que cualquier otro (R-025)
      expect(publishProblems(seed.resolution), seed.id).toEqual([]);
      expect(seed.title).toMatch(/^¿.+\?$/);
      // el pozo y los resultados declarados hablan del mismo mercado
      expect(Object.keys(seed.pool.outcomes).sort()).toEqual(
        seed.outcomes!.map((o) => o.id).sort(),
      );
      // y cada resultado tiene pozo propio: ninguno arranca en cero
      for (const outcome of seed.outcomes!) {
        expect(seed.pool.outcomes[outcome.id], `${seed.id}/${outcome.id}`).toBeGreaterThan(0);
      }
    }
  });

  it("las probabilidades de cada mercado del catálogo suman 1", () => {
    for (const seed of OWN_MARKETS) {
      const suma = Object.values(probabilities(seed.pool)).reduce((s, v) => s + v, 0);
      expect(suma, seed.id).toBeCloseTo(1, 10);
    }
  });

  it("un mercado cuyo pozo y resultados no coinciden no se publica", () => {
    const base = OWN_MARKETS.find((s) => (s.outcomes?.length ?? 2) > 2)!;
    expect(() =>
      validateSeed({
        ...base,
        id: "roto",
        outcomes: [...base.outcomes!, { id: "fantasma", label: "Fantasma" }],
      }),
    ).toThrow(/declara/);
  });

  it("R-062 · ningún mercado de N respuestas gasta cupo de confirmación humana", () => {
    // R-062 topa en tres los mercados que dependen de que una persona se
    // siente a verlos. Los dos que agrega esta fase se resuelven solos contra
    // ESPN, así que no consumen cupo: lo que esta prueba impide es que un
    // mercado de N respuestas entre al catálogo sin forma de resolverse sola.
    //
    // El catálogo heredado ya venía por encima del tope. Eso es un hallazgo
    // aparte, con su evidencia, y no se tapa desde aquí: cerrarlo pide enchufar
    // BCRP y BCRA, que sí publican endpoint (R-051).
    const multiples = OWN_MARKETS.filter((seed) => (seed.outcomes?.length ?? 2) > 2);
    expect(multiples.length).toBeGreaterThan(0);
    for (const seed of multiples) {
      expect(seed.rule, `${seed.id} no se resuelve solo`).toBeDefined();
    }
  });
});
