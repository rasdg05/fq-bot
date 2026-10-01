import { KALSHI_API, type EstadoKalshi } from "@/adapters/oracles/mirrorOracle";
import type { MarketCategory } from "@/domain/types";
import { espejoSeed, probabilidadKalshi, type EspejoCurado } from "./espejos";
import { OUTCOME_LABEL_MAX, type OwnMarketSeed } from "./catalog";

/**
 * Espejos **recurrentes**: preguntas que Kalshi vuelve a abrir cada semana o
 * cada día —la película más vista de Netflix, el #1 del Billboard— y que aquí
 * se crean solas, sin que nadie escriba una entrada por semana.
 *
 * Es la parte rápida del catálogo: se resuelven en días, no en meses, con la
 * misma liquidación pública de Kalshi que los espejos curados (R-073).
 *
 * ## Lo que decide si una semana entra: el libro, no la lista
 *
 * La lista de series es editorial y amplia a propósito; lo que entra cada
 * vuelta lo deciden dos compuertas medidas, y una serie sin libro simplemente
 * no aparece esa semana:
 *
 *  1. **Cada respuesta con precio de verdad** (`probabilidadKalshi`, spread
 *     máximo 0.10). El YouTube diario y el Spotify diario estaban el
 *     2026-10-01 en 0.00/0.95: sin gente adentro.
 *  2. **Un libro coherente**: en un evento de respuestas excluyentes, los
 *     puntos medios de todos sus mercados tienen que sumar cerca de 1. El top
 *     de series de Netflix de esa semana sumaba 0.35 —el favorito real no
 *     tenía mercado o nadie cotizaba—, y normalizarlo habría inflado al
 *     primero de la lista hasta un 60 % que nadie dijo.
 */

export interface SerieRecurrente {
  /** Serie de Kalshi: `KXNETFLIXRANKMOVIEGLOBAL`. */
  serie: string;
  /** Prefijo del id: `netflix-peli` → `k-netflix-peli-26oct05`. */
  clave: string;
  hub: string;
  category: MarketCategory;
  /** `fecha` viene en español: «5 de octubre». */
  titulo: (fecha: string) => string;
  shortTitle: (fecha: string) => string;
  /** Qué publica la fuente, para el criterio: «el Top 10 global de películas de Netflix». */
  queMide: string;
  /** Cuántas respuestas con nombre; el resto va a «Otra». */
  candidatos?: number;
  otra: string;
}

export const SERIES_RECURRENTES: SerieRecurrente[] = [
  {
    serie: "KXNETFLIXRANKMOVIEGLOBAL",
    clave: "netflix-peli",
    hub: "Streaming y música",
    category: "cultura",
    titulo: (f) => `Netflix: ¿cuál es la película #1 del mundo en la semana al ${f}?`,
    shortTitle: () => "Netflix: película #1 semanal",
    queMide: "la película #1 del Top 10 global semanal de Netflix",
    otra: "Otra película",
  },
  {
    serie: "KXNETFLIXRANKSHOWGLOBAL",
    clave: "netflix-serie",
    hub: "Streaming y música",
    category: "cultura",
    titulo: (f) => `Netflix: ¿cuál es la serie #1 del mundo en la semana al ${f}?`,
    shortTitle: () => "Netflix: serie #1 semanal",
    queMide: "la serie #1 del Top 10 global semanal de Netflix",
    otra: "Otra serie",
  },
  {
    serie: "KXTOPSONG",
    clave: "hot100",
    hub: "Streaming y música",
    category: "cultura",
    titulo: (f) => `Billboard Hot 100: ¿qué canción es #1 en la lista del ${f}?`,
    shortTitle: (f) => `Billboard: #1 del ${f}`,
    queMide: "la canción #1 del Billboard Hot 100",
    otra: "Otra canción",
  },
  {
    serie: "KXTOPALBUM",
    clave: "bb200",
    hub: "Streaming y música",
    category: "cultura",
    titulo: (f) => `Billboard 200: ¿qué álbum es #1 en la lista del ${f}?`,
    shortTitle: (f) => `Billboard 200: álbum #1 ${f}`,
    queMide: "el álbum #1 del Billboard 200",
    otra: "Otro álbum",
  },
  {
    serie: "KXSPOTIFYGLOBALD",
    clave: "spotify-global",
    hub: "Streaming y música",
    category: "cultura",
    titulo: (f) => `Spotify: ¿qué canción es #1 del mundo el ${f}?`,
    shortTitle: (f) => `Spotify global: #1 del ${f}`,
    queMide: "la canción #1 de la lista diaria global de Spotify",
    otra: "Otra canción",
  },
  {
    serie: "KXSPOTIFYBRAZILD",
    clave: "spotify-brasil",
    hub: "Streaming y música",
    category: "cultura",
    titulo: (f) => `Spotify Brasil: ¿qué canción es #1 el ${f}?`,
    shortTitle: (f) => `Spotify Brasil: #1 del ${f}`,
    queMide: "la canción #1 de la lista diaria de Spotify en Brasil",
    otra: "Otra canción",
  },
  {
    serie: "KXYTDAILYTOPVIDEO",
    clave: "youtube-video",
    hub: "Streaming y música",
    category: "cultura",
    titulo: (f) => `YouTube: ¿qué video musical es #1 en EE.UU. el ${f}?`,
    shortTitle: (f) => `YouTube: video #1 del ${f}`,
    queMide: "el video #1 de la lista diaria de videos musicales de YouTube en EE.UU.",
    otra: "Otro video",
  },
];

/** Un evento de Kalshi con sus mercados, tal como lo devuelve `/events`. */
export interface EventoKalshi {
  event_ticker: string;
  title?: string;
  mutually_exclusive?: boolean;
  markets?: (EstadoKalshi & { yes_sub_title?: string; close_time?: string })[];
}

const MESES = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
const MESES_ES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

/** `KXTOPSONG-26OCT10` → `2026-10-10`. Sólo el formato canónico de fecha. */
export function fechaDeEvento(evento: string): string | undefined {
  const m = /-(\d{2})([A-Z]{3})(\d{2})$/.exec(evento);
  if (!m) return undefined;
  const mes = MESES.indexOf(m[2]);
  if (mes < 0) return undefined;
  return `20${m[1]}-${String(mes + 1).padStart(2, "0")}-${m[3]}`;
}

/** `2026-10-10` → «10 de octubre». */
export function fechaEnEspanol(iso: string): string {
  const [, mes, dia] = iso.split("-").map(Number);
  return `${dia} de ${MESES_ES[mes - 1]}`;
}

/** «10 oct.», para títulos cortos. */
function fechaCorta(iso: string): string {
  const [, mes, dia] = iso.split("-").map(Number);
  return `${dia} ${MESES_ES[mes - 1].slice(0, 3)}.`;
}

/**
 * La etiqueta de una respuesta a partir del nombre que publica Kalshi. Sin la
 * temporada («: Season 1») y, si no cabe, cortada con elipsis: el nombre entero
 * va en el criterio, que es donde se cita.
 */
export function etiquetaDe(nombre: string): string {
  const limpio = nombre.replace(/:\s*Season\s+\d+$/i, "").replace(/\s+/g, " ").trim();
  return limpio.length <= OUTCOME_LABEL_MAX ? limpio : `${limpio.slice(0, OUTCOME_LABEL_MAX - 1).trimEnd()}…`;
}

/** Margen de la compuerta de coherencia: los puntos medios suman 1 ± esto. */
export const COHERENCIA = 0.2;
/** Se cierra una hora antes que Kalshi: el dato no se publica hasta después. */
const CIERRE_ANTES_MS = 60 * 60_000;
/** No se abre algo que viviría menos de esto: no da tiempo de entrar. */
const VIDA_MINIMA_MS = 2 * 60 * 60_000;
/** Ni algo que cierra en más de esto: lo recurrente es lo rápido. */
const HORIZONTE_MS = 8 * 24 * 60 * 60_000;

/**
 * El espejo de un evento recurrente, o el motivo por el que no se crea. Puro:
 * lo que decide está todo en los argumentos.
 */
export function recurrenteDe(
  serie: SerieRecurrente,
  evento: EventoKalshi,
  ahora: number,
): { seed: OwnMarketSeed } | { motivo: string } {
  const fecha = fechaDeEvento(evento.event_ticker);
  if (!fecha || !evento.event_ticker.startsWith(`${serie.serie}-`)) {
    return { motivo: "no es un evento con fecha de la serie" };
  }
  const mercados = (evento.markets ?? []).filter((m) => m.status === "active");
  const cierreKalshi = Math.min(
    ...mercados.map((m) => Date.parse(m.close_time ?? "")).filter(Number.isFinite),
  );
  if (!Number.isFinite(cierreKalshi)) return { motivo: "sin mercados activos" };
  const cierre = cierreKalshi - CIERRE_ANTES_MS;
  if (cierre - ahora < VIDA_MINIMA_MS) return { motivo: "cierra demasiado pronto" };
  if (cierre - ahora > HORIZONTE_MS) return { motivo: "todavía lejos" };

  // compuerta 2: el libro entero tiene que contar una historia coherente
  const precios = mercados.map((m) => ({ m, p: probabilidadKalshi(m) }));
  const conPrecio = precios.filter((x): x is { m: (typeof precios)[number]["m"]; p: number } => x.p !== undefined);
  const suma = conPrecio.reduce((s, x) => s + x.p, 0);
  if (Math.abs(suma - 1) > COHERENCIA) {
    return { motivo: `libro incoherente: los precios suman ${suma.toFixed(2)}` };
  }

  // compuerta 1: los candidatos con nombre, todos con precio de verdad. Un
  // contendiente sin precio (ask alto, bid en cero) no se esconde en «Otra»
  const contendientes = mercados.filter((m) => Number(m.yes_ask_dollars ?? 0) >= 0.15);
  if (contendientes.some((m) => probabilidadKalshi(m) === undefined)) {
    return { motivo: "un contendiente no tiene precio de verdad" };
  }
  const elegidos = conPrecio
    .sort((a, b) => b.p - a.p)
    .slice(0, serie.candidatos ?? 3)
    .filter((x) => x.p >= 0.01);
  if (elegidos.length < 1) return { motivo: "nadie cotiza" };

  const nombres = elegidos.map((x) => x.m.yes_sub_title?.trim() || x.m.ticker);
  const etiquetas = nombres.map(etiquetaDe);
  if (new Set(etiquetas).size !== etiquetas.length) return { motivo: "dos respuestas se llamarían igual" };

  const sufijo = evento.event_ticker.slice(serie.serie.length + 1).toLowerCase();
  const curado: EspejoCurado = {
    id: `k-${serie.clave}-${sufijo}`,
    evento: evento.event_ticker,
    category: serie.category,
    country: "GLOBAL",
    hub: serie.hub,
    title: serie.titulo(fechaEnEspanol(fecha)),
    shortTitle: serie.shortTitle(fechaCorta(fecha)),
    closesAt: new Date(cierre).toISOString(),
    // Kalshi liquida cuando la fuente publica; tres días cubren el martes de
    // Netflix y el lunes de Billboard. Si tarda más, el plazo anula y devuelve
    settlesAt: new Date(cierreKalshi + 3 * 24 * 60 * 60_000).toISOString(),
    criterio:
      `Se resuelve con el evento ${evento.event_ticker} de Kalshi sobre ${serie.queMide} ` +
      `(${fechaEnEspanol(fecha)} de ${fecha.slice(0, 4)}): gana ` +
      nombres.map((n, i) => `«${n}» si Kalshi liquida en «sí» el mercado ${elegidos[i].m.ticker}`).join("; ") +
      `. ${serie.otra} si Kalshi no liquida ninguno de esos. Las apuestas cierran una hora antes que en Kalshi.`,
    respuestas: [
      ...elegidos.map((x, i) => ({ id: `r${i + 1}`, label: etiquetas[i], tickers: [x.m.ticker] })),
      { id: "otra", label: serie.otra, tickers: [] },
    ],
  };
  const seed = espejoSeed(curado, new Map(mercados.map((m) => [m.ticker, m])));
  return seed ? { seed } : { motivo: "sin precio para alguna respuesta" };
}

export function urlEventosDeSerie(serie: string): string {
  return `${KALSHI_API}/events?series_ticker=${encodeURIComponent(serie)}&status=open&with_nested_markets=true&limit=20`;
}

export async function cargarEventosDeSerie(fetchImpl: typeof fetch, serie: string): Promise<EventoKalshi[]> {
  const respuesta = await fetchImpl(urlEventosDeSerie(serie));
  if (!respuesta.ok) throw new Error(`Kalshi respondió ${respuesta.status} para ${serie}`);
  const cuerpo = (await respuesta.json()) as { events?: EventoKalshi[] };
  return cuerpo.events ?? [];
}

/**
 * Los recurrentes que faltan. Una serie que ya tiene uno abierto no se vuelve
 * a pedir: con siete series y un ciclo cada cuarto de hora, pedir siempre sería
 * hablarle a Kalshi 670 veces al día para crear siete mercados a la semana.
 */
export async function recurrentesPendientes(input: {
  ahora: number;
  existentes: ReadonlySet<string>;
  /** Ids de los que siguen aceptando apuestas. */
  abiertos?: ReadonlySet<string>;
  cargarSerie?: (serie: string) => Promise<EventoKalshi[]>;
  series?: SerieRecurrente[];
  /**
   * Pausa entre series. Medido el 2026-10-01: siete pedidos en ráfaga junto
   * con los curados dieron 429 en cuatro. Uno a la vez y espaciados, no.
   */
  pausaMs?: number;
}): Promise<{ seeds: OwnMarketSeed[]; errores: string[]; omitidos: string[] }> {
  const cargar = input.cargarSerie ?? ((s: string) => cargarEventosDeSerie(fetch, s));
  const series = input.series ?? SERIES_RECURRENTES;
  const abiertos = input.abiertos ?? new Set<string>();
  const seeds: OwnMarketSeed[] = [];
  const errores: string[] = [];
  const omitidos: string[] = [];

  const pausaMs = input.pausaMs ?? 400;
  let pedidos = 0;
  for (const serie of series) {
    const prefijo = `k-${serie.clave}-`;
    if ([...abiertos].some((id) => id.startsWith(prefijo))) continue;
    if (pedidos++ > 0 && pausaMs > 0) await new Promise((r) => setTimeout(r, pausaMs));
    let eventos: EventoKalshi[];
    try {
      eventos = await cargar(serie.serie);
    } catch (error) {
      errores.push(`${serie.clave}: ${error instanceof Error ? error.message : String(error)}`);
      continue;
    }
    // el que cierra primero y todavía da tiempo de entrar
    const ordenados = eventos
      .filter((e) => fechaDeEvento(e.event_ticker) && e.event_ticker.startsWith(`${serie.serie}-`))
      // por fecha real: `26AUG` va antes que `26APR` en orden alfabético
      .sort((a, b) => fechaDeEvento(a.event_ticker)!.localeCompare(fechaDeEvento(b.event_ticker)!));
    let creado = false;
    const motivos: string[] = [];
    for (const evento of ordenados) {
      const r = recurrenteDe(serie, evento, input.ahora);
      if ("seed" in r) {
        if (!input.existentes.has(r.seed.id)) seeds.push(r.seed);
        creado = true;
        break;
      }
      motivos.push(`${evento.event_ticker}: ${r.motivo}`);
    }
    if (!creado) omitidos.push(`${serie.clave}: ${motivos.join("; ") || "sin eventos abiertos"}`);
  }
  return { seeds, errores, omitidos };
}
