import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { createFakeApi, renderApp, READY_NO_FUNDS } from "./helpers";
import { S } from "@/lib/strings";
import { saldoVisible } from "@/domain/saldo";
import type { Position } from "@/domain/types";

/**
 * El saldo saltaba entre 700 y 900 al ir y volver de Portafolio, sin que nadie
 * apostara. La causa: `state.points.balance` tenía dos escritores. El reducer
 * lo pisaba con `cuenta.puntos` (verdad del servidor) y `creditSettlements` le
 * sumaba encima los pagos de lo liquidado — pagos que el servidor **ya** había
 * acreditado. Entrar al portafolio los sumaba otra vez (900) y volver al feed
 * los borraba (700).
 *
 * Estas pruebas corren por el camino con cuenta, que hasta ahora **ninguna
 * prueba de interfaz tocaba**.
 */

/** Una posición ya liquidada que pagó 200. El servidor ya sumó esos 200. */
const LIQUIDADA: Position = {
  id: "pos-vieja",
  market_id: "m-1",
  side: "si",
  size: 100,
  entry_price: 0.5,
  pnl: 100,
  status: "won",
  payout: 200,
  marketTitle: "¿Un mercado que ya resolvió?",
};

/** Saldo tal como lo cuenta el servidor: 1000 de bienvenida − 300 + 200 pagados. */
const PUNTOS_REALES = 900 - 200;

/**
 * El aviso de liquidación se muestra una vez por posición pagada y, siendo un
 * diálogo, deja el resto de la app fuera del árbol accesible. Aquí estorba: lo
 * que se mide es la navegación, no el aviso. Se marca como visto de antemano,
 * igual que si ya se hubiera cerrado en una sesión anterior.
 */
function darPorVistas(ids: string[]) {
  globalThis.localStorage?.setItem("marea.liquidaciones.vistas", JSON.stringify(ids));
}

/** Las pestañas de abajo comparten `role="tab"` con los chips de categoría. */
function pestana(nombre: string): HTMLElement {
  // por texto y no por nombre accesible: la de Mercados le cuelga el contador
  // de velas vivas cuando las hay, y entonces deja de llamarse sólo "Mercados"
  const tabs = within(screen.getByTestId("bottom-tabs")).getAllByRole("tab");
  const encontrada = tabs.find((t) => (t.textContent ?? "").startsWith(nombre));
  if (!encontrada) throw new Error(`sin pestaña "${nombre}"`);
  return encontrada;
}

function saldoDelHeader(): number {
  const texto = screen.getByTestId("header-balance").textContent ?? "";
  return Number(texto.replace(/[^\d]/g, ""));
}

function saldoDelPortafolio(): number {
  const texto = screen.getByTestId("portfolio-saldo").textContent ?? "";
  return Number(texto.replace(/[^\d]/g, ""));
}

describe("El saldo tiene una sola fuente", () => {
  it("ir y volver diez veces no mueve el número, y header y Portafolio coinciden", async () => {
    const user = userEvent.setup();
    darPorVistas([LIQUIDADA.id]);
    const servidor = createFakeApi({
      puntos: PUNTOS_REALES,
      posiciones: [LIQUIDADA],
    });
    renderApp({
      engine: "parimutuel_points",
      api: servidor.api,
      overrides: READY_NO_FUNDS,
    });

    await screen.findByTestId("home-screen");
    await waitFor(() => expect(saldoDelHeader()).toBe(PUNTOS_REALES));

    for (let vuelta = 0; vuelta < 10; vuelta += 1) {
      await user.click(pestana(S.tabs.portfolio));
      await screen.findByTestId("portfolio-screen");
      await waitFor(() => expect(saldoDelPortafolio()).toBe(PUNTOS_REALES));
      // el header sigue montado: es el mismo número, leído del mismo sitio
      expect(saldoDelHeader()).toBe(PUNTOS_REALES);

      await user.click(pestana(S.tabs.markets));
      await screen.findByTestId("home-screen");
      expect(saldoDelHeader()).toBe(PUNTOS_REALES);
    }

    // el valor inflado que aparecía al acreditar el pago dos veces
    expect(saldoDelHeader()).not.toBe(PUNTOS_REALES + 200);
  });

  it("cargar el portafolio no vuelve a acreditar lo que el servidor ya pagó", async () => {
    const user = userEvent.setup();
    darPorVistas([LIQUIDADA.id]);
    const servidor = createFakeApi({
      puntos: PUNTOS_REALES,
      posiciones: [LIQUIDADA],
    });
    renderApp({
      engine: "parimutuel_points",
      api: servidor.api,
      overrides: READY_NO_FUNDS,
    });
    await screen.findByTestId("home-screen");

    // tres cargas del portafolio: la doble contabilidad se notaría a la primera
    for (let i = 0; i < 3; i += 1) {
      await user.click(pestana(S.tabs.portfolio));
      await screen.findByTestId("portfolio-screen");
      await user.click(pestana(S.tabs.markets));
      await screen.findByTestId("home-screen");
    }

    await waitFor(() => expect(saldoDelHeader()).toBe(PUNTOS_REALES));
    expect(servidor.estado.puntos).toBe(PUNTOS_REALES);
  });

  it("el saldo fresco no se vuelve a pedir en cada visita", async () => {
    const user = userEvent.setup();
    const servidor = createFakeApi({ puntos: PUNTOS_REALES });
    renderApp({
      engine: "parimutuel_points",
      api: servidor.api,
      overrides: READY_NO_FUNDS,
    });
    await screen.findByTestId("home-screen");
    await waitFor(() => expect(servidor.llamadas.yo).toBeGreaterThan(0));

    const trasElPrimerMontaje = servidor.llamadas.yo;
    for (let i = 0; i < 4; i += 1) {
      await user.click(pestana(S.tabs.portfolio));
      await screen.findByTestId("portfolio-screen");
      await user.click(pestana(S.tabs.markets));
      await screen.findByTestId("home-screen");
    }

    // las posiciones sí se piden; la cuenta, no: dentro de la ventana de
    // frescura se reusa el dato en vez de disparar una petición por toque
    expect(servidor.llamadas.yo - trasElPrimerMontaje).toBeLessThanOrEqual(4);
    expect(saldoDelHeader()).toBe(PUNTOS_REALES);
  });
});

describe("saldoVisible", () => {
  const ledger = { balance: 1000, entries: [] };

  it("con cuenta manda el servidor, no el ledger local", () => {
    expect(
      saldoVisible(
        { cuenta: { puntos: 700 }, points: ledger, wallet: null, optimistas: [] },
        true,
      ),
    ).toBe(700);
  });

  it("sin cuenta manda el ledger local", () => {
    expect(
      saldoVisible({ cuenta: null, points: ledger, wallet: null, optimistas: [] }, true),
    ).toBe(1000);
  });

  it("los movimientos en el aire se suman, en cualquier orden", () => {
    const base = { cuenta: { puntos: 700 }, points: ledger, wallet: null };
    const dos = [
      { id: "a", delta: -50 },
      { id: "b", delta: -30 },
    ];
    expect(saldoVisible({ ...base, optimistas: dos }, true)).toBe(620);
    expect(saldoVisible({ ...base, optimistas: [...dos].reverse() }, true)).toBe(620);
    // quitar el primero deja exactamente el segundo, sin restos del otro
    expect(saldoVisible({ ...base, optimistas: [dos[1]] }, true)).toBe(670);
  });

  it("nunca se enseña un saldo negativo: sin crédito, tampoco en pantalla", () => {
    expect(
      saldoVisible(
        {
          cuenta: { puntos: 10 },
          points: ledger,
          wallet: null,
          optimistas: [{ id: "a", delta: -50 }],
        },
        true,
      ),
    ).toBe(0);
  });

  it("con dinero el saldo vive en la wallet y los optimistas no aplican", () => {
    expect(
      saldoVisible(
        {
          cuenta: { puntos: 700 },
          points: ledger,
          wallet: { balance: 120 },
          optimistas: [{ id: "a", delta: -50 }],
        },
        false,
      ),
    ).toBe(120);
  });
});
