import { assertPublishable } from "@/domain/resolution";
import { SEED, type Pool } from "@/domain/parimutuel";
import type { PriceRule } from "@/domain/oracleRule";
import type { OwnMarketSeed } from "./catalog";

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

export interface SpotPrices {
  "BTC/USD"?: number;
  "ETH/USD"?: number;
}

/** Redondeo a un número que se dice en voz alta: 71,000, no 70,842. */
function nivelRedondo(precio: number, paso: number): number {
  return Math.round(precio / paso) * paso;
}

function conSeparador(valor: number): string {
  return valor.toLocaleString("en-US");
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

function seedPool(si: number, no: number): Pool {
  return { si, no, feeBps: FEE_BPS };
}

interface Plantilla {
  id: string;
  activo: "BTC" | "ETH";
  par: PriceRule["par"];
  nombre: string;
  paso: number;
}

const PLANTILLAS: Plantilla[] = [
  { id: "btc", activo: "BTC", par: "BTC/USD", nombre: "Bitcoin", paso: 1_000 },
  { id: "eth", activo: "ETH", par: "ETH/USD", nombre: "Ethereum", paso: 100 },
];

const KRAKEN_DOC = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440";

function urlKraken(par: PriceRule["par"]): string {
  const simbolo = par === "BTC/USD" ? "XBTUSD" : "ETHUSD";
  return `https://api.kraken.com/0/public/OHLC?pair=${simbolo}&interval=1440`;
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

export { KRAKEN_DOC };
