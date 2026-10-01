import type { OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";
import { verificarCadena, type EntradaBitacora, type TipoDecision, type Verificacion } from "../src/domain/bitacora";
import type { Hallazgo, Severidad } from "../src/domain/revisor";
import type { EstadoJuez } from "./juez.mts";
import type { Store } from "./store.mts";

/**
 * El reporte público del director (MEMORY/FILOSOFIA.md, principios 5 y 9: *un
 * agente que no se mide es una superstición*; *transparencia hacia afuera*).
 *
 * Sale por `/api/director` y lo pinta la pantalla «Director». No lleva datos de
 * usuarios: sólo mercados, decisiones y números agregados.
 */

const FAMILIA: Record<string, string> = {
  precio: "Cripto",
  vela: "Velas en vivo",
  serie: "Indicadores",
  partido: "Partidos",
  partido_multiple: "Partidos",
  espejo: "Espejos de Kalshi",
  tenis: "Tenis",
  tendencia: "Tendencias",
  sismo: "Sismos",
  sin_regla: "Sin oráculo",
};

export interface ReporteDirector {
  at: string;
  catalogo: { abiertos: number; porFamilia: Record<string, number>; multiOpcion: number };
  resoluciones7d: { resueltos: number; pagados: number; devueltos: number; medianaHoras: number | null };
  salud: { atorados: number; retenidos: number; hallazgos: Record<Severidad, number> };
  hallazgos: (Hallazgo & { titulo?: string })[];
  decisiones: {
    total: number;
    cadena: Verificacion;
    porTipo24h: Partial<Record<TipoDecision, number>>;
    /** Con el título legible del mercado al lado; la entrada de la cadena no se toca. */
    ultimas: (EntradaBitacora & { titulo?: string })[];
  };
  juez: EstadoJuez;
}

const H = 3_600_000;

function mediana(valores: number[]): number | null {
  if (valores.length === 0) return null;
  const v = [...valores].sort((a, b) => a - b);
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

export function reporteDirector(input: {
  store: Store;
  seeds: readonly OwnMarketSeed[];
  juez: EstadoJuez;
  ahora: number;
  ultimas?: number;
}): ReporteDirector {
  const { store, seeds, ahora } = input;
  const porId = new Map(seeds.map((s) => [s.id, s]));

  const abiertos = seeds.filter((s) => {
    const fase = store.liquidacion(s.id)?.phase;
    return Date.parse(s.closesAt) > ahora && (!fase || fase === "abierto");
  });
  const porFamilia: Record<string, number> = {};
  for (const s of abiertos) {
    const familia = FAMILIA[s.rule?.kind ?? "sin_regla"] ?? s.rule?.kind ?? "Otros";
    porFamilia[familia] = (porFamilia[familia] ?? 0) + 1;
  }

  const recientes = store
    .liquidaciones()
    .filter((l) => (l.phase === "pagado" || l.phase === "devuelto") && l.paidAt && ahora - Date.parse(l.paidAt) <= 7 * 24 * H);
  const tardanzas = recientes.flatMap((l) => {
    const seed = porId.get(l.marketId);
    if (!seed || !l.paidAt) return [];
    const horas = (Date.parse(l.paidAt) - Date.parse(seed.resolution.settlesAt)) / H;
    return Number.isFinite(horas) ? [Math.max(0, horas)] : [];
  });

  const hallazgos = [...store.hallazgos()];
  const conteo: Record<Severidad, number> = { critico: 0, grave: 0, aviso: 0, info: 0 };
  for (const h of hallazgos) conteo[h.severidad] += 1;

  const bitacora = store.bitacora();
  const porTipo24h: Partial<Record<TipoDecision, number>> = {};
  for (const e of bitacora) {
    if (ahora - Date.parse(e.at) <= 24 * H) porTipo24h[e.tipo] = (porTipo24h[e.tipo] ?? 0) + 1;
  }

  const estados = store.liquidaciones();
  const mediaHoras = mediana(tardanzas);
  return {
    at: new Date(ahora).toISOString(),
    catalogo: {
      abiertos: abiertos.length,
      porFamilia,
      multiOpcion: abiertos.filter((s) => (s.outcomes?.length ?? 2) > 2).length,
    },
    resoluciones7d: {
      resueltos: recientes.length,
      pagados: recientes.filter((l) => l.phase === "pagado").length,
      devueltos: recientes.filter((l) => l.phase === "devuelto").length,
      medianaHoras: mediaHoras === null ? null : Math.round(mediaHoras * 10) / 10,
    },
    salud: {
      atorados: estados.filter((l) => l.phase === "atorado" && !l.retenidoPor).length,
      retenidos: estados.filter((l) => l.retenidoPor).length,
      hallazgos: conteo,
    },
    hallazgos: hallazgos.slice(0, 30).map((h) => ({ ...h, titulo: porId.get(h.sujeto)?.shortTitle })),
    decisiones: {
      total: bitacora.length,
      cadena: verificarCadena(bitacora),
      porTipo24h,
      ultimas: bitacora
        .slice(-(input.ultimas ?? 40))
        .reverse()
        .map((e) => ({ ...e, titulo: porId.get(e.sujeto)?.shortTitle })),
    },
    juez: input.juez,
  };
}
