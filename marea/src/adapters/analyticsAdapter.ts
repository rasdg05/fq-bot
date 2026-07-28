/**
 * Puerto de analítica. Nunca puede tumbar la UX: todo va envuelto en try/catch
 * y un sink caído se degrada a silencio (R-009).
 */
export type AnalyticsEvent =
  | "view_feed"
  | "open_market_detail"
  | "click_trade_cta"
  | "click_deposit_cta"
  | "view_onboarding_step"
  | "onboarding_completed"
  | "wallet_created"
  | "wallet_connected"
  | "deposit_started"
  | "deposit_method_selected"
  | "view_portfolio"
  | "trade_confirmed"
  | "explore_without_funds"
  | "web_vital"
  | "eligibility_blocked"
  | "market_settled"
  | "country_detected"
  | "cuenta_creada"
  | "cuenta_entrada";

export interface AnalyticsAdapter {
  track(event: AnalyticsEvent, props?: Record<string, unknown>): void;
}

export interface RecordedEvent {
  event: AnalyticsEvent;
  props?: Record<string, unknown>;
  at: number;
}

/** Sink en memoria: sirve de default seguro y de espía en las pruebas. */
export function createMemoryAnalytics(sink: RecordedEvent[] = []): AnalyticsAdapter & {
  events: RecordedEvent[];
} {
  return {
    events: sink,
    track(event, props) {
      try {
        sink.push({ event, props, at: Date.now() });
      } catch {
        /* la analítica jamás rompe la UX (R-009) */
      }
    },
  };
}

/** Envuelve cualquier sink real para que un fallo suyo no escale a la vista. */
export function safeAnalytics(inner: AnalyticsAdapter): AnalyticsAdapter {
  return {
    track(event, props) {
      try {
        inner.track(event, props);
      } catch {
        /* silencio deliberado (R-009) */
      }
    },
  };
}

export const analyticsAdapter = createMemoryAnalytics();
