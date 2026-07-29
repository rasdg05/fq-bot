import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { renderApp, READY_NO_FUNDS, READY_WITH_FUNDS } from "./helpers";
import { S } from "@/lib/strings";
import { tabIds } from "@/components/BottomTabs";
import { MOCK_MARKETS } from "@/adapters/mock/markets";
import { MAX_DESTACADOS } from "@/components/FeaturedCarousel";
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
      const dominant = card.querySelector('[data-role="probability"]') as HTMLElement;
      expect(dominant).not.toBeNull();
      // en la card el nodo dominante es la pill de 30 px en peso 700: el de
      // 44 px (`text-prob`) se fue al detalle. El rival existe y es más chico
      // —`text-prob-riv`, 20 px—, así que la comprobación es que **nadie más**
      // usa la escala del líder, no que no haya otro número (R-004)
      expect(dominant.className).toMatch(/text-prob-pill/);
      expect(dominant.className).toMatch(/font-bold/);
      const compiten = [...card.querySelectorAll("*")].filter(
        (el) =>
          el !== dominant &&
          /text-prob-pill|text-prob-lg|text-prob\b/.test(el.className.toString()),
      );
      expect(compiten).toHaveLength(0);
    }
  });

  it("V4 — el Edge no vive en el feed: se lee en el detalle, que es donde se decide", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_NO_FUNDS });
    await feed();
    const cards = await screen.findAllByTestId("market-card");
    // ninguna card, tenga o no Edge, lo enseña: ni badge, ni borde, ni orden
    for (const card of cards) {
      expect(
        within(card).queryByTestId("edge-badge"),
        `${card.getAttribute("data-market-id")} no debe enseñar Edge en el feed`,
      ).toBeNull();
    }
    // y sigue existiendo donde importa: el detalle de un mercado con Edge
    const conEdge = MOCK_MARKETS.find((m) => m.edge !== null)!;
    const card = cards.find((c) => c.getAttribute("data-market-id") === conEdge.id)!;
    await user.click(within(card).getByTestId("card-open"));
    const detalle = await screen.findByTestId("market-detail");
    const badge = within(detalle).getByTestId("edge-badge-detail");
    expect(Math.abs(conEdge.edge as number)).toBeGreaterThanOrEqual(4);
    expect(badge.textContent).toContain(conEdge.edgeLabel ?? "Marea");
  });

  it("V5 — Home abre con destacados, agrupa por categoría y los chips filtran", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_NO_FUNDS });
    await feed();

    // el carrusel de destacados, con su tope y sus puntos
    const carrusel = screen.getByTestId("featured-carousel");
    const piezas = within(carrusel).getAllByTestId("featured-card");
    expect(piezas.length).toBeGreaterThan(1);
    expect(piezas.length).toBeLessThanOrEqual(MAX_DESTACADOS);
    expect(screen.getByTestId("featured-dots").childElementCount).toBe(piezas.length);

    // el feed va en bloques por categoría, cada uno con su encabezado
    const encabezados = screen.getAllByTestId("section-header");
    expect(encabezados.length).toBeGreaterThan(1);
    expect(encabezados.some((h) => h.textContent?.includes(S.categories.cripto))).toBe(true);

    expect(screen.getByRole("tab", { name: S.categories.cripto })).toBeInTheDocument();
    expect((await screen.findAllByTestId("market-card")).length).toBeGreaterThan(3);

    await user.click(screen.getByRole("tab", { name: S.categories.deportes }));
    const cards = await screen.findAllByTestId("market-card");
    for (const card of cards) {
      const id = card.getAttribute("data-market-id");
      expect(MOCK_MARKETS.find((m) => m.id === id)!.category).toBe("deportes");
    }
    // con un filtro puesto no se repite ni el carrusel ni la agrupación
    expect(screen.queryByTestId("featured-carousel")).toBeNull();
  });

  it("V5 — el chevron de un encabezado filtra por esa categoría", async () => {
    const user = userEvent.setup();
    renderApp({ overrides: READY_NO_FUNDS });
    await feed();

    const encabezado = screen
      .getAllByTestId("section-header")
      .find((h) => h.textContent?.includes(S.categories.deportes))!;
    await user.click(encabezado);

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
      within((await screen.findAllByTestId("market-card"))[0]).getByTestId("card-open"),
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

  it("V8 — hay exactamente 4 tabs y Mercados es la de entrada", async () => {
    renderApp({ overrides: READY_NO_FUNDS });
    const tabs = within(screen.getByTestId("bottom-tabs")).getAllByRole("tab");
    expect(tabs).toHaveLength(4);
    // la tabla y la cartera no son destinos de navegación: se consultan desde
    // Perfil. Cuatro pestañas, siempre las mismas, con o sin dinero real
    expect(tabIds()).toEqual(["markets", "search", "portfolio", "profile"]);
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
      within((await screen.findAllByTestId("market-card"))[0]).getByTestId("card-open"),
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
      within((await screen.findAllByTestId("market-card"))[0]).getByTestId("card-open"),
    );
    await user.click(await screen.findByTestId("detail-trade-cta"));
    expect(app.eventNames()).toContain("click_trade_cta");
    expect(app.eventNames()).toContain("trade_confirmed");
  });

  it("V12 — sin sesión el header ofrece Entrar y Crear cuenta, nunca un muro", async () => {
    renderApp({ overrides: { ...READY_NO_FUNDS, wallet: null } });
    // el header lleva identidad: dos puertas y las dos a la vista
    expect(screen.getByTestId("header-entrar")).toHaveTextContent(S.cuenta.entrarCta);
    expect(screen.getByTestId("header-crear-cuenta")).toHaveTextContent(
      S.cuenta.sinCuentaCta,
    );
    // y el saldo no se pierde: vive con las posiciones, que es lo tuyo
    await feed();
  });

  it("V12 — el saldo y el camino para recargar viven en el portafolio", async () => {
    const user = userEvent.setup();
    renderApp({
      overrides: {
        ...READY_NO_FUNDS,
        wallet: { ...READY_NO_FUNDS.wallet!, balance: 50 },
      },
    });
    await feed();
    await user.click(within(screen.getByTestId("bottom-tabs")).getAllByRole("tab")[2]);
    const saldo = await screen.findByTestId("portfolio-saldo");
    expect(saldo).toHaveTextContent("50");
    expect(within(saldo).getByTestId("portfolio-recargar")).toBeInTheDocument();
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
