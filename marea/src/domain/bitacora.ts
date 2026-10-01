import { sha256Hex } from "./sha256";

/**
 * La bitácora del director: cada decisión autónoma, escrita una vez y nunca
 * reescrita (MEMORY/FILOSOFIA.md, principio 2: *una decisión sin rastro no
 * ocurrió*).
 *
 * Es *append-only* y está **encadenada por hash**: cada entrada guarda el hash
 * de la anterior y el suyo propio sobre su contenido. Editar o borrar una entrada
 * del medio rompe la cadena desde ahí, y `verificarCadena` dice exactamente dónde.
 * No es criptografía de adorno: es lo que permite decir «esto es lo que el
 * agente decidió» sin pedir que nos crean.
 *
 * Se escriben **cambios**, no observaciones: un hallazgo que se abre y se cierra
 * son dos entradas, aunque el revisor lo haya visto en cien ciclos. Así la
 * bitácora crece con lo que pasa y no con el reloj.
 */

/** Quién tomó la decisión. Un modelo se nombra con su versión exacta. */
export type AutorDecision = "reglas" | "persona" | `claude:${string}`;

export type TipoDecision =
  /** El director publicó un mercado. */
  | "publicar"
  /** El director decidió no publicar un candidato, con su motivo. */
  | "omitir"
  /** El juez vetó un texto antes de publicarse. */
  | "vetar"
  /** El revisor abrió o cerró un hallazgo. */
  | "hallazgo_abre"
  | "hallazgo_cierra"
  /** El revisor retuvo una resolución antes de pagarla. */
  | "retener"
  /** Una persona liberó lo que el agente retuvo. */
  | "liberar";

export interface DecisionNueva {
  tipo: TipoDecision;
  /** Sobre qué: un id de mercado, de fuente, o «catalogo». */
  sujeto: string;
  /** Por qué, en una frase que una persona entiende sin abrir el código. */
  motivo: string;
  /** La regla que la sostiene (`R-076`, `L9`…), si la hay. */
  regla?: string;
  autor: AutorDecision;
  /** El dato que se miró. */
  evidencia?: string;
  /** ¿Se puede deshacer sin perjudicar a nadie? Lo irreversible no lo hace el agente solo. */
  reversible: boolean;
}

export interface EntradaBitacora extends DecisionNueva {
  n: number;
  at: string;
  prev: string;
  hash: string;
}

/** El hash del génesis: la primera entrada encadena contra esto. */
export const GENESIS = "0".repeat(64);

const codificar = (texto: string) => new TextEncoder().encode(texto);

/**
 * El contenido que se firma, en un orden fijo. `JSON.stringify` de un objeto
 * depende del orden de inserción de sus claves; aquí se arma a mano para que el
 * mismo dato dé siempre el mismo hash, venga de donde venga.
 */
function contenido(e: Omit<EntradaBitacora, "hash">): string {
  return JSON.stringify([
    e.n,
    e.at,
    e.prev,
    e.tipo,
    e.sujeto,
    e.motivo,
    e.regla ?? null,
    e.autor,
    e.evidencia ?? null,
    e.reversible,
  ]);
}

export function hashEntrada(e: Omit<EntradaBitacora, "hash">): string {
  return sha256Hex(codificar(contenido(e)));
}

/** La entrada siguiente de la cadena. Pura: no modifica `cadena`. */
export function anexar(
  cadena: readonly EntradaBitacora[],
  decision: DecisionNueva,
  ahora: number,
): EntradaBitacora {
  const ultima = cadena.at(-1);
  const base = {
    ...decision,
    n: (ultima?.n ?? 0) + 1,
    at: new Date(ahora).toISOString(),
    prev: ultima?.hash ?? GENESIS,
  };
  return { ...base, hash: hashEntrada(base) };
}

export type Verificacion = { ok: true; entradas: number } | { ok: false; en: number; motivo: string };

/** Recorre la cadena entera. Una sola entrada tocada la rompe desde ahí. */
export function verificarCadena(cadena: readonly EntradaBitacora[]): Verificacion {
  let prev = GENESIS;
  for (let i = 0; i < cadena.length; i++) {
    const e = cadena[i];
    if (e.n !== i + 1) return { ok: false, en: e.n, motivo: `numeración rota: se esperaba ${i + 1}` };
    if (e.prev !== prev) return { ok: false, en: e.n, motivo: "no encadena con la anterior" };
    const { hash, ...resto } = e;
    if (hashEntrada(resto) !== hash) return { ok: false, en: e.n, motivo: "el contenido no coincide con su hash" };
    prev = hash;
  }
  return { ok: true, entradas: cadena.length };
}
