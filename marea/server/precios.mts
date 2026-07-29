/**
 * Ticker de spot. Una sola lectura para todos, en el servidor, cada pocos
 * segundos — no una por dispositivo: con mil personas mirando la misma vela, un
 * ticker por navegador es mil veces la misma pregunta al mismo endpoint.
 *
 * Dos fuentes, con precedencia declarada:
 *
 *  1. **El motor FQ**, que ya analiza las monedas grandes. Es la fuente
 *     primaria cuando `MAREA_FQ_PRECIOS_URL` está configurada.
 *  2. **Kraken público**, como respaldo. Se usa si el motor tarda más de 5 s,
 *     falla, o simplemente no está configurado.
 *
 * Lo que **nunca** cambia de fuente es la liquidación: el strike y el cierre se
 * leen de las velas públicas de Kraken, que es lo que cita el criterio. El
 * ticker sólo mueve el número que se ve mientras la vela corre. Cuando las dos
 * fuentes no coinciden al milímetro, la que manda para pagar es la citada, y por
 * eso la card declara de dónde viene el precio que enseña (R-022).
 *
 * Nunca se sirve una lectura vieja como si fuera de ahora: pasada la ventana de
 * frescura, el ticker responde "no sé", y la card enseña ausencia en vez de un
 * número que dejó de ser cierto.
 */

export type FuentePrecio = "fq" | "kraken";

export interface Tick {
  precio: number;
  /** Cuándo se leyó, ms. */
  at: number;
  fuente: FuentePrecio;
}

export interface TickerOptions {
  /** Endpoint del motor FQ. Sin él, el respaldo es la fuente primaria. */
  urlFq?: string;
  fetchImpl?: typeof fetch;
  /** Cada cuánto se pide el precio. */
  intervaloMs?: number;
  /** Arriba de esto el motor se considera lento y se usa el respaldo. */
  latenciaMaximaMs?: number;
  /** Cuánto vale una lectura antes de dejar de mostrarse. */
  frescuraMs?: number;
  /** Cuánto se castiga al motor tras una lectura lenta o fallida. */
  castigoMs?: number;
  now?: () => number;
  onError?: (mensaje: string) => void;
}

/** Los pares que seguimos. Es el mismo conjunto que genera mercados vivos. */
export const PARES_VIVOS = ["BTC/USD", "ETH/USD"] as const;
export type ParVivo = (typeof PARES_VIVOS)[number];

const KRAKEN_TICKER = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD,ETHUSD";

/** Lo que devuelve cualquiera de las dos fuentes: par → precio. */
type Lectura = Partial<Record<ParVivo, number>>;

function normalizarClave(clave: string): ParVivo | undefined {
  const limpia = clave.toUpperCase();
  if (/^(BTC|XBT|XXBT)/.test(limpia)) return "BTC/USD";
  if (/^(ETH|XETH)/.test(limpia)) return "ETH/USD";
  return undefined;
}

/**
 * Lee el motor FQ. Acepta las dos formas razonables de responder —el mapa
 * pelón o envuelto en `precios`— porque el motor es nuestro y la frontera no
 * merece un contrato ceremonioso.
 */
export async function leerFq(
  fetchImpl: typeof fetch,
  url: string,
  timeoutMs: number,
): Promise<Lectura> {
  const corte = AbortSignal.timeout(timeoutMs);
  const respuesta = await fetchImpl(url, { signal: corte });
  if (!respuesta.ok) throw new Error(`el motor FQ respondió ${respuesta.status}`);
  const cuerpo = (await respuesta.json()) as Record<string, unknown>;
  const crudo = (cuerpo.precios ?? cuerpo) as Record<string, unknown>;
  const lectura: Lectura = {};
  for (const [clave, valor] of Object.entries(crudo)) {
    const par = normalizarClave(clave);
    const precio = Number(
      typeof valor === "object" && valor !== null
        ? (valor as { precio?: unknown; price?: unknown }).precio ??
            (valor as { price?: unknown }).price
        : valor,
    );
    if (par && Number.isFinite(precio) && precio > 0) lectura[par] = precio;
  }
  if (Object.keys(lectura).length === 0) {
    throw new Error("el motor FQ no devolvió ningún par conocido");
  }
  return lectura;
}

export async function leerKraken(
  fetchImpl: typeof fetch,
  timeoutMs: number,
): Promise<Lectura> {
  const respuesta = await fetchImpl(KRAKEN_TICKER, {
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!respuesta.ok) throw new Error(`Kraken respondió ${respuesta.status}`);
  const cuerpo = (await respuesta.json()) as {
    error?: string[];
    result?: Record<string, { c?: string[] }>;
  };
  if (cuerpo.error?.length) throw new Error(cuerpo.error.join("; "));
  const lectura: Lectura = {};
  for (const [clave, dato] of Object.entries(cuerpo.result ?? {})) {
    const par = normalizarClave(clave);
    const ultimo = Number(dato.c?.[0]);
    if (par && Number.isFinite(ultimo) && ultimo > 0) lectura[par] = ultimo;
  }
  return lectura;
}

export interface Ticker {
  /** El último precio del par, o `undefined` si no hay lectura fresca. */
  precio(par: string): Tick | undefined;
  /** Una vuelta de lectura. Se llama sola con `arrancar`. */
  refrescar(): Promise<void>;
  arrancar(): void;
  detener(): void;
  estado(): {
    fuente: FuentePrecio | null;
    motorDegradado: boolean;
    ultimaLatenciaMs: number | null;
    pares: Record<string, { precio: number; at: string; fuente: FuentePrecio }>;
  };
}

export function crearTicker(options: TickerOptions = {}): Ticker {
  const ahora = options.now ?? (() => Date.now());
  const fetchImpl = options.fetchImpl ?? fetch;
  const intervaloMs = options.intervaloMs ?? 3_000;
  const latenciaMaxima = options.latenciaMaximaMs ?? 5_000;
  // tres vueltas de ticker: una lectura de hace diez segundos ya no es "ahora"
  const frescuraMs = options.frescuraMs ?? Math.max(10_000, intervaloMs * 3);
  const castigoMs = options.castigoMs ?? 60_000;

  const ticks = new Map<ParVivo, Tick>();
  let temporizador: ReturnType<typeof setInterval> | null = null;
  let corriendo = false;
  let motorCastigadoHasta = 0;
  let ultimaLatencia: number | null = null;
  let ultimaFuente: FuentePrecio | null = null;

  function guardar(lectura: Lectura, fuente: FuentePrecio, at: number) {
    for (const par of PARES_VIVOS) {
      const precio = lectura[par];
      if (precio !== undefined) ticks.set(par, { precio, at, fuente });
    }
    ultimaFuente = fuente;
  }

  async function refrescar(): Promise<void> {
    // una vuelta a la vez: si el motor tarda, no se apilan lecturas encima
    if (corriendo) return;
    corriendo = true;
    try {
      const t0 = ahora();
      if (options.urlFq && t0 >= motorCastigadoHasta) {
        try {
          const lectura = await leerFq(fetchImpl, options.urlFq, latenciaMaxima);
          const latencia = ahora() - t0;
          ultimaLatencia = latencia;
          if (latencia <= latenciaMaxima) {
            guardar(lectura, "fq", ahora());
            return;
          }
          // llegó, pero tarde: el dato sirve y el motor se castiga un rato
          guardar(lectura, "fq", ahora());
          motorCastigadoHasta = ahora() + castigoMs;
          options.onError?.(`motor FQ lento (${latencia} ms): se usa el respaldo`);
          return;
        } catch (error) {
          motorCastigadoHasta = ahora() + castigoMs;
          options.onError?.(`motor FQ no respondió: ${String(error)}`);
        }
      }

      try {
        const lectura = await leerKraken(fetchImpl, latenciaMaxima);
        guardar(lectura, "kraken", ahora());
      } catch (error) {
        // sin lectura nueva no se pisa la vieja: envejece sola y deja de
        // servirse cuando pasa la ventana de frescura
        options.onError?.(`ticker sin fuente: ${String(error)}`);
      }
    } finally {
      corriendo = false;
    }
  }

  return {
    precio(par: string): Tick | undefined {
      const tick = ticks.get(par as ParVivo);
      if (!tick) return undefined;
      // una lectura vieja no se sirve como si fuera de ahora
      return ahora() - tick.at <= frescuraMs ? tick : undefined;
    },

    refrescar,

    arrancar() {
      if (temporizador) return;
      void refrescar();
      temporizador = setInterval(() => void refrescar(), intervaloMs);
      // el ticker no puede ser la razón por la que el proceso no termina
      temporizador.unref?.();
    },

    detener() {
      if (temporizador) clearInterval(temporizador);
      temporizador = null;
    },

    estado() {
      const pares: Record<string, { precio: number; at: string; fuente: FuentePrecio }> = {};
      for (const [par, tick] of ticks) {
        pares[par] = {
          precio: tick.precio,
          at: new Date(tick.at).toISOString(),
          fuente: tick.fuente,
        };
      }
      return {
        fuente: ultimaFuente,
        motorDegradado: ahora() < motorCastigadoHasta,
        ultimaLatenciaMs: ultimaLatencia,
        pares,
      };
    },
  };
}
