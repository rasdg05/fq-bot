import { assertPublishable } from "@/domain/resolution";
import { SEED, declareSeed } from "@/domain/parimutuel";
import type { QuakeRule } from "@/domain/oracleRule";
import { urlSismos } from "@/adapters/oracles/quakeOracle";
import type { OwnMarketSeed } from "./catalog";

/**
 * «¿Habrá un sismo de magnitud 5 o mayor en México la semana que viene?»
 *
 * ## La tasa base, medida
 *
 * Catálogo del USGS, 260 semanas (27-sep-2021 a 28-sep-2026), con la misma
 * definición de «en México» que usa el oráculo: semanas con al menos un sismo
 * M4.5+ 72.7 %, **M5.0+ 34.2 % (89 de 260)**, M5.5+ 15.8 %, M6.0+ 4.2 %. Se
 * eligió M5.0: la pregunta no viene contestada y la cifra es la que se dice en
 * voz alta. El pozo nace en esa proporción, no en 50/50.
 *
 * ## Por qué la semana **que viene** y no la que corre
 *
 * Con la semana en curso abierta, quien recibe la alerta sísmica en el celular
 * apostaría «sí» en los minutos que el USGS tarda en publicar y el ciclo en
 * leer. Preguntando por la siguiente semana y cerrando al empezar, nadie apuesta
 * con información que los demás no pueden tener.
 */

export const MAGNITUD = 5.0;
/** Semanas con al menos un M5.0+ en México: 89 de 260 (medido, ver arriba). */
export const TASA_BASE_SEMANAL = 89 / 260;

const H = 3_600_000;
const DIA = 24 * H;
const MESES = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sep.", "oct.", "nov.", "dic."];
const MESES_LARGOS = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

/** El próximo lunes a las 00:00 de la Ciudad de México (06:00 UTC), estrictamente después de `ahora`. */
export function proximoLunesCdmx(ahora: number): number {
  const d = new Date(ahora - 6 * H); // reloj de la CDMX (UTC−6, sin horario de verano desde 2022)
  const diasHastaLunes = (8 - d.getUTCDay()) % 7 || 7;
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + diasHastaLunes) + 6 * H;
}

const fechaCdmx = (ms: number) => new Date(ms - 6 * H);

export function sismoSeed(desde: number): OwnMarketSeed {
  const hasta = desde + 7 * DIA;
  const ini = fechaCdmx(desde);
  const fin = fechaCdmx(hasta - 1);
  const rango =
    ini.getUTCMonth() === fin.getUTCMonth()
      ? `${ini.getUTCDate()}–${fin.getUTCDate()} ${MESES[fin.getUTCMonth()]}`
      : `${ini.getUTCDate()} ${MESES[ini.getUTCMonth()]}–${fin.getUTCDate()} ${MESES[fin.getUTCMonth()]}`;
  const largo = `del ${ini.getUTCDate()} de ${MESES_LARGOS[ini.getUTCMonth()]} al ${fin.getUTCDate()} de ${MESES_LARGOS[fin.getUTCMonth()]} de ${fin.getUTCFullYear()}`;
  const rule: QuakeRule = {
    kind: "sismo",
    fuente: "usgs",
    region: "MX",
    magnitudMin: MAGNITUD,
    desde: new Date(desde).toISOString(),
    hasta: new Date(hasta).toISOString(),
  };
  const si = Math.round(SEED * 4 * TASA_BASE_SEMANAL);

  return {
    id: `sismo-mx-${new Date(desde).toISOString().slice(0, 10)}`,
    title: `¿Habrá un sismo de magnitud 5 o mayor en México la semana ${largo}?`,
    shortTitle: `Sismo M5+ en México (${rango})`,
    category: "otros",
    country: "MX",
    liga: "Sismos",
    closesAt: new Date(desde).toISOString(),
    outcomes: [
      { id: "si", label: "Habrá al menos uno" },
      { id: "no", label: "Ninguno" },
    ],
    pool: declareSeed({ outcomes: { si, no: SEED * 4 - si }, feeBps: 300 }, "apuesta"),
    rule,
    resolution: assertPublishable({
      sourceName: "USGS (catálogo público de sismos, Servicio Geológico de EE.UU.)",
      sourceUrl: urlSismos(rule),
      criterion:
        `Se resuelve con el catálogo público del USGS: Habrá al menos uno si entre las 00:00 del lunes y las ` +
        `00:00 del lunes siguiente, hora de la Ciudad de México (semana ${largo}), el USGS registra un sismo de ` +
        `magnitud ${MAGNITUD.toFixed(1)} o mayor cuya descripción de lugar termina en «Mexico» o «MX» (no cuenta ` +
        `«New Mexico», que es Estados Unidos). Se paga con el sismo ya revisado por el USGS; uno sin revisar se ` +
        `espera hasta 72 h después de la semana. Ninguno, si un día después de terminada la semana no hay ninguno. ` +
        `Las apuestas cierran al empezar la semana. La semilla es la tasa medida: 34 % de las semanas de 2021 a 2026.`,
      settlesAt: new Date(hasta + DIA).toISOString(),
      disputeWindowHours: 12,
    }),
  };
}

/** El de la semana que viene, si falta. Sin red: el mercado sale del calendario. */
export function sismosPendientes(input: { ahora: number; existentes: ReadonlySet<string> }): OwnMarketSeed[] {
  const seed = sismoSeed(proximoLunesCdmx(input.ahora));
  return input.existentes.has(seed.id) ? [] : [seed];
}
