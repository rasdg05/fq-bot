import type { Oracle, OracleQuery, OracleReading } from "@/domain/settlement";
import type { TrendRule } from "@/domain/oracleRule";

/**
 * Oráculo de tendencias: visitas diarias de Wikipedia en español, de la API
 * pública de Wikimedia. Verificable a mano desde el navegador:
 * https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/es.wikipedia/all-access/user/Diego_Luna/daily/20260929/20260930
 *
 * Medido el 2026-10-01:
 *  - El día D se publica horas después de terminar: a las 02:20 UTC del 1 de
 *    octubre la API todavía no tenía el 30 de septiembre. Por eso no se lee
 *    hasta una hora después de medianoche y, si falta, se reintenta.
 *  - Wikimedia limita a los agentes genéricos: con un User-Agent que decía
 *    «node-fetch» el primer pedido ya volvía «too many requests». Con uno que
 *    identifica al proyecto, no.
 */

export const WIKIMEDIA_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews";

/** Cómo nos presentamos a Wikimedia: su política pide un agente identificable. */
export const WIKIMEDIA_UA = "Marea/1.0 (https://github.com/rasdg05/fq-bot; mercados de prediccion)";

const compacta = (iso: string) => iso.replace(/-/g, "");

/** El día anterior, `YYYY-MM-DD`. */
export function diaAntes(iso: string): string {
  return new Date(Date.parse(`${iso}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10);
}

export function urlVisitas(titulo: string, desde: string, hasta: string): string {
  return (
    `${WIKIMEDIA_API}/per-article/es.wikipedia/all-access/user/` +
    `${encodeURIComponent(titulo)}/daily/${compacta(desde)}/${compacta(hasta)}`
  );
}

/** Visitas por día (`YYYY-MM-DD` → visitas). Un día sin visitas no viene. */
export async function cargarVisitas(
  fetchImpl: typeof fetch,
  titulo: string,
  desde: string,
  hasta: string,
): Promise<Map<string, number>> {
  const respuesta = await fetchImpl(urlVisitas(titulo, desde, hasta), {
    headers: { "User-Agent": WIKIMEDIA_UA },
  });
  // 404 es «no hay datos para esas fechas»: o no se publicaron, o cero visitas
  if (respuesta.status === 404) return new Map();
  if (!respuesta.ok) throw new Error(`Wikimedia respondió ${respuesta.status}`);
  const cuerpo = (await respuesta.json()) as { items?: { timestamp: string; views: number }[] };
  const dias = new Map<string, number>();
  for (const item of cuerpo.items ?? []) {
    const t = item.timestamp;
    dias.set(`${t.slice(0, 4)}-${t.slice(4, 6)}-${t.slice(6, 8)}`, Number(item.views));
  }
  return dias;
}

const legible = (titulo: string) => titulo.replace(/_/g, " ");
const cifra = (n: number) => n.toLocaleString("es-MX");

/** La decisión, sin red. Exportada para probar cada caso. */
export function resolverTendencia(
  rule: TrendRule,
  visitas: [Map<string, number>, Map<string, number>],
): OracleReading {
  const [a, b] = rule.articulos;
  const [va, vb] = visitas;
  // ¿está publicado el día? Lo dice que al menos uno de los dos lo tenga
  if (!va.has(rule.fecha) && !vb.has(rule.fecha)) {
    return {
      status: "sin_dato",
      evidence: `Wikimedia todavía no publica las visitas del ${rule.fecha}.`,
    };
  }
  const hoyA = va.get(rule.fecha) ?? 0;
  const hoyB = vb.get(rule.fecha) ?? 0;
  const resumen =
    `${legible(a.titulo)}: ${cifra(hoyA)} visitas; ${legible(b.titulo)}: ${cifra(hoyB)} ` +
    `(Wikipedia en español, ${rule.fecha}, agente user). Verificable en ${urlVisitas(a.titulo, rule.fecha, rule.fecha)}`;
  // el dato es del final de ese día, no de cuándo se consultó (L8)
  const observedAt = new Date(Date.parse(`${rule.fecha}T23:59:59Z`)).toISOString();

  if (hoyA !== hoyB) {
    return { status: "resuelto", outcome: hoyA > hoyB ? a.id : b.id, evidence: resumen, observedAt, definitivo: true };
  }
  const ayer = diaAntes(rule.fecha);
  const ayerA = va.get(ayer) ?? 0;
  const ayerB = vb.get(ayer) ?? 0;
  if (ayerA !== ayerB) {
    return {
      status: "resuelto",
      outcome: ayerA > ayerB ? a.id : b.id,
      evidence: `${resumen}. Empate exacto: decide el día anterior (${cifra(ayerA)} contra ${cifra(ayerB)}).`,
      observedAt,
      definitivo: true,
    };
  }
  // doble empate: no se adivina; el plazo anula y devuelve
  return { status: "sin_dato", evidence: `${resumen}. Empate exacto también el día anterior.` };
}

export interface TrendOracleOptions {
  fetchImpl?: typeof fetch;
  /** Se inyecta en pruebas para no depender de la red. */
  cargarVisitas?: (titulo: string, desde: string, hasta: string) => Promise<Map<string, number>>;
}

/** Una hora de gracia tras la medianoche UTC: antes, el día no puede estar. */
const GRACIA_MS = 60 * 60_000;

export function createTrendOracle(options: TrendOracleOptions = {}): Oracle {
  const cargar =
    options.cargarVisitas ??
    ((titulo: string, desde: string, hasta: string) =>
      cargarVisitas(options.fetchImpl ?? fetch, titulo, desde, hasta));

  return {
    id: "wikimedia-tendencia",

    handles(query: OracleQuery): boolean {
      return query.rule?.kind === "tendencia";
    },

    async read(query: OracleQuery): Promise<OracleReading> {
      const rule = query.rule as TrendRule;
      const finDelDia = Date.parse(`${rule.fecha}T00:00:00Z`) + 86_400_000;
      if (query.now < finDelDia + GRACIA_MS) {
        return { status: "sin_dato", evidence: `El ${rule.fecha} todavía no termina en UTC.` };
      }
      const desde = diaAntes(rule.fecha);
      try {
        // uno detrás del otro: Wikimedia castiga las ráfagas
        const va = await cargar(rule.articulos[0].titulo, desde, rule.fecha);
        const vb = await cargar(rule.articulos[1].titulo, desde, rule.fecha);
        return resolverTendencia(rule, [va, vb]);
      } catch (error) {
        return {
          status: "sin_dato",
          evidence: `Wikimedia: ${error instanceof Error ? error.message : String(error)}`,
        };
      }
    },
  };
}
