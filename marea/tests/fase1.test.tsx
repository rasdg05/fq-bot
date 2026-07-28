import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { renderApp, READY_NO_FUNDS, READY_WITH_FUNDS } from "./helpers";
import { S } from "@/lib/strings";
import { tabIds } from "@/components/BottomTabs";
import { MOCK_MARKETS } from "@/adapters/mock/markets";
import { MarketCard, resolveVariant } from "@/components/MarketCard";
import { render } from "@testing-library/react";

const feed = () => screen.findByTestId("home-screen");

describe("Fase 1 — descubrimiento", () => {
  it("V2 — MarketCard resuelve las cuatro variantes", async () => {
    const live = MOCK_MARKETS.find((m) => m.status === "live")!;
    const edge = MOCK_MARKETS.find(
      (m) => m.edge !== null && m.status !== "live",
    )!;
    const plain = MOCK_MARKETS.find((m) => m.edge === null && m.status === "open")!;

    expect(resolveVariant(live)).toBe("live");
    expect(resolveVariant(edge)).toBe("edge");
    expect(resolveVariant(plain)).toBe("default");

    const { container } = render(
      <>
        <MarketCard market={live} onOpen={() => {}} />
        <MarketCard market={edge} onOpen={() => {}} />
        <MarketCard market={plain} onOpen={() => {}} />
        <MarketCard market={plain} variant="compact" onOpen={() => {}} />
      </>,
    );
    const variants = [...container.querySelectorAll("[data-variant]")].map((el) =>
      el.getAttribute("data-variant"),
    );
    expect(variants).toEqual(["live", "edge", "default", "compact"]);
  });

  it("V3 — la probabilidad es el nodo tipográfico dominante", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await feed();
    const cards = await screen.findAllByTestId("market-card");
    for (const card of cards.slice(0, 4)) {
      const dominant = within(card).getByText(S.market.probability)
        .previousElementSibling as HTMLElement;
      expect(dominant.getAttribute("data-role")).toBe("probability");
      // única escala `text-prob*` de la card: nada compite con ella (R-004)
      expect(dominant.className).toMatch(/text-prob/);
      const others = [...card.querySelectorAll("*")].filter(
        (el) => el !== dominant && /text-prob/.test(el.className.toString()),
      );
      expect(others).toHaveLength(0);
    }
  });

  it("V4 — el Edge aparece sólo en las cards que superan el umbral", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    await feed();
    const cards = await screen.findAllByTestId("market-card");
    for (const card of cards) {
      const id = card.getAttribute("data-market-id");
      const market = MOCK_MARKETS.find((m) => m.id === id)!;
      const badge = within(card).queryByTestId("edge-badge");
      if (market.edge === null) {
        expect(badge, `${id} no debe mostrar Edge`).toBeNull();
      } else {
        expect(badge).not.toBeNull();
        expect(badge!.textContent).toContain("Marea");
        expect(Math.abs(Number(badge!.getAttribute("data-edge-pp")))).toBeGreaterThanOrEqual(4);
      }
    }
  });

  it("V5 — Home muestra Hot ahora, chips de categoría y cards", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_NO_FUNDS });
    await feed();

    expect(screen.getByText(S.feed.hotNow)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: S.categories.cripto })).toBeInTheDocument();
    expect((await screen.findAllByTestId("market-card")).length).toBeGreaterThan(3);

    await user.click(screen.getByRole("tab", { name: S.categories.deportes }));
    const cards = await screen.findAllByTestId("market-card");
    for (const card of cards) {
      const id = card.getAttribute("data-market-id");
      expect(MOCK_MARKETS.find((m) => m.id === id)!.category).toBe("deportes");
    }
  });

  it("V6 — el detalle tiene una sola zona de decisión y el criterio de resolución antes del CTA", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_NO_FUNDS });
    await feed();
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );

    const detail = await screen.findByTestId("market-detail");
    expect(within(detail).getAllByTestId("decision-zone")).toHaveLength(1);

    const resolution = within(detail).getByTestId("resolution-summary");
    const cta =
      within(detail).queryByTestId("detail-trade-cta") ??
      within(detail).getByTestId("detail-deposit-cta");
    // el criterio se lee antes de operar (R-013)
    expect(
      resolution.compareDocumentPosition(cta) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("V7 — el feed vacío muestra su estado y el skeleton precede a los datos", async () => {
    const empty = {
      listMarkets: async () => [],
      getMarket: async () => {
        throw new Error("n/a");
      },
      listPositions: async () => [],
      prepareTrade: async () => ({ positionId: "x", venue: "agregado" }),
    };
    const { rerender: _ } = renderApp({
      overrides: READY_NO_FUNDS,
      marketDataAdapter: empty as never,
    });
    expect(screen.getByTestId("list-skeleton")).toBeInTheDocument();
    const state = await screen.findByTestId("feed-empty");
    expect(state).toHaveTextContent(S.feed.empty);
    // estados excluyentes: al llegar el vacío ya no hay skeleton (R-014)
    expect(screen.queryByTestId("list-skeleton")).toBeNull();
    expect(_).toBeDefined();
  });

  it("V8 — hay 5 tabs y Mercados es la de entrada", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    const tabs = within(screen.getByTestId("bottom-tabs")).getAllByRole("tab");
    expect(tabs).toHaveLength(5);
    // con dinero real la cartera existe; en modo puntos su lugar lo toma la tabla
    expect(tabIds(false)).toEqual(["markets", "search", "portfolio", "wallet", "profile"]);
    expect(tabIds(true)).toEqual(["markets", "search", "portfolio", "tabla", "profile"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[0]).toHaveTextContent(S.tabs.markets);
    await feed();
  });

  it("V9 — el feed emite view_feed, open_market_detail y los CTA de operar y depositar", async () => {
    const user = userEvent.setup();
    const app = renderApp({ overrides: READY_NO_FUNDS });
    await feed();
    expect(app.eventNames()).toContain("view_feed");

    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );
    expect(app.eventNames()).toContain("open_market_detail");

    // sin saldo el CTA de la zona de decisión es depositar
    await user.click(await screen.findByTestId("detail-deposit-cta"));
    expect(app.eventNames()).toContain("click_deposit_cta");
  });

  it("V9 — operar con saldo emite click_trade_cta", async () => {
    const user = userEvent.setup();
    const app = renderApp({ overrides: READY_WITH_FUNDS });
    await feed();
    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByRole("button"),
    );
    await user.click(await screen.findByTestId("detail-trade-cta"));
    expect(app.eventNames()).toContain("click_trade_cta");
    expect(app.eventNames()).toContain("trade_confirmed");
  });

  it("V12 — con saldo 0 el header ofrece Depositar", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    const deposit = screen.getByTestId("header-deposit");
    expect(deposit).toHaveTextContent(S.header.deposit);
    await feed();
  });

  it("V12 — con saldo el header ya no empuja a depositar", async () => {
    renderApp({
      overrides: {
        ...READY_NO_FUNDS,
        wallet: { ...READY_NO_FUNDS.wallet!, balance: 50 },
      },
    });
    expect(screen.queryByTestId("header-deposit")).toBeNull();
    expect(screen.getByTestId("header-balance")).toHaveTextContent("50");
    await feed();
  });

  it("V23 — un fallo del feed muestra mensaje en español y Reintentar", async () => {
    const user = userEvent.setup();
    let fail = true;
    const adapter = {
      listMarkets: async () => {
        if (fail) {
          fail = false;
          const { appError } = await import("@/domain/errors");
          throw appError("E_MARKETS_FETCH_FAILED");
        }
        return MOCK_MARKETS;
      },
      getMarket: async () => MOCK_MARKETS[0],
      listPositions: async () => [],
      prepareTrade: async () => ({ positionId: "x", venue: "agregado" }),
    };
    renderApp({ overrides: READY_NO_FUNDS, marketDataAdapter: adapter as never });

    const error = await screen.findByTestId("error-state");
    expect(error).toHaveTextContent("No pudimos cargar los mercados");
    expect(error.textContent).not.toMatch(/E_[A-Z_]+/);

    await user.click(within(error).getByRole("button", { name: S.common.retry }));
    await waitFor(() => expect(screen.queryByTestId("error-state")).toBeNull());
    expect((await screen.findAllByTestId("market-card")).length).toBeGreaterThan(0);
  });
});
