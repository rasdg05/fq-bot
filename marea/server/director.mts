import type { OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";
import { esVelaViva } from "../src/adapters/ownMarkets/cryptoLive";
import { backtest, type Calificacion, type Muestra } from "../src/domain/calibracion";
import { probabilities } from "../src/domain/parimutuel";
import { verificarCadena, type EntradaBitacora, type TipoDecision, type Verificacion } from "../src/domain/bitacora";
import type { Hallazgo, Severidad } from "../src/domain/revisor";
import type { ResumenAgente } from "./agente.mts";
import type { EstadoJuez } from "./juez.mts";
import type { Store } from "./store.mts";

/**
 * El tablero del director (MEMORY/FILOSOFIA.md, principio 5: *un agente que no
 * se mide es una superstición*).
 *
 * Sale por `/api/director` —sólo para quien opera Marea, ver `esDirector`— y lo
 * pinta la pantalla «Director». No lleva datos de usuarios: sólo mercados,
 * decisiones y números agregados.
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
  /** El bucle en tiempo real (R-085): su última vuelta y cada cuánto corre. */
  enVivo: { cadaSegundos: number; ultima: ResumenAgente | null; acciones24h: number } | null;
  /** ¿Sirven sus priors? Calificados contra lo que de verdad pasó. */
  backtest: { total: Calificacion; porFamilia: Record<string, Calificacion> };
  /** Las últimas vueltas que hicieron algo o fallaron, la más reciente primero. */
  depuracion: { vueltas: ResumenAgente[] };
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
  enVivo?: { cadaMs: number; ultima: ResumenAgente | null; historial?: readonly ResumenAgente[] };
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
    enVivo: input.enVivo
      ? {
          cadaSegundos: Math.round(input.enVivo.cadaMs / 1000),
          ultima: input.enVivo.ultima,
          acciones24h: porTipo24h.actuar ?? 0,
        }
      : null,
    backtest: backtest(muestrasDe(store, seeds)),
    depuracion: { vueltas: [...(input.enVivo?.historial ?? [])].slice(0, 30) },
  };
}

/**
 * Lo calificable: cada mercado del catálogo que ya pagó, con el prior con que
 * nació (`seed.pool`, que no cambia) y el precio del pozo al cierre (la semilla
 * más todo lo apostado). Las velas no entran: su semilla es pareja por
 * construcción y no dice nada del director.
 */
export function muestrasDe(store: Store, seeds: readonly OwnMarketSeed[]): Muestra[] {
  const muestras: Muestra[] = [];
  const vistos = new Set<string>();
  for (const seed of seeds) {
    if (vistos.has(seed.id) || esVelaViva(seed)) continue;
    vistos.add(seed.id);
    const estado = store.liquidacion(seed.id);
    if (estado?.phase !== "pagado" || !estado.outcome) continue;
    const ids = seed.outcomes?.map((o) => o.id) ?? ["si", "no"];
    if (!ids.includes(estado.outcome)) continue;
    const director = probabilities({ ...seed.pool, outcomes: Object.fromEntries(ids.map((id) => [id, seed.pool.outcomes[id] ?? 0])) });
    const apuestas = store.apuestasDeMercado(seed.id);
    const alCierre = Object.fromEntries(ids.map((id) => [id, seed.pool.outcomes[id] ?? 0]));
    for (const a of apuestas) if (a.side in alCierre) alCierre[a.side] += a.stake;
    muestras.push({
      id: seed.id,
      familia: FAMILIA[seed.rule?.kind ?? "sin_regla"] ?? seed.rule?.kind ?? "Otros",
      apuestas: apuestas.length,
      director,
      gente: probabilities({ ...seed.pool, outcomes: alCierre }),
      ganador: estado.outcome,
    });
  }
  return muestras;
}

/**
 * La traza de un mercado, para depurar: todo lo que se sabe de él en un solo
 * lugar —qué prometía, en qué fase está, qué dijo la fuente la última vez, qué
 * hallazgos tiene abiertos y cada decisión que se tomó sobre él—.
 */
export function trazaDe(store: Store, seeds: readonly OwnMarketSeed[], id: string) {
  const seed = seeds.find((s) => s.id === id);
  const decisiones = store.bitacora().filter((e) => e.sujeto === id);
  if (!seed && decisiones.length === 0) return null;
  const apuestas = store.apuestasDeMercado(id);
  return {
    id,
    mercado: seed
      ? {
          titulo: seed.shortTitle,
          familia: FAMILIA[seed.rule?.kind ?? "sin_regla"] ?? seed.rule?.kind,
          cierra: seed.closesAt,
          resuelve: seed.resolution.settlesAt,
          fuente: seed.resolution.sourceName,
          fuenteUrl: seed.resolution.sourceUrl,
          criterio: seed.resolution.criterion,
          opciones: seed.outcomes?.map((o) => o.id) ?? ["si", "no"],
          prior: probabilities(seed.pool),
        }
      : null,
    estado: store.liquidacion(id) ?? null,
    pozo: store.pozo(id)?.outcomes ?? null,
    apuestas: { n: apuestas.length, sinPagar: apuestas.filter((a) => a.pagado === undefined).length },
    hallazgos: store.hallazgos().filter((h) => h.sujeto === id),
    decisiones,
  };
}

/**
 * Quién ve el panel del director. No es público: enseña hallazgos, pozos y la
 * bitácora completa, y eso es tablero de operación, no vitrina.
 *
 * `MAREA_ADMINS` lista los usuarios separados por coma, sin distinguir
 * mayúsculas. Sin la variable, la cuenta más antigua —quien abrió la app— y
 * nadie más: un panel interno no se abre por omisión.
 */
export function directores(store: Store, env: Record<string, string | undefined> = process.env): Set<string> {
  const lista = (env.MAREA_ADMINS ?? "")
    .split(",")
    .map((n) => n.trim().toLowerCase())
    .filter(Boolean);
  if (lista.length > 0) return new Set(lista);
  const [primera] = [...store.usuarios()].sort((a, b) => a.creado.localeCompare(b.creado));
  return new Set(primera ? [primera.usuario.toLowerCase()] : []);
}

export function esDirector(
  store: Store,
  usuario: { usuario: string } | null | undefined,
  env: Record<string, string | undefined> = process.env,
): boolean {
  return !!usuario && directores(store, env).has(usuario.usuario.toLowerCase());
}
