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

import type { LigaId } from "./ligas";

/**
 * Pares de cripto que Marea sabe resolver. Todos cotizan en Kraken, que publica
 * velas y ticker sin llave: lo que no se puede leer de una fuente pública no se
 * lista.
 */
export const PARES_CRIPTO = ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "DOGE/USD"] as const;
export type ParCripto = (typeof PARES_CRIPTO)[number];

/** El nombre del par en la URL pública de Kraken (`pair=`). */
export const KRAKEN_PAR: Record<ParCripto, string> = {
  "BTC/USD": "XBTUSD",
  "ETH/USD": "ETHUSD",
  "SOL/USD": "SOLUSD",
  "XRP/USD": "XRPUSD",
  "DOGE/USD": "XDGUSD",
};

/**
 * Divisas de Latam contra el dólar. No cotizan en Kraken: las publica **Bitso**,
 * casa de cambio mexicana regulada (ITF), con velas públicas sin llave.
 *
 * Medido el 2026-10-01 sobre siete días de velas de Bitso: USD/MXN tiene velas
 * sin operaciones en 0.2 % (5 min) y 0 % (15 min); USD/ARS y USD/BRL, 10 % en
 * 5 min y menos de 2 % en 15. Una vela sin operaciones repite el cierre
 * anterior y empata con el strike, así que esos dos sólo van a 15 min.
 * USD/COP quedó fuera: 31 % de sus velas de 5 min no tienen ni una operación.
 */
export const PARES_DIVISA = ["USD/MXN", "USD/ARS", "USD/BRL"] as const;
export type ParDivisa = (typeof PARES_DIVISA)[number];

/** El libro de Bitso de cada par (`book=`). */
export const BITSO_LIBRO: Record<ParDivisa, string> = {
  "USD/MXN": "usd_mxn",
  "USD/ARS": "usd_ars",
  "USD/BRL": "usd_brl",
};

export function esParDivisa(par: string): par is ParDivisa {
  return (PARES_DIVISA as readonly string[]).includes(par);
}

/**
 * Kraken contesta con claves propias (`XXBTZUSD`, `XDGUSD`, `SOLUSD`…). Esto
 * devuelve el par que nombran, o nada si no es uno de los nuestros.
 */
export function parDeClaveKraken(clave: string): ParCripto | undefined {
  const limpia = clave.toUpperCase();
  if (/^(BTC|XBT|XXBT)/.test(limpia)) return "BTC/USD";
  if (/^(ETH|XETH)/.test(limpia)) return "ETH/USD";
  if (/^SOL/.test(limpia)) return "SOL/USD";
  if (/^(XRP|XXRP)/.test(limpia)) return "XRP/USD";
  if (/^(DOGE|XDG|XXDG)/.test(limpia)) return "DOGE/USD";
  return undefined;
}

/** El activo de un mercado de cripto (`BTC`, `SOL`…), leído de su regla. */
export function activoDeRegla(rule: { kind: string; par?: string } | undefined): string | undefined {
  if (!rule || (rule.kind !== "precio" && rule.kind !== "vela")) return undefined;
  // en una divisa el activo es la moneda local: los tres pares empiezan con
  // USD, y «USD» juntaría el peso, el real y el peso argentino en uno solo
  if (rule.par && esParDivisa(rule.par)) return rule.par.split("/")[1];
  return rule.par?.split("/")[0];
}

export interface PriceRule {
  kind: "precio";
  /** Par tal como lo cotiza el exchange público. */
  par: ParCripto;
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
 * Vela de 5 o 15 minutos. Es la regla de los mercados vivos de cripto: la
 * pregunta es si el cierre de **esta** vela queda arriba o abajo del strike.
 *
 * Se separa de `PriceRule` porque no es la misma lectura: aquella busca la vela
 * diaria del día que resuelve, y ésta busca una vela concreta identificada por
 * el milisegundo en que abre. Meterlas en la misma regla habría obligado al
 * oráculo a adivinar cuál de las dos cosas le están preguntando.
 *
 * `arriba` exige cierre **estrictamente mayor** que el strike. El empate exacto
 * resuelve `abajo`, y así está escrito en el criterio publicado: un caso borde
 * sin regla escrita es una discusión esperando a ocurrir.
 */
export interface VelaRule {
  kind: "vela";
  /** Cripto en Kraken, o divisa de Latam en Bitso. El par decide la fuente. */
  par: ParCripto | ParDivisa;
  /** Minutos de la vela. Sólo los que Kraken publica nativamente. */
  intervalo: 5 | 15;
  /** Apertura de la vela, en ms UTC. Alineada al reloj por construcción. */
  inicio: number;
  /** Precio de referencia, ya redondeado a un número que se dice en voz alta. */
  strike: number;
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
  /** Liga tal como la nombra la fuente. `mex.1` es la Liga MX (ver `ligas.ts`). */
  liga: LigaId;
  /** Día del partido en UTC, `YYYY-MM-DD`. */
  fecha: string;
  /**
   * Arranque exacto, en ISO. ESPN agrupa por día **de Estados Unidos**, así que
   * un partido de las 21:00 en CDMX cae en la jornada del día anterior al UTC.
   * Con el arranque, el oráculo reconoce el partido aunque lo busque en la
   * jornada vecina — y no confunde el de hoy con el de ayer en la MLB.
   */
  inicio?: string;
  /** Equipo del que se pregunta, con el nombre que usa la fuente. */
  equipo: string;
  /** `gana` es victoria; `no_pierde` incluye el empate. */
  resultado: "gana" | "no_pierde";
  /** El rival. Con él, el oráculo reconoce el mismo partido si se reprograma. */
  rival?: string;
  /**
   * Días en que un partido reprogramado sigue siendo **este** partido. Sólo lo
   * tienen los mercados cuyo criterio lo dice (R-084); los anteriores no lo
   * prometieron y no se resuelven con otro día.
   */
  reprogramacionDias?: number;
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
  liga: LigaId;
  /** Día del partido en UTC, `YYYY-MM-DD`. */
  fecha: string;
  /** Arranque exacto, en ISO. Ver `MatchRule.inicio`. */
  inicio?: string;
  /** Equipo desde cuya perspectiva se lee el resultado. */
  equipo: string;
  /** El rival y la ventana de reprogramación, como en `MatchRule`. */
  rival?: string;
  reprogramacionDias?: number;
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

/**
 * Mercado **espejo** de un mercado regulado: la pregunta es la misma que una de
 * Kalshi (bolsa registrada ante la CFTC) y se resuelve con **su liquidación
 * pública**, que cualquiera puede leer sin llave:
 * `https://api.elections.kalshi.com/trade-api/v2/markets/<ticker>`.
 *
 * Es lo que permite abrir política, elecciones y geopolítica sin que nadie
 * decida a mano quién ganó: la decisión la toma una bolsa regulada con reglas
 * publicadas, y nosotros sólo leemos su `result` cuando su `status` llega a
 * `finalized` — el estado en el que ya pagó y no hay vuelta atrás.
 *
 * Una sola forma cubre los cuatro casos:
 *  - binario de un mercado: `sí` → `[T]` con `resultado: "yes"`; `no` → `[T]`
 *    con `resultado: "no"`;
 *  - varias respuestas excluyentes (la Cámara: D o R): cada una con su ticker;
 *  - respuestas agrupadas (Banxico «recorta» = recorte de 25, de 50 o más);
 *  - «ninguno de los anteriores»: `tickers: []`, gana si todos los demás
 *    liquidaron sin ganador.
 */
export interface MirrorRule {
  kind: "espejo";
  fuente: "kalshi";
  /** Evento de Kalshi. Todos los tickers de la regla pertenecen a él. */
  evento: string;
  respuestas: {
    /** Id de la respuesta en nuestro mercado. */
    id: string;
    /** Mercados de Kalshi que hacen ganar a esta respuesta (basta uno). */
    tickers: string[];
    /** Qué liquidación cuenta. Por omisión `yes`. */
    resultado?: "yes" | "no";
  }[];
}

/**
 * Partido de tenis (individual masculino del circuito ATP), leído del marcador
 * público de ESPN, el mismo que ya resuelve el futbol:
 * `https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard?dates=YYYYMMDD`.
 *
 * Se identifica por el **id del partido** de ESPN, no por los nombres: dos
 * «Cerúndolo» en el mismo cuadro o un nombre con tilde distinta no pueden
 * confundir a quién se paga. `si` = gana `jugador`; `no` = gana `rival`.
 *
 * Gana quien ESPN marca como ganador del partido, **incluido** el retiro o la
 * no presentación del otro (gana quien avanza: la convención de las bolsas de
 * eventos). Un partido cancelado sin ganador no paga a nadie: el plazo lo anula
 * y devuelve lo apostado.
 */
export interface TennisRule {
  kind: "tenis";
  circuito: "atp";
  /** Id del partido (competition) en ESPN. */
  partido: string;
  /** Día del partido en UTC, `YYYY-MM-DD`: la jornada que se pide. */
  fecha: string;
  /** Jugador de la respuesta `si`, como lo nombra ESPN. */
  jugador: string;
  /** Jugador de la respuesta `no`, como lo nombra ESPN. */
  rival: string;
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

/**
 * Duelo de tendencias: cuál de dos artículos de Wikipedia en español tiene más
 * visitas en un día (UTC), según la API pública de Wikimedia, agente `user`
 * (sin bots), todos los accesos:
 * `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/es.wikipedia/all-access/user/<artículo>/daily/<desde>/<hasta>`.
 *
 * Es la medida pública más limpia de «de qué se está hablando»: las tendencias
 * de X o TikTok no tienen una fuente abierta que un tercero pueda volver a leer.
 *
 * Gana quien tenga más visitas ese día. **Empate exacto: gana quien tuvo más el
 * día anterior.** Un día sin visitas no aparece en la API y cuenta como cero,
 * pero sólo si el día ya está publicado — se sabe porque el otro artículo sí
 * tiene el dato.
 */
export interface TrendRule {
  kind: "tendencia";
  fuente: "wikipedia";
  proyecto: "es.wikipedia";
  /** Día que se mide, `YYYY-MM-DD`, en UTC. */
  fecha: string;
  /** Exactamente dos. `titulo` es el nombre del artículo en la URL (`Diego_Luna`). */
  articulos: { id: string; titulo: string }[];
}

/**
 * ¿Hubo al menos un sismo de magnitud `magnitudMin` o mayor en México entre
 * `desde` y `hasta`? Según el catálogo público del USGS:
 * `https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&…`.
 *
 * «En México» es lo que dice el USGS, no una interpretación nuestra: un evento
 * cuenta si su descripción de lugar termina en «Mexico» (p. ej. «off the coast
 * of Michoacan, Mexico»). Así cualquiera repite la consulta y llega a lo mismo.
 */
export interface QuakeRule {
  kind: "sismo";
  fuente: "usgs";
  region: "MX";
  magnitudMin: number;
  /** Ventana, ISO. `desde` incluido, `hasta` excluido. */
  desde: string;
  hasta: string;
}

export type OracleRule =
  | QuakeRule
  | PriceRule
  | VelaRule
  | SeriesRule
  | MatchRule
  | MatchOutcomeRule
  | MirrorRule
  | TennisRule
  | TrendRule;

/**
 * Las reglas que un oráculo resuelve **sin una persona**. Es un `Record` sobre
 * el tipo a propósito: una regla nueva que no se agregue aquí no compila, así
 * que nadie puede sumar una fuente y olvidarse de declarar si se resuelve sola.
 */
const SE_RESUELVE_SOLA: Record<OracleRule["kind"], true> = {
  precio: true,
  vela: true,
  serie: true,
  partido: true,
  partido_multiple: true,
  espejo: true,
  tenis: true,
  tendencia: true,
  sismo: true,
};

/**
 * ¿Este mercado se resuelve solo? Lo que la reposición genera sin que nadie lo
 * escriba tiene que resolverse sin que nadie lo lea: un mercado automático que
 * espera a una persona es uno que nadie va a liquidar a las tres de la mañana.
 */
export function seResuelveSolo(rule: { kind: string } | undefined): boolean {
  return rule !== undefined && Object.prototype.hasOwnProperty.call(SE_RESUELVE_SOLA, rule.kind);
}

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

  if (rule.kind === "sismo") {
    if (!(rule.magnitudMin >= 3 && rule.magnitudMin <= 9)) problems.push("la magnitud mínima no es razonable");
    if (!(Date.parse(rule.desde) < Date.parse(rule.hasta))) problems.push("la ventana del sismo está al revés");
    if (!/usgs/i.test(criterion)) problems.push("el criterio no nombra al USGS como fuente");
    if (!criterion.includes(rule.magnitudMin.toFixed(1))) {
      problems.push(`la magnitud ${rule.magnitudMin.toFixed(1)} no aparece en el criterio`);
    }
    return problems;
  }

  if (rule.kind === "tendencia") {
    if (rule.proyecto !== "es.wikipedia") problems.push("sólo se mide Wikipedia en español");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(rule.fecha)) problems.push("la fecha del duelo tiene que ser YYYY-MM-DD");
    if (rule.articulos.length !== 2) problems.push("un duelo es entre exactamente dos artículos");
    const titulos = rule.articulos.map((a) => a.titulo);
    if (new Set(titulos).size !== titulos.length) problems.push("los dos artículos son el mismo");
    if (!/wikipedia/i.test(criterion)) problems.push("el criterio no nombra a Wikipedia como fuente");
    // los dos artículos, tal como van en la URL, citados en el criterio: así
    // cualquiera arma la misma consulta que hace el oráculo
    for (const titulo of titulos) {
      if (!criterion.includes(titulo)) problems.push(`el criterio no cita el artículo ${titulo}`);
    }
    return problems;
  }

  if (rule.kind === "tenis") {
    if (!/^\d+$/.test(rule.partido)) problems.push("el id de partido de ESPN tiene que ser numérico");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(rule.fecha)) problems.push("la fecha del partido tiene que ser YYYY-MM-DD");
    // los dos jugadores tienen que estar en el criterio publicado, por su
    // apellido: el criterio y la regla hablan del mismo partido
    for (const nombre of [rule.jugador, rule.rival]) {
      const apellido = nombre.trim().split(/\s+/).at(-1) ?? nombre;
      if (!new RegExp(apellido.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i").test(criterion)) {
        problems.push(`el criterio no menciona a ${nombre}`);
      }
    }
    if (rule.jugador === rule.rival) problems.push("un partido necesita dos jugadores distintos");
    return problems;
  }

  if (rule.kind === "espejo") {
    if (!/^[A-Z0-9-]+$/.test(rule.evento)) problems.push("el evento de Kalshi no es un ticker");
    // la fuente tiene que estar nombrada en el criterio: quien apuesta tiene
    // derecho a saber de quién depende el resultado
    if (!/kalshi/i.test(criterion)) problems.push("el criterio no nombra a Kalshi como fuente");
    if (rule.respuestas.length < 2) problems.push("un espejo necesita al menos dos respuestas");
    const ids = rule.respuestas.map((r) => r.id);
    if (new Set(ids).size !== ids.length) problems.push("hay respuestas repetidas en el espejo");
    const ninguna = rule.respuestas.filter((r) => r.tickers.length === 0);
    if (ninguna.length > 1) problems.push("sólo puede haber un «ninguno de los anteriores»");
    for (const respuesta of rule.respuestas) {
      for (const ticker of respuesta.tickers) {
        // un ticker de otro evento resolvería con una pregunta distinta
        if (!ticker.startsWith(`${rule.evento}-`) && ticker !== rule.evento) {
          problems.push(`el ticker ${ticker} no pertenece al evento ${rule.evento}`);
        }
      }
    }
    return problems;
  }

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

  if (rule.kind === "vela") {
    if (!umbralEnTexto(rule.strike).test(criterion)) {
      problems.push(
        `el strike de la regla (${rule.strike}) no aparece en el criterio publicado`,
      );
    }
    const activo = rule.par.split("/")[0];
    if (!new RegExp(activo, "i").test(criterion)) {
      problems.push(`el criterio no menciona el activo ${activo}`);
    }
    // la vela tiene que caer en la rejilla del reloj, o Kraken no la publica y
    // el mercado no se podría resolver con la fuente que promete
    const paso = rule.intervalo * 60_000;
    if (!Number.isFinite(rule.inicio) || rule.inicio % paso !== 0) {
      problems.push(`la vela de ${rule.intervalo} min no está alineada al reloj`);
    }
    if (rule.strike <= 0) problems.push("el strike tiene que ser mayor a cero");
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
