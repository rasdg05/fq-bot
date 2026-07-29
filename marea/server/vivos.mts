import { totalPool, type Pool } from "../src/domain/parimutuel";
import { bloqueoDeVentana, deltaPp, type IntervaloVivo } from "../src/domain/vela";
import type { VelaRule } from "../src/domain/oracleRule";
import type { PulsoVivo } from "../src/domain/types";
import type { OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";
import {
  ACTIVOS_VIVOS,
  esVelaViva,
  idDeVela,
  velaSeed,
  velasVigentes,
  type ActivoVivo,
} from "../src/adapters/ownMarkets/cryptoLive";
import type { Ticker } from "./precios.mts";
import type { Store } from "./store.mts";

/**
 * Planificador de mercados vivos.
 *
 * Lo que hace, en una frase: garantizar que a cualquier hora exista un mercado
 * de 5 min y uno de 15 min abiertos por activo, sin que nadie corra un script.
 *
 * Vive en el proceso del servidor y no en `public/mercados.json` a propósito.
 * El catálogo publicado se escribe con `npm run roll` y se relee cada cuarto de
 * hora — una cadencia perfectamente sana para un mercado que cierra el domingo
 * y absurda para uno que dura cinco minutos. Aquí el reloj es el mismo que el
 * de las velas.
 *
 * Los mercados vivos **no siembran pozo en disco al nacer**: son cientos al
 * día y la inmensa mayoría muere sin que nadie los toque. El pozo se crea con
 * la primera apuesta (ver `/api/apostar`), y desde ese momento el mercado
 * también se persiste, para que un reinicio a mitad de vela no deje esa apuesta
 * sin quién la resuelva.
 */

/** Cuánto se conserva un mercado vivo ya vencido antes de olvidarlo. */
const RETENCION_MS = 5 * 60_000;

export interface VivosOptions {
  intervalos?: readonly IntervaloVivo[];
  activos?: ActivoVivo[];
  now?: () => number;
}

/**
 * Lo que necesita la card viva para repintarse. El contrato es del dominio
 * (`PulsoVivo`) y no de este archivo: la interfaz y el servidor tienen que
 * estar hablando de la misma forma o el día que se separen la card enseña un
 * campo que ya no llega.
 */
export type VistaViva = PulsoVivo;

export class MercadosVivos {
  private readonly velas = new Map<string, OwnMarketSeed>();
  private readonly ahora: () => number;

  constructor(
    private readonly store: Store,
    private readonly ticker: Ticker,
    private readonly options: VivosOptions = {},
  ) {
    this.ahora = options.now ?? (() => Date.now());
    // lo que sobrevivió a un reinicio vuelve al planificador tal cual: su
    // strike ya está fijado y no se recalcula, o la pregunta cambiaría debajo
    // de quien ya apostó
    for (const seed of store.seedsVivas()) {
      if (esVelaViva(seed)) this.velas.set(seed.id, seed);
    }
  }

  /**
   * Una vuelta del planificador: crea lo que falte y olvida lo que ya no sirve.
   * Es idempotente — llamarla cien veces por ventana no crea cien mercados —
   * porque el id sale del reloj y un id ya conocido no se vuelve a sembrar.
   */
  tick(ahora = this.ahora()): void {
    for (const vela of velasVigentes({
      ahora,
      precio: (par) => this.ticker.precio(par)?.precio,
      intervalos: this.options.intervalos,
      activos: this.options.activos ?? ACTIVOS_VIVOS,
    })) {
      const id = idDeVela(vela.activo, vela.intervalo, vela.inicio);
      // el strike se fija la primera vez y nunca se recalcula: por eso la vela
      // ya conocida se deja intacta aunque el precio se haya movido
      if (this.velas.has(id)) continue;
      // la vela ya bloqueada no se crea: nacería sin poder aceptar apuestas
      if (ahora >= bloqueoDeVentana(vela.inicio, vela.intervalo)) continue;
      this.velas.set(id, velaSeed(vela));
    }

    this.purgar(ahora);
  }

  /**
   * Suelta lo que ya no tiene nada que hacer. Un mercado sin apuestas se va en
   * cuanto vence; uno con apuestas se queda hasta que el ciclo lo pague, porque
   * mientras haya dinero adentro tiene que existir el mercado que lo explique.
   */
  private purgar(ahora: number): void {
    for (const [id, seed] of this.velas) {
      const vence = new Date(seed.resolution.settlesAt).getTime() + RETENCION_MS;
      if (ahora < vence) continue;

      const apuestas = this.store.apuestasDeMercado(id);
      if (apuestas.length === 0) {
        this.velas.delete(id);
        continue;
      }
      const estado = this.store.liquidacion(id);
      if (estado?.phase === "pagado" || estado?.phase === "devuelto") {
        this.velas.delete(id);
        this.store.olvidarSeedViva(id);
      }
      // atorado o sin leer: se queda. Un mercado con dinero adentro no
      // desaparece del catálogo por haber vencido
    }
  }

  /** El catálogo vivo de este instante, para sumarlo al catálogo publicado. */
  seeds(): OwnMarketSeed[] {
    return [...this.velas.values()];
  }

  seed(id: string): OwnMarketSeed | undefined {
    return this.velas.get(id);
  }

  /**
   * Marca que este mercado ya tiene dinero adentro. Desde aquí sobrevive a un
   * reinicio; antes de la primera apuesta no valía la pena escribirlo.
   */
  persistir(id: string): void {
    const seed = this.velas.get(id);
    if (seed) this.store.guardarSeedViva(seed);
  }

  /** Los que hay que liquidar: sólo los que tienen apuestas de verdad. */
  seedsConApuestas(): OwnMarketSeed[] {
    return this.seeds().filter(
      (seed) => this.store.apuestasDeMercado(seed.id).length > 0,
    );
  }

  /**
   * El payload que refresca las cards, cada pocos segundos. Lleva sólo lo que
   * cambia —precio, reloj y pozo— y no el mercado entero: repetir el título y
   * el criterio de resolución veinte veces por minuto es gastar la red de la
   * gente en algo que no se movió (R-047).
   */
  vista(ahora = this.ahora()): VistaViva[] {
    const salida: VistaViva[] = [];
    for (const seed of this.velas.values()) {
      if (!esVelaViva(seed)) continue;
      const rule: VelaRule = seed.rule;
      const bloquea = new Date(seed.closesAt).getTime();
      // una vez bloqueado ya no hay nada vivo que mirar
      if (ahora > bloquea) continue;

      const tick = this.ticker.precio(rule.par);
      const pozo = this.pozoDe(seed);
      const total = totalPool(pozo);
      const probabilidades: Record<string, number> = {};
      const multiplicadores: Record<string, number> = {};
      const neto = 1 - Math.min(500, Math.max(0, pozo.feeBps)) / 10_000;
      for (const [id, apostado] of Object.entries(pozo.outcomes)) {
        probabilidades[id] = total > 0 ? apostado / total : 0;
        multiplicadores[id] = apostado > 0 ? (total * neto) / apostado : 0;
      }

      salida.push({
        id: seed.id,
        strike: rule.strike,
        spot: tick?.precio,
        deltaPp: tick ? deltaPp(tick.precio, rule.strike) : undefined,
        fuente: tick?.fuente,
        spotAt: tick ? new Date(tick.at).toISOString() : undefined,
        bloqueaAt: seed.closesAt,
        cierraAt: seed.resolution.settlesAt,
        probabilidades,
        multiplicadores,
        pozo: total,
        jugando: this.store.participantesDe(seed.id),
      });
    }
    return salida.sort((a, b) => a.bloqueaAt.localeCompare(b.bloqueaAt));
  }

  private pozoDe(seed: OwnMarketSeed): Pool {
    const guardado = this.store.pozo(seed.id);
    return guardado
      ? { outcomes: guardado.outcomes, feeBps: guardado.feeBps }
      : { outcomes: { ...seed.pool.outcomes }, feeBps: seed.pool.feeBps };
  }
}
