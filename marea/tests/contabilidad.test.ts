import { describe, expect, it } from "vitest";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Store } from "../server/store.mts";
import {
  CUENTAS_SISTEMA,
  asiento,
  cuadre,
  cuentaPozo,
  cuentaUsuario,
  saldoDe,
  saldos,
  LibroDesbalanceado,
  type Asiento,
} from "@/domain/contabilidad";
import {
  avanzar,
  crearSolicitud,
  puedeAvanzar,
  ESTADOS_DEPOSITO,
  ESTADOS_RETIRO,
  type Solicitud,
} from "@/domain/solicitudes";
import { contratoSimulado } from "@/adapters/custodia/contrato";
import { eligibilityFor } from "@/domain/eligibility";

/**
 * Contabilidad de partida doble. Sin esto no hay auditoría, y sin auditoría no
 * hay dinero: una comisión que se calcula y desaparece es la forma exacta de
 * perderle la pista al dinero (R-064).
 */

describe("Partida doble", () => {
  it("un asiento que no cuadra no se puede crear", () => {
    expect(() =>
      asiento("prueba", [
        { cuenta: cuentaUsuario("u1"), monto: 100 },
        { cuenta: CUENTAS_SISTEMA.entrada, monto: -90 },
      ]),
    ).toThrow(LibroDesbalanceado);
  });

  it("un asiento con una sola pata no existe: siempre hay contrapartida", () => {
    expect(() => asiento("prueba", [{ cuenta: cuentaUsuario("u1"), monto: 0 }])).toThrow();
  });

  it("depositar mueve de `entrada` al usuario y el libro sigue en cero", () => {
    const libro: Asiento[] = [
      asiento("deposito", [
        { cuenta: CUENTAS_SISTEMA.entrada, monto: -500 },
        { cuenta: cuentaUsuario("u1"), monto: 500 },
      ]),
    ];
    expect(saldoDe(libro, cuentaUsuario("u1"))).toBe(500);
    expect(saldoDe(libro, CUENTAS_SISTEMA.entrada)).toBe(-500);
    expect(cuadre(libro)).toBe(0);
  });

  it("apostar mueve del usuario al pozo del mercado, no a la casa", () => {
    const libro: Asiento[] = [
      asiento("deposito", [
        { cuenta: CUENTAS_SISTEMA.entrada, monto: -500 },
        { cuenta: cuentaUsuario("u1"), monto: 500 },
      ]),
      asiento("apuesta", [
        { cuenta: cuentaUsuario("u1"), monto: -200 },
        { cuenta: cuentaPozo("m1"), monto: 200 },
      ]),
    ];
    expect(saldoDe(libro, cuentaUsuario("u1"))).toBe(300);
    expect(saldoDe(libro, cuentaPozo("m1"))).toBe(200);
    expect(saldoDe(libro, CUENTAS_SISTEMA.tesoreria)).toBe(0);
    expect(cuadre(libro)).toBe(0);
  });

  it("liquidar reparte el pozo y la comisión llega a tesorería, no al aire", () => {
    const libro: Asiento[] = [
      asiento("apuesta", [
        { cuenta: cuentaUsuario("u1"), monto: -300 },
        { cuenta: cuentaPozo("m1"), monto: 300 },
      ]),
      asiento("liquidacion", [
        { cuenta: cuentaPozo("m1"), monto: -300 },
        { cuenta: cuentaUsuario("u1"), monto: 291 },
        { cuenta: CUENTAS_SISTEMA.tesoreria, monto: 9 },
      ]),
    ];
    // el pozo queda vacío tras repartir
    expect(saldoDe(libro, cuentaPozo("m1"))).toBe(0);
    expect(saldoDe(libro, CUENTAS_SISTEMA.tesoreria)).toBe(9);
    expect(cuadre(libro)).toBe(0);
  });

  it("cuadre() da cero tras 500 operaciones aleatorias", () => {
    // la propiedad que sostiene toda la auditoría: pase lo que pase, la suma
    // de todas las cuentas es cero. Si un día no lo es, hay dinero perdido
    const libro: Asiento[] = [];
    const usuarios = ["u1", "u2", "u3", "u4"];
    const mercados = ["m1", "m2", "m3"];
    const saldoUsuario: Record<string, number> = { u1: 0, u2: 0, u3: 0, u4: 0 };
    const saldoPozo: Record<string, number> = { m1: 0, m2: 0, m3: 0 };

    for (let i = 0; i < 500; i += 1) {
      const u = usuarios[Math.floor(Math.random() * usuarios.length)];
      const m = mercados[Math.floor(Math.random() * mercados.length)];
      const tipo = Math.floor(Math.random() * 4);
      const monto = Math.floor(Math.random() * 500) + 1;

      if (tipo === 0) {
        libro.push(
          asiento("deposito", [
            { cuenta: CUENTAS_SISTEMA.entrada, monto: -monto },
            { cuenta: cuentaUsuario(u), monto },
          ]),
        );
        saldoUsuario[u] += monto;
      } else if (tipo === 1 && saldoUsuario[u] >= monto) {
        libro.push(
          asiento("apuesta", [
            { cuenta: cuentaUsuario(u), monto: -monto },
            { cuenta: cuentaPozo(m), monto },
          ]),
        );
        saldoUsuario[u] -= monto;
        saldoPozo[m] += monto;
      } else if (tipo === 2 && saldoPozo[m] > 0) {
        const total = saldoPozo[m];
        const comision = Math.floor(total * 0.03);
        libro.push(
          asiento("liquidacion", [
            { cuenta: cuentaPozo(m), monto: -total },
            { cuenta: cuentaUsuario(u), monto: total - comision },
            { cuenta: CUENTAS_SISTEMA.tesoreria, monto: comision },
          ]),
        );
        saldoUsuario[u] += total - comision;
        saldoPozo[m] = 0;
      } else if (tipo === 3 && saldoUsuario[u] >= monto) {
        libro.push(
          asiento("retiro", [
            { cuenta: cuentaUsuario(u), monto: -monto },
            { cuenta: CUENTAS_SISTEMA.salida, monto },
          ]),
        );
        saldoUsuario[u] -= monto;
      }
    }

    expect(libro.length).toBeGreaterThan(50);
    expect(cuadre(libro)).toBe(0);
    // y los saldos del libro coinciden con los que llevamos por fuera
    for (const u of usuarios) {
      expect(saldoDe(libro, cuentaUsuario(u)), u).toBe(saldoUsuario[u]);
    }
    // ningún usuario terminó en negativo: no hay crédito, jamás
    for (const u of usuarios) expect(saldoUsuario[u]).toBeGreaterThanOrEqual(0);
  });

  it("los saldos por cuenta suman exactamente lo mismo que el libro", () => {
    const libro: Asiento[] = [
      asiento("deposito", [
        { cuenta: CUENTAS_SISTEMA.entrada, monto: -100 },
        { cuenta: cuentaUsuario("u1"), monto: 100 },
      ]),
      asiento("apuesta", [
        { cuenta: cuentaUsuario("u1"), monto: -40 },
        { cuenta: cuentaPozo("m1"), monto: 40 },
      ]),
    ];
    const todos = saldos(libro);
    expect(Object.values(todos).reduce((s, v) => s + v, 0)).toBe(0);
    expect(todos[cuentaUsuario("u1")]).toBe(60);
  });
});

describe("Solicitudes de depósito y retiro", () => {
  /**
   * La máquina de estados se prueba con la solicitud construida a mano, a
   * propósito: `crearSolicitud` no deja crear ninguna mientras la puerta de
   * elegibilidad esté cerrada, y debilitar la puerta para poder probar el resto
   * sería abrir el camino de dinero por la puerta de atrás. La puerta tiene su
   * propia prueba más abajo.
   */
  const nueva = (tipo: "deposito" | "retiro"): Solicitud => ({
    id: `${tipo}-prueba`,
    tipo,
    usuarioId: "u1",
    monto: 100,
    pais: "MX",
    estado: "pendiente",
    creada: "2026-07-28T00:00:00Z",
    historial: [{ estado: "pendiente", at: "2026-07-28T00:00:00Z" }],
  });

  it("un depósito recorre pendiente → confirmando → acreditado", () => {
    let s = nueva("deposito");
    expect(s.estado).toBe("pendiente");
    s = avanzar(s, "confirmando");
    s = avanzar(s, "acreditado");
    expect(s.estado).toBe("acreditado");
    expect(ESTADOS_DEPOSITO).toContain("acreditado");
  });

  it("un retiro pasa además por revisión: no sale dinero sin mirarlo", () => {
    let s = nueva("retiro");
    // no se puede saltar la revisión
    expect(puedeAvanzar(s, "acreditado")).toBe(false);
    s = avanzar(s, "en_revision");
    s = avanzar(s, "confirmando");
    s = avanzar(s, "acreditado");
    expect(s.estado).toBe("acreditado");
    expect(ESTADOS_RETIRO).toContain("en_revision");
  });

  it("una solicitud rechazada es terminal: no revive", () => {
    let s = nueva("deposito");
    s = avanzar(s, "rechazado");
    expect(puedeAvanzar(s, "confirmando")).toBe(false);
    expect(() => avanzar(s, "acreditado")).toThrow();
  });

  it("avanzar dos veces al mismo estado no duplica nada (I5)", () => {
    let s = nueva("deposito");
    s = avanzar(s, "confirmando");
    const otraVez = avanzar(s, "confirmando");
    expect(otraVez.historial.length).toBe(s.historial.length);
  });
});

describe("La puerta de elegibilidad sigue cerrada", () => {
  it("ningún país permite mover dinero todavía", () => {
    for (const pais of ["MX", "AR", "BR", "CL", "CO", "PE"] as const) {
      const e = eligibilityFor(pais);
      expect(e.canDeposit, pais).toBe(false);
      expect(e.canExplore, pais).toBe(true);
    }
  });

  it("crear una solicitud en un país sin permiso se rechaza en el acto", () => {
    expect(() =>
      crearSolicitud({ tipo: "deposito", usuarioId: "u1", monto: 100, pais: "US" }),
    ).toThrow(/permiso|país|pais/i);
  });
});

describe("Contrato de custodia", () => {
  it("declara que es simulado: nada finge hablar con una cadena (R-022, I8)", () => {
    const contrato = contratoSimulado();
    expect(contrato.esSimulado).toBe(true);
    expect(contrato.descripcion).toMatch(/simulad/i);
  });

  it("no expone forma de firmar con fondos de usuarios", () => {
    const contrato = contratoSimulado();
    expect(contrato).not.toHaveProperty("firmar");
    expect(contrato).not.toHaveProperty("retirar");
  });
});

describe("El libro del servidor cuadra con la realidad", () => {
  it("el saldo contable de cada usuario es exactamente sus puntos", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-libro-"));
    try {
      const store = new Store(dir);
      store.asegurarPozo({
        marketId: "m1",
        outcomes: { si: 300, no: 200 },
        feeBps: 300,
      });
      for (const id of ["u1", "u2"]) {
        store.crearUsuario({
          id,
          usuario: id,
          hash: "x",
          salt: "y",
          creado: new Date().toISOString(),
          puntos: 1000,
        });
      }
      store.apostar({ usuarioId: "u1", marketId: "m1", side: "si", stake: 200, precio: 0.5 });
      store.apostar({ usuarioId: "u2", marketId: "m1", side: "no", stake: 300, precio: 0.5 });

      expect(store.cuadre()).toBe(0);
      for (const u of store.usuarios()) {
        expect(saldoDe(store.libro(), cuentaUsuario(u.id)), u.id).toBe(u.puntos);
      }
      // el pozo contable es el pozo real, semilla incluida
      const pozo = store.pozo("m1")!;
      const total = Object.values(pozo.outcomes).reduce((s, v) => s + v, 0);
      expect(saldoDe(store.libro(), cuentaPozo("m1"))).toBe(total);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("tras liquidar, el libro sigue en cero y la tesorería concilia", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-liquidar-"));
    try {
      const store = new Store(dir);
      store.asegurarPozo({ marketId: "m1", outcomes: { si: 100, no: 100 }, feeBps: 300 });
      store.crearUsuario({
        id: "u1", usuario: "u1", hash: "x", salt: "y",
        creado: new Date().toISOString(), puntos: 1000,
      });
      store.apostar({ usuarioId: "u1", marketId: "m1", side: "si", stake: 200, precio: 0.5 });

      const pozo = store.pozo("m1")!;
      const total = Object.values(pozo.outcomes).reduce((s, v) => s + v, 0);
      const comision = (total * pozo.feeBps) / 10_000;
      store.pagarMercado("m1", { "m1-1": total - comision });
      store.acumularComision("m1", comision);

      expect(store.cuadre()).toBe(0);
      // el pozo quedó vacío: todo lo que entró salió
      expect(saldoDe(store.libro(), cuentaPozo("m1"))).toBe(0);
      // y la tesorería del resumen coincide con la del libro
      const conciliacion = store.conciliar();
      expect(conciliacion.cuadra, JSON.stringify(conciliacion)).toBe(true);
      expect(conciliacion.libro).toBeCloseTo(comision, 8);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("el libro sobrevive al reinicio del proceso", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-libro-reinicio-"));
    try {
      const store = new Store(dir);
      store.asegurarPozo({ marketId: "m1", outcomes: { si: 100, no: 100 }, feeBps: 300 });
      store.crearUsuario({
        id: "u1", usuario: "u1", hash: "x", salt: "y",
        creado: new Date().toISOString(), puntos: 500,
      });
      const antes = store.libro().length;
      expect(antes).toBeGreaterThan(0);

      const otro = new Store(dir);
      expect(otro.libro().length).toBe(antes);
      expect(otro.cuadre()).toBe(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("Asiento de apertura", () => {
  it("un volumen con saldos vivos y sin libro se abre cuadrado", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-apertura-"));
    try {
      // así estaba producción antes de que existiera el libro
      writeFileSync(
        join(dir, "marea.json"),
        JSON.stringify({
          version: 1,
          usuarios: [
            { id: "u1", usuario: "a", hash: "x", salt: "y", creado: "2026-01-01", puntos: 900 },
            { id: "u2", usuario: "b", hash: "x", salt: "y", creado: "2026-01-01", puntos: 1000 },
          ],
          apuestas: [],
          pozos: [{ marketId: "m1", si: 420, no: 260, feeBps: 300 }],
          liquidaciones: [],
          comisiones: [],
        }),
      );
      const store = new Store(dir);

      expect(store.cuadre()).toBe(0);
      // cada usuario arranca en el libro con los puntos que ya tenía
      for (const u of store.usuarios()) {
        expect(saldoDe(store.libro(), cuentaUsuario(u.id)), u.id).toBe(u.puntos);
      }
      expect(saldoDe(store.libro(), cuentaPozo("m1"))).toBe(680);

      // y apostar después no deja a nadie en negativo
      store.apostar({ usuarioId: "u1", marketId: "m1", side: "si", stake: 400, precio: 0.6 });
      expect(store.cuadre()).toBe(0);
      expect(saldoDe(store.libro(), cuentaUsuario("u1"))).toBe(500);
      expect(saldoDe(store.libro(), cuentaUsuario("u1"))).toBeGreaterThanOrEqual(0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("la apertura no se repite al reabrir el store", () => {
    const dir = mkdtempSync(join(tmpdir(), "marea-apertura-2-"));
    try {
      writeFileSync(
        join(dir, "marea.json"),
        JSON.stringify({
          version: 1,
          usuarios: [{ id: "u1", usuario: "a", hash: "x", salt: "y", creado: "2026-01-01", puntos: 900 }],
          apuestas: [], pozos: [], liquidaciones: [], comisiones: [],
        }),
      );
      const primero = new Store(dir);
      expect(primero.libro()).toHaveLength(1);
      const segundo = new Store(dir);
      expect(segundo.libro()).toHaveLength(1);
      expect(segundo.cuadre()).toBe(0);
      expect(saldoDe(segundo.libro(), cuentaUsuario("u1"))).toBe(900);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
