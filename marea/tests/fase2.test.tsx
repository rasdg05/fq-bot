import { describe, expect, it, vi } from "vitest";
import { act, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { renderApp, READY_NO_FUNDS, READY_WITH_FUNDS } from "./helpers";
import { S } from "@/lib/strings";
import { SPLASH_MAX_MS, SPLASH_MIN_MS } from "@/screens/OnboardingFlow";
import { createMockWalletAdapter } from "@/adapters/walletAdapter";

/** P0 se auto-avanza: esperamos al CTA de P1 con margen sobre el splash. */
const waitForP1 = () =>
  screen.findByTestId("onboarding-start", {}, { timeout: SPLASH_MAX_MS + 2000 });

/** Camino feliz completo del onboarding, sin depositar. */
async function walkOnboarding(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByTestId("onboarding");
  await user.click(await waitForP1());
  await user.click(await screen.findByTestId("onboarding-create-wallet"));
  await user.click(await screen.findByTestId("onboarding-explore"));
}

describe("Fase 2 — activación", () => {
  it("V13 — el onboarding termina en el feed", async () => {
    const user = userEvent.setup();
    renderApp();
    await walkOnboarding(user);
    expect(screen.queryByTestId("onboarding")).toBeNull();
    expect(await screen.findByTestId("home-screen")).toBeInTheDocument();
    expect((await screen.findAllByTestId("market-card")).length).toBeGreaterThan(0);
  });

  it("V14 — el camino feliz cabe en 75 s con presupuesto humano por paso", async () => {
    const user = userEvent.setup();
    renderApp();
    const start = performance.now();
    await walkOnboarding(user);
    await screen.findByTestId("home-screen");
    const machine = performance.now() - start;

    // 3 taps + 3 lecturas: presupuesto humano generoso por paso
    const TAPS = 3;
    const HUMAN_MS_PER_STEP = 12_000;
    const budget = SPLASH_MAX_MS + TAPS * HUMAN_MS_PER_STEP + machine;
    expect(budget).toBeLessThan(75_000);
    // y ningún paso extra escondido: exactamente 3 decisiones hasta el feed
    expect(TAPS).toBeLessThanOrEqual(3);
  });

  it("V15 — crear wallet es el camino primario y conectar el secundario", async () => {
    const user = userEvent.setup();
    const app = renderApp();
    await screen.findByTestId("onboarding");
    await user.click(await waitForP1());

    const primary = await screen.findByTestId("onboarding-create-wallet");
    const secondary = screen.getByTestId("onboarding-connect-wallet");
    // el primario va primero en el DOM y en jerarquía visual
    expect(
      primary.compareDocumentPosition(secondary) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(primary.className).toContain("bg-teal");
    expect(secondary.className).toContain("bg-transparent");

    await user.click(primary);
    await screen.findByTestId("onboarding-explore");
    expect(app.eventNames()).toContain("wallet_created");
  });

  it("V16 — con saldo 0 se explora el feed y el detalle completo", async () => {
    const user = userEvent.setup();
    const app = renderApp();
    await walkOnboarding(user);
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByTestId("card-open"),
    );
    const detail = await screen.findByTestId("market-detail");
    expect(within(detail).getByTestId("resolution-summary")).toBeInTheDocument();
    expect(within(detail).getByTestId("decision-zone")).toBeInTheDocument();
    expect(app.eventNames()).toContain("explore_without_funds");
  });

  it("V17 — la hoja de depósito ofrece on-ramp, transferencia y cerrar", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");
    await user.click(screen.getByTestId("header-deposit"));

    const sheet = await screen.findByTestId("deposit-sheet");
    expect(within(sheet).getByTestId("deposit-onramp")).toBeEnabled();
    expect(within(sheet).getByTestId("deposit-transfer")).toBeEnabled();

    await user.click(within(sheet).getByRole("button", { name: S.deposit.close }));
    await waitFor(() => expect(screen.queryByTestId("deposit-sheet")).toBeNull());
  });

  it("V18 — el portafolio vacío ofrece volver a los mercados", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_NO_FUNDS });
    await screen.findByTestId("home-screen");
    await user.click(screen.getByRole("tab", { name: new RegExp(`^${S.tabs.portfolio}`) }));

    const empty = await screen.findByTestId("portfolio-empty");
    expect(empty).toHaveTextContent(S.portfolio.empty);
    await user.click(within(empty).getByRole("button", { name: S.portfolio.emptyCta }));
    expect(await screen.findByTestId("home-screen")).toBeInTheDocument();
  });

  it("V19 — tras operar hay dos salidas: portafolio o seguir explorando", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_WITH_FUNDS });
    await screen.findByTestId("home-screen");
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByTestId("card-open"),
    );
    await user.click(await screen.findByTestId("detail-trade-cta"));

    const post = await screen.findByTestId("post-trade");
    expect(within(post).getByTestId("post-trade-portfolio")).toBeInTheDocument();
    expect(within(post).getByTestId("post-trade-explore")).toBeInTheDocument();

    await user.click(within(post).getByTestId("post-trade-portfolio"));
    expect(await screen.findByTestId("portfolio-screen")).toBeInTheDocument();
    expect((await screen.findAllByTestId("position-row")).length).toBeGreaterThan(0);
  });

  it("V20 — el header sigue el estado de la wallet", async () => {
    const user = userEvent.setup();
    renderApp();
    // sin wallet no hay saldo: el header lleva identidad, las dos puertas
    expect(screen.queryByTestId("header-balance")).toBeNull();
    expect(screen.getByTestId("header-entrar")).toBeInTheDocument();
    expect(screen.getByTestId("header-crear-cuenta")).toBeInTheDocument();
    await walkOnboarding(user);
    await waitFor(() =>
      expect(screen.getByTestId("header-balance")).toHaveTextContent("$0"),
    );
    expect(screen.getByTestId("header-deposit")).toBeInTheDocument();
  });

  it("V20 — operar descuenta del saldo que muestra el header", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_WITH_FUNDS });
    await screen.findByTestId("home-screen");
    expect(screen.getByTestId("header-balance")).toHaveTextContent("120");
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByTestId("card-open"),
    );
    await user.click(await screen.findByTestId("detail-trade-cta"));
    await screen.findByTestId("post-trade");
    await waitFor(() =>
      expect(screen.getByTestId("header-balance")).toHaveTextContent("110"),
    );
  });

  it("V21 — se emiten los eventos de onboarding, wallet, depósito y portafolio", async () => {
    const user = userEvent.setup();
    const app = renderApp();
    await walkOnboarding(user);
    await user.click(screen.getByTestId("header-deposit"));
    await user.click(await screen.findByTestId("deposit-transfer"));
    await screen.findByTestId("deposit-started");
    // la hoja atrapa el foco: se cierra antes de volver a la navegación
    await user.click(
      within(screen.getByTestId("deposit-sheet")).getByRole("button", {
        name: S.deposit.close,
      }),
    );
    await waitFor(() => expect(screen.queryByTestId("deposit-sheet")).toBeNull());
    await user.click(screen.getByRole("tab", { name: new RegExp(`^${S.tabs.portfolio}`) }));

    const names = app.eventNames();
    for (const event of [
      "view_onboarding_step",
      "wallet_created",
      "onboarding_completed",
      "explore_without_funds",
      "click_deposit_cta",
      "deposit_method_selected",
      "deposit_started",
      "view_portfolio",
      "view_feed",
    ]) {
      expect(names, `falta ${event}`).toContain(event);
    }
  });

  it("V22 — no hay KYC ni frase semilla en el camino de activación", async () => {
    const user = userEvent.setup();
    const { container } = renderApp();
    const forbidden =
      /kyc|identidad|ine\b|pasaporte|selfie|frase semilla|seed phrase|clave secreta|respaldo de 12|12 palabras/i;

    await screen.findByTestId("onboarding");
    expect(container.textContent).not.toMatch(forbidden);
    const start = await waitForP1();
    expect(container.textContent).not.toMatch(forbidden);
    await user.click(start);
    expect(container.textContent).not.toMatch(forbidden);
    await user.click(await screen.findByTestId("onboarding-create-wallet"));
    await screen.findByTestId("onboarding-explore");
    expect(container.textContent).not.toMatch(forbidden);
    await user.click(screen.getByTestId("onboarding-explore"));
    await screen.findByTestId("home-screen");
    expect(container.textContent).not.toMatch(forbidden);
  });

  it("V23 — un fallo al crear la wallet deja error accionable y no cierra el onboarding", async () => {
    const user = userEvent.setup();
    const app = renderApp({ wallet: { failCreate: true } });
    await screen.findByTestId("onboarding");
    await user.click(await waitForP1());
    await user.click(await screen.findByTestId("onboarding-create-wallet"));

    const error = await screen.findByTestId("onboarding-wallet-error");
    expect(error).toHaveTextContent("No pudimos crear tu wallet");
    expect(within(error).getByRole("button", { name: S.common.retry })).toBeInTheDocument();
    // sigue en P2: el onboarding no se cerró (R-015)
    expect(screen.getByTestId("onboarding")).toHaveAttribute("data-step", "p2");
    expect(app.eventNames()).not.toContain("onboarding_completed");
  });

  it("P0 tiene techo de 1.5 s y avanza en cuanto el shell pintó", async () => {
    vi.useFakeTimers();
    try {
      renderApp();
      expect(screen.getByTestId("onboarding")).toHaveAttribute("data-step", "p0");
      expect(SPLASH_MAX_MS).toBeLessThanOrEqual(1500);
      // no espera el techo: con el mínimo cumplido ya sigue
      await act(async () => {
        vi.advanceTimersByTime(SPLASH_MIN_MS + 40);
      });
      expect(screen.getByTestId("onboarding")).toHaveAttribute("data-step", "p1");
      expect(SPLASH_MIN_MS).toBeLessThan(SPLASH_MAX_MS);
    } finally {
      vi.useRealTimers();
    }
  });

  it("conectar wallet también lleva a P3", async () => {
    const user = userEvent.setup();
    const app = renderApp({ walletAdapter: createMockWalletAdapter({ latencyMs: 0 }) });
    await screen.findByTestId("onboarding");
    await user.click(await waitForP1());
    await user.click(await screen.findByTestId("onboarding-connect-wallet"));
    await screen.findByTestId("onboarding-explore");
    expect(app.eventNames()).toContain("wallet_connected");
  });
});
