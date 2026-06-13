# -*- coding: utf-8 -*-
"""
================================================================================
  BT QUALITY - gate de calidad "VIP oro": aisla el decil superior OOS
  by RasDG_Sol + Claude

  El North Star del proyecto: dejar SOLO senales VIP de oro puro (matar las
  tacticas, quedarse con la crema). Esta pieza toma un SCORE de ranking ya
  validado out-of-sample (la probabilidad OOS del modelo LightGBM, o la
  expectancy del vecindario del retrieval causal) y, por PERCENTIL, recorta el
  top X% de senales. Luego mide la expectancy/WR/total_R/drawdown REALIZADO de
  ese subset VIP frente al universo completo.

  Por que percentil y no umbral fijo de probabilidad: cuando el AUC ronda 0.5 o
  el modelo nunca cruza p=0.5, un umbral fijo (0.5..0.9) selecciona 0 senales y
  el reporte queda vacio. El percentil SIEMPRE aisla el top relativo, asi se ve
  si el ranking ordena bien aunque la calibracion absoluta sea pobre.

  HONESTIDAD OOS: el score y el pnl_r deben venir del walk-forward (oof del
  modelo / retrieval causal). Aqui solo se rebana y se mide; no se ajusta nada.
  El test de placebo (score barajado) debe colapsar el edge -> demuestra que el
  filtro ordena por senal real y no por azar.

  Drawdown en R: el subset VIP no es una serie de equity con compounding sino
  una secuencia de pnl_r; el drawdown se mide ADITIVO en R (suma acumulada vs su
  pico). Asi el riesgo del subset es comparable entre cortes sin depender del
  sizing.

  Pieza pura: arrays in, DataFrame out. Sin I/O, sin red.
================================================================================
"""
import logging

import numpy as np
import pandas as pd

log = logging.getLogger("bt_quality")


def max_drawdown_r(pnl_r):
    """Maximo drawdown ADITIVO en R de una secuencia de pnl_r (en orden).

    Construye la equity acumulada en R (0 -> cumsum) y devuelve el peor
    (equity - pico) <= 0. 0.0 si nunca hay retroceso o muestra vacia.
    """
    p = np.asarray(pnl_r, dtype="float64")
    p = p[np.isfinite(p)]
    if len(p) == 0:
        return 0.0
    eq = np.concatenate([[0.0], np.cumsum(p)])
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    return float(dd.min())


def subset_stats(pnl_r):
    """Estadisticos de un subset de senales a partir de su pnl_r realizado.

    Devuelve n, wr, expectancy_r, total_r, max_dd_r y calmar_r
    (= total_r / |max_dd_r|; inf si no hubo drawdown). nan-safe para subset vacio.
    """
    p = np.asarray(pnl_r, dtype="float64")
    p = p[np.isfinite(p)]
    if len(p) == 0:
        return {"n": 0, "wr": np.nan, "expectancy_r": np.nan, "total_r": np.nan,
                "max_dd_r": np.nan, "calmar_r": np.nan}
    total = float(p.sum())
    mdd = max_drawdown_r(p)
    calmar_r = float("inf") if mdd == 0 else float(total / abs(mdd))
    return {
        "n": int(len(p)),
        "wr": float((p > 0).mean()),
        "expectancy_r": float(p.mean()),
        "total_r": total,
        "max_dd_r": mdd,
        "calmar_r": calmar_r,
    }


def quality_gate(scores, pnl_r, quantiles=(0.5, 0.75, 0.9, 0.95)):
    """Rebana el top (1-q) de senales por `scores` y mide su pnl_r realizado.

    scores : senal de ranking (mayor = mejor). Prob OOS del modelo o expectancy
             del vecindario del retrieval. Filas con score/pnl_r no finito se
             descartan emparejadas.
    pnl_r  : desenlace realizado (en R) de cada senal, alineado con scores.
    quantiles: cortes; q=0.9 => top 10%. Se reportan en orden creciente de q
             (subsets cada vez mas selectivos).

    Devuelve un DataFrame: fila 'base' (todas) + una fila por corte con
    subset='top{pct}%', su umbral de score y los stats de subset_stats. El edge
    del gate = expectancy_r(top) - expectancy_r(base).
    """
    s = np.asarray(scores, dtype="float64")
    p = np.asarray(pnl_r, dtype="float64")
    if len(s) != len(p):
        raise ValueError("scores y pnl_r deben tener la misma longitud")
    m = np.isfinite(s) & np.isfinite(p)
    s, p = s[m], p[m]

    base = subset_stats(p)
    base_exp = base["expectancy_r"]
    rows = [{"subset": "base", "threshold": np.nan, "edge_vs_base_r": 0.0, **base}]
    if len(s) == 0:
        return pd.DataFrame(rows)

    for q in quantiles:
        thr = float(np.quantile(s, q))
        sel = p[s >= thr]
        st = subset_stats(sel)
        pct = int(round((1.0 - q) * 100))
        edge = (st["expectancy_r"] - base_exp) if (
            st["n"] and np.isfinite(base_exp)) else np.nan
        rows.append({"subset": f"top{pct}%", "threshold": thr,
                     "edge_vs_base_r": edge, **st})
    return pd.DataFrame(rows)


def format_gate(grid, title="VIP gate"):
    """Render legible de la tabla de quality_gate para CLI/logs."""
    def f(v):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "n/a" if v is None or np.isnan(v) else ("inf" if v > 0 else "-inf")
        return f"{v:.4f}" if isinstance(v, float) else str(v)
    lines = [f"  [{title}]",
             f"  {'subset':<8} {'n':>6} {'wr':>6} {'exp_r':>8} {'total_r':>9} "
             f"{'max_dd_r':>9} {'calmar_r':>9} {'edge':>8}"]
    for _, r in grid.iterrows():
        lines.append(
            f"  {str(r['subset']):<8} {int(r['n']):>6} {f(r['wr']):>6} "
            f"{f(r['expectancy_r']):>8} {f(r['total_r']):>9} {f(r['max_dd_r']):>9} "
            f"{f(r['calmar_r']):>9} {f(r['edge_vs_base_r']):>8}")
    return "\n".join(lines)


def segment_expectancy(df, by, min_n=10, pnl_col="pnl_r"):
    """Edge CONDICIONAL por segmento: agrupa trades por la columna `by` y mide
    subset_stats por valor (n, wr, expectancy_r, total_r, max_dd_r).

    Es el cazador de 'fractales' LEGIBLE: en que killzone / bloque horario /
    tipo de nodo / direccion el sistema es consistentemente rentable, en una
    tabla que un humano puede explotar y replicar.

    HONESTIDAD: esto es un RADAR, no una prueba. Con muchos cortes SIEMPRE
    aparece un grupo bueno por azar (multiple comparisons); min_n marca
    ok_n=False en grupos chicos y el segmento se explota SOLO tras confirmarse
    OOS/forward (mismo estandar que la poda). Ordena ok_n primero y por
    expectancy_r desc. NaN del segmento -> '(nan)'.
    """
    cols = [by, "n", "wr", "expectancy_r", "total_r", "max_dd_r", "ok_n"]
    if df is None or len(df) == 0 or by not in df.columns:
        return pd.DataFrame(columns=cols)
    key = df[by].astype("object").where(df[by].notna(), "(nan)").astype(str)
    rows = []
    for val, sub in df.groupby(key, sort=False):
        st = subset_stats(sub[pnl_col]) if pnl_col in sub.columns else subset_stats([])
        rows.append({by: val, "n": st["n"], "wr": st["wr"],
                     "expectancy_r": st["expectancy_r"], "total_r": st["total_r"],
                     "max_dd_r": st["max_dd_r"], "ok_n": bool(st["n"] >= min_n)})
    out = pd.DataFrame(rows, columns=cols)
    return out.sort_values(["ok_n", "expectancy_r"],
                           ascending=[False, False]).reset_index(drop=True)
