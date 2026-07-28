/**
 * Regla legible por máquina para resolver un mercado.
 *
 * El criterio en español es lo que lee el usuario y manda sobre cualquier
 * discusión. Esta regla es la misma frase escrita para que un programa la
 * ejecute sin interpretar lenguaje natural — leer el criterio con expresiones
 * regulares sería inventar un resultado con pasos extra.
 *
 * Las dos tienen que decir lo mismo, y eso se verifica: el umbral de la regla
 * aparece en el texto del criterio o el mercado no se publica (R-042).
 */

export interface PriceRule {
  kind: "precio";
  /** Par tal como lo cotiza el exchange público. */
  par: "BTC/USD" | "ETH/USD";
  umbral: number;
  comparacion: "arriba" | "abajo";
  /**
   * `cierre`: se lee la vela del día que resuelve.
   * `toca`: basta con que el precio haya llegado en cualquier momento.
   */
  modo: "cierre" | "toca";
  /** Desde cuándo cuenta, para `toca`. */
  desde?: string;
}

/**
 * Serie estadística publicada por un banco central o un instituto. Es lo que
 * permite resolver un mercado de inflación o de tasa **sin que nadie lea un
 * PDF**: el dato existe en un endpoint, con fecha y con valor.
 */
export interface SeriesRule {
  kind: "serie";
  /** Quién publica. Cada fuente tiene su lector en `seriesOracle`. */
  fuente: "bcb" | "banxico";
  /** Identificador de la serie en esa fuente. */
  serie: string;
  /**
   * `menor`/`mayor`: contra `umbral`.
   * `baja`/`sube`: contra la observación anterior de la misma serie.
   */
  comparacion: "menor" | "mayor" | "baja" | "sube";
  umbral?: number;
  /** Cómo se llama el dato en el criterio, para la evidencia. */
  etiqueta: string;
}

/**
 * Partido de futbol. Es la categoría que de verdad se comparte en Latam, y
 * resulta que **también se puede leer por programa**: ESPN publica el marcador
 * de la Liga MX sin llave ni registro.
 */
export interface MatchRule {
  kind: "partido";
  /** Liga tal como la nombra la fuente. `mex.1` es la Liga MX. */
  liga: "mex.1";
  /** Día del partido en UTC, `YYYY-MM-DD`. */
  fecha: string;
  /** Equipo del que se pregunta, con el nombre que usa la fuente. */
  equipo: string;
  /** `gana` es victoria; `no_pierde` incluye el empate. */
  resultado: "gana" | "no_pierde";
}

export type OracleRule = PriceRule | SeriesRule | MatchRule;

/** Cómo se escribe el umbral en el texto: `71000`, `71,000`, `71.000`, `5.00`. */
function umbralEnTexto(umbral: number): RegExp {
  const entero = Math.trunc(umbral).toString();
  const conSeparador = entero.replace(/\B(?=(\d{3})+(?!\d))/g, "[.,]?");
  return new RegExp(`\\b${conSeparador}\\b`);
}

/**
 * La regla y el criterio publicado tienen que coincidir. Si alguien cambia el
 * umbral en un lado y no en el otro, el mercado paga distinto de lo que
 * prometió — que es la forma más rápida de perder la confianza que vendemos.
 */
export function ruleProblems(rule: OracleRule, criterion: string): string[] {
  const problems: string[] = [];

  if (rule.kind === "partido") {
    // el equipo tiene que aparecer en la pregunta, o el criterio publicado y
    // la regla estarían hablando de partidos distintos
    if (!new RegExp(rule.equipo.split(" ")[0], "i").test(criterion)) {
      problems.push(`el criterio no menciona a ${rule.equipo}`);
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(rule.fecha)) {
      problems.push("la fecha del partido tiene que ser YYYY-MM-DD");
    }
    return problems;
  }

  if (rule.kind === "serie") {
    const necesitaUmbral = rule.comparacion === "menor" || rule.comparacion === "mayor";
    if (necesitaUmbral && rule.umbral === undefined) {
      problems.push("una comparación contra umbral necesita el umbral");
    }
    if (necesitaUmbral && rule.umbral !== undefined) {
      if (!umbralEnTexto(rule.umbral).test(criterion)) {
        problems.push(
          `el umbral de la regla (${rule.umbral}) no aparece en el criterio publicado`,
        );
      }
    }
    if (!rule.serie.trim()) problems.push("falta el identificador de la serie");
    return problems;
  }

  if (!umbralEnTexto(rule.umbral).test(criterion)) {
    problems.push(
      `el umbral de la regla (${rule.umbral}) no aparece en el criterio publicado`,
    );
  }
  const activo = rule.par.split("/")[0];
  if (!new RegExp(activo, "i").test(criterion)) {
    problems.push(`el criterio no menciona el activo ${activo}`);
  }
  if (rule.modo === "toca" && !rule.desde) {
    problems.push("una regla de tipo `toca` necesita fecha de inicio");
  }
  return problems;
}
