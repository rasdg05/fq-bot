import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Store } from "../server/store.mts";
import { correrCiclo } from "../server/ciclo.mts";
import { listarMercados, sembrarPozos, todosLosMercados } from "../server/mercados.mts";
import { validateSeed, type OwnMarketSeed } from "@/adapters/ownMarkets/catalog";
import {
  atascoDe,
  congelados,
  initialState,
  onClose,
  onDeadline,
  onRead,
  PLAZO_ANULACION_DIAS,
  PLAZO_ATASCO_DIAS,
  type Oracle,
} from "@/domain/settlement";
import { binaryPool } from "@/domain/parimutuel";
import { cuentaPozo, saldoDe } from "@/domain/contabilidad";

/**
 * El atasco silencioso, que es el peor fallo que ha tenido este producto y se
 * vio en producción: un mercado se queda sin resolver para siempre y nadie se
 * entera.
 *
 * El oráculo no puede leer la fuente y contesta `sin_dato`. `onRead` hace lo
 * correcto —no inventa un resultado, reintenta— y eso, mil corridas seguidas,
 * es un mercado congelado con el dinero de alguien dentro. Y era invisible:
 * `sin_dato` no es `atorado`, así que el resumen decía «0 atorados · 0 errores».
 *
 * Medido en producción antes del arreglo: 1008 corridas sin un solo error, y
 * apuestas de agosto todavía en «si aciertas» el 10 de septiembre.
 */

const DIA = 86_400_000;
const AHORA = Date.parse("2026-08-01T00:00:00Z");

const seed: OwnMarketSeed = validateSeed({
  id: "congelado",
  title: "¿Un mercado cuya fuente dejó de contestar?",
  shortTitle: "Fuente caída",
  // esta rama exige nombres de verdad: "Sí" y "No" no dicen de qué lado estás
  // cuando la pregunta ya no está a la vista (§3.3 del rediseño)
  outcomes: [
    { id: "si", label: "Abajo de 5 %" },
    { id: "no", label: "5 % o más" },
  ],
  category: "economia",
  country: "BR",
  closesAt: new Date(AHORA).toISOString(),
  pool: binaryPool(200, 200, 300),
  resolution: {
    sourceName: "Banco Central do Brasil (serie 13522 del SGS)",
    sourceUrl: "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/6?formato=json",
    criterion:
      "Se resuelve Sí si el IPCA acumulado de 12 meses que publica el Banco Central do Brasil en su serie 13522 es menor a 5 por ciento. Se lee del endpoint público.",
    settlesAt: new Date(AHORA + DIA).toISOString(),
    disputeWindowHours: 24,
  },
});

/** Una fuente caída: contesta siempre, y siempre que no sabe. */
const fuenteCaida: Oracle = {
  id: "caida",
  handles: () => true,
  read: async () => ({
    status: "sin_dato",
    evidence: "No se pudo leer: Unexpected token '<', \"<?xml vers\"... is not valid JSON",
  }),
};

const fuenteViva: Oracle = {
  id: "viva",
  handles: () => true,
  read: async () => ({
    status: "resuelto",
    outcome: "si",
    evidence: "IPCA 12 meses: 4.44 %",
    observedAt: new Date(AHORA + DIA).toISOString(),
  }),
};

function conStore(): { dir: string; store: Store } {
  const dir = mkdtempSync(join(tmpdir(), "marea-congelado-"));
  const store = new Store(dir);
  sembrarPozos(store, [seed]);
  store.crearUsuario({
    id: "ana", usuario: "ana", hash: "x", salt: "y",
    creado: new Date(AHORA).toISOString(), puntos: 1_000,
  } as never);
  store.crearUsuario({
    id: "beto", usuario: "beto", hash: "x", salt: "y",
    creado: new Date(AHORA).toISOString(), puntos: 1_000,
  } as never);
  store.apostar({ usuarioId: "ana", marketId: seed.id, side: "si", stake: 300, precio: 0.5 });
  store.apostar({ usuarioId: "beto", marketId: seed.id, side: "no", stake: 100, precio: 0.5 });
  return { dir, store };
}

describe("El atasco silencioso deja de ser silencioso", () => {
  it("una fuente caída ya NO congela el mercado en silencio: a los 7 días se ve", async () => {
    const { dir, store } = conStore();
    try {
      // dos días después: la fuente no contesta, y todavía es pronto
      let r = await correrCiclo(store, [seed], [fuenteCaida], AHORA + 2 * DIA);
      expect(r.atorados).toEqual([]);
      expect(store.liquidacion(seed.id)?.phase).toBe("cerrado");

      // pasado el plazo corto, aparece — que es lo que faltaba
      r = await correrCiclo(store, [seed], [fuenteCaida], AHORA + (PLAZO_ATASCO_DIAS + 2) * DIA);
      expect(r.atorados).toEqual([seed.id]);
      expect(r.incobrables).toEqual([]);
      const estado = store.liquidacion(seed.id)!;
      expect(estado.phase).toBe("atorado");
      expect(estado.stuckReason).toContain("Sin resolver");
      expect(estado.stuckReason).toContain("Se sigue");
      // y nadie ha cobrado ni perdido nada todavía
      expect(store.usuarioPorId("ana")!.puntos).toBe(700);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("estar atorado NO es una condena: si la fuente vuelve, el mercado se resuelve solo", async () => {
    const { dir, store } = conStore();
    try {
      await correrCiclo(store, [seed], [fuenteCaida], AHORA + (PLAZO_ATASCO_DIAS + 2) * DIA);
      expect(store.liquidacion(seed.id)?.phase).toBe("atorado");

      // la fuente vuelve
      await correrCiclo(store, [seed], [fuenteViva], AHORA + (PLAZO_ATASCO_DIAS + 3) * DIA);
      const estado = store.liquidacion(seed.id)!;
      expect(estado.phase).toBe("en_disputa");
      expect(estado.outcome).toBe("si");
      expect(estado.stuckReason).toBeUndefined(); // el motivo se va con el atasco

      // y paga como cualquier otro
      const r = await correrCiclo(store, [seed], [fuenteViva], AHORA + (PLAZO_ATASCO_DIAS + 5) * DIA);
      expect(r.pagados).toBe(1);
      expect(store.usuarioPorId("ana")!.puntos).toBeGreaterThan(700);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("a los 30 días se anula y se devuelve TODO, sin comisión", async () => {
    const { dir, store } = conStore();
    try {
      const r = await correrCiclo(
        store, [seed], [fuenteCaida], AHORA + (PLAZO_ANULACION_DIAS + 1) * DIA,
      );
      expect(r.incobrables).toEqual([seed.id]);
      expect(r.anulados).toBe(1);

      // cada quien recupera exactamente lo suyo
      expect(store.usuarioPorId("ana")!.puntos).toBe(1_000);
      expect(store.usuarioPorId("beto")!.puntos).toBe(1_000);
      // la casa no cobra de un mercado que nadie pudo ganar (R-024)
      expect(store.tesoreria()).toBe(0);
      expect(store.cuadre()).toBe(0);
      expect(store.liquidacion(seed.id)?.phase).toBe("devuelto");
      expect(store.pozosConSaldoTrasLiquidar()).toEqual({});
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("y no devuelve dos veces si el ciclo vuelve a correr", async () => {
    const { dir, store } = conStore();
    try {
      await correrCiclo(store, [seed], [fuenteCaida], AHORA + (PLAZO_ANULACION_DIAS + 1) * DIA);
      const asientos = store.libro().length;
      const r = await correrCiclo(store, [seed], [fuenteCaida], AHORA + (PLAZO_ANULACION_DIAS + 9) * DIA);
      expect(r.acreditado).toBe(0);
      expect(store.usuarioPorId("ana")!.puntos).toBe(1_000);
      expect(store.libro().length).toBe(asientos);
      expect(store.cuadre()).toBe(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("un mercado que SÍ resolvió no cuenta como atascado aunque tarde en pagarse", () => {
    // esperar la ventana de disputa es la promesa, no una demora (R-040)
    const leido = onRead(
      onClose(initialState(seed.id)),
      { status: "resuelto", outcome: "si", evidence: "ok" },
      seed.resolution,
      AHORA + DIA,
    );
    expect(leido.phase).toBe("en_disputa");
    expect(atascoDe(leido, seed.resolution, AHORA + 90 * DIA).estado).toBe("ninguno");
    expect(onDeadline(leido, seed.resolution, AHORA + 90 * DIA)).toEqual(leido);
  });

  it("el auditor lista los congelados, que es lo que `cuadre` no puede ver", () => {
    const cerrado = onClose(initialState("congelado"));
    const sano = onRead(
      onClose(initialState("sano")),
      { status: "resuelto", outcome: "si", evidence: "ok" },
      seed.resolution,
      AHORA + DIA,
    );
    const lista = congelados(
      [
        { state: cerrado, spec: seed.resolution },
        { state: sano, spec: seed.resolution },
      ],
      AHORA + 40 * DIA,
    );
    expect(lista.map((c) => c.marketId)).toEqual(["congelado"]);
    expect(lista[0].estado).toBe("incobrable");
    expect(lista[0].dias).toBe(39);
  });

  it("un mercado puede declarar su propio plazo si su fuente es lenta", () => {
    const lento = { ...seed.resolution, maxStuckDays: 120 };
    const cerrado = onClose(initialState("lento"));
    expect(atascoDe(cerrado, lento, AHORA + 40 * DIA).estado).toBe("atascado");
    expect(atascoDe(cerrado, lento, AHORA + 130 * DIA).estado).toBe("incobrable");
  });
});

/**
 * Lo que se ve en el feed. La queja que lo destapó fue literal: «el de Brasil
 * que ya está cerrado sigue saliendo en mercados con los demás abiertos».
 */
describe("Feed — un mercado cerrado no se enseña como si se pudiera entrar", () => {
  const abierto = (id: string, si: number, no: number): OwnMarketSeed =>
    validateSeed({
      ...seed,
      id,
      closesAt: new Date(AHORA + 30 * DIA).toISOString(),
      pool: binaryPool(si, no, 300),
      resolution: { ...seed.resolution, settlesAt: new Date(AHORA + 31 * DIA).toISOString() },
    });

  const cerrado = (id: string, si: number, no: number): OwnMarketSeed =>
    validateSeed({
      ...seed,
      id,
      closesAt: new Date(AHORA - DIA).toISOString(),
      pool: binaryPool(si, no, 300),
      resolution: { ...seed.resolution, settlesAt: new Date(AHORA - DIA + 3_600_000).toISOString() },
    });

  it("un mercado cerrado nunca es `hot`, por grande que sea su pozo", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-feed-"));
    try {
      const store = new Store(dir);
      const seeds = [cerrado("gordo-cerrado", 5_000, 5_000), abierto("chico-abierto", 100, 100)];
      sembrarPozos(store, seeds);
      const feed = listarMercados(store, seeds, AHORA);

      const gordo = feed.find((m) => m.id === "gordo-cerrado")!;
      const chico = feed.find((m) => m.id === "chico-abierto")!;
      expect(gordo.status).not.toBe("open");
      expect(gordo.hot).toBe(false); // enseñar una puerta con el candado puesto
      // y el hueco de `hot` se lo queda el que sí acepta apuestas
      expect(chico.hot).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("los cerrados van al final aunque tengan más pozo", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-orden-"));
    try {
      const store = new Store(dir);
      const seeds = [cerrado("gordo-cerrado", 5_000, 5_000), abierto("chico-abierto", 100, 100)];
      sembrarPozos(store, seeds);
      const feed = listarMercados(store, seeds, AHORA);
      // lo primero que ve quien llega tiene que ser algo en lo que pueda entrar
      expect(feed.map((m) => m.id)).toEqual(["chico-abierto", "gordo-cerrado"]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("el umbral de `hot` se mide sólo entre los abiertos, o los cerrados lo suben", () => {
    /**
     * Con dos mercados no se nota: `HOT_TOP_N` es 3 y caben los dos. Hace falta
     * que los cerrados **desplacen** a los abiertos del top para que se vea —
     * que es exactamente lo que pasaba en producción, donde los pozos viejos
     * eran los más grandes y los mercados nuevos nacían chicos.
     */
    const dir = mkdtempSync(join(tmpdir(), "marea-umbral-"));
    try {
      const store = new Store(dir);
      const seeds = [
        cerrado("viejo-1", 5_000, 5_000),
        cerrado("viejo-2", 4_000, 4_000),
        cerrado("viejo-3", 3_000, 3_000),
        abierto("nuevo-1", 200, 200),
        abierto("nuevo-2", 100, 100),
      ];
      sembrarPozos(store, seeds);
      const feed = listarMercados(store, seeds, AHORA);

      // los tres huecos de `hot` son para los abiertos, que son los que
      // aceptan apuestas — aunque sus pozos sean diez veces menores
      expect(feed.filter((m) => m.hot).map((m) => m.id).sort()).toEqual(["nuevo-1", "nuevo-2"]);
      for (const id of ["viejo-1", "viejo-2", "viejo-3"]) {
        expect(feed.find((m) => m.id === id)!.hot, id).toBe(false);
      }
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("entre abiertos sigue mandando el pozo", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-orden2-"));
    try {
      const store = new Store(dir);
      const seeds = [abierto("chico", 100, 100), abierto("grande", 900, 900)];
      sembrarPozos(store, seeds);
      const feed = listarMercados(store, seeds, AHORA);
      expect(feed.map((m) => m.id)).toEqual(["grande", "chico"]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

/**
 * Un mercado deja de mostrarse; no deja de existir para quien puso dinero.
 */
describe("Portafolio — una apuesta vieja puede abrir su mercado", () => {
  it("el mercado vencido sale del feed pero se sigue pudiendo consultar", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-viejo-"));
    try {
      const store = new Store(dir);
      const vencido = validateSeed({
        ...seed,
        id: "partido-de-agosto",
        closesAt: new Date(AHORA - 40 * DIA).toISOString(),
        resolution: { ...seed.resolution, settlesAt: new Date(AHORA - 39 * DIA).toISOString() },
      });
      sembrarPozos(store, [vencido]);

      // el feed no lo enseña, que es lo correcto
      expect(listarMercados(store, [vencido], AHORA).map((m) => m.id)).toEqual([]);
      // pero quien tiene una apuesta dentro sí lo puede abrir
      const todos = todosLosMercados(store, [vencido], AHORA);
      expect(todos.map((m) => m.id)).toEqual(["partido-de-agosto"]);
      expect(todos[0].title).toBe(vencido.title);
      // y no se cuela como `hot` por la puerta de atrás
      expect(todos[0].hot).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

/**
 * Apuestas huérfanas: el mercado desapareció del catálogo y la apuesta se
 * quedó dentro.
 *
 * Es el caso que peor se ve de todos, y se vio en producción: el portafolio de
 * alguien mostraba `latam-libertadores-br` —el id crudo, porque ni el título se
 * podía resolver— con su apuesta sin cobrar. El ciclo itera sobre las semillas,
 * y la semilla es justo lo que falta: ninguna corrida iba a mirarla nunca.
 */
describe("Apuestas huérfanas — el mercado se perdió, el dinero no", () => {
  function conApuestaHuerfana() {
    const dir = mkdtempSync(join(tmpdir(), "marea-huerfana-"));
    const store = new Store(dir);
    sembrarPozos(store, [seed]);
    store.crearUsuario({
      id: "ana", usuario: "ana", hash: "x", salt: "y",
      creado: new Date(AHORA).toISOString(), puntos: 1_000,
    } as never);
    store.apostar({ usuarioId: "ana", marketId: seed.id, side: "si", stake: 300, precio: 0.5 });
    return { dir, store };
  }

  it("el auditor las encuentra: es lo único que conoce todas las apuestas", () => {
    const { dir, store } = conApuestaHuerfana();
    try {
      // con su mercado en el catálogo no hay nada que reportar
      expect(store.apuestasHuerfanas([seed.id])).toEqual({});
      // sin él, aparece con lo que hay dentro
      expect(store.apuestasHuerfanas([])).toEqual({ [seed.id]: 300 });
      expect(store.apuestasHuerfanas(["otro-mercado"])).toEqual({ [seed.id]: 300 });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("el ciclo las devuelve íntegras y sin comisión", async () => {
    const { dir, store } = conApuestaHuerfana();
    try {
      expect(store.usuarioPorId("ana")!.puntos).toBe(700);

      // el catálogo ya no lo trae: es exactamente lo que pasó en producción
      const r = await correrCiclo(store, [], [fuenteViva], AHORA + 5 * DIA);

      expect(r.huerfanos).toEqual([seed.id]);
      expect(r.anulados).toBe(1);
      expect(store.usuarioPorId("ana")!.puntos).toBe(1_000); // le vuelve lo suyo
      expect(store.tesoreria()).toBe(0); // y la casa no cobra por su propio error
      expect(store.cuadre()).toBe(0);
      expect(saldoDe(store.libro(), cuentaPozo(seed.id))).toBe(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("y no las devuelve dos veces", async () => {
    const { dir, store } = conApuestaHuerfana();
    try {
      await correrCiclo(store, [], [fuenteViva], AHORA + 5 * DIA);
      const asientos = store.libro().length;
      const r = await correrCiclo(store, [], [fuenteViva], AHORA + 6 * DIA);
      expect(r.huerfanos).toEqual([]);
      expect(r.acreditado).toBe(0);
      expect(store.usuarioPorId("ana")!.puntos).toBe(1_000);
      expect(store.libro().length).toBe(asientos);
      /**
       * Y el auditor deja de reportarla. El dinero ya lo protege la guarda de
       * `liquidarMercado`, así que esto no es sobre pagar dos veces: es sobre
       * que el informe no mienta. Un auditor que sigue gritando por algo que ya
       * se arregló es un auditor que se deja de leer, y entonces no sirve el
       * día que grite por algo de verdad.
       */
      expect(store.apuestasHuerfanas([])).toEqual({});
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("un mercado que SÍ está en el catálogo no se toca por esta vía", async () => {
    const { dir, store } = conApuestaHuerfana();
    try {
      const r = await correrCiclo(store, [seed], [fuenteViva], AHORA + 2 * DIA);
      expect(r.huerfanos).toEqual([]);
      // sigue su ciclo normal: leído y esperando la ventana de disputa
      expect(store.liquidacion(seed.id)?.phase).toBe("en_disputa");
      expect(store.usuarioPorId("ana")!.puntos).toBe(700);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
