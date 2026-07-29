/**
 * Ventanas intradía alineadas al reloj.
 *
 * Un mercado de 5 minutos no empieza cuando alguien pulsa un botón: empieza a
 * las 08:35:00 en punto y cierra a las 08:40:00. Alinear al reloj es lo que
 * hace que la vela del mercado y la vela pública del exchange sean **la misma
 * vela** — y por eso cualquiera puede abrir la URL de Kraken y comprobar el
 * resultado. Una ventana que empieza a las 08:36:23 no se puede auditar contra
 * nada.
 *
 * Todo el módulo es aritmética pura sobre milisegundos UTC. No sabe de precios,
 * de pozos ni de red.
 */

/** Duraciones vigentes, en minutos. Son las dos que se juegan en vivo. */
export type DuracionVela = 5 | 15;

export const DURACIONES: readonly DuracionVela[] = [5, 15];

export interface Ventana {
  /** Inicio de la vela, en ms UTC. Múltiplo exacto de la duración. */
  inicio: number;
  /** Cierre de la vela, en ms UTC. Es el instante que resuelve. */
  cierre: number;
  minutos: DuracionVela;
  /** `2026-07-29T08:35Z`, para armar ids legibles y estables. */
  clave: string;
}

const MINUTO_MS = 60_000;

/**
 * Cuánto antes del cierre dejan de aceptarse apuestas.
 *
 * En un pozo compartido, quien apuesta con el precio a un segundo del cierre no
 * está prediciendo: está cobrando. Se lleva parte del pozo de los que sí
 * arriesgaron, sin haber arriesgado. Treinta segundos es lo que hace que la
 * apuesta siga siendo una apuesta (R-043 aplicado a intradía).
 */
export const CIERRE_ANTES_MS = 30_000;

/**
 * Con cuánta antelación se siembra la vela siguiente. Es lo que garantiza que
 * **siempre** haya un mercado abierto: la próxima ya existe cuando la actual
 * deja de aceptar apuestas.
 */
export const SIEMBRA_ANTES_MS = 45_000;

function clave(inicio: number): string {
  return new Date(inicio).toISOString().slice(0, 16) + "Z";
}

/** La ventana de `minutos` que contiene a `ahora`. */
export function ventanaDe(ahora: number, minutos: DuracionVela): Ventana {
  const paso = minutos * MINUTO_MS;
  const inicio = Math.floor(ahora / paso) * paso;
  return { inicio, cierre: inicio + paso, minutos, clave: clave(inicio) };
}

export function siguienteVentana(ventana: Ventana): Ventana {
  const paso = ventana.minutos * MINUTO_MS;
  const inicio = ventana.inicio + paso;
  return { inicio, cierre: inicio + paso, minutos: ventana.minutos, clave: clave(inicio) };
}

/** Hasta cuándo se puede apostar en esta ventana. */
export function cierreDeApuestas(ventana: Ventana): number {
  return ventana.cierre - CIERRE_ANTES_MS;
}

/**
 * Las ventanas que deben existir ahora mismo para una duración: la actual y,
 * cuando la actual está por dejar de aceptar apuestas, también la siguiente.
 * Nunca hay un momento sin mercado abierto.
 */
export function ventanasVivas(ahora: number, minutos: DuracionVela): Ventana[] {
  const actual = ventanaDe(ahora, minutos);
  const ventanas = [actual];
  if (cierreDeApuestas(actual) - ahora <= SIEMBRA_ANTES_MS) {
    ventanas.push(siguienteVentana(actual));
  }
  return ventanas;
}

/**
 * El strike: el precio de apertura de la vela, redondeado a un número que se
 * dice en voz alta.
 *
 * `71,183.42` no es una pregunta, es un ruido. `71,200` sí. El paso depende del
 * activo porque un paso de 100 en ETH sería la mitad del precio.
 */
export function strikeLegible(spot: number, paso: number): number {
  return Math.round(spot / paso) * paso;
}

/** `mm:ss`. Lo que se pinta en el badge de cuenta regresiva. */
export function cuentaRegresiva(restanteMs: number): string {
  const total = Math.max(0, Math.floor(restanteMs / 1000));
  const minutos = Math.floor(total / 60);
  const segundos = total % 60;
  return `${minutos}:${String(segundos).padStart(2, "0")}`;
}
