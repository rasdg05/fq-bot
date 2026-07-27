/**
 * Modelo propio de probabilidad para mercados de precio.
 *
 * Esta es la lectura de Marea: para una pregunta del tipo "¿X cierra arriba de
 * K en la fecha T?", la probabilidad se calcula con el precio de hoy, la
 * volatilidad reciente y el tiempo que falta. No es una opinión ni una señal:
 * es una cuenta que cualquiera puede rehacer con datos públicos (R-030).
 *
 * Supuesto explícito: los rendimientos logarítmicos son aproximadamente
 * normales con volatilidad constante en el horizonte. Es el supuesto estándar
 * y es **falso en las colas** — los mercados saltan más de lo que dice la
 * campana—. Por eso el modelo se calibra contra historia real antes de
 * mostrarse, y por eso `scripts/calibrate.mts` existe.
 *
 * Sólo aplica a preguntas de precio con umbral. Para "¿Banxico baja la tasa?"
 * este modelo no dice nada, y decir que sí sería inventar.
 */

export type Direction = "above" | "below";

export interface PriceQuestion {
  /** Precio actual del subyacente. */
  spot: number;
  /** Umbral de la pregunta. */
  strike: number;
  direction: Direction;
  /** Días calendario hasta la resolución. */
  daysToResolve: number;
  /** Volatilidad anualizada, en tanto por uno (0.45 = 45 %). */
  annualVolatility: number;
  /**
   * Si la pregunta se resuelve por tocar el umbral en cualquier momento
   * ("¿toca 4,500 antes de octubre?") en lugar de por el valor final.
   */
  touch?: boolean;
}

/** Días hábiles al año para anualizar. Cripto opera todos los días. */
export const TRADING_DAYS = 365;

/**
 * Función de distribución normal acumulada. Aproximación de Abramowitz y
 * Stegun 26.2.17: error máximo 7.5e-8, de sobra para mostrar un porcentaje.
 */
export function normalCdf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const z = Math.abs(x) / Math.SQRT2;
  const t = 1 / (1 + 0.3275911 * z);
  const y =
    1 -
    ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t +
      0.254829592) *
      t *
      Math.exp(-z * z);
  return 0.5 * (1 + sign * y);
}

/**
 * Probabilidad de que el precio final quede del lado de la pregunta.
 *
 * Bajo el supuesto lognormal sin deriva (no pronosticamos dirección: eso sería
 * una señal, y no es lo que hacemos), la probabilidad de terminar arriba de K
 * es `N(-d)` con `d = ln(K/S) / (σ√t)`.
 */
export function terminalProbability(question: PriceQuestion): number {
  const { spot, strike, direction, daysToResolve, annualVolatility } = question;
  if (spot <= 0 || strike <= 0 || annualVolatility <= 0) return 0.5;

  const t = Math.max(daysToResolve, 0) / TRADING_DAYS;
  if (t <= 0) {
    // ya venció: la respuesta la da el precio, no el modelo
    const above = spot > strike;
    return direction === "above" ? (above ? 1 : 0) : above ? 0 : 1;
  }

  const sigma = annualVolatility * Math.sqrt(t);
  // sin deriva: el punto medio de la distribución es el precio de hoy
  const d = Math.log(strike / spot) / sigma;
  const pAbove = normalCdf(-d);
  return direction === "above" ? pAbove : 1 - pAbove;
}

/**
 * Probabilidad de **tocar** el umbral antes del vencimiento.
 *
 * Para un movimiento browniano sin deriva, la probabilidad de que el máximo
 * supere una barrera es el doble de la de terminar arriba (principio de
 * reflexión). Tocar siempre es más probable que terminar arriba, y por eso una
 * pregunta de "toca" nunca puede valer menos que una de "cierra".
 */
export function touchProbability(question: PriceQuestion): number {
  const terminal = terminalProbability(question);
  return Math.min(1, 2 * terminal);
}

export function priceProbability(question: PriceQuestion): number {
  const raw = question.touch
    ? touchProbability(question)
    : terminalProbability(question);
  // 0 y 100 % no existen mientras el mercado esté abierto
  return Math.min(0.99, Math.max(0.01, raw));
}

/**
 * Volatilidad anualizada a partir de cierres diarios. Desviación estándar de
 * los rendimientos logarítmicos, escalada por la raíz del tiempo.
 */
export function realizedVolatility(closes: number[]): number | null {
  if (closes.length < 10) return null;
  const returns: number[] = [];
  for (let i = 1; i < closes.length; i += 1) {
    if (closes[i] > 0 && closes[i - 1] > 0) {
      returns.push(Math.log(closes[i] / closes[i - 1]));
    }
  }
  if (returns.length < 9) return null;

  const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
  const variance =
    returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) /
    (returns.length - 1);
  return Math.sqrt(variance) * Math.sqrt(TRADING_DAYS);
}

/** El porqué, en una frase que el usuario puede verificar. */
export function priceBasis(question: PriceQuestion): string {
  const vol = Math.round(question.annualVolatility * 100);
  const dias = Math.round(question.daysToResolve);
  return `Calculado con el precio de hoy, la volatilidad de ${vol}% anual de los últimos 30 días y los ${dias} días que faltan.`;
}


/* ---------------------------------------------------------------------------
   Recalibración
   ---------------------------------------------------------------------------
   El modelo crudo sale sesgado en las colas: la campana subestima los saltos
   grandes, así que "casi seguro" falla más seguido de lo que dice la cuenta.
   Medido contra 721 velas de BTC y ETH, el sesgo llega a −10 pp en el tramo
   90-100 % para preguntas de cierre, y a −15 pp en todo el rango para
   preguntas de "toca".

   La corrección es un escalado de Platt sobre las probabilidades logarítmicas:
   dos parámetros, ajustados **fuera de muestra** (`npm run calibrate`). Si el
   ajuste no baja el error por debajo del umbral, el modelo no se usa: un Edge
   que sale de un modelo descalibrado es un Edge inventado (R-031).
--------------------------------------------------------------------------- */

export interface Calibration {
  /** Pendiente sobre las probabilidades logarítmicas. */
  a: number;
  /** Desplazamiento. */
  b: number;
  /** Error de calibración esperado, fuera de muestra, en puntos porcentuales. */
  eceOutOfSample: number;
  /** Cuándo se ajustó, para saber si ya envejeció. */
  fittedAt?: string;
}

const EPSILON = 1e-6;

export function logit(p: number): number {
  const clamped = Math.min(1 - EPSILON, Math.max(EPSILON, p));
  return Math.log(clamped / (1 - clamped));
}

export function sigmoid(x: number): number {
  return 1 / (1 + Math.exp(-x));
}

export function applyCalibration(p: number, calibration: Calibration): number {
  return Math.min(0.99, Math.max(0.01, sigmoid(calibration.a * logit(p) + calibration.b)));
}

/**
 * Umbral de uso. El Edge se muestra a partir de 4 pp de diferencia, así que un
 * modelo que se equivoca 2 pp o más en promedio no puede sostenerlo: la mitad
 * del Edge sería error del modelo.
 */
export const MAX_USABLE_ECE_PP = 2;

export function isUsable(calibration: Calibration): boolean {
  return calibration.eceOutOfSample <= MAX_USABLE_ECE_PP;
}
