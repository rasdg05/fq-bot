import { assertPublishable } from "@/domain/resolution";
import { FRESCURA_MAX_HORAS } from "@/domain/settlement";
import { SEED, binaryPool, declareSeed, type Pool } from "@/domain/parimutuel";
import {
  KRAKEN_PAR,
  type MatchOutcomeRule,
  type MatchRule,
  type ParCripto,
  type PriceRule,
} from "@/domain/oracleRule";
import { ligaDe, urlJornadaEspn, type LigaId } from "@/domain/ligas";
import { OUTCOME_LABEL_MAX, SHORT_TITLE_MAX, type OwnMarketSeed } from "./catalog";

/**
 * Mercados que se reponen solos.
 *
 * Un catálogo con fechas fijas caduca (R-041): el que escribimos a mano vence
 * y el feed se vacía sin que nadie se entere. Estas plantillas generan las
 * preguntas de cada semana a partir del precio del día, con umbrales redondos
 * que la gente entiende.
 *
 * Se generan sólo para lo que el oráculo sabe leer por programa: una pregunta
 * que se crea sola pero que necesita a una persona para resolverse mueve el
 * problema, no lo arregla.
 *
 * El precio de referencia entra como dato, no se adivina: sin precio no hay
 * mercado. Un umbral inventado sería una pregunta sin sentido.
 */

const DIA_MS = 86_400_000;
const FEE_BPS = 300;
/** Entre el cierre de apuestas y la resolución. Ver R-043. */
const CIERRE_ANTES_MS = 24 * 3_600_000;

export type SpotPrices = Partial<Record<ParCripto, number>>;

/** Redondeo a un número que se dice en voz alta: 71,000, no 70,842. */
function nivelRedondo(precio: number, paso: number): number {
  // el paso de DOGE es medio centavo: sin recortar, 0.1 + 0.005 da colas de
  // coma flotante que acabarían escritas en el criterio publicado
  const decimales = Math.max(0, -Math.floor(Math.log10(paso)) + 1);
  return Number((Math.round(precio / paso) * paso).toFixed(decimales));
}

function conSeparador(valor: number): string {
  return valor.toLocaleString("en-US");
}

/**
 * El umbral como se dice en voz alta y como cabe en la etiqueta de un
 * resultado: `71k`, no `71,000`. La tarjeta le da unos 13 caracteres a cada
 * lado, y "Arriba de 71,000" no entra — se recortaba justo en el número, que
 * es lo único que no se puede recortar.
 */
function nivelCorto(valor: number): string {
  if (valor >= 1000) {
    const miles = valor / 1000;
    return `${Number.isInteger(miles) ? miles : miles.toFixed(1)}k`;
  }
  return conSeparador(valor);
}

/** Próximo domingo a las 23:59 UTC, en cuya vela diaria se lee el cierre. */
export function proximoCierreSemanal(now: number): number {
  const fecha = new Date(now);
  const diasAlDomingo = (7 - fecha.getUTCDay()) % 7 || 7;
  const domingo = new Date(
    Date.UTC(
      fecha.getUTCFullYear(),
      fecha.getUTCMonth(),
      fecha.getUTCDate() + diasAlDomingo,
      23,
      59,
      0,
    ),
  );
  return domingo.getTime();
}

/**
 * Los mercados generados nacen con la semilla **declarada** y en modo
 * `"apuesta"`, igual que el catálogo estático.
 *
 * R-067 pide que la liquidez de la casa sea subsidio, pero pide subsidio
 * declarado **con tope**, y el tope todavía no existe (es `domain/presupuesto.ts`,
 * fase L9). Encender el subsidio antes que el freno sería comprometer un coste
 * por mercado sin nada que lo apague, que es la mitad de la regla y la mitad
 * cara. Un tope que no apaga nada es un comentario.
 *
 * Lo que sí cambia hoy: la semilla queda **registrada**. Sin ese registro, media
 * hora después de abrir el mercado ya no se puede saber cuánto del pozo es de la
 * casa — y eso es justo lo que el presupuesto de L9 va a tener que sumar.
 */
function seedPool(si: number, no: number): Pool {
  return declareSeed(binaryPool(si, no, FEE_BPS), "apuesta");
}

interface Plantilla {
  id: string;
  activo: string;
  par: PriceRule["par"];
  nombre: string;
  paso: number;
}

const PLANTILLAS: Plantilla[] = [
  { id: "btc", activo: "BTC", par: "BTC/USD", nombre: "Bitcoin", paso: 1_000 },
  { id: "eth", activo: "ETH", par: "ETH/USD", nombre: "Ethereum", paso: 100 },
  { id: "sol", activo: "SOL", par: "SOL/USD", nombre: "Solana", paso: 5 },
  { id: "xrp", activo: "XRP", par: "XRP/USD", nombre: "XRP", paso: 0.05 },
  { id: "doge", activo: "DOGE", par: "DOGE/USD", nombre: "Dogecoin", paso: 0.005 },
];

const KRAKEN_DOC = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440";

function urlKraken(par: PriceRule["par"]): string {
  return `https://api.kraken.com/0/public/OHLC?pair=${KRAKEN_PAR[par]}&interval=1440`;
}

/** Mercado de cierre semanal: la pregunta más simple que existe sobre precio. */
function cierreSemanal(
  plantilla: Plantilla,
  spot: number,
  now: number,
): OwnMarketSeed {
  const settlesAtMs = proximoCierreSemanal(now);
  const settlesAt = new Date(settlesAtMs).toISOString();
  const umbral = nivelRedondo(spot, plantilla.paso);
  const semana = settlesAt.slice(0, 10);

  const rule: PriceRule = {
    kind: "precio",
    par: plantilla.par,
    umbral,
    comparacion: "arriba",
    modo: "cierre",
  };

  return {
    id: `${plantilla.id}-cierre-${semana}`,
    title: `¿${plantilla.nombre} cierra la semana arriba de ${conSeparador(umbral)} dólares?`,
    shortTitle: `${plantilla.nombre} arriba de ${conSeparador(umbral)} el domingo`,
    // los dos lados se llaman por lo que son. "Sí" y "No" no dicen de qué lado
    // está uno cuando la pregunta ya no está a la vista (§3.3 del rediseño)
    outcomes: [
      { id: "si", label: `Arriba de ${nivelCorto(umbral)}` },
      { id: "no", label: `Abajo de ${nivelCorto(umbral)}` },
    ],
    category: "cripto",
    country: "LATAM",
    closesAt: new Date(settlesAtMs - CIERRE_ANTES_MS).toISOString(),
    pool: seedPool(SEED * 5, SEED * 5),
    referenceKey: `${plantilla.nombre.toLowerCase()} above ${umbral}`,
    rule,
    resolution: {
      sourceName: "Kraken (velas diarias públicas)",
      sourceUrl: urlKraken(plantilla.par),
      criterion: `Se resuelve Sí si la vela diaria de ${plantilla.par} en Kraken correspondiente al domingo ${semana} cierra por encima de ${conSeparador(
        umbral,
      )} dólares. Se lee del endpoint público de Kraken, que cualquiera puede consultar.`,
      settlesAt,
      disputeWindowHours: 12,
      // vela diaria de Kraken / marcador de ESPN: fuentes que laten a diario,
      // así que aquí el reloj SÍ dice si el colector sigue vivo (L8)
      maxAgeHours: FRESCURA_MAX_HORAS,
    },
  };
}

/** Mercado de toque: resuelve en cuanto el precio llega, no al vencer. */
function tocaEnElMes(plantilla: Plantilla, spot: number, now: number): OwnMarketSeed {
  const settlesAtMs = now + 30 * DIA_MS;
  const settlesAt = new Date(settlesAtMs).toISOString();
  const umbral = nivelRedondo(spot * 1.08, plantilla.paso);
  const desde = new Date(now).toISOString();

  const rule: PriceRule = {
    kind: "precio",
    par: plantilla.par,
    umbral,
    comparacion: "arriba",
    modo: "toca",
    desde,
  };

  return {
    id: `${plantilla.id}-toca-${desde.slice(0, 10)}`,
    title: `¿${plantilla.nombre} toca ${conSeparador(umbral)} dólares en 30 días?`,
    shortTitle: `${plantilla.nombre} toca ${conSeparador(umbral)} en 30 días`,
    outcomes: [
      { id: "si", label: `Toca ${nivelCorto(umbral)}` },
      { id: "no", label: "No lo toca" },
    ],
    category: "cripto",
    country: "LATAM",
    // el mercado deja de aceptar apuestas cuando resuelve, y puede resolver antes
    closesAt: new Date(settlesAtMs - CIERRE_ANTES_MS).toISOString(),
    pool: seedPool(SEED * 3, SEED * 6),
    rule,
    resolution: {
      sourceName: "Kraken (velas diarias públicas)",
      sourceUrl: urlKraken(plantilla.par),
      criterion: `Se resuelve Sí si el precio de ${plantilla.par} en Kraken alcanza o supera ${conSeparador(
        umbral,
      )} dólares en cualquier momento entre el ${desde.slice(0, 10)} y el ${settlesAt.slice(
        0,
        10,
      )}, medido sobre el máximo de las velas diarias públicas.`,
      settlesAt,
      disputeWindowHours: 12,
      // vela diaria de Kraken / marcador de ESPN: fuentes que laten a diario,
      // así que aquí el reloj SÍ dice si el colector sigue vivo (L8)
      maxAgeHours: FRESCURA_MAX_HORAS,
    },
  };
}

/**
 * Genera la tanda de mercados de precio para hoy. Determinista: el mismo
 * precio y el mismo día producen los mismos ids, así que correr el generador
 * dos veces no duplica el catálogo.
 */
export function rollingSeeds(input: {
  spot: SpotPrices;
  now: number;
}): OwnMarketSeed[] {
  const seeds: OwnMarketSeed[] = [];
  for (const plantilla of PLANTILLAS) {
    const spot = input.spot[plantilla.par];
    // sin precio no se inventa un umbral: se genera un mercado menos
    if (!spot || !Number.isFinite(spot) || spot <= 0) continue;
    seeds.push(cierreSemanal(plantilla, spot, input.now));
    seeds.push(tocaEnElMes(plantilla, spot, input.now));
  }
  return seeds.map((seed) => ({
    ...seed,
    resolution: assertPublishable(seed.resolution),
  }));
}

/* ------------------------------- deportes -------------------------------- */

/**
 * Un partido tal como lo lista ESPN. `liga` falta en los que vienen del flujo
 * viejo, que sólo conocía la Liga MX.
 */
export interface PartidoDeLaLiga {
  /** ISO del arranque del partido. */
  inicio: string;
  local: string;
  visitante: string;
  liga?: LigaId;
  /** Nombres cortos de ESPN (`shortDisplayName`), para cuando el largo no cabe. */
  localCorto?: string;
  visitanteCorto?: string;
  /** Escudo que publica la misma fuente que se lee (R-046). */
  escudoLocal?: string;
  escudoVisitante?: string;
}

const ESPN_MX = "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard";

/** Cuánto se espera al marcador final antes de leerlo. */
const DURACION_PARTIDO_MS = 3 * 3_600_000;

function claveDe(texto: string): string {
  return texto
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/** `2 de agosto de 2026`, como se escribe en el criterio. */
function diaLargo(dia: string): string {
  const fecha = new Date(`${dia}T12:00:00Z`);
  return fecha.toLocaleDateString("es-MX", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

/**
 * El mercado de un partido. La forma depende de la liga:
 *
 * - **Liga MX**: «¿X le gana a Y?», sí o no. Es la forma con la que nació el
 *   feed y se conserva tal cual (mismos ids, mismo criterio).
 * - **Resto del futbol**: la quiniela — gana, empata o pierde. El empate pasa
 *   un cuarto de las veces; plegarlo dentro de «no» esconde la mitad de la
 *   pregunta.
 * - **Deportes sin empate** (NFL, MLB, NBA, NHL): quién gana, con los dos
 *   nombres como respuestas.
 */
/** Lo que cabe en una respuesta y en el título corto: los topes del catálogo. */
const MAX_RESPUESTA = OUTCOME_LABEL_MAX;
const MAX_TITULO_CORTO = SHORT_TITLE_MAX;

function nombreQueCabe(
  largo: string,
  corto: string | undefined,
  max: number,
  preferirCortoDesde = max,
): string {
  if (largo.length <= preferirCortoDesde) return largo;
  if (corto && corto.length < largo.length && corto.length <= max) return corto;
  if (largo.length <= max) return largo;
  if (corto && corto.length <= max) return corto;
  return `${(corto ?? largo).slice(0, max - 1).trimEnd()}…`;
}

export function partidoSeed(partido: PartidoDeLaLiga): OwnMarketSeed {
  const liga = ligaDe(partido.liga ?? "mex.1");
  // la respuesta se lee en una pill de unos trece caracteres: «Gana Bills»
  // cabe entera, «Gana Buffalo Bills» se corta en «Gana Buffalo…» y deja de
  // decir quién. Con nombre corto disponible, se usa pasado el ancho de la pill
  const ANCHO_PILL = 12;
  const localR = nombreQueCabe(partido.local, partido.localCorto, MAX_RESPUESTA - 5, ANCHO_PILL);
  const visitanteR = nombreQueCabe(
    partido.visitante,
    partido.visitanteCorto,
    MAX_RESPUESTA - 5,
    ANCHO_PILL,
  );
  const versus = (() => {
    const largo = `${partido.local} vs ${partido.visitante}`;
    if (largo.length <= MAX_TITULO_CORTO) return largo;
    const corto = `${partido.localCorto ?? partido.local} vs ${partido.visitanteCorto ?? partido.visitante}`;
    return corto.length <= MAX_TITULO_CORTO ? corto : `${localR} vs ${visitanteR}`.slice(0, MAX_TITULO_CORTO);
  })();
  const inicioMs = new Date(partido.inicio).getTime();
  const dia = new Date(inicioMs).toISOString().slice(0, 10);
  const settlesAt = new Date(inicioMs + DURACION_PARTIDO_MS).toISOString();
  const clave = claveDe(`${partido.local}-${partido.visitante}`);
  const fuente = urlJornadaEspn(liga.id, dia);
  const equipos = [
    { nombre: partido.local, escudo: partido.escudoLocal },
    { nombre: partido.visitante, escudo: partido.escudoVisitante },
  ];
  const comun = {
    category: "deportes" as const,
    country: liga.pais,
    liga: liga.nombre,
    // se cierra al arrancar: con el marcador a la vista ya no es predicción
    closesAt: partido.inicio,
    equipos,
  };
  const resolucion = (criterion: string) => ({
    sourceName: `ESPN (marcador oficial de ${liga.nombre})`,
    sourceUrl: fuente,
    criterion,
    settlesAt,
    disputeWindowHours: 12,
    // el marcador de ESPN late a diario: aquí el reloj SÍ dice si el colector
    // sigue vivo (L8)
    maxAgeHours: FRESCURA_MAX_HORAS,
  });

  if (liga.id === "mex.1") {
    const rule: MatchRule = {
      kind: "partido",
      liga: liga.id,
      fecha: dia,
      inicio: partido.inicio,
      equipo: partido.local,
      resultado: "gana",
    };
    return {
      ...comun,
      id: `mx-${clave}-${dia}`,
      title: `¿${partido.local} le gana a ${partido.visitante}?`,
      shortTitle: nombreQueCabe(
        `${partido.local} le gana a ${partido.visitante}`,
        `${localR} le gana a ${visitanteR}`,
        MAX_TITULO_CORTO,
      ),
      outcomes: [
        { id: "si", label: `Gana ${localR}` },
        { id: "no", label: "Empata o pierde" },
      ],
      pool: seedPool(SEED * 4, SEED * 4),
      rule,
      resolution: resolucion(
        `Se resuelve Sí si ${partido.local} le gana a ${partido.visitante} en el partido del ${dia}, según el marcador final que publica ESPN. Un empate resuelve No.`,
      ),
    };
  }

  if (liga.empate) {
    const rule: MatchOutcomeRule = {
      kind: "partido_multiple",
      liga: liga.id,
      fecha: dia,
      inicio: partido.inicio,
      equipo: partido.local,
      mercado: "1x2",
    };
    return {
      ...comun,
      id: `${liga.prefijo}-${clave}-${dia}`,
      title: `${partido.local} vs ${partido.visitante}: ¿cómo termina?`,
      shortTitle: versus,
      outcomes: [
        { id: "gana", label: `Gana ${localR}` },
        { id: "empata", label: "Empatan" },
        { id: "pierde", label: `Gana ${visitanteR}` },
      ],
      pool: declareSeed(
        { outcomes: { gana: SEED * 3, empata: SEED * 2, pierde: SEED * 3 }, feeBps: FEE_BPS },
        "apuesta",
      ),
      rule,
      resolution: resolucion(
        `Se resuelve con el marcador final de ${partido.local} contra ${partido.visitante} del ${diaLargo(dia)} (${liga.nombre}), tal como lo publica ESPN: Gana ${partido.local} si anota más goles, Empatan si terminan iguales, y Gana ${partido.visitante} si ${partido.local} anota menos.`,
      ),
    };
  }

  const rule: MatchRule = {
    kind: "partido",
    liga: liga.id,
    fecha: dia,
    inicio: partido.inicio,
    equipo: partido.local,
    resultado: "gana",
  };
  return {
    ...comun,
    id: `${liga.prefijo}-${clave}-${dia}`,
    title: `${liga.nombre}: ¿gana ${partido.local} o ${partido.visitante}?`,
    shortTitle: versus,
    outcomes: [
      { id: "si", label: `Gana ${localR}` },
      { id: "no", label: `Gana ${visitanteR}` },
    ],
    pool: seedPool(SEED * 4, SEED * 4),
    rule,
    resolution: resolucion(
      `Se resuelve Gana ${partido.local} si ${partido.local} termina con más puntos que ${partido.visitante} en el partido del ${diaLargo(dia)} (${liga.nombre}), según el marcador final que publica ESPN. En cualquier otro caso —incluido un empate, si lo hubiera— se resuelve Gana ${partido.visitante}.`,
    ),
  };
}

export function partidosSeeds(partidos: PartidoDeLaLiga[], now: number): OwnMarketSeed[] {
  return partidos
    // sólo lo que todavía no empieza: un partido en curso no se puede apostar
    .filter((partido) => new Date(partido.inicio).getTime() > now)
    .map(partidoSeed)
    .map((seed) => ({ ...seed, resolution: assertPublishable(seed.resolution) }));
}

export { KRAKEN_DOC, ESPN_MX };
