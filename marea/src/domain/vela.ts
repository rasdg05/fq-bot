/**
 * Ventanas de vela alineadas al reloj.
 *
 * Un mercado de cinco minutos que arranca cuando alguien abre la app no es un
 * mercado: dos personas verían preguntas distintas sobre lo mismo. La ventana
 * se calcula del reloj —`16:35`, `16:40`, `16:45`— y sale igual en el servidor,
 * en el navegador y en el endpoint público de Kraken, que publica sus velas
 * sobre esa misma rejilla.
 *
 * Todo aquí es aritmética pura sobre milisegundos UTC: sin red, sin estado y
 * sin zona horaria. Es lo que permite probarlo sin inventar un reloj falso.
 */

/** Los intervalos que Kraken publica nativamente y que usamos. */
export const INTERVALOS_VIVOS = [5, 15] as const;
export type IntervaloVivo = (typeof INTERVALOS_VIVOS)[number];

/**
 * Cuánto antes del cierre de la vela dejan de aceptarse apuestas.
 *
 * No es cero a propósito: apostar con un segundo de vela por delante es apostar
 * sobre algo que ya pasó, y el pozo lo pagaría el resto (R-043). Diez segundos
 * es el mínimo que deja el margen sin volver inútil el último minuto, que es
 * justo cuando la gente juega.
 *
 * Es también el momento en que nace la vela siguiente: así nunca hay un hueco
 * sin mercado abierto.
 */
export const BLOQUEO_MS = 10_000;

/**
 * Cuánto se espera después del cierre antes de dar la vela por publicada.
 * Kraken sella la vela al cerrarla, pero el dato tarda en propagarse; leer al
 * segundo exacto devuelve la vela todavía en curso.
 */
export const GRACIA_VELA_MS = 20_000;

export function ventanaMs(intervalo: IntervaloVivo): number {
  return intervalo * 60_000;
}

/** Apertura de la vela que está corriendo ahora mismo. */
export function inicioDeVentana(ahora: number, intervalo: IntervaloVivo): number {
  const paso = ventanaMs(intervalo);
  return Math.floor(ahora / paso) * paso;
}

export function finDeVentana(inicio: number, intervalo: IntervaloVivo): number {
  return inicio + ventanaMs(intervalo);
}

/** Cuándo dejan de aceptarse apuestas de esta vela. */
export function bloqueoDeVentana(inicio: number, intervalo: IntervaloVivo): number {
  return finDeVentana(inicio, intervalo) - BLOQUEO_MS;
}

/**
 * Paso de redondeo del strike, por par.
 *
 * El strike se dice en voz alta —"arriba de 71,200"— así que se redondea. Pero
 * redondear mucho inclina el mercado antes de que empiece: si el paso es grande
 * frente a lo que se mueve el precio en cinco minutos, la pregunta ya viene
 * contestada. El criterio es que el paso no pase del 0.1 % del precio.
 */
export function pasoDeStrike(par: string): number {
  return par === "BTC/USD" ? 100 : 5;
}

export function redondearStrike(precio: number, paso: number): number {
  return Math.round(precio / paso) * paso;
}

/** `16:35` en UTC — cómo se nombra la vela en el criterio publicado. */
export function relojUtc(ms: number): string {
  const fecha = new Date(ms);
  const hh = String(fecha.getUTCHours()).padStart(2, "0");
  const mm = String(fecha.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

/** `20260729T1635` — la parte del id que hace única a cada vela. */
export function claveDeVentana(inicio: number): string {
  return new Date(inicio).toISOString().replace(/[-:]/g, "").slice(0, 13);
}

/** `02:41` — la cuenta regresiva tal como se pinta en la card. */
export function cuentaRegresiva(restanteMs: number): string {
  const seguro = Math.max(0, Math.floor(restanteMs / 1000));
  const mm = String(Math.floor(seguro / 60)).padStart(2, "0");
  const ss = String(seguro % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

/**
 * Variación del spot contra el strike, en puntos porcentuales.
 *
 * Se mide contra el strike y no contra la apertura real de la vela a propósito:
 * el strike **es** la apertura redondeada, y es el número contra el que se
 * liquida. Enseñar una variación medida contra otra cosa sería enseñar un
 * número que no decide nada.
 */
export function deltaPp(spot: number, strike: number): number {
  if (!Number.isFinite(spot) || !Number.isFinite(strike) || strike <= 0) return 0;
  return ((spot - strike) / strike) * 100;
}

/**
 * Umbral de animación del porcentaje. Por debajo de esto el número cambia sin
 * transición: una card que parpadea cada dos segundos por medio punto es ruido,
 * no información.
 */
export const UMBRAL_ANIMACION_PP = 0.5;
