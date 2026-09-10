import { describe, expect, it } from "vitest";
import {
  exposicionViva,
  filtrarPorPresupuesto,
  mercadoVivoDe,
  puedeCrear,
  sinSemillaDeclarada,
  subsidioDe,
  subsidioVivo,
  topesDelEntorno,
  TOPES_POR_DEFECTO,
  type MercadoVivo,
} from "@/domain/presupuesto";
import { OWN_MARKETS } from "@/adapters/ownMarkets/catalog";
import { rollingSeeds } from "@/adapters/ownMarkets/templates";

/**
 * El freno de L9. Lo que se prueba no es que sume: es que **se niegue**, que
 * diga por qué, y que no se le pueda colar una tanda que junta cruza el tope
 * aunque ninguno lo cruce solo.
 */

const subsidio = (id: string, semilla: number): MercadoVivo => ({
  id,
  semilla,
  modo: "subsidio",
  declarada: true,
});
const apuesta = (id: string, semilla: number): MercadoVivo => ({
  id,
  semilla,
  modo: "apuesta",
  declarada: true,
});

describe("Presupuesto de subsidio (L9)", () => {
  it("sólo el subsidio es coste: una semilla que puede volver no lo es", () => {
    expect(subsidioDe(subsidio("a", 500))).toBe(500);
    expect(subsidioDe(apuesta("b", 500))).toBe(0);
    // pero las dos son exposición: dinero de la casa dentro de un mercado
    expect(exposicionViva([subsidio("a", 500), apuesta("b", 500)])).toBe(1000);
    expect(subsidioVivo([subsidio("a", 500), apuesta("b", 500)])).toBe(500);
  });

  it("con el presupuesto agotado, la creación se niega y dice por qué", () => {
    const vivos = [subsidio("a", 800), subsidio("b", 150)];
    const v = puedeCrear({
      vivos,
      candidato: subsidio("c", 100),
      topes: { porMercado: 500, abierto: 1000 },
    });
    expect(v.permitido).toBe(false);
    expect(v.motivo).toContain("1050"); // el número que lo causó, no una opinión
    expect(v.motivo).toContain("1000");
    expect(v.medido.subsidioVivo).toBe(950);
    expect(v.medido.subsidioTrasCrear).toBe(1050);
  });

  it("un solo mercado por encima del tope por mercado se niega aunque quepa en el total", () => {
    const v = puedeCrear({
      vivos: [],
      candidato: subsidio("gordo", 900),
      topes: { porMercado: 500, abierto: 100_000 },
    });
    expect(v.permitido).toBe(false);
    expect(v.motivo).toContain("tope por mercado");
  });

  it("justo en el tope pasa; un céntimo por encima no", () => {
    const topes = { porMercado: 500, abierto: 1000 };
    expect(puedeCrear({ vivos: [subsidio("a", 500)], candidato: subsidio("b", 500), topes }).permitido).toBe(true);
    expect(puedeCrear({ vivos: [subsidio("a", 500)], candidato: subsidio("b", 500.01), topes }).permitido).toBe(false);
  });

  it("una tanda que junta cruza el tope no se cuela: se cuentan entre sí", () => {
    // ninguno cruza solo el tope abierto de 1000; los tres juntos sí
    const candidatos = [subsidio("a", 400), subsidio("b", 400), subsidio("c", 400)];
    const { aceptados, rechazados } = filtrarPorPresupuesto({
      vivos: [],
      candidatos,
      topes: { porMercado: 500, abierto: 1000 },
    });
    expect(aceptados.map((m) => m.id)).toEqual(["a", "b"]);
    expect(rechazados.map((r) => r.mercado.id)).toEqual(["c"]);
    expect(subsidioVivo(aceptados)).toBe(800);
  });

  it("el freno nace armado: sin presupuesto configurado, un subsidio no se crea", () => {
    // R-067 pide subsidio CON tope. Primero el tope, después el gasto
    const v = puedeCrear({ vivos: [], candidato: subsidio("nuevo", 100) });
    expect(v.permitido).toBe(false);
    expect(TOPES_POR_DEFECTO.abierto).toBe(0);
  });

  it("y no estorba a lo que hay hoy: nada nace en subsidio, así que todo pasa", () => {
    const vivos = OWN_MARKETS.map(mercadoVivoDe);
    expect(subsidioVivo(vivos)).toBe(0);
    for (const seed of OWN_MARKETS) {
      expect(puedeCrear({ vivos, candidato: mercadoVivoDe(seed) }).permitido).toBe(true);
    }
  });
});

describe("Presupuesto — lo que no se puede sumar", () => {
  it("un pozo sin semilla declarada no se cuenta como cero: se marca", () => {
    const viejo = mercadoVivoDe({ id: "viejo", pool: {} });
    expect(viejo.declarada).toBe(false);
    expect(viejo.semilla).toBe(0);
    expect(sinSemillaDeclarada([viejo, apuesta("nuevo", 100)])).toEqual(["viejo"]);
  });

  it("con tope de exposición y mercados opacos, se niega en vez de sumar de menos", () => {
    // sumar cero por los opacos es una cota inferior, y una cota inferior
    // contra un tope hace que el freno se dispare tarde — o sea, que no frene
    const vivos = [apuesta("a", 400), mercadoVivoDe({ id: "opaco", pool: {} })];
    const v = puedeCrear({
      vivos,
      candidato: apuesta("nuevo", 100),
      topes: { porMercado: 0, abierto: 0, exposicion: 10_000 },
    });
    expect(v.permitido).toBe(false);
    expect(v.motivo).toContain("sin semilla declarada");
    expect(v.medido.sinDeclarar).toBe(1);
  });

  it("sin tope de exposición, los opacos no estorban: no hay nada que hacer cumplir", () => {
    const vivos = [apuesta("a", 400), mercadoVivoDe({ id: "opaco", pool: {} })];
    const v = puedeCrear({ vivos, candidato: apuesta("nuevo", 100) });
    expect(v.permitido).toBe(true);
    expect(v.medido.sinDeclarar).toBe(1); // se mide igual, para que se vea
  });

  it("la semilla declarada se lee del pozo, los dos modos", () => {
    expect(mercadoVivoDe({ id: "m", pool: { seed: { si: 300, no: 200 }, seedMode: "subsidio" } })).toEqual({
      id: "m",
      semilla: 500,
      modo: "subsidio",
      declarada: true,
    });
    // sin modo, apuesta: es lo que hubo siempre
    expect(mercadoVivoDe({ id: "m", pool: { seed: { si: 100, no: 100 } } }).modo).toBe("apuesta");
  });
});

describe("Presupuesto — los topes del entorno", () => {
  it("lo que no está configurado no se inventa", () => {
    const topes = topesDelEntorno({});
    expect(topes.porMercado).toBe(0);
    expect(topes.abierto).toBe(0);
    expect(topes.exposicion).toBeUndefined(); // sin tope, y se dice
  });

  it("lee los tres topes", () => {
    const topes = topesDelEntorno({
      MAREA_SUBSIDIO_MAX_MERCADO: "500",
      MAREA_SUBSIDIO_MAX_ABIERTO: "5000",
      MAREA_EXPOSICION_MAX: "20000",
    });
    expect(topes).toEqual({ porMercado: 500, abierto: 5000, exposicion: 20_000 });
  });

  it("un tope mal escrito se ignora y AVISA, no se lee como NaN", () => {
    // un NaN haría pasar cualquier comparación: un freno que siempre dice que
    // sí es el mismo que no existe
    const avisos: string[] = [];
    const topes = topesDelEntorno(
      { MAREA_SUBSIDIO_MAX_ABIERTO: "cinco mil", MAREA_EXPOSICION_MAX: "-3" },
      (m) => avisos.push(m),
    );
    expect(topes.abierto).toBe(0); // cae al default armado, no a NaN
    expect(topes.exposicion).toBeUndefined();
    expect(avisos.length).toBe(2);
    expect(avisos[0]).toContain("MAREA_SUBSIDIO_MAX_ABIERTO");
  });
});

/**
 * El guardia de `roll.mts`, probado sin tocar la red.
 *
 * `roll` sale a Kraken y a ESPN y reescribe el catálogo de producción, así que
 * no se corre desde aquí. Lo que sí se puede correr es exactamente lo que
 * `roll` decide: los mismos candidatos que genera `rollingSeeds`, el mismo
 * `filtrarPorPresupuesto`, los mismos topes. Si esto pasa, el guardia pasa —
 * lo que queda en el script es una llamada y un `console.warn`.
 */
describe("El guardia de roll (L9), sin red", () => {
  const AHORA = Date.UTC(2026, 8, 8, 12, 0, 0);
  const candidatos = rollingSeeds({ spot: { "BTC/USD": 68_000, "ETH/USD": 3_400 }, now: AHORA });

  it("hay candidatos de verdad que juzgar", () => {
    expect(candidatos.length).toBeGreaterThan(0);
  });

  it("hoy no estorba: nada nace en subsidio, se crean todos", () => {
    const { aceptados, rechazados } = filtrarPorPresupuesto({
      vivos: OWN_MARKETS.map(mercadoVivoDe),
      candidatos: candidatos.map(mercadoVivoDe),
      topes: topesDelEntorno({}),
    });
    expect(aceptados.length).toBe(candidatos.length);
    expect(rechazados).toEqual([]);
  });

  it("si alguien enciende el subsidio sin presupuesto, roll no crea NADA y dice por qué", () => {
    // el mismo catálogo, con las semillas en modo subsidio: es la línea que
    // U4 deja lista para U-siguiente y el momento exacto en que el freno actúa
    const enSubsidio = candidatos
      .map(mercadoVivoDe)
      .map((m) => ({ ...m, modo: "subsidio" as const }));
    const { aceptados, rechazados } = filtrarPorPresupuesto({
      vivos: OWN_MARKETS.map(mercadoVivoDe),
      candidatos: enSubsidio,
      topes: topesDelEntorno({}),
    });
    expect(aceptados).toEqual([]);
    expect(rechazados.length).toBe(enSubsidio.length);
    expect(rechazados[0].motivo).toContain("tope");
  });

  it("con presupuesto puesto, se crean los que caben y se para en el que no", () => {
    const enSubsidio = candidatos
      .map(mercadoVivoDe)
      .map((m) => ({ ...m, modo: "subsidio" as const }));
    const cabe = enSubsidio[0].semilla + enSubsidio[1].semilla;
    const { aceptados, rechazados } = filtrarPorPresupuesto({
      vivos: [],
      candidatos: enSubsidio,
      topes: topesDelEntorno({
        MAREA_SUBSIDIO_MAX_MERCADO: String(Math.max(...enSubsidio.map((m) => m.semilla))),
        MAREA_SUBSIDIO_MAX_ABIERTO: String(cabe),
      }),
    });
    expect(aceptados.length).toBe(2);
    expect(rechazados.length).toBe(enSubsidio.length - 2);
    expect(subsidioVivo(aceptados)).toBe(cabe);
  });
});
