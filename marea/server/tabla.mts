import type { Store } from "./store.mts";

/**
 * Tabla de posiciones. En un producto de predicción el marcador no es cuánto
 * apostaste: es **cuántas veces le atinaste**. Por eso se muestra precisión y
 * racha junto a los puntos — es lo que la gente quiere presumir y lo que hace
 * que vuelva mañana a ver si la mantuvo.
 *
 * Sólo entra quien ya tiene una apuesta liquidada. Una tabla llena de gente
 * con cero apuestas no dice nada y hace ver el producto vacío.
 */

export interface FilaTabla {
  posicion: number;
  usuario: string;
  puntos: number;
  /** Apuestas ya liquidadas. */
  resueltas: number;
  aciertos: number;
  /** Aciertos sobre resueltas, 0..1. */
  precision: number;
  /** Aciertos consecutivos, contando desde la última liquidación. */
  racha: number;
}

export interface Tabla {
  filas: FilaTabla[];
  /** Dónde va el que pregunta, aunque esté fuera del top. */
  tuya?: FilaTabla;
}

export function calcularTabla(store: Store, usuarioId?: string, limite = 20): Tabla {
  const filas: FilaTabla[] = [];

  for (const usuario of store.usuarios()) {
    /**
     * Las **devueltas no cuentan**, ni a favor ni en contra.
     *
     * Un mercado anulado —porque hizo falta gente (R-059), porque nadie acertó
     * (R-024), o porque la fuente no contestó nunca y se dio por incobrable—
     * no dice nada sobre si alguien atina. El dinero volvió íntegro: no hubo
     * acierto ni fallo, no hubo pregunta.
     *
     * Contarlas hundía la precisión de quien no había hecho nada mal. Medido en
     * producción el día que se arregló el atasco: `rasdg05` pasó de 1/10 a
     * **1/13** en cuanto se anularon tres mercados congelados desde agosto —
     * castigado por un fallo nuestro, dos veces: primero esperando un mes, y
     * después en la tabla.
     *
     * Se mira la **fase de la liquidación**, no `pagado === stake`: una apuesta
     * puede pagar exactamente lo apostado y ser un acierto legítimo cuando el
     * multiplicador da 1.
     */
    const liquidadas = store
      .apuestasDe(usuario.id)
      .filter((apuesta) => apuesta.pagado !== undefined)
      .filter((apuesta) => store.liquidacion(apuesta.marketId)?.phase !== "devuelto")
      .sort((a, b) => (a.pagadoAt ?? "").localeCompare(b.pagadoAt ?? ""));

    if (liquidadas.length === 0) continue;

    const aciertos = liquidadas.filter((apuesta) => (apuesta.pagado ?? 0) > apuesta.stake).length;

    // la racha se cuenta hacia atrás desde la última: se rompe con un fallo
    let racha = 0;
    for (let i = liquidadas.length - 1; i >= 0; i -= 1) {
      if ((liquidadas[i].pagado ?? 0) > liquidadas[i].stake) racha += 1;
      else break;
    }

    filas.push({
      posicion: 0,
      usuario: usuario.usuario,
      puntos: usuario.puntos,
      resueltas: liquidadas.length,
      aciertos,
      precision: aciertos / liquidadas.length,
      racha,
    });
  }

  // se ordena por puntos, que es el marcador que todos entienden sin explicar
  filas.sort((a, b) => b.puntos - a.puntos || b.precision - a.precision);
  filas.forEach((fila, indice) => {
    fila.posicion = indice + 1;
  });

  const yo = usuarioId ? store.usuarioPorId(usuarioId) : undefined;
  const tuya = yo ? filas.find((fila) => fila.usuario === yo.usuario) : undefined;

  return { filas: filas.slice(0, limite), tuya };
}
