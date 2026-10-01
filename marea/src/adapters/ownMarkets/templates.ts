import { assertPublishable } from "@/domain/resolution";
import { FRESCURA_MAX_HORAS } from "@/domain/settlement";
import { SEED, binaryPool, declareSeed, type Pool } from "@/domain/parimutuel";
import {
  KRAKEN_PAR,
  type MatchOutcomeRule,
  type MatchRule,
  type TennisRule,
  type ParCripto,
  type PriceRule,
} from "@/domain/oracleRule";
import { ligaDe, urlJornadaEspn, type LigaId } from "@/domain/ligas";
import { pozoDesdePrior, probabilidadesDeMomios, type Momios } from "@/domain/director";
import { urlJornadaTenis } from "@/adapters/oracles/tennisOracle";
import {
  OUTCOME_LABEL_MAX,
  SHORT_TITLE_IDEAL,
  SHORT_TITLE_MAX,
  type OwnMarketSeed,
} from "./catalog";

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
    // «sobre» y no «arriba de»: con «arriba de» medía 35 y en la tarjeta caben 32
    // (hallazgo `titulo_largo` del revisor, primer arranque del 2026-10-01)
    shortTitle: `${plantilla.nombre} sobre ${conSeparador(umbral)} el domingo`,
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
  /**
   * Momios publicados con el partido. Sólo deciden con qué prior nace el pozo
   * —el trabajo de quien hace existir el mercado—; nunca resuelven nada.
   */
  momios?: Momios;
}

const ESPN_MX = "https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard";

/** Días en que un partido reprogramado sigue siendo el mismo mercado (R-084). */
export const DIAS_REPROGRAMACION = 7;

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
    const corto = `${partido.localCorto ?? partido.local} vs ${partido.visitanteCorto ?? partido.visitante}`;
    // primero lo que cabe entero en la línea (medido); si el largo no cabe y el
    // corto sí, el corto: «Browns vs Steelers» se lee entero, «Cleveland
    // Browns vs Pittsburgh…» no. Sólo si ninguno cabe se usa el tope de 42
    if (largo.length <= SHORT_TITLE_IDEAL) return largo;
    if (corto.length <= SHORT_TITLE_IDEAL) return corto;
    if (largo.length <= MAX_TITULO_CORTO) return largo;
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
  /**
   * El prior: los momios publicados, sin la comisión de la casa de apuestas. Sin
   * momios legibles, el pozo nace parejo como antes —y la bitácora lo dice—.
   */
  const prior = partido.momios ? probabilidadesDeMomios(partido.momios, Boolean(liga.empate) || liga.id === "mex.1") : undefined;
  const nota = prior && partido.momios
    ? ` La semilla sigue los momios de ${partido.momios.proveedor} al crear el mercado; no intervienen en el resultado.`
    : "";
  // R-084: lo que pasa si el partido se mueve o no se juega, dicho antes de apostar
  const reprogramacion =
    ` Si el partido se reprograma, se resuelve con el partido entre los mismos equipos jugado dentro de los ${DIAS_REPROGRAMACION} días siguientes; si se cancela o no se juega en ese plazo, se anula y se devuelve todo.`;
  const resolucion = (criterion: string) => ({
    sourceName: `ESPN (marcador oficial de ${liga.nombre})`,
    sourceUrl: fuente,
    criterion: `${criterion}${reprogramacion}${nota}`,
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
      rival: partido.visitante,
      reprogramacionDias: DIAS_REPROGRAMACION,
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
      pool: prior
        ? declareSeed(
            { outcomes: pozoDesdePrior({ si: prior.local, no: prior.visitante + (prior.empate ?? 0) }, SEED * 8), feeBps: FEE_BPS },
            "apuesta",
          )
        : seedPool(SEED * 4, SEED * 4),
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
      rival: partido.visitante,
      reprogramacionDias: DIAS_REPROGRAMACION,
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
        {
          outcomes: prior?.empate !== undefined
            ? pozoDesdePrior({ gana: prior.local, empata: prior.empate, pierde: prior.visitante }, SEED * 8)
            : { gana: SEED * 3, empata: SEED * 2, pierde: SEED * 3 },
          feeBps: FEE_BPS,
        },
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
    rival: partido.visitante,
    reprogramacionDias: DIAS_REPROGRAMACION,
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
    pool: prior
      ? declareSeed({ outcomes: pozoDesdePrior({ si: prior.local, no: prior.visitante }, SEED * 8), feeBps: FEE_BPS }, "apuesta")
      : seedPool(SEED * 4, SEED * 4),
    rule,
    resolution: resolucion(
      `Se resuelve Gana ${partido.local} si ${partido.local} termina con más puntos que ${partido.visitante} en el partido del ${diaLargo(dia)} (${liga.nombre}), según el marcador final que publica ESPN. En cualquier otro caso —incluido un empate, si lo hubiera— se resuelve Gana ${partido.visitante}.`,
    ),
  };
}

/**
 * ¿El rival todavía no existe? ESPN publica los cruces de eliminatoria con
 * «TBD» antes de que se definan. Un mercado «TBD vs TBD» no tiene a quién
 * pagar y el oráculo nunca lo encuentra (hallazgo `sin_leer` del revisor,
 * producción 2026-10-01). El de tenis ya lo filtraba; el de partidos no.
 */
export function equipoPorDefinir(nombre: string | undefined): boolean {
  const n = (nombre ?? "").trim().toLowerCase();
  return n === "" || n === "tbd" || n === "tba" || /^(winner|loser|ganador|perdedor)\b/.test(n) || n.includes("por definir");
}

export function partidosSeeds(partidos: PartidoDeLaLiga[], now: number): OwnMarketSeed[] {
  return partidos
    // sólo lo que todavía no empieza: un partido en curso no se puede apostar
    .filter((partido) => new Date(partido.inicio).getTime() > now)
    .filter((partido) => !equipoPorDefinir(partido.local) && !equipoPorDefinir(partido.visitante))
    .map(partidoSeed)
    .map((seed) => ({ ...seed, resolution: assertPublishable(seed.resolution) }));
}

/* --------------------------------- tenis --------------------------------- */

/** Sección y hub de los partidos de tenis en el feed. */
export const LIGA_TENIS = "Tenis ATP";

/** Un partido individual masculino tal como lo lista ESPN. */
export interface PartidoTenis {
  /** Id del partido en ESPN. */
  id: string;
  /** ISO del arranque programado. */
  inicio: string;
  torneo: string;
  /** Ronda como la da ESPN: `Round 1`, `Quarterfinal`, `Final`… */
  ronda?: string;
  jugador: string;
  rival: string;
  /** `C. Alcaraz`: de aquí sale el apellido para la pill. */
  jugadorCorto?: string;
  rivalCorto?: string;
  /** Bandera que sirve la misma fuente que resuelve (R-046). */
  banderaJugador?: string;
  banderaRival?: string;
}

/** Cuánto se espera al resultado: un partido largo a cinco sets ronda las 5 h. */
const DURACION_TENIS_MS = 6 * 3_600_000;

/** «A. Davidovich Fokina» → «Davidovich Fokina». */
function apellido(corto: string | undefined, largo: string): string {
  const base = (corto ?? largo).trim();
  const sinInicial = base.replace(/^[A-ZÀ-Ý]\.\s+/u, "");
  return sinInicial || largo;
}

/** La ronda en español, como se dice aquí. */
export function rondaEnEspanol(ronda: string | undefined): string | undefined {
  if (!ronda) return undefined;
  const r = ronda.toLowerCase();
  if (/^final$/.test(r)) return "final";
  if (/semi/.test(r)) return "semifinal";
  if (/quarter/.test(r)) return "cuartos de final";
  if (/round of 16|4th round/.test(r)) return "octavos de final";
  const n = r.match(/round (\d+)/);
  if (n) return `${n[1]}.ª ronda`;
  if (/qualif/.test(r)) return "clasificación";
  return ronda;
}

/** Qué tan lejos está la ronda de la final: las rondas finales van primero. */
function pesoRonda(ronda: string | undefined): number {
  const r = (ronda ?? "").toLowerCase();
  if (/^final$/.test(r)) return 100;
  if (/semi/.test(r)) return 90;
  if (/quarter/.test(r)) return 80;
  if (/round of 16|4th round/.test(r)) return 70;
  const n = r.match(/round (\d+)/);
  return n ? Number(n[1]) * 10 : 0;
}

export function tenisSeed(p: PartidoTenis): OwnMarketSeed {
  const apA = apellido(p.jugadorCorto, p.jugador);
  const apB = apellido(p.rivalCorto, p.rival);
  const inicioMs = Date.parse(p.inicio);
  const dia = new Date(inicioMs).toISOString().slice(0, 10);
  const ronda = rondaEnEspanol(p.ronda);
  const donde = ronda ? `${p.torneo}, ${ronda}` : p.torneo;
  const rule: TennisRule = {
    kind: "tenis",
    circuito: "atp",
    partido: p.id,
    fecha: dia,
    jugador: p.jugador,
    rival: p.rival,
  };
  return {
    id: `atp-${p.id}`,
    title: `${donde}: ¿gana ${p.jugador} o ${p.rival}?`,
    shortTitle: nombreQueCabe(`${apA} vs ${apB}`, `${apA.split(" ").at(-1)} vs ${apB.split(" ").at(-1)}`, MAX_TITULO_CORTO, SHORT_TITLE_IDEAL),
    category: "deportes",
    country: "GLOBAL",
    liga: LIGA_TENIS,
    // se cierra al arrancar; si el orden de juego lo adelanta, el oráculo lo
    // ve en juego y detiene las apuestas antes
    closesAt: new Date(inicioMs).toISOString(),
    equipos: [
      { nombre: p.jugador, escudo: p.banderaJugador },
      { nombre: p.rival, escudo: p.banderaRival },
    ],
    outcomes: [
      { id: "si", label: nombreQueCabe(`Gana ${apA}`, `Gana ${apA.split(" ").at(-1)}`, MAX_RESPUESTA) },
      { id: "no", label: nombreQueCabe(`Gana ${apB}`, `Gana ${apB.split(" ").at(-1)}`, MAX_RESPUESTA) },
    ],
    pool: seedPool(SEED * 4, SEED * 4),
    rule,
    resolution: assertPublishable({
      sourceName: "ESPN (marcador oficial del circuito ATP)",
      sourceUrl: urlJornadaTenis("atp", dia),
      criterion: `Se resuelve Gana ${apA} si ESPN marca a ${p.jugador} como ganador del partido contra ${p.rival} del ${diaLargo(dia)} (${donde}), incluido el retiro o la no presentación de su rival: gana quien avanza. En el caso contrario se resuelve Gana ${apB}. Un partido cancelado sin ganador se anula y se devuelve todo.`,
      settlesAt: new Date(inicioMs + DURACION_TENIS_MS).toISOString(),
      disputeWindowHours: 12,
      maxAgeHours: FRESCURA_MAX_HORAS,
    }),
  };
}

/**
 * Los partidos de tenis que merecen mercado, de mejor a peor: las rondas
 * finales primero (un cuarto de final de Pekín vale más que una primera ronda
 * de Tokio) y, dentro de la misma ronda, el que empieza antes. Sólo los que no
 * han empezado y tienen a sus dos jugadores definidos.
 */
export function tenisSeeds(partidos: PartidoTenis[], now: number): OwnMarketSeed[] {
  return partidos
    .filter((p) => Date.parse(p.inicio) > now)
    .filter((p) => !/\b(tbd|por definir|qualifier)\b/i.test(`${p.jugador} ${p.rival}`))
    .sort((a, b) => pesoRonda(b.ronda) - pesoRonda(a.ronda) || Date.parse(a.inicio) - Date.parse(b.inicio))
    .map(tenisSeed)
    .map((seed) => ({ ...seed, resolution: assertPublishable(seed.resolution) }));
}

export { KRAKEN_DOC, ESPN_MX };
