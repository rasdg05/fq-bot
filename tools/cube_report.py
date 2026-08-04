# -*- coding: utf-8 -*-
"""
cube_report — "pulido" reutilizable de un cubo de research (tp_cube_<sym>.parquet).

Corre, sobre CUALQUIER simbolo, el MISMO analisis que se le hizo a SOL/BTC inline:
  1) celda fija (tp x horizonte): donde vive el edge + la mejor politica fija.
  2) veto-mining: segmentos -EV (killzone / dia / bloque-UTC) robustos IS y OOS.
  3) conviccion: ¿el P_master predice el outcome? (quintiles).
Es symbol-agnostico -> para poner un simbolo nuevo (ETH) al nivel de los otros
apenas se cosecha su cubo.

E8 — EL BRUTO YA NO SALE SOLO. El `pnl_r` del cubo es pre-coste, y la diferencia
no es un detalle: el mismo motor da +0.224R bruto sobre 7 anos y -0.510R vivo con
fees. El coste en R es ~ (2*fee + 2*slip) / (distancia_al_stop / precio), o sea
que con stops del 0.5% del precio se come ~0.25R POR TRADE. Por eso este informe
aplica `bt_engine.CostModel` a las etiquetas y **ninguna cifra bruta se imprime
sin su neta al lado** (`cell_stats` levanta si falta `net_pnl_r`). Backtest y
forward hablan por fin en las mismas unidades.

Sigue siendo una COTA SUPERIOR, no una simulacion: la etiqueta triple-barrera
asume fill perfecto en el precio de la barrera y no modela cola ni rechazo, y ya
se midio que el fill importa muchisimo (los maker rapidos pierden el 80% del R).

Uso: python tools/cube_report.py cosecha_cubes/tp_cube_ETH_USDT.parquet
     python tools/cube_report.py cosecha_cubes/            # pool de simbolos
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))           # raiz del repo (bt_engine)
sys.path.insert(0, _HERE)                            # tools/ (validation_gate)
from bt_engine import CostModel, simulate            # noqa: E402
from validation_gate import _sharpe, deflated_from_trials   # noqa: E402

DOW = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]

# Velas de 5m: el TF del research (FQ_MOTOR_PAPER_TF). Solo entra en el prorrateo
# del funding, pero un valor mal puesto ahi falsea el coste de las vidas largas.
BAR_MINUTES = 5.0
MIN_N = 30


class GrossWithoutNetError(RuntimeError):
    """Se intento resumir una celda del cube sin haberle aplicado costes.

    Es la invariante de E8. El +0.224R bruto circulo durante meses como si fuera
    el edge; el neto de la misma cosecha esta en cero. Que el bruto no pueda
    imprimirse solo no es cosmetica: es lo que impide que vuelva a circular.
    """


def _load(path):
    c = pd.read_parquet(path)
    c["tp"] = c["tp"].astype(str)
    c["horizon"] = c["horizon"].astype(int)
    return c


def load_pool(path):
    """Un parquet, un directorio o un glob -> cubo unico con columna `symbol`."""
    if os.path.isdir(path):
        paths = sorted(glob.glob(os.path.join(path, "tp_cube_*.parquet")))
    else:
        paths = sorted(glob.glob(path)) or [path]
    out = []
    for p in paths:
        c = _load(p)
        if "symbol" not in c.columns:
            c["symbol"] = os.path.basename(p).split("tp_cube_")[-1].replace(
                ".parquet", "")
        out.append(c)
    return pd.concat(out, ignore_index=True)


def cell_events(c, tp="tp4", horizon=576):
    """1 fila por senal canonica de la celda (dedup por symbol+entry_ts)."""
    e = c[(c.tp == tp) & (c.horizon == int(horizon))].copy()
    keys = [k for k in ("symbol", "entry_ts") if k in e.columns]
    return e.drop_duplicates(subset=keys).sort_values("entry_ts").reset_index(drop=True)


def apply_costs(events, cost=None, bar_minutes=BAR_MINUTES):
    """Anade `net_pnl_r` a una celda del cube via bt_engine.simulate.

    Reutiliza el MISMO motor de costes que el backtest y el paper -> las tres
    superficies cuentan fees, slippage y funding con una sola definicion. El
    equity es enorme y el risk_frac diminuto a proposito: `net_pnl_r` es
    net_pnl/risk_amount y ambos escalan con el equity, asi que la R neta por
    trade sale invariante al capital (esto mide expectancy, no una curva).
    """
    ev = events.copy()
    ev["direction"] = ev["direction"].astype(int)
    res = simulate(ev, equity0=1e9, risk_frac=1e-6, bar_minutes=bar_minutes,
                   cost=cost or CostModel(), stop_on_ruin=False)
    return res["trades"]


def cell_stats(g):
    """(exp_bruta, exp_neta, n, WR). Levanta si nadie aplico costes."""
    if "net_pnl_r" not in getattr(g, "columns", []):
        raise GrossWithoutNetError(
            "celda sin net_pnl_r: pasa por apply_costs() antes de resumir. "
            "El bruto del cube no describe ninguna operacion realizable.")
    return (float(g.pnl_r.mean()), float(g.net_pnl_r.mean()), len(g),
            float((g.pnl_r > 0).mean() * 100))


def _b(g):
    gross, net, n, wr = cell_stats(g)
    return "exp=%+.3f -> NET %+.3f  n=%4d  WR=%4.0f%%" % (gross, net, n, wr)


def fixed_cells(c):
    print("\n=== 1) CELDA FIJA (tp x horizonte) — donde vive el edge ===")
    cell_stats(c)                      # invariante: sin netos no se resume nada
    g = (c.groupby([c.tp, c.horizon])
         .apply(lambda d: pd.Series({
             "exp": d.pnl_r.mean(), "net": d.net_pnl_r.mean(),
             "wr": (d.pnl_r > 0).mean(), "n": len(d)}), include_groups=False)
         .sort_values("net", ascending=False))
    for (tp, h), r in g.iterrows():
        print("  %-4s h%-3d  exp=%+.3f -> NET %+.3f  WR=%3.0f%%  n=%d%s"
              % (tp, h, r.exp, r.net, r.wr * 100, r.n,
                 "" if r.net > 0 else "   <- no sobrevive costes"))
    best = g.index[0]
    print("  -> mejor celda fija POR NETO: %s  (la politica simple a batir)"
          % str(best))
    return best


def _events_cell(c, tp="tp4", horizon=576):
    """1 fila por evento en la celda de referencia + tiempo derivado."""
    e = c[(c.tp == tp) & (c.horizon == horizon)].copy()
    e["ts"] = pd.to_datetime(e["entry_ts"])
    e["weekday"] = e["ts"].dt.dayofweek
    e["utc4"] = (e["ts"].dt.hour // 4) * 4
    return e


def veto_mine(c, tp="tp4", horizon=576):
    cell_stats(c)                      # invariante: sin netos no se resume nada
    e = _events_cell(c, tp, horizon)
    if e.empty:
        print("\n=== 2) VETO-MINING: sin celda %s/h%d ===" % (tp, horizon))
        return
    print("\n=== 2) VETO-MINING (celda %s/h%d, NETO) — segmentos -EV ===" % (tp, horizon))
    for col, lab in [("field_killzone", "killzone"), ("weekday", "dia"), ("utc4", "bloque-UTC")]:
        if col not in e.columns:
            continue
        print("  -- por %s --" % lab)
        gg = (e.groupby(col)
              .apply(lambda d: pd.Series({"exp": d.pnl_r.mean(),
                                          "net": d.net_pnl_r.mean(),
                                          "n": len(d)}), include_groups=False)
              .sort_values("net"))
        for idx, r in gg.iterrows():
            name = DOW[int(idx)] if col == "weekday" else str(idx)
            flag = "  <<< -EV NETO (candidato veto)" if (r.net < 0 and r.n >= 15) else ""
            print("     %-18s exp=%+.3f -> NET %+.3f  n=%d%s"
                  % (name[:18], r.exp, r.net, r.n, flag))


def conviction(c, tp="tp4", horizon=576, col="p_master"):
    cell_stats(c)                      # invariante: sin netos no se resume nada
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
    g = e.groupby("q", observed=True).apply(
        lambda d: pd.Series({"exp": d.pnl_r.mean(), "net": d.net_pnl_r.mean(),
                             "n": len(d)}), include_groups=False)
    print("  bruto: " + "  ".join("%s:%+.2f(n%d)" % (q, r.exp, r.n)
                                  for q, r in g.iterrows()))
    print("  NETO : " + "  ".join("%s:%+.2f" % (q, r.net) for q, r in g.iterrows()))
    sp = g.iloc[-1]["net"] - g.iloc[0]["net"]
    print("  spread NETO Q5-Q1 = %+.3fR  corr(p_master,net)=%+.3f  -> %s"
          % (sp, e[col].corr(e["net_pnl_r"]), "util" if sp > 0.05 else "plano/no util"))


def _boot_ci(x, reps=2000, seed=7):
    """IC95% bootstrap de la media + P(>0). Sin scipy, como el gate."""
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    m = np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(reps)])
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)), float((m > 0).mean())


def _subsets(t):
    """Los cortes que se inspeccionan. Contarlos ES el n_trials del DSR: mirar
    30 subconjuntos y quedarse con el mejor infla el Sharpe por construccion.
    """
    subs = {}
    for s, d in t.groupby("symbol"):
        subs["simbolo:%s" % s] = d
    for s, d in t.groupby(t.entry_ts.dt.year):
        subs["ano:%s" % s] = d
    for s, d in t.groupby("direction"):
        subs["lado:%s" % ("long" if int(s) > 0 else "short")] = d
    for s, d in t.groupby("stop_q", observed=True):
        subs["stop_%s" % s] = d
    return subs


def net_bridge(t, min_n=MIN_N):
    """4) EL PUENTE BRUTO->NETO (E8) — ¿cuanto del edge sobrevive al coste?

    Y despues: ¿se concentra el neto en algun subconjunto que SI aguante? La
    pregunta tiene trampa y hay que responderla con la trampa a la vista: mirar
    30 cortes y quedarse con el mejor es exactamente lo que el DSR deflacta, asi
    que aqui cada candidato pasa por el gate con n_trials = cortes inspeccionados.
    """
    gross, net, n, wr = cell_stats(t)
    lo, hi, p = _boot_ci(t.net_pnl_r.values)
    print("\n=== 4) PUENTE BRUTO -> NETO (bt_engine.CostModel) ===")
    print("  n=%d  bruto %+.4fR  ->  NETO %+.4fR   (coste %+.4fR por trade)"
          % (n, gross, net, net - gross))
    print("  IC95%% del neto [%+.4f, %+.4f]  P(E[R]>0)=%.3f" % (lo, hi, p))
    surv = int((t.net_pnl_r > 0).sum())
    print("  senales que sobreviven costes (neto>0): %d/%d = %.1f%%"
          % (surv, n, 100.0 * surv / n))
    stop_pct = ((t.entry_price - t.stop_price).abs() / t.entry_price * 100).median()
    print("  stop mediano = %.3f%% del precio -> el coste fijo pesa ~%.3fR"
          % (stop_pct, abs(net - gross)))

    print("\n  -- ¿se concentra el neto en algun subconjunto? --")
    t = t.copy()
    t["entry_ts"] = pd.to_datetime(t["entry_ts"])
    # Quintil de distancia de stop: es el corte que MAS manda sobre el coste en R
    # (coste_R ~ fee/(stop/precio)) y ademas se conoce ANTES de entrar, asi que a
    # diferencia de "el simbolo que mas cargo" es una regla pre-registrable.
    sf = (t.entry_price - t.stop_price).abs() / t.entry_price
    if sf.nunique() >= 5:
        codes = pd.qcut(sf, 5, labels=False, duplicates="drop")
        t["stop_q"] = ["Q%d" % (int(v) + 1) for v in codes]
    else:
        t["stop_q"] = "Qunico"
    subs = _subsets(t)
    sharpes = {k: _sharpe(d.net_pnl_r.values) for k, d in subs.items()}
    ranked = sorted(subs, key=lambda k: -sharpes[k])
    print("  (n_trials=%d cortes inspeccionados; el DSR los deflacta)" % len(subs))
    print("  %-18s %6s %9s %9s %20s %7s" % ("corte", "n", "bruto", "NETO", "IC95% neto", "DSR"))
    any_pass = False
    for k in ranked[:6]:
        d = subs[k]
        if len(d) < min_n:
            continue
        l2, h2, _ = _boot_ci(d.net_pnl_r.values)
        dsr = deflated_from_trials(d.net_pnl_r.values, list(sharpes.values()))
        any_pass = any_pass or (dsr["significant"] and l2 > 0)
        print("  %-18s %6d %+9.4f %+9.4f  [%+7.4f,%+7.4f] %7.3f%s"
              % (k, len(d), d.pnl_r.mean(), d.net_pnl_r.mean(), l2, h2,
                 dsr["dsr"], "" if dsr["significant"] else "  NO pasa"))
    if not any_pass:
        print("  >> NINGUN subconjunto clarea el gate (DSR>0.95 + IC95%>0).")
        print("     El mejor corte de la lista es el ganador de un concurso de")
        print("     %d, medido despues de ver los resultados. No es una" % len(subs))
        print("     estrategia: es el maximo del ruido.")
    print("\n  COTA SUPERIOR, no simulacion: la etiqueta asume fill perfecto en el")
    print("  precio de la barrera. Sin modelo de cola ni de rechazo, y ya se midio")
    print("  que el fill se lleva el 80% del R en los maker rapidos. Lo realizable")
    print("  esta POR DEBAJO de esta tabla, nunca por encima.")
    return net


def main(argv):
    ap = argparse.ArgumentParser(description="Pulido de un cubo de research")
    ap.add_argument("path", nargs="?", help="parquet, glob o directorio de cubos")
    ap.add_argument("--tp", default="tp4")
    ap.add_argument("--horizon", type=int, default=576)
    ap.add_argument("--bar-minutes", type=float, default=BAR_MINUTES)
    a = ap.parse_args(argv[1:])
    if not a.path:
        print("uso: python tools/cube_report.py <tp_cube_<sym>.parquet | dir/>")
        return 2
    path = a.path
    c = load_pool(path)
    ev = len(c.drop_duplicates(subset=["symbol", "entry_ts"]))
    sym = ("POOL(%d simbolos)" % c.symbol.nunique() if c.symbol.nunique() > 1
           else str(c.symbol.iloc[0]))
    print("================ PULIDO: %s ================" % sym)
    print("eventos=%d  rango=%s..%s  celdas=%d"
          % (ev, c["entry_ts"].min(), c["entry_ts"].max(),
             len(set(zip(c.tp, c.horizon)))))
    if ev < 1000:
        print("⚠ GATE §6.6: %d < 1000 eventos -> bajo poder, RADAR no veredicto." % ev)
    c = apply_costs(c, bar_minutes=a.bar_minutes)
    fixed_cells(c)
    veto_mine(c, tp=a.tp, horizon=a.horizon)
    conviction(c, tp=a.tp, horizon=a.horizon)
    net_bridge(cell_events(c, tp=a.tp, horizon=a.horizon))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
