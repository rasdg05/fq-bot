import type { Oracle, OracleQuery, OracleReading } from "@/domain/settlement";
import type { VelaRule } from "@/domain/oracleRule";
import { GRACIA_VELA_MS, relojUtc } from "@/domain/vela";
import { ABAJO, ARRIBA, urlKrakenVela } from "@/adapters/ownMarkets/cryptoLive";

/**
 * Oráculo de vela corta. Resuelve los mercados vivos de 5 y 15 minutos contra
 * el mismo endpoint público de Kraken que cita el criterio.
 *
 * Kraken publica esos intervalos nativamente, así que no reconstruimos nada:
 * pedimos `interval=5` y buscamos la vela cuya apertura es exactamente la de la
 * pregunta. Componerla desde velas de un minuto habría metido una cuenta
 * nuestra en medio de la liquidación, y entonces el usuario ya no podría
 * re-verificar el resultado con la URL que le prometimos.
 *
 * **Qué se lee para pagar (decisión, `vault/CRYPTO_LIVE.md`):** el *cierre
 * exacto* de la vela, no un promedio de los últimos 30-60 s. El cierre es un
 * número que Kraken sella y que cualquiera vuelve a leer con una consulta; un
 * promedio exigiría que el usuario rehiciera nuestra aritmética para
 * comprobarnos, que es justo lo contrario de lo que vendemos.
 *
 * Empate exacto resuelve `abajo`: `arriba` pide cierre estrictamente mayor, y
 * así está escrito en el criterio publicado.
 */

type VelaKraken = { inicio: number; cierre: number };

export interface VelaOracleOptions {
  fetchImpl?: typeof fetch;
  /** Se inyecta en pruebas para no depender de la red. */
  cargarVelas?: (
    par: VelaRule["par"],
    intervalo: VelaRule["intervalo"],
    desde: number,
  ) => Promise<VelaKraken[]>;
  /**
   * Cuánto vale una respuesta de Kraken antes de volver a pedirla. El ciclo
   * vivo corre cada pocos segundos y mira varios mercados del mismo par: sin
   * caché haríamos una consulta por mercado para leer exactamente la misma
   * lista de velas.
   */
  cacheMs?: number;
  now?: () => number;
}

const KRAKEN_PARES: Record<VelaRule["par"], string> = {
  "BTC/USD": "XBTUSD",
  "ETH/USD": "ETHUSD",
};

async function pedirVelas(
  fetchImpl: typeof fetch,
  par: VelaRule["par"],
  intervalo: VelaRule["intervalo"],
  desde: number,
): Promise<VelaKraken[]> {
  const url =
    `https://api.kraken.com/0/public/OHLC?pair=${KRAKEN_PARES[par]}` +
    `&interval=${intervalo}&since=${Math.floor(desde / 1000)}`;
  const respuesta = await fetchImpl(url);
  if (!respuesta.ok) throw new Error(`Kraken respondió ${respuesta.status}`);
  const cuerpo = (await respuesta.json()) as {
    error?: string[];
    result?: Record<string, unknown>;
  };
  if (cuerpo.error?.length) throw new Error(cuerpo.error.join("; "));
  const serie = Object.entries(cuerpo.result ?? {}).find(([clave]) => clave !== "last");
  if (!serie) throw new Error("Kraken no devolvió velas");
  return (serie[1] as unknown[][]).map((fila) => ({
    inicio: Number(fila[0]) * 1000,
    cierre: Number(fila[4]),
  }));
}

function monto(valor: number): string {
  return valor.toLocaleString("es-MX", { maximumFractionDigits: 2 });
}

export function createVelaOracle(options: VelaOracleOptions = {}): Oracle {
  const ahora = options.now ?? (() => Date.now());
  const cacheMs = options.cacheMs ?? 5_000;
  const cargar =
    options.cargarVelas ??
    ((par: VelaRule["par"], intervalo: VelaRule["intervalo"], desde: number) =>
      pedirVelas(options.fetchImpl ?? fetch, par, intervalo, desde));

  const cache = new Map<string, { at: number; velas: Promise<VelaKraken[]> }>();

  function velasDe(
    par: VelaRule["par"],
    intervalo: VelaRule["intervalo"],
    desde: number,
  ): Promise<VelaKraken[]> {
    const clave = `${par}|${intervalo}`;
    const guardado = cache.get(clave);
    if (guardado && ahora() - guardado.at < cacheMs) return guardado.velas;
    // se guarda la promesa, no el resultado: dos mercados del mismo par
    // resueltos en el mismo tick comparten una sola consulta
    const velas = cargar(par, intervalo, desde).catch((error) => {
      cache.delete(clave);
      throw error;
    });
    cache.set(clave, { at: ahora(), velas });
    return velas;
  }

  return {
    id: "kraken-vela",

    handles(query: OracleQuery): boolean {
      return query.rule?.kind === "vela" && query.rule.par in KRAKEN_PARES;
    },

    async read(query: OracleQuery): Promise<OracleReading> {
      const rule = query.rule as VelaRule;
      const ventana = rule.intervalo * 60_000;
      const fin = rule.inicio + ventana;
      const reloj = `${relojUtc(rule.inicio)}–${relojUtc(fin)} UTC`;

      // antes del cierre no hay nada que leer, y la gracia evita quedarnos con
      // la vela todavía en curso, que Kraken devuelve como si fuera una más
      if (query.now < fin + GRACIA_VELA_MS) {
        return {
          status: "sin_dato",
          evidence: `La vela de ${rule.intervalo} min de ${rule.par} (${reloj}) todavía no cierra.`,
        };
      }

      // se piden un par de velas de contexto: hace falta ver la siguiente para
      // saber que la nuestra ya cerró de verdad
      const velas = await velasDe(rule.par, rule.intervalo, rule.inicio - 2 * ventana);
      const vela = velas.find((candidata) => candidata.inicio === rule.inicio);
      const haySiguiente = velas.some((candidata) => candidata.inicio >= fin);

      if (!vela || !haySiguiente) {
        return {
          status: "sin_dato",
          evidence: `Kraken todavía no publica cerrada la vela de ${rule.par} de ${reloj}.`,
        };
      }
      if (!Number.isFinite(vela.cierre)) {
        return {
          status: "sin_dato",
          evidence: `Kraken devolvió la vela de ${rule.par} de ${reloj} sin cierre legible.`,
        };
      }

      // `arriba` exige estrictamente mayor: el empate exacto paga `abajo`, tal
      // como lo dice el criterio que se publicó antes de aceptar apuestas
      const outcome = vela.cierre > rule.strike ? ARRIBA : ABAJO;
      return {
        status: "resuelto",
        outcome,
        evidence:
          `Vela de ${rule.intervalo} min de ${rule.par} en Kraken (${reloj}): cierre ` +
          `${monto(vela.cierre)} USD frente al strike de ${monto(rule.strike)}. ` +
          `Verificable en ${urlKrakenVela(rule.par, rule.intervalo)}`,
      };
    },
  };
}
