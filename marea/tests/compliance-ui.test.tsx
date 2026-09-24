import { describe, expect, it, afterEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { renderApp, READY_NO_FUNDS } from "./helpers";
import { FLAGS } from "@/lib/flags";
import { COUNTRY_POLICY } from "@/domain/eligibility";
import { S } from "@/lib/strings";

afterEach(() => {
  FLAGS.eligibility_enforced = false;
  Object.assign(COUNTRY_POLICY, {
    MX: { status: "pendiente", depositCapUsd: 0, note: "Falta opinión legal local." },
  });
});

describe("Elegibilidad en la interfaz", () => {
  it("con el bloqueo activo, un país sin permiso no puede depositar pero sí explorar", async () => {
    const user = userEvent.setup();
    FLAGS.eligibility_enforced = true;
    renderApp({ overrides: { ...READY_NO_FUNDS, country: "US" } });

    // explorar sigue intacto: el feed y el detalle se ven completos (R-002)
    await screen.findByTestId("home-screen");
    const cards = await screen.findAllByTestId("market-card");
    expect(cards.length).toBeGreaterThan(0);
    await user.click(within(cards[0]).getByTestId("card-open"));
    expect(await screen.findByTestId("resolution-summary")).toBeInTheDocument();

    // el depósito sí se detiene, con motivo en español y salida a explorar
    await user.click(screen.getByTestId("detail-deposit-cta"));
    const blocked = await screen.findByTestId("deposit-blocked");
    expect(blocked).toHaveTextContent(S.deposit.blockedTitle);
    expect(blocked.textContent).toMatch(/explorando/i);
    expect(screen.queryByTestId("deposit-onramp")).toBeNull();
    expect(screen.queryByTestId("deposit-transfer")).toBeNull();

    await user.click(within(blocked).getByTestId("deposit-blocked-explore"));
    await waitFor(() => expect(screen.queryByTestId("deposit-sheet")).toBeNull());
    expect(screen.getByTestId("market-detail")).toBeInTheDocument();
  });

  it("con el bloqueo activo y país habilitado, el depósito funciona normal", async () => {
    const user = userEvent.setup();
    FLAGS.eligibility_enforced = true;
    Object.assign(COUNTRY_POLICY, {
      MX: { status: "permitido", depositCapUsd: 200, note: "" },
    });
    renderApp({ overrides: { ...READY_NO_FUNDS, country: "MX" } });
    await screen.findByTestId("home-screen");
    await user.click(screen.getByTestId("header-deposit"));

    expect(await screen.findByTestId("deposit-onramp")).toBeEnabled();
    expect(screen.queryByTestId("deposit-blocked")).toBeNull();
  });

  it("con el bloqueo apagado (build simulada) el depósito no se estorba", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: { ...READY_NO_FUNDS, country: "US" } });
    await screen.findByTestId("home-screen");
    await user.click(screen.getByTestId("header-deposit"));
    expect(await screen.findByTestId("deposit-onramp")).toBeEnabled();
    expect(screen.queryByTestId("deposit-blocked")).toBeNull();
  });
});
