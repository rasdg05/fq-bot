import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";
import { renderApp, READY_NO_FUNDS } from "./helpers";
import { S } from "@/lib/strings";

/**
 * Los mercados calientes ya estaban arriba del feed, pero apilados: cuatro de
 * ellos empujaban el resto del catálogo fuera de la primera pantalla. En
 * horizontal caben los mismos sin gastar alto, y se ve que hay varios.
 */
describe("Carrusel de destacados", () => {
  it("se anuncia como grupo y lleva las tarjetas calientes", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");

    const carrusel = await screen.findByTestId("carrusel-destacados");
    expect(carrusel).toHaveAttribute("aria-label", S.feed.hotNow);
    const items = within(carrusel).getAllByTestId("carrusel-item");
    expect(items.length).toBeGreaterThan(0);
    for (const item of items) {
      expect(within(item).getByTestId("market-card")).toBeInTheDocument();
    }
  });

  it("desborda en horizontal y lo contiene él, no la página (V11)", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");

    const carrusel = await screen.findByTestId("carrusel-destacados");
    expect(carrusel.className).toContain("overflow-x-auto");
    // con anclaje: el dedo suelta y la tarjeta queda centrada, sin quedarse a
    // medio camino entre dos
    expect(carrusel.className).toContain("snap-x");
    expect(carrusel.className).toContain("snap-mandatory");
  });

  it("no se mueve solo: ni animación ni avance automático", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");

    const carrusel = await screen.findByTestId("carrusel-destacados");
    // un carrusel que avanza cada tres segundos le quita el control a quien
    // está leyendo, y es lo primero que estorba con `prefers-reduced-motion`
    expect(carrusel.className).not.toMatch(/\banimate-/);
    for (const item of within(carrusel).getAllByTestId("carrusel-item")) {
      expect(item.className).not.toMatch(/\banimate-/);
    }
  });

  it("los mercados que no están calientes siguen en la lista de abajo", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");

    const carrusel = await screen.findByTestId("carrusel-destacados");
    const enCarrusel = new Set(
      within(carrusel)
        .getAllByTestId("market-card")
        .map((c) => c.getAttribute("data-market-id")),
    );
    const todas = screen
      .getAllByTestId("market-card")
      .map((c) => c.getAttribute("data-market-id"));
    const enLista = todas.filter((id) => !enCarrusel.has(id));

    // ninguna se pierde por el camino y ninguna sale dos veces
    expect(enLista.length).toBeGreaterThan(0);
    expect(new Set(todas).size).toBe(todas.length);
  });
});
