import { assertPublishable } from "@/domain/resolution";
import { SEED, binaryPool } from "@/domain/parimutuel";
import type { PriceRule } from "@/domain/oracleRule";
import {
  cierreDeApuestas,
  strikeLegible,
  ventanasVivas,
  DURACIONES,
  type DuracionVela,
  type Ventana,
} from "@/domain/velas";
import type { OwnMarketSeed } from "./catalog";

/**
 * Cripto en vivo: BTC y ETH, en ventanas de 5 y 15 minutos que se reponen
 * solas.
 *
 * Es lo que hace que Marea esté viva a las tres de la tarde de un martes sin
 * que haya partido. La pregunta es la más simple que existe —¿cierra la vela
 * arriba o abajo de este precio?— y se resuelve sola contra la misma vela
 * pública de Kraken que cualquiera puede abrir en el navegador.
 *
 * Los ids son deterministas (`btc-5m-2026-07-29T08:35Z`): generar dos veces la
 * misma tanda no duplica el catálogo, y el pozo sembrado sobrevive al
 * siguiente tick.
 */

const FEE_BPS = 300;

interface Activo {
  id: "btc" | "eth";
  nombre: string;
  par: PriceRule["par"];
  /** Paso del strike: 100 en BTC, 10 en ETH. Un paso de 100 en ETH sería absurdo. */
  paso: number;
}

const ACTIVOS: Activo[] = [
  { id: "btc", nombre: "Bitcoin", par: "BTC/USD", paso: 100 },
  { id: "eth", nombre: "Ethereum", par: "ETH/USD", paso: 10 },
];

/** El umbral como se dice en voz alta: `71.2k`. */
export function nivelCorto(valor: number): string {
  if (valor >= 1000) {
    const miles = valor / 1000;
    return `${Number.isInteger(miles) ? miles : miles.toFixed(1)}k`;
  }
  return String(Math.round(valor));
}

function conSeparador(valor: number): string {
  return valor.toLocaleString("en-US");
}

function urlKraken(par: PriceRule["par"], minutos: DuracionVela): string {
  const simbolo = par === "BTC/USD" ? "XBTUSD" : "ETHUSD";
  return `https://api.kraken.com/0/public/OHLC?pair=${simbolo}&interval=${minutos}`;
}

/**
 * Lo que hay que recordar de una ventana: el strike y el precio con el que se
 * abrió. Sin esta memoria el strike se recalcularía en cada tick con el spot de
 * ese momento, y el mercado cambiaría de pregunta a media vela — con gente ya
 * dentro. La ventana se decide una vez y no se toca.
 */
export interface VentanaFijada {
  strike: number;
  apertura: number;
}

export type MemoriaIntradia = Record<string, VentanaFijada>;

function seedDeVentana(
  activo: Activo,
  ventana: Ventana,
  fijada: VentanaFijada,
): OwnMarketSeed {
  const strike = fijada.strike;
  const settlesAt = new Date(ventana.cierre).toISOString();
  const hora = new Date(ventana.cierre).toISOString().slice(11, 16);

  const rule: PriceRule = {
    kind: "precio",
    par: activo.par,
    umbral: strike,
    comparacion: "arriba",
    modo: "cierre",
    // sin esto el oráculo leería la vela diaria y resolvería otra pregunta
    intervaloMin: ventana.minutos,
    ventanaInicio: new Date(ventana.inicio).toISOString(),
  };

  return {
    id: `${activo.id}-${ventana.minutos}m-${ventana.clave}`,
    title: `¿${activo.nombre} cierra la vela de ${ventana.minutos} min arriba de ${conSeparador(
      strike,
    )} dólares?`,
    shortTitle: `${activo.nombre} arriba de ${nivelCorto(strike)} a las ${hora}`,
    category: "cripto",
    country: "LATAM",
    // las apuestas cierran 30 s antes que la vela: con el precio a la vista, el
    // último segundo no es predecir, es cobrar (ver `CIERRE_ANTES_MS`)
    closesAt: new Date(cierreDeApuestas(ventana)).toISOString(),
    pool: binaryPool(SEED * 5, SEED * 5, FEE_BPS),
    // el precio con el que abrió la vela: es contra esto que la card enseña
    // cuánto se ha movido, no contra el strike redondeado
    aperturaSpot: fijada.apertura,
    outcomes: [
      { id: "si", label: `Arriba de ${nivelCorto(strike)}` },
      { id: "no", label: `Abajo de ${nivelCorto(strike)}` },
    ],
    rule,
    resolution: {
      sourceName: `Kraken (velas públicas de ${ventana.minutos} min)`,
      sourceUrl: urlKraken(activo.par, ventana.minutos),
      criterion: `Se resuelve Arriba si la vela de ${ventana.minutos} minutos de ${activo.par} en Kraken que abre a las ${new Date(
        ventana.inicio,
      )
        .toISOString()
        .slice(11, 16)} UTC cierra por encima de ${conSeparador(
        strike,
      )} dólares. Se lee el precio de cierre de esa vela en el endpoint público de Kraken, que cualquiera puede consultar.`,
      settlesAt,
      // intradía: la ventana de disputa es corta porque el dato es inmediato y
      // público. Media hora alcanza para reclamar y no atora el pago
      disputeWindowHours: 1,
    },
  };
}

export interface SpotVivo {
  "BTC/USD"?: number;
  "ETH/USD"?: number;
}

/**
 * Los mercados intradía que deben existir en este instante.
 *
 * Sin precio para un activo no se genera nada suyo: un strike inventado sería
 * una pregunta sin sentido (R-022). El resto sigue.
 */
export function seedsIntradia(input: {
  spot: SpotVivo;
  ahora: number;
  /** Se lee y se completa: la ventana que ya existía conserva su strike. */
  memoria: MemoriaIntradia;
}): OwnMarketSeed[] {
  const seeds: OwnMarketSeed[] = [];
  for (const activo of ACTIVOS) {
    const spot = input.spot[activo.par];
    for (const minutos of DURACIONES) {
      for (const ventana of ventanasVivas(input.ahora, minutos)) {
        const clave = `${activo.id}-${minutos}m-${ventana.clave}`;
        let fijada = input.memoria[clave];
        if (!fijada) {
          // sin precio no se abre ventana nueva: un strike inventado sería una
          // pregunta sin sentido (R-022). Las que ya existen siguen su curso
          if (!spot || !Number.isFinite(spot) || spot <= 0) continue;
          fijada = { strike: strikeLegible(spot, activo.paso), apertura: spot };
          input.memoria[clave] = fijada;
        }
        seeds.push(seedDeVentana(activo, ventana, fijada));
      }
    }
  }
  return seeds.map((seed) => ({
    ...seed,
    resolution: assertPublishable(seed.resolution),
  }));
}

/** Si un id es de un mercado intradía. Lo usa el ciclo rápido para no leer todo. */
export function esIntradia(id: string): boolean {
  return /^(btc|eth)-(5|15)m-/.test(id);
}
