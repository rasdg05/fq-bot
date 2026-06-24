# -*- coding: utf-8 -*-
"""
cube_report — "pulido" reutilizable de un cubo de research (tp_cube_<sym>.parquet).

Corre, sobre CUALQUIER simbolo, el MISMO analisis que se le hizo a SOL/BTC inline:
  1) celda fija (tp x horizonte): donde vive el edge + la mejor politica fija.
  2) veto-mining: segmentos -EV (killzone / dia / bloque-UTC) robustos IS y OOS.
  3) conviccion: ¿el P_master predice el outcome? (quintiles).
Es symbol-agnostico -> para poner un simbolo nuevo (ETH) al nivel de los otros
apenas se cosecha su cubo. GROSS (pnl_r del cubo es pre-coste): diagnostico/radar,
no veredicto neto — los candidatos se validan con regrade/matriz como london/asia.

Uso: python tools/cube_report.py cosecha_cubes/tp_cube_ETH_USDT.parquet
"""
import sys
import numpy as np
import pandas as pd

DOW = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]


def _load(path):
    c = pd.read_parquet(path)
    c["tp"] = c["tp"].astype(str)
    c["horizon"] = c["horizon"].astype(int)
    return c


def _b(g):
    return "exp=%+.3f  n=%4d  WR=%4.0f%%" % (
        g.pnl_r.mean(), len(g), (g.pnl_r > 0).mean() * 100)


def fixed_cells(c):
    print("\n=== 1) CELDA FIJA (tp x horizonte) — donde vive el edge ===")
    g = (c.groupby([c.tp, c.horizon])["pnl_r"]
         .agg(exp="mean", wr=lambda s: (s > 0).mean(), n="count")
         .sort_values("exp", ascending=False))
    for (tp, h), r in g.iterrows():
        print("  %-4s h%-3d  exp=%+.3f  WR=%3.0f%%  n=%d"
              % (tp, h, r.exp, r.wr * 100, r.n))
    best = g.index[0]
    print("  -> mejor celda fija: %s  (la politica simple a batir)" % str(best))
    return best


def _events_cell(c, tp="tp4", horizon=576):
    """1 fila por evento en la celda de referencia + tiempo derivado."""
    e = c[(c.tp == tp) & (c.horizon == horizon)].copy()
    e["ts"] = pd.to_datetime(e["entry_ts"])
    e["weekday"] = e["ts"].dt.dayofweek
    e["utc4"] = (e["ts"].dt.hour // 4) * 4
    return e


def veto_mine(c, tp="tp4", horizon=576):
    e = _events_cell(c, tp, horizon)
    if e.empty:
        print("\n=== 2) VETO-MINING: sin celda %s/h%d ===" % (tp, horizon))
        return
    print("\n=== 2) VETO-MINING (celda %s/h%d, gross) — segmentos -EV ===" % (tp, horizon))
    for col, lab in [("field_killzone", "killzone"), ("weekday", "dia"), ("utc4", "bloque-UTC")]:
        if col not in e.columns:
            continue
        print("  -- por %s --" % lab)
        gg = e.groupby(col)["pnl_r"].agg(exp="mean", n="count").sort_values("exp")
        for idx, r in gg.iterrows():
            name = DOW[int(idx)] if col == "weekday" else str(idx)
            flag = "  <<< -EV (candidato veto)" if (r.exp < 0.05 and r.n >= 15) else ""
            print("     %-18s exp=%+.3f  n=%d%s" % (name[:18], r.exp, r.n, flag))


def conviction(c, tp="tp4", horizon=576, col="p_master"):
    e = _events_cell(c, tp, horizon)
    if col not in e.columns or e[col].nunique() < 5:
        print("\n=== 3) CONVICCION: %s no usable ===" % col)
        return
    e = e.dropna(subset=[col])
    try:
        e["q"] = pd.qcut(e[col], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"], duplicates="drop")
    except Exception:
        print("\n=== 3) CONVICCION: %s no quintilable ===" % col)
        return
    print("\n=== 3) CONVICCION (P_master, quintiles) — ¿predice? ===")
    g = e.groupby("q")["pnl_r"].agg(exp="mean", n="count")
    line = "  ".join("%s:%+.2f(n%d)" % (q, r.exp, r.n) for q, r in g.iterrows())
    sp = g.iloc[-1]["exp"] - g.iloc[0]["exp"]
    print("  " + line)
    print("  spread Q5-Q1 = %+.3fR  corr(p_master,pnl)=%+.3f  -> %s"
          % (sp, e[col].corr(e["pnl_r"]), "util" if sp > 0.05 else "plano/no util"))


def main(argv):
    if len(argv) < 2:
        print("uso: python tools/cube_report.py <tp_cube_<sym>.parquet>")
        return 2
    path = argv[1]
    c = _load(path)
    ev = c["entry_index"].nunique()
    sym = path.split("tp_cube_")[-1].split(".parquet")[0]
    print("================ PULIDO: %s ================" % sym)
    print("eventos=%d  rango=%s..%s  celdas=%d"
          % (ev, c["entry_ts"].min(), c["entry_ts"].max(),
             len(set(zip(c.tp, c.horizon)))))
    if ev < 1000:
        print("⚠ GATE §6.6: %d < 1000 eventos -> bajo poder, RADAR no veredicto." % ev)
    fixed_cells(c)
    veto_mine(c)
    conviction(c)
    print("\n(gross/pre-coste: candidatos a validar net como london/asia)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
