import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { renderApp, READY_NO_FUNDS } from "./helpers";
import { S } from "@/lib/strings";
import {
  CATEGORIAS_VISIBLES,
  COLOR_CATEGORIA,
  FORMA_CATEGORIA,
  ICONO_CATEGORIA,
} from "@/lib/categoria";

/**
 * La marca de categoría llevaba `data-testid="categoria-marca"` y
 * `data-categoria` en el markup **sin una sola prueba que los mirara**: eran
 * atributos de test sin test. Este archivo cierra ese hueco, porque el color
 * por categoría sin algo que lo fije vuelve a ser "todo teal plano" en cuanto
 * alguien reordene un mapa.
 */
describe("Color por categoría", () => {
  it("los cuatro mapas por categoría hablan de las mismas ocho", () => {
    const color = Object.keys(COLOR_CATEGORIA).sort();
    expect(Object.keys(FORMA_CATEGORIA).sort()).toEqual(color);
    expect(Object.keys(ICONO_CATEGORIA).sort()).toEqual(color);
    expect(Object.keys(S.categories).sort()).toEqual(color);
    expect(color).toHaveLength(8);
  });

  it("cada color sale de un token y ninguno se repite", () => {
    const valores = Object.values(COLOR_CATEGORIA);
    // V1: el color vive en tokens.css, aquí sólo se nombra
    for (const valor of valores) {
      expect(valor).toMatch(/^var\(--cat-[a-z-]+\)$/);
    }
    expect(new Set(valores).size).toBe(valores.length);
  });

  it("las dos futuras tienen color y glifo, pero no pestaña", () => {
    for (const id of ["materias-primas", "clima"] as const) {
      expect(COLOR_CATEGORIA[id]).toBeTruthy();
      expect(ICONO_CATEGORIA[id]).toBeTruthy();
      expect(S.categories[id]).toBeTruthy();
      expect(CATEGORIAS_VISIBLES).not.toContain(id);
    }
  });

  it("en el feed, dos categorías distintas pintan azulejos distintos", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");

    const marcas = await screen.findAllByTestId("categoria-marca");
    const vistas = new Set(marcas.map((m) => m.getAttribute("data-categoria")));
    // el feed mock trae varias categorías: si todas cayeran en la misma, esta
    // prueba no estaría comprobando nada
    expect(vistas.size).toBeGreaterThan(1);
    for (const categoria of vistas) {
      expect(COLOR_CATEGORIA).toHaveProperty(categoria as string);
    }
  });

  it("el color nunca viaja solo: la palabra sigue al lado del azulejo", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");

    const cards = await screen.findAllByTestId("market-card");
    for (const card of cards.slice(0, 6)) {
      const marca = card.querySelector('[data-testid="categoria-marca"]')!;
      const categoria = marca.getAttribute("data-categoria") as keyof typeof S.categories;
      // el azulejo es decorativo para el lector de pantalla; lo que se anuncia
      // es la palabra, y por eso tiene que estar (R-005)
      expect(marca).toHaveAttribute("aria-hidden");
      expect(card).toHaveTextContent(S.categories[categoria]);
    }
  });

  it("la pestaña activa toma el color de su categoría, y sigue cambiando de peso", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");

    const tab = screen.getByRole("tab", { name: S.categories.deportes });
    await user.click(tab);

    expect(tab).toHaveAttribute("aria-selected", "true");
    expect(tab.getAttribute("style") ?? "").toContain("--cat-deportes");
    // el color es un acento: el estado se sigue anunciando por peso y por
    // `aria-selected`, así que quien no distinga los tonos no pierde nada
    expect(tab.className).toContain("font-bold");

    const otra = screen.getByRole("tab", { name: S.categories.cripto });
    expect(otra).toHaveAttribute("aria-selected", "false");
    expect(otra.getAttribute("style") ?? "").not.toContain("--cat-");
  });

  it("el anillo de la pill líder se tiñe, pero el relleno no", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");

    const card = (await screen.findAllByTestId("market-card"))[0];
    const categoria = card
      .querySelector('[data-testid="categoria-marca"]')!
      .getAttribute("data-categoria")!;
    const lider = card.querySelector('[data-role="pill"][data-lado="lider"]')!;

    expect(lider.getAttribute("style") ?? "").toContain(`--cat-${categoria}`);
    // sólo el borde: el relleno sigue siendo el mismo para todas, para que el
    // número siga siendo el nodo dominante y la card no sea un semáforo (R-004)
    expect(lider.className).toContain("bg-teal-soft");
  });
});
