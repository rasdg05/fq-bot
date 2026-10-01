import type { Oracle, OracleQuery, OracleReading } from "@/domain/settlement";
import type { MirrorRule } from "@/domain/oracleRule";

/**
 * Oráculo **espejo**: resuelve un mercado nuestro con la liquidación pública de
 * su gemelo en Kalshi, una bolsa regulada por la CFTC.
 *
 * Verificable a mano desde el navegador, sin llave:
 * https://api.elections.kalshi.com/trade-api/v2/markets/CONTROLH-2026-D
 *
 * El ciclo de vida que publica Kalshi, medido el 2026-10-01 sobre 400 mercados:
 *
 *   active → closed (result "") → determined (result yes/no) → finalized
 *
 * Tres reglas, de la más importante a la menos:
 *
 *  1. **Sólo se paga con `finalized`.** `determined` ya tiene resultado pero
 *     está en su temporizador de liquidación; `finalized` es cuando Kalshi ya
 *     pagó. Pagar antes sería adelantarse a la fuente que citamos.
 *  2. **Se deja de aceptar apuestas en cuanto la fuente deja de operar**: un
 *     ganador `determined`/`finalized`, o todas las patas cerradas. Entre eso y
 *     el pago el resultado ya circula (R-023: no se apuesta sobre lo ocurrido).
 *  3. **Nada se adivina.** Un resultado vacío, `void` o que no encaja con
 *     ninguna respuesta es `sin_dato`; si nunca llega, el plazo de anulación
 *     devuelve lo apostado íntegro.
 */

export const KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2";

/** Lo que leemos de un mercado de Kalshi. */
export interface EstadoKalshi {
  ticker: string;
  status: string;
  result?: string;
  /** Cuándo se liquidó, en ISO. Es la fecha del dato, no de la consulta (L8). */
  settlement_ts?: string;
  yes_bid_dollars?: string | number | null;
  yes_ask_dollars?: string | number | null;
  last_price_dollars?: string | number | null;
}

export function urlMercadoKalshi(ticker: string): string {
  return `${KALSHI_API}/markets/${encodeURIComponent(ticker)}`;
}

export async function cargarMercadoKalshi(
  fetchImpl: typeof fetch,
  ticker: string,
): Promise<EstadoKalshi> {
  const respuesta = await fetchImpl(urlMercadoKalshi(ticker));
  if (!respuesta.ok) throw new Error(`Kalshi respondió ${respuesta.status} para ${ticker}`);
  const cuerpo = (await respuesta.json()) as { market?: EstadoKalshi };
  if (!cuerpo.market) throw new Error(`Kalshi no devolvió el mercado ${ticker}`);
  return cuerpo.market;
}

export function urlEventoKalshi(evento: string): string {
  return `${KALSHI_API}/events/${encodeURIComponent(evento)}?with_nested_markets=true`;
}

/**
 * Todos los mercados de un evento en **un** pedido. Un espejo de Banxico tiene
 * siete tickers; pedirlos uno a uno multiplicaba las llamadas y Kalshi empezó a
 * limitar la tasa (medido: 3 de 9 espejos fallaban en una misma vuelta). La
 * respuesta correcta a un límite de tasa es pedir menos, no reintentar más.
 */
export async function cargarEventoKalshi(
  fetchImpl: typeof fetch,
  evento: string,
): Promise<EstadoKalshi[]> {
  const respuesta = await fetchImpl(urlEventoKalshi(evento));
  if (!respuesta.ok) throw new Error(`Kalshi respondió ${respuesta.status} para ${evento}`);
  const cuerpo = (await respuesta.json()) as {
    event?: { markets?: EstadoKalshi[] };
    markets?: EstadoKalshi[];
  };
  const mercados = cuerpo.event?.markets ?? cuerpo.markets ?? [];
  if (mercados.length === 0) throw new Error(`Kalshi no devolvió mercados para ${evento}`);
  return mercados;
}

const DETENIDO = new Set(["closed", "determined", "finalized", "settled"]);
const CON_RESULTADO = new Set(["determined", "finalized", "settled"]);

function resultadoDe(mercado: EstadoKalshi | undefined): "yes" | "no" | undefined {
  const r = mercado?.result?.toLowerCase();
  return r === "yes" || r === "no" ? r : undefined;
}

/**
 * La decisión, sin red: dado el estado de cada ticker, qué responde el oráculo.
 * Exportada para probar cada caso con datos fijos.
 */
export function resolverEspejo(
  rule: MirrorRule,
  mercados: ReadonlyMap<string, EstadoKalshi>,
): OracleReading {
  const tickers = [...new Set(rule.respuestas.flatMap((r) => r.tickers))];
  const faltan = tickers.filter((t) => !mercados.has(t));
  if (faltan.length > 0) {
    return { status: "sin_dato", evidence: `Kalshi no devolvió ${faltan.join(", ")}.` };
  }

  const finalizado = (t: string) => {
    const m = mercados.get(t)!;
    return m.status === "finalized" || m.status === "settled";
  };
  const fuente = `Kalshi, evento ${rule.evento}`;

  // 1. ¿alguna respuesta ganó ya, con liquidación final?
  for (const respuesta of rule.respuestas) {
    const esperado = respuesta.resultado ?? "yes";
    const ganador = respuesta.tickers.find(
      (t) => finalizado(t) && resultadoDe(mercados.get(t)) === esperado,
    );
    if (ganador) {
      const m = mercados.get(ganador)!;
      return {
        status: "resuelto",
        outcome: respuesta.id,
        evidence: `${fuente}: el mercado ${ganador} se liquidó en «${esperado}»${
          m.settlement_ts ? ` el ${m.settlement_ts.slice(0, 10)}` : ""
        }. Verificable en ${urlMercadoKalshi(ganador)}`,
        ...(m.settlement_ts ? { observedAt: m.settlement_ts } : {}),
        // liquidado en firme por la bolsa: no envejece
        definitivo: true,
      };
    }
  }

  // 2. «ninguno de los anteriores»: todo liquidado y nadie ganó
  const ninguna = rule.respuestas.find((r) => r.tickers.length === 0);
  const todosFinal = tickers.length > 0 && tickers.every(finalizado);
  if (ninguna && todosFinal) {
    const ultimo = tickers
      .map((t) => mercados.get(t)!.settlement_ts)
      .filter(Boolean)
      .sort()
      .at(-1);
    return {
      status: "resuelto",
      outcome: ninguna.id,
      evidence: `${fuente}: los ${tickers.length} mercados se liquidaron y ninguno de los nombrados ganó.`,
      ...(ultimo ? { observedAt: ultimo } : {}),
      definitivo: true,
    };
  }

  // 3. todavía no se paga — pero ¿hay que dejar de aceptar apuestas?
  const hayGanadorConocido = rule.respuestas.some((respuesta) =>
    respuesta.tickers.some((t) => {
      const m = mercados.get(t)!;
      return CON_RESULTADO.has(m.status) && resultadoDe(m) === (respuesta.resultado ?? "yes");
    }),
  );
  const todoDetenido = tickers.every((t) => DETENIDO.has(mercados.get(t)!.status));
  if (hayGanadorConocido || todoDetenido) {
    return {
      status: "sin_dato",
      detenerApuestas: true,
      evidence: hayGanadorConocido
        ? `${fuente}: el resultado ya se conoce y espera su liquidación final. Se dejan de aceptar apuestas.`
        : `${fuente}: Kalshi cerró la operación de todas sus patas. Se dejan de aceptar apuestas hasta su liquidación.`,
    };
  }
  if (todosFinal) {
    // liquidado sin ganador reconocible (void, o un resultado fuera de la
    // pregunta): no se adivina; si no se aclara, el plazo devuelve todo
    return {
      status: "sin_dato",
      detenerApuestas: true,
      evidence: `${fuente}: liquidado sin un ganador que corresponda a esta pregunta. Si no se aclara, se anula y se devuelve todo.`,
    };
  }
  return { status: "sin_dato", evidence: `${fuente}: el evento sigue abierto.` };
}

export interface MirrorOracleOptions {
  fetchImpl?: typeof fetch;
  /** Se inyecta en pruebas para no depender de la red. Devuelve los mercados del evento. */
  cargarEventoKalshi?: (evento: string) => Promise<EstadoKalshi[]>;
}

export function createMirrorOracle(options: MirrorOracleOptions = {}): Oracle {
  const cargar =
    options.cargarEventoKalshi ??
    ((evento: string) => cargarEventoKalshi(options.fetchImpl ?? fetch, evento));

  return {
    id: "kalshi-espejo",

    handles(query: OracleQuery): boolean {
      return query.rule?.kind === "espejo";
    },

    async read(query: OracleQuery): Promise<OracleReading> {
      const rule = query.rule as MirrorRule;
      let lista: EstadoKalshi[];
      try {
        lista = await cargar(rule.evento);
      } catch (error) {
        // una fuente caída no resuelve ni detiene: se reintenta en la próxima
        return {
          status: "sin_dato",
          evidence: `Kalshi, evento ${rule.evento}: ${error instanceof Error ? error.message : String(error)}`,
        };
      }
      return resolverEspejo(rule, new Map(lista.map((m) => [m.ticker, m])));
    },
  };
}
