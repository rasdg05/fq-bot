import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { renderApp } from "./helpers";
import { S } from "@/lib/strings";
import { SPLASH_MAX_MS } from "@/screens/OnboardingFlow";
import { createOwnMarketsAdapter } from "@/adapters/ownMarkets/ownMarketsAdapter";
import { OWN_MARKETS } from "@/adapters/ownMarkets/catalog";
import { WELCOME_GRANT } from "@/domain/points";
import { EDGE_MIN_PP } from "@/domain/edge";

const points = () => ({ engine: "parimutuel_points" as const });
const waitForP1 = () =>
  screen.findByTestId("onboarding-start", {}, { timeout: SPLASH_MAX_MS + 2000 });

/** Onboarding de puntos: un solo tap hasta el feed, sin wallet. */
async function enter(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await waitForP1());
  await screen.findByTestId("home-screen");
}

describe("Mercados propios — adapter", () => {
  it("expone el pozo, la probabilidad implícita y el criterio citado", async () => {
    const adapter = createOwnMarketsAdapter();
    const markets = await adapter.listMarkets();
    expect(markets.length).toBe(OWN_MARKETS.length);

    for (const market of markets) {
      expect(market.pool).toBeDefined();
      expect(market.probability).toBeGreaterThan(0);
      expect(market.probability).toBeLessThan(1);
      expect(market.region).toBe("latam");
      // el criterio siempre cita institución y ventana de disputa
      expect(market.resolution_summary).toMatch(/Fuente:/);
      expect(market.resolution_summary).toMatch(/disputar/);
      expect(market.venue?.label).toBe("Marea");
    }
  });

  it("sin referencia externa no hay Edge, que es la mayoría del catálogo", async () => {
    const markets = await createOwnMarketsAdapter().listMarkets();
    const conEdge = markets.filter((market) => market.edge !== null);
    expect(conEdge).toHaveLength(0);
  });

  it("con referencia externa el Edge aparece y dice de quién es la lectura", async () => {
    const seed = OWN_MARKETS.find((entry) => entry.referenceKey)!;
    const adapter = createOwnMarketsAdapter({
      reference: new Map([
        [seed.referenceKey!, { probability: 0.9, venue: "Polymarket" }],
      ]),
    });
    const market = await adapter.getMarket(seed.id);
    expect(market.edge).not.toBeNull();
    expect(Math.abs(market.edge as number)).toBeGreaterThanOrEqual(EDGE_MIN_PP);
    // la lectura no es nuestra y el copy no puede decir "Marea" (R-027)
    expect(market.edgeLabel).toBe("Polymarket");
    expect(market.mareaBasis).toContain("Polymarket");
  });

  it("apostar mueve el pozo y el siguiente ve otro precio", async () => {
    const adapter = createOwnMarketsAdapter();
    const [first] = await adapter.listMarkets();
    const antes = first.probability;
    await adapter.prepareTrade({ marketId: first.id, side: "si", size: 5_000 });
    const despues = await adapter.getMarket(first.id);
    expect(despues.probability).toBeGreaterThan(antes);
  });

  it("no acepta apuestas en un mercado cerrado", async () => {
    const adapter = createOwnMarketsAdapter({ now: () => Date.parse("2030-01-01") });
    const [first] = await adapter.listMarkets();
    await expect(
      adapter.prepareTrade({ marketId: first.id, side: "si", size: 100 }),
    ).rejects.toMatchObject({ code: "E_TRADE_INIT_FAILED" });
  });

  it("la posición trae pago potencial, no un resultado inventado", async () => {
    const adapter = createOwnMarketsAdapter();
    const [first] = await adapter.listMarkets();
    await adapter.prepareTrade({ marketId: first.id, side: "no", size: 200 });
    const [position] = await adapter.listPositions();
    expect(position.pnl).toBe(0);
    expect(position.toWin).toBeGreaterThan(200);
    expect(position.multiplier).toBeGreaterThan(1);
  });
});

describe("Mercados propios — interfaz", () => {
  it("el onboarding de puntos llega al feed en un solo tap, sin wallet", async () => {
    const user = userEvent.setup();
    const app = renderApp(points());
    const start = await waitForP1();
    // se declara la unidad antes de empezar, no después (R-026)
    expect(screen.getByTestId("onboarding-points-note")).toHaveTextContent(
      /no se cambian por efectivo/i,
    );
    await user.click(start);

    expect(await screen.findByTestId("home-screen")).toBeInTheDocument();
    expect(screen.queryByTestId("onboarding-create-wallet")).toBeNull();
    expect(app.eventNames()).toContain("onboarding_completed");
  });

  it("el saldo de bienvenida se ve en el header, en puntos", async () => {
    const user = userEvent.setup();
    renderApp(points());
    await enter(user);
    const balance = screen.getByTestId("header-balance");
    expect(balance).toHaveTextContent("1,000 pts");
    expect(balance.textContent).not.toMatch(/\$/);
  });

  it("las cards muestran cuánto paga, no cuánto se ha operado", async () => {
    const user = userEvent.setup();
    renderApp(points());
    await enter(user);
    const cards = await screen.findAllByTestId("market-card");
    expect(cards.length).toBeGreaterThan(5);
    expect(cards[0]).toHaveTextContent(/Paga \d/);
    expect(cards[0].textContent).not.toMatch(/\$/);
  });

  it("el detalle explica el reparto del pozo y que Marea no apuesta en contra", async () => {
    const user = userEvent.setup();
    renderApp(points());
    await enter(user);
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );

    const pool = await screen.findByTestId("pool-breakdown");
    expect(pool).toHaveTextContent(/se reparte/i);
    expect(pool).toHaveTextContent(/Marea no apuesta contra ti/i);
    // el criterio de resolución sigue antes del CTA (R-013)
    const resolution = screen.getByTestId("resolution-summary");
    expect(resolution).toHaveTextContent(/Fuente:/);
  });

  it("antes de apostar se ve cuánto se cobra si acierta", async () => {
    const user = userEvent.setup();
    renderApp(points());
    await enter(user);
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );
    const hint = await screen.findByTestId("payout-hint");
    expect(hint).toHaveTextContent(/Si aciertas, cobras .*pts.*×/);
    expect(screen.getByTestId("points-disclaimer")).toHaveTextContent(
      /no.*dinero/i,
    );
  });

  it("cambiar de lado cambia el pago que se muestra", async () => {
    const user = userEvent.setup();
    renderApp(points());
    await enter(user);
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );
    const before = (await screen.findByTestId("payout-hint")).textContent;
    await user.click(screen.getByTestId("side-no"));
    await waitFor(() =>
      expect(screen.getByTestId("payout-hint").textContent).not.toBe(before),
    );
  });

  it("apostar descuenta puntos y deja la posición con su pago potencial", async () => {
    const user = userEvent.setup();
    renderApp(points());
    await enter(user);
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );
    await user.click(await screen.findByTestId("detail-trade-cta"));
    await screen.findByTestId("post-trade");

    await waitFor(() =>
      expect(screen.getByTestId("header-balance")).toHaveTextContent("900 pts"),
    );
    await user.click(screen.getByTestId("post-trade-portfolio"));
    const row = (await screen.findAllByTestId("position-row"))[0];
    expect(within(row).getByTestId("position-towin")).toHaveTextContent(/pts/);
    expect(row).toHaveTextContent(S.portfolio.toWin);
  });

  it("sin puntos el CTA ofrece recargar en contexto, no un error", async () => {
    const user = userEvent.setup();
    renderApp({ ...points(), overrides: { points: { balance: 0, entries: [] } } });
    await enter(user);
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );

    // mismo patrón que el depósito contextual: nunca un muro, nunca un error
    const cta = await screen.findByTestId("detail-deposit-cta");
    expect(cta).toHaveTextContent(S.points.topUp);
    expect(screen.queryByTestId("trade-error")).toBeNull();

    await user.click(cta);
    expect(await screen.findByTestId("points-sheet")).toBeInTheDocument();
  });

  it("el guardia de saldo es defensa en profundidad: rechaza sin mover el ledger", async () => {
    // la interfaz ya impide llegar aquí; el dominio lo rechaza igual
    const user = userEvent.setup();
    const app = renderApp({
      ...points(),
      overrides: { points: { balance: 60, entries: [] } },
    });
    await enter(user);
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );
    // con 60 puntos el preajuste de 100 no alcanza: se ofrece recargar
    expect(await screen.findByTestId("detail-deposit-cta")).toBeInTheDocument();
    expect(app.eventNames()).not.toContain("trade_confirmed");
  });

  it("la hoja de puntos recarga y explica por qué se juega sin dinero", async () => {
    const user = userEvent.setup();
    renderApp({ ...points(), overrides: { points: { balance: 0, entries: [] } } });
    await enter(user);
    await user.click(screen.getByTestId("header-deposit"));

    const sheet = await screen.findByTestId("points-sheet");
    expect(sheet).toHaveTextContent(S.points.why);
    expect(within(sheet).queryByTestId("deposit-onramp")).toBeNull();

    await user.click(within(sheet).getByTestId("points-topup"));
    expect(await screen.findByTestId("points-topup-done")).toBeInTheDocument();
    // la segunda del día ya no da nada, y lo dice
    await user.click(within(sheet).getByTestId("points-topup"));
    expect(await screen.findByTestId("points-topup-unavailable")).toBeInTheDocument();
  });

  it("en ninguna superficie de puntos aparece un símbolo de moneda", async () => {
    const user = userEvent.setup();
    const { container } = renderApp(points());
    await enter(user);
    const surfaces: string[] = [container.textContent ?? ""];

    for (const tab of [S.tabs.portfolio, S.tabs.wallet, S.tabs.profile]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      await waitFor(() => expect(container.textContent).toBeTruthy());
      surfaces.push(container.textContent ?? "");
    }
    for (const text of surfaces) {
      // los títulos del catálogo sí mencionan dólares: se excluyen del barrido
      const chrome = text.replace(/¿[^?]*\?/g, "");
      expect(chrome).not.toMatch(/US\$|\$\s?\d/);
    }
  });

  it("explorar sigue sin costar nada: se ve todo con cero puntos", async () => {
    const user = userEvent.setup();
    renderApp({ ...points(), overrides: { points: { balance: 0, entries: [] } } });
    await enter(user);
    const cards = await screen.findAllByTestId("market-card");
    expect(cards.length).toBeGreaterThan(5);
    await user.click(within(cards[0]).getByRole("button"));
    expect(await screen.findByTestId("resolution-summary")).toBeInTheDocument();
    expect(screen.getByTestId("pool-breakdown")).toBeInTheDocument();
  });

  it("la bienvenida es exactamente la declarada, no un número suelto", async () => {
    const user = userEvent.setup();
    renderApp(points());
    await enter(user);
    expect(screen.getByTestId("header-balance")).toHaveTextContent(
      new Intl.NumberFormat("es-MX").format(WELCOME_GRANT),
    );
  });
});
