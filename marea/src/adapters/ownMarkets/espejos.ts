import { assertPublishable } from "@/domain/resolution";
import { SEED, declareSeed } from "@/domain/parimutuel";
import type { MarketCategory } from "@/domain/types";
import type { MirrorRule } from "@/domain/oracleRule";
import {
  cargarEventoKalshi,
  urlMercadoKalshi,
  type EstadoKalshi,
} from "@/adapters/oracles/mirrorOracle";
import type { OwnMarketSeed } from "./catalog";

/**
 * Mercados **espejo**: política, elecciones y geopolítica que se resuelven con
 * la liquidación pública de Kalshi (ver `mirrorOracle.ts`).
 *
 * ## Por qué curados y no automáticos
 *
 * Kalshi tiene ocho mil eventos abiertos. Abrirlos todos sería un feed de
 * preguntas sobre visitas a la Casa Blanca y fusiones de bancos regionales. Un
 * mercado de predicción se juzga por lo que **elige** ofrecer, así que la lista
 * es editorial: cada entrada tiene su título en español, su cierre elegido a
 * propósito y un criterio escrito a mano que dice lo mismo que la regla de
 * Kalshi. Añadir uno es añadir un objeto aquí; la validación del catálogo
 * (`validateSeed`) lo revisa igual que a todos.
 *
 * ## El cierre, que es la decisión que más importa
 *
 * Kalshi cierra muchos de estos meses después del evento (la Cámara, en
 * febrero de 2027). Aquí se cierra **antes del evento**: el día de la elección
 * a primera hora, una hora antes del anuncio de Banxico. Y si el evento ocurre
 * antes de lo previsto (un acuerdo firmado en noviembre), el oráculo detiene
 * las apuestas en cuanto Kalshi deja de operar (`detenerApuestas`).
 *
 * ## El pozo inicial
 *
 * Se siembra con la probabilidad de Kalshi al momento de crear el mercado.
 * Abrir «¿Los demócratas ganan la Cámara?» en 50/50 cuando la bolsa regulada
 * dice 91 % sería mentir en el primer píxel. Sin precio de Kalshi el mercado
 * **no se crea** —se reintenta en la siguiente vuelta—: nunca con un 50/50
 * inventado.
 */

export interface RespuestaEspejo {
  id: string;
  label: string;
  /** Mercados de Kalshi que la hacen ganar (basta uno). `[]` = «ninguno de los anteriores». */
  tickers: string[];
  resultado?: "yes" | "no";
}

export interface EspejoCurado {
  id: string;
  evento: string;
  category: MarketCategory;
  country: OwnMarketSeed["country"];
  /** Sección y hub en el feed: «Elecciones EE.UU. 2026», «México», «Geopolítica». */
  hub: string;
  title: string;
  shortTitle: string;
  /** Cuándo dejamos de aceptar apuestas: antes del evento, no cuando Kalshi cierra. */
  closesAt: string;
  /** Cuándo se espera la liquidación de Kalshi. Cuenta el plazo de anulación. */
  settlesAt: string;
  criterio: string;
  respuestas: RespuestaEspejo[];
}

const KALSHI_WEB = "https://kalshi.com";

export const ESPEJOS: EspejoCurado[] = [
  /* ------------------------- Elecciones EE.UU. 2026 ------------------------ */
  {
    id: "pol-eeuu-camara-2026",
    evento: "CONTROLH-2026",
    category: "politica",
    country: "US",
    hub: "Elecciones EE.UU. 2026",
    title: "Intermedias 2026: ¿qué partido gana la Cámara de Representantes?",
    shortTitle: "Control de la Cámara de EE.UU.",
    closesAt: "2026-11-03T11:00:00Z",
    settlesAt: "2027-02-01T15:00:00Z",
    criterio:
      "Se resuelve con el mercado CONTROLH-2026 de Kalshi: gana el partido que Kalshi liquide como ganador del control de la Cámara de Representantes en la elección intermedia del 3 de noviembre de 2026. Las apuestas cierran el día de la elección, antes de que abran las casillas.",
    respuestas: [
      { id: "dem", label: "Demócratas", tickers: ["CONTROLH-2026-D"] },
      { id: "rep", label: "Republicanos", tickers: ["CONTROLH-2026-R"] },
    ],
  },
  {
    id: "pol-eeuu-senado-2026",
    evento: "CONTROLS-2026",
    category: "politica",
    country: "US",
    hub: "Elecciones EE.UU. 2026",
    title: "Intermedias 2026: ¿qué partido gana el Senado?",
    shortTitle: "Control del Senado de EE.UU.",
    closesAt: "2026-11-03T11:00:00Z",
    settlesAt: "2027-02-01T15:00:00Z",
    criterio:
      "Se resuelve con el mercado CONTROLS-2026 de Kalshi: gana el partido que Kalshi liquide como ganador del control del Senado tras la elección intermedia del 3 de noviembre de 2026. Las apuestas cierran el día de la elección, antes de que abran las casillas.",
    respuestas: [
      { id: "dem", label: "Demócratas", tickers: ["CONTROLS-2026-D"] },
      { id: "rep", label: "Republicanos", tickers: ["CONTROLS-2026-R"] },
    ],
  },
  {
    id: "pol-eeuu-congreso-2026",
    evento: "KXBALANCEPOWERCOMBO-27FEB",
    category: "politica",
    country: "US",
    hub: "Elecciones EE.UU. 2026",
    title: "Intermedias 2026: ¿cómo queda el equilibrio de poder en el Congreso?",
    shortTitle: "Equilibrio del Congreso EE.UU.",
    closesAt: "2026-11-03T11:00:00Z",
    settlesAt: "2027-02-01T15:00:00Z",
    criterio:
      "Se resuelve con el evento KXBALANCEPOWERCOMBO-27FEB de Kalshi: gana la combinación de control de Cámara y Senado que Kalshi liquide tras la elección intermedia del 3 de noviembre de 2026. Las apuestas cierran el día de la elección, antes de que abran las casillas.",
    respuestas: [
      { id: "dd", label: "Demócratas arrasan", tickers: ["KXBALANCEPOWERCOMBO-27FEB-DD"] },
      { id: "dr", label: "Cámara D, Senado R", tickers: ["KXBALANCEPOWERCOMBO-27FEB-DR"] },
      { id: "rr", label: "Republicanos arrasan", tickers: ["KXBALANCEPOWERCOMBO-27FEB-RR"] },
      { id: "rd", label: "Cámara R, Senado D", tickers: ["KXBALANCEPOWERCOMBO-27FEB-RD"] },
    ],
  },

  /* --------------------------------- México -------------------------------- */
  {
    id: "mx-banxico-nov-2026",
    evento: "KXCBDECISIONMEXICO-26NOV05",
    category: "economia",
    country: "MX",
    hub: "México",
    title: "¿Qué decide Banxico con la tasa el 5 de noviembre?",
    shortTitle: "Banxico: decisión del 5 de nov.",
    closesAt: "2026-11-05T18:00:00Z",
    settlesAt: "2026-11-06T16:00:00Z",
    criterio:
      "Se resuelve con el evento KXCBDECISIONMEXICO-26NOV05 de Kalshi sobre el anuncio de política monetaria del Banco de México del 5 de noviembre de 2026: Mantiene si Kalshi liquida «mantener», Recorta si liquida un recorte de cualquier tamaño, y Sube si liquida un alza de cualquier tamaño. Las apuestas cierran una hora antes del anuncio.",
    respuestas: [
      { id: "mantiene", label: "Mantiene la tasa", tickers: ["KXCBDECISIONMEXICO-26NOV05-HOLD"] },
      {
        id: "recorta",
        label: "Recorta",
        tickers: [
          "KXCBDECISIONMEXICO-26NOV05-C25",
          "KXCBDECISIONMEXICO-26NOV05-C50",
          "KXCBDECISIONMEXICO-26NOV05-C50P",
        ],
      },
      {
        id: "sube",
        label: "Sube",
        tickers: [
          "KXCBDECISIONMEXICO-26NOV05-H25P",
          "KXCBDECISIONMEXICO-26NOV05-H50",
          "KXCBDECISIONMEXICO-26NOV05-H50P",
        ],
      },
    ],
  },
  {
    id: "mx-diputados-2027",
    evento: "KXMEXICODEPUTIES-27",
    category: "politica",
    country: "MX",
    hub: "México",
    title: "Elección intermedia 2027: ¿qué partido gana la Cámara de Diputados?",
    shortTitle: "Diputados 2027: partido ganador",
    closesAt: "2027-06-06T12:00:00Z",
    settlesAt: "2027-06-30T16:00:00Z",
    criterio:
      "Se resuelve con el evento KXMEXICODEPUTIES-27 de Kalshi: gana el partido que Kalshi liquide como ganador de la elección de la Cámara de Diputados de México de 2027. Otro partido se resuelve si Kalshi no liquida como ganador ni a Morena ni al PAN. Las apuestas cierran el día de la elección.",
    respuestas: [
      { id: "morena", label: "Morena", tickers: ["KXMEXICODEPUTIES-27-MORENA"] },
      { id: "pan", label: "PAN", tickers: ["KXMEXICODEPUTIES-27-PAN"] },
      { id: "otro", label: "Otro partido", tickers: [] },
    ],
  },

  /* ----------------------------- Brasil 2026 ------------------------------ */
  {
    id: "br-presidente-1v-2026",
    evento: "KXBRPRES1MOV-BRPRES26",
    category: "politica",
    country: "BR",
    hub: "Elecciones Brasil 2026",
    title: "Brasil, primera vuelta del 4 de octubre: ¿quién queda primero?",
    shortTitle: "Brasil: ganador de la 1.ª vuelta",
    // las casillas abren a las 8:00 de Brasilia (UTC−3)
    closesAt: "2026-10-04T11:00:00Z",
    settlesAt: "2026-10-15T16:00:00Z",
    criterio:
      "Se resuelve con el evento KXBRPRES1MOV-BRPRES26 de Kalshi (margen de victoria en la primera vuelta presidencial de Brasil del 4 de octubre de 2026): gana Lula si Kalshi liquida en «sí» cualquiera de los tramos de margen a favor de Luiz Inácio Lula da Silva, y Flávio Bolsonaro si liquida cualquiera de los suyos. Otra persona, si Kalshi no liquida ninguno de los dos. Quedar primero en la primera vuelta no es ganar la presidencia si hay segunda vuelta. Las apuestas cierran al abrir las casillas.",
    respuestas: [
      {
        id: "lula",
        label: "Lula",
        tickers: [
          "KXBRPRES1MOV-BRPRES26-LSIL-P2",
          "KXBRPRES1MOV-BRPRES26-LSIL-P7",
          "KXBRPRES1MOV-BRPRES26-LSIL-P12",
          "KXBRPRES1MOV-BRPRES26-LSIL-P57",
        ],
      },
      {
        id: "flavio",
        label: "Flávio Bolsonaro",
        tickers: [
          "KXBRPRES1MOV-BRPRES26-FBOL-P2",
          "KXBRPRES1MOV-BRPRES26-FBOL-P7",
          "KXBRPRES1MOV-BRPRES26-FBOL-P12",
          "KXBRPRES1MOV-BRPRES26-FBOL-P57",
        ],
      },
      { id: "otro", label: "Otra persona", tickers: [] },
    ],
  },
  {
    id: "br-segunda-vuelta-2026",
    evento: "KXBRAZILPRES1R-26OCT04",
    category: "politica",
    country: "BR",
    hub: "Elecciones Brasil 2026",
    title: "Brasil 2026: ¿la presidencia se decide en segunda vuelta?",
    shortTitle: "Brasil: ¿habrá segunda vuelta?",
    closesAt: "2026-10-04T11:00:00Z",
    settlesAt: "2026-10-15T16:00:00Z",
    criterio:
      "Se resuelve con el mercado KXBRAZILPRES1R-26OCT04 de Kalshi (¿algún candidato gana en primera vuelta la elección presidencial de Brasil del 4 de octubre de 2026?): Habrá segunda vuelta si Kalshi lo liquida en «no»; Se decide en primera si lo liquida en «sí». Las apuestas cierran al abrir las casillas.",
    respuestas: [
      { id: "segunda", label: "Habrá segunda vuelta", tickers: ["KXBRAZILPRES1R-26OCT04"], resultado: "no" },
      { id: "primera", label: "Se decide en primera", tickers: ["KXBRAZILPRES1R-26OCT04"], resultado: "yes" },
    ],
  },

  /* ------------------------------- Geopolítica ----------------------------- */
  {
    id: "geo-iran-acuerdo-2026",
    evento: "KXUSAIRANAGREEMENT-27",
    category: "politica",
    country: "GLOBAL",
    hub: "Geopolítica",
    title: "¿EE.UU. e Irán firman un acuerdo nuclear antes de 2027?",
    shortTitle: "Acuerdo nuclear EE.UU.-Irán",
    closesAt: "2026-12-31T23:00:00Z",
    settlesAt: "2027-01-02T16:00:00Z",
    criterio:
      "Se resuelve con el mercado KXUSAIRANAGREEMENT-27 de Kalshi (acuerdo nuclear entre Estados Unidos e Irán antes del 1 de enero de 2027): Hay acuerdo si Kalshi lo liquida en «sí»; No hay acuerdo si lo liquida en «no». Si el acuerdo llega antes, las apuestas se detienen en cuanto Kalshi deja de operar.",
    respuestas: [
      { id: "si", label: "Hay acuerdo", tickers: ["KXUSAIRANAGREEMENT-27"], resultado: "yes" },
      { id: "no", label: "No hay acuerdo", tickers: ["KXUSAIRANAGREEMENT-27"], resultado: "no" },
    ],
  },
  {
    id: "geo-venezuela-2026",
    evento: "KXVENEZUELALEADER-26DEC31",
    category: "politica",
    country: "LATAM",
    hub: "Geopolítica",
    title: "¿Quién gobierna oficialmente Venezuela al cierre de 2026?",
    shortTitle: "Venezuela: líder al 31 de dic.",
    closesAt: "2026-12-31T12:00:00Z",
    settlesAt: "2027-01-05T16:00:00Z",
    criterio:
      "Se resuelve con el evento KXVENEZUELALEADER-26DEC31 de Kalshi sobre quién encabeza oficialmente Venezuela al terminar 2026: gana Maduro o Delcy Rodríguez si Kalshi los liquida como tales, y Otra persona si Kalshi no liquida a ninguno de los dos.",
    respuestas: [
      { id: "maduro", label: "Nicolás Maduro", tickers: ["KXVENEZUELALEADER-26DEC31-NMAD"] },
      { id: "delcy", label: "Delcy Rodríguez", tickers: ["KXVENEZUELALEADER-26DEC31-DROD"] },
      { id: "otro", label: "Otra persona", tickers: [] },
    ],
  },
  {
    id: "geo-zelenski-putin-2026",
    evento: "KXZELENSKYPUTIN-29",
    category: "politica",
    country: "GLOBAL",
    hub: "Geopolítica",
    title: "¿Zelenski y Putin hablan directamente antes de 2027?",
    shortTitle: "Zelenski y Putin hablan en 2026",
    closesAt: "2026-12-31T23:00:00Z",
    settlesAt: "2027-01-03T16:00:00Z",
    criterio:
      "Se resuelve con el mercado KXZELENSKYPUTIN-29-27 de Kalshi (Zelenski y Putin hablan antes de 2027): Hablan si Kalshi lo liquida en «sí»; No hablan si lo liquida en «no». Si ocurre antes, las apuestas se detienen en cuanto Kalshi deja de operar.",
    respuestas: [
      { id: "si", label: "Hablan", tickers: ["KXZELENSKYPUTIN-29-27"], resultado: "yes" },
      { id: "no", label: "No hablan", tickers: ["KXZELENSKYPUTIN-29-27"], resultado: "no" },
    ],
  },
  {
    id: "geo-israel-pm-2026",
    evento: "KXISRAELPM-26OCT27",
    category: "politica",
    country: "GLOBAL",
    hub: "Geopolítica",
    title: "Elección en Israel: ¿quién será primer ministro tras los comicios de 2026?",
    shortTitle: "Próximo primer ministro israelí",
    closesAt: "2026-10-27T04:00:00Z",
    settlesAt: "2027-10-27T16:00:00Z",
    criterio:
      "Se resuelve con el evento KXISRAELPM-26OCT27 de Kalshi: gana quien Kalshi liquide como primer ministro de Israel tras la elección de 2026, y Otra persona si Kalshi no liquida a ninguno de los tres nombrados. Las apuestas cierran el día de la elección.",
    respuestas: [
      { id: "eizenkot", label: "Gadi Eizenkot", tickers: ["KXISRAELPM-26OCT27-GEIZ"] },
      { id: "netanyahu", label: "Benjamín Netanyahu", tickers: ["KXISRAELPM-26OCT27-BNET"] },
      { id: "bennett", label: "Naftali Bennett", tickers: ["KXISRAELPM-26OCT27-NBEN"] },
      { id: "otro", label: "Otra persona", tickers: [] },
    ],
  },
];

/* ------------------------------------------------------------------------- */

/**
 * Lo más ancho que puede estar un libro para que su punto medio cuente como
 * precio. Medido el 2026-10-01: las 30 patas de los espejos curados y de Brasil
 * están en 0.07 o menos; el dólar diario de Kalshi y el Billboard de la semana
 * estaban en 0.01/0.99 y 0.00/0.90 — libros vacíos.
 */
export const SPREAD_MAXIMO = 0.1;

/**
 * Probabilidad de «sí» de un mercado de Kalshi: el punto medio de un libro
 * **con gente adentro**, o nada.
 *
 * La versión anterior tomaba el punto medio de cualquier libro, y el de un
 * libro vacío (bid 0.01 / ask 0.99) es 0.50: un 50/50 inventado con forma de
 * precio, justo lo que el espejo promete no hacer. Tampoco cae ya al último
 * precio operado: puede ser de hace semanas, y un precio viejo enseñado como de
 * ahora es mentira con forma de dato (R-022).
 */
export function probabilidadKalshi(mercado: EstadoKalshi): number | undefined {
  const num = (v: unknown) => (v === null || v === undefined ? NaN : Number(v));
  const bid = Math.max(0, num(mercado.yes_bid_dollars) || 0);
  const ask = num(mercado.yes_ask_dollars);
  if (!(ask > 0) || ask > 1) return undefined;
  // un libro de 0.00/0.01 sí dice algo: que nadie paga ni un centavo por el sí
  if (ask - bid > SPREAD_MAXIMO + 1e-9) return undefined;
  return (bid + ask) / 2;
}

/** Pozo inicial total de un espejo, en puntos. */
export const POZO_ESPEJO = SEED * 10;
/** Ninguna respuesta nace con menos de esto: un pozo vacío paga infinito. */
const PISO_PARTICIPACION = 0.03;

/**
 * La semilla de un espejo, o `null` si no se puede crear con honestidad: algún
 * ticker sin precio, o el evento ya no opera en Kalshi.
 */
export function espejoSeed(
  curado: EspejoCurado,
  mercados: ReadonlyMap<string, EstadoKalshi>,
): OwnMarketSeed | null {
  const tickers = [...new Set(curado.respuestas.flatMap((r) => r.tickers))];
  if (tickers.some((t) => mercados.get(t)?.status !== "active")) return null;

  const crudas: number[] = [];
  for (const respuesta of curado.respuestas) {
    if (respuesta.tickers.length === 0) {
      crudas.push(NaN); // se calcula al final: lo que dejan las demás
      continue;
    }
    let p = 0;
    for (const ticker of respuesta.tickers) {
      const pSi = probabilidadKalshi(mercados.get(ticker)!);
      if (pSi === undefined) return null;
      p += (respuesta.resultado ?? "yes") === "yes" ? pSi : 1 - pSi;
    }
    crudas.push(p);
  }
  const conocidas = crudas.filter((p) => !Number.isNaN(p)).reduce((s, p) => s + p, 0);
  const probabilidades = crudas.map((p) => (Number.isNaN(p) ? Math.max(0, 1 - conocidas) : p));
  const total = probabilidades.reduce((s, p) => s + p, 0);
  if (!(total > 0)) return null;

  // normaliza (los libros traen sobreprecio), aplica el piso y vuelve a normalizar
  const conPiso = probabilidades.map((p) => Math.max(PISO_PARTICIPACION, p / total));
  const sumaPiso = conPiso.reduce((s, p) => s + p, 0);
  const outcomes: Record<string, number> = {};
  curado.respuestas.forEach((respuesta, i) => {
    outcomes[respuesta.id] = Math.max(1, Math.round((POZO_ESPEJO * conPiso[i]) / sumaPiso));
  });

  const rule: MirrorRule = {
    kind: "espejo",
    fuente: "kalshi",
    evento: curado.evento,
    respuestas: curado.respuestas.map(({ id, tickers: ts, resultado }) => ({
      id,
      tickers: ts,
      ...(resultado ? { resultado } : {}),
    })),
  };

  return {
    id: curado.id,
    title: curado.title,
    shortTitle: curado.shortTitle,
    category: curado.category,
    country: curado.country,
    liga: curado.hub,
    closesAt: curado.closesAt,
    outcomes: curado.respuestas.map(({ id, label }) => ({ id, label })),
    pool: declareSeed({ outcomes, feeBps: 300 }, "apuesta"),
    rule,
    resolution: assertPublishable({
      sourceName: `Kalshi (liquidación del evento ${curado.evento}, bolsa regulada por la CFTC)`,
      // la URL de la API del primer ticker se abre en el navegador sin llave;
      // la de la web es más amable pero exige JavaScript y cambia de forma
      sourceUrl: tickers[0] ? urlMercadoKalshi(tickers[0]) : `${KALSHI_WEB}/markets`,
      criterion: curado.criterio,
      settlesAt: curado.settlesAt,
      // un día: lo que publica una bolsa regulada no se discute, pero quien
      // apostó merece la ventana para ver la evidencia antes de que se pague
      disputeWindowHours: 24,
    }),
  };
}

/**
 * Los espejos que faltan, listos para el freno de presupuesto. Sólo los que
 * siguen abiertos y no existen todavía. Pide a Kalshi en paralelo; un evento
 * que no contesta no tapa a los demás y queda en `errores` con su motivo.
 */
export async function espejosPendientes(input: {
  ahora: number;
  existentes: ReadonlySet<string>;
  /** Los mercados de un evento de Kalshi. Por omisión, la API pública. */
  cargarEvento?: (evento: string) => Promise<EstadoKalshi[]>;
  curados?: EspejoCurado[];
}): Promise<{ seeds: OwnMarketSeed[]; errores: string[] }> {
  const cargar = input.cargarEvento ?? ((e: string) => cargarEventoKalshi(fetch, e));
  const curados = input.curados ?? ESPEJOS;
  const faltan = curados.filter(
    (c) => !input.existentes.has(c.id) && Date.parse(c.closesAt) > input.ahora,
  );
  const seeds: OwnMarketSeed[] = [];
  const errores: string[] = [];
  // un pedido por evento, en paralelo; uno que no contesta no tapa a los demás
  await Promise.all(
    faltan.map(async (curado) => {
      let mercados: Map<string, EstadoKalshi>;
      try {
        mercados = new Map((await cargar(curado.evento)).map((m) => [m.ticker, m]));
      } catch (error) {
        errores.push(`${curado.id}: ${error instanceof Error ? error.message : String(error)}`);
        return;
      }
      const seed = espejoSeed(curado, mercados);
      if (seed) seeds.push(seed);
      else errores.push(`${curado.id}: Kalshi sin precio o sin operar; se reintenta`);
    }),
  );
  // orden estable: el de la lista curada, no el de llegada de la red
  const orden = new Map(curados.map((c, i) => [c.id, i]));
  seeds.sort((a, b) => (orden.get(a.id) ?? 0) - (orden.get(b.id) ?? 0));
  return { seeds, errores };
}
