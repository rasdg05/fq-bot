import { assertPublishable } from "@/domain/resolution";
import { SEED, type Pool } from "@/domain/parimutuel";
import type { VelaRule } from "@/domain/oracleRule";
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
  id: "btc" | "eth";
  par: VelaRule["par"];
  nombre: string;
}

export const ACTIVOS_VIVOS: ActivoVivo[] = [
  { id: "btc", par: "BTC/USD", nombre: "Bitcoin" },
  { id: "eth", par: "ETH/USD", nombre: "Ethereum" },
];

const KRAKEN_PARES: Record<VelaRule["par"], string> = {
  "BTC/USD": "XBTUSD",
  "ETH/USD": "ETHUSD",
};

export function urlKrakenVela(par: VelaRule["par"], intervalo: IntervaloVivo): string {
  return `https://api.kraken.com/0/public/OHLC?pair=${KRAKEN_PARES[par]}&interval=${intervalo}`;
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
export function velaSeed(vela: VelaViva): OwnMarketSeed {
  const { activo, intervalo, inicio } = vela;
  const strike = redondearStrike(vela.spot, pasoDeStrike(activo.par));
  const fin = finDeVentana(inicio, intervalo);
  const cierra = bloqueoDeVentana(inicio, intervalo);
  const strikeTexto = conSeparador(strike);
  const abre = relojUtc(inicio);
  const cierraReloj = relojUtc(fin);

  const rule: VelaRule = { kind: "vela", par: activo.par, intervalo, inicio, strike };

  return {
    id: idDeVela(activo, intervalo, inicio),
    title: `${activo.nombre} en ${intervalo} min: ¿arriba o abajo de ${strikeTexto}?`,
    // el título de la tarjeta: una línea, afirmativo y con la hora de cierre,
    // que es el dato que decide si te da tiempo de entrar
    shortTitle: `${activo.nombre} · vela de ${intervalo} min`,
    category: "cripto",
    country: "LATAM",
    closesAt: new Date(cierra).toISOString(),
    pool: pozoSimetrico(),
    outcomes: [
      { id: ARRIBA, label: `Arriba de ${strikeTexto}` },
      { id: ABAJO, label: `Abajo de ${strikeTexto}` },
    ],
    rule,
    resolution: {
      sourceName: `Kraken (velas de ${intervalo} minutos, públicas)`,
      sourceUrl: urlKrakenVela(activo.par, intervalo),
      criterion:
        `Se resuelve Arriba si la vela de ${intervalo} minutos de ${activo.par} en Kraken ` +
        `que abre a las ${abre} UTC y cierra a las ${cierraReloj} UTC cierra por encima de ` +
        `${strikeTexto} dólares. Cierre igual al strike resuelve Abajo. Se lee del endpoint ` +
        `público de Kraken, que cualquiera puede consultar.`,
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
