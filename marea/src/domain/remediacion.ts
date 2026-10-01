import type { OracleRule } from "./oracleRule";
import type { SettlementState } from "./settlement";
import type { Hallazgo } from "./revisor";

/**
 * El manual de remediación del director: qué hace **solo y en el momento** con
 * cada cosa que el revisor encuentra (MEMORY/FILOSOFIA.md; R-085).
 *
 * El revisor ve; el director actúa. Auditar sin poder corregir dejaba trece
 * partidos atorados esperando a que alguien leyera un panel. Cada acción de
 * aquí es determinista —ninguna la decide un modelo— y cabe en una de tres:
 *
 * | Acción | Cuándo | Mueve dinero |
 * |---|---|---|
 * | `actuar` | se pasó su cierre, o está sin resolver/atorado: se vuelve a leer la fuente **ya**, con los mismos oráculos, y si hay resultado sigue el camino normal (disputa, pago) | sólo por el camino normal |
 * | `anular` | el evento demostrablemente no se va a resolver: devolución íntegra **ya**, no a los 30 días | devuelve todo; nadie gana |
 * | `retener` | el resultado contradice al mercado | no |
 *
 * Lo que nunca hace: elegir un ganador, pagar distinto de lo que dice la
 * fuente, o anular algo que todavía puede resolverse.
 */

/** Cada cuánto, como mínimo, se vuelve a intentar un mismo mercado. */
export const REINTENTO_MS = 5 * 60_000;

const H = 3_600_000;

/** Lo que el director necesita saber de un mercado para decidir. */
export interface MercadoParaRemediar {
  id: string;
  closesAt: string;
  rule?: OracleRule;
  estado?: SettlementState;
}

const POR_DEFINIR = /^(tbd|tba|por definir)$|^(winner|loser|ganador|perdedor)\b/i;

/**
 * Si este mercado ya no puede resolverse, el motivo; si todavía puede, nada.
 * Sólo partidos y tenis, con reglas que se pueden leer en su criterio:
 *
 *  - **rival por definir** («TBD vs TBD») y ya pasó su hora: no hay a quién
 *    pagar, ni lo habrá;
 *  - **no se jugó en su fecha**: pasó la ventana —72 h sin cláusula de
 *    reprogramación; su cláusula + 24 h si la tiene (R-084)— y la última
 *    lectura sigue diciendo que la fuente no lo lista, que está pospuesto o que
 *    no ha terminado.
 */
export function irresoluble(m: MercadoParaRemediar, ahora: number): string | undefined {
  const rule = m.rule;
  const e = m.estado;
  if (!rule || (rule.kind !== "partido" && rule.kind !== "partido_multiple" && rule.kind !== "tenis")) return undefined;
  if (e && (e.phase === "en_disputa" || e.phase === "pagado" || e.phase === "devuelto" || e.retenidoPor)) return undefined;

  const inicio = Date.parse(("inicio" in rule && rule.inicio) || m.closesAt);
  if (!Number.isFinite(inicio) || ahora < inicio) return undefined;

  const nombres =
    rule.kind === "tenis" ? [rule.jugador, rule.rival] : [rule.equipo, "rival" in rule ? rule.rival : undefined];
  if (nombres.some((n) => n !== undefined && POR_DEFINIR.test(n.trim()))) {
    return "El partido no tiene rival definido: no hay a quién pagar.";
  }

  const clausula = "reprogramacionDias" in rule ? rule.reprogramacionDias : undefined;
  const ventana = clausula ? (clausula + 1) * 24 * H : 72 * H;
  const sinJugarse = /no lista (el )?partido|pospuesto|no ha terminado/i.test(e?.evidence ?? "");
  if (ahora > inicio + ventana && sinJugarse) {
    return clausula
      ? `No se jugó en su fecha ni dentro de los ${clausula} días de reprogramación que prometía su criterio.`
      : "No se jugó en su fecha y su criterio no prometía reprogramación.";
  }
  return undefined;
}

/** Los hallazgos sobre los que el director actúa en vivo. */
const ACCIONABLES = new Set(["sin_leer", "atorado", "abierto_tras_cierre"]);

/**
 * De los hallazgos abiertos, qué mercados se intentan ahora. Respeta el
 * reintento mínimo por mercado y un tope por vuelta, para no martillar a una
 * fuente caída.
 */
export function porActuar(
  hallazgos: readonly Hallazgo[],
  ultimoIntento: ReadonlyMap<string, number>,
  ahora: number,
  tope = 20,
): string[] {
  const ids: string[] = [];
  for (const h of hallazgos) {
    if (!ACCIONABLES.has(h.codigo)) continue;
    const previo = ultimoIntento.get(h.sujeto);
    if (previo !== undefined && ahora - previo < REINTENTO_MS) continue;
    if (!ids.includes(h.sujeto)) ids.push(h.sujeto);
    if (ids.length >= tope) break;
  }
  return ids;
}
