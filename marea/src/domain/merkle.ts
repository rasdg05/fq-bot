/**
 * Árbol de Merkle de la época. Funciones puras: sin estado, sin red, sin reloj.
 *
 * =====================================================================
 * API PARA LA PANTALLA DEL VERIFICADOR
 * =====================================================================
 *
 * Quien comprueba su propia prueba necesita exactamente cuatro cosas:
 *
 * ```ts
 * const hojas: Hoja[] = [...];                  // el libro de la época
 * const ancla = anclaDe(hojas);                 // { raiz, hojas } — lo publicado
 * const prueba = pruebaDeInclusion(hojas, i);   // el camino de MI hoja
 * verificar(hojas[i], prueba, ancla.raiz);      // true / false
 * ```
 *
 * `verificar` **no recibe el libro**: sólo la hoja, su camino y la raíz. Es la
 * propiedad que hace que la prueba valga algo — el usuario comprueba sin
 * confiar en nosotros ni tener que descargar todo.
 *
 * `Prueba` viaja como JSON plano (números y strings hex). No hay clases ni
 * `Uint8Array` en la frontera a propósito: lo que cruza a la pantalla tiene que
 * poder serializarse sin ceremonia.
 *
 * =====================================================================
 * Las tres correcciones que hacen que el árbol no sea falsificable
 * =====================================================================
 *
 * **1. Separación de dominio.** La hoja se hashea con prefijo `0x00` y el nodo
 * interno con `0x01`. Sin esos prefijos, el hash de un nodo interno tiene
 * exactamente la misma forma que el de una hoja, y un atacante puede presentar
 * un nodo como si fuera un hecho suyo. Es la clase de fallo que no se ve
 * probando el camino feliz: el árbol verifica igual de bien.
 *
 * **2. Hoja impar: se PROMUEVE, no se duplica.** Si un nivel tiene un número
 * impar de nodos, el último sube al siguiente nivel tal cual. Duplicarlo —que
 * es lo que hace la implementación ingenua— abre un **segundo camino a la misma
 * raíz**: un árbol con las hojas `[a, b, c]` y otro con `[a, b, c, c]` dan la
 * misma raíz, así que la raíz deja de identificar el libro. Es el fallo de
 * maleabilidad de Bitcoin (CVE-2012-2459). La regla se escribe una vez y no se
 * cambia.
 *
 * **3. Campos con longitud, no concatenados.** Los bytes de la hoja llevan la
 * longitud de cada campo delante. Sin eso,
 * `{usuario:"ab", hecho:"c"}` y `{usuario:"a", hecho:"bc"}` podrían producir los
 * mismos bytes, y dos hechos distintos tendrían la misma hoja.
 *
 * =====================================================================
 * Lo que un árbol de Merkle NO prueba
 * =====================================================================
 *
 * Prueba que **tu** hecho está en el libro. **No** prueba que el libro esté
 * completo: si un hecho se omite entero, la raíz sigue verificando para todos
 * los demás y nadie lo nota. Eso es L15 y se cierra en `epoca.ts`, con la
 * secuencia por usuario y el conteo de hojas en el ancla. Aquí se deja dicho
 * para que nadie confunda «mi prueba verifica» con «el libro está entero».
 */

import { deHex, sha256Hex } from "./sha256";

/** Un hecho del libro, tal como se ancla. */
export interface Hoja {
  /** De quién es el hecho. La secuencia se cuenta por usuario (L15). */
  usuario: string;
  /** El n-ésimo hecho **de ese usuario**, empezando en 1 y sin huecos. */
  seq: number;
  /** El hecho, ya serializado. Qué contiene no le importa al árbol. */
  hecho: string;
}

const PREFIJO_HOJA = 0x00;
const PREFIJO_NODO = 0x01;

function u32(valor: number): Uint8Array {
  const salida = new Uint8Array(4);
  new DataView(salida.buffer).setUint32(0, valor);
  return salida;
}

function concat(partes: Uint8Array[]): Uint8Array {
  let total = 0;
  for (const parte of partes) total += parte.length;
  const salida = new Uint8Array(total);
  let cursor = 0;
  for (const parte of partes) {
    salida.set(parte, cursor);
    cursor += parte.length;
  }
  return salida;
}

/**
 * `SHA256(0x00 ‖ len(usuario) ‖ usuario ‖ seq ‖ len(hecho) ‖ hecho)`
 *
 * Las longitudes van delante de cada campo de texto para que la codificación
 * sea inequívoca: dos hojas distintas nunca producen los mismos bytes.
 */
export function hashHoja(hoja: Hoja): string {
  if (!Number.isInteger(hoja.seq) || hoja.seq < 1) {
    throw new Error(`secuencia inválida para ${hoja.usuario}: ${hoja.seq}`);
  }
  const codificar = new TextEncoder();
  const usuario = codificar.encode(hoja.usuario);
  const hecho = codificar.encode(hoja.hecho);
  return sha256Hex(
    concat([
      new Uint8Array([PREFIJO_HOJA]),
      u32(usuario.length),
      usuario,
      u32(hoja.seq),
      u32(hecho.length),
      hecho,
    ]),
  );
}

/** `SHA256(0x01 ‖ izq ‖ der)` — el prefijo distinto es lo que impide el disfraz. */
export function hashNodo(izquierdo: string, derecho: string): string {
  return sha256Hex(
    concat([new Uint8Array([PREFIJO_NODO]), deHex(izquierdo), deHex(derecho)]),
  );
}

/**
 * La raíz del árbol. Un libro vacío no tiene raíz: se lanza en vez de devolver
 * el hash de la cadena vacía, que verificaría «correctamente» contra nada.
 */
export function raiz(hojas: readonly Hoja[]): string {
  if (hojas.length === 0) throw new Error("una época vacía no tiene raíz");
  let nivel = hojas.map(hashHoja);
  while (nivel.length > 1) {
    const siguiente: string[] = [];
    for (let i = 0; i < nivel.length; i += 2) {
      // el impar se PROMUEVE tal cual: duplicarlo abriría un segundo camino
      // a la misma raíz, y la raíz dejaría de identificar el libro
      siguiente.push(i + 1 < nivel.length ? hashNodo(nivel[i], nivel[i + 1]) : nivel[i]);
    }
    nivel = siguiente;
  }
  return nivel[0];
}

/** Un paso del camino: el hermano, y de qué lado está. */
export interface Paso {
  hash: string;
  lado: "izq" | "der";
}

/** Lo que se le entrega a alguien para que compruebe su hoja sin el libro. */
export interface Prueba {
  /** Posición de la hoja en la época. Sirve para reproducir el camino. */
  indice: number;
  /** Cuántas hojas tenía la época. Tiene que coincidir con el ancla (L15). */
  hojas: number;
  camino: Paso[];
}

export function pruebaDeInclusion(hojas: readonly Hoja[], indice: number): Prueba {
  if (!Number.isInteger(indice) || indice < 0 || indice >= hojas.length) {
    throw new Error(`índice fuera del árbol: ${indice} de ${hojas.length} hojas`);
  }
  let nivel = hojas.map(hashHoja);
  let posicion = indice;
  const camino: Paso[] = [];

  while (nivel.length > 1) {
    const siguiente: string[] = [];
    for (let i = 0; i < nivel.length; i += 2) {
      if (i + 1 < nivel.length) {
        if (i === posicion) camino.push({ hash: nivel[i + 1], lado: "der" });
        else if (i + 1 === posicion) camino.push({ hash: nivel[i], lado: "izq" });
        siguiente.push(hashNodo(nivel[i], nivel[i + 1]));
      } else {
        // promovido: sube sin hermano, así que el camino no gana un paso
        siguiente.push(nivel[i]);
      }
    }
    posicion = posicion >> 1;
    nivel = siguiente;
  }
  return { indice, hojas: hojas.length, camino };
}

/**
 * Comprueba una hoja contra una raíz **sin ver el libro**. Es toda la gracia:
 * quien apostó puede verificar que su hecho está anclado sin descargar nada
 * nuestro y sin creernos.
 */
export function verificar(hoja: Hoja, prueba: Prueba, raizEsperada: string): boolean {
  if (prueba.indice < 0 || prueba.indice >= prueba.hojas) return false;
  let actual: string;
  try {
    actual = hashHoja(hoja);
    for (const paso of prueba.camino) {
      actual = paso.lado === "izq" ? hashNodo(paso.hash, actual) : hashNodo(actual, paso.hash);
    }
  } catch {
    // un camino con hashes mal formados no verifica; no revienta a quien mira
    return false;
  }
  return actual === raizEsperada;
}
