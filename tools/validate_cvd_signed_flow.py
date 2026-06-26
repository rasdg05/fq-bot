# -*- coding: utf-8 -*-
"""
validate_cvd_signed_flow — ¿la confirmación de order-flow FIRMADO mejora el edge?

Cierra el loop del research SIN esperar forward y SIN comprar data: usa el CVD REAL
histórico (fetch_binance_vision_cvd, gratis) + el cube del motor + el gate DSR.

Para cada evento del cube computa, CAUSAL (sólo CVD antes de la entrada), si el
order-flow firmado CONFIRMA la dirección del setup (cvd_features/confirms_direction).
Compara el R de los CONFIRMADOS vs los NO-confirmados, y corre el Deflated Sharpe
sobre la diferencia -> ¿el filtro CVD es edge real o ruido tras multiple-testing?

Pipeline (para correr con historia completa en GitHub-hosted/Hetzner):
  1) python tools/fetch_binance_vision_cvd.py SOLUSDT --start 2021-06-01 --end 2026-06-19
  2) python tools/validate_cvd_signed_flow.py --cube cosecha_cubes/tp_cube_SOL_USDT.parquet \
        --cvd data/okx/cvd_hist_SOLUSDT.parquet --tp tp4 --horizon 576

Honesto: nada se cablea a la señal hasta que el CVD-confirmado BATA al baseline Y
sobreviva el DSR. Esta es la decisión, medida.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_cvd  # noqa: E402
import validation_gate as vg  # noqa: E402


def evaluate(cube_path, cvd_path, tp="tp4", horizon=576, win=24, lookback=48, imb_min=0.55):
    cube = pd.read_parquet(cube_path)
    cube["tp"] = cube["tp"].astype(str)
    cube["horizon"] = cube["horizon"].astype(int)
    e = cube[(cube.tp == tp) & (cube.horizon == horizon)].drop_duplicates("entry_index").copy()
    # ms epoch ROBUSTO a la resolución (pandas 2.x preserva ns/us/ms): forzar a ms en numpy
    e["ts"] = pd.to_datetime(e["entry_ts"]).values.astype("datetime64[ms]").astype("int64")
    cvd = pd.read_parquet(cvd_path).sort_values("ts").reset_index(drop=True)
    lo, hi = cvd.ts.min(), cvd.ts.max()
    ev = e[(e.ts >= lo + lookback * 300000) & (e.ts <= hi)].sort_values("ts")
    rows = []
    cvd_ts = cvd.ts.values
    for _, r in ev.iterrows():
        j = int(np.searchsorted(cvd_ts, r.ts))          # CAUSAL: barras con ts < entrada
        w = cvd.iloc[max(0, j - lookback):j]
        if len(w) < win:
            continue
        f = fetch_cvd.cvd_features(w, win=win)
        conf = fetch_cvd.confirms_direction(f, int(r.direction), imb_min=imb_min)
        rows.append({"pnl_r": float(r.pnl_r), "confirma": bool(conf),
                     "imbalance": f["imbalance"], "dir": int(r.direction)})
    return pd.DataFrame(rows)


def report(df, n_trials=12):
    n = len(df)
    print("=== CVD signed-flow vs cube (dato REAL, no proxy) ===")
    print("eventos con CVD real cubriendo la entrada: %d" % n)
    if n < 20:
        print("muestra insuficiente (<20) para veredicto DSR — bajá MÁS historia "
              "(fetch_binance_vision_cvd sobre el rango completo del cube, GitHub/Hetzner).")
        return
    cf = df[df.confirma]["pnl_r"]
    nf = df[~df.confirma]["pnl_r"]
    base = df["pnl_r"]
    print("  baseline        n=%-4d exp=%+.3fR  WR=%.0f%%" % (len(base), base.mean(), (base > 0).mean() * 100))
    print("  CVD-confirmado  n=%-4d exp=%+.3fR  WR=%.0f%%" % (len(cf), cf.mean() if len(cf) else float("nan"),
                                                              (cf > 0).mean() * 100 if len(cf) else float("nan")))
    print("  NO-confirmado   n=%-4d exp=%+.3fR  WR=%.0f%%" % (len(nf), nf.mean() if len(nf) else float("nan"),
                                                              (nf > 0).mean() * 100 if len(nf) else float("nan")))
    if len(cf) >= 20:
        # DSR del subset confirmado, deflactado por los trials (configs) explorados
        sr_std = float(np.std([base.std(ddof=1) and base.mean() / base.std(ddof=1),
                               cf.std(ddof=1) and cf.mean() / cf.std(ddof=1)], ddof=0)) or 0.02
        d = vg.deflated_sharpe_ratio(cf.values, n_trials=n_trials, sr_trials_std=max(sr_std, 0.01))
        uplift = (cf.mean() - base.mean())
        print("\n  uplift CVD-confirmado vs baseline: %+.3fR" % uplift)
        print("  DSR(confirmado, n_trials=%d) = %.3f  -> %s" % (
            n_trials, d["dsr"], "EDGE REAL ✓ (cablear)" if (d["significant"] and uplift > 0)
            else "NO pasa / no mejora — NO cablear"))
    else:
        print("\n  pocos confirmados (<20) para DSR — más historia.")


def main(argv):
    p = argparse.ArgumentParser(description="Valida si el CVD firmado mejora el edge (real + DSR).")
    p.add_argument("--cube", required=True)
    p.add_argument("--cvd", required=True, help="cvd_hist_<SYM>.parquet de fetch_binance_vision_cvd")
    p.add_argument("--tp", default="tp4")
    p.add_argument("--horizon", type=int, default=576)
    p.add_argument("--imb-min", type=float, default=0.55)
    p.add_argument("--n-trials", type=int, default=12)
    a = p.parse_args(argv)
    df = evaluate(a.cube, a.cvd, tp=a.tp, horizon=a.horizon, imb_min=a.imb_min)
    report(df, n_trials=a.n_trials)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
