import { CONFIG } from "@/lib/config";
import { createMockMarketDataAdapter } from "./marketDataAdapter";
import { createMockWalletAdapter } from "./walletAdapter";
import {
  createInjectedWalletAdapter,
  hasInjectedWallet,
} from "./wallet/injectedWallet";
import { createMemoryAnalytics, safeAnalytics } from "./analyticsAdapter";
import { createMemoryErrorReporter, safeErrorReporter } from "./errorReporter";
import { createHttpAnalytics } from "./analytics/httpAnalytics";
import { createHttpErrorReporter } from "./errors/httpErrorReporter";
import { createAggregatedMarketDataAdapter } from "./aggregatedMarketDataAdapter";
import { createPolymarketAdapter } from "./venues/polymarket";
import { createKalshiAdapter } from "./venues/kalshi";
import { createConsensusProvider } from "@/domain/probability";
import {
  createOwnMarketsAdapter,
  referenceFromVenues,
} from "./ownMarkets/ownMarketsAdapter";
import {
  loadPublishedSeeds,
  loadPublishedSettlements,
} from "./ownMarkets/published";
import { FLAGS, isOwnMarketMode } from "@/lib/flags";
import type { Adapters } from "@/state/store";

/**
 * Resolución de adapters según configuración. Cada integración sin configurar
 * cae en su versión simulada — nunca en una que finja hablar con un proveedor.
 */
export function resolveAdapters(): Adapters {
  const errors = CONFIG.errorEndpoint
    ? createHttpErrorReporter({
        endpoint: CONFIG.errorEndpoint,
        apiKey: CONFIG.errorKey,
        release: CONFIG.release,
      })
    : createMemoryErrorReporter();

  const analytics = CONFIG.analyticsEndpoint
    ? createHttpAnalytics({
        endpoint: CONFIG.analyticsEndpoint,
        apiKey: CONFIG.analyticsKey,
        release: CONFIG.release,
        sampleRate: CONFIG.analyticsSampleRate,
      })
    : createMemoryAnalytics();

  /**
   * Referencia externa: el precio de la misma pregunta en una casa global. Es
   * la única fuente de Edge (R-038). Si el venue no responde, no hay Edge —
   * nunca un número viejo presentado como fresco.
   */
  const loadReference = async () => {
    const venues = [
      createPolymarketAdapter({ limit: 200 }),
      createKalshiAdapter({ seriesTickers: CONFIG.kalshiSeries }),
    ];
    const settled = await Promise.allSettled(venues.map((v) => v.listMarkets()));
    const quotes = settled.flatMap((r) => (r.status === "fulfilled" ? r.value : []));
    return referenceFromVenues(quotes);
  };

  const marketData = isOwnMarketMode(FLAGS)
    ? // mercados propios de Latam: Marea crea la pregunta y corre el pozo
      createOwnMarketsAdapter({
        loadReference,
        // los mercados que se reponen solos y las resoluciones del liquidador:
        // los dos son archivos publicados por el proceso que corre a diario
        loadSeeds: () =>
          loadPublishedSeeds({
            onRejected: (id, reason) =>
              errors.report({
                code: "E_MARKETS_FETCH_FAILED",
                user_message_es: "No pudimos cargar los mercados. Revisa tu conexión.",
                retryable: true,
                context: { kind: "catalogo", id, reason },
              }),
          }),
        loadSettlements: () => loadPublishedSettlements({}),
        onReferenceError: (error) =>
          errors.report({
            code: "E_MARKETS_FETCH_FAILED",
            user_message_es: "No pudimos cargar los mercados. Revisa tu conexión.",
            retryable: true,
            context: { kind: "referencia", cause: String(error) },
          }),
      })
    : CONFIG.dataSource === "aggregated"
      ? createAggregatedMarketDataAdapter({
          venues: [
            createPolymarketAdapter({ limit: 200 }),
            createKalshiAdapter({ seriesTickers: CONFIG.kalshiSeries }),
          ],
          probability: createConsensusProvider(),
          onVenueError: (id, error) =>
            errors.report({
              code: "E_MARKETS_FETCH_FAILED",
              user_message_es: "No pudimos cargar los mercados. Revisa tu conexión.",
              retryable: true,
              context: { id, cause: String(error) },
            }),
        })
      : createMockMarketDataAdapter();

  /**
   * Wallet: si el dispositivo trae una (MetaMask y compañía), se conecta de
   * verdad — ese camino no necesita contrato con nadie porque la custodia es
   * del usuario. La wallet embebida sí lo necesita, y mientras no exista, el
   * camino simulado es el único honesto (R-022).
   */
  const wallet = hasInjectedWallet()
    ? createInjectedWalletAdapter()
    : createMockWalletAdapter();

  return {
    marketData,
    wallet,
    analytics: safeAnalytics(analytics),
    errors: safeErrorReporter(errors),
  };
}
