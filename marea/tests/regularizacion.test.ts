import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { Store } from "../server/store.mts";
import { verificarCadena } from "@/domain/bitacora";
import { saldoDe, cuentaPozo, CUENTAS_SISTEMA } from "@/domain/contabilidad";
import { createMatchOracle } from "@/adapters/oracles/matchOracle";
import { equipoPorDefinir, partidosSeeds } from "@/adapters/ownMarkets/templates";

/**
 * Los hallazgos del revisor en su primera vuelta en producción (2026-10-01),
 * cada uno cerrado con su prueba (DECISIONES §26).
 */

function conStore(fn: (store: Store) => void) {
  const dir = mkdtempSync(join(tmpdir(), "marea-regulariza-"));
  try {
    fn(new Store(dir));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

/** Un pozo como los que dejó el pago anterior a L3: liquidado y con la semilla adentro. */
function pozoHeredado(store: Store, marketId: string) {
  store.asegurarPozo({ marketId, outcomes: { si: 200, no: 200 }, feeBps: 300 });
  // la liquidación vieja no devolvía toda la semilla: el resto queda en el pozo
  store.liquidarMercado({ marketId, pagos: {}, fee: 0, aCapital: 1 });
}

describe("Regularización de pozos heredados — tres candados", () => {
  it("un residuo anterior al corte, con todo pagado, vuelve al capital y queda en la bitácora", () =>
    conStore((store) => {
      pozoHeredado(store, "viejo");
      expect(store.pozosConSaldoTrasLiquidar()).toEqual({ viejo: 399 });
      const capitalAntes = saldoDe(store.libro(), CUENTAS_SISTEMA.capital);

      const { regularizados } = store.regularizarPozosHeredados("2099-01-01T00:00:00Z", Date.now());
      expect(regularizados).toEqual([{ marketId: "viejo", saldo: 399 }]);
      expect(saldoDe(store.libro(), cuentaPozo("viejo"))).toBe(0);
      expect(saldoDe(store.libro(), CUENTAS_SISTEMA.capital)).toBe(capitalAntes + 399);
      expect(store.cuadre()).toBe(0);
      const entrada = store.bitacora().at(-1)!;
      expect(entrada).toMatchObject({ tipo: "regularizar", autor: "migracion", reversible: false, regla: "L3" });
      expect(verificarCadena(store.bitacora()).ok).toBe(true);
      // idempotente
      expect(store.regularizarPozosHeredados("2099-01-01T00:00:00Z", Date.now()).regularizados).toEqual([]);
    }));

  it("un residuo posterior al corte NO se regulariza: es un bug vigente y el revisor lo tiene que ver", () =>
    conStore((store) => {
      pozoHeredado(store, "nuevo");
      expect(store.regularizarPozosHeredados("2000-01-01T00:00:00Z", Date.now()).regularizados).toEqual([]);
      expect(store.pozosConSaldoTrasLiquidar()).toHaveProperty("nuevo");
    }));

  it("si queda una apuesta sin pagar, ese dinero puede ser de alguien: no se toca", () =>
    conStore((store) => {
      pozoHeredado(store, "con-deuda");
      // una apuesta que llegó después y nunca se pagó (lo que el candado protege)
      store.crearUsuario({ id: "u1", usuario: "ana", hash: "h", salt: "s", creado: "2026-08-01", puntos: 100 });
      store.apostar({ usuarioId: "u1", marketId: "con-deuda", side: "si", stake: 50, precio: 0.5 });
      expect(store.detallePozosConSaldo()["con-deuda"]).toMatchObject({ sinPagar: 1 });
      expect(store.regularizarPozosHeredados("2099-01-01T00:00:00Z", Date.now()).regularizados).toEqual([]);
    }));
});

describe("Liga MX: «FC Juarez» es «FC Juárez»", () => {
  it("el oráculo encuentra el partido aunque el mercado escriba el nombre sin acento", async () => {
    const oraculo = createMatchOracle({
      cargarPartidos: async () => [
        {
          date: "2026-09-19T03:00Z",
          name: "Tigres UANL at FC Juárez",
          competitions: [
            {
              status: { type: { name: "STATUS_FULL_TIME", completed: true } },
              competitors: [
                { homeAway: "home", score: "1", team: { displayName: "FC Juárez" } },
                { homeAway: "away", score: "0", team: { displayName: "Tigres UANL" } },
              ],
            },
          ],
        },
      ],
    });
    const r = await oraculo.read({
      marketId: "mx-fc-juarez-tigres-uanl-2026-09-19",
      spec: {} as never,
      rule: { kind: "partido", liga: "mex.1", fecha: "2026-09-19", inicio: "2026-09-19T03:00Z", equipo: "FC Juarez", resultado: "gana" },
      now: Date.parse("2026-10-01T19:00:00Z"),
    });
    expect(r).toMatchObject({ status: "resuelto", outcome: "si" });
  });
});

describe("Partidos con rival por definir no se publican", () => {
  it("«TBD vs TBD» no es un mercado", () => {
    expect(equipoPorDefinir("TBD")).toBe(true);
    expect(equipoPorDefinir("Winner Match 101")).toBe(true);
    expect(equipoPorDefinir("Monterrey")).toBe(false);
    const ahora = Date.parse("2026-10-01T12:00:00Z");
    const seeds = partidosSeeds(
      [
        { inicio: "2026-10-04T01:00:00Z", local: "TBD", visitante: "TBD", liga: "usa.1" },
        { inicio: "2026-10-04T01:00:00Z", local: "Monterrey", visitante: "Cruz Azul", liga: "mex.1" },
      ],
      ahora,
    );
    expect(seeds).toHaveLength(1);
  });
});
