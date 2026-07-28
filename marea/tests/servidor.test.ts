import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Store } from "../server/store.mts";
import { correrCiclo } from "../server/ciclo.mts";
import { posicionesDe, sembrarPozos } from "../server/mercados.mts";
import { hashear, firmarSesion, leerSesion, verificar } from "../server/auth.mts";
import { validateSeed, type OwnMarketSeed } from "@/adapters/ownMarkets/catalog";
import type { Oracle } from "@/domain/settlement";

/**
 * El servidor es lo que convierte a Marea en producto: sin él, la apuesta de
 * alguien vive en la memoria de su navegador y desaparece al recargar.
 */

const AHORA = Date.parse("2026-08-12T00:00:00Z");

const seed: OwnMarketSeed = validateSeed({
  id: "btc-servidor",
  title: "¿Bitcoin cierra la semana arriba de 71,000 dólares?",
  category: "cripto",
  country: "LATAM",
  closesAt: "2026-08-10T00:00:00Z",
  pool: { si: 100, no: 100, feeBps: 300 },
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
    expect(otro.pozo(seed.id)).toMatchObject({ si: 400, no: 100 });
  });

  it("V48 el pozo es uno solo: lo que apuesta uno mueve el precio del otro", () => {
    const ana = alta("ana");
    const beto = alta("beto");
    store.apostar({ usuarioId: ana.id, marketId: seed.id, side: "si", stake: 500, precio: 0.5 });
    store.apostar({ usuarioId: beto.id, marketId: seed.id, side: "si", stake: 100, precio: 0.75 });

    const pozo = store.pozo(seed.id)!;
    expect(pozo.si).toBe(700);
    // el segundo entra a un precio peor porque el primero ya movió el pozo
    expect(pozo.si / (pozo.si + pozo.no)).toBeGreaterThan(0.5);
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

  it("V52 correr el ciclo mil veces paga una sola vez", async () => {
    const ana = alta("ana");
    store.apostar({ usuarioId: ana.id, marketId: seed.id, side: "si", stake: 300, precio: 0.5 });

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
    store.apostar({ usuarioId: ana.id, marketId: seed.id, side: "si", stake: 300, precio: 0.5 });

    await correrCiclo(store, [seed], [oraculoSi], AHORA);
    await correrCiclo(store, [seed], [oraculoSi], AHORA + 2 * 86_400_000);

    const [posicion] = posicionesDe(store, ana.id, [seed]);
    expect(posicion.status).toBe("won");
    expect(posicion.payout).toBeGreaterThan(posicion.size);
    expect(posicion.evidence).toContain("72,500");
  });
});
