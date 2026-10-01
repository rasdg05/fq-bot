import type { Oracle, OracleQuery, OracleReading } from "@/domain/settlement";
import type { Momios } from "@/domain/director";
import { idsDeTramos, type MatchOutcomeRule, type MatchRule } from "@/domain/oracleRule";
import { urlJornadaEspn } from "@/domain/ligas";

/**
 * Oráculo de futbol contra el marcador público de ESPN, que sirve la Liga MX
 * sin llave, sin registro y sin bloqueo geográfico.
 *
 * Verificable a mano desde el navegador:
 * https://site.api.espn.com/apis/site/v2/sports/soccer/mex.1/scoreboard?dates=20260802
 *
 * Por qué importa: el futbol es lo que la gente de aquí comparte en el grupo, y
 * hasta ahora habríamos tenido que resolverlo a mano. Se puede leer solo, así
 * que se lee solo (R-051).
 *
 * Nunca resuelve un partido que no terminó: un 1-0 al minuto 60 no es un
 * resultado, y pagar con eso sería pagar con una lectura falsa.
 */

export interface EspnCompetidor {
  homeAway: string;
  score?: string;
  winner?: boolean;
  team: { displayName: string; shortDisplayName?: string; abbreviation?: string; logo?: string };
}

export interface EspnEvento {
  date: string;
  name: string;
  competitions: {
    status: { type: { name: string; completed?: boolean } };
    competitors: EspnCompetidor[];
    /**
     * Momios que ESPN publica junto al partido (DraftKings, medido el
     * 2026-10-01). Sólo siembran el prior; nunca resuelven nada. La lista puede
     * traer entradas `null` (Liga MX).
     */
    odds?: ({
      provider?: { name?: string };
      moneyline?: {
        home?: { close?: { odds?: string }; open?: { odds?: string } };
        away?: { close?: { odds?: string }; open?: { odds?: string } };
        draw?: { close?: { odds?: string }; open?: { odds?: string } };
      };
    } | null)[];
  }[];
}

export interface MatchOracleOptions {
  fetchImpl?: typeof fetch;
  /** Se inyecta en pruebas para no depender de la red. */
  cargarPartidos?: (rule: MatchRule | MatchOutcomeRule) => Promise<EspnEvento[]>;
}

export function urlDeJornada(liga: string, fecha: string): string {
  return urlJornadaEspn(liga, fecha);
}

/** `YYYY-MM-DD` del día anterior. */
function diaAnterior(fecha: string): string {
  return new Date(Date.parse(`${fecha}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10);
}

function mismoArranque(evento: EspnEvento, inicio: string): boolean {
  return Math.abs(Date.parse(evento.date) - Date.parse(inicio)) < 60_000;
}

export async function cargarEspn(
  fetchImpl: typeof fetch,
  liga: string,
  fecha: string,
): Promise<EspnEvento[]> {
  const respuesta = await fetchImpl(urlDeJornada(liga, fecha));
  if (!respuesta.ok) throw new Error(`ESPN respondió ${respuesta.status}`);
  const cuerpo = (await respuesta.json()) as { events?: EspnEvento[] };
  return cuerpo.events ?? [];
}

/** Coincide por cualquiera de los nombres con que la fuente llama al equipo. */
function esElEquipo(competidor: EspnCompetidor, equipo: string): boolean {
  const nombres = [
    competidor.team.displayName,
    competidor.team.shortDisplayName,
    competidor.team.abbreviation,
  ].filter(Boolean) as string[];
  return nombres.some((nombre) => sinAcentos(nombre) === sinAcentos(equipo));
}

/**
 * Comparación de nombres sin mayúsculas ni acentos. El mercado decía «FC
 * Juarez» y ESPN «FC Juárez»: el partido existía, terminado, y el oráculo
 * contestaba que no lo encontraba (hallazgo `atorado` del revisor, producción
 * 2026-10-01).
 */
export function sinAcentos(texto: string): string {
  return texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

export function createMatchOracle(options: MatchOracleOptions = {}): Oracle {
  const cargar =
    options.cargarPartidos ??
    ((rule: MatchRule | MatchOutcomeRule) =>
      cargarEspn(options.fetchImpl ?? fetch, rule.liga, rule.fecha));

  return {
    id: "espn-futbol",

    handles(query: OracleQuery): boolean {
      return (
        query.rule?.kind === "partido" || query.rule?.kind === "partido_multiple"
      );
    },

    async read(query: OracleQuery): Promise<OracleReading> {
      const rule = query.rule as MatchRule | MatchOutcomeRule;
      const delEquipo = (lista: EspnEvento[]) =>
        lista.filter((candidato) =>
          candidato.competitions[0]?.competitors.some((competidor) =>
            esElEquipo(competidor, rule.equipo),
          ),
        );
      const elegir = (lista: EspnEvento[]) => {
        const candidatos = delEquipo(lista);
        if (!rule.inicio) return candidatos[0];
        return candidatos.find((candidato) => mismoArranque(candidato, rule.inicio!));
      };

      let evento = elegir(await cargar(rule));
      // ESPN agrupa por día de Estados Unidos: un partido nocturno de América
      // Latina vive en la jornada del día anterior al UTC. Sin esta segunda
      // mirada, el mercado se quedaba sin dato para siempre
      if (!evento) {
        try {
          evento = elegir(await cargar({ ...rule, fecha: diaAnterior(rule.fecha) }));
        } catch {
          // la jornada vecina es una ayuda, no un requisito: sin ella se
          // contesta lo mismo que antes
        }
      }
      if (!evento) {
        return {
          status: "sin_dato",
          evidence: `ESPN no lista partido de ${rule.equipo} el ${rule.fecha}.`,
        };
      }

      const competencia = evento.competitions[0];
      const terminado =
        competencia.status.type.completed === true ||
        competencia.status.type.name === "STATUS_FULL_TIME";

      const nuestro = competencia.competitors.find((competidor) =>
        esElEquipo(competidor, rule.equipo),
      )!;
      const rival = competencia.competitors.find((competidor) => competidor !== nuestro)!;
      const marcador = `${nuestro.team.displayName} ${nuestro.score ?? "?"} - ${
        rival.score ?? "?"
      } ${rival.team.displayName}`;

      // un marcador a medio partido no es un resultado
      if (!terminado) {
        return {
          status: "sin_dato",
          evidence: `${evento.name}: el partido no ha terminado (${marcador}).`,
        };
      }

      /**
       * De cuándo es el dato: la fecha del propio partido según ESPN, no el
       * momento en que preguntamos. Un scoreboard congelado seguiría
       * devolviendo el marcador de la semana pasada con un 200 impecable.
       */
      const observedAt = Number.isFinite(Date.parse(evento.date))
        ? new Date(evento.date).toISOString()
        : undefined;

      const nuestros = Number(nuestro.score ?? NaN);
      const suyos = Number(rival.score ?? NaN);
      if (!Number.isFinite(nuestros) || !Number.isFinite(suyos)) {
        return { status: "sin_dato", evidence: `${evento.name}: ESPN no publicó marcador.` };
      }

      const gano = nuestros > suyos;
      const empato = nuestros === suyos;
      const evidencia = `Marcador final en ESPN del ${rule.fecha}: ${marcador}.`;

      // el mismo marcador responde las tres formas de preguntar. Del 1X2 y de
      // los goles totales sale un `outcomeId`, no un sí/no: plegar un empate
      // dentro de "no" era una limitación nuestra, no de la pregunta
      if (rule.kind === "partido_multiple") {
        if (rule.mercado === "1x2") {
          const outcome = gano ? "gana" : empato ? "empata" : "pierde";
          return { status: "resuelto", outcome, evidence: evidencia, observedAt, definitivo: true };
        }
        const totales = nuestros + suyos;
        const tramos = idsDeTramos(rule.cortes ?? []);
        const cortes = rule.cortes ?? [];
        let indice = cortes.findIndex((corte) => totales < corte);
        if (indice === -1) indice = cortes.length;
        return {
          status: "resuelto",
          outcome: tramos[indice].id,
          evidence: `${evidencia} Goles totales: ${totales}.`,
          observedAt,
          definitivo: true,
        };
      }

      const cumple = rule.resultado === "gana" ? gano : gano || empato;

      return {
        status: "resuelto",
        outcome: cumple ? "si" : "no",
        evidence: evidencia,
        observedAt,
        // un marcador final de ESTE partido (identificado por su arranque) es un
        // hecho consumado: no envejece (ver `definitivo` en settlement.ts)
        definitivo: true,
      };
    },
  };
}

/** Los momios de un partido de ESPN, o nada. Toma el cierre; si no hay, la apertura. */
export function momiosDeEspn(evento: EspnEvento): Momios | undefined {
  for (const o of evento.competitions[0]?.odds ?? []) {
    const ml = o?.moneyline;
    const de = (lado?: { close?: { odds?: string }; open?: { odds?: string } }) => lado?.close?.odds ?? lado?.open?.odds;
    const local = de(ml?.home);
    const visitante = de(ml?.away);
    if (local === undefined || visitante === undefined) continue;
    const empate = de(ml?.draw);
    return {
      local,
      visitante,
      ...(empate !== undefined ? { empate } : {}),
      proveedor: `${o?.provider?.name ?? "casa de apuestas"} vía ESPN`,
    };
  }
  return undefined;
}
