import { createHash, randomBytes } from "node:crypto";
import { describe, expect, it } from "vitest";
import { deHex, sha256Hex } from "@/domain/sha256";
import {
  hashHoja,
  hashNodo,
  pruebaDeInclusion,
  raiz,
  verificar,
  type Hoja,
} from "@/domain/merkle";
import {
  cerrarEpoca,
  huecosDeSecuencia,
  verificarAncla,
  type Ancla,
} from "@/domain/epoca";

/**
 * El árbol de época. Lo que se prueba no es que hashee: es que **no sea
 * falsificable** de las tres formas conocidas, y que una omisión se note.
 */

function prng(semilla: number): () => number {
  let s = (Math.imul(semilla ^ 0x9e37_79b9, 0x85eb_ca6b) >>> 0) || 1;
  const siguiente = (): number => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 0x1_0000_0000;
  };
  for (let i = 0; i < 8; i += 1) siguiente();
  return siguiente;
}

/** Un libro con la secuencia bien puesta: 1..n por usuario, sin huecos. */
function libro(usuarios: string[], porUsuario: number[]): Hoja[] {
  const hojas: Hoja[] = [];
  usuarios.forEach((usuario, i) => {
    for (let n = 1; n <= porUsuario[i]; n += 1) {
      hojas.push({ usuario, seq: n, hecho: `apuesta ${n} de ${usuario}` });
    }
  });
  return hojas;
}

describe("SHA-256 propio", () => {
  it("da los vectores conocidos", () => {
    expect(sha256Hex(new Uint8Array())).toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
    expect(sha256Hex(new TextEncoder().encode("abc"))).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });

  it("coincide con node:crypto en las longitudes que cruzan el borde de bloque", () => {
    // que una implementación sea consistente consigo misma no prueba nada.
    // 55/56/64/119/120 son donde el relleno cambia de forma
    for (const n of [0, 1, 54, 55, 56, 57, 63, 64, 65, 119, 120, 121, 1000]) {
      const bytes = randomBytes(n);
      expect(sha256Hex(new Uint8Array(bytes)), `n=${n}`).toBe(
        createHash("sha256").update(bytes).digest("hex"),
      );
    }
  });
});

describe("Árbol de época — no falsificable", () => {
  it("genera una prueba de inclusión y se verifica sin ver el libro", () => {
    const hojas = libro(["ana", "beto", "caro"], [2, 3, 2]);
    const r = raiz(hojas);
    for (let i = 0; i < hojas.length; i += 1) {
      expect(verificar(hojas[i], pruebaDeInclusion(hojas, i), r), `hoja ${i}`).toBe(true);
    }
  });

  it("un árbol con número IMPAR de hojas verifica igual de bien", () => {
    for (const n of [1, 3, 5, 7, 9, 11, 13, 21, 33]) {
      const hojas = libro(["ana"], [n]);
      const r = raiz(hojas);
      for (let i = 0; i < n; i += 1) {
        expect(verificar(hojas[i], pruebaDeInclusion(hojas, i), r), `n=${n} i=${i}`).toBe(true);
      }
    }
  });

  it("separación de dominio: hoja y nodo viven en dominios distintos, y se comprueba", () => {
    /**
     * Lo que hay que fijar no es «el nodo no es igual a la hoja» —eso pasa por
     * casualidad aunque los prefijos sean iguales— sino que **los dos prefijos
     * existen y son distintos**. Sin eso, el hash de un nodo interno tiene la
     * misma forma que el de una hoja y se puede presentar como un hecho.
     *
     * Se comprueba contra los bytes, no contra la propia función: se
     * reconstruye a mano lo que debería hashearse.
     */
    const a = hashHoja({ usuario: "ana", seq: 1, hecho: "x" });
    const b = hashHoja({ usuario: "ana", seq: 2, hecho: "y" });
    const cuerpo = [...deHex(a), ...deHex(b)];

    // el nodo se hashea con 0x01 delante
    expect(hashNodo(a, b)).toBe(sha256Hex(new Uint8Array([0x01, ...cuerpo])));
    // y NO con 0x00, que es el dominio de las hojas: ése es el disfraz que se cierra
    expect(hashNodo(a, b)).not.toBe(sha256Hex(new Uint8Array([0x00, ...cuerpo])));

    // y la hoja, simétricamente, se hashea con 0x00 y no con 0x01
    const u = new TextEncoder().encode("ana");
    const h = new TextEncoder().encode("x");
    const cuerpoHoja = [0, 0, 0, u.length, ...u, 0, 0, 0, 1, 0, 0, 0, h.length, ...h];
    expect(hashHoja({ usuario: "ana", seq: 1, hecho: "x" })).toBe(
      sha256Hex(new Uint8Array([0x00, ...cuerpoHoja])),
    );
    expect(hashHoja({ usuario: "ana", seq: 1, hecho: "x" })).not.toBe(
      sha256Hex(new Uint8Array([0x01, ...cuerpoHoja])),
    );

    // el orden importa, además: un nodo no es su espejo
    expect(hashNodo(a, b)).not.toBe(hashNodo(b, a));
  });

  it("hoja impar: se PROMUEVE, y por eso [a,b,c] y [a,b,c,c] NO dan la misma raíz", () => {
    // duplicar la última abriría un segundo camino a la misma raíz, y la raíz
    // dejaría de identificar el libro (CVE-2012-2459)
    const tres = libro(["ana"], [3]);
    const cuatro = [...tres, tres[2]];
    expect(raiz(tres)).not.toBe(raiz(cuatro));
  });

  it("campos con longitud: la colisión real que existiría sin ellas, no una parecida", () => {
    /**
     * Sin longitudes, la hoja serían los bytes `usuario ‖ u32(seq) ‖ hecho`, y
     * este par **colisiona de verdad** — comprobado sobre los bytes:
     *
     *   {usuario:"ab", seq:1,          hecho:""}       → 61 62 00 00 00 01
     *   {usuario:"a",  seq:0x62000000, hecho:"\u0001"} → 61 62 00 00 00 01
     *
     * Dos hechos de dos usuarios distintos con la misma hoja. El primer intento
     * de este test usaba "ab"+"c" contra "a"+"bc", que **no** colisiona porque
     * el `seq` de ancho fijo va en medio: pasaba en verde con y sin longitudes,
     * y no probaba nada.
     */
    const A = { usuario: "ab", seq: 1, hecho: "" };
    const B = { usuario: "a", seq: 0x62000000, hecho: "\u0001" };
    expect(hashHoja(A)).not.toBe(hashHoja(B));

    // y lo evidente sigue valiendo: el seq forma parte de la identidad
    expect(hashHoja({ usuario: "ana", seq: 1, hecho: "x" })).not.toBe(
      hashHoja({ usuario: "ana", seq: 2, hecho: "x" }),
    );
  });

  it("una prueba de otra hoja no verifica, y una raíz de otra época tampoco", () => {
    const hojas = libro(["ana", "beto"], [3, 3]);
    const r = raiz(hojas);
    expect(verificar(hojas[0], pruebaDeInclusion(hojas, 1), r)).toBe(false);
    expect(verificar(hojas[0], pruebaDeInclusion(hojas, 0), raiz(libro(["ana"], [4])))).toBe(false);
  });

  it("cambiar un hecho invalida su prueba", () => {
    const hojas = libro(["ana", "beto"], [2, 2]);
    const r = raiz(hojas);
    const prueba = pruebaDeInclusion(hojas, 2);
    expect(verificar({ ...hojas[2], hecho: "otra cosa" }, prueba, r)).toBe(false);
  });

  it("una época vacía no tiene raíz: no se devuelve un hash que verifique contra nada", () => {
    expect(() => raiz([])).toThrow();
  });

  it("una secuencia inválida no llega a hoja", () => {
    expect(() => hashHoja({ usuario: "ana", seq: 0, hecho: "x" })).toThrow();
    expect(() => hashHoja({ usuario: "ana", seq: 1.5, hecho: "x" })).toThrow();
  });

  it("un camino con basura devuelve false, no revienta a quien mira", () => {
    const hojas = libro(["ana"], [4]);
    const prueba = pruebaDeInclusion(hojas, 0);
    expect(
      verificar(hojas[0], { ...prueba, camino: [{ hash: "no-es-hex", lado: "der" }] }, raiz(hojas)),
    ).toBe(false);
  });

  it("propiedad: cualquier libro de 1 a 40 hojas, cualquier hoja, verifica", () => {
    const rnd = prng(20260908);
    for (let caso = 0; caso < 120; caso += 1) {
      const usuarios = ["ana", "beto", "caro", "dani"].slice(0, 1 + Math.floor(rnd() * 4));
      const porUsuario = usuarios.map(() => 1 + Math.floor(rnd() * 10));
      const hojas = libro(usuarios, porUsuario);
      const r = raiz(hojas);
      const i = Math.floor(rnd() * hojas.length);
      expect(verificar(hojas[i], pruebaDeInclusion(hojas, i), r), `caso ${caso}`).toBe(true);
    }
  });
});

describe("L15 — una omisión es detectable", () => {
  it("borrar una hoja del libro rompe la verificación de alguien", () => {
    const hojas = libro(["ana", "beto", "caro"], [3, 3, 3]);
    const ancla = cerrarEpoca({ epoca: 1, hojas });

    // se borra la del medio de beto y se guardan las pruebas que ya se habían dado
    const pruebasPrevias = hojas.map((_, i) => pruebaDeInclusion(hojas, i));
    const mutilado = hojas.filter((_, i) => i !== 4);

    // 1. el conteo del ancla ya no cuadra
    expect(verificarAncla(ancla, mutilado)[0]).toContain("9 hojas y el libro trae 8");
    // 2. y las pruebas que ya se habían entregado dejan de verificar
    const rotas = hojas.filter((hoja, i) => !verificar(hoja, pruebasPrevias[i], raiz(mutilado)));
    expect(rotas.length).toBeGreaterThan(0);
  });

  it("y si se reancla el libro mutilado, la SECUENCIA lo delata", () => {
    // el caso interesante: quien borra también republica una raíz coherente.
    // La raíz y el conteo cuadran entre sí; lo que no cuadra es que a beto le
    // falte su hecho n.º 2, y eso lo ve él solo, sin ver el resto del libro
    const hojas = libro(["ana", "beto", "caro"], [3, 3, 3]);
    const mutilado = hojas.filter((h) => !(h.usuario === "beto" && h.seq === 2));
    const reanclado = cerrarEpoca({ epoca: 1, hojas: mutilado });

    expect(reanclado.hojas).toBe(8);
    expect(raiz(mutilado)).toBe(reanclado.raiz); // la raíz cuadra con el libro
    const problemas = verificarAncla(reanclado, mutilado);
    expect(problemas).toEqual(["a beto le falta el hecho n.º 2"]);
  });

  it("el usuario detecta su propio hueco mirando SÓLO sus hojas", () => {
    const mias = [
      { usuario: "beto", seq: 1, hecho: "a" },
      { usuario: "beto", seq: 3, hecho: "c" },
    ];
    expect(huecosDeSecuencia(mias)).toEqual([{ usuario: "beto", falta: 2 }]);
  });

  it("un libro entero no tiene huecos", () => {
    expect(huecosDeSecuencia(libro(["ana", "beto"], [5, 3]))).toEqual([]);
  });

  it("un duplicado es un hueco disfrazado y se reporta", () => {
    const hojas: Hoja[] = [
      { usuario: "ana", seq: 1, hecho: "a" },
      { usuario: "ana", seq: 2, hecho: "b" },
      { usuario: "ana", seq: 2, hecho: "b-falsa" },
    ];
    expect(huecosDeSecuencia(hojas)).toEqual([{ usuario: "ana", falta: 2 }]);
  });

  it("el ancla encadena con la anterior, y una época que se salta no se cierra", () => {
    const e1 = cerrarEpoca({ epoca: 1, hojas: libro(["ana"], [2]) });
    expect(e1.anterior).toBeNull();
    const e2 = cerrarEpoca({ epoca: 2, hojas: libro(["ana"], [3]), anterior: e1 });
    expect(e2.anterior).toBe(e1.raiz);
    expect(() => cerrarEpoca({ epoca: 4, hojas: libro(["ana"], [1]), anterior: e2 })).toThrow();
  });

  it("las tres comprobaciones del ancla son distintas y ninguna implica a las otras", () => {
    const hojas = libro(["ana", "beto"], [3, 3]);
    const ancla = cerrarEpoca({ epoca: 1, hojas });
    expect(verificarAncla(ancla, hojas)).toEqual([]);

    // sólo el conteo mal: mismo libro, ancla que miente en el número
    const mienteElConteo: Ancla = { ...ancla, hojas: 7 };
    expect(verificarAncla(mienteElConteo, hojas)).toEqual([
      "el ancla dice 7 hojas y el libro trae 6",
    ]);

    // sólo la raíz mal: mismo conteo, raíz de otro libro
    const mienteLaRaiz: Ancla = { ...ancla, raiz: raiz(libro(["ana", "beto"], [4, 2])) };
    expect(verificarAncla(mienteLaRaiz, hojas)[0]).toContain("la raíz no coincide");
  });
});
