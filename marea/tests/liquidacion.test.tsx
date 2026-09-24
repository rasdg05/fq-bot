import { describe, expect, it } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { renderApp } from "./helpers";
import { S } from "@/lib/strings";
import { SPLASH_MAX_MS } from "@/screens/OnboardingFlow";
import { createOwnMarketsAdapter } from "@/adapters/ownMarkets/ownMarketsAdapter";
import { validateSeed, type OwnMarketSeed } from "@/adapters/ownMarkets/catalog";
import type { SettlementState } from "@/domain/settlement";
import { WELCOME_GRANT } from "@/domain/points";
import { binaryPool } from "@/domain/parimutuel";

/**
 * El ciclo entero, de punta a punta: se apuesta, el mercado cierra, el
 * liquidador publica el resultado y el usuario cobra. Es la prueba que faltaba
 * y la que sostiene el producto (R-040).
 */

const AHORA = Date.parse("2026-08-05T12:00:00Z");

const seed: OwnMarketSeed = validateSeed({
  id: "btc-prueba",
  title: "¿Bitcoin cierra la semana arriba de 71,000 dólares?",
  shortTitle: "Bitcoin cierra la semana arriba de 71 mil",
  outcomes: [
    { id: "si", label: "Arriba de 71,000" },
    { id: "no", label: "Abajo de 71,000" },
  ],
  category: "cripto",
  country: "LATAM",
  closesAt: "2026-08-10T00:00:00Z",
  pool: binaryPool(500, 500, 300),
  rule: {
    kind: "precio",
    par: "BTC/USD",
    umbral: 71_000,
    comparacion: "arriba",
    modo: "cierre",
  },
  resolution: {
    sourceName: "Kraken (velas diarias públicas)",
    sourceUrl: "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440",
    criterion:
      "Se resuelve Sí si la vela diaria de BTC/USD en Kraken del domingo cierra por encima de 71,000 dólares.",
    settlesAt: "2026-08-10T23:59:00Z",
    disputeWindowHours: 12,
  },
});

const EVIDENCIA = "Vela diaria de BTC/USD en Kraken del 2026-08-10: cierre 72,500 USD.";

function pagado(outcome: "si" | "no"): SettlementState {
  return {
    marketId: seed.id,
    phase: "pagado",
    outcome,
    evidence: EVIDENCIA,
    readAt: "2026-08-11T00:10:00Z",
    disputeUntil: "2026-08-11T12:10:00Z",
    paidAt: "2026-08-11T12:11:00Z",
  };
}

function adapterConLiquidacion(estados: () => SettlementState[]) {
  return createOwnMarketsAdapter({
    seeds: [seed],
    loadSettlements: async () => estados(),
    now: () => AHORA,
  });
}

describe("Liquidación de punta a punta", () => {
  it("V40 una posición ganadora cobra el pozo y trae la lectura que lo justifica", async () => {
    let estados: SettlementState[] = [];
    const adapter = adapterConLiquidacion(() => estados);

    await adapter.prepareTrade({ marketId: seed.id, side: "si", size: 100 });
    const abiertas = await adapter.listPositions();
    expect(abiertas[0].status).toBe("open");
    expect(abiertas[0].payout).toBeUndefined();

    estados = [pagado("si")];
    const cerradas = await adapter.listPositions();
    expect(cerradas[0].status).toBe("won");
    // pozo de 1,100 menos 3 %, repartido entre los 600 del lado Sí
    expect(cerradas[0].payout).toBeCloseTo((1_100 * 0.97 * 100) / 600, 6);
    expect(cerradas[0].pnl).toBeGreaterThan(0);
    expect(cerradas[0].evidence).toBe(EVIDENCIA);
    // ya no se muestra pago potencial: el resultado dejó de ser hipotético
    expect(cerradas[0].toWin).toBeUndefined();
  });

  it("V41 una posición perdedora se marca perdida y no paga", async () => {
    let estados: SettlementState[] = [];
    const adapter = adapterConLiquidacion(() => estados);
    await adapter.prepareTrade({ marketId: seed.id, side: "si", size: 100 });

    estados = [pagado("no")];
    const posiciones = await adapter.listPositions();
    expect(posiciones[0].status).toBe("lost");
    expect(posiciones[0].payout).toBe(0);
    expect(posiciones[0].pnl).toBe(-100);
  });

  it("V42 un mercado ya resuelto no acepta más apuestas", async () => {
    const adapter = adapterConLiquidacion(() => [pagado("si")]);
    // el estado se conoce al listar; después de eso, apostar es imposible
    await adapter.listMarkets();
    await expect(
      adapter.prepareTrade({ marketId: seed.id, side: "si", size: 10 }),
    ).rejects.toMatchObject({ code: "E_TRADE_INIT_FAILED" });
  });

  it("V43 el mercado resuelto muestra qué salió y con qué lectura", async () => {
    const adapter = adapterConLiquidacion(() => [pagado("si")]);
    const [market] = await adapter.listMarkets();
    expect(market.status).toBe("resolved");
    expect(market.outcome).toBe("si");
    expect(market.settlementEvidence).toBe(EVIDENCIA);
  });

  it("V46 una casa externa lenta no deja el feed en blanco: sale sin Edge y el Edge llega después", async () => {
    let resolver: (() => void) | undefined;
    const conReferencia = createOwnMarketsAdapter({
      seeds: [{ ...seed, referenceKey: "btc" }],
      now: () => AHORA,
      referenceTimeoutMs: 20,
      loadReference: () =>
        new Promise((resolve) => {
          resolver = () => resolve(new Map([["btc", { probability: 0.95, venue: "Polymarket" }]]));
        }),
    });

    const avisos: number[] = [];
    conReferencia.subscribe?.(() => avisos.push(1));

    // el feed no espera a la casa externa: los mercados no dependen de ella
    const inicio = Date.now();
    const [sinEdge] = await conReferencia.listMarkets();
    expect(Date.now() - inicio).toBeLessThan(1_000);
    expect(sinEdge.edge).toBeNull();

    // cuando la lectura llega, avisa para repintar y ahí sí aparece el Edge
    resolver!();
    await waitFor(() => expect(avisos).toHaveLength(1));
    const [conEdge] = await conReferencia.listMarkets();
    expect(conEdge.edge).not.toBeNull();
  });

  it("V44 el pago se acredita al saldo una sola vez, aunque se recargue el portafolio", async () => {
    const user = userEvent.setup();
    let estados: SettlementState[] = [];
    const adapter = adapterConLiquidacion(() => estados);

    const app = renderApp({
      engine: "parimutuel_points",
      marketDataAdapter: adapter,
    });

    await user.click(
      await screen.findByTestId("onboarding-start", {}, { timeout: SPLASH_MAX_MS + 2000 }),
    );
    await screen.findByTestId("home-screen");

    await user.click(
      within((await screen.findAllByTestId("market-card"))[0]).getByTestId("card-open"),
    );
    await user.click(await screen.findByTestId("detail-trade-cta"));
    await screen.findByTestId("post-trade");
    await waitFor(() =>
      expect(screen.getByTestId("header-balance")).toHaveTextContent(
        `${WELCOME_GRANT - 100} pts`,
      ),
    );

    // el liquidador publica el resultado mientras la app está abierta
    estados = [pagado("si")];
    await user.click(screen.getByTestId("post-trade-portfolio"));

    // al resolver a favor, la app avisa al volver con la lectura que lo
    // justifica. Se cierra para seguir: el aviso es modal a propósito, porque
    // cobrar es uno de los dos momentos que importan (UX3)
    const aviso = await screen.findByTestId("liquidacion-aviso");
    expect(within(aviso).getByTestId("liquidacion-evidencia")).toHaveTextContent(
      EVIDENCIA,
    );
    await user.click(screen.getByTestId("liquidacion-cerrar"));

    const fila = (await screen.findAllByTestId("position-row"))[0];
    expect(within(fila).getByTestId("position-outcome")).toHaveTextContent(
      S.portfolio.won,
    );
    expect(within(fila).getByTestId("position-evidence")).toHaveTextContent(EVIDENCIA);

    const saldo = () => screen.getByTestId("header-balance").textContent;
    await waitFor(() => expect(saldo()).not.toBe(`${WELCOME_GRANT - 100} pts`));
    const acreditado = saldo();

    // volver a entrar al portafolio no vuelve a pagar
    await user.click(screen.getByRole("tab", { name: S.tabs.markets }));
    await user.click(screen.getByRole("tab", { name: S.tabs.portfolio }));
    await screen.findAllByTestId("position-row");
    await waitFor(() => expect(saldo()).toBe(acreditado));
    expect(app.eventNames().filter((name) => name === "market_settled")).toHaveLength(1);
  });
});
