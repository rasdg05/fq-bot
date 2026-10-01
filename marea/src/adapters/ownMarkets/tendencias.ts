import { assertPublishable } from "@/domain/resolution";
import { SEED, declareSeed } from "@/domain/parimutuel";
import type { TrendRule } from "@/domain/oracleRule";
import { WIKIMEDIA_API, WIKIMEDIA_UA, urlVisitas } from "@/adapters/oracles/trendOracle";
import { OUTCOME_LABEL_MAX, SHORT_TITLE_IDEAL, type OwnMarketSeed } from "./catalog";

/**
 * Duelos de tendencias: «¿quién tendrá más visitas mañana en Wikipedia en
 * español: A o B?». Los candidatos salen del top de visitas del último día
 * publicado, y se emparejan por rangos vecinos para que el duelo esté parejo.
 *
 * ## Lo que no se pregunta (regla editorial, medida)
 *
 * El 30 de septiembre de 2026 el top traía a una mujer ejecutada esa semana,
 * dos personas recién fallecidas y tres asesinos de una serie de true crime. Un
 * mercado sobre la atención a una muerte o a un crimen no se publica, aunque
 * sea el tema del día. Se lee el resumen público de cada artículo y se excluye:
 *
 *  - lo que no es un artículo (portada, búsqueda, anexos, desambiguaciones);
 *  - lo que la propia Wikipedia narra en pasado («fue un actor…»): personas
 *    fallecidas y figuras históricas. Es conservador a propósito;
 *  - lo que menciona crimen, violencia o sexo.
 *
 * ## Cuándo
 *
 * Se pregunta por **mañana** (día UTC) y se cierra a su medianoche: nadie
 * apuesta con el día corriendo. La semilla sigue las visitas del día de los
 * candidatos —el dato público más cercano—, no un 50/50.
 */

const PREFIJOS_NO_ARTICULO = /^(Wikipedia|Especial|Anexo|Archivo|Categoría|Portal|Ayuda|Usuario|Plantilla|Wikiproyecto|Discusión|MediaWiki|Módulo):/i;
const PORTADAS = new Set(["Wikipedia:Portada", "Portada", "Main_Page", "-"]);
const SENSIBLE =
  /asesin|homicid|crimen|criminal|terroris|masacre|atentado|tiroteo|suicid|violaci|abuso|sexual|porno|desnud|secuestr|narcotrafic|ejecutad|condenad|feminicid|genocid|holocausto|guerra|muert|falleci/i;

export interface ArticuloTop {
  article: string;
  views: number;
  rank: number;
}

export interface ResumenWiki {
  type?: string;
  description?: string;
  extract?: string;
}

/** ¿Se puede preguntar por este artículo? Puro, para probarlo con casos reales. */
export function esCandidato(titulo: string, resumen: ResumenWiki | undefined): boolean {
  if (PORTADAS.has(titulo) || PREFIJOS_NO_ARTICULO.test(titulo)) return false;
  if (!resumen || resumen.type !== "standard") return false;
  const texto = `${resumen.description ?? ""} ${resumen.extract ?? ""}`;
  if (SENSIBLE.test(texto)) return false;
  // «X fue un …»: la propia Wikipedia lo narra en pasado
  if (/^[^.]{0,120}?\bfue (un|una)\b/i.test(resumen.extract ?? "")) return false;
  return true;
}

/** «La_bola_negra_(película)» → «La bola negra». */
export function nombreLegible(titulo: string): string {
  return titulo.replace(/_/g, " ").replace(/\s*\([^)]*\)\s*$/, "").trim();
}

function etiqueta(titulo: string): string {
  const nombre = nombreLegible(titulo);
  return nombre.length <= OUTCOME_LABEL_MAX ? nombre : `${nombre.slice(0, OUTCOME_LABEL_MAX - 1).trimEnd()}…`;
}

const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];
const enEspanol = (iso: string) => {
  const [, m, d] = iso.split("-").map(Number);
  return `${d} de ${MESES[m - 1]}`;
};

/** Pozo inicial de un duelo, en puntos. */
export const POZO_DUELO = SEED * 4;

/**
 * El mercado de un duelo. `visitas` son las del día de referencia: la semilla
 * reparte el pozo en esa proporción, con un piso del 15 % para que ningún lado
 * nazca pagando casi nada.
 */
export function dueloSeed(input: {
  numero: number;
  fecha: string;
  a: ArticuloTop;
  b: ArticuloTop;
  diaReferencia: string;
}): OwnMarketSeed {
  const { fecha, a, b } = input;
  const total = a.views + b.views;
  const pa = Math.min(0.85, Math.max(0.15, total > 0 ? a.views / total : 0.5));
  const nombreA = nombreLegible(a.article);
  const nombreB = nombreLegible(b.article);
  const corto = `${nombreA} vs ${nombreB}`;
  const rule: TrendRule = {
    kind: "tendencia",
    fuente: "wikipedia",
    proyecto: "es.wikipedia",
    fecha,
    articulos: [
      { id: "a", titulo: a.article },
      { id: "b", titulo: b.article },
    ],
  };
  const cierre = `${fecha}T00:00:00.000Z`;

  return {
    id: `wiki-${fecha}-${input.numero}`,
    title: `Tendencias: ¿quién tendrá más visitas en Wikipedia el ${enEspanol(fecha)}, ${nombreA} o ${nombreB}?`,
    // si los nombres no caben, la pregunta: las pastillas ya dicen quiénes son.
    // «mañana» es exacto mientras está abierto: cierra a las 18:00 de la CDMX
    // del día anterior al que se mide
    shortTitle: corto.length <= SHORT_TITLE_IDEAL ? corto : "¿Quién será más visto mañana?",
    category: "cultura",
    country: "LATAM",
    liga: "Tendencias",
    closesAt: cierre,
    outcomes: [
      { id: "a", label: etiqueta(a.article) },
      { id: "b", label: etiqueta(b.article) },
    ],
    pool: declareSeed(
      {
        outcomes: { a: Math.round(POZO_DUELO * pa), b: Math.round(POZO_DUELO * (1 - pa)) },
        feeBps: 300,
      },
      "apuesta",
    ),
    rule,
    resolution: assertPublishable({
      sourceName: "Wikimedia (visitas diarias de Wikipedia en español, API pública)",
      sourceUrl: urlVisitas(a.article, fecha, fecha),
      criterion:
        `Se resuelve con las visitas del ${enEspanol(fecha)} de ${fecha.slice(0, 4)} (día UTC) a dos artículos ` +
        `de Wikipedia en español, según la API pública de Wikimedia (agente user, todos los accesos): ` +
        `«${a.article}» y «${b.article}». Gana el que tenga más visitas ese día. Empate exacto: gana el que ` +
        `tuvo más visitas el día anterior. Un día sin visitas no aparece en la API y cuenta como cero. ` +
        `Las apuestas cierran a las 00:00 UTC de ese día. La semilla sigue las visitas del ${enEspanol(input.diaReferencia)}.`,
      // Wikimedia publica el día horas después; un día y medio deja margen
      settlesAt: new Date(Date.parse(cierre) + 36 * 3_600_000).toISOString(),
      disputeWindowHours: 12,
    }),
  };
}

/** `YYYY-MM-DD` de un instante, en UTC. */
const diaUtc = (ms: number) => new Date(ms).toISOString().slice(0, 10);

export interface FuentesTendencias {
  /** Top de visitas de un día. `undefined` si aún no está publicado. */
  top: (dia: string) => Promise<ArticuloTop[] | undefined>;
  /** Resumen público de un artículo. `undefined` si no se pudo leer. */
  resumen: (titulo: string) => Promise<ResumenWiki | undefined>;
}

export function fuentesWikimedia(fetchImpl: typeof fetch = fetch, pausaMs = 900): FuentesTendencias {
  const pausa = () => new Promise((r) => setTimeout(r, pausaMs));
  const headers = { "User-Agent": WIKIMEDIA_UA };
  return {
    async top(dia) {
      const [y, m, d] = dia.split("-");
      const r = await fetchImpl(`${WIKIMEDIA_API}/top/es.wikipedia/all-access/${y}/${m}/${d}`, { headers });
      if (r.status === 404) return undefined;
      if (!r.ok) throw new Error(`Wikimedia respondió ${r.status}`);
      const cuerpo = (await r.json()) as { items?: { articles?: ArticuloTop[] }[] };
      return cuerpo.items?.[0]?.articles ?? [];
    },
    async resumen(titulo) {
      await pausa();
      const r = await fetchImpl(
        `https://es.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(titulo)}`,
        { headers },
      );
      if (!r.ok) return undefined;
      try {
        return (await r.json()) as ResumenWiki;
      } catch {
        return undefined;
      }
    },
  };
}

/**
 * Los duelos de mañana que faltan. Idempotente: el id sale de la fecha y del
 * número de duelo, y si ya existe el primero de mañana no se vuelve a pedir
 * nada a Wikimedia.
 */
export async function tendenciasPendientes(input: {
  ahora: number;
  existentes: ReadonlySet<string>;
  fuentes?: FuentesTendencias;
  duelos?: number;
}): Promise<{ seeds: OwnMarketSeed[]; errores: string[] }> {
  const fuentes = input.fuentes ?? fuentesWikimedia();
  const duelos = input.duelos ?? 3;
  const manana = diaUtc(input.ahora + 86_400_000);
  const errores: string[] = [];
  if (input.existentes.has(`wiki-${manana}-1`)) return { seeds: [], errores };
  // si cierra en menos de tres horas, no da tiempo de entrar: mañana se abre el siguiente
  if (Date.parse(`${manana}T00:00:00Z`) - input.ahora < 3 * 3_600_000) return { seeds: [], errores };

  // el último día publicado: ayer, o anteayer si ayer todavía no está
  let top: ArticuloTop[] | undefined;
  let referencia = "";
  for (const atras of [1, 2]) {
    referencia = diaUtc(input.ahora - atras * 86_400_000);
    try {
      top = await fuentes.top(referencia);
    } catch (error) {
      errores.push(`tendencias: ${error instanceof Error ? error.message : String(error)}`);
      return { seeds: [], errores };
    }
    if (top && top.length > 0) break;
  }
  if (!top || top.length === 0) return { seeds: [], errores: [...errores, "tendencias: Wikimedia sin top publicado"] };

  const elegidos: ArticuloTop[] = [];
  for (const articulo of top.slice(0, 40)) {
    if (elegidos.length >= duelos * 2) break;
    if (PORTADAS.has(articulo.article) || PREFIJOS_NO_ARTICULO.test(articulo.article)) continue;
    if (esCandidato(articulo.article, await fuentes.resumen(articulo.article))) elegidos.push(articulo);
  }

  const seeds: OwnMarketSeed[] = [];
  for (let i = 0; i + 1 < elegidos.length && seeds.length < duelos; i += 2) {
    const seed = dueloSeed({ numero: seeds.length + 1, fecha: manana, a: elegidos[i], b: elegidos[i + 1], diaReferencia: referencia });
    if (!input.existentes.has(seed.id)) seeds.push(seed);
  }
  return { seeds, errores };
}
