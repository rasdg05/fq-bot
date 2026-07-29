import type { Market } from "@/domain/types";
import { withEdge } from "@/domain/edge";

type RawMarket = Omit<Market, "edge">;

/**
 * Datos simulados con forma de agregación real: mismo contrato que va a
 * entregar el adapter de producción, para que cambiar la fuente no toque la UI.
 * Incluye a propósito mercados con diferencia < 4 pp, que NO deben mostrar
 * Edge (R-001), y mercados sin lectura propia de Marea.
 */
const RAW: RawMarket[] = [
  {
    id: "mx-inflacion-jul",
    title: "¿La inflación de México cierra julio abajo de 4.0%?",
    shortTitle: "Inflación de México abajo de 4 % en julio",
    probability: 0.62,
    mareaProbability: 0.69,
    volume: 184_300,
    status: "open",
    category: "economia",
    region: "latam",
    hot: true,
    closesAt: "2026-08-07T14:00:00Z",
    resolution_summary:
      "Se resuelve con el dato de INPC anual que publica el INEGI el 7 de agosto.",
  },
  {
    id: "btc-cierre-semana",
    title: "¿Bitcoin cierra la semana arriba de $71,000?",
    shortTitle: "Bitcoin cierra la semana arriba de 71 mil",
    probability: 0.48,
    mareaProbability: 0.585,
    volume: 921_400,
    status: "live",
    category: "cripto",
    region: "global",
    hot: true,
    closesAt: "2026-08-02T23:59:00Z",
    resolution_summary:
      "Se resuelve con el cierre semanal de BTC/USDT en Binance, domingo 23:59 UTC.",
  },
  {
    id: "arg-tasa-agosto",
    title: "¿El Banco Central de Argentina baja la tasa en agosto?",
    shortTitle: "Argentina baja la tasa en agosto",
    probability: 0.71,
    mareaProbability: 0.74,
    volume: 96_800,
    status: "open",
    category: "economia",
    region: "latam",
    closesAt: "2026-08-29T20:00:00Z",
    resolution_summary:
      "Se resuelve con el comunicado oficial del BCRA sobre la tasa de política monetaria.",
  },
  {
    id: "libertadores-final",
    title: "¿Un equipo brasileño gana la Libertadores?",
    shortTitle: "Un equipo brasileño gana la Libertadores",
    probability: 0.66,
    mareaProbability: 0.58,
    volume: 412_500,
    status: "open",
    category: "deportes",
    region: "latam",
    hot: true,
    closesAt: "2026-11-28T22:00:00Z",
    resolution_summary:
      "Se resuelve con el resultado oficial de la final publicado por CONMEBOL.",
  },
  {
    id: "eth-flippening",
    title: "¿ETH supera los $4,500 antes de octubre?",
    shortTitle: "ETH supera los 4,500 antes de octubre",
    probability: 0.34,
    mareaProbability: 0.355,
    volume: 288_100,
    status: "open",
    category: "cripto",
    region: "global",
    closesAt: "2026-10-01T00:00:00Z",
    resolution_summary:
      "Se resuelve si el precio de ETH/USDT en Binance toca $4,500 antes del 1 de octubre.",
  },
  {
    id: "col-elecciones-2t",
    title: "¿Habrá segunda vuelta en las presidenciales de Colombia?",
    shortTitle: "Hay segunda vuelta en Colombia",
    probability: 0.78,
    mareaProbability: 0.84,
    volume: 156_900,
    status: "open",
    category: "politica",
    region: "latam",
    closesAt: "2026-05-31T23:00:00Z",
    resolution_summary:
      "Se resuelve con el conteo oficial de la Registraduría Nacional.",
  },
  {
    id: "peso-mxn-19",
    title: "¿El dólar cierra el mes abajo de 19 pesos?",
    shortTitle: "El dólar cierra el mes abajo de 19 pesos",
    probability: 0.41,
    mareaProbability: 0.33,
    volume: 233_400,
    status: "closing_soon",
    category: "economia",
    region: "latam",
    closesAt: "2026-07-31T21:00:00Z",
    resolution_summary:
      "Se resuelve con el tipo de cambio FIX que publica Banxico el último día hábil del mes.",
  },
  {
    id: "premios-latam",
    title: "¿Una película latinoamericana gana Mejor Película Internacional?",
    shortTitle: "Una latina gana Mejor Internacional",
    probability: 0.29,
    volume: 61_200,
    status: "open",
    category: "cultura",
    region: "latam",
    closesAt: "2027-03-14T02:00:00Z",
    resolution_summary:
      "Se resuelve con el anuncio oficial de la Academia en la ceremonia.",
  },
  {
    id: "sol-ath",
    title: "¿Solana hace nuevo máximo histórico este trimestre?",
    shortTitle: "Solana hace nuevo máximo este trimestre",
    probability: 0.22,
    mareaProbability: 0.31,
    volume: 174_600,
    status: "live",
    category: "cripto",
    region: "global",
    hot: true,
    closesAt: "2026-09-30T23:59:00Z",
    resolution_summary:
      "Se resuelve si SOL/USDT en Binance supera su máximo histórico antes del cierre del trimestre.",
  },
  {
    id: "chile-crecimiento",
    title: "¿Chile crece más de 2.5% este año?",
    shortTitle: "Chile crece más de 2.5 % este año",
    probability: 0.55,
    mareaProbability: 0.52,
    volume: 88_700,
    status: "open",
    category: "economia",
    region: "latam",
    closesAt: "2027-03-18T13:00:00Z",
    resolution_summary:
      "Se resuelve con la cifra anual de PIB que publica el Banco Central de Chile.",
  },
  {
    id: "mundial-sede",
    title: "¿México gana su grupo en el próximo Mundial?",
    shortTitle: "México gana su grupo en el Mundial",
    probability: 0.37,
    mareaProbability: 0.45,
    volume: 507_300,
    status: "open",
    category: "deportes",
    region: "latam",
    hot: true,
    closesAt: "2026-06-27T22:00:00Z",
    resolution_summary:
      "Se resuelve con la tabla oficial del grupo publicada por FIFA al terminar la fase.",
  },
  {
    id: "brl-estabilidad",
    title: "¿El real brasileño termina el mes abajo de 5.20 por dólar?",
    shortTitle: "El real cierra el mes abajo de 5.20",
    probability: 0.44,
    mareaProbability: 0.46,
    volume: 119_500,
    status: "open",
    category: "economia",
    region: "latam",
    closesAt: "2026-07-31T21:00:00Z",
    resolution_summary:
      "Se resuelve con la cotización PTAX de cierre que publica el Banco Central de Brasil.",
  },
];

/**
 * Los dos partidos en vivo de la build simulada. Van aparte de `RAW` porque
 * traen marcador estructurado y ya nacen con `edge: null`: aquí no hay lectura
 * externa contra la que comparar, y no se inventa una.
 */
const VIVOS: Market[] = [
  {
    id: "atp-alcaraz-zverev",
    title: "¿Alcaraz le gana a Zverev?",
    shortTitle: "Alcaraz le gana a Zverev",
    probability: 0.71,
    volume: 5900,
    status: "live",
    category: "deportes",
    edge: null,
    region: "latam",
    hot: true,
    participantes: 142,
    marcadorVivo: {
      deporte: "tenis",
      jugadores: ["Alcaraz", "Zverev"],
      sets: [
        [6, 3],
        [4, 6],
        [2, 1],
      ],
      saque: 0,
      game: "40-30",
    },
    eventoReciente: { tipo: "quiebre", hace: 2 },
    resolution_summary:
      "Se resuelve con el ganador que publique la ATP en el marcador oficial del cuadro.",
  },
  {
    id: "lmp-naranjeros-tomateros",
    title: "¿Los Naranjeros le ganan a los Tomateros?",
    shortTitle: "Naranjeros le ganan a Tomateros",
    probability: 0.64,
    volume: 2860,
    status: "live",
    category: "deportes",
    edge: null,
    region: "latam",
    country: "MX",
    participantes: 71,
    marcadorVivo: {
      deporte: "beisbol",
      equipos: ["Naranjeros", "Tomateros"],
      carreras: [4, 3],
      entrada: 7,
      mitad: "alta",
      outs: 2,
      bases: "1ª y 3ª",
    },
    eventoReciente: { tipo: "carrera", hace: 3 },
    resolution_summary:
      "Se resuelve con el marcador final que publica la Liga Mexicana del Pacífico.",
  },
];

export const MOCK_MARKETS: Market[] = [...VIVOS, ...RAW.map(withEdge)];

export function findMockMarket(id: string): Market | undefined {
  return MOCK_MARKETS.find((market) => market.id === id);
}
