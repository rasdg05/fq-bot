import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Store } from "../server/store.mts";
import { correrCiclo } from "../server/ciclo.mts";
import { posicionesDe, sembrarPozos } from "../server/mercados.mts";
import {
  hashear,
  firmarSesion,
  generarCodigoRecuperacion,
  leerSesion,
  normalizarCodigo,
  verificar,
} from "../server/auth.mts";
import { limpiarEvento } from "../server/eventos.mts";
import { calcularTabla } from "../server/tabla.mts";
import { descripcionDe, metaDeMercado } from "../server/compartir.mts";
import { construirMercado } from "../server/mercados.mts";
import { validateSeed, type OwnMarketSeed } from "@/adapters/ownMarkets/catalog";
import type { Oracle } from "@/domain/settlement";
import { binaryPool } from "@/domain/parimutuel";

/**
 * El servidor es lo que convierte a Marea en producto: sin él, la apuesta de
 * alguien vive en la memoria de su navegador y desaparece al recargar.
 */

const AHORA = Date.parse("2026-08-12T00:00:00Z");

const seed: OwnMarketSeed = validateSeed({
  id: "btc-servidor",
  title: "¿Bitcoin cierra la semana arriba de 71,000 dólares?",
  shortTitle: "Bitcoin cierra la semana arriba de 71 mil",
  outcomes: [
    { id: "si", label: "Arriba de 71,000" },
    { id: "no", label: "Abajo de 71,000" },
  ],
  category: "cripto",
  country: "LATAM",
  closesAt: "2026-08-10T00:00:00Z",
  pool: binaryPool(100, 100, 300),
  resolution: {
    sourceName: "Kraken (velas diarias públicas)",
    sourceUrl: "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440",
    criterion:
      "Se resuelve Sí si la vela diaria de BTC/USD en Kraken del domingo cierra por encima de 71,000 dólares.",
    settlesAt: "2026-08-10T23:59:00Z",
    disputeWindowHours: 12,
  },
});

const oraculoSi: Oracle = {
  id: "prueba",
  handles: () => true,
  read: async () => ({ status: "resuelto", outcome: "si", evidence: "cierre 72,500 USD" }),
};

let dir: string;
let store: Store;

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "marea-"));
  store = new Store(dir);
  sembrarPozos(store, [seed]);
});

afterEach(() => rmSync(dir, { recursive: true, force: true }));

function alta(usuario: string, password = "marea12345") {
  const { hash, salt } = hashear(password);
  return store.crearUsuario({
    id: `id-${usuario}`,
    usuario,
    hash,
    salt,
    creado: new Date(AHORA).toISOString(),
    puntos: 1_000,
  });
}

describe("Servidor · cuentas y persistencia", () => {
  it("V47 lo que apuesta alguien sobrevive a reiniciar el servidor", () => {
    const usuario = alta("rasdg");
    store.apostar({
      usuarioId: usuario.id,
      marketId: seed.id,
      side: "si",
      stake: 300,
      precio: 0.5,
    });

    // otro proceso, mismo disco: es exactamente lo que pasa en un redeploy
    const otro = new Store(dir);
    expect(otro.usuarioPorNombre("rasdg")?.puntos).toBe(700);
    expect(otro.apuestasDe(usuario.id)).toHaveLength(1);
    expect(otro.pozo(seed.id)).toMatchObject({ outcomes: { si: 400, no: 100 } });
  });

  it("V48 el pozo es uno solo: lo que apuesta uno mueve el precio del otro", () => {
    const ana = alta("ana");
    const beto = alta("beto");
    store.apostar({ usuarioId: ana.id, marketId: seed.id, side: "si", stake: 500, precio: 0.5 });
    store.apostar({ usuarioId: beto.id, marketId: seed.id, side: "si", stake: 100, precio: 0.75 });

    const pozo = store.pozo(seed.id)!;
    expect(pozo.outcomes.si).toBe(700);
    // el segundo entra a un precio peor porque el primero ya movió el pozo
    expect(
      pozo.outcomes.si / (pozo.outcomes.si + pozo.outcomes.no),
    ).toBeGreaterThan(0.5);
  });

  it("V49 nadie apuesta más de lo que tiene: no hay crédito", () => {
    const usuario = alta("sinfondos");
    expect(() =>
      store.apostar({
        usuarioId: usuario.id,
        marketId: seed.id,
        side: "si",
        stake: 5_000,
        precio: 0.5,
      }),
    ).toThrow(/saldo insuficiente/);
    expect(store.usuarioPorId(usuario.id)?.puntos).toBe(1_000);
  });

  it("V50 la contraseña no se guarda y la sesión no se puede falsificar", () => {
    const usuario = alta("segura", "contrasena-larga");
    expect(JSON.stringify(usuario)).not.toContain("contrasena-larga");
    expect(verificar("contrasena-larga", usuario)).toBe(true);
    expect(verificar("otra-cosa-larga", usuario)).toBe(false);

    const token = firmarSesion(usuario.id);
    expect(leerSesion(token)).toBe(usuario.id);
    expect(leerSesion(`${usuario.id}.9999999999999.firmainventada`)).toBeNull();
    expect(leerSesion(firmarSesion(usuario.id, 0))).toBeNull();
  });
});

describe("Servidor · liquidación que paga a la gente", () => {
  it("V51 al resolver, el ganador cobra en su cuenta y el perdedor no", async () => {
    const ana = alta("ana");
    const beto = alta("beto");
    store.apostar({ usuarioId: ana.id, marketId: seed.id, side: "si", stake: 300, precio: 0.5 });
    store.apostar({ usuarioId: beto.id, marketId: seed.id, side: "no", stake: 300, precio: 0.5 });

    // primera corrida: lee la fuente y abre la ventana de disputa
    await correrCiclo(store, [seed], [oraculoSi], AHORA);
    expect(store.liquidacion(seed.id)?.phase).toBe("en_disputa");
    // dentro de la ventana no se paga, aunque el resultado ya se conozca
    expect(store.usuarioPorId(ana.id)?.puntos).toBe(700);

    // pasada la ventana, se paga
    const resumen = await correrCiclo(store, [seed], [oraculoSi], AHORA + 2 * 86_400_000);
    expect(store.liquidacion(seed.id)?.phase).toBe("pagado");
    expect(resumen.acreditado).toBeGreaterThan(0);

    const saldoAna = store.usuarioPorId(ana.id)!.puntos;
    const saldoBeto = store.usuarioPorId(beto.id)!.puntos;
    // pozo de 800 menos 3 %, repartido entre los 400 del lado Sí
    expect(saldoAna).toBeCloseTo(700 + (800 * 0.97 * 300) / 400, 6);
    expect(saldoBeto).toBe(700);
  });

  it("V62 un mercado con un solo apostador se anula y se devuelve todo", async () => {
    const ana = alta("ana");
    store.apostar({ usuarioId: ana.id, marketId: seed.id, side: "si", stake: 300, precio: 0.5 });

    await correrCiclo(store, [seed], [oraculoSi], AHORA);
    const resumen = await correrCiclo(store, [seed], [oraculoSi], AHORA + 2 * 86_400_000);

    // acertó, pero no le ganó a nadie: el pozo perdedor era nuestra semilla
    expect(resumen.anulados).toBe(1);
    expect(resumen.pagados).toBe(0);
    expect(store.usuarioPorId(ana.id)!.puntos).toBe(1_000);
    expect(store.liquidacion(seed.id)?.phase).toBe("devuelto");
    expect(store.liquidacion(seed.id)?.stuckReason).toMatch(/hizo falta gente/);

    const [posicion] = posicionesDe(store, ana.id, [seed]);
    expect(posicion.payout).toBe(300);
    expect(posicion.pnl).toBe(0);
  });

  it("V66 la comisión llega a la tesorería y cuadra con el pozo", async () => {
    const ana = alta("ana");
    const beto = alta("beto");
    store.apostar({ usuarioId: ana.id, marketId: seed.id, side: "si", stake: 300, precio: 0.5 });
    store.apostar({ usuarioId: beto.id, marketId: seed.id, side: "no", stake: 300, precio: 0.5 });

    await correrCiclo(store, [seed], [oraculoSi], AHORA);
    const resumen = await correrCiclo(store, [seed], [oraculoSi], AHORA + 2 * 86_400_000);

    // 3 % del pozo de 800: si se resta del reparto, tiene que llegar a algún lado
    expect(resumen.comision).toBeCloseTo(800 * 0.03, 6);
    expect(store.tesoreria()).toBeCloseTo(800 * 0.03, 6);

    // y lo repartido más la comisión es el pozo entero: nada se evapora
    const pagado = store.apuestasDeMercado(seed.id).reduce((s, a) => s + (a.pagado ?? 0), 0);
    const pozo = store.pozo(seed.id)!;
    // el resto es la parte de la semilla, que se queda con la casa
    expect(pagado + store.tesoreria()).toBeLessThanOrEqual(
      pozo.outcomes.si + pozo.outcomes.no + 1e-6,
    );

    // correrlo otra vez no cobra dos veces
    await correrCiclo(store, [seed], [oraculoSi], AHORA + 3 * 86_400_000);
    expect(store.tesoreria()).toBeCloseTo(800 * 0.03, 6);
  });

  it("V67 un mercado anulado no deja comisión: se devuelve todo", async () => {
    const ana = alta("ana");
    store.apostar({ usuarioId: ana.id, marketId: seed.id, side: "si", stake: 300, precio: 0.5 });

    await correrCiclo(store, [seed], [oraculoSi], AHORA);
    await correrCiclo(store, [seed], [oraculoSi], AHORA + 2 * 86_400_000);

    expect(store.tesoreria()).toBe(0);
    expect(store.usuarioPorId(ana.id)!.puntos).toBe(1_000);
  });

  it("V52 correr el ciclo mil veces paga una sola vez", async () => {
    const ana = alta("ana");
    const beto = alta("beto");
    store.apostar({ usuarioId: ana.id, marketId: seed.id, side: "si", stake: 300, precio: 0.5 });
    store.apostar({ usuarioId: beto.id, marketId: seed.id, side: "no", stake: 100, precio: 0.5 });

    await correrCiclo(store, [seed], [oraculoSi], AHORA);
    await correrCiclo(store, [seed], [oraculoSi], AHORA + 2 * 86_400_000);
    const despuesDelPago = store.usuarioPorId(ana.id)!.puntos;

    for (let i = 0; i < 5; i += 1) {
      await correrCiclo(store, [seed], [oraculoSi], AHORA + 3 * 86_400_000);
    }
    expect(store.usuarioPorId(ana.id)!.puntos).toBe(despuesDelPago);
  });

  it("V53 el portafolio muestra el resultado con la lectura que lo justifica", async () => {
    const ana = alta("ana");
    const beto = alta("beto");
    store.apostar({ usuarioId: ana.id, marketId: seed.id, side: "si", stake: 300, precio: 0.5 });
    // hace falta más de uno: con un solo apostador el mercado se anula (R-059)
    store.apostar({ usuarioId: beto.id, marketId: seed.id, side: "no", stake: 100, precio: 0.5 });

    await correrCiclo(store, [seed], [oraculoSi], AHORA);
    await correrCiclo(store, [seed], [oraculoSi], AHORA + 2 * 86_400_000);

    const [posicion] = posicionesDe(store, ana.id, [seed]);
    expect(posicion.status).toBe("won");
    expect(posicion.payout).toBeGreaterThan(posicion.size);
    expect(posicion.evidence).toContain("72,500");
  });
});

describe("Servidor · tabla y compartir", () => {
  async function conResultado() {
    const ana = alta("ana");
    const beto = alta("beto");
    store.apostar({ usuarioId: ana.id, marketId: seed.id, side: "si", stake: 300, precio: 0.5 });
    store.apostar({ usuarioId: beto.id, marketId: seed.id, side: "no", stake: 300, precio: 0.5 });
    await correrCiclo(store, [seed], [oraculoSi], AHORA);
    await correrCiclo(store, [seed], [oraculoSi], AHORA + 2 * 86_400_000);
    return { ana, beto };
  }

  it("V54 la tabla mide precisión y racha, no cuánto apostaste", async () => {
    const { ana } = await conResultado();
    const tabla = calcularTabla(store, ana.id);

    // sólo entra quien ya tiene un mercado resuelto
    expect(tabla.filas).toHaveLength(2);
    const fila = tabla.filas.find((f) => f.usuario === "ana")!;
    expect(fila.aciertos).toBe(1);
    expect(fila.resueltas).toBe(1);
    expect(fila.precision).toBe(1);
    expect(fila.racha).toBe(1);

    const perdedor = tabla.filas.find((f) => f.usuario === "beto")!;
    expect(perdedor.precision).toBe(0);
    expect(perdedor.racha).toBe(0);

    // quien pregunta ve su lugar aunque esté fuera del top
    expect(tabla.tuya?.usuario).toBe("ana");
  });

  it("V55 quien no tiene nada resuelto no aparece en la tabla", () => {
    alta("nuevo");
    expect(calcularTabla(store).filas).toHaveLength(0);
  });

  it("V56 la liga compartida lleva la pregunta y la probabilidad en la vista previa", () => {
    const mercado = construirMercado(store, seed, Infinity, AHORA);
    const html = `<!doctype html><html><head>
      <meta
        name="description"
        content="Marea"
      />
      <title>Marea</title>
    </head><body></body></html>`;

    const salida = metaDeMercado(html, mercado, "https://marea.app");
    expect(salida).toContain('property="og:title"');
    expect(salida).toContain(seed.title);
    expect(salida).toContain("https://marea.app/m/btc-servidor");
    // el título viejo no puede sobrevivir: sería el que se ve al compartir
    expect(salida).not.toMatch(/<title>Marea<\/title>/);

    // sin Edge no se promete Edge, justo en la superficie que más se comparte
    expect(descripcionDe(mercado)).not.toMatch(/Edge/);
    expect(descripcionDe(mercado)).toMatch(/%/);
  });

  it("V57 el HTML compartido escapa lo que venga del título", () => {
    const mercado = {
      ...construirMercado(store, seed, Infinity, AHORA),
      title: 'Bitcoin "arriba" <script>alert(1)</script>',
    };
    const salida = metaDeMercado("<head><title>x</title></head>", mercado, "https://marea.app");
    expect(salida).not.toContain("<script>");
    expect(salida).toContain("&lt;script&gt;");
  });
});

describe("Servidor · recuperación y analítica", () => {
  it("V63 el código de recuperación devuelve la cuenta, y sólo el correcto", () => {
    const codigo = generarCodigoRecuperacion();
    const guardado = hashear(codigo);

    // se guarda el hash, nunca el código
    expect(guardado.hash).not.toContain(codigo);
    // y quien lo escribe en minúsculas o con espacios también entra
    expect(hashear(normalizarCodigo(` ${codigo.toLowerCase()} `), guardado.salt).hash).toBe(
      guardado.hash,
    );
    expect(hashear("XXXX-XXXX-XXXX", guardado.salt).hash).not.toBe(guardado.hash);
  });

  it("V64 el código no trae caracteres que se confundan al dictarlo", () => {
    for (let i = 0; i < 40; i += 1) {
      const codigo = generarCodigoRecuperacion();
      expect(codigo).toMatch(/^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$/);
      // sin O ni 0, sin I ni 1: se dicta por teléfono
      expect(codigo).not.toMatch(/[O0I1]/);
    }
  });

  it("V65 la analítica descarta lo que no está en la lista blanca", () => {
    const limpio = limpiarEvento(
      {
        event: "view_feed",
        props: { count: 17, direccion: "0xSECRETO", texto: "no debe salir", anidado: {} },
      },
      "rasdg",
    );
    expect(limpio?.props).toEqual({ count: 17 });
    expect(limpio?.usuario).toBe("rasdg");

    // un evento inventado no entra
    expect(limpiarEvento({ event: "robar_datos", props: {} })).toBeNull();
    // y el usuario sale de la sesión del servidor, no de lo que mande el cliente
    expect(limpiarEvento({ event: "view_feed", usuario: "otro" })?.usuario).toBeUndefined();
  });
});
