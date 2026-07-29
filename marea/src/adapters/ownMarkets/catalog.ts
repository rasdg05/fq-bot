import type { MarketCategory } from "@/domain/types";
import { assertPublishable, type ResolutionSpec } from "@/domain/resolution";
import { ruleProblems, type OracleRule } from "@/domain/oracleRule";
import type { Pool } from "@/domain/parimutuel";
import {
  BINARY_OUTCOMES,
  SEED,
  binaryPool,
  normalizePool,
  type Outcome,
} from "@/domain/parimutuel";

/**
 * Catálogo de mercados propios de Latam. Esto es contenido de producto, no
 * datos de un tercero: la pregunta la escribimos nosotros, en español, sobre
 * cosas que a la gente de aquí le importan.
 *
 * Cada entrada declara su fuente de resolución antes de existir. Un mercado sin
 * fuente pública y verificable no se publica: `assertPublishable` lo rechaza en
 * el arranque, no en producción (R-025).
 *
 * `referenceKey` marca las preguntas que también cotizan en una casa global.
 * Ésas son las que pueden tener Edge: la casa externa es la lectura
 * independiente contra la que se compara nuestro pozo (R-019).
 */
export interface OwnMarketSeed {
  id: string;
  title: string;
  /**
   * El título como se pinta en la tarjeta: afirmativo y de 42 caracteres para
   * arriba se corta. Es obligatorio en el catálogo propio — sin él el título
   * cae en dos líneas y la tarjeta pasa de 114 a 133 px, que es un tercio de
   * mercado menos por pantalla.
   */
  shortTitle: string;
  category: MarketCategory;
  country: "MX" | "AR" | "BR" | "CL" | "CO" | "PE" | "LATAM";
  closesAt: string;
  resolution: ResolutionSpec;
  /** Estado inicial del pozo, sembrado por nosotros para que se pueda entrar. */
  pool: Pool;
  /**
   * Los resultados posibles, con el texto que ve la gente. Si falta, el
   * mercado es de sí/no: el binario es el caso particular, no un motor aparte.
   */
  outcomes?: Outcome[];
  referenceKey?: string;
  /**
   * El mismo criterio, escrito para que el oráculo lo ejecute sin interpretar
   * español. Sin regla, el mercado se resuelve con confirmación humana — no se
   * queda sin resolver, pero tarda lo que tarde una persona.
   */
  rule?: OracleRule;
  /**
   * Los dos equipos, para los mercados de futbol. El escudo es la URL que
   * sirve la **misma** fuente que resuelve el mercado: citar a ESPN y pintar
   * el escudo de otro sería citar una fuente distinta de la que se lee (R-046).
   *
   * Se guarda en la semilla y no se pide al vuelo: el contenido principal nunca
   * espera a un dato secundario (R-047), y un escudo es lo más secundario que
   * hay.
   */
  equipos?: { nombre: string; escudo?: string }[];
}

const FEE_BPS = 300;

function seedPool(si = SEED, no = SEED): Pool {
  return binaryPool(si, no, FEE_BPS);
}

/** Semilla de un mercado de N resultados: cada id con lo suyo. */
function seedOutcomes(outcomes: Record<string, number>): Pool {
  return { outcomes: { ...outcomes }, feeBps: FEE_BPS };
}

const SEEDS: OwnMarketSeed[] = [
  {
    id: "mx-inpc-anual",
    title: "¿La inflación anual de México sale abajo de 4.0%?",
    shortTitle: "Inflación de México abajo de 4.0 % anual",
    category: "economia",
    country: "MX",
    closesAt: "2026-08-07T13:00:00Z",
    pool: seedPool(420, 260),
    // 628194: INPC variación anual en el BIE. La API del INEGI es gratis pero
    // pide token, igual que Banxico; sin él el mercado lo declara (R-022)
    rule: {
      kind: "serie",
      fuente: "inegi",
      serie: "628194",
      comparacion: "menor",
      umbral: 4,
      etiqueta: "INPC anual del INEGI",
    },
    resolution: {
      sourceName: "INEGI (indicador 628194 del BIE)",
      sourceUrl:
        "https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml/INDICATOR/628194/es/0700/false/BIE/2.0/",
      criterion:
        "Se resuelve Sí si la variación anual del INPC que publica el INEGI en su indicador 628194 del BIE es menor a 4.00%. Se lee del API pública del INEGI, sin redondeos nuestros.",
      settlesAt: "2026-08-07T13:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "mx-banxico-tasa",
    title: "¿Banxico recorta la tasa en su próxima reunión?",
    shortTitle: "Banxico recorta la tasa",
    category: "economia",
    country: "MX",
    closesAt: "2026-08-13T19:00:00Z",
    pool: seedPool(560, 300),
    // SF61745: tasa objetivo. La API de Banxico es gratis pero pide token
    rule: {
      kind: "serie",
      fuente: "banxico",
      serie: "SF61745",
      comparacion: "baja",
      etiqueta: "Tasa objetivo de Banxico",
    },
    resolution: {
      sourceName: "Banco de México (serie SF61745 del SIE)",
      sourceUrl: "https://www.banxico.org.mx/SieAPIRest/service/v1/series/SF61745/datos/oportuno",
      criterion:
        "Se resuelve Sí si la tasa objetivo que publica Banxico en su serie SF61745 queda por debajo de la vigente antes del anuncio. Se lee del API público del Banco de México.",
      settlesAt: "2026-08-13T19:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "mx-dolar-19",
    title: "¿El dólar cierra el mes abajo de 19 pesos?",
    shortTitle: "El dólar cierra el mes abajo de 19 pesos",
    category: "economia",
    country: "MX",
    closesAt: "2026-07-31T21:00:00Z",
    pool: seedPool(300, 480),
    rule: {
      kind: "serie",
      fuente: "banxico",
      serie: "SF43718",
      comparacion: "menor",
      umbral: 19,
      etiqueta: "Tipo de cambio FIX",
    },
    resolution: {
      sourceName: "Banco de México (serie SF43718 del SIE)",
      sourceUrl: "https://www.banxico.org.mx/SieAPIRest/service/v1/series/SF43718/datos/oportuno",
      criterion:
        "Se resuelve Sí si el tipo de cambio FIX que publica Banxico en su serie SF43718 el último día hábil del mes es menor a 19 pesos por dólar.",
      settlesAt: "2026-07-31T21:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "ar-badlar-tasa",
    title: "¿La tasa BADLAR de Argentina baja este mes?",
    shortTitle: "La BADLAR de Argentina baja este mes",
    category: "economia",
    country: "AR",
    closesAt: "2026-08-29T20:00:00Z",
    pool: seedPool(640, 240),
    // variable 7 del BCRA: BADLAR de bancos privados, diaria y sin llave.
    // La serie de "tasa de política monetaria" (160) lleva parada desde julio
    // de 2025, y un dato viejo no resuelve un mercado nuevo (R-052)
    rule: {
      kind: "serie",
      fuente: "bcra",
      serie: "7",
      comparacion: "baja",
      etiqueta: "Tasa BADLAR de bancos privados",
    },
    resolution: {
      sourceName: "BCRA (variable 7 de estadísticas monetarias)",
      sourceUrl: "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/7",
      criterion:
        "Se resuelve Sí si la tasa BADLAR de bancos privados que publica el BCRA en su variable 7 queda por debajo de la vigente al abrir el mes. Se lee del API pública del Banco Central, que cualquiera puede consultar.",
      settlesAt: "2026-08-31T20:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "br-selic-corte",
    title: "¿El Copom baja la Selic en la próxima reunión?",
    shortTitle: "El Copom baja la Selic",
    category: "economia",
    country: "BR",
    closesAt: "2026-09-16T21:00:00Z",
    pool: seedPool(510, 390),
    // serie 432 del BCB: meta Selic, pública y sin llave
    rule: { kind: "serie", fuente: "bcb", serie: "432", comparacion: "baja", etiqueta: "Meta Selic" },
    resolution: {
      sourceName: "Banco Central do Brasil (serie 432 del SGS)",
      sourceUrl: "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/6?formato=json",
      criterion:
        "Se resuelve Sí si la meta Selic que publica el Banco Central do Brasil en su serie 432 queda por debajo de la vigente antes de la reunión. Se lee del endpoint público, que cualquiera puede consultar.",
      settlesAt: "2026-09-16T21:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "br-ipca-5",
    title: "¿La inflación anual de Brasil sigue abajo de 5%?",
    shortTitle: "Inflación de Brasil abajo de 5 % anual",
    category: "economia",
    country: "BR",
    closesAt: "2026-09-09T12:00:00Z",
    pool: seedPool(430, 350),
    // serie 13522 del BCB: IPCA acumulado 12 meses, pública y sin llave
    rule: {
      kind: "serie",
      fuente: "bcb",
      serie: "13522",
      comparacion: "menor",
      umbral: 5,
      etiqueta: "IPCA acumulado 12 meses",
    },
    resolution: {
      sourceName: "Banco Central do Brasil (serie 13522 del SGS)",
      sourceUrl: "https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/6?formato=json",
      criterion:
        "Se resuelve Sí si el IPCA acumulado de 12 meses que publica el Banco Central do Brasil en su serie 13522 es menor a 5 por ciento. Se lee del endpoint público.",
      settlesAt: "2026-09-10T12:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "co-dolar-trm",
    title: "¿El dólar en Colombia cierra el mes abajo de 3,300 pesos?",
    shortTitle: "El dólar en Colombia abajo de 3,300",
    category: "economia",
    country: "CO",
    closesAt: "2026-08-31T12:00:00Z",
    pool: seedPool(380, 420),
    // 32sa-8pi3: la TRM diaria en el portal de datos abiertos de Colombia.
    // El IPC del DANE sólo está publicado por ciudad y hasta 2016, así que no
    // se puede resolver solo: se cambió la pregunta por una que sí se lee
    rule: {
      kind: "serie",
      fuente: "datosgov",
      serie: "32sa-8pi3",
      comparacion: "menor",
      umbral: 3300,
      etiqueta: "Tasa de cambio representativa del mercado",
    },
    resolution: {
      sourceName: "datos.gov.co (conjunto 32sa-8pi3, TRM oficial)",
      sourceUrl: "https://www.datos.gov.co/resource/32sa-8pi3.json",
      criterion:
        "Se resuelve Sí si la Tasa de Cambio Representativa del Mercado publicada en el portal de datos abiertos de Colombia el último día del mes es menor a 3,300 pesos por dólar.",
      settlesAt: "2026-09-01T12:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "cl-imacec",
    title: "¿El Imacec de Chile vuelve a terreno positivo?",
    shortTitle: "El Imacec de Chile vuelve a positivo",
    category: "economia",
    country: "CL",
    closesAt: "2026-09-01T12:00:00Z",
    pool: seedPool(290, 310),
    // mindicador.cl publica el Imacec sin llave. El Banco Central de Chile lo
    // sirve sólo con credenciales, y una fuente que no se puede leer no puede
    // resolver un mercado
    rule: {
      kind: "serie",
      fuente: "mindicador",
      serie: "imacec",
      comparacion: "mayor",
      umbral: 0,
      etiqueta: "Imacec de Chile",
      // el Imacec sale con casi dos meses de rezago y viene fechado al día 1
      // del mes que mide: con el margen de una serie diaria no resolvería nunca
      frescuraDias: 100,
    },
    resolution: {
      sourceName: "mindicador.cl (serie Imacec del Banco Central de Chile)",
      sourceUrl: "https://mindicador.cl/api/imacec",
      criterion:
        "Se resuelve Sí si la variación del Imacec que publica mindicador.cl para el mes que resuelve es mayor a 0 por ciento. Se lee del API pública, que cualquiera puede consultar.",
      settlesAt: "2026-09-02T12:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "btc-cierre-semanal",
    title: "¿Bitcoin cierra la semana arriba de 71,000 dólares?",
    shortTitle: "Bitcoin cierra la semana arriba de 71 mil",
    category: "cripto",
    country: "LATAM",
    // las apuestas cierran un día antes del cierre que se lee (R-043)
    closesAt: "2026-08-01T23:59:00Z",
    pool: seedPool(910, 780),
    // también cotiza afuera: por eso puede tener Edge contra una casa global
    referenceKey: "bitcoin close above 71000",
    // se cita la fuente que el oráculo lee de verdad, no otra
    rule: { kind: "precio", par: "BTC/USD", umbral: 71_000, comparacion: "arriba", modo: "cierre" },
    resolution: {
      sourceName: "Kraken (velas diarias públicas)",
      sourceUrl: "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440",
      criterion:
        "Se resuelve Sí si la vela diaria de BTC/USD en Kraken correspondiente al domingo 2026-08-02 cierra por encima de 71,000 dólares. Se lee del endpoint público de Kraken, que cualquiera puede consultar.",
      settlesAt: "2026-08-02T23:59:00Z",
      disputeWindowHours: 12,
    },
  },
  {
    id: "eth-4500",
    title: "¿Ethereum toca 4,500 dólares antes de octubre?",
    shortTitle: "Ethereum toca 4,500 antes de octubre",
    category: "cripto",
    country: "LATAM",
    closesAt: "2026-09-30T00:00:00Z",
    pool: seedPool(340, 690),
    referenceKey: "ethereum above 4500",
    rule: {
      kind: "precio",
      par: "ETH/USD",
      umbral: 4_500,
      comparacion: "arriba",
      modo: "toca",
      desde: "2026-07-01T00:00:00Z",
    },
    resolution: {
      sourceName: "Kraken (velas diarias públicas)",
      sourceUrl: "https://api.kraken.com/0/public/OHLC?pair=ETHUSD&interval=1440",
      criterion:
        "Se resuelve Sí si el precio de ETH/USD en Kraken alcanza o supera 4,500 dólares en cualquier momento entre el 1 de julio y el 1 de octubre de 2026, medido sobre el máximo de las velas diarias públicas.",
      settlesAt: "2026-10-01T00:00:00Z",
      disputeWindowHours: 12,
    },
  },
  {
    id: "pe-inflacion-lima",
    title: "¿La inflación anual de Perú se mantiene abajo de 3%?",
    shortTitle: "Inflación de Perú abajo de 3 % anual",
    category: "economia",
    country: "PE",
    closesAt: "2026-09-30T12:00:00Z",
    pool: seedPool(260, 240),
    // PN01279PM: variación anual del IPC de Lima. Pública y sin llave
    rule: {
      kind: "serie",
      fuente: "bcrp",
      serie: "PN01279PM",
      comparacion: "menor",
      umbral: 3,
      etiqueta: "Inflación anual de Lima Metropolitana",
    },
    resolution: {
      sourceName: "BCRP (serie PN01279PM)",
      sourceUrl:
        "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PN01279PM/json",
      criterion:
        "Se resuelve Sí si la variación anual del índice de precios de Lima Metropolitana que publica el BCRP en su serie PN01279PM es menor a 3.00 por ciento. Se lee del API pública del Banco Central de Reserva.",
      settlesAt: "2026-10-01T12:00:00Z",
      disputeWindowHours: 24,
    },
  },

  /* ------------------------- mercados de N respuestas --------------------- */
  /*
   * La quiniela de toda la vida no es de sí/no: es "gana, empata o pierde".
   * Plegar el empate dentro de "no" era una limitación de nuestro motor, no de
   * la pregunta, y el empate en Liga MX pasa casi un tercio de las veces.
   *
   * Los dos se resuelven solos contra el marcador público de ESPN, así que no
   * consumen ninguno de los tres cupos de confirmación humana (R-062).
   */
  {
    id: "mx-america-santos-1x2",
    title: "¿Cómo termina el América ante Santos?",
    shortTitle: "Cómo termina el América ante Santos",
    category: "deportes",
    country: "MX",
    closesAt: "2026-08-02T23:00:00Z",
    pool: seedOutcomes({ gana: 520, empata: 260, pierde: 220 }),
    outcomes: [
      { id: "gana", label: "Gana el América" },
      { id: "empata", label: "Empatan" },
      { id: "pierde", label: "Gana Santos" },
    ],
    rule: {
      kind: "partido_multiple",
      liga: "mex.1",
      fecha: "2026-08-02",
      equipo: "América",
      mercado: "1x2",
    },
    equipos: [
      { nombre: "América", escudo: "https://a.espncdn.com/i/teamlogos/soccer/500/227.png" },
      { nombre: "Santos", escudo: "https://a.espncdn.com/i/teamlogos/soccer/500/225.png" },
    ],
    resolution: {
      sourceName: "ESPN (marcador de la Liga MX)",
      sourceUrl:
        "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard?dates=20260802",
      criterion:
        "Se resuelve con el marcador final del América contra Santos del 2 de agosto de 2026, tal como lo publica ESPN: Gana el América si anota más goles, Empatan si terminan iguales, y Gana Santos si el América anota menos. Sólo cuenta el marcador al final del tiempo reglamentario que publica la fuente.",
      settlesAt: "2026-08-03T04:00:00Z",
      disputeWindowHours: 12,
    },
  },
  {
    id: "mx-toluca-necaxa-goles",
    title: "¿Cuántos goles se anotan en Toluca-Necaxa?",
    shortTitle: "Cuántos goles en Toluca-Necaxa",
    category: "deportes",
    country: "MX",
    closesAt: "2026-08-03T01:00:00Z",
    pool: seedOutcomes({ goles_0_1: 240, goles_2_3: 480, goles_4_mas: 280 }),
    outcomes: [
      { id: "goles_0_1", label: "0-1 goles" },
      { id: "goles_2_3", label: "2-3 goles" },
      { id: "goles_4_mas", label: "4 o más goles" },
    ],
    rule: {
      kind: "partido_multiple",
      liga: "mex.1",
      fecha: "2026-08-03",
      equipo: "Toluca",
      mercado: "goles",
      cortes: [2, 4],
    },
    resolution: {
      sourceName: "ESPN (marcador de la Liga MX)",
      sourceUrl:
        "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard?dates=20260803",
      criterion:
        "Se resuelve con los goles totales del Toluca contra Necaxa del 3 de agosto de 2026, sumando los de los dos equipos según el marcador final que publica ESPN: 0-1 goles, 2-3 goles, o 4 o más goles. Sólo cuenta el marcador al final del tiempo reglamentario que publica la fuente.",
      settlesAt: "2026-08-03T06:00:00Z",
      disputeWindowHours: 12,
    },
  },
];

/**
 * Valida el catálogo al cargarlo. Si alguna entrada no declara fuente pública,
 * criterio inequívoco y ventana de disputa, el módulo falla al importarse: es
 * el momento correcto para enterarse, no cuando ya hay gente apostando.
 */
/** Lo que cabe en una línea de la tarjeta a 390 px. Medido, no estimado. */
export const SHORT_TITLE_MAX = 42;

export function validateSeed(seed: OwnMarketSeed): OwnMarketSeed {
  const resolution = assertPublishable(seed.resolution);
  // el título corto es parte del contrato, no un adorno: sin él la tarjeta
  // crece 19 px y entra un mercado menos por pantalla. Un archivo publicado
  // por una versión vieja no trae el campo, así que se deriva del largo en vez
  // de tirar el mercado — degradar es correcto, quedarse sin feed no
  const corto = (seed.shortTitle ?? "").trim();
  const shortTitle = corto || seed.title.replace(/^¿|\?$/g, "").trim();
  if (shortTitle.length > SHORT_TITLE_MAX) {
    throw new Error(
      `Mercado ${seed.id}: el título corto mide ${shortTitle.length} caracteres y el máximo es ${SHORT_TITLE_MAX}`,
    );
  }
  const outcomes = seed.outcomes ?? [...BINARY_OUTCOMES];
  // el catálogo generado que ya está publicado trae pozos en el formato viejo.
  // Se leen igual que los del volumen: un mercado que se cae por la forma del
  // pozo desaparece del feed sin que nadie se entere
  const pool = normalizePool(seed.pool);

  // el pozo y los resultados declarados tienen que hablar del mismo mercado:
  // un resultado sin pozo no se puede elegir, y un pozo sin resultado es
  // dinero apostado a algo que la interfaz no sabe nombrar
  const idsPozo = Object.keys(pool.outcomes).sort();
  const idsDeclarados = outcomes.map((o) => o.id).sort();
  if (idsPozo.join("|") !== idsDeclarados.join("|")) {
    throw new Error(
      `Mercado ${seed.id}: el pozo tiene [${idsPozo}] y declara [${idsDeclarados}]`,
    );
  }
  if (outcomes.length < 2) {
    throw new Error(`Mercado ${seed.id}: un mercado necesita al menos dos resultados`);
  }
  if (new Set(idsDeclarados).size !== idsDeclarados.length) {
    throw new Error(`Mercado ${seed.id}: hay ids de resultado repetidos`);
  }
  for (const outcome of outcomes) {
    if (!outcome.label.trim()) {
      throw new Error(`Mercado ${seed.id}: el resultado ${outcome.id} no tiene texto`);
    }
  }
  if (seed.rule) {
    // la regla de máquina y el criterio publicado tienen que decir lo mismo
    const problems = ruleProblems(seed.rule, resolution.criterion);
    if (problems.length > 0) {
      throw new Error(`Mercado ${seed.id}: ${problems.join("; ")}`);
    }
  }
  if (new Date(seed.closesAt).getTime() > new Date(resolution.settlesAt).getTime()) {
    throw new Error(`Mercado ${seed.id}: las apuestas cierran después de resolver`);
  }
  return { ...seed, shortTitle, resolution, outcomes, pool };
}

export const OWN_MARKETS: OwnMarketSeed[] = SEEDS.map(validateSeed);

/**
 * Lo que se puede mostrar hoy. Un mercado vencido en el feed es peor que un
 * feed corto: promete algo que ya no existe. Se deja visible un par de días
 * después de resolver para que quien apostó vea el resultado, y luego se va.
 */
const VENTANA_POST_RESOLUCION_MS = 48 * 3_600_000;

export function activeSeeds(
  now: number,
  seeds: OwnMarketSeed[] = OWN_MARKETS,
): OwnMarketSeed[] {
  return seeds.filter(
    (seed) =>
      new Date(seed.resolution.settlesAt).getTime() + VENTANA_POST_RESOLUCION_MS > now,
  );
}

/** Cuántos siguen aceptando apuestas. Es la cifra que dice si el feed vive. */
export function openSeeds(
  now: number,
  seeds: OwnMarketSeed[] = OWN_MARKETS,
): OwnMarketSeed[] {
  return seeds.filter((seed) => new Date(seed.closesAt).getTime() > now);
}

export function findOwnMarket(id: string): OwnMarketSeed | undefined {
  return OWN_MARKETS.find((seed) => seed.id === id);
}
