import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Store } from "../server/store.mts";
import { correrCiclo } from "../server/ciclo.mts";
import { sembrarPozos } from "../server/mercados.mts";
import { correrRevisor, fotoDe } from "../server/revisor.mts";
import { validateSeed, type OwnMarketSeed } from "@/adapters/ownMarkets/catalog";
import { anexar, verificarCadena, type EntradaBitacora } from "@/domain/bitacora";
import { conciliar, revisar, type Foto, type MercadoEnFoto } from "@/domain/revisor";
import { initialState, onRead, resolveByHand, retener, type Oracle } from "@/domain/settlement";
import { binaryPool } from "@/domain/parimutuel";

/**
 * El revisor autónomo y su bitácora (MEMORY/FILOSOFIA.md). Lo que se prueba es
 * lo que lo vuelve confiable: que su rastro no se puede editar sin que se note,
 * que registra cambios y no ruido, y que su única acción sobre dinero —retener—
 * no la deshace la siguiente lectura del oráculo.
 */

const H = 3_600_000;
const AHORA = Date.parse("2026-10-01T12:00:00Z");

describe("Bitácora — una decisión sin rastro no ocurrió", () => {
  function cadena(n: number): EntradaBitacora[] {
    const c: EntradaBitacora[] = [];
    for (let i = 0; i < n; i++) {
      c.push(
        anexar(c, { tipo: "omitir", sujeto: `m${i}`, motivo: `motivo ${i}`, autor: "reglas", reversible: true }, AHORA + i),
      );
    }
    return c;
  }

  it("una cadena íntegra verifica", () => {
    expect(verificarCadena(cadena(5))).toEqual({ ok: true, entradas: 5 });
  });

  it("editar el motivo de una entrada del medio se nota, y se sabe cuál", () => {
    const c = cadena(5);
    c[2] = { ...c[2], motivo: "otro motivo, más cómodo" };
    expect(verificarCadena(c)).toMatchObject({ ok: false, en: 3 });
  });

  it("borrar una entrada se nota", () => {
    const c = cadena(5);
    c.splice(1, 1);
    expect(verificarCadena(c).ok).toBe(false);
  });

  it("el mismo contenido da el mismo hash (no depende del orden de las claves)", () => {
    const a = anexar([], { tipo: "omitir", sujeto: "x", motivo: "y", autor: "reglas", reversible: true }, AHORA);
    const b = anexar([], { reversible: true, autor: "reglas", motivo: "y", sujeto: "x", tipo: "omitir" }, AHORA);
    expect(a.hash).toBe(b.hash);
  });
});

function mercado(parcial: Partial<MercadoEnFoto> = {}): MercadoEnFoto {
  return {
    id: "m",
    shortTitle: "Un mercado",
    category: "economia",
    closesAt: new Date(AHORA + 24 * H).toISOString(),
    settlesAt: new Date(AHORA + 48 * H).toISOString(),
    outcomes: ["si", "no"],
    fuente: "serie",
    conApuestas: false,
    vela: false,
    ...parcial,
  };
}
const foto = (mercados: MercadoEnFoto[], extra: Partial<Foto> = {}): Foto => ({
  ahora: AHORA,
  mercados,
  descuadre: 0,
  pozosConSaldo: {},
  huerfanas: {},
  ...extra,
});

describe("Revisor — los chequeos", () => {
  it("un resultado que el mercado no tiene es crítico y pide retener", () => {
    const h = revisar(
      foto([mercado({ estado: { marketId: "m", phase: "en_disputa", outcome: "tal-vez", evidence: "x" } })]),
    );
    expect(h).toContainEqual(expect.objectContaining({ codigo: "resultado_fuera_de_opciones", severidad: "critico", accion: "retener" }));
  });

  it("sin leer tras su fecha: aviso a las 24 h, grave a las 72 h", () => {
    const vencido = (horas: number) =>
      revisar(foto([mercado({ settlesAt: new Date(AHORA - horas * H).toISOString() })])).find((x) => x.codigo === "sin_leer");
    expect(vencido(10)).toBeUndefined();
    expect(vencido(30)?.severidad).toBe("aviso");
    expect(vencido(80)?.severidad).toBe("grave");
  });

  it("una fuente con fallas de red en dos mercados es un hallazgo de la fuente, no de cada mercado", () => {
    const caido = (id: string) =>
      mercado({ id, fuente: "espejo", estado: { marketId: id, phase: "abierto", evidence: "Kalshi respondió 429 para X" } });
    expect(revisar(foto([caido("a")])).some((h) => h.codigo === "fuente_con_fallas")).toBe(false);
    const h = revisar(foto([caido("a"), caido("b")])).filter((x) => x.codigo === "fuente_con_fallas");
    expect(h).toEqual([expect.objectContaining({ sujeto: "espejo", severidad: "grave" })]);
  });

  it("el dinero: un libro descuadrado o un pozo con saldo tras liquidar es crítico", () => {
    const h = revisar(foto([], { descuadre: 3, pozosConSaldo: { viejo: 12 } }));
    expect(h.filter((x) => x.codigo === "pozo_descuadrado").map((x) => x.severidad)).toEqual(["critico", "critico"]);
  });

  it("una familia que debería tener algo abierto y no tiene nada", () => {
    const h = revisar(
      foto([mercado({ fuente: "partido" })], {
        familias: [
          { nombre: "partidos", es: (m) => m.fuente === "partido" },
          { nombre: "sismos", es: (m) => m.fuente === "sismo" },
        ],
      }),
    );
    expect(h.filter((x) => x.codigo === "familia_vacia").map((x) => x.sujeto)).toEqual(["sismos"]);
  });

  it("un lado con pozo vacío paga infinito; un título que no cabe se corta", () => {
    const h = revisar(
      foto([mercado({ shortTitle: "x".repeat(40), pozo: { outcomes: { si: 100, no: 0 }, feeBps: 300 } })], { tituloIdeal: 32 }),
    );
    expect(h.map((x) => x.codigo).sort()).toEqual(["pago_infinito", "titulo_largo"]);
  });
});

describe("Revisor — registra cambios, no observaciones", () => {
  it("abre con fecha, conserva la fecha mientras sigue, y cierra cuando deja de verse", () => {
    const h = revisar(foto([], { descuadre: 1 }));
    const primero = conciliar([], h, AHORA);
    expect(primero.abren).toHaveLength(1);
    const segundo = conciliar(primero.abiertos, h, AHORA + H);
    expect(segundo.abren).toEqual([]);
    expect(segundo.abiertos[0].desde).toBe(new Date(AHORA).toISOString());
    const tercero = conciliar(segundo.abiertos, [], AHORA + 2 * H);
    expect(tercero.cierran.map((x) => x.codigo)).toEqual(["pozo_descuadrado"]);
    expect(tercero.abiertos).toEqual([]);
  });
});

describe("Retener — la única acción del revisor sobre dinero", () => {
  const spec = {
    sourceName: "x",
    sourceUrl: "https://x",
    criterion: "x",
    settlesAt: new Date(AHORA).toISOString(),
    disputeWindowHours: 24,
  };

  it("la siguiente lectura del oráculo no deshace la retención", () => {
    const retenido = retener({ marketId: "m", phase: "en_disputa", outcome: "si", evidence: "x" }, "no cuadra");
    expect(retenido).toMatchObject({ phase: "atorado", retenidoPor: "revisor" });
    const leido = onRead(retenido, { status: "resuelto", outcome: "si", evidence: "x" }, spec, AHORA);
    expect(leido).toBe(retenido);
  });

  it("una persona la libera resolviendo a mano", () => {
    const retenido = retener({ marketId: "m", phase: "en_disputa", outcome: "si", evidence: "x" }, "no cuadra");
    expect(resolveByHand(retenido, "no", "revisado", spec, AHORA).retenidoPor).toBeUndefined();
  });

  it("no toca lo ya pagado", () => {
    const pagado = { marketId: "m", phase: "pagado" as const, outcome: "si" };
    expect(retener(pagado, "tarde")).toBe(pagado);
  });
});

describe("En el servidor — el ciclo, el revisor y la bitácora juntos", () => {
  const seed: OwnMarketSeed = validateSeed({
    id: "mal-resuelto",
    title: "¿Un mercado cuyo oráculo contesta algo que no existe?",
    shortTitle: "Oráculo despistado",
    outcomes: [
      { id: "si", label: "Pasa" },
      { id: "no", label: "No pasa" },
    ],
    category: "economia",
    country: "MX",
    closesAt: new Date(AHORA - 48 * H).toISOString(),
    pool: binaryPool(200, 200, 300),
    resolution: {
      sourceName: "Banco de México (serie SF43718)",
      sourceUrl: "https://www.banxico.org.mx/SieAPIRest/service/v1/series/SF43718/datos/oportuno",
      criterion: "Se resuelve Pasa si el tipo de cambio FIX publicado por el Banco de México supera 18. Se lee del endpoint público.",
      settlesAt: new Date(AHORA - 24 * H).toISOString(),
      disputeWindowHours: 12,
    },
  });
  const despistado: Oracle = {
    id: "despistado",
    handles: () => true,
    read: async () => ({ status: "resuelto", outcome: "tal-vez", evidence: "un valor raro" }),
  };

  it("el ciclo retiene en el punto de pago; el revisor lo registra una sola vez y la cadena verifica", async () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-revisor-"));
    try {
      const store = new Store(dir);
      sembrarPozos(store, [seed]);
      store.guardarLiquidacion(initialState(seed.id));
      const ciclo = await correrCiclo(store, [seed], [despistado], AHORA);
      expect(ciclo.pagados).toBe(0);
      expect(ciclo.errores.join()).toMatch(/fuera de las opciones; pago retenido/);
      expect(store.liquidacion(seed.id)).toMatchObject({ phase: "atorado", retenidoPor: "revisor" });

      // el siguiente ciclo no lo reabre ni lo paga
      await correrCiclo(store, [seed], [despistado], AHORA + H);
      expect(store.liquidacion(seed.id)?.phase).toBe("atorado");

      const r1 = correrRevisor(store, fotoDe(store, [seed], AHORA + H));
      expect(r1.abren.length).toBeGreaterThan(0);
      const entradas = store.bitacora().length;
      // otra vuelta igual: nada nuevo que anotar
      const r2 = correrRevisor(store, fotoDe(store, [seed], AHORA + 2 * H));
      expect(r2.abren).toEqual([]);
      expect(store.bitacora().length).toBe(entradas);
      expect(verificarCadena(store.bitacora()).ok).toBe(true);
      // la bitácora sobrevive a un reinicio
      expect(verificarCadena(new Store(dir).bitacora())).toEqual({ ok: true, entradas });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("el revisor retiene un mercado en disputa con un resultado inválido que llegó por otro camino", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-revisor-"));
    try {
      const store = new Store(dir);
      sembrarPozos(store, [seed]);
      store.guardarLiquidacion({ marketId: seed.id, phase: "en_disputa", outcome: "tal-vez", evidence: "x", disputeUntil: new Date(AHORA + 24 * H).toISOString() });
      const r = correrRevisor(store, fotoDe(store, [seed], AHORA));
      expect(r.retenidos).toEqual([seed.id]);
      expect(store.bitacora().map((e) => e.tipo)).toContain("retener");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
