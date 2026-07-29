import { existsSync, readFileSync } from "node:fs";
import type { PriceRule } from "../src/domain/oracleRule";

/**
 * El precio spot de BTC y ETH, para los mercados intradía.
 *
 * Dos fuentes, en este orden:
 *
 *  1. **El motor FQ**, que ya sigue las monedas grandes tick a tick. Deja el
 *     último precio en un archivo JSON; aquí sólo se lee. No se le pide nada
 *     por red: si el motor está parado, el archivo se queda viejo y se nota.
 *  2. **Kraken público**, cuando el archivo del motor tiene más de 5 s. Es la
 *     misma casa que resuelve los mercados, así que el precio que se enseña y
 *     el que liquida vienen del mismo sitio.
 *
 * Lo que **no** se hace: inventar un precio, ni seguir mostrando uno viejo como
 * si fuera de ahora. Cada lectura viaja con su edad y con el nombre de quién la
 * dio, y la interfaz lo declara cuando se atrasa (R-022).
 */

export type Par = PriceRule["par"];

export type FuenteSpot = "motor" | "kraken" | "ninguna";

export interface Spot {
  par: Par;
  precio: number;
  /** Cuándo lo dio la fuente, en ms. */
  at: number;
  fuente: FuenteSpot;
}

export interface LecturaSpot {
  pares: Partial<Record<Par, Spot>>;
  at: number;
}

/** Más viejo que esto, el motor no cuenta como fuente viva. */
const MOTOR_MAX_EDAD_MS = 5_000;
/** Cada cuánto se le puede volver a preguntar a Kraken. */
const KRAKEN_CACHE_MS = 2_000;

const KRAKEN_TICKER = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD,ETHUSD";

const DE_KRAKEN: Record<string, Par> = {
  XXBTZUSD: "BTC/USD",
  XETHZUSD: "ETH/USD",
  XBTUSD: "BTC/USD",
  ETHUSD: "ETH/USD",
};

interface Cache {
  at: number;
  pares: Partial<Record<Par, Spot>>;
}

let cacheKraken: Cache = { at: 0, pares: {} };

/**
 * Lo que el motor FQ deja escrito. Formato mínimo a propósito: un precio y
 * cuándo se tomó. Cualquier cosa más rica se puede añadir sin romper esto.
 */
interface ArchivoMotor {
  [par: string]: { precio: number; at: string } | undefined;
}

function leerMotor(ruta: string, ahora: number): Partial<Record<Par, Spot>> {
  if (!existsSync(ruta)) return {};
  try {
    const crudo = JSON.parse(readFileSync(ruta, "utf8")) as ArchivoMotor;
    const pares: Partial<Record<Par, Spot>> = {};
    for (const par of ["BTC/USD", "ETH/USD"] as Par[]) {
      const dato = crudo[par];
      if (!dato || !Number.isFinite(dato.precio) || dato.precio <= 0) continue;
      const at = new Date(dato.at).getTime();
      if (!Number.isFinite(at)) continue;
      // un precio viejo no es un precio: se descarta y entra el respaldo
      if (ahora - at > MOTOR_MAX_EDAD_MS) continue;
      pares[par] = { par, precio: dato.precio, at, fuente: "motor" };
    }
    return pares;
  } catch {
    // un archivo a medio escribir no tumba el feed: se cae al respaldo
    return {};
  }
}

async function leerKraken(
  fetchImpl: typeof fetch,
  ahora: number,
): Promise<Partial<Record<Par, Spot>>> {
  if (ahora - cacheKraken.at < KRAKEN_CACHE_MS) return cacheKraken.pares;
  const respuesta = await fetchImpl(KRAKEN_TICKER);
  if (!respuesta.ok) throw new Error(`Kraken respondió ${respuesta.status}`);
  const cuerpo = (await respuesta.json()) as {
    error?: string[];
    result?: Record<string, { c?: string[] }>;
  };
  if (cuerpo.error?.length) throw new Error(cuerpo.error.join("; "));
  const pares: Partial<Record<Par, Spot>> = {};
  for (const [clave, valor] of Object.entries(cuerpo.result ?? {})) {
    const par = DE_KRAKEN[clave];
    const precio = Number(valor?.c?.[0]);
    if (!par || !Number.isFinite(precio) || precio <= 0) continue;
    pares[par] = { par, precio, at: ahora, fuente: "kraken" };
  }
  cacheKraken = { at: ahora, pares };
  return pares;
}

export interface PreciosOptions {
  /** Archivo que escribe el motor FQ. */
  rutaMotor?: string;
  fetchImpl?: typeof fetch;
}

/**
 * El spot de ahora, con el motor primero y Kraken de respaldo. Nunca lanza: sin
 * ninguna fuente devuelve el mapa vacío, y sin precio no se genera mercado.
 */
export async function leerSpot(
  options: PreciosOptions = {},
  ahora = Date.now(),
): Promise<LecturaSpot> {
  const ruta = options.rutaMotor ?? process.env.MAREA_SPOT_FILE ?? "";
  const delMotor = ruta ? leerMotor(ruta, ahora) : {};
  const faltan = (["BTC/USD", "ETH/USD"] as Par[]).filter((par) => !delMotor[par]);
  if (faltan.length === 0) return { pares: delMotor, at: ahora };

  try {
    const deKraken = await leerKraken(options.fetchImpl ?? fetch, ahora);
    return { pares: { ...deKraken, ...delMotor }, at: ahora };
  } catch {
    return { pares: delMotor, at: ahora };
  }
}
