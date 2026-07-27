import type { MarketCategory } from "@/domain/types";
import { assertPublishable, type ResolutionSpec } from "@/domain/resolution";
import type { Pool } from "@/domain/parimutuel";
import { SEED } from "@/domain/parimutuel";

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
  category: MarketCategory;
  country: "MX" | "AR" | "BR" | "CL" | "CO" | "PE" | "LATAM";
  closesAt: string;
  resolution: ResolutionSpec;
  /** Estado inicial del pozo, sembrado por nosotros para que se pueda entrar. */
  pool: Pool;
  referenceKey?: string;
}

const FEE_BPS = 300;

function seedPool(si = SEED, no = SEED): Pool {
  return { si, no, feeBps: FEE_BPS };
}

const SEEDS: OwnMarketSeed[] = [
  {
    id: "mx-inpc-anual",
    title: "¿La inflación anual de México sale abajo de 4.0%?",
    category: "economia",
    country: "MX",
    closesAt: "2026-08-07T13:00:00Z",
    pool: seedPool(420, 260),
    resolution: {
      sourceName: "INEGI",
      sourceUrl: "https://www.inegi.org.mx/temas/inpc/",
      criterion:
        "Se resuelve Sí si el INPC anual que publica el INEGI el 7 de agosto es menor a 4.00%. Se toma la cifra del comunicado oficial, sin redondeos nuestros.",
      settlesAt: "2026-08-07T13:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "mx-banxico-tasa",
    title: "¿Banxico recorta la tasa en su próxima reunión?",
    category: "economia",
    country: "MX",
    closesAt: "2026-08-13T19:00:00Z",
    pool: seedPool(560, 300),
    resolution: {
      sourceName: "Banco de México",
      sourceUrl: "https://www.banxico.org.mx/publicaciones-y-prensa/anuncios-de-las-decisiones-de-politica-monetaria/",
      criterion:
        "Se resuelve Sí si el anuncio de política monetaria de Banxico fija una tasa objetivo menor a la vigente. Se lee del comunicado oficial publicado ese mismo día.",
      settlesAt: "2026-08-13T19:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "mx-dolar-19",
    title: "¿El dólar cierra el mes abajo de 19 pesos?",
    category: "economia",
    country: "MX",
    closesAt: "2026-07-31T21:00:00Z",
    pool: seedPool(300, 480),
    resolution: {
      sourceName: "Banco de México (tipo de cambio FIX)",
      sourceUrl: "https://www.banxico.org.mx/tipcamb/tipCamMIAction.do",
      criterion:
        "Se resuelve Sí si el tipo de cambio FIX que publica Banxico el último día hábil del mes es menor a 19.0000 pesos por dólar.",
      settlesAt: "2026-07-31T21:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "ar-bcra-tasa",
    title: "¿El Banco Central de Argentina baja la tasa este mes?",
    category: "economia",
    country: "AR",
    closesAt: "2026-08-29T20:00:00Z",
    pool: seedPool(640, 240),
    resolution: {
      sourceName: "BCRA",
      sourceUrl: "https://www.bcra.gob.ar/Noticias/Comunicados-de-prensa.asp",
      criterion:
        "Se resuelve Sí si el BCRA comunica una tasa de política monetaria menor a la vigente al abrir el mercado. Se toma del comunicado de prensa oficial.",
      settlesAt: "2026-08-31T20:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "br-selic-corte",
    title: "¿El Copom baja la Selic en la próxima reunión?",
    category: "economia",
    country: "BR",
    closesAt: "2026-09-16T21:00:00Z",
    pool: seedPool(510, 390),
    resolution: {
      sourceName: "Banco Central do Brasil (Copom)",
      sourceUrl: "https://www.bcb.gov.br/controleinflacao/historicotaxasjuros",
      criterion:
        "Se resuelve Sí si la tasa Selic definida por el Copom en su próxima reunión queda por debajo de la vigente, según el histórico oficial del Banco Central.",
      settlesAt: "2026-09-16T21:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "co-inflacion-dane",
    title: "¿La inflación anual de Colombia baja del 5%?",
    category: "economia",
    country: "CO",
    closesAt: "2026-08-08T12:00:00Z",
    pool: seedPool(380, 420),
    resolution: {
      sourceName: "DANE",
      sourceUrl: "https://www.dane.gov.co/index.php/estadisticas-por-tema/precios-y-costos/indice-de-precios-al-consumidor-ipc",
      criterion:
        "Se resuelve Sí si la variación anual del IPC que publica el DANE es menor a 5.00%. Se usa la cifra del boletín técnico oficial.",
      settlesAt: "2026-08-08T12:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "cl-imacec",
    title: "¿El Imacec de Chile crece más de 2% interanual?",
    category: "economia",
    country: "CL",
    closesAt: "2026-08-03T12:00:00Z",
    pool: seedPool(290, 310),
    resolution: {
      sourceName: "Banco Central de Chile",
      sourceUrl: "https://www.bcentral.cl/areas/estadisticas/imacec",
      criterion:
        "Se resuelve Sí si la variación interanual del Imacec publicada por el Banco Central de Chile supera 2.0%. Se toma la primera publicación, no las revisiones.",
      settlesAt: "2026-08-03T12:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "latam-libertadores-br",
    title: "¿Un equipo brasileño gana la Libertadores?",
    category: "deportes",
    country: "LATAM",
    closesAt: "2026-11-28T22:00:00Z",
    pool: seedPool(820, 440),
    resolution: {
      sourceName: "CONMEBOL",
      sourceUrl: "https://www.conmebol.com/libertadores/",
      criterion:
        "Se resuelve Sí si el campeón oficial de la CONMEBOL Libertadores es un club afiliado a la confederación brasileña, según el resultado publicado por CONMEBOL.",
      settlesAt: "2026-11-29T04:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "mx-mundial-grupo",
    title: "¿México pasa la fase de grupos del Mundial?",
    category: "deportes",
    country: "MX",
    closesAt: "2026-06-27T22:00:00Z",
    pool: seedPool(700, 520),
    resolution: {
      sourceName: "FIFA",
      sourceUrl: "https://www.fifa.com/es/tournaments/mens/worldcup",
      criterion:
        "Se resuelve Sí si la selección de México aparece entre los clasificados a la siguiente ronda en la tabla oficial que publica FIFA al cerrar la fase de grupos.",
      settlesAt: "2026-06-28T06:00:00Z",
      disputeWindowHours: 24,
    },
  },
  {
    id: "btc-cierre-semanal",
    title: "¿Bitcoin cierra la semana arriba de 71,000 dólares?",
    category: "cripto",
    country: "LATAM",
    closesAt: "2026-08-02T23:59:00Z",
    pool: seedPool(910, 780),
    // también cotiza afuera: por eso puede tener Edge contra una casa global
    referenceKey: "bitcoin close above 71000",
    resolution: {
      sourceName: "Binance (par BTC/USDT)",
      sourceUrl: "https://www.binance.com/es/trade/BTC_USDT",
      criterion:
        "Se resuelve Sí si la vela semanal de BTC/USDT en Binance cierra el domingo a las 23:59 UTC por encima de 71,000 dólares.",
      settlesAt: "2026-08-02T23:59:00Z",
      disputeWindowHours: 12,
    },
  },
  {
    id: "eth-4500",
    title: "¿Ethereum toca 4,500 dólares antes de octubre?",
    category: "cripto",
    country: "LATAM",
    closesAt: "2026-10-01T00:00:00Z",
    pool: seedPool(340, 690),
    referenceKey: "ethereum above 4500",
    resolution: {
      sourceName: "Binance (par ETH/USDT)",
      sourceUrl: "https://www.binance.com/es/trade/ETH_USDT",
      criterion:
        "Se resuelve Sí si el precio de ETH/USDT en Binance alcanza o supera 4,500 dólares en cualquier momento antes del 1 de octubre a las 00:00 UTC.",
      settlesAt: "2026-10-01T00:00:00Z",
      disputeWindowHours: 12,
    },
  },
  {
    id: "pe-cobre-exportacion",
    title: "¿Perú exporta más cobre este trimestre que el anterior?",
    category: "economia",
    country: "PE",
    closesAt: "2026-10-15T12:00:00Z",
    pool: seedPool(260, 240),
    resolution: {
      sourceName: "Banco Central de Reserva del Perú",
      sourceUrl: "https://estadisticas.bcrp.gob.pe/estadisticas/series/",
      criterion:
        "Se resuelve Sí si el volumen de exportación de cobre del trimestre supera al del trimestre anterior, según las series estadísticas del BCRP.",
      settlesAt: "2026-10-15T12:00:00Z",
      disputeWindowHours: 24,
    },
  },
];

/**
 * Valida el catálogo al cargarlo. Si alguna entrada no declara fuente pública,
 * criterio inequívoco y ventana de disputa, el módulo falla al importarse: es
 * el momento correcto para enterarse, no cuando ya hay gente apostando.
 */
export const OWN_MARKETS: OwnMarketSeed[] = SEEDS.map((seed) => ({
  ...seed,
  resolution: assertPublishable(seed.resolution),
}));

export function findOwnMarket(id: string): OwnMarketSeed | undefined {
  return OWN_MARKETS.find((seed) => seed.id === id);
}
