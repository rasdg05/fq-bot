import { SHORT_TITLE_IDEAL, type OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";
import { esVelaViva } from "../src/adapters/ownMarkets/cryptoLive";
import { retener } from "../src/domain/settlement";
import type { DecisionNueva } from "../src/domain/bitacora";
import {
  conciliar,
  revisar,
  type CodigoHallazgo,
  type FamiliaEsperada,
  type Foto,
  type Hallazgo,
  type MercadoEnFoto,
} from "../src/domain/revisor";
import type { Store } from "./store.mts";

/**
 * El revisor autónomo, corriendo en el servidor después de cada ciclo.
 *
 * Arma la foto con lo que hay en el disco, deja que el dominio decida, aplica
 * **la única** acción que toma solo sobre dinero —retener un pago que
 * contradice al mercado— y escribe en la bitácora lo que cambió. Nunca paga,
 * nunca anula antes del plazo, nunca reescribe un resultado (R-082).
 */

/** Las familias que el catálogo automático debería tener siempre abiertas. */
export const FAMILIAS: FamiliaEsperada[] = [
  { nombre: "partidos", es: (m) => m.fuente === "partido" || m.fuente === "partido_multiple" },
  { nombre: "cripto", es: (m) => m.fuente === "precio" },
  { nombre: "espejos de Kalshi", es: (m) => m.fuente === "espejo" },
  { nombre: "tendencias", es: (m) => m.fuente === "tendencia" },
  { nombre: "sismos", es: (m) => m.fuente === "sismo" },
];

/** La regla escrita que sostiene cada hallazgo, para la bitácora. */
const REGLA: Partial<Record<CodigoHallazgo, string>> = {
  resultado_fuera_de_opciones: "R-082",
  evidencia_no_sostiene: "R-081",
  resolucion_sin_evidencia: "R-025",
  pozo_descuadrado: "L3",
  huerfanas: "R-024",
  sin_leer: "L8",
  atorado: "L8",
};

export function fotoDe(
  store: Store,
  seeds: readonly OwnMarketSeed[],
  ahora: number,
  extra: Pick<Foto, "juicios" | "huerfanas"> = { huerfanas: {} },
): Foto {
  const vistos = new Set<string>();
  const mercados: MercadoEnFoto[] = [];
  for (const seed of seeds) {
    if (vistos.has(seed.id)) continue;
    vistos.add(seed.id);
    const conApuestas = store.apuestasDeMercado(seed.id).length > 0;
    const vela = esVelaViva(seed);
    // una vela sin apuestas nace y muere sin que nadie la toque: no hay nada que revisar
    if (vela && !conApuestas) continue;
    const guardado = store.pozo(seed.id);
    mercados.push({
      id: seed.id,
      shortTitle: seed.shortTitle,
      category: seed.category,
      closesAt: seed.closesAt,
      settlesAt: seed.resolution.settlesAt,
      outcomes: seed.outcomes?.map((o) => o.id) ?? ["si", "no"],
      fuente: seed.rule?.kind ?? "sin_regla",
      estado: store.liquidacion(seed.id),
      pozo: guardado ? { outcomes: guardado.outcomes, feeBps: guardado.feeBps } : seed.pool,
      conApuestas,
      vela,
    });
  }
  return {
    ahora,
    mercados,
    descuadre: store.cuadre(),
    pozosConSaldo: store.pozosConSaldoTrasLiquidar(),
    detallePozos: store.detallePozosConSaldo(),
    huerfanas: extra.huerfanas,
    familias: FAMILIAS,
    tituloIdeal: SHORT_TITLE_IDEAL,
    ...(extra.juicios ? { juicios: extra.juicios } : {}),
  };
}

export interface ResumenRevisor {
  abiertos: Hallazgo[];
  abren: Hallazgo[];
  cierran: Hallazgo[];
  retenidos: string[];
}

export function correrRevisor(store: Store, foto: Foto): ResumenRevisor {
  const { abiertos, abren, cierran } = conciliar(store.hallazgos(), revisar(foto), foto.ahora);
  const decisiones: DecisionNueva[] = [];
  const retenidos: string[] = [];

  // la única acción sobre dinero: retener lo que contradice al mercado
  for (const h of abiertos) {
    if (h.accion !== "retener") continue;
    const estado = store.liquidacion(h.sujeto);
    if (!estado || estado.retenidoPor || estado.phase !== "en_disputa") continue;
    store.guardarLiquidacion(retener(estado, h.detalle));
    retenidos.push(h.sujeto);
    decisiones.push({
      tipo: "retener",
      sujeto: h.sujeto,
      motivo: `Pago retenido: ${h.detalle}`,
      regla: REGLA[h.codigo] ?? "R-082",
      autor: "reglas",
      evidencia: estado.evidence,
      reversible: true,
    });
  }

  for (const h of abren) {
    decisiones.push({
      tipo: "hallazgo_abre",
      sujeto: h.sujeto,
      motivo: `[${h.severidad}] ${h.codigo}: ${h.detalle}`,
      ...(REGLA[h.codigo] ? { regla: REGLA[h.codigo] } : {}),
      autor: "reglas",
      reversible: true,
    });
  }
  for (const h of cierran) {
    decisiones.push({
      tipo: "hallazgo_cierra",
      sujeto: h.sujeto,
      motivo: `${h.codigo} ya no se observa (abierto desde ${h.desde ?? "?"}).`,
      autor: "reglas",
      reversible: true,
    });
  }

  store.anotar(decisiones, foto.ahora);
  store.guardarHallazgos(abiertos);
  return { abiertos, abren, cierran, retenidos };
}
