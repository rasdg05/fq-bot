import type { OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";
import { esVelaViva } from "../src/adapters/ownMarkets/cryptoLive";
import type { DecisionNueva } from "../src/domain/bitacora";
import { anular, initialState, type Oracle } from "../src/domain/settlement";
import { irresoluble, porActuar, REINTENTO_MS } from "../src/domain/remediacion";
import type { Foto } from "../src/domain/revisor";
import { correrCiclo } from "./ciclo.mts";
import { defaultOracles } from "../src/adapters/oracles/priceOracle";
import { correrRevisor, fotoDe } from "./revisor.mts";
import type { Store } from "./store.mts";

/**
 * El director en tiempo real (R-085): audita y, en la misma vuelta, actúa.
 *
 * Antes el revisor veía un partido atorado y lo dejaba escrito; el arreglo
 * esperaba al ciclo de un cuarto de hora, o al plazo de 30 días, o a una
 * persona. Ahora cada minuto:
 *
 *  1. revisa todo (la misma foto que el ciclo largo);
 *  2. de lo accionable —se pasó su cierre, sin resolver, atorado— elige lo que
 *     no intentó en los últimos minutos;
 *  3. anula y devuelve **ya** lo que demostrablemente no se va a resolver;
 *  4. vuelve a leer la fuente de lo demás, con los mismos oráculos y el mismo
 *     `correrCiclo`: si hay resultado, sigue el camino normal (disputa, pago);
 *  5. anota cada cambio de fase en la bitácora, con la evidencia.
 *
 * Lo que no hace: elegir un ganador, pagar distinto de lo que dice la fuente ni
 * tocar velas en vivo (tienen su propio reloj de diez segundos).
 */

export interface AccionDirector {
  id: string;
  de: string;
  a: string;
  /** Anulado por irresoluble, o vuelto a leer. */
  como: "anular" | "releer";
  motivo: string;
}

export interface ResumenAgente {
  at: string;
  intentados: number;
  acciones: AccionDirector[];
  errores: string[];
}

/**
 * Serializa todo lo que liquida. El ciclo largo y el director leen y escriben
 * las mismas liquidaciones; dos `correrCiclo` a la vez sobre un mismo mercado
 * podrían leer la misma fase y pagar dos veces.
 */
export class Turno {
  private cola: Promise<unknown> = Promise.resolve();
  correr<T>(trabajo: () => Promise<T>): Promise<T> {
    const siguiente = this.cola.then(trabajo, trabajo);
    this.cola = siguiente.catch(() => undefined);
    return siguiente;
  }
}

export class DirectorEnVivo {
  private readonly ultimoIntento = new Map<string, number>();
  ultima: ResumenAgente | null = null;

  constructor(
    private readonly store: Store,
    private readonly oracles: () => Oracle[] = defaultOracles,
  ) {}

  /**
   * Una vuelta. `catalogo` son los mercados sobre los que puede actuar;
   * `foto` lleva además lo que sólo se audita (velas con apuestas).
   */
  async vuelta(input: {
    catalogo: readonly OwnMarketSeed[];
    auditados?: readonly OwnMarketSeed[];
    extra?: Pick<Foto, "juicios" | "huerfanas">;
    ahora: number;
  }): Promise<ResumenAgente> {
    const { store } = this;
    const { catalogo, ahora } = input;
    const auditados = input.auditados ?? catalogo;
    const extra = input.extra ?? { huerfanas: store.apuestasHuerfanas(auditados.map((s) => s.id)) };
    const resumen: ResumenAgente = { at: new Date(ahora).toISOString(), intentados: 0, acciones: [], errores: [] };

    const revision = correrRevisor(store, fotoDe(store, auditados, ahora, extra));
    const porId = new Map(catalogo.filter((s) => !esVelaViva(s)).map((s) => [s.id, s]));
    const ids = porActuar(revision.abiertos, this.ultimoIntento, ahora).filter((id) => porId.has(id));
    if (ids.length === 0) return (this.ultima = resumen);
    resumen.intentados = ids.length;

    const antes = new Map(ids.map((id) => [id, store.liquidacion(id)?.phase ?? "abierto"]));
    const anulados = new Map<string, string>();
    for (const id of ids) {
      this.ultimoIntento.set(id, ahora);
      const seed = porId.get(id)!;
      const estado = store.liquidacion(id);
      const motivo = irresoluble({ id, closesAt: seed.closesAt, rule: seed.rule, estado }, ahora);
      if (motivo) {
        store.guardarLiquidacion(anular(estado ?? initialState(id), motivo));
        anulados.set(id, motivo);
      }
    }

    // la devolución, la relectura y el pago, por el camino de siempre
    const subconjunto = ids.map((id) => porId.get(id)!);
    const ciclo = await correrCiclo(store, subconjunto, this.oracles(), ahora);
    resumen.errores.push(...ciclo.errores);

    const decisiones: DecisionNueva[] = [];
    for (const id of ids) {
      const despues = store.liquidacion(id);
      const de = antes.get(id)!;
      const a = despues?.phase ?? "abierto";
      if (a === de && !anulados.has(id)) continue;
      const como = anulados.has(id) ? "anular" : "releer";
      const motivo = anulados.get(id) ?? despues?.evidence ?? despues?.stuckReason ?? "Se volvió a leer la fuente.";
      resumen.acciones.push({ id, de, a, como, motivo });
      decisiones.push({
        tipo: "actuar",
        sujeto: id,
        motivo:
          como === "anular"
            ? `Anulado y devuelto (${de} → ${a}): ${motivo}`
            : `Releído en vivo (${de} → ${a}).`,
        regla: "R-085",
        autor: "reglas",
        ...(despues?.evidence ? { evidencia: despues.evidence } : {}),
        // devolver lo apostado no se deshace; cerrar o pasar a disputa sí
        reversible: a !== "devuelto" && a !== "pagado",
      });
    }
    store.anotar(decisiones, ahora);

    // lo que se arregló deja de verse en esta misma vuelta, no en la siguiente
    if (decisiones.length > 0) correrRevisor(store, fotoDe(store, auditados, ahora, extra));

    for (const [id, cuando] of this.ultimoIntento) {
      if (ahora - cuando > 24 * 60 * 60_000 + REINTENTO_MS) this.ultimoIntento.delete(id);
    }
    return (this.ultima = resumen);
  }
}
