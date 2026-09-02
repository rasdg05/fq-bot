import { describe, expect, it } from "vitest";
import {
  abrir,
  acunar,
  auditar,
  colateral,
  contratosDe,
  cruce,
  emitidos,
  exposicionNeta,
  fusionar,
  liquidar,
  transferir,
  PozoInconsistente,
  type Asignacion,
  type OutcomeId,
  type Pozo,
  type TenedorId,
} from "@/domain/pozo";

/**
 * Pruebas del compensador. La de propiedad es la que importa: mil secuencias
 * aleatorias de operaciones, y en todas el pozo tiene que salir neutral con
 * cualquier ganador.
 *
 * El generador es **determinista** — un PRNG con semilla fija — para que un
 * fallo se pueda reproducir con el número de secuencia y no dependa de la hora
 * a la que corrió la suite.
 */

function prng(semilla: number): () => number {
  /**
   * Se mezcla la semilla y se descartan las primeras salidas. Sin esto el
   * generador miente: un LCG sembrado con valores consecutivos —como aquí,
   * `0x9e37 + n`— devuelve primeros valores correlacionados, y la primera
   * decisión de cada secuencia es cuántos resultados tiene el mercado. Medido:
   * salían 827 mercados binarios y 173 de cuatro resultados, y **ni uno solo de
   * tres**. Mil secuencias en verde que nunca probaron un caso entero.
   */
  let s = (Math.imul(semilla ^ 0x9e37_79b9, 0x85eb_ca6b) >>> 0) || 1;
  const siguiente = (): number => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 0x1_0000_0000;
  };
  for (let i = 0; i < 8; i += 1) siguiente();
  return siguiente;
}

const TENEDORES: TenedorId[] = ["ana", "beto", "caro", "dani", "casa"];

interface Secuencia {
  pozo: Pozo;
  /** Colateral que entró al pozo por acuñaciones. */
  entrado: number;
  /** Colateral que salió por fusiones, antes de resolver. */
  liberado: number;
  /** Problemas detectados en cualquier paso intermedio. */
  problemas: string[];
}

function generar(rnd: () => number): Secuencia {
  const nOutcomes = 2 + Math.floor(rnd() * 3); // 2, 3 o 4 resultados
  const outcomes: OutcomeId[] = Array.from({ length: nOutcomes }, (_, i) => `r${i}`);
  let pozo = abrir(`m-${Math.floor(rnd() * 1e6)}`, outcomes);
  let entrado = 0;
  let liberado = 0;
  const problemas: string[] = [];

  const tenedor = () => TENEDORES[Math.floor(rnd() * TENEDORES.length)];
  const cantidad = () => 1 + Math.floor(rnd() * 50);

  const pasos = 3 + Math.floor(rnd() * 10);
  for (let i = 0; i < pasos; i += 1) {
    const dado = rnd();

    if (dado < 0.45) {
      // el caso normal: dos partes se cruzan
      const q = cantidad();
      pozo = cruce(pozo, q, outcomes[Math.floor(rnd() * outcomes.length)], tenedor(), tenedor());
      entrado += q;
    } else if (dado < 0.65) {
      // alguien acuña para sí mismo un conjunto completo
      const q = cantidad();
      const duenio = tenedor();
      const asignacion: Asignacion = {};
      for (const id of outcomes) asignacion[id] = { [duenio]: q };
      pozo = acunar(pozo, q, asignacion);
      entrado += q;
    } else if (dado < 0.85) {
      // mercado secundario: mueve contratos sin tocar el colateral
      const outcome = outcomes[Math.floor(rnd() * outcomes.length)];
      const conAlgo = Object.entries(pozo.contratos[outcome]).filter(([, c]) => c > 0);
      if (conAlgo.length > 0) {
        const [de, tiene] = conAlgo[Math.floor(rnd() * conAlgo.length)];
        const q = Math.max(1, Math.floor(tiene * rnd()));
        pozo = transferir(pozo, outcome, de, tenedor(), Math.min(q, tiene));
      }
    } else {
      // sale antes de que resuelva: devuelve un conjunto completo
      const candidato = TENEDORES.find((t) =>
        outcomes.every((id) => contratosDe(pozo, id, t) >= 1),
      );
      if (candidato) {
        const maximo = Math.min(...outcomes.map((id) => contratosDe(pozo, id, candidato)));
        const q = Math.max(1, Math.floor(maximo * rnd()));
        const salida = fusionar(pozo, Math.min(q, maximo), candidato);
        pozo = salida.pozo;
        liberado += salida.colateralLiberado;
      }
    }

    // L2 · el pozo nunca es contraparte: se comprueba en CADA paso, no al final
    problemas.push(...auditar(pozo).map((p) => `paso ${i}: ${p}`));
  }

  return { pozo, entrado, liberado, problemas };
}

describe("pozo · propiedad de neutralidad (L1 · L2 · L5)", () => {
  it("mil secuencias aleatorias: el pozo sale neutral con cualquier ganador", () => {
    const SECUENCIAS = 1000;
    const fallos: string[] = [];

    for (let n = 0; n < SECUENCIAS; n += 1) {
      const rnd = prng(0x9e37 + n);
      const { pozo, entrado, liberado, problemas } = generar(rnd);

      if (problemas.length > 0) {
        fallos.push(`secuencia ${n}: ${problemas[0]}`);
        continue;
      }

      // L1 · el colateral retenido es exactamente lo que entró menos lo que salió
      if (colateral(pozo) !== entrado - liberado) {
        fallos.push(
          `secuencia ${n}: colateral ${colateral(pozo)} ≠ entrado ${entrado} − liberado ${liberado}`,
        );
        continue;
      }

      // L2 · exposición neta cero en todos los resultados, antes de resolver
      for (const outcome of pozo.outcomes) {
        if (exposicionNeta(pozo, outcome) !== 0) {
          fallos.push(`secuencia ${n}: exposición en ${outcome}`);
        }
      }

      // La propiedad del dinero: se liquida el MISMO pozo con CADA ganador
      // posible y sale exactamente lo mismo. El pozo no sabe quién ganó.
      const pagados = pozo.outcomes.map((ganador) => liquidar(pozo, ganador));
      for (const [i, resultado] of pagados.entries()) {
        if (resultado.pagado !== colateral(pozo)) {
          fallos.push(
            `secuencia ${n}: con ganador ${pozo.outcomes[i]} pagó ${resultado.pagado} y retenía ${colateral(pozo)}`,
          );
        }
        // L5 · la suma de los pagos individuales es el total pagado
        const suma = Object.values(resultado.pagos).reduce((a, b) => a + b, 0);
        if (suma !== resultado.pagado) {
          fallos.push(`secuencia ${n}: los pagos suman ${suma} y el total dice ${resultado.pagado}`);
        }
        // y el pozo queda en cero, sin contratos colgando
        if (resultado.pozo.conjuntos !== 0) {
          fallos.push(`secuencia ${n}: quedaron ${resultado.pozo.conjuntos} conjuntos vivos`);
        }
        for (const id of resultado.pozo.outcomes) {
          if (emitidos(resultado.pozo, id) !== 0) {
            fallos.push(`secuencia ${n}: quedaron contratos de ${id} después de liquidar`);
          }
        }
      }

      // Capital propio del pozo: todo lo que entró volvió a salir, ni un céntimo
      // se quedó en la caja. Con cualquiera de los ganadores posibles.
      for (const resultado of pagados) {
        if (liberado + resultado.pagado !== entrado) {
          fallos.push(
            `secuencia ${n}: entró ${entrado}, salió ${liberado + resultado.pagado}`,
          );
        }
      }
    }

    expect(fallos.slice(0, 5)).toEqual([]);
    expect(fallos).toHaveLength(0);
  });
});

describe("pozo · lo que no se puede hacer", () => {
  it("no se abre un mercado con menos de dos resultados", () => {
    expect(() => abrir("m", ["si"])).toThrow(PozoInconsistente);
    expect(() => abrir("m", ["si", "si"])).toThrow(PozoInconsistente);
  });

  it("una acuñación que no reparte todo un resultado se rechaza al escribir", () => {
    const pozo = abrir("m", ["si", "no"]);
    // faltan 4 contratos del "no" por repartir: serían obligación sin dueño
    expect(() => acunar(pozo, 10, { si: { ana: 10 }, no: { beto: 6 } })).toThrow(
      PozoInconsistente,
    );
    // y de más: contratos sin colateral detrás
    expect(() => acunar(pozo, 10, { si: { ana: 10 }, no: { beto: 12 } })).toThrow(
      PozoInconsistente,
    );
  });

  it("no existe forma de crear contratos sin colateral", () => {
    const pozo = abrir("m", ["si", "no"]);
    expect(() => acunar(pozo, 0, { si: {}, no: {} })).toThrow(PozoInconsistente);
    expect(() => acunar(pozo, -5, { si: { ana: -5 }, no: { beto: -5 } })).toThrow(
      PozoInconsistente,
    );
  });

  it("nadie fusiona sin tener el conjunto completo", () => {
    const pozo = cruce(abrir("m", ["si", "no"]), 10, "si", "ana", "beto");
    expect(() => fusionar(pozo, 10, "ana")).toThrow(PozoInconsistente);
    expect(() => fusionar(pozo, 1, "caro")).toThrow(PozoInconsistente);
  });

  it("nadie transfiere lo que no tiene", () => {
    const pozo = cruce(abrir("m", ["si", "no"]), 10, "si", "ana", "beto");
    expect(() => transferir(pozo, "si", "ana", "caro", 11)).toThrow(PozoInconsistente);
    expect(() => transferir(pozo, "si", "beto", "caro", 1)).toThrow(PozoInconsistente);
  });

  it("no se liquida con un ganador que no es del mercado", () => {
    const pozo = cruce(abrir("m", ["si", "no"]), 10, "si", "ana", "beto");
    expect(() => liquidar(pozo, "quiza")).toThrow(PozoInconsistente);
  });
});

describe("pozo · el cruce, con números a la mano", () => {
  // El ejemplo del boceto: 10,000 contratos entre dos partes.
  const base = cruce(abrir("mx-inpc", ["si", "no"]), 10_000, "si", "evan", "diego");

  it("retiene exactamente lo acuñado y no tiene lado", () => {
    expect(colateral(base)).toBe(10_000);
    expect(exposicionNeta(base, "si")).toBe(0);
    expect(exposicionNeta(base, "no")).toBe(0);
    expect(auditar(base)).toEqual([]);
  });

  it("paga lo mismo gane quien gane", () => {
    const conSi = liquidar(base, "si");
    const conNo = liquidar(base, "no");
    expect(conSi.pagado).toBe(10_000);
    expect(conNo.pagado).toBe(10_000);
    expect(conSi.pagos).toEqual({ evan: 10_000 });
    expect(conNo.pagos).toEqual({ diego: 10_000 });
    expect(conSi.pozo.conjuntos).toBe(0);
  });

  it("quien junta el conjunto completo se sale sin esperar al oráculo", () => {
    const juntado = transferir(base, "no", "diego", "evan", 10_000);
    const { pozo, colateralLiberado } = fusionar(juntado, 10_000, "evan");
    expect(colateralLiberado).toBe(10_000);
    expect(colateral(pozo)).toBe(0);
    expect(auditar(pozo)).toEqual([]);
  });

  it("un pozo torcido a mano no se puede liquidar", () => {
    // se fabrica una obligación sin colateral detrás, saltándose las funciones
    const torcido = {
      ...base,
      contratos: { ...base.contratos, si: { evan: 10_001 } },
    };
    expect(auditar(torcido)).not.toEqual([]);
    expect(() => liquidar(torcido, "si")).toThrow(PozoInconsistente);
  });
});
