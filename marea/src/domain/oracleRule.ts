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
  /**
   * Qué vela se lee, en minutos. Sin esto se lee la diaria (1440), que es lo
   * que resolvía todo el catálogo antes de que existieran los mercados de 5 y
   * 15 minutos. Kraken publica 1, 5, 15, 30, 60, 240, 1440 — y el número entra
   * tal cual en la URL que se cita.
   */
  intervaloMin?: number;
  /**
   * Apertura exacta de la vela que resuelve, en ISO. Es lo que ata el mercado a
   * **una** vela y no a "la última": en intradía hay una nueva cada cinco
   * minutos, y "la última" sería una pregunta distinta cada vez que se lee.
   */
  ventanaInicio?: string;
}

/**
 * Serie estadística publicada por un banco central o un instituto. Es lo que
 * permite resolver un mercado de inflación o de tasa **sin que nadie lea un
 * PDF**: el dato existe en un endpoint, con fecha y con valor.
 */
export interface SeriesRule {
  kind: "serie";
  /**
   * Quién publica. Cada fuente tiene su lector en `seriesOracle`.
   *
   * `bcb`, `bcra`, `bcrp`, `mindicador` (Chile) y `datosgov` (Colombia) son
   * públicas y sin llave. `banxico` e `inegi` dan token gratis: sin él el
   * mercado lo declara en vez de inventar un número (R-022).
   */
  fuente:
    | "bcb"
    | "banxico"
    | "bcra"
    | "bcrp"
    | "inegi"
    | "mindicador"
    | "datosgov";
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
  /**
   * Cuántos días puede tener el dato más reciente y seguir resolviendo el
   * mercado. Por omisión día y medio, que es lo que tarda en publicarse una
   * serie diaria.
   *
   * Una serie **mensual** necesita declarar el suyo: el Imacec de mayo se
   * publica a principios de julio y viene fechado al 1 de mayo, así que con el
   * margen de una serie diaria nunca resolvería. Se declara por mercado y a la
   * vista — aflojar el margen global habría dejado que un dato viejo resolviera
   * cualquier mercado (R-052).
   */
  frescuraDias?: number;
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

/**
 * Partido con más de dos respuestas. Es la forma natural de preguntar por un
 * partido —gana, empata o pierde— y la que la gente usa en la quiniela; que
 * hasta ahora se plegara a sí/no era una limitación nuestra, no de la pregunta.
 *
 * Se lee de la misma fuente que `MatchRule`: ESPN publica el marcador final, y
 * de un marcador salen tanto el 1X2 como los goles totales.
 */
export interface MatchOutcomeRule {
  kind: "partido_multiple";
  liga: "mex.1";
  /** Día del partido en UTC, `YYYY-MM-DD`. */
  fecha: string;
  /** Equipo desde cuya perspectiva se lee el resultado. */
  equipo: string;
  /**
   * `1x2`: resuelve `gana` | `empata` | `pierde`.
   * `goles`: resuelve por tramos de goles totales, según `cortes`.
   */
  mercado: "1x2" | "goles";
  /**
   * Cortes de los tramos de goles, ascendentes. `[2, 4]` produce tres tramos:
   * `0-1`, `2-3` y `4+`, con los ids `goles_0_1`, `goles_2_3` y `goles_4_mas`.
   */
  cortes?: number[];
}

/** Los ids que produce una regla de tramos de goles, en orden. */
export function idsDeTramos(cortes: number[]): { id: string; label: string }[] {
  const tramos: { id: string; label: string }[] = [];
  let desde = 0;
  for (const corte of cortes) {
    tramos.push({
      id: `goles_${desde}_${corte - 1}`,
      label: desde === corte - 1 ? `${desde} goles` : `${desde}-${corte - 1} goles`,
    });
    desde = corte;
  }
  tramos.push({ id: `goles_${desde}_mas`, label: `${desde} o más goles` });
  return tramos;
}

/** Los tres ids del 1X2, desde la perspectiva del equipo de la pregunta. */
export const IDS_1X2 = ["gana", "empata", "pierde"] as const;

export type OracleRule = PriceRule | SeriesRule | MatchRule | MatchOutcomeRule;

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

  if (rule.kind === "partido_multiple") {
    if (!new RegExp(rule.equipo.split(" ")[0], "i").test(criterion)) {
      problems.push(`el criterio no menciona a ${rule.equipo}`);
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(rule.fecha)) {
      problems.push("la fecha del partido tiene que ser YYYY-MM-DD");
    }
    if (rule.mercado === "goles") {
      if (!rule.cortes || rule.cortes.length === 0) {
        problems.push("una regla de goles necesita sus cortes");
      } else {
        const ordenados = [...rule.cortes].every(
          (corte, i, todos) => i === 0 || todos[i - 1] < corte,
        );
        if (!ordenados) problems.push("los cortes de goles tienen que ir de menor a mayor");
        // cada tramo publicado tiene que aparecer en el criterio, o el mercado
        // pagaría por unos tramos y habría prometido otros (R-042)
        for (const corte of rule.cortes) {
          if (!umbralEnTexto(corte).test(criterion)) {
            problems.push(`el corte de goles ${corte} no aparece en el criterio publicado`);
          }
        }
      }
    }
    return problems;
  }

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
