import type { Oracle, OracleQuery, OracleReading } from "@/domain/settlement";
import type { TennisRule } from "@/domain/oracleRule";

/**
 * Oráculo de tenis contra el marcador público de ESPN — el mismo proveedor que
 * ya resuelve el futbol, sin llave ni registro.
 *
 * Verificable a mano desde el navegador:
 * https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard?dates=20260928
 *
 * La forma, medida el 2026-10-01: torneo → agrupación (`mens-singles`) →
 * partido (`competitions`) con `status.type` y `winner` en cada jugador. El
 * partido terminado trae además una nota legible («Tsitsipas (GRE) bt Hijikata
 * (AUS) 6-4 6-3») que se usa como evidencia tal cual.
 *
 * Tres reglas:
 *  1. Sólo se paga con el partido **terminado** y **un** ganador marcado.
 *  2. Si el partido ya empezó (ESPN lo da en juego), se dejan de aceptar
 *     apuestas aunque falte su hora programada: un cambio de orden de juego
 *     por lluvia adelanta partidos, y apostar con el marcador a la vista no es
 *     predicción (`detenerApuestas`).
 *  3. Cancelado o sin ganador: no se paga a nadie; el plazo anula y devuelve.
 */

export const ESPN_TENIS = "https://site.api.espn.com/apis/site/v2/sports/tennis";

export interface EspnJugador {
  id?: string;
  order?: number;
  winner?: boolean | null;
  athlete?: {
    displayName?: string;
    shortName?: string;
    flag?: { href?: string; alt?: string };
  };
}

export interface EspnPartidoTenis {
  id: string;
  date: string;
  round?: { displayName?: string };
  notes?: { text?: string }[];
  status: { type: { name: string; state?: string; completed?: boolean } };
  competitors: EspnJugador[];
}

export interface EspnTorneoTenis {
  id: string;
  name: string;
  groupings?: { grouping: { slug?: string }; competitions: EspnPartidoTenis[] }[];
}

export function urlJornadaTenis(circuito: string, fecha?: string): string {
  const dia = fecha ? `?dates=${fecha.replace(/-/g, "")}` : "";
  return `${ESPN_TENIS}/${circuito}/scoreboard${dia}`;
}

/** Los partidos individuales masculinos de una jornada, con su torneo. */
export async function cargarJornadaTenis(
  fetchImpl: typeof fetch,
  circuito: string,
  fecha?: string,
): Promise<{ torneo: string; partido: EspnPartidoTenis }[]> {
  const respuesta = await fetchImpl(urlJornadaTenis(circuito, fecha));
  if (!respuesta.ok) throw new Error(`ESPN respondió ${respuesta.status}`);
  const cuerpo = (await respuesta.json()) as { events?: EspnTorneoTenis[] };
  const salida: { torneo: string; partido: EspnPartidoTenis }[] = [];
  for (const torneo of cuerpo.events ?? []) {
    for (const grupo of torneo.groupings ?? []) {
      // el evento de Pekín trae la WTA en el mismo paquete: el individual
      // masculino se reconoce por su slug, no por el nombre del circuito
      if (grupo.grouping.slug !== "mens-singles") continue;
      for (const partido of grupo.competitions) salida.push({ torneo: torneo.name, partido });
    }
  }
  return salida;
}

/** `YYYY-MM-DD` del día anterior: ESPN agrupa por día de Estados Unidos. */
function diaAnterior(fecha: string): string {
  return new Date(Date.parse(`${fecha}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10);
}

const nombre = (j: EspnJugador | undefined) => j?.athlete?.displayName ?? "?";

export interface TennisOracleOptions {
  fetchImpl?: typeof fetch;
  /** Se inyecta en pruebas para no depender de la red. */
  cargarTenis?: (fecha: string) => Promise<{ torneo: string; partido: EspnPartidoTenis }[]>;
}

/** La decisión, sin red. Exportada para probar cada caso. */
export function resolverTenis(rule: TennisRule, partido: EspnPartidoTenis | undefined): OracleReading {
  if (!partido) {
    return { status: "sin_dato", evidence: `ESPN no lista el partido ${rule.partido} (${rule.jugador} vs ${rule.rival}).` };
  }
  const estado = partido.status.type;
  const enJuego = estado.state === "in" || estado.name === "STATUS_IN_PROGRESS";
  const terminado = estado.completed === true || estado.name === "STATUS_FINAL";
  const nota = partido.notes?.map((n) => n.text).filter(Boolean).join("; ");

  if (!terminado) {
    if (enJuego) {
      return {
        status: "sin_dato",
        detenerApuestas: true,
        evidence: `ESPN da en juego ${nombre(partido.competitors[0])} vs ${nombre(partido.competitors[1])}: se dejan de aceptar apuestas.`,
      };
    }
    return { status: "sin_dato", evidence: `El partido ${rule.jugador} vs ${rule.rival} no ha terminado (${estado.name}).` };
  }

  const ganadores = partido.competitors.filter((j) => j.winner === true);
  if (ganadores.length !== 1) {
    // terminado sin un ganador claro: cancelado, abandonado o dato raro. No se
    // adivina; si no se aclara, el plazo anula y devuelve todo
    return {
      status: "sin_dato",
      detenerApuestas: true,
      evidence: `ESPN cerró el partido ${rule.partido} sin un único ganador (${estado.name}).`,
    };
  }
  const ganador = nombre(ganadores[0]);
  const esJugador = ganador.toLowerCase() === rule.jugador.toLowerCase();
  const esRival = ganador.toLowerCase() === rule.rival.toLowerCase();
  if (!esJugador && !esRival) {
    return {
      status: "sin_dato",
      evidence: `ESPN marca ganador a ${ganador}, que no es ninguno de los dos del mercado.`,
    };
  }
  const observedAt = Number.isFinite(Date.parse(partido.date))
    ? new Date(partido.date).toISOString()
    : undefined;
  return {
    status: "resuelto",
    outcome: esJugador ? "si" : "no",
    evidence: `Resultado final en ESPN (partido ${rule.partido}): ${nota || `gana ${ganador}`}.`,
    ...(observedAt ? { observedAt } : {}),
  };
}

export function createTennisOracle(options: TennisOracleOptions = {}): Oracle {
  // una jornada se pide una vez por vuelta aunque haya ocho partidos en ella:
  // memoria corta, un minuto, sólo para no repetir el mismo pedido en el ciclo
  const memoria = new Map<string, { en: number; datos: Promise<{ torneo: string; partido: EspnPartidoTenis }[]> }>();
  const cargarBase =
    options.cargarTenis ??
    ((fecha: string) => cargarJornadaTenis(options.fetchImpl ?? fetch, "atp", fecha));
  const cargar = (fecha: string) => {
    const previa = memoria.get(fecha);
    if (previa && Date.now() - previa.en < 60_000) return previa.datos;
    const datos = cargarBase(fecha);
    memoria.set(fecha, { en: Date.now(), datos });
    datos.catch(() => memoria.delete(fecha));
    return datos;
  };

  return {
    id: "espn-tenis",

    handles(query: OracleQuery): boolean {
      return query.rule?.kind === "tenis";
    },

    async read(query: OracleQuery): Promise<OracleReading> {
      const rule = query.rule as TennisRule;
      const buscar = (lista: { partido: EspnPartidoTenis }[]) =>
        lista.find((x) => x.partido.id === rule.partido)?.partido;
      try {
        let partido = buscar(await cargar(rule.fecha));
        // ESPN agrupa por día de EE.UU.: un partido de Asia de madrugada UTC
        // vive en la jornada anterior
        if (!partido) partido = buscar(await cargar(diaAnterior(rule.fecha)).catch(() => []));
        return resolverTenis(rule, partido);
      } catch (error) {
        return {
          status: "sin_dato",
          evidence: `ESPN tenis: ${error instanceof Error ? error.message : String(error)}`,
        };
      }
    },
  };
}
