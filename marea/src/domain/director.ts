/**
 * La política del director de mercados que no depende de ninguna fuente.
 *
 * ## Opciones sólidas (decisión de RasDG, 2026-10-01; R-079)
 *
 * «Cualquier mercado que tenga más de dos opciones sólidas puede ser variable:
 * más posibilidades, más variación de apuesta. La gente puede que ni sepa de
 * qué se trata como tal, pero si el resultado es verificable y se resuelve
 * solo, entra.»
 *
 * Una opción es **sólida** cuando su probabilidad de nacimiento, sacada de la
 * fuente que siembra el mercado, es al menos `PISO_SOLIDA`. Una tarjeta puede
 * tener más de dos respuestas cuando hay más de dos sólidas; las que no lo son
 * no se ofrecen con nombre propio: van a «Otra», que existe para que el
 * mercado cubra todos los casos, no para rellenar.
 *
 * La tarjeta 1X2 del futbol se queda: el empate es una opción sólida (≈25 %).
 */

/** Probabilidad mínima para ofrecer una respuesta con nombre propio. */
export const PISO_SOLIDA = 0.05;

/** Máximo de respuestas con nombre en una tarjeta (más «Otra»). */
export const MAX_CON_NOMBRE = 4;

/**
 * De candidatos con su probabilidad, cuáles se ofrecen con nombre: las sólidas,
 * de mayor a menor, hasta `MAX_CON_NOMBRE`. Si ninguna es sólida, la favorita
 * sola —el mercado es entonces «la favorita o no»— siempre que alguien la
 * cotice.
 */
export function conNombre<T>(candidatos: readonly { item: T; p: number }[], max = MAX_CON_NOMBRE): T[] {
  const orden = [...candidatos].sort((a, b) => b.p - a.p);
  const solidas = orden.filter((c) => c.p >= PISO_SOLIDA).slice(0, max);
  if (solidas.length > 0) return solidas.map((c) => c.item);
  return orden.filter((c) => c.p >= 0.01).slice(0, 1).map((c) => c.item);
}

/* ------------------------------------------------------------------------- */
/*  Market maker: el prior con que nace un partido                            */
/* ------------------------------------------------------------------------- */

/**
 * Un momio americano (`-270`, `+160`, `EVEN`) como probabilidad implícita, sin
 * quitar la comisión. `undefined` si no es un número que se pueda leer.
 */
export function implicitaDeMomio(momio: string | number | undefined | null): number | undefined {
  if (momio === undefined || momio === null) return undefined;
  const texto = String(momio).trim().toUpperCase();
  const n = texto === "EVEN" || texto === "EV" ? 100 : Number(texto.replace(/^\+/, ""));
  if (!Number.isFinite(n) || Math.abs(n) < 100) return undefined;
  return n < 0 ? -n / (-n + 100) : 100 / (n + 100);
}

export interface Momios {
  local: string | number;
  visitante: string | number;
  empate?: string | number;
  /** Quién los publica, para el criterio: «DraftKings vía ESPN». */
  proveedor: string;
}

/**
 * Probabilidades sin la comisión de la casa de apuestas, o `undefined` si los
 * momios no cuentan una historia coherente.
 *
 * La suma de las implícitas de un libro sano es algo más que 1 (la comisión,
 * 3–8 %). Fuera de [1.00, 1.25] el libro está roto, incompleto o es de otro
 * mercado, y se siembra sin él: un prior malo es peor que ninguno (R-077).
 */
export function probabilidadesDeMomios(
  momios: Momios,
  conEmpate: boolean,
): { local: number; visitante: number; empate?: number } | undefined {
  const local = implicitaDeMomio(momios.local);
  const visitante = implicitaDeMomio(momios.visitante);
  const empate = conEmpate ? implicitaDeMomio(momios.empate) : 0;
  if (local === undefined || visitante === undefined || empate === undefined) return undefined;
  const suma = local + visitante + empate;
  if (suma < 1 || suma > 1.25) return undefined;
  return conEmpate
    ? { local: local / suma, visitante: visitante / suma, empate: empate / suma }
    : { local: local / suma, visitante: visitante / suma };
}

/**
 * Reparte un pozo inicial según un prior, con piso: ningún lado nace con menos
 * de `PISO_SOLIDA` del pozo (pagaría casi infinito y no sería una opción).
 */
export function pozoDesdePrior(prior: Record<string, number>, total: number): Record<string, number> {
  const conPiso = Object.fromEntries(Object.entries(prior).map(([k, p]) => [k, Math.max(PISO_SOLIDA, p)]));
  const suma = Object.values(conPiso).reduce((s, p) => s + p, 0);
  return Object.fromEntries(
    Object.entries(conPiso).map(([k, p]) => [k, Math.max(1, Math.round((total * p) / suma))]),
  );
}
