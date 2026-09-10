/**
 * SHA-256 en TypeScript puro. Sin dependencias y **síncrono**.
 *
 * ## Por qué no `node:crypto` ni `crypto.subtle`
 *
 * `node:crypto` no existe en el navegador, y la pantalla del verificador —que
 * es de quien comprueba su propia prueba de inclusión— corre ahí. `crypto.subtle`
 * existe en los dos pero es **asíncrono**, y una API asíncrona se contagia hacia
 * arriba: el árbol entero, las pruebas y quien las verifique acabarían
 * devolviendo promesas por una decisión de plataforma, no de dominio.
 *
 * El resto de `domain/` es puro y síncrono. Sesenta líneas de aritmética con
 * vectores de prueba conocidos cuestan menos que romper eso.
 *
 * Contrastado en la suite contra `node:crypto` sobre entradas aleatorias: no
 * vale que una implementación sea consistente consigo misma.
 */

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

function rotr(x: number, n: number): number {
  return ((x >>> n) | (x << (32 - n))) >>> 0;
}

/** SHA-256 de una secuencia de bytes. Devuelve los 32 bytes del digest. */
export function sha256(mensaje: Uint8Array): Uint8Array {
  const h = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);

  // relleno: un 1, ceros, y la longitud en bits como entero de 64 bits big-endian
  const bits = mensaje.length * 8;
  const conRelleno = new Uint8Array(((mensaje.length + 9 + 63) >> 6) << 6);
  conRelleno.set(mensaje);
  conRelleno[mensaje.length] = 0x80;
  // la longitud cabe en 53 bits sin perder precisión; más que eso no lo vamos a hashear
  const vista = new DataView(conRelleno.buffer);
  vista.setUint32(conRelleno.length - 8, Math.floor(bits / 0x1_0000_0000));
  vista.setUint32(conRelleno.length - 4, bits >>> 0);

  const w = new Uint32Array(64);
  for (let inicio = 0; inicio < conRelleno.length; inicio += 64) {
    for (let i = 0; i < 16; i += 1) w[i] = vista.getUint32(inicio + i * 4);
    for (let i = 16; i < 64; i += 1) {
      const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
      const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }

    let [a, b, c, d, e, f, g, hh] = h;
    for (let i = 0; i < 64; i += 1) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (hh + S1 + ch + K[i] + w[i]) >>> 0;
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (S0 + maj) >>> 0;
      hh = g;
      g = f;
      f = e;
      e = (d + t1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (t1 + t2) >>> 0;
    }
    h[0] = (h[0] + a) >>> 0;
    h[1] = (h[1] + b) >>> 0;
    h[2] = (h[2] + c) >>> 0;
    h[3] = (h[3] + d) >>> 0;
    h[4] = (h[4] + e) >>> 0;
    h[5] = (h[5] + f) >>> 0;
    h[6] = (h[6] + g) >>> 0;
    h[7] = (h[7] + hh) >>> 0;
  }

  const salida = new Uint8Array(32);
  const salidaVista = new DataView(salida.buffer);
  for (let i = 0; i < 8; i += 1) salidaVista.setUint32(i * 4, h[i]);
  return salida;
}

export function aHex(bytes: Uint8Array): string {
  let salida = "";
  for (const byte of bytes) salida += byte.toString(16).padStart(2, "0");
  return salida;
}

export function deHex(hex: string): Uint8Array {
  if (hex.length % 2 !== 0 || !/^[0-9a-f]*$/i.test(hex)) {
    throw new Error(`no es hexadecimal: ${hex}`);
  }
  const salida = new Uint8Array(hex.length / 2);
  for (let i = 0; i < salida.length; i += 1) salida[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return salida;
}

/** SHA-256 en hexadecimal, que es como viaja en el ancla y en las pruebas. */
export function sha256Hex(mensaje: Uint8Array): string {
  return aHex(sha256(mensaje));
}
