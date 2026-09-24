/**
 * Presupuesto de subsidio y el freno de creación (L9, R-067, R-068).
 *
 * R-067 no dice «la casa puede subsidiar»: dice que toda liquidez que la casa
 * aporta es subsidio declarado **con tope**. La palabra «tope» es la mitad de la
 * regla, y es la mitad cara — un subsidio cuesta S en cada mercado, gane quien
 * gane, y sin nada que lo apague el compromiso crece con cada `roll`.
 *
 * Este archivo es esa mitad. Funciones puras, sin relojes y sin red: se les
 * dice qué hay vivo y qué topes rigen, y contestan si se puede crear otro
 * mercado. La decisión se toma **antes** de escribir el catálogo, no en un
 * tablero que alguien mira el lunes: un tope que no apaga nada es un
 * comentario.
 *
 * ## La distinción que hace que los números signifiquen algo
 *
 * - **Subsidio** — la casa lo pone y **no lo recupera**. Es coste. Es lo que el
 *   tope de R-067 acota.
 * - **Semilla en modo apuesta** — la casa la pone y puede volver. Es posición,
 *   no coste. No consume presupuesto de subsidio; sí cuenta como exposición.
 *
 * Sumarlas en un solo número haría que un catálogo entero de semillas
 * recuperables pareciera gasto, o —peor— que un subsidio real se escondiera
 * dentro de una exposición que nadie acotó.
 */

import type { ModoSemilla } from "./contabilidad";

/** Un mercado vivo, visto desde el dinero que la casa tiene dentro. */
export interface MercadoVivo {
  id: string;
  /** Lo que la casa puso al abrirlo. */
  semilla: number;
  /** Si vuelve (`apuesta`) o si es coste (`subsidio`). */
  modo: ModoSemilla;
  /**
   * ¿La semilla está **declarada**, o es un pozo viejo donde la semilla y las
   * apuestas ya están sumadas y no se pueden separar?
   *
   * Importa porque un mercado sin semilla declarada no se puede sumar: contarlo
   * como cero es una subestimación del compromiso, y una subestimación hace que
   * el freno se dispare tarde. Cuando hay un tope de exposición configurado, la
   * respuesta honesta a «no lo sé» es negarse, no redondear a cero.
   */
  declarada: boolean;
}

/**
 * Los topes. `undefined` significa **sin tope configurado**, y no se inventa un
 * número: un límite inventado es peor que no tenerlo, porque parece una
 * decisión. Lo que sí se hace es decirlo en el veredicto, para que «no hay
 * tope» nunca pase por «pasó el tope».
 */
export interface Topes {
  /** Subsidio máximo que puede llevar un solo mercado. */
  porMercado?: number;
  /** Suma de subsidios vivos a la vez. */
  abierto?: number;
  /** Dinero total de la casa dentro de mercados, subsidio y semilla juntos. */
  exposicion?: number;
}

/**
 * Los topes por defecto: **cero subsidio autorizado**.
 *
 * No es un placeholder. Hoy ningún mercado nace en modo subsidio (P-002), así
 * que un tope de cero no impide nada de lo que ya se hace — y en el momento en
 * que alguien encienda el subsidio sin haber puesto un presupuesto, la creación
 * se detiene. El freno nace armado, que es el único orden que respeta R-067:
 * primero el tope, después el gasto.
 *
 * La exposición se deja **sin tope** a propósito: acotar las semillas
 * recuperables que ya existen es una decisión de producto con un número que
 * sólo puede poner RasDG, y elegirlo aquí sería exactamente «bajar el umbral
 * para que el tablero salga verde», al revés.
 */
export const TOPES_POR_DEFECTO: Topes = { porMercado: 0, abierto: 0 };

/** Lo que un mercado cuesta de verdad: sólo el subsidio es coste. */
export function subsidioDe(mercado: MercadoVivo): number {
  return mercado.modo === "subsidio" ? mercado.semilla : 0;
}

/** Subsidio comprometido en todos los mercados vivos. */
export function subsidioVivo(mercados: readonly MercadoVivo[]): number {
  let total = 0;
  for (const mercado of mercados) total += subsidioDe(mercado);
  return total;
}

/**
 * Todo el dinero de la casa dentro de mercados, vuelva o no vuelva.
 *
 * Es una cota **inferior** cuando hay mercados sin semilla declarada, y por eso
 * `puedeCrear` no la usa a solas: la acompaña siempre del recuento de lo que no
 * se pudo sumar.
 */
export function exposicionViva(mercados: readonly MercadoVivo[]): number {
  let total = 0;
  for (const mercado of mercados) total += mercado.semilla;
  return total;
}

/** Los mercados cuya semilla no se puede saber. Vacío = la suma es exacta. */
export function sinSemillaDeclarada(mercados: readonly MercadoVivo[]): string[] {
  return mercados.filter((m) => !m.declarada).map((m) => m.id);
}

export interface Veredicto {
  permitido: boolean;
  /** Por qué no, en una frase que se pueda imprimir. Vacío si se permite. */
  motivo: string;
  /** Lo que se midió, para que el «no» sea auditable y no una opinión. */
  medido: {
    subsidioVivo: number;
    subsidioTrasCrear: number;
    exposicionViva: number;
    sinDeclarar: number;
  };
}

/**
 * ¿Se puede crear este mercado?
 *
 * Se responde antes de escribirlo, y el «no» viene con el número que lo causó.
 * Un freno que se niega sin decir por qué se acaba desactivando a mano, que es
 * la forma lenta de no tener freno.
 */
export function puedeCrear(input: {
  vivos: readonly MercadoVivo[];
  candidato: MercadoVivo;
  topes?: Topes;
}): Veredicto {
  const { vivos, candidato } = input;
  const topes = input.topes ?? TOPES_POR_DEFECTO;

  const vivoAhora = subsidioVivo(vivos);
  const delCandidato = subsidioDe(candidato);
  const trasCrear = vivoAhora + delCandidato;
  const expuesto = exposicionViva(vivos);
  const opacos = sinSemillaDeclarada(vivos);

  const medido = {
    subsidioVivo: vivoAhora,
    subsidioTrasCrear: trasCrear,
    exposicionViva: expuesto,
    sinDeclarar: opacos.length,
  };
  const no = (motivo: string): Veredicto => ({ permitido: false, motivo, medido });

  if (topes.porMercado !== undefined && delCandidato > topes.porMercado) {
    return no(
      `el mercado ${candidato.id} lleva ${delCandidato} de subsidio y el tope por mercado es ${topes.porMercado}`,
    );
  }
  if (topes.abierto !== undefined && trasCrear > topes.abierto) {
    return no(
      `crearlo dejaría ${trasCrear} de subsidio vivo y el tope abierto es ${topes.abierto} (hay ${vivoAhora} comprometidos)`,
    );
  }

  /**
   * El tope de exposición sólo se puede hacer cumplir si se puede sumar. Con
   * mercados de semilla no declarada la suma es una cota inferior, y una cota
   * inferior contra un tope hace que el freno se dispare tarde — o sea, que no
   * frene. Si alguien puso un tope, la respuesta honesta a «no lo sé» es
   * negarse; si no lo puso, no hay nada que hacer cumplir y no se estorba.
   */
  if (topes.exposicion !== undefined) {
    if (opacos.length > 0) {
      return no(
        `hay ${opacos.length} mercados vivos sin semilla declarada (${opacos.slice(0, 3).join(", ")}${opacos.length > 3 ? ", …" : ""}) y no se pueden sumar contra el tope de exposición`,
      );
    }
    const trasCrearExpuesto = expuesto + candidato.semilla;
    if (trasCrearExpuesto > topes.exposicion) {
      return no(
        `crearlo dejaría ${trasCrearExpuesto} de exposición y el tope es ${topes.exposicion}`,
      );
    }
  }

  return { permitido: true, motivo: "", medido };
}

/**
 * Filtra una tanda de candidatos contra el presupuesto, en orden.
 *
 * Va uno a uno y **cuenta los aceptados como vivos** para el siguiente: aprobar
 * la tanda entera contra el estado inicial dejaría pasar N mercados que juntos
 * cruzan el tope aunque ninguno lo cruce solo. Es el error clásico de un límite
 * por lotes, y aquí se traduce en gastar de más y enterarse después.
 */
export function filtrarPorPresupuesto(input: {
  vivos: readonly MercadoVivo[];
  candidatos: readonly MercadoVivo[];
  topes?: Topes;
}): { aceptados: MercadoVivo[]; rechazados: { mercado: MercadoVivo; motivo: string }[] } {
  const aceptados: MercadoVivo[] = [];
  const rechazados: { mercado: MercadoVivo; motivo: string }[] = [];
  const vivos = [...input.vivos];

  for (const candidato of input.candidatos) {
    const veredicto = puedeCrear({ vivos, candidato, topes: input.topes });
    if (veredicto.permitido) {
      aceptados.push(candidato);
      vivos.push(candidato);
    } else {
      rechazados.push({ mercado: candidato, motivo: veredicto.motivo });
    }
  }
  return { aceptados, rechazados };
}

/* -------------------------------------------------------------------------
 * El puente con lo que hay escrito: de una semilla de catálogo a un mercado
 * vivo, y de las variables de entorno a los topes.
 * ---------------------------------------------------------------------- */

/** Lo mínimo de una semilla de catálogo que hace falta para presupuestar. */
export interface SemillaPresupuestable {
  id: string;
  pool: { seed?: Record<string, number>; seedMode?: ModoSemilla };
}

/**
 * Lee un mercado del catálogo en términos de dinero de la casa.
 *
 * Un pozo sin `seed` **no** se cuenta como cero en silencio: se marca como no
 * declarado. Es el caso de los mercados que un `roll` anterior publicó con el
 * formato viejo, donde la semilla y las apuestas ya están sumadas en el mismo
 * número y no hay forma de separarlas. Decir «cero» ahí sería inventar.
 */
export function mercadoVivoDe(seed: SemillaPresupuestable): MercadoVivo {
  const declarada = seed.pool.seed !== undefined;
  const semilla = declarada
    ? Object.values(seed.pool.seed as Record<string, number>).reduce((s, v) => s + v, 0)
    : 0;
  return { id: seed.id, semilla, modo: seed.pool.seedMode ?? "apuesta", declarada };
}

/**
 * Los topes, leídos del entorno. Lo que no está configurado **no se inventa**:
 * el subsidio cae a cero autorizado y la exposición se queda sin tope, que es
 * lo que dice `TOPES_POR_DEFECTO` y por qué.
 *
 * Un valor que no es un número finito y no negativo se trata como ausente y se
 * avisa: un tope mal escrito que se lee como `NaN` haría pasar cualquier
 * comparación, y un freno que siempre dice que sí es el mismo que no existe.
 */
export function topesDelEntorno(
  env: Record<string, string | undefined>,
  avisar: (mensaje: string) => void = () => {},
): Topes {
  const leer = (clave: string, porDefecto?: number): number | undefined => {
    const crudo = env[clave];
    if (crudo === undefined || crudo.trim() === "") return porDefecto;
    const valor = Number(crudo);
    if (!Number.isFinite(valor) || valor < 0) {
      avisar(`${clave}="${crudo}" no es un número válido; se ignora y rige ${porDefecto ?? "sin tope"}`);
      return porDefecto;
    }
    return valor;
  };
  return {
    porMercado: leer("MAREA_SUBSIDIO_MAX_MERCADO", TOPES_POR_DEFECTO.porMercado),
    abierto: leer("MAREA_SUBSIDIO_MAX_ABIERTO", TOPES_POR_DEFECTO.abierto),
    exposicion: leer("MAREA_EXPOSICION_MAX", TOPES_POR_DEFECTO.exposicion),
  };
}
