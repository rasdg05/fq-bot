/**
 * La época y su ancla. Funciones puras: sin estado, sin red, sin reloj.
 *
 * ## El agujero que este archivo tapa
 *
 * Una raíz de Merkle prueba que **tu** hecho está en el libro. **No prueba que
 * el libro esté completo.** Si un hecho se omite entero, la raíz sigue
 * verificando para todos los demás y nadie lo nota: no hay nada contra lo que
 * comparar. Es el problema clásico de disponibilidad de datos, y `merkle.ts`
 * —por bien construido que esté— no lo puede resolver solo.
 *
 * Se cierra con dos cosas baratas, y las dos van **en el ancla** (L15):
 *
 * 1. **Secuencia por usuario.** Cada hoja lleva `(usuario, n)` consecutivo desde
 *    1. Un hueco —falta el `n=7`— lo detecta **el propio usuario**, mirando sólo
 *    sus hojas y sin ver el resto del libro. Es la parte que no depende de que
 *    nosotros contestemos nada.
 * 2. **Conteo anclado.** El ancla publica cuántas hojas tenía la época. Sin él
 *    se puede encoger el libro en silencio y republicar una raíz coherente; con
 *    él, cualquiera nota que el número no cuadra.
 *
 * Falta una tercera, que no es código: **publicar las hojas** de la época (o
 * servirlas bajo demanda). Sin eso, «auditable» sigue dependiendo de que
 * nosotros contestemos. Queda anotado aquí porque es la diferencia entre una
 * promesa verificable y una que hay que creerse.
 */

import { raiz, type Hoja } from "./merkle";

/**
 * Lo que se publica de una época. Es lo único que hace falta creerse, y por eso
 * es lo que va a la cadena.
 */
export interface Ancla {
  /** Número de época, consecutivo desde 1. */
  epoca: number;
  /** Raíz del árbol de las hojas de esta época. */
  raiz: string;
  /** Cuántas hojas. Sin este número, el libro se puede encoger en silencio. */
  hojas: number;
  /** El ancla de la época anterior, o `null` en la primera. Encadena la historia. */
  anterior: string | null;
}

/**
 * Cierra una época y produce su ancla.
 *
 * El orden de las hojas **es** parte de lo anclado: cambiarlo cambia la raíz. Se
 * anclan en el orden en que se reciben y no se ordenan aquí — reordenar en el
 * cierre haría que la raíz dejara de corresponder al libro tal como se escribió.
 */
export function cerrarEpoca(input: {
  epoca: number;
  hojas: readonly Hoja[];
  anterior?: Ancla | null;
}): Ancla {
  const { epoca, hojas } = input;
  if (!Number.isInteger(epoca) || epoca < 1) {
    throw new Error(`época inválida: ${epoca}`);
  }
  const anterior = input.anterior ?? null;
  if (anterior && anterior.epoca !== epoca - 1) {
    // una época que no sigue a la anterior deja un hueco en la historia, y un
    // hueco en la historia es exactamente lo que el encadenado existe para evitar
    throw new Error(`la época ${epoca} no sigue a la ${anterior.epoca}`);
  }
  return {
    epoca,
    raiz: raiz(hojas),
    hojas: hojas.length,
    anterior: anterior ? anterior.raiz : null,
  };
}

/** Un hueco en la secuencia de un usuario: la prueba de que falta un hecho. */
export interface Hueco {
  usuario: string;
  /** El número que falta. */
  falta: number;
}

/**
 * Los huecos de secuencia del libro. Vacío = ningún usuario echa nada en falta.
 *
 * Esto es lo que un usuario puede correr **sobre sus propias hojas**, sin ver
 * las de nadie: si su lista salta del 6 al 8, falta el 7 y no hace falta
 * confiar en nosotros para saberlo.
 *
 * Un duplicado también es un hueco disfrazado —dos hojas con el mismo `n` y una
 * ausente— y se reporta igual: la secuencia tiene que ser 1..n sin repetir.
 */
export function huecosDeSecuencia(hojas: readonly Hoja[]): Hueco[] {
  const porUsuario = new Map<string, number[]>();
  for (const hoja of hojas) {
    const lista = porUsuario.get(hoja.usuario) ?? [];
    lista.push(hoja.seq);
    porUsuario.set(hoja.usuario, lista);
  }

  const huecos: Hueco[] = [];
  for (const [usuario, seqs] of porUsuario) {
    const vistos = new Set(seqs);
    const maximo = Math.max(...seqs);
    for (let n = 1; n <= maximo; n += 1) {
      if (!vistos.has(n)) huecos.push({ usuario, falta: n });
    }
    // un repetido significa que hay tantas hojas como dice pero una es falsa
    if (vistos.size !== seqs.length) {
      const repetidos = seqs.filter((n, i) => seqs.indexOf(n) !== i);
      for (const n of new Set(repetidos)) huecos.push({ usuario, falta: n });
    }
  }
  return huecos.sort((a, b) =>
    a.usuario === b.usuario ? a.falta - b.falta : a.usuario < b.usuario ? -1 : 1,
  );
}

/**
 * Comprueba un ancla contra el libro que dice representar. Vacío = sano.
 *
 * Las tres comprobaciones son distintas y ninguna implica a las otras:
 * - la **raíz** dice que las hojas que hay son las que se anclaron;
 * - el **conteo** dice que no falta ninguna al final;
 * - la **secuencia** dice que no falta ninguna en medio.
 *
 * Un libro al que se le quitó una hoja falla la primera **y** la segunda; un
 * libro al que se le quitó una hoja y se reancló pasa la primera y falla la
 * tercera. Ésa es la razón de que estén las tres.
 */
export function verificarAncla(ancla: Ancla, hojas: readonly Hoja[]): string[] {
  const problemas: string[] = [];
  if (hojas.length !== ancla.hojas) {
    problemas.push(`el ancla dice ${ancla.hojas} hojas y el libro trae ${hojas.length}`);
  }
  if (hojas.length > 0) {
    const calculada = raiz(hojas);
    if (calculada !== ancla.raiz) {
      problemas.push(`la raíz no coincide: ancla ${ancla.raiz.slice(0, 16)}…, libro ${calculada.slice(0, 16)}…`);
    }
  }
  for (const hueco of huecosDeSecuencia(hojas)) {
    problemas.push(`a ${hueco.usuario} le falta el hecho n.º ${hueco.falta}`);
  }
  return problemas;
}
