import type { Oracle, OracleQuery, OracleReading } from "@/domain/settlement";
import { idsDeTramos, type MatchOutcomeRule, type MatchRule } from "@/domain/oracleRule";

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
  team: { displayName: string; shortDisplayName?: string; abbreviation?: string };
}

export interface EspnEvento {
  date: string;
  name: string;
  competitions: {
    status: { type: { name: string; completed?: boolean } };
    competitors: EspnCompetidor[];
  }[];
}

export interface MatchOracleOptions {
  fetchImpl?: typeof fetch;
  /** Se inyecta en pruebas para no depender de la red. */
  cargarPartidos?: (rule: MatchRule | MatchOutcomeRule) => Promise<EspnEvento[]>;
}

const BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer";

export function urlDeJornada(liga: string, fecha: string): string {
  return `${BASE}/${liga}/scoreboard?dates=${fecha.replace(/-/g, "")}`;
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
  return nombres.some((nombre) => nombre.toLowerCase() === equipo.toLowerCase());
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
      const eventos = await cargar(rule);

      const evento = eventos.find((candidato) =>
        candidato.competitions[0]?.competitors.some((competidor) =>
          esElEquipo(competidor, rule.equipo),
        ),
      );
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
          return { status: "resuelto", outcome, evidence: evidencia };
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
        };
      }

      const cumple = rule.resultado === "gana" ? gano : gano || empato;

      return {
        status: "resuelto",
        outcome: cumple ? "si" : "no",
        evidence: evidencia,
      };
    },
  };
}
