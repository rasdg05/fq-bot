import { assertPublishable } from "@/domain/resolution";
import { SEED, type Pool } from "@/domain/parimutuel";
import { BITSO_LIBRO, KRAKEN_PAR, esParDivisa, type ParCripto, type VelaRule } from "@/domain/oracleRule";
import {
  bloqueoDeVentana,
  claveDeVentana,
  finDeVentana,
  inicioDeVentana,
  pasoDeStrike,
  redondearStrike,
  relojUtc,
  type IntervaloVivo,
} from "@/domain/vela";
import type { OwnMarketSeed } from "./catalog";

/**
 * Mercados vivos de cripto: "¿la vela de cinco minutos cierra arriba o abajo?".
 *
 * Es la pregunta más corta que se puede hacer sobre un precio, y por eso es la
 * que hace que la app se sienta viva: quien entra encuentra algo pasando ahora,
 * no algo que resuelve en septiembre.
 *
 * Tres decisiones que sostienen el resto:
 *
 *  1. **La ventana sale del reloj**, no de cuándo se generó el mercado. Todos
 *     ven la misma vela y Kraken publica exactamente esa.
 *  2. **El strike se fija al nacer el mercado y no cambia nunca.** Nace diez
 *     segundos antes de que su vela abra, con el precio de ese momento
 *     redondeado. Un strike que se "corrige" al abrir la vela sería cambiarle
 *     la pregunta a quien ya apostó.
 *  3. **Sin precio no hay mercado.** Si el ticker no tiene una lectura fresca,
 *     no se genera la vela: un strike inventado es una pregunta sin sentido.
 */

const FEE_BPS = 300;

/** Semilla del pozo. Simétrica: la casa no opina de hacia dónde va la vela. */
const SEMILLA = SEED * 2;

export const ARRIBA = "arriba";
export const ABAJO = "abajo";

export interface ActivoVivo {
  id: "btc" | "eth" | "sol" | "usdmxn" | "usdars" | "usdbrl";
  par: VelaRule["par"];
  nombre: string;
  /**
   * Las ventanas en que tiene sentido preguntar. Sin esto, todas. Un par con
   * velas vacías a cinco minutos sólo se ofrece a quince (ver `PARES_DIVISA`).
   */
  intervalos?: readonly IntervaloVivo[];
  /**
   * Cómo se nombra en la línea de la tarjeta, si el nombre no cabe. Medido: en
   * el carrusel «Dólar en pesos · vela de 5 min» se cortaba en «vela…»; el
   * ticker «USD/MXN» es como lo escribe cualquier casa de cambio.
   */
  corto?: string;
}

export const ACTIVOS_VIVOS: ActivoVivo[] = [
  { id: "btc", par: "BTC/USD", nombre: "Bitcoin" },
  { id: "eth", par: "ETH/USD", nombre: "Ethereum" },
  { id: "sol", par: "SOL/USD", nombre: "Solana" },
  // el dólar, que es el precio que más mira Latam. Bitso, no Kraken
  { id: "usdmxn", par: "USD/MXN", nombre: "Dólar en pesos", corto: "USD/MXN" },
  { id: "usdars", par: "USD/ARS", nombre: "Dólar en Argentina", corto: "USD/ARS", intervalos: [15] },
  { id: "usdbrl", par: "USD/BRL", nombre: "Dólar en reales", corto: "USD/BRL", intervalos: [15] },
];

/** De qué se habla y en qué moneda, por par: lo que cambia del criterio. */
const DIVISA: Record<string, { moneda: string; country: OwnMarketSeed["country"]; decimales: number }> = {
  "USD/MXN": { moneda: "pesos mexicanos", country: "MX", decimales: 2 },
  "USD/ARS": { moneda: "pesos argentinos", country: "AR", decimales: 0 },
  "USD/BRL": { moneda: "reales", country: "BR", decimales: 3 },
};

export function urlKrakenVela(par: VelaRule["par"], intervalo: IntervaloVivo): string {
  return `https://api.kraken.com/0/public/OHLC?pair=${KRAKEN_PAR[par as ParCripto]}&interval=${intervalo}`;
}

/** Velas públicas de Bitso. `time_bucket` va en segundos. */
export function urlBitsoVela(par: VelaRule["par"], intervalo: IntervaloVivo): string {
  const libro = esParDivisa(par) ? BITSO_LIBRO[par] : par;
  return `https://api.bitso.com/v3/ohlc?book=${libro}&time_bucket=${intervalo * 60}`;
}

/** La URL que cita el criterio, según quién publica la vela del par. */
export function urlVela(par: VelaRule["par"], intervalo: IntervaloVivo): string {
  return esParDivisa(par) ? urlBitsoVela(par, intervalo) : urlKrakenVela(par, intervalo);
}

export function conSeparador(valor: number): string {
  return valor.toLocaleString("en-US");
}

/** `btc-5m-20260729T1635`. Determinista: la misma vela produce el mismo id. */
export function idDeVela(
  activo: ActivoVivo,
  intervalo: IntervaloVivo,
  inicio: number,
): string {
  return `${activo.id}-${intervalo}m-${claveDeVentana(inicio)}`;
}

/** ¿Este mercado es una vela viva? Es la única forma de preguntarlo. */
export function esVelaViva(seed: OwnMarketSeed): seed is OwnMarketSeed & { rule: VelaRule } {
  return seed.rule?.kind === "vela";
}

function pozoSimetrico(): Pool {
  return { outcomes: { [ARRIBA]: SEMILLA, [ABAJO]: SEMILLA }, feeBps: FEE_BPS };
}

export interface VelaViva {
  activo: ActivoVivo;
  intervalo: IntervaloVivo;
  /** Apertura de la vela, ms UTC. */
  inicio: number;
  /** Precio de referencia sin redondear, tal como lo dio el ticker. */
  spot: number;
}

/**
 * Construye el mercado de una vela. El strike se calcula aquí y una sola vez:
 * es lo único que hace falta congelar para que la pregunta no se mueva.
 */
/**
 * El strike como cabe en la etiqueta de un resultado: `64.2k`. En la card hay
 * unos trece caracteres por lado, y "Arriba de 64,200" se recortaba justo en el
 * número — que es lo único que no se puede recortar. El criterio publicado
 * conserva la cifra entera: ahí no hay ancho que respetar y sí una fuente que
 * citar al milímetro.
 */
function strikeCorto(strike: number, par?: string): string {
  // una divisa se dice con sus decimales fijos: «18.10», no «18.1»; y el peso
  // argentino entero, sin «k»: «1,602» es como se lee en una casa de cambio
  const divisa = par ? DIVISA[par] : undefined;
  if (divisa) return strike.toFixed(divisa.decimales);
  if (strike >= 1000) {
    const miles = strike / 1000;
    return `${Number.isInteger(miles) ? miles : miles.toFixed(1)}k`;
  }
  // un strike de SOL lleva decimales (117.5): redondearlo en la etiqueta
  // diría otra cifra que la del criterio
  return Number.isInteger(strike) ? String(strike) : String(Number(strike.toFixed(2)));
}

export function velaSeed(vela: VelaViva): OwnMarketSeed {
  const { activo, intervalo, inicio } = vela;
  const strike = redondearStrike(vela.spot, pasoDeStrike(activo.par));
  const fin = finDeVentana(inicio, intervalo);
  const cierra = bloqueoDeVentana(inicio, intervalo);
  const divisa = DIVISA[activo.par];
  const strikeTexto = divisa ? strike.toFixed(divisa.decimales) : conSeparador(strike);
  const abre = relojUtc(inicio);
  const cierraReloj = relojUtc(fin);
  const fuente = divisa ? "Bitso" : "Kraken";
  const moneda = divisa?.moneda ?? "dólares";

  const rule: VelaRule = { kind: "vela", par: activo.par, intervalo, inicio, strike };

  return {
    id: idDeVela(activo, intervalo, inicio),
    title: `${activo.nombre} en ${intervalo} min: ¿arriba o abajo de ${strikeTexto}?`,
    // el título de la tarjeta: una línea, afirmativo y con la hora de cierre,
    // que es el dato que decide si te da tiempo de entrar
    shortTitle: `${activo.corto ?? activo.nombre} · vela de ${intervalo} min`,
    // el dólar es economía, no cripto: la pestaña de cripto no es donde se
    // busca el tipo de cambio
    category: divisa ? "economia" : "cripto",
    country: divisa?.country ?? "LATAM",
    closesAt: new Date(cierra).toISOString(),
    pool: pozoSimetrico(),
    outcomes: [
      // sin "de": con decimales, `Arriba de 63.9k` no cabe en la columna y se
      // recortaba en el número. El título de la card dice de qué activo se
      // habla, así que la preposición era lo único prescindible
      { id: ARRIBA, label: `Arriba ${strikeCorto(strike, activo.par)}` },
      { id: ABAJO, label: `Abajo ${strikeCorto(strike, activo.par)}` },
    ],
    rule,
    resolution: {
      sourceName: divisa
        ? `Bitso (velas de ${intervalo} minutos de ${activo.par}, públicas; casa de cambio regulada en México)`
        : `Kraken (velas de ${intervalo} minutos, públicas)`,
      sourceUrl: urlVela(activo.par, intervalo),
      criterion:
        `Se resuelve Arriba si la vela de ${intervalo} minutos de ${activo.par} en ${fuente} ` +
        `que abre a las ${abre} UTC y cierra a las ${cierraReloj} UTC cierra por encima de ` +
        `${strikeTexto} ${moneda}. Cierre igual al strike resuelve Abajo. Se lee del endpoint ` +
        `público de ${fuente}, que cualquiera puede consultar.` +
        (divisa
          ? " El cierre es el último precio operado de la vela (last_rate); una vela sin operaciones repite el cierre anterior, tal como la publica Bitso."
          : ""),
      settlesAt: new Date(fin).toISOString(),
      // sesenta segundos: el dato ya está publicado y se re-verifica con una
      // sola consulta a la URL citada. Ver `liveVerification` en resolution.ts
      disputeWindowHours: 1 / 60,
      liveVerification: true,
    },
  };
}

/**
 * Las velas que deberían existir ahora mismo, por activo e intervalo.
 *
 * Devuelve la vela en curso y, cuando ya entramos en los últimos diez segundos,
 * también la siguiente: ése es el momento en que la actual deja de aceptar
 * apuestas, y no puede haber un instante sin mercado abierto.
 *
 * El precio entra como argumento y no se busca aquí: esta función es pura, y el
 * que no haya precio para un par significa que ese par no genera mercado.
 */
export function velasVigentes(input: {
  ahora: number;
  precio: (par: VelaRule["par"]) => number | undefined;
  intervalos?: readonly IntervaloVivo[];
  activos?: ActivoVivo[];
}): VelaViva[] {
  const intervalos = input.intervalos ?? ([5, 15] as const);
  const activos = input.activos ?? ACTIVOS_VIVOS;
  const velas: VelaViva[] = [];

  for (const activo of activos) {
    const spot = input.precio(activo.par);
    // sin lectura fresca no se inventa un strike: se genera un mercado menos
    if (!spot || !Number.isFinite(spot) || spot <= 0) continue;

    for (const intervalo of intervalos) {
      if (activo.intervalos && !activo.intervalos.includes(intervalo)) continue;
      const inicio = inicioDeVentana(input.ahora, intervalo);
      velas.push({ activo, intervalo, inicio, spot });
      if (input.ahora >= bloqueoDeVentana(inicio, intervalo)) {
        velas.push({
          activo,
          intervalo,
          inicio: finDeVentana(inicio, intervalo),
          spot,
        });
      }
    }
  }
  return velas;
}

/** Con su especificación ya validada, listo para publicarse. */
export function velasSeeds(
  input: Parameters<typeof velasVigentes>[0],
): OwnMarketSeed[] {
  return velasVigentes(input).map((vela) => {
    const seed = velaSeed(vela);
    return { ...seed, resolution: assertPublishable(seed.resolution) };
  });
}
