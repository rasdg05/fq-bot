import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { renderApp, READY_NO_FUNDS } from "./helpers";
import { S } from "@/lib/strings";

/**
 * Métricas móviles. jsdom no calcula layout, así que verificamos el contrato
 * de clases que garantiza el tamaño: `min-h-touch` = 44 px, `min-h-[52px]` para
 * los CTA de pantalla, `h-touch` para los objetivos cuadrados (R-010).
 */
const TOUCH = /min-h-touch|min-h-\[(4[4-9]|[5-9]\d|\d{3,})px\]|h-touch|h-\[(4[4-9]|[5-9]\d)px\]/;

function assertTouchTargets(root: HTMLElement, label: string) {
  const interactive = [...root.querySelectorAll("button, [role='tab'], a[href]")];
  expect(interactive.length, `${label} no tiene elementos accionables`).toBeGreaterThan(0);
  for (const element of interactive) {
    const className = element.className.toString();
    // los iconos dentro de un botón no cuentan: sólo el elemento accionable
    expect(
      TOUCH.test(className),
      `${label}: target sin altura táctil garantizada → "${element.textContent?.trim().slice(0, 40)}" (${className.slice(0, 90)})`,
    ).toBe(true);
  }
}

describe("Métricas móviles", () => {
  it("los targets del chrome (header, tabs) cumplen 44 px", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");
    assertTouchTargets(screen.getByTestId("bottom-tabs"), "tabs");
    assertTouchTargets(
      document.querySelector("header") as HTMLElement,
      "header",
    );
  });

  it("las pestañas de categoría cumplen 44 px y se separan de sobra", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");
    const row = screen.getByRole("tablist", { name: S.search.byCategory });
    assertTouchTargets(row, "chips");
    // dejaron de ser burbujas: sin borde, la separación tiene que hacer el
    // trabajo que hacía el marco, así que sube de 8 a 20 px (R-010)
    expect(row.className).toMatch(/gap-5/);
    expect(row.className).toMatch(/overflow-x-auto/);
  });

  it("la zona de decisión del detalle vive abajo y cumple 44 px", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByTestId("card-open"),
    );

    const detail = await screen.findByTestId("market-detail");
    const zone = within(detail).getByTestId("decision-zone");
    assertTouchTargets(zone, "zona de decisión");

    // el CTA primario es el último bloque del detalle: zona de pulgar
    const cta = within(zone).getByTestId("detail-deposit-cta");
    const title = within(detail).getByRole("heading", { level: 1 });
    expect(
      title.compareDocumentPosition(cta) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(cta.className).toMatch(/min-h-\[52px\]/);
  });

  it("la hoja de depósito cumple 44 px y siempre se puede cerrar", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");
    await user.click(screen.getByTestId("header-deposit"));

    const sheet = await screen.findByTestId("deposit-sheet");
    // las opciones son tarjetas altas; el cierre es un target explícito
    expect(within(sheet).getByRole("button", { name: S.deposit.close }).className).toMatch(
      /min-h-\[52px\]/,
    );
    expect(
      document.querySelector("[aria-label='Cerrar']")?.className,
    ).toMatch(/h-touch/);
  });

  it("el onboarding usa CTA de ancho completo en la zona de pulgar", async () => {
    renderApp();
    const start = await screen.findByTestId("onboarding-start", {}, { timeout: 3500 });
    expect(start.className).toMatch(/min-h-\[52px\]/);
    expect(start.className).toMatch(/w-full/);
  });
});
