/**
 * Motor parimutuel. Es la mecánica de la quiniela, que es cultura conocida en
 * Latam: los que apostaron a un lado se reparten lo del otro lado, menos una
 * comisión. No hay libro de órdenes, no hay creador de mercado, y no hace falta
 * contraparte — con poca gente ya funciona.
 *
 * La casa **no le gana al jugador**: cobra comisión sobre el pozo. Esa es la
 * diferencia con un casino y sostiene el copy honesto del producto.
 *
 * El motor es agnóstico a la unidad: opera igual con puntos que con dinero.
 * Quién decide la unidad es `FLAGS.market_engine`, no este archivo.
 */

export type Side = "si" | "no";

export interface Pool {
  /** Total apostado al Sí, en la unidad vigente. */
  si: number;
  /** Total apostado al No. */
  no: number;
  /** Comisión de Marea sobre el pozo, en puntos base (200 = 2 %). */
  feeBps: number;
}

/** Semilla mínima del pozo, para que el primero en entrar no vea un pago absurdo. */
export const SEED = 100;

export const MAX_FEE_BPS = 500;

export function totalPool(pool: Pool): number {
  return pool.si + pool.no;
}

/**
 * Probabilidad implícita del Sí: la fracción del pozo que le apostó.
 * Con el pozo vacío la respuesta honesta es 50 %, no una invención.
 */
export function impliedProbability(pool: Pool): number {
  const total = totalPool(pool);
  if (total <= 0) return 0.5;
  return pool.si / total;
}

/**
 * Cuánto paga un lado por cada unidad apostada, **incluyendo** la apuesta que
 * se está por hacer. Se calcula así a propósito: el usuario tiene que ver el
 * pago que va a recibir él, no el que había antes de entrar (R-023).
 */
export function payoutMultiplier(
  pool: Pool,
  side: Side,
  stake: number = 0,
): number {
  const sameSide = (side === "si" ? pool.si : pool.no) + stake;
  const total = totalPool(pool) + stake;
  if (sameSide <= 0) return 0;
  const afterFee = total * (1 - clampFee(pool.feeBps) / 10_000);
  return afterFee / sameSide;
}

function clampFee(feeBps: number): number {
  if (!Number.isFinite(feeBps) || feeBps < 0) return 0;
  return Math.min(MAX_FEE_BPS, feeBps);
}

/** `1.8×` — el formato con el que el usuario entiende cuánto le pagan. */
export function formatMultiplier(multiplier: number): string {
  return `${multiplier.toFixed(2).replace(/0$/, "")}×`;
}

export interface Quote {
  /** Probabilidad implícita del lado elegido, tras entrar. */
  probability: number;
  /** Cuánto paga cada unidad. */
  multiplier: number;
  /** Lo que se cobra si el lado gana, incluyendo lo apostado. */
  toWin: number;
  /** Comisión que se lleva Marea si este lado gana. */
  fee: number;
}

/** Cotización completa de una apuesta antes de confirmarla. */
export function quote(pool: Pool, side: Side, stake: number): Quote {
  const multiplier = payoutMultiplier(pool, side, stake);
  const total = totalPool(pool) + stake;
  const sameSide = (side === "si" ? pool.si : pool.no) + stake;
  return {
    probability: sameSide / total,
    multiplier,
    toWin: stake * multiplier,
    fee: (total * clampFee(pool.feeBps)) / 10_000,
  };
}

export function addStake(pool: Pool, side: Side, stake: number): Pool {
  if (stake <= 0) return pool;
  return side === "si"
    ? { ...pool, si: pool.si + stake }
    : { ...pool, no: pool.no + stake };
}

export interface Bet {
  id: string;
  side: Side;
  stake: number;
}

export interface Settlement {
  /** Lo que cobra cada apuesta, por id. */
  payouts: Record<string, number>;
  /** Lo que se lleva Marea. */
  fee: number;
  /** Lo repartido entre ganadores. */
  distributed: number;
}

/**
 * Liquidación. El pozo perdedor se reparte entre los ganadores en proporción a
 * lo que puso cada uno, menos la comisión.
 *
 * El denominador es **todo** el lado ganador, incluida la semilla que pusimos
 * nosotros para que el mercado arrancara. Repartir sólo entre las apuestas de
 * usuarios pagaría más de lo que dice el multiplicador que se mostró antes de
 * entrar, y el número que se enseña tiene que ser el que se cobra (R-044).
 *
 * Caso borde que importa: si **nadie** —ni la semilla— está del lado ganador,
 * no hay a quién repartir. Devolvemos todo, sin comisión: quedarnos con el pozo
 * de un mercado que nadie ganó sería exactamente lo que hace una casa (R-024).
 */
export function settle(pool: Pool, bets: Bet[], winner: Side): Settlement {
  const winnerStake = winner === "si" ? pool.si : pool.no;
  const total = totalPool(pool);

  if (winnerStake <= 0) {
    // nadie acertó: se devuelve lo apostado, íntegro
    const payouts: Record<string, number> = {};
    for (const bet of bets) payouts[bet.id] = bet.stake;
    return { payouts, fee: 0, distributed: bets.reduce((s, b) => s + b.stake, 0) };
  }

  const fee = (total * clampFee(pool.feeBps)) / 10_000;
  const distributable = total - fee;
  const payouts: Record<string, number> = {};
  for (const bet of bets) {
    payouts[bet.id] =
      bet.side === winner ? (bet.stake / winnerStake) * distributable : 0;
  }
  return { payouts, fee, distributed: distributable };
}

/**
 * En parimutuel no hay resultado marcado a mercado: no puedes salirte a mitad
 * del camino. O tu lado gana y cobras, o pierdes lo que pusiste. Mostrar un
 * "resultado no realizado" sería inventar un número que además saldría siempre
 * en verde, porque el pago nunca baja de lo apostado (R-029).
 *
 * Lo honesto son dos cifras: lo que cobras si aciertas y lo que pierdes si no.
 */
export interface Outlook {
  /** Lo que se cobra si el lado acierta, incluyendo lo apostado. */
  toWin: number;
  /** Lo que se pierde si falla: exactamente lo apostado, nunca más. */
  toLose: number;
  multiplier: number;
}

export function outlook(pool: Pool, bet: Bet): Outlook {
  const multiplier = payoutMultiplier(pool, bet.side);
  return {
    toWin: bet.stake * multiplier,
    toLose: bet.stake,
    multiplier,
  };
}
