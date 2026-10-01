import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderApp, READY_NO_FUNDS } from "./helpers";
import { S } from "@/lib/strings";

/**
 * «Eventos top»: las secciones con más en juego como accesos directos, el
 * patrón de los hubs de Kalshi. Tocar uno lleva a su sección; no es otro filtro.
 */
describe("Eventos top", () => {
  afterEach(() => vi.restoreAllMocks());

  it("aparece en «Todos» con sus hubs, cada uno con mercados y lo que hay en juego", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");
    const fila = screen.getByTestId("eventos-top");
    expect(screen.getByRole("heading", { name: S.feed.eventosTop })).toBeInTheDocument();
    const hubs = within(fila).getAllByTestId("hub");
    expect(hubs.length).toBeGreaterThanOrEqual(2);
    expect(hubs.length).toBeLessThanOrEqual(6);
    for (const hub of hubs) {
      expect(hub.tagName).toBe("BUTTON");
      expect(hub.className).toMatch(/min-h-touch/);
      expect(hub.getAttribute("aria-label")).toMatch(/^Ir a .+mercado/);
      // cada hub lleva a una sección que existe
      const clave = hub.getAttribute("data-hub")!;
      expect(document.querySelector(`[data-seccion="${clave}"]`)).not.toBeNull();
    }
  });

  it("tocar un hub lleva a su sección y le pasa el foco", async () => {
    const user = userEvent.setup();
    const desplazar = vi.fn();
    Element.prototype.scrollIntoView = desplazar;
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");
    const fila = screen.getByTestId("eventos-top");
    const hub = within(fila).getAllByTestId("hub")[0];
    await user.click(hub);
    expect(desplazar).toHaveBeenCalled();
    const seccion = document.querySelector(`[data-seccion="${hub.getAttribute("data-hub")}"]`)!;
    expect(seccion.querySelector("h3")).toHaveFocus();
  });
});
