import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { renderApp, READY_NO_FUNDS, READY_WITH_FUNDS } from "./helpers";
import { S } from "@/lib/strings";
import { SPLASH_MS } from "@/screens/OnboardingFlow";
import { MOCK_MARKETS } from "@/adapters/mock/markets";
import { appError } from "@/domain/errors";

const waitForP1 = () =>
  screen.findByTestId("onboarding-start", {}, { timeout: SPLASH_MS + 2000 });

/**
 * RED-TEAM UX. Diez escenarios adversarios. Cualquiera en rojo bloquea el
 * soft launch.
 */
describe("Red-team UX", () => {
  it("RT/1 — el que sólo quiere mirar llega al feed sin poner un peso", async () => {
    const user = userEvent.setup();
    const { container } = renderApp();
    await user.click(await waitForP1());
    await user.click(await screen.findByTestId("onboarding-create-wallet"));
    await user.click(await screen.findByTestId("onboarding-explore"));

    await screen.findByTestId("home-screen");
    // en ningún momento se montó la hoja de depósito
    expect(screen.queryByTestId("deposit-sheet")).toBeNull();
    expect(container.textContent).not.toMatch(/deposita para (ver|continuar|explorar)/i);
    expect((await screen.findAllByTestId("market-card")).length).toBeGreaterThan(0);
  });

  it("RT/2 — la categoría se entiende sin tutorial: chips con nombre y etiqueta en cada card", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");

    for (const label of Object.values(S.categories)) {
      expect(screen.getByRole("tab", { name: label })).toBeInTheDocument();
    }
    const cards = await screen.findAllByTestId("market-card");
    for (const card of cards.slice(0, 5)) {
      const id = card.getAttribute("data-market-id")!;
      const market = MOCK_MARKETS.find((m) => m.id === id)!;
      expect(card).toHaveTextContent(S.categories[market.category]);
      // el título es una pregunta cerrada: se entiende solo
      expect(market.title).toMatch(/^¿.+\?$/);
    }
  });

  it("RT/3 — un Edge de 4 pp o más siempre se ve", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");
    const cards = await screen.findAllByTestId("market-card");
    const withEdgeInData = MOCK_MARKETS.filter((m) => m.edge !== null).map((m) => m.id);
    const shown = cards
      .filter((card) => within(card).queryByTestId("edge-badge"))
      .map((card) => card.getAttribute("data-market-id"));
    expect(shown.sort()).toEqual(withEdgeInData.sort());
  });

  it("RT/4 — intentar operar sin saldo abre el depósito en contexto, nunca un muro previo", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );
    const detail = await screen.findByTestId("market-detail");
    // el detalle se ve completo ANTES de pedir dinero
    expect(within(detail).getByTestId("resolution-summary")).toBeInTheDocument();
    expect(screen.queryByTestId("deposit-sheet")).toBeNull();

    await user.click(within(detail).getByTestId("detail-deposit-cta"));
    expect(await screen.findByTestId("deposit-sheet")).toBeInTheDocument();
  });

  it("RT/5 — doble tap no duplica ni la wallet ni la operación", async () => {
    const user = userEvent.setup();

    let creates = 0;
    const app = renderApp({
      walletAdapter: {
        async createEmbedded() {
          creates += 1;
          await new Promise((r) => setTimeout(r, 40));
          return {
            address: "0xabc0000000000000000000000000000000000001",
            balance: 0,
            chain: "Polygon",
            origin: "embedded" as const,
          };
        },
        async connectExternal() {
          throw appError("E_WALLET_CONNECT_FAILED");
        },
        async getBalance() {
          return 0;
        },
        async startDeposit() {
          return { reference: "r", instructions: "i" };
        },
      },
    });

    await user.click(await waitForP1());
    const create = await screen.findByTestId("onboarding-create-wallet");
    await user.dblClick(create);
    await screen.findByTestId("onboarding-explore");
    expect(creates).toBe(1);

    await user.click(screen.getByTestId("onboarding-explore"));
    await screen.findByTestId("home-screen");
    expect(app.eventNames().filter((e) => e === "wallet_created")).toHaveLength(1);
  });

  it("RT/5 — doble tap en Operar deja una sola posición", async () => {
    const user = userEvent.setup();
    let trades = 0;
    const app = renderApp({
      overrides: READY_WITH_FUNDS,
      marketDataAdapter: {
        async listMarkets() {
          return MOCK_MARKETS;
        },
        async getMarket() {
          return MOCK_MARKETS[0];
        },
        async listPositions() {
          return [];
        },
        async prepareTrade() {
          trades += 1;
          await new Promise((r) => setTimeout(r, 40));
          return { positionId: `p${trades}`, venue: "agregado" };
        },
      },
    });
    await screen.findByTestId("home-screen");
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );
    await user.dblClick(await screen.findByTestId("detail-trade-cta"));
    await screen.findByTestId("post-trade");
    expect(trades).toBe(1);
    expect(app.eventNames().filter((e) => e === "trade_confirmed")).toHaveLength(1);
  });

  it("RT/6 — reabrir con el onboarding hecho entra directo al feed", async () => {
    const user = userEvent.setup();
    const first = renderApp();
    await user.click(await waitForP1());
    await user.click(await screen.findByTestId("onboarding-create-wallet"));
    await user.click(await screen.findByTestId("onboarding-explore"));
    await screen.findByTestId("home-screen");
    first.unmount();

    // segunda sesión: mismo almacenamiento, cero onboarding
    renderApp();
    expect(screen.queryByTestId("onboarding")).toBeNull();
    expect(await screen.findByTestId("home-screen")).toBeInTheDocument();
  });

  it("RT/7 — si los mercados fallan hay mensaje en español y reintento que funciona", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    renderApp({
      overrides: READY_NO_FUNDS,
      marketDataAdapter: {
        async listMarkets() {
          attempts += 1;
          if (attempts === 1) throw appError("E_MARKETS_FETCH_FAILED");
          return MOCK_MARKETS;
        },
        async getMarket() {
          return MOCK_MARKETS[0];
        },
        async listPositions() {
          return [];
        },
        async prepareTrade() {
          return { positionId: "p1", venue: "agregado" };
        },
      },
    });

    const error = await screen.findByTestId("error-state");
    expect(error.textContent).toMatch(/No pudimos cargar los mercados/);
    expect(error.textContent).not.toMatch(/undefined|null|Error:|E_[A-Z_]+/);
    await user.click(within(error).getByRole("button", { name: S.common.retry }));
    expect((await screen.findAllByTestId("market-card")).length).toBeGreaterThan(0);
  });

  it("RT/8 — si falla crear la wallet, el onboarding NO queda marcado como completo", async () => {
    const user = userEvent.setup();
    const app = renderApp({ wallet: { failCreate: true } });
    await user.click(await waitForP1());
    await user.click(await screen.findByTestId("onboarding-create-wallet"));
    await screen.findByTestId("onboarding-wallet-error");

    expect(screen.getByTestId("onboarding")).toHaveAttribute("data-step", "p2");
    expect(app.eventNames()).not.toContain("onboarding_completed");
    expect(globalThis.localStorage.getItem("marea.onboarding_completed")).toBeNull();
  });

  it("RT/9 — proveedor de depósito caído: lo decimos y dejamos la alternativa abierta", async () => {
    const user = userEvent.setup();
    renderApp({
      overrides: READY_NO_FUNDS,
      wallet: { providerDown: true },
    });
    await screen.findByTestId("home-screen");
    await user.click(screen.getByTestId("header-deposit"));
    await user.click(await screen.findByTestId("deposit-onramp"));

    const error = await screen.findByTestId("deposit-error");
    expect(error).toHaveTextContent(/fuera de servicio/i);
    expect(error).toHaveTextContent(/transferencia/i);
    // sin botón de reintento inútil, y con el otro camino disponible
    expect(within(error).queryByRole("button", { name: S.common.retry })).toBeNull();
    expect(screen.getByTestId("deposit-transfer")).toBeEnabled();

    await user.click(screen.getByTestId("deposit-transfer"));
    expect(await screen.findByTestId("deposit-started")).toBeInTheDocument();
  });

  it("RT/10 — ninguna superficie del producto usa lenguaje prohibido", async () => {
    const user = userEvent.setup();
    const { container } = renderApp({ overrides: READY_WITH_FUNDS });
    const forbidden =
      /copiloto|co-piloto|fibonacci|deflated sharpe|se[nñ]al ganadora|garantizado|100\s?%\s?(de\s)?(acierto|efectivo)|millonario|lorem|\bTODO\b/i;

    const surfaces: string[] = [];
    await screen.findByTestId("home-screen");
    surfaces.push(container.textContent ?? "");

    for (const tab of [S.tabs.search, S.tabs.portfolio, S.tabs.wallet, S.tabs.profile]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      await waitFor(() => expect(container.textContent).toBeTruthy());
      surfaces.push(container.textContent ?? "");
    }

    await user.click(screen.getByRole("tab", { name: S.tabs.markets }));
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );
    surfaces.push((await screen.findByTestId("market-detail")).textContent ?? "");

    for (const text of surfaces) {
      expect(text).not.toMatch(forbidden);
      // "FQ" como palabra suelta tampoco aparece
      expect(text).not.toMatch(/\bFQ\b/);
    }
  });

  it("RT/10 — el copy de ejecución es honesto sobre quién es la contraparte", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_WITH_FUNDS });
    await screen.findByTestId("home-screen");
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );
    const notice = await screen.findByTestId("aggregation-notice");
    expect(notice).toHaveTextContent(/Marea no es tu contraparte/i);
    const detail = screen.getByTestId("market-detail");
    expect(detail.textContent).not.toMatch(/nuestro libro|matching nativo|nuestra liquidez/i);
  });
});
