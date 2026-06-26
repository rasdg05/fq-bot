# -*- coding: utf-8 -*-
"""
validate_metric_flow — valida CUALQUIER medidor de posicionamiento/flujo con DSR.

Generaliza validate_oi_flow a cualquier columna del dataset `metrics` de Binance Vision
(GRATIS, ya lo baja fetch_binance_vision_oi):
  toptrader_ls — long/short de POSICIONES de top-traders   -> regla `directional` (smart money con el trade)
  taker_ls     — taker buy/sell volume ratio               -> regla `directional` (flujo agresivo con el trade)
  global_ls    — long/short de CUENTAS global (retail)     -> regla `contrarian`  (fade a la multitud)
  oi_usd       — open interest                              -> regla `rising`      (posicionamiento nuevo)

Por cada evento del cube computa la confirmación CAUSAL (sólo metric antes de la entrada)
según la regla, compara el R de CONFIRMADOS vs NO y corre el Deflated Sharpe. MISMA
disciplina que CVD/OI: no se cablea nada sin pasar el DSR (mata el espejismo de muestra chica).

Uso:
  python tools/validate_metric_flow.py --cube cosecha_cubes/tp_cube_BTC_USDT.parquet \
      --metric data/oi_hist_BTCUSDT.parquet --col taker_ls --rule directional --thr 0.05
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validation_gate as vg  # noqa: E402


def metric_features(df, col, win=24):
    """Estado del medidor en las últimas `win` barras: last/mean/slope/change_pct."""
    d = df.sort_values("ts")
    v = pd.to_numeric(d[col], errors="coerce").to_numpy(float)
    v = v[~np.isnan(v)]
    w = min(int(win), len(v))
    if w < 2:
        last = float(v[-1]) if len(v) else float("nan")
        return {"last": last, "mean": last, "slope": 0.0, "change_pct": 0.0, "n": int(len(v))}
    seg = v[-w:]
    slope = float(np.polyfit(np.arange(w), seg, 1)[0])
    chg = float((seg[-1] - seg[0]) / seg[0]) if seg[0] else 0.0
    return {"last": float(seg[-1]), "mean": float(seg.mean()), "slope": slope,
            "change_pct": chg, "n": int(len(v))}


def metric_confirms(feat, direction, rule="directional", thr=0.0):
    """¿El medidor confirma la dirección del trade? Tres hipótesis a validar con DSR:
      rising      — el medidor SUBIENDO (convicción/posicionamiento nuevo), direction-agnóstico.
      directional — ratio>1 = alcista; confirma LONG si mean>1+thr, SHORT si mean<1-thr.
      contrarian  — fade a la multitud; confirma LONG si mean<1-thr, SHORT si mean>1+thr.
    """
    m = feat["mean"]
    is_long = direction in (1, "long", "buy")
    if rule == "rising":
        return feat["change_pct"] > thr
    if rule == "directional":
        return (m > 1.0 + thr) if is_long else (m < 1.0 - thr)
    if rule == "contrarian":
        return (m < 1.0 - thr) if is_long else (m > 1.0 + thr)
    raise ValueError("regla desconocida: %s" % rule)


def evaluate(cube_path, metric_path, col, rule="directional", thr=0.0,
             tp="tp4", horizon=576, win=24, lookback=48):
    cube = pd.read_parquet(cube_path)
    cube["tp"] = cube["tp"].astype(str)
    cube["horizon"] = cube["horizon"].astype(int)
    e = cube[(cube.tp == tp) & (cube.horizon == horizon)].drop_duplicates("entry_index").copy()
    e["ts"] = pd.to_datetime(e["entry_ts"]).values.astype("datetime64[ms]").astype("int64")
    m = pd.read_parquet(metric_path).sort_values("ts").reset_index(drop=True)
    if col not in m.columns:
        raise SystemExit("columna '%s' no está en %s (tiene: %s)" % (col, metric_path, list(m.columns)))
    m = m.dropna(subset=[col])
    m_ts = m.ts.values
    lo, hi = m.ts.min(), m.ts.max()
    ev = e[(e.ts >= lo + lookback * 300000) & (e.ts <= hi)].sort_values("ts")
    rows = []
    for _, r in ev.iterrows():
        j = int(np.searchsorted(m_ts, r.ts))            # CAUSAL: barras con ts < entrada
        w = m.iloc[max(0, j - lookback):j]
        if len(w) < win:
            continue
        f = metric_features(w, col, win=win)
        rows.append({"pnl_r": float(r.pnl_r),
                     "confirma": bool(metric_confirms(f, int(r.direction), rule=rule, thr=thr)),
                     "dir": int(r.direction)})
    return pd.DataFrame(rows)


def report(df, col, rule, thr, n_trials=16):
    n = len(df)
    print("=== %s (%s, thr=%.3f) vs cube (dato REAL) ===" % (col, rule, thr))
    print("eventos con metric real cubriendo la entrada: %d" % n)
    if n < 20:
        print("muestra insuficiente (<20) — más historia.")
        return
    cf = df[df.confirma]["pnl_r"]
    nf = df[~df.confirma]["pnl_r"]
    base = df["pnl_r"]
    print("  baseline      n=%-4d exp=%+.3fR  WR=%.0f%%" % (len(base), base.mean(), (base > 0).mean() * 100))
    print("  confirmado    n=%-4d exp=%+.3fR  WR=%.0f%%" % (
        len(cf), cf.mean() if len(cf) else float("nan"), (cf > 0).mean() * 100 if len(cf) else float("nan")))
    print("  no-confirmado n=%-4d exp=%+.3fR  WR=%.0f%%" % (
        len(nf), nf.mean() if len(nf) else float("nan"), (nf > 0).mean() * 100 if len(nf) else float("nan")))
    if len(cf) >= 20:
        srs = [base.mean() / base.std(ddof=1) if base.std(ddof=1) else 0.0,
               cf.mean() / cf.std(ddof=1) if cf.std(ddof=1) else 0.0]
        sr_std = float(np.std(srs, ddof=0)) or 0.02
        d = vg.deflated_sharpe_ratio(cf.values, n_trials=n_trials, sr_trials_std=max(sr_std, 0.01))
        uplift = cf.mean() - base.mean()
        print("\n  uplift confirmado vs baseline: %+.3fR" % uplift)
        print("  DSR(n_trials=%d) = %.3f  -> %s" % (
            n_trials, d["dsr"], "EDGE REAL ✓ (candidato a cablear)"
            if (d["significant"] and uplift > 0) else "NO pasa / no mejora — al cementerio"))
    else:
        print("\n  pocos confirmados (<20) para DSR.")


def main(argv):
    p = argparse.ArgumentParser(description="Valida un medidor de flujo/posicionamiento (real + DSR).")
    p.add_argument("--cube", required=True)
    p.add_argument("--metric", required=True, help="oi_hist_<SYM>.parquet (dataset metrics)")
    p.add_argument("--col", required=True, help="toptrader_ls | taker_ls | global_ls | oi_usd")
    p.add_argument("--rule", default="directional", choices=["rising", "directional", "contrarian"])
    p.add_argument("--thr", type=float, default=0.0)
    p.add_argument("--tp", default="tp4")
    p.add_argument("--horizon", type=int, default=576)
    p.add_argument("--n-trials", type=int, default=16)
    a = p.parse_args(argv)
    df = evaluate(a.cube, a.metric, a.col, rule=a.rule, thr=a.thr, tp=a.tp, horizon=a.horizon)
    report(df, a.col, a.rule, a.thr, n_trials=a.n_trials)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
