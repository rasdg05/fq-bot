/**
 * El backtest del director: ¿sus priors sirven? (MEMORY/FILOSOFIA.md,
 * principio 5: *un agente que no se mide es una superstición*).
 *
 * Cada mercado pagado es una predicción que ya se puede calificar. Se califican
 * tres pronosticadores sobre los **mismos** mercados:
 *
 *  - **parejo**: 1/K a cada opción. La vara mínima;
 *  - **director**: el prior con que sembró el mercado (momios, libro de Kalshi,
 *    tasa base…, R-083);
 *  - **gente**: el precio del pozo al cierre, con todas las apuestas dentro.
 *
 * La métrica es el Brier multiclase, Σ(p−y)²: 0 es perfecto, 1−1/K es parejo.
 * La comparación es **pareada** —la diferencia mercado por mercado— y se da con
 * su IC95%. Con n < 30 no se concluye nada, ni a favor ni en contra (CLAUDE.md).
 */

export interface Muestra {
  id: string;
  familia: string;
  apuestas: number;
  /** El prior del director: probabilidad por opción, suma 1. */
  director: Record<string, number>;
  /** El precio del pozo al cierre. */
  gente: Record<string, number>;
  ganador: string;
}

export type Veredicto = "no_concluye" | "mejor" | "peor" | "indistinguible";

export interface Comparacion {
  /** Diferencia media de Brier (a − b): negativa = `a` acierta más. */
  media: number;
  ic95: [number, number];
  veredicto: Veredicto;
}

export interface Calificacion {
  n: number;
  /** Cuántos nacieron con un prior que no era parejo: sin ellos no hay nada que medir. */
  conPrior: number;
  /** Cuántos tuvieron apuestas: sin ellas la gente no dijo nada. */
  conApuestas: number;
  brier: { parejo: number; director: number; gente: number };
  /** El director contra el parejo: ¿su prior aporta algo? */
  directorVsParejo: Comparacion;
  /** La gente contra el director: ¿apostar mejora el precio con que nació? */
  genteVsDirector: Comparacion;
  /** Probabilidad que dio el director al ganador, por tramos: calibración gruesa. */
  tramos: { desde: number; hasta: number; n: number; predicho: number; observado: number }[];
}

export const N_MINIMO = 30;

export function brier(p: Record<string, number>, ganador: string): number {
  const ids = new Set([...Object.keys(p), ganador]);
  let suma = 0;
  for (const id of ids) suma += ((p[id] ?? 0) - (id === ganador ? 1 : 0)) ** 2;
  return suma;
}

function parejo(p: Record<string, number>): Record<string, number> {
  const ids = Object.keys(p);
  return Object.fromEntries(ids.map((id) => [id, 1 / ids.length]));
}

function comparar(diferencias: number[]): Comparacion {
  const n = diferencias.length;
  const media = n > 0 ? diferencias.reduce((s, d) => s + d, 0) / n : 0;
  const varianza = n > 1 ? diferencias.reduce((s, d) => s + (d - media) ** 2, 0) / (n - 1) : 0;
  const margen = n > 1 ? 1.96 * Math.sqrt(varianza / n) : Number.POSITIVE_INFINITY;
  const ic95: [number, number] = [media - margen, media + margen];
  const veredicto: Veredicto =
    n < N_MINIMO ? "no_concluye" : ic95[1] < 0 ? "mejor" : ic95[0] > 0 ? "peor" : "indistinguible";
  return { media, ic95, veredicto };
}

const TRAMOS = [0, 0.2, 0.4, 0.6, 0.8, 1.0001];

export function calificar(muestras: readonly Muestra[]): Calificacion {
  const bp = muestras.map((m) => brier(parejo(m.director), m.ganador));
  const bd = muestras.map((m) => brier(m.director, m.ganador));
  const bg = muestras.map((m) => brier(m.gente, m.ganador));
  const media = (xs: number[]) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : 0);

  // calibración: cada opción de cada mercado es un pronóstico «p de que sea esta»
  const tramos = TRAMOS.slice(0, -1).map((desde, i) => ({ desde, hasta: Math.min(1, TRAMOS[i + 1]), n: 0, predicho: 0, observado: 0 }));
  for (const m of muestras) {
    for (const [id, p] of Object.entries(m.director)) {
      const t = tramos.find((x, i) => p >= x.desde && p < TRAMOS[i + 1]);
      if (!t) continue;
      t.n += 1;
      t.predicho += p;
      t.observado += id === m.ganador ? 1 : 0;
    }
  }
  for (const t of tramos) {
    if (t.n > 0) {
      t.predicho /= t.n;
      t.observado /= t.n;
    }
  }

  const conPrior = muestras.filter((m) => {
    const k = Object.keys(m.director).length;
    return Object.values(m.director).some((p) => Math.abs(p - 1 / k) > 0.01);
  }).length;
  return {
    n: muestras.length,
    conPrior,
    conApuestas: muestras.filter((m) => m.apuestas > 0).length,
    brier: { parejo: media(bp), director: media(bd), gente: media(bg) },
    directorVsParejo: comparar(bd.map((d, i) => d - bp[i])),
    genteVsDirector: comparar(bg.map((g, i) => g - bd[i])),
    tramos: tramos.filter((t) => t.n > 0),
  };
}

/** Por familia y en total. Una familia sola rara vez llega a n = 30; el total sí antes. */
export function backtest(muestras: readonly Muestra[]): { total: Calificacion; porFamilia: Record<string, Calificacion> } {
  const grupos = new Map<string, Muestra[]>();
  for (const m of muestras) grupos.set(m.familia, [...(grupos.get(m.familia) ?? []), m]);
  return {
    total: calificar(muestras),
    porFamilia: Object.fromEntries([...grupos].map(([f, ms]) => [f, calificar(ms)])),
  };
}
