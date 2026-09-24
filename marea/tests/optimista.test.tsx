import { beforeAll, describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { createFakeApi, renderApp, READY_NO_FUNDS } from "./helpers";
import { S } from "@/lib/strings";
import { initialState } from "@/state/store";
import { createOwnMarketsAdapter } from "@/adapters/ownMarkets/ownMarketsAdapter";
import type { Market } from "@/domain/types";

/**
 * La interfaz responde al instante y el servidor manda después.
 *
 * Lo que se guarda para poder deshacer no es una foto del saldo anterior sino
 * el movimiento con su id. Con la foto, dos apuestas seguidas se pisaban: la
 * segunda retrataba el valor ya descontado por la primera, y deshacer la
 * primera restauraba un número que ya no era verdad. Restar el monto y luego
 * quitar el movimiento da lo mismo en cualquier orden de respuesta, y eso es
 * justo lo que se prueba abajo.
 */

const SALDO = 700;

/**
 * El catálogo propio, que es el que trae pozo: sin pozo no hay cotización, y
 * sin cotización no hay apuesta que probar.
 */
let CATALOGO: Market[] = [];
beforeAll(async () => {
  CATALOGO = await createOwnMarketsAdapter().listMarkets();
});

function saldoDelHeader(): number {
  return Number(
    (screen.getByTestId("header-balance").textContent ?? "").replace(/[^\d]/g, ""),
  );
}

function montar(opciones: { puntos?: number; recargaDisponible?: number } = {}) {
  const servidor = createFakeApi({
    puntos: opciones.puntos ?? SALDO,
    recargaDisponible: opciones.recargaDisponible ?? 0,
    mercados: CATALOGO,
  });
  const utils = renderApp({
    engine: "parimutuel_points",
    api: servidor.api,
    overrides: { ...READY_NO_FUNDS, onboardingCompleted: true, onboardingStep: "done" },
  });
  return { servidor, ...utils };
}

/** Abre el primer mercado y confirma la apuesta con el monto que trae por defecto. */
async function apostar(user: ReturnType<typeof userEvent.setup>) {
  await user.click(
    within((await screen.findAllByTestId("market-card"))[0]).getByTestId("card-open"),
  );
  const cta = await screen.findByTestId("detail-trade-cta");
  await user.click(cta);
}

describe("Apuesta optimista", () => {
  it("el saldo baja antes de que el servidor conteste, y se queda ahí al confirmar", async () => {
    const user = userEvent.setup();
    const { servidor } = montar();
    await screen.findByTestId("home-screen");
    await waitFor(() => expect(saldoDelHeader()).toBe(SALDO));

    // el servidor se queda colgado a propósito: lo que se mide es que el saldo
    // se mueva **sin** su respuesta
    let soltar: (() => void) | null = null;
    const original = servidor.api.apostar.bind(servidor.api);
    servidor.api.apostar = ((datos: Parameters<typeof original>[0]) =>
      new Promise((resolve) => {
        soltar = () => resolve(original(datos));
      })) as typeof original;

    await apostar(user);

    // todavía nadie contestó y el número ya se movió
    await waitFor(() => expect(saldoDelHeader()).toBeLessThan(SALDO));
    const optimista = saldoDelHeader();
    expect(servidor.estado.puntos).toBe(SALDO);

    soltar!();
    await screen.findByTestId("post-trade");
    // y al confirmar se queda exactamente donde estaba: ni un salto ni un
    // doble descuento al cerrar el movimiento
    await waitFor(() => expect(saldoDelHeader()).toBe(optimista));
    expect(servidor.estado.puntos).toBe(optimista);
  });

  it("si el servidor rechaza, el saldo vuelve limpio y no queda posición fantasma", async () => {
    const user = userEvent.setup();
    const { servidor } = montar();
    await screen.findByTestId("home-screen");
    await waitFor(() => expect(saldoDelHeader()).toBe(SALDO));

    servidor.romperApuesta(new Error("el servidor dijo que no"));
    await apostar(user);

    await screen.findByTestId("trade-error");
    // vuelve al valor exacto de antes, no a uno aproximado
    await waitFor(() => expect(saldoDelHeader()).toBe(SALDO));
    expect(servidor.estado.puntos).toBe(SALDO);
    expect(screen.queryByTestId("post-trade")).toBeNull();

    // y el portafolio no se queda con la posición que se pintó pendiente
    await user.click(screen.getByRole("button", { name: S.common.back }));
    const tabs = within(screen.getByTestId("bottom-tabs")).getAllByRole("tab");
    await user.click(tabs.find((t) => (t.textContent ?? "").startsWith(S.tabs.portfolio))!);
    await screen.findByTestId("portfolio-screen");
    expect(screen.queryByTestId("portfolio-saldo")).toHaveTextContent(String(SALDO));
    for (const fila of screen.queryAllByTestId("position-row")) {
      expect(fila).not.toHaveAttribute("data-pendiente");
    }
  });

  it("navegar después de apostar mantiene el mismo número en las dos vistas", async () => {
    const user = userEvent.setup();
    const { servidor } = montar();
    await screen.findByTestId("home-screen");
    await waitFor(() => expect(saldoDelHeader()).toBe(SALDO));

    await apostar(user);
    await screen.findByTestId("post-trade");
    const despues = saldoDelHeader();
    expect(despues).toBeLessThan(SALDO);

    await user.click(screen.getByTestId("post-trade-portfolio"));
    await screen.findByTestId("portfolio-screen");
    expect(screen.getByTestId("portfolio-saldo")).toHaveTextContent(String(despues));
    expect(saldoDelHeader()).toBe(despues);

    const tabs = within(screen.getByTestId("bottom-tabs")).getAllByRole("tab");
    await user.click(tabs.find((t) => (t.textContent ?? "").startsWith(S.tabs.markets))!);
    await screen.findByTestId("home-screen");
    expect(saldoDelHeader()).toBe(despues);
    expect(servidor.estado.puntos).toBe(despues);
  });
});

describe("Recarga optimista", () => {
  it("los puntos aparecen al tocar y el servidor sólo los confirma", async () => {
    const user = userEvent.setup();
    const { servidor } = montar({ puntos: 0, recargaDisponible: 100 });
    await screen.findByTestId("home-screen");
    await waitFor(() => expect(saldoDelHeader()).toBe(0));

    let soltar: (() => void) | null = null;
    const original = servidor.api.recargar.bind(servidor.api);
    servidor.api.recargar = (() =>
      new Promise((resolve) => {
        soltar = () => resolve(original());
      })) as typeof original;

    const tabs = within(screen.getByTestId("bottom-tabs")).getAllByRole("tab");
    await user.click(tabs.find((t) => (t.textContent ?? "").startsWith(S.tabs.portfolio))!);
    await screen.findByTestId("portfolio-screen");
    await user.click(screen.getByTestId("portfolio-recargar"));
    await user.click(await screen.findByTestId("points-topup"));

    await waitFor(() => expect(saldoDelHeader()).toBe(100));
    expect(servidor.estado.puntos).toBe(0);

    soltar!();
    await waitFor(() => expect(servidor.estado.puntos).toBe(100));
    expect(saldoDelHeader()).toBe(100);
  });

  it("si la recarga falla, el saldo vuelve al valor anterior", async () => {
    const user = userEvent.setup();
    const { servidor } = montar({ puntos: 0, recargaDisponible: 100 });
    await screen.findByTestId("home-screen");
    await waitFor(() => expect(saldoDelHeader()).toBe(0));

    servidor.api.recargar = (() =>
      Promise.reject(new Error("hoy no"))) as typeof servidor.api.recargar;

    const tabs = within(screen.getByTestId("bottom-tabs")).getAllByRole("tab");
    await user.click(tabs.find((t) => (t.textContent ?? "").startsWith(S.tabs.portfolio))!);
    await screen.findByTestId("portfolio-screen");
    await user.click(screen.getByTestId("portfolio-recargar"));
    await user.click(await screen.findByTestId("points-topup"));

    await waitFor(() => expect(saldoDelHeader()).toBe(0));
  });
});

describe("El estado inicial", () => {
  it("arranca sin movimientos en el aire y sin marca de frescura", () => {
    const estado = initialState({});
    expect(estado.optimistas).toEqual([]);
    expect(estado.cuentaAt).toBeNull();
  });
});
