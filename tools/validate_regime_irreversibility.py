# -*- coding: utf-8 -*-
"""
validate_regime_irreversibility — KL: irreversibilidad temporal como CONDICIONADOR de régimen.

Del research (grafo de visibilidad + divergencia KL, arXiv:1601.01980): la irreversibilidad
temporal de una serie de precio es samplable por barra y SIN parámetros libres. NO es señal
líder (detecta tarde), así que NO se usa como dirección — se usa como DESCRIPTOR DE RÉGIMEN:
irreversible = trending/activo; reversible = choppy/muerto.

Hipótesis falsable: el edge de FQ (R base, y/o CVD-confirmado) se CONCENTRA en ventanas de
alta irreversibilidad y se muere en las reversibles. Se testea partiendo los eventos del cube
por irreversibilidad (alta vs baja) y comparando R/DSR en cada régimen. Si separa -> sirve
como gate de régimen (complementa tu KL de régimen existente); si no, al cementerio.

Irreversibilidad = KL(P_in || P_out) de las distribuciones de grado del Grafo de Visibilidad
Horizontal DIRIGIDO sobre la ventana causal de precio (klines). Data GRATIS (kl_hist).

Uso:
  python tools/validate_regime_irreversibility.py --cube cosecha_cubes/tp_cube_ETH_USDT.parquet \
      --klines data/kl_hist_ETHUSDT.parquet [--cvd data/cvd_hist_ETHUSDT.parquet]
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validation_gate as vg          # noqa: E402


def _hvg_degrees(y):
    """Grado in/out del Grafo de Visibilidad Horizontal dirigido. i ve a j>i si toda barra
    entre ellos es menor que min(y_i,y_j). O(n·visibles)."""
    n = len(y)
    indeg = np.zeros(n, dtype=float)
    outdeg = np.zeros(n, dtype=float)
    for i in range(n):
        mid_max = -np.inf
        yi = y[i]
        for j in range(i + 1, n):
            yj = y[j]
            if mid_max < (yi if yi < yj else yj):
                outdeg[i] += 1.0
                indeg[j] += 1.0
            if yj > mid_max:
                mid_max = yj
            if yj >= yi:                 # y_i queda bloqueado hacia la derecha
                break
    return indeg, outdeg


def irreversibility(y):
    """KL(P_in || P_out) de las distribuciones de grado. 0 = reversible (tiempo-simétrico);
    >0 = irreversible (trending/asimétrico). Sin parámetros libres."""
    y = np.asarray(y, float)
    y = y[np.isfinite(y)]
    if len(y) < 8:
        return 0.0
    indeg, outdeg = _hvg_degrees(y)
    kmax = int(max(indeg.max(), outdeg.max()))
    if kmax < 1:
        return 0.0
    bins = np.arange(0, kmax + 2)
    pin, _ = np.histogram(indeg, bins=bins)
    pout, _ = np.histogram(outdeg, bins=bins)
    pin = pin.astype(float) + 1e-9       # suavizado
    pout = pout.astype(float) + 1e-9
    pin /= pin.sum()
    pout /= pout.sum()
    return float(np.sum(pin * np.log(pin / pout)))


def evaluate(cube_path, klines_path, tp="tp4", horizon=576, lookback=64, cvd_path=None, imb_min=0.50):
    """Por evento: irreversibilidad de la ventana causal de precio (klines) + (opcional)
    confirmación CVD para el corte más fino."""
    cube = pd.read_parquet(cube_path)
    cube["tp"] = cube["tp"].astype(str)
    cube["horizon"] = cube["horizon"].astype(int)
    e = cube[(cube.tp == tp) & (cube.horizon == horizon)].drop_duplicates("entry_index").copy()
    e["ts"] = pd.to_datetime(e["entry_ts"]).values.astype("datetime64[ms]").astype("int64")
    kl = pd.read_parquet(klines_path).sort_values("ts").reset_index(drop=True)
    if "close" not in kl.columns:
        raise SystemExit("klines sin 'close' (tiene: %s)" % list(kl.columns))
    kl_ts = kl.ts.values
    cvd = cvd_ts = fetch_cvd = None
    if cvd_path and os.path.exists(cvd_path):
        import fetch_cvd as _fc
        fetch_cvd = _fc
        cvd = pd.read_parquet(cvd_path).sort_values("ts").reset_index(drop=True)
        cvd_ts = cvd.ts.values
    lo, hi = kl.ts.min(), kl.ts.max()
    ev = e[(e.ts >= lo + lookback * 300000) & (e.ts <= hi)].sort_values("ts")
    rows = []
    for _, r in ev.iterrows():
        j = int(np.searchsorted(kl_ts, r.ts))           # CAUSAL
        w = kl.iloc[max(0, j - lookback):j]
        if len(w) < 16:
            continue
        irr = irreversibility(pd.to_numeric(w["close"], errors="coerce").to_numpy(float))
        row = {"pnl_r": float(r.pnl_r), "irrev": irr, "dir": int(r.direction), "cvd_conf": None}
        if cvd is not None:
            k = int(np.searchsorted(cvd_ts, r.ts))
            wc = cvd.iloc[max(0, k - 48):k]
            if len(wc) >= 12:
                fc = fetch_cvd.cvd_features(wc, win=min(24, len(wc)))
                row["cvd_conf"] = bool(fetch_cvd.confirms_direction(fc, int(r.direction), imb_min=imb_min))
        rows.append(row)
    return pd.DataFrame(rows)


def _dsr(series, base, n_trials):
    if len(series) < 20:
        return None
    srs = [base.mean() / base.std(ddof=1) if base.std(ddof=1) else 0.0,
           series.mean() / series.std(ddof=1) if series.std(ddof=1) else 0.0]
    sr_std = float(np.std(srs, ddof=0)) or 0.02
    return vg.deflated_sharpe_ratio(series.values, n_trials=n_trials, sr_trials_std=max(sr_std, 0.01))


def report(df, n_trials=16):
    n = len(df)
    print("=== irreversibilidad como condicionador de régimen vs cube ===")
    print("eventos con irreversibilidad computable: %d" % n)
    if n < 40:
        print("muestra insuficiente (<40) — más historia.")
        return
    base = df["pnl_r"]
    med = df["irrev"].median()
    hi = df[df.irrev > med]; lo = df[df.irrev <= med]
    print("  corte por mediana de irreversibilidad = %.4f" % med)
    print("  baseline TOTAL        n=%-4d exp=%+.3fR  WR=%.0f%%" % (len(base), base.mean(), (base > 0).mean() * 100))
    for nombre, seg in (("RÉGIMEN irrev-ALTO ", hi), ("RÉGIMEN irrev-BAJO ", lo)):
        s = seg["pnl_r"]
        print("  %s n=%-4d exp=%+.3fR  WR=%.0f%%" % (nombre, len(s), s.mean(), (s > 0).mean() * 100))
    sep = hi["pnl_r"].mean() - lo["pnl_r"].mean()
    dd = _dsr(hi["pnl_r"], base, n_trials)
    print("\n  separación (alto − bajo): %+.3fR   DSR(régimen alto)=%s" % (
        sep, ("%.3f" % dd["dsr"]) if dd else "n/a"))
    print("  -> %s" % ("CONDICIONADOR ✓ — el edge se concentra en régimen irreversible/trending"
                       if (sep > 0.05 and dd and dd["significant"]) else
                       "no separa de forma significativa — al cementerio (o ya cubierto por tu KL de régimen)"))
    d = df[df.cvd_conf.notna()]
    if len(d) >= 60:
        print("\n  --- corte fino: CVD-confirmado por régimen ---")
        for nombre, seg in (("CVD✓ & irrev-ALTO", d[(d.cvd_conf) & (d.irrev > med)]),
                            ("CVD✓ & irrev-BAJO", d[(d.cvd_conf) & (d.irrev <= med)])):
            s = seg["pnl_r"]
            if len(s):
                print("  %s n=%-4d exp=%+.3fR" % (nombre, len(s), s.mean()))


def main(argv):
    p = argparse.ArgumentParser(description="Valida la irreversibilidad temporal como gate de régimen.")
    p.add_argument("--cube", required=True)
    p.add_argument("--klines", required=True, help="kl_hist_<SYM>.parquet (precio)")
    p.add_argument("--cvd", default=None, help="cvd_hist_<SYM>.parquet (corte fino opcional)")
    p.add_argument("--imb-min", type=float, default=0.50)
    p.add_argument("--tp", default="tp4")
    p.add_argument("--horizon", type=int, default=576)
    p.add_argument("--lookback", type=int, default=64)
    p.add_argument("--n-trials", type=int, default=16)
    a = p.parse_args(argv)
    df = evaluate(a.cube, a.klines, tp=a.tp, horizon=a.horizon, lookback=a.lookback,
                  cvd_path=a.cvd, imb_min=a.imb_min)
    report(df, n_trials=a.n_trials)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
