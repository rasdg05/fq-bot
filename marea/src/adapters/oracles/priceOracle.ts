import type { Oracle, OracleQuery, OracleReading } from "@/domain/settlement";
import type { PriceRule } from "@/domain/oracleRule";
import { createSeriesOracle, type SeriesOracleOptions } from "./seriesOracle";
import { createMatchOracle, type MatchOracleOptions } from "./matchOracle";

/**
 * Oráculo de precio contra Kraken, que publica velas históricas sin llave y sin
 * bloqueo geográfico. Es la fuente que **sí** se puede leer por programa, y por
 * eso es la que citamos: citar Binance y leer Kraken sería resolver con una
 * fuente distinta de la prometida.
 *
 * Endpoint público, verificable a mano desde el navegador:
 * https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440
 *
 * Cada vela es `[inicio, apertura, máximo, mínimo, cierre, vwap, volumen, n]`,
 * con `inicio` en segundos UTC. Una vela diaria cierra 24 h después de empezar:
 * mientras no haya cerrado, no hay dato y no se resuelve nada.
 */

const DIA_MS = 86_400_000;

const PARES: Record<PriceRule["par"], string> = {
  "BTC/USD": "XBTUSD",
  "ETH/USD": "ETHUSD",
};

type Candle = { inicio: number; alto: number; bajo: number; cierre: number };

export interface PriceOracleOptions {
  fetchImpl?: typeof fetch;
  /** Se inyecta en pruebas para no depender de la red. */
  loadCandles?: (par: PriceRule["par"], desde: number) => Promise<Candle[]>;
}

async function fetchCandles(
  fetchImpl: typeof fetch,
  par: PriceRule["par"],
  desde: number,
): Promise<Candle[]> {
  const url = `https://api.kraken.com/0/public/OHLC?pair=${PARES[par]}&interval=1440&since=${Math.floor(
    desde / 1000,
  )}`;
  const response = await fetchImpl(url);
  if (!response.ok) throw new Error(`Kraken respondió ${response.status}`);
  const body = (await response.json()) as {
    error?: string[];
    result?: Record<string, unknown>;
  };
  if (body.error?.length) throw new Error(body.error.join("; "));
  const series = Object.entries(body.result ?? {}).find(([key]) => key !== "last");
  if (!series) throw new Error("Kraken no devolvió velas");
  return (series[1] as unknown[][]).map((row) => ({
    inicio: Number(row[0]) * 1000,
    alto: Number(row[2]),
    bajo: Number(row[3]),
    cierre: Number(row[4]),
  }));
}

function fecha(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

function monto(valor: number): string {
  return valor.toLocaleString("es-MX", { maximumFractionDigits: 2 });
}

export function createPriceOracle(options: PriceOracleOptions = {}): Oracle {
  const load =
    options.loadCandles ??
    ((par: PriceRule["par"], desde: number) =>
      fetchCandles(options.fetchImpl ?? fetch, par, desde));

  return {
    id: "kraken-ohlc",

    handles(query: OracleQuery): boolean {
      return query.rule?.kind === "precio" && query.rule.par in PARES;
    },

    async read(query: OracleQuery): Promise<OracleReading> {
      const rule = query.rule as PriceRule;
      const settlesAt = new Date(query.spec.settlesAt).getTime();
      const arriba = rule.comparacion === "arriba";

      // Un mercado de cierre no se puede leer antes de su fecha. Uno de toque
      // sí: en cuanto el precio llega, el resultado ya existe y esperar sería
      // dejar apostar sobre algo que ya pasó.
      if (rule.modo === "cierre" && query.now < settlesAt) {
        return {
          status: "sin_dato",
          evidence: `El mercado resuelve el ${fecha(settlesAt)}; todavía no hay dato.`,
        };
      }

      // se lee de velas diarias: la ventana arranca al inicio del día, o el
      // día en que empieza el mercado quedaría fuera de su propia ventana
      const inicio =
        rule.modo === "toca" && rule.desde
          ? new Date(rule.desde).getTime()
          : settlesAt - 5 * DIA_MS;
      const desde = Math.floor(inicio / DIA_MS) * DIA_MS;
      const candles = await load(rule.par, desde - DIA_MS);

      if (rule.modo === "cierre") {
        // la vela del día que resuelve, y sólo si ya cerró
        const dia = fecha(settlesAt);
        const vela = candles.find((candle) => fecha(candle.inicio) === dia);
        if (!vela || query.now < vela.inicio + DIA_MS) {
          return {
            status: "sin_dato",
            evidence: `La vela diaria de ${rule.par} del ${dia} todavía no cerró en Kraken.`,
          };
        }
        const outcome = (arriba ? vela.cierre > rule.umbral : vela.cierre < rule.umbral)
          ? "si"
          : "no";
        return {
          status: "resuelto",
          outcome,
          evidence: `Vela diaria de ${rule.par} en Kraken del ${dia}: cierre ${monto(
            vela.cierre,
          )} USD frente al umbral de ${monto(rule.umbral)}.`,
        };
      }

      // `toca`: basta con que el precio haya llegado en cualquier momento
      const hasta = Math.min(query.now, settlesAt);
      const ventana = candles.filter(
        (candle) => candle.inicio >= desde && candle.inicio < hasta,
      );
      if (ventana.length === 0) {
        return {
          status: "sin_dato",
          evidence: `Kraken no devolvió velas de ${rule.par} en la ventana del mercado.`,
        };
      }
      const extremo = arriba
        ? Math.max(...ventana.map((candle) => candle.alto))
        : Math.min(...ventana.map((candle) => candle.bajo));
      const toco = arriba ? extremo >= rule.umbral : extremo <= rule.umbral;
      const detalle = `${arriba ? "Máximo" : "Mínimo"} de ${rule.par} en Kraken entre ${fecha(
        desde,
      )} y ${fecha(hasta)}: ${monto(extremo)} USD frente al umbral de ${monto(rule.umbral)}.`;

      // si todavía no tocó y queda tiempo, el mercado sigue vivo
      if (!toco && query.now < settlesAt) {
        return { status: "sin_dato", evidence: detalle };
      }
      return { status: "resuelto", outcome: toco ? "si" : "no", evidence: detalle };
    },
  };
}

/**
 * Última red: lo que ninguna otra fuente sabe leer. Hoy son las instituciones
 * sin API estable (DANE, BCRP, Banco Central de Chile). No adivina: marca el
 * mercado para que una persona lo confirme, con la liga a la mano.
 *
 * Cada vez que una de estas fuentes abra un endpoint, su mercado se mueve al
 * oráculo de series y sale de aquí.
 */
export function createInstitutionalOracle(): Oracle {
  return {
    id: "institucional",
    handles: () => true,
    async read(query: OracleQuery): Promise<OracleReading> {
      return {
        status: "requiere_humano",
        evidence: `Confirmar en ${query.spec.sourceName}: ${query.spec.sourceUrl}`,
      };
    },
  };
}

/** El orden importa: primero los que saben leer, y el humano como red de fondo. */
export function defaultOracles(
  options: PriceOracleOptions & SeriesOracleOptions & MatchOracleOptions = {},
): Oracle[] {
  return [
    createPriceOracle(options),
    createSeriesOracle(options),
    createMatchOracle(options),
    createInstitutionalOracle(),
  ];
}
