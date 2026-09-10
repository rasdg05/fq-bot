import {
  filtrarPorPresupuesto,
  mercadoVivoDe,
  topesDelEntorno,
  type Topes,
} from "../src/domain/presupuesto";
import { partidosSeeds, rollingSeeds, type PartidoDeLaLiga } from "../src/adapters/ownMarkets/templates";
import { validateSeed, type OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";
import { esVelaViva } from "../src/adapters/ownMarkets/cryptoLive";
import type { Store } from "./store.mts";

/**
 * Reposición del catálogo, **dentro del servidor**.
 *
 * ## Por qué existe
 *
 * El catálogo se reponía con `npm run roll`, y ese comando lo dispara un cron
 * instalado **en la máquina de alguien** (`npm run cron:install` escribe un
 * launchd o un crontab local). Es decir: el feed de un producto en vivo
 * dependía de que una laptop concreta estuviera encendida.
 *
 * No es hipotético. Nadie lo corrió desde principios de agosto, y el 10 de
 * septiembre la app tenía **cuatro** mercados duraderos: la pantalla que ve
 * alguien que llega estaba prácticamente vacía. AGENTE §2 lo dice en una línea:
 * *un proceso que depende de que alguien se acuerde no existe.*
 *
 * El liquidador ya vive dentro del proceso y corre cada cuarto de hora. La
 * reposición va al mismo sitio, por el mismo reloj, y escribe al mismo volumen
 * persistente. Es exactamente lo que ya se hizo con las velas en vivo — sólo
 * que el catálogo duradero nunca lo recibió.
 *
 * ## Lo que NO hace
 *
 * No toca `public/mercados.json`. Ese archivo es del repo, se despliega y en
 * producción es de sólo lectura; los mercados generados aquí van al store, que
 * es el disco que sobrevive al redeploy. `roll` sigue existiendo para escribir
 * catálogo a mano cuando alguien quiera.
 *
 * Y no crea nada sin pasar por el presupuesto (L9, R-067). Repetir es barato;
 * gastar sin tope no.
 */

/** Cuántos mercados abiertos consideramos un feed vivo. Igual que en `roll`. */
export const MINIMO_ABIERTOS = 6;

export interface ReposicionOptions {
  /** Precio de contado por par. Ausente = no se generan mercados de cripto. */
  spot?: () => Record<string, number | undefined>;
  /** Partidos de los próximos días. Si falla, se sigue sin ellos. */
  partidos?: (dias: number) => Promise<PartidoDeLaLiga[]>;
  topes?: Topes;
  /** Para no depender del entorno en pruebas. */
  env?: Record<string, string | undefined>;
  avisar?: (mensaje: string) => void;
}

export interface ResumenReposicion {
  /**
   * Cuántos mercados **duraderos** aceptaban apuestas antes de reponer. Las
   * velas de cripto no cuentan: nacen y mueren cada cinco minutos, así que
   * siempre hay algunas y siempre parecería que el feed está lleno.
   */
  abiertosAntes: number;
  creados: string[];
  /** Rechazados por el freno de presupuesto, con su motivo. */
  frenados: { id: string; motivo: string }[];
  errores: string[];
}

/**
 * Una vuelta de la reposición. Idempotente: los ids de los mercados generados
 * salen de la fecha, así que llamarla cien veces en la misma ventana no crea
 * cien mercados.
 */
export async function reponer(
  store: Store,
  catalogo: readonly OwnMarketSeed[],
  ahora: number,
  options: ReposicionOptions = {},
): Promise<ResumenReposicion> {
  const resumen: ResumenReposicion = {
    abiertosAntes: 0,
    creados: [],
    frenados: [],
    errores: [],
  };

  const vivos = [...catalogo, ...store.seedsGeneradas()];
  const conocidos = new Set(vivos.map((seed) => seed.id));

  /**
   * Se cuentan sólo los mercados **duraderos**. Las velas de cripto no cuentan
   * aunque estén abiertas: nacen cada cinco minutos y mueren igual de rápido,
   * así que siempre hay tres o cuatro y siempre parecería que el feed está
   * lleno.
   *
   * No es hipotético: la primera versión de esto las contaba, y arrancando el
   * servidor contra un disco limpio se quedó sin reponer **nada** —cuatro velas
   * más tres mercados duraderos daban siete, por encima del mínimo— con la
   * pantalla igual de vacía que antes. Lo destapó la verificación en proceso
   * real, no la suite: el test pasaba un catálogo sin velas.
   */
  resumen.abiertosAntes = vivos.filter(
    (seed) => !esVelaViva(seed) && new Date(seed.closesAt).getTime() > ahora,
  ).length;

  // el feed ya está sano: no se crea por crear. Un catálogo que sólo crece es
  // un feed lleno de preguntas que a nadie le importan
  if (resumen.abiertosAntes >= MINIMO_ABIERTOS) return resumen;

  const candidatos: OwnMarketSeed[] = [];

  const precios = options.spot?.() ?? {};
  const spot: Record<string, number> = {};
  for (const [par, valor] of Object.entries(precios)) {
    if (typeof valor === "number" && Number.isFinite(valor) && valor > 0) spot[par] = valor;
  }
  if (Object.keys(spot).length > 0) {
    try {
      candidatos.push(...rollingSeeds({ spot, now: ahora }));
    } catch (error) {
      resumen.errores.push(`cripto: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  /**
   * Los partidos son opcionales a propósito: si ESPN no contesta se generan
   * igual los de cripto. Una fuente caída puede dejar el feed más corto; no
   * puede dejarlo vacío.
   */
  if (options.partidos) {
    try {
      candidatos.push(...partidosSeeds(await options.partidos(7), ahora));
    } catch (error) {
      resumen.errores.push(`partidos: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  const nuevos = candidatos.filter((seed) => !conocidos.has(seed.id));
  if (nuevos.length === 0) return resumen;

  // el freno de L9, antes de escribir nada
  const topes = options.topes ?? topesDelEntorno(options.env ?? {}, options.avisar);
  const { aceptados, rechazados } = filtrarPorPresupuesto({
    vivos: vivos.map(mercadoVivoDe),
    candidatos: nuevos.map(mercadoVivoDe),
    topes,
  });
  for (const { mercado, motivo } of rechazados) {
    resumen.frenados.push({ id: mercado.id, motivo });
  }

  const permitidos = new Set(aceptados.map((m) => m.id));
  for (const seed of nuevos) {
    if (!permitidos.has(seed.id)) continue;
    try {
      // se valida antes de guardar: un mercado sin fuente pública verificable no
      // se publica, y enterarse al arrancar es mejor que enterarse con gente
      // adentro (R-025)
      store.guardarSeedGenerada(validateSeed(seed));
      resumen.creados.push(seed.id);
    } catch (error) {
      resumen.errores.push(`${seed.id}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  return resumen;
}
