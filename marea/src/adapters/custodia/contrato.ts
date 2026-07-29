/**
 * Interfaz del contrato de custodia — **definida, no desplegada**.
 *
 * La decisión de arquitectura es híbrida si la regulación lo permite: el pozo
 * vive en un contrato y nosotros sólo operamos la resolución. Si el marco legal
 * lo impide, no custodial. Custodial quedó descartado.
 *
 * Lo que se puede escribir hoy sin esperar a nadie es **la forma** de esa
 * conversación. Lo que no se puede es fingir que existe: esta implementación
 * declara que es simulada y no expone ninguna manera de firmar una transacción
 * con fondos de nadie (R-022, I8).
 *
 * Lo que deliberadamente NO está aquí, y no se agrega hasta que haya opinión
 * legal escrita por país:
 *
 *  - `firmar()` — mover fondos de un usuario.
 *  - `retirar()` — sacar del pozo hacia una dirección.
 *  - cualquier llave privada, en cualquier forma.
 *
 * Se leen saldos y se calculan liquidaciones; ejecutar es otro asunto.
 */

export type EstadoPozoEnCadena = "sin_desplegar" | "abierto" | "cerrado" | "liquidado";

export interface PozoEnCadena {
  marketId: string;
  estado: EstadoPozoEnCadena;
  /** Lo comprometido por resultado, en la unidad mínima de la cadena. */
  outcomes: Record<string, number>;
  /** Dirección del contrato, cuando exista. */
  direccion?: string;
}

/** El resultado que la resolución le comunicaría al contrato. */
export interface InstruccionResolucion {
  marketId: string;
  outcomeId: string;
  /** La lectura que lo justifica, para que quede en el registro. */
  evidencia: string;
}

export interface ContratoCustodia {
  readonly id: string;
  /**
   * Si es `true`, nada de lo que devuelve esta implementación viene de una
   * cadena. Se expone a propósito para que la interfaz pueda decirlo en voz
   * alta en vez de aparentar (R-022).
   */
  readonly esSimulado: boolean;
  /** Qué es esto, en una frase que se pueda mostrar. */
  readonly descripcion: string;

  /** Lee el estado del pozo. Sólo lectura. */
  leerPozo(marketId: string): Promise<PozoEnCadena>;

  /**
   * Qué haría la resolución, sin hacerla. Devuelve la instrucción que se
   * mandaría, para poder revisarla antes de que exista la capacidad de
   * mandarla.
   */
  planearResolucion(instruccion: InstruccionResolucion): Promise<{
    /** Siempre `false` mientras no haya contrato desplegado. */
    ejecutable: boolean;
    motivo: string;
    instruccion: InstruccionResolucion;
  }>;
}

/**
 * Implementación simulada. Es la única que existe y lo dice.
 *
 * No hay una variante "real" escondida detrás de una bandera: cuando exista el
 * contrato, será otro módulo que implemente esta misma interfaz, y este seguirá
 * siendo el que se usa en pruebas.
 */
export function contratoSimulado(
  pozos: Record<string, Record<string, number>> = {},
): ContratoCustodia {
  return {
    id: "custodia-simulada",
    esSimulado: true,
    descripcion:
      "Contrato simulado: la interfaz está definida pero no hay contrato desplegado ni fondos en cadena.",

    async leerPozo(marketId: string): Promise<PozoEnCadena> {
      return {
        marketId,
        estado: "sin_desplegar",
        outcomes: pozos[marketId] ?? {},
      };
    },

    async planearResolucion(instruccion: InstruccionResolucion) {
      return {
        ejecutable: false,
        motivo:
          "No hay contrato desplegado. La resolución en cadena espera opinión legal por país.",
        instruccion,
      };
    },
  };
}
