import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Store } from "../server/store.mts";
import { correrCiclo } from "../server/ciclo.mts";
import { sembrarPozos } from "../server/mercados.mts";
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
