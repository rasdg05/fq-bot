/**
 * Motor parimutuel. Es la mecánica de la quiniela, que es cultura conocida en
 * Latam: los que apostaron a un resultado se reparten lo de los demás, menos
 * una comisión. No hay libro de órdenes, no hay creador de mercado, y no hace
 * falta contraparte — con poca gente ya funciona.
 *
 * La casa **no le gana al jugador**: cobra comisión sobre el pozo. Esa es la
 * diferencia con un casino y sostiene el copy honesto del producto.
 *
 * El motor es agnóstico a la unidad: opera igual con puntos que con dinero.
 * Quién decide la unidad es `FLAGS.market_engine`, no este archivo.
 *
 * También es agnóstico a **cuántos** resultados tiene la pregunta. El pozo es
 * un mapa de `id → apostado`, y el binario es el caso particular con los ids
 * `si` y `no`. No hay un segundo motor para los mercados de N opciones a
 * propósito: dos implementaciones de la misma matemática de dinero serían dos
 * fuentes de verdad, y el día que se separen una de las dos paga distinto de lo
 * que prometió (R-044).
 */

/** Identificador de un resultado dentro de un mercado. */
export type OutcomeId = string;

/**
 * Se conserva el nombre `Side` porque es como lo llama el resto del código y
 * como viaja en los datos ya persistidos. Hoy es un `outcomeId` cualquiera, no
 * un lado de dos.
 */
export type Side = OutcomeId;

export const SI: OutcomeId = "si";
export const NO: OutcomeId = "no";

/** Un resultado, tal como se le presenta al usuario. */
export interface Outcome {
  id: OutcomeId;
  label: string;
}

/** Los dos resultados del caso binario, con el texto que ve la gente. */
export const BINARY_OUTCOMES: readonly Outcome[] = [
  { id: SI, label: "Sí" },
  { id: NO, label: "No" },
];

/**
 * Qué es la semilla que la casa puso para que el mercado no naciera vacío.
 *
 * - `"apuesta"` — es una posición pequeña: si cae del lado ganador, su parte del
 *   reparto se queda en el pozo y la cobra la casa. Es lo que hubo siempre.
 * - `"subsidio"` — es un premio: la casa **nunca** cobra de ella, y su parte se
 *   reparte entre los usuarios que acertaron. Cuesta S gane quien gane (R-067).
 *
 * Ausente significa `"apuesta"`, y ese default no es pereza: un pozo escrito en
 * disco antes de que este campo existiera tiene que seguir pagando exactamente
 * lo mismo que prometió el día que alguien apostó en él.
 */
export type SeedMode = "apuesta" | "subsidio";

export interface Pool {
  /** Lo apostado a cada resultado, por id, en la unidad vigente. */
  outcomes: Record<OutcomeId, number>;
  /** Comisión de Marea sobre el pozo, en puntos base (200 = 2 %). */
  feeBps: number;
  /**
   * Lo que puso la casa en cada resultado al abrir el mercado. Va aparte de
   * `outcomes` porque `outcomes` crece con las apuestas y la semilla no: sin
   * este registro, media hora después de abrir ya no se puede saber cuánto del
   * pozo es de la casa. Ausente = no declarada = cero.
   */
  seed?: Record<OutcomeId, number>;
  /**
   * Cómo se comporta la semilla al liquidar. **No se migra sobre un mercado
   * abierto**: cambiarlo movería el multiplicador que ya se le mostró a quien
   * apostó, y el número que se enseña es el que se cobra (R-023, R-044). Cada
   * mercado termina con las reglas con las que nació.
   */
  seedMode?: SeedMode;
}

/**
 * Cuántos apostadores distintos necesita un mercado para que su resultado
 * signifique algo. Con uno solo, el pozo perdedor es la semilla de la casa y el
 * "mercado" es una persona hablando sola; con dos ya hay desacuerdo, que es de
 * lo que se trata. Debajo de esto se anula y se devuelve todo (R-059).
 */
export const MIN_APOSTADORES = 2;

/** Semilla mínima del pozo, para que el primero en entrar no vea un pago absurdo. */
export const SEED = 100;

export const MAX_FEE_BPS = 500;

/** Atajo para el caso binario, que sigue siendo la mayoría del catálogo. */
export function binaryPool(si: number, no: number, feeBps: number): Pool {
  return { outcomes: { [SI]: si, [NO]: no }, feeBps };
}

/** ¿Es una pregunta de sí/no? Decide cómo se pinta, nunca cómo se calcula. */
export function isBinary(pool: Pool): boolean {
  const ids = Object.keys(pool.outcomes);
  return ids.length === 2 && ids.includes(SI) && ids.includes(NO);
}

/**
 * Forma vieja del pozo, tal como quedó escrita en el volumen de producción
 * antes de que existieran los mercados de N resultados.
 */
interface PoolBinarioViejo {
  si: number;
  no: number;
  feeBps: number;
}

function esFormatoViejo(raw: unknown): raw is PoolBinarioViejo {
  return (
    typeof raw === "object" &&
    raw !== null &&
    !("outcomes" in raw) &&
    typeof (raw as PoolBinarioViejo).si === "number" &&
    typeof (raw as PoolBinarioViejo).no === "number"
  );
}

/**
 * Lee un pozo venga en el formato que venga. El volumen de producción tiene
 * pozos escritos como `{ si, no, feeBps }` y no se puede perder ninguno: un
 * pozo que no se lee es dinero de gente que desaparece.
 *
 * Es idempotente — un pozo ya migrado sale igual que entró — para que releer lo
 * que acabamos de escribir no lo vuelva a tocar.
 */
export function normalizePool(raw: unknown): Pool {
  if (esFormatoViejo(raw)) {
    return binaryPool(raw.si, raw.no, raw.feeBps);
  }
  const pool = raw as Pool;
  return {
    outcomes: { ...pool.outcomes },
    feeBps: pool.feeBps,
    // se copian sólo si existen: un pozo viejo no gana una semilla por pasar
    // por aquí, y uno con subsidio no la pierde por releerse (I6)
    ...(pool.seed ? { seed: { ...pool.seed } } : {}),
    ...(pool.seedMode ? { seedMode: pool.seedMode } : {}),
  };
}

/** Lo apostado a un resultado. Un id que no existe vale cero, no `undefined`. */
export function outcomeStake(pool: Pool, id: OutcomeId): number {
  return pool.outcomes[id] ?? 0;
}

/** Lo que puso la casa en ese resultado. Sin semilla declarada, cero. */
export function seedStake(pool: Pool, id: OutcomeId): number {
  return pool.seed?.[id] ?? 0;
}

/** La semilla entera del mercado, sumando todos los resultados. Es el coste. */
export function totalSeed(pool: Pool): number {
  if (!pool.seed) return 0;
  let total = 0;
  for (const valor of Object.values(pool.seed)) total += valor;
  return total;
}

/**
 * La parte de un resultado que **no cobra** cuando gana: la semilla, y sólo si
 * es subsidio. En modo `"apuesta"` es cero y toda la aritmética de abajo se
 * reduce a la de siempre, término por término.
 */
export function subsidyStake(pool: Pool, id: OutcomeId): number {
  return pool.seedMode === "subsidio" ? seedStake(pool, id) : 0;
}

/**
 * El denominador del reparto: lo apostado a un resultado descontando lo que no
 * va a cobrar. Es el **único** lugar donde se decide qué entra al reparto, y
 * por eso `payoutMultiplier` y `settle` lo llaman los dos. Si cada uno hiciera
 * su propia resta, el día que se separen la app mostraría un número y pagaría
 * otro — que es exactamente lo que R-044 prohíbe.
 *
 * Nunca sale negativo: una semilla mayor que el pozo sería un pozo corrupto, y
 * la respuesta honesta a eso es cero (nadie cobra), no un multiplicador con
 * signo.
 */
export function bettorStake(pool: Pool, id: OutcomeId): number {
  return Math.max(0, outcomeStake(pool, id) - subsidyStake(pool, id));
}

/**
 * Estampa la semilla de un mercado que nace: todo lo que hay en el pozo ahora
 * mismo es de la casa, porque todavía no ha apostado nadie.
 *
 * Se llama **al crear**, nunca sobre un mercado vivo: hacerlo después contaría
 * como semilla apuestas de usuarios, y esas sí cobran.
 */
export function declareSeed(pool: Pool, seedMode: SeedMode = "apuesta"): Pool {
  return { ...pool, seed: { ...pool.outcomes }, seedMode };
}

export function outcomeIds(pool: Pool): OutcomeId[] {
  return Object.keys(pool.outcomes);
}

export function totalPool(pool: Pool): number {
  let total = 0;
  for (const valor of Object.values(pool.outcomes)) total += valor;
  return total;
}

/**
 * Probabilidad implícita de un resultado: la fracción del pozo que le apostó.
 * Con el pozo vacío la respuesta honesta es el reparto uniforme, no una
 * invención. Por omisión responde por el `si`, que es lo que espera el binario.
 */
export function impliedProbability(pool: Pool, id: OutcomeId = SI): number {
  const total = totalPool(pool);
  if (total <= 0) {
    const n = outcomeIds(pool).length;
    return n > 0 ? 1 / n : 0.5;
  }
  return outcomeStake(pool, id) / total;
}

/**
 * Todas las probabilidades, por id. Suman 1 por construcción: son fracciones
 * del mismo total. Es lo que pinta la lista de un mercado de N opciones.
 */
export function probabilities(pool: Pool): Record<OutcomeId, number> {
  const total = totalPool(pool);
  const ids = outcomeIds(pool);
  const salida: Record<OutcomeId, number> = {};
  if (total <= 0) {
    for (const id of ids) salida[id] = ids.length > 0 ? 1 / ids.length : 0;
    return salida;
  }
  for (const id of ids) salida[id] = pool.outcomes[id] / total;
  return salida;
}

/**
 * Cuánto paga un resultado por cada unidad apostada, **incluyendo** la apuesta
 * que se está por hacer. Se calcula así a propósito: el usuario tiene que ver
 * el pago que va a recibir él, no el que había antes de entrar (R-023).
 *
 * El denominador es `bettorStake`, no el pozo del lado: con subsidio, la parte
 * de la semilla se reparte entre quienes acertaron, así que el multiplicador
 * **sube**. Mover `settle()` sin mover esto dejaría a la app mostrando menos de
 * lo que paga — mentir en la dirección generosa sigue siendo mentir (R-067).
 */
export function payoutMultiplier(
  pool: Pool,
  id: OutcomeId,
  stake: number = 0,
): number {
  const sameSide = bettorStake(pool, id) + stake;
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
  /** Probabilidad implícita del resultado elegido, tras entrar. */
  probability: number;
  /** Cuánto paga cada unidad. */
  multiplier: number;
  /** Lo que se cobra si el resultado gana, incluyendo lo apostado. */
  toWin: number;
  /** Comisión que se lleva Marea si este resultado gana. */
  fee: number;
}

/**
 * Cotización completa de una apuesta antes de confirmarla.
 *
 * La probabilidad se calcula sobre el pozo **entero**, semilla incluida: el
 * subsidio es colateral de verdad y mueve el precio como cualquier otro. Lo que
 * el subsidio cambia es quién cobra, no cuánto se apostó — por eso sale del
 * denominador del multiplicador y no del de la probabilidad. Con subsidio,
 * `multiplier > 1 / probability`, y esa diferencia **es** el premio.
 */
export function quote(pool: Pool, id: OutcomeId, stake: number): Quote {
  const multiplier = payoutMultiplier(pool, id, stake);
  const total = totalPool(pool) + stake;
  const sameSide = outcomeStake(pool, id) + stake;
  return {
    probability: total > 0 ? sameSide / total : 0,
    multiplier,
    toWin: stake * multiplier,
    fee: (total * clampFee(pool.feeBps)) / 10_000,
  };
}

export function addStake(pool: Pool, id: OutcomeId, stake: number): Pool {
  if (stake <= 0) return pool;
  return {
    ...pool,
    outcomes: { ...pool.outcomes, [id]: outcomeStake(pool, id) + stake },
  };
}

export interface Bet {
  id: string;
  side: OutcomeId;
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
 * Liquidación. Los pozos perdedores se reparten entre los ganadores en
 * proporción a lo que puso cada uno, menos la comisión. Con dos resultados o
 * con siete la cuenta es la misma: cambia cuántos pozos pierden, no cómo se
 * reparte el que gana.
 *
 * El denominador es `bettorStake(ganador)`: el lado ganador menos lo que no
 * cobra. En un mercado nacido en modo `"apuesta"` eso es el lado entero, semilla
 * incluida, y la cuenta es idéntica a la de siempre. En modo `"subsidio"` la
 * semilla sale del denominador y su parte del reparto se va a los usuarios que
 * acertaron: la casa nunca cobra de lo que puso (R-067).
 *
 * El mismo `bettorStake` que usa `payoutMultiplier`, a propósito. Ésa es la
 * forma ejecutable de R-044: lo que reparte la liquidación es exactamente lo
 * que prometió la cotización, y no porque alguien se acuerde de mantener las
 * dos fórmulas iguales, sino porque son la misma función.
 *
 * Caso borde que importa: si **nadie que cobre** está del lado ganador —ni un
 * usuario, y la semilla no cuenta si es subsidio— no hay a quién repartir.
 * Devolvemos todo, sin comisión: quedarnos con el pozo de un mercado que nadie
 * ganó sería exactamente lo que hace una casa (R-024). El subsidio, que no lo
 * reclamó nadie, se queda en el pozo y vuelve a tesorería.
 */
export function settle(pool: Pool, bets: Bet[], winner: OutcomeId): Settlement {
  const winnerStake = bettorStake(pool, winner);
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
 * del camino. O tu resultado gana y cobras, o pierdes lo que pusiste. Mostrar
 * un "resultado no realizado" sería inventar un número que además saldría
 * siempre en verde, porque el pago nunca baja de lo apostado (R-029).
 *
 * Lo honesto son dos cifras: lo que cobras si aciertas y lo que pierdes si no.
 */
export interface Outlook {
  /** Lo que se cobra si el resultado acierta, incluyendo lo apostado. */
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

/**
 * Los resultados ordenados por probabilidad, de mayor a menor, con su pago.
 * Es lo que necesita la lista de un mercado de N opciones: quien apuesta ve
 * contra qué apuesta, y en qué orden (R-063).
 */
export interface RankedOutcome extends Outcome {
  probability: number;
  multiplier: number;
  staked: number;
}

export function rankedOutcomes(
  pool: Pool,
  outcomes: readonly Outcome[],
  stake = 0,
): RankedOutcome[] {
  const probs = probabilities(pool);
  return outcomes
    .map((outcome) => ({
      ...outcome,
      probability: probs[outcome.id] ?? 0,
      multiplier: payoutMultiplier(pool, outcome.id, stake),
      staked: outcomeStake(pool, outcome.id),
    }))
    .sort((a, b) => b.probability - a.probability);
}
