#!/usr/bin/env python3
"""measure_tiers — cadencia y distribución-R por TIER sobre un cube, en la
ventana común donde existe CVD (apples-to-apples).

Tiers:
  base     — todas las señales del cube (tp4/h576)
  calidad  — KL-bajo (irreversibilidad < umbral) = el filtro "Calidad" en vivo
  premium  — CVD✓ & persist✓ & KL-bajo (el "motor premium", triple cruce)

Reusa las funciones YA validadas:
  - irreversibility()          (validate_regime_irreversibility)
  - persistence_confirms()     (validate_persistence_flow, Bouchaud-Farmer-Lillo)
  - confirms_direction()       (fetch_cvd, el edge CVD validado)

Salida: JSON con n, cadencia/sem, meanR, WR, stdR y la serie R por tier
(para el bootstrap Monte-Carlo del escenario).

  python tools/measure_tiers.py --symbol BTC \
    --cube cosecha_cubes/tp_cube_BTC_USDT.parquet \
    --klines data/kl_hist_BTCUSDT.parquet --cvd data/cvd_hist_BTCUSDT.parquet \
    --kl-thr 0.34 --out scratchpad/tiers_BTC.json
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "tools")
from validate_regime_irreversibility import irreversibility  # noqa: E402
from validate_persistence_flow import persistence_features, persistence_confirms  # noqa: E402
import fetch_cvd  # noqa: E402

MS_5M = 300000


def _stats(r):
    r = np.asarray(r, float)
    if r.size == 0:
        return {"n": 0, "meanR": None, "WR": None, "stdR": None}
    return {"n": int(r.size), "meanR": float(r.mean()),
            "WR": float((r > 0).mean()), "stdR": float(r.std(ddof=1)) if r.size > 1 else 0.0}


def measure(cube_path, klines_path, cvd_path, *, tp="tp4", horizon=576,
            kl_lookback=64, cvd_lookback=48, win=24, imb_min=0.55, kl_thr=None):
    cube = pd.read_parquet(cube_path)
    cube["tp"] = cube["tp"].astype(str)
    cube["horizon"] = cube["horizon"].astype(int)
    e = cube[(cube.tp == tp) & (cube.horizon == horizon)].drop_duplicates("entry_index").copy()
    e["ts"] = pd.to_datetime(e["entry_ts"]).values.astype("datetime64[ms]").astype("int64")

    kl = pd.read_parquet(klines_path).sort_values("ts").reset_index(drop=True)
    kl_ts = kl.ts.values
    has_cvd = bool(cvd_path) and os.path.exists(cvd_path)
    cvd = cvd_ts = None
    if has_cvd:
        cvd = pd.read_parquet(cvd_path).sort_values("ts").reset_index(drop=True)
        cvd_ts = cvd.ts.values

    # ventana común: donde TODO el dato necesario existe (con sus lookbacks)
    lo = kl.ts.min() + kl_lookback * MS_5M
    hi = kl.ts.max()
    if has_cvd:
        lo = max(lo, cvd.ts.min() + cvd_lookback * MS_5M)
        hi = min(hi, cvd.ts.max())
    ev = e[(e.ts >= lo) & (e.ts <= hi)].sort_values("ts")

    rows = []
    for _, r in ev.iterrows():
        j = int(np.searchsorted(kl_ts, r.ts))             # causal
        w = kl.iloc[max(0, j - kl_lookback):j]
        if len(w) < 16:
            continue
        irr = irreversibility(pd.to_numeric(w["close"], errors="coerce").to_numpy(float))
        stop_pct = None
        try:
            ep, sp = float(r.entry_price), float(r.stop_price)
            if ep > 0 and sp > 0:
                stop_pct = abs(ep - sp) / ep
        except Exception:
            pass
        rec = {"ts": int(r.ts), "pnl_r": float(r.pnl_r), "dir": int(r.direction),
               "irrev": float(irr), "stop_pct": stop_pct, "persist": None, "cvd": None}
        if has_cvd:
            k = int(np.searchsorted(cvd_ts, r.ts))
            wc = cvd.iloc[max(0, k - cvd_lookback):k]
            if len(wc) >= win:
                pf = persistence_features(wc, win=win)
                rec["persist"] = bool(persistence_confirms(pf, int(r.direction), rule="persist", thr=0.0))
                cf = fetch_cvd.cvd_features(wc, win=win)
                rec["cvd"] = bool(fetch_cvd.confirms_direction(cf, int(r.direction), imb_min=imb_min))
        rows.append(rec)

    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("sin eventos evaluables en la ventana común")

    span_wk = (df.ts.max() - df.ts.min()) / 1000 / 86400 / 7.0
    if kl_thr is None:
        kl_thr = float(df.irrev.median())
    kl_bajo = df.irrev < kl_thr

    tiers = {}

    def add(name, mask):
        sub = df[mask]
        st = _stats(sub.pnl_r.values)
        st["cadence_wk"] = float(st["n"] / span_wk) if span_wk > 0 else None
        st["R"] = [round(float(x), 4) for x in sub.pnl_r.values]
        st["stops"] = [round(float(x), 6) if x is not None and not np.isnan(x) else None
                       for x in sub.stop_pct.values]
        sp = sub.stop_pct.dropna()
        st["stop_pct_median"] = float(sp.median()) if len(sp) else None
        tiers[name] = st

    add("base", pd.Series(True, index=df.index))
    add("calidad", kl_bajo)
    if has_cvd:
        cvd_ok = df.cvd.fillna(False).astype(bool)
        persist_ok = df.persist.fillna(False).astype(bool)
        add("cvd", cvd_ok)
        add("premium", cvd_ok & persist_ok & kl_bajo)

    return {"span_weeks": round(span_wk, 1),
            "window": [int(df.ts.min()), int(df.ts.max())],
            "kl_thr": round(float(kl_thr), 4),
            "kl_median": round(float(df.irrev.median()), 4),
            "n_evaluated": int(len(df)),
            "has_cvd": has_cvd,
            "tiers": tiers}


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--cube", required=True)
    p.add_argument("--klines", required=True)
    p.add_argument("--cvd", default=None)
    p.add_argument("--kl-thr", type=float, default=None, help="umbral irrev (default=mediana)")
    p.add_argument("--imb-min", type=float, default=0.55)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)

    res = measure(a.cube, a.klines, a.cvd, imb_min=a.imb_min, kl_thr=a.kl_thr)
    res["symbol"] = a.symbol
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=2)

    print("=== %s ===  ventana %.1f sem  (KL thr=%.3f, mediana=%.3f)" % (
        a.symbol, res["span_weeks"], res["kl_thr"], res["kl_median"]))
    for name, t in res["tiers"].items():
        if t["n"] == 0:
            print("  %-8s n=0" % name)
            continue
        print("  %-8s n=%-4d  cad=%.2f/sem  meanR=%+.3f  WR=%.0f%%  stdR=%.2f" % (
            name, t["n"], t["cadence_wk"], t["meanR"], 100 * t["WR"], t["stdR"]))
    print("  -> %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
