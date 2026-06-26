# -*- coding: utf-8 -*-
"""
validate_oi_flow — ¿la confirmación de OI (posicionamiento) mejora el edge?

Espejo de validate_cvd_signed_flow, pero para OI. Cierra el loop SIN esperar forward
y SIN comprar data: usa el OI REAL histórico (fetch_binance_vision_oi, gratis, desde
~2020-09) + el cube del motor + el gate DSR.

Para cada evento del cube computa, CAUSAL (sólo OI antes de la entrada), si el OI venía
SUBIENDO (oi_features/oi_confirms = posicionamiento nuevo entrando). Compara el R de los
CONFIRMADOS vs los NO-confirmados y corre el Deflated Sharpe -> ¿el OI es edge real o
ruido tras multiple-testing? MISMA disciplina que el CVD: no se cablea nada hasta que
el OI-confirmado BATA al baseline Y sobreviva el DSR.

Pipeline:
  1) python tools/fetch_binance_vision_oi.py BTCUSDT --start 2021-01-01 --end 2026-06-26
  2) python tools/validate_oi_flow.py --cube cosecha_cubes/tp_cube_BTC_USDT.parquet \
        --oi data/oi_hist_BTCUSDT.parquet --tp tp4 --horizon 576 --min-change 0.005
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_agg_oi  # noqa: E402
import validation_gate as vg  # noqa: E402


def evaluate(cube_path, oi_path, tp="tp4", horizon=576, win=24, lookback=48, min_change=0.0):
    cube = pd.read_parquet(cube_path)
    cube["tp"] = cube["tp"].astype(str)
    cube["horizon"] = cube["horizon"].astype(int)
    e = cube[(cube.tp == tp) & (cube.horizon == horizon)].drop_duplicates("entry_index").copy()
    # ms epoch robusto a la resolución (pandas 2.x preserva ns/us/ms): forzar ms en numpy
    e["ts"] = pd.to_datetime(e["entry_ts"]).values.astype("datetime64[ms]").astype("int64")
    oi = pd.read_parquet(oi_path).sort_values("ts").reset_index(drop=True)
    lo, hi = oi.ts.min(), oi.ts.max()
    ev = e[(e.ts >= lo + lookback * 300000) & (e.ts <= hi)].sort_values("ts")
    rows = []
    oi_ts = oi.ts.values
    for _, r in ev.iterrows():
        j = int(np.searchsorted(oi_ts, r.ts))           # CAUSAL: barras con ts < entrada
        w = oi.iloc[max(0, j - lookback):j]
        if len(w) < win:
            continue
        f = fetch_agg_oi.oi_features(w, win=win)
        conf = fetch_agg_oi.oi_confirms(f, int(r.direction), min_change=min_change)
        rows.append({"pnl_r": float(r.pnl_r), "confirma": bool(conf),
                     "oi_change_pct": f["oi_change_pct"], "dir": int(r.direction)})
    return pd.DataFrame(rows)


def report(df, min_change, n_trials=16):
    n = len(df)
    print("=== OI (posicionamiento) vs cube (dato REAL, no proxy) · min_change=%.3f ===" % min_change)
    print("eventos con OI real cubriendo la entrada: %d" % n)
    if n < 20:
        print("muestra insuficiente (<20) — bajá MÁS historia (fetch_binance_vision_oi "
              "sobre el rango completo del cube).")
        return
    cf = df[df.confirma]["pnl_r"]
    nf = df[~df.confirma]["pnl_r"]
    base = df["pnl_r"]
    print("  baseline       n=%-4d exp=%+.3fR  WR=%.0f%%" % (len(base), base.mean(), (base > 0).mean() * 100))
    print("  OI-confirmado  n=%-4d exp=%+.3fR  WR=%.0f%%" % (
        len(cf), cf.mean() if len(cf) else float("nan"), (cf > 0).mean() * 100 if len(cf) else float("nan")))
    print("  NO-confirmado  n=%-4d exp=%+.3fR  WR=%.0f%%" % (
        len(nf), nf.mean() if len(nf) else float("nan"), (nf > 0).mean() * 100 if len(nf) else float("nan")))
    if len(cf) >= 20:
        srs = [base.mean() / base.std(ddof=1) if base.std(ddof=1) else 0.0,
               cf.mean() / cf.std(ddof=1) if cf.std(ddof=1) else 0.0]
        sr_std = float(np.std(srs, ddof=0)) or 0.02
        d = vg.deflated_sharpe_ratio(cf.values, n_trials=n_trials, sr_trials_std=max(sr_std, 0.01))
        uplift = cf.mean() - base.mean()
        print("\n  uplift OI-confirmado vs baseline: %+.3fR" % uplift)
        print("  DSR(confirmado, n_trials=%d) = %.3f  -> %s" % (
            n_trials, d["dsr"], "EDGE REAL ✓ (candidato a cablear)"
            if (d["significant"] and uplift > 0) else "NO pasa / no mejora — NO cablear"))
    else:
        print("\n  pocos confirmados (<20) para DSR — subí historia o bajá min_change.")


def main(argv):
    p = argparse.ArgumentParser(description="Valida si el OI mejora el edge (real + DSR).")
    p.add_argument("--cube", required=True)
    p.add_argument("--oi", required=True, help="oi_hist_<SYM>.parquet de fetch_binance_vision_oi")
    p.add_argument("--tp", default="tp4")
    p.add_argument("--horizon", type=int, default=576)
    p.add_argument("--min-change", type=float, default=0.0)
    p.add_argument("--n-trials", type=int, default=16)
    a = p.parse_args(argv)
    df = evaluate(a.cube, a.oi, tp=a.tp, horizon=a.horizon, min_change=a.min_change)
    report(df, a.min_change, n_trials=a.n_trials)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
