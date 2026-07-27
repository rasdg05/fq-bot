import { describe, expect, it } from "vitest";
import { createHttpAnalytics, scrubProps } from "@/adapters/analytics/httpAnalytics";
import { createHttpErrorReporter, scrubContext } from "@/adapters/errors/httpErrorReporter";
import { appError } from "@/domain/errors";
import { rate, THRESHOLDS } from "@/lib/vitals";

interface Sent {
  body: string;
  keepalive: boolean;
}

function recorder(ok = true) {
  const sent: Sent[] = [];
  return {
    sent,
    transport: async (_url: string, body: string, keepalive = false) => {
      sent.push({ body, keepalive });
      return ok;
    },
    payloads: () => sent.map((entry) => JSON.parse(entry.body)),
  };
}

describe("Sink de analítica", () => {
  it("agrupa por lotes y envía una sola petición", async () => {
    const t = recorder();
    const analytics = createHttpAnalytics({
      endpoint: "https://sink.test/e",
      release: "1.0",
      batchSize: 3,
      transport: t.transport,
    });
    analytics.track("view_feed");
    analytics.track("open_market_detail", { market_id: "m1" });
    analytics.track("click_trade_cta", { side: "si" });
    await analytics.flush();

    expect(t.sent).toHaveLength(1);
    expect(t.payloads()[0].events).toHaveLength(3);
    expect(t.payloads()[0].release).toBe("1.0");
  });

  it("sólo deja salir propiedades de la lista blanca", () => {
    const clean = scrubProps({
      market_id: "m1",
      side: "si",
      // nada de esto debe salir del dispositivo (R-020)
      address: "0x7Ac4e1f0B2d93C5a4E8b19Fd0c6A2b31D5e70F84",
      size: 250,
      email: "alguien@ejemplo.mx",
      query: "inflación méxico",
    });
    expect(clean).toEqual({ market_id: "m1", side: "si" });
  });

  it("descarta una dirección aunque venga en una clave permitida", () => {
    const clean = scrubProps({ source: "0x7Ac4e1f0B2d93C5a4E8b19Fd0c6A2b31D5e70F84" });
    expect(clean).toBeUndefined();
  });

  it("devuelve el lote a la cola si el sink lo rechaza", async () => {
    const t = recorder(false);
    const analytics = createHttpAnalytics({
      endpoint: "https://sink.test/e",
      release: "1.0",
      batchSize: 2,
      transport: t.transport,
    });
    analytics.track("view_feed");
    analytics.track("view_feed");
    await analytics.flush();
    expect(analytics.queued()).toBe(2);
  });

  it("un transporte que explota no propaga la excepción", async () => {
    const analytics = createHttpAnalytics({
      endpoint: "https://sink.test/e",
      release: "1.0",
      batchSize: 1,
      transport: async () => {
        throw new Error("sink caído");
      },
    });
    expect(() => analytics.track("view_feed")).not.toThrow();
    await expect(analytics.flush()).resolves.toBeUndefined();
  });

  it("con muestreo en cero no sale nada", async () => {
    const t = recorder();
    const analytics = createHttpAnalytics({
      endpoint: "https://sink.test/e",
      release: "1.0",
      sampleRate: 0,
      batchSize: 1,
      transport: t.transport,
    });
    analytics.track("view_feed");
    await analytics.flush();
    expect(t.sent).toHaveLength(0);
  });

  it("respeta el tope de cola y descarta lo más viejo", () => {
    const analytics = createHttpAnalytics({
      endpoint: "https://sink.test/e",
      release: "1.0",
      batchSize: 1_000,
      maxQueue: 5,
      transport: async () => false,
    });
    for (let i = 0; i < 20; i += 1) analytics.track("view_feed");
    expect(analytics.queued()).toBe(5);
  });
});

describe("Reporter de errores", () => {
  it("no repite el mismo código dentro de la ventana de dedupe", () => {
    let clock = 0;
    const sent: string[] = [];
    const reporter = createHttpErrorReporter({
      endpoint: "https://sink.test/x",
      release: "1.0",
      dedupeMs: 10_000,
      now: () => clock,
      transport: async (_url, body) => {
        sent.push(body);
        return true;
      },
    });
    reporter.report(appError("E_MARKETS_FETCH_FAILED"));
    reporter.report(appError("E_MARKETS_FETCH_FAILED"));
    clock = 11_000;
    reporter.report(appError("E_MARKETS_FETCH_FAILED"));
    expect(sent).toHaveLength(2);
  });

  it("se autolimita: una tormenta no se convierte en tormenta de peticiones", () => {
    let clock = 0;
    const reporter = createHttpErrorReporter({
      endpoint: "https://sink.test/x",
      release: "1.0",
      maxPerWindow: 3,
      dedupeMs: 0,
      now: () => (clock += 1),
      transport: async () => true,
    });
    for (let i = 0; i < 50; i += 1) reporter.report(appError("E_NETWORK"));
    expect(reporter.sent()).toBe(3);
  });

  it("nunca envía el mensaje al usuario ni datos identificables", async () => {
    const sent: string[] = [];
    const reporter = createHttpErrorReporter({
      endpoint: "https://sink.test/x",
      release: "1.0",
      transport: async (_url, body) => {
        sent.push(body);
        return true;
      },
    });
    reporter.report(
      appError("E_BALANCE_FETCH_FAILED", {
        address: "0x7Ac4e1f0B2d93C5a4E8b19Fd0c6A2b31D5e70F84",
        status: 500,
        cause: "boom en línea 42",
      }),
    );
    const payload = JSON.parse(sent[0]);
    expect(payload.code).toBe("E_BALANCE_FETCH_FAILED");
    expect(payload.context).toEqual({ status: 500 });
    expect(sent[0]).not.toContain("0x7Ac4");
    expect(sent[0]).not.toContain("boom");
  });

  it("enmascara una dirección incrustada en una clave permitida", () => {
    expect(scrubContext({ url: "https://x.test/0x7Ac4e1f0B2d93C5a4E8b" })).toEqual({
      url: "https://x.test/0x…",
    });
  });

  it("un transporte caído no propaga la excepción", () => {
    const reporter = createHttpErrorReporter({
      endpoint: "https://sink.test/x",
      release: "1.0",
      transport: async () => {
        throw new Error("caído");
      },
    });
    expect(() => reporter.report(appError("E_UNKNOWN"))).not.toThrow();
  });
});

describe("Web Vitals", () => {
  it("clasifica contra los umbrales de Core Web Vitals", () => {
    expect(THRESHOLDS.LCP[0]).toBe(2_500);
    expect(THRESHOLDS.INP[0]).toBe(200);
    expect(THRESHOLDS.CLS[0]).toBe(0.1);

    expect(rate("LCP", 2_400)).toBe("good");
    expect(rate("LCP", 3_000)).toBe("needs-improvement");
    expect(rate("LCP", 5_000)).toBe("poor");
    expect(rate("CLS", 0.05)).toBe("good");
    expect(rate("INP", 190)).toBe("good");
  });
});
