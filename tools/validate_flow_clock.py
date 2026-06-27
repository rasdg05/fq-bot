# -*- coding: utf-8 -*-
"""
validate_flow_clock — F3: ¿el RELOJ DE FLUJO mejora la persistencia vs el reloj de pared?

Prueba PAREADA y limpia: por cada evento del cube, computa la persistencia del flujo firmado
(F2, ac1 del signo) sobre los MISMOS datos en DOS relojes — el de pared (últimas n_bars barras
5m, tiempo igual) y el de flujo (n_bars cubetas de volumen-firmado igual, build_flow_clock).
El reloj es la ÚNICA diferencia. Si el de flujo sube el DSR / el uplift dentro-de-CVD vs el de
pared, robustamente en varios n_bars -> la idea de RasDG es real y se cablea; si no, al cementerio.

Mismo gate que CVD/F2 (DSR/CPCV/PBO) + ortogonalidad vs CVD. Data GRATIS (cvd_hist, aggTrades).

Uso:
  python tools/validate_flow_clock.py --cube cosecha_cubes/tp_cube_ETH_USDT.parquet \
      --cvd data/cvd_hist_ETHUSDT.parquet --n-bars 24 --thr 0.0
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validation_gate as vg          # noqa: E402
import fetch_cvd                      # noqa: E402
from build_flow_clock import to_flow_bars                       # noqa: E402
from validate_persistence_flow import persistence_features, persistence_confirms  # noqa: E402


def _persist_ok(bars, direction, win, thr):
    if bars is None or len(bars) < max(4, win // 2):
        return None
    f = persistence_features(bars, win=win)
    return bool(persistence_confirms(f, direction, rule="persist", thr=thr))


def evaluate(cube_path, cvd_path, n_bars=24, thr=0.0, tp="tp4", horizon=576,
             lookback=96, imb_min=0.50):
    """Por evento: persistencia en reloj de PARED (últimas n_bars 5m) vs reloj de FLUJO
    (n_bars cubetas de volumen igual), + confirmación CVD para la ortogonalidad."""
    cube = pd.read_parquet(cube_path)
    cube["tp"] = cube["tp"].astype(str)
    cube["horizon"] = cube["horizon"].astype(int)
    e = cube[(cube.tp == tp) & (cube.horizon == horizon)].drop_duplicates("entry_index").copy()
    e["ts"] = pd.to_datetime(e["entry_ts"]).values.astype("datetime64[ms]").astype("int64")
    cvd = pd.read_parquet(cvd_path).sort_values("ts").reset_index(drop=True)
    for c in ("buy_vol", "sell_vol"):
        if c not in cvd.columns:
            raise SystemExit("cvd sin columna '%s' (tiene: %s)" % (c, list(cvd.columns)))
    cvd_ts = cvd.ts.values
    lo, hi = cvd.ts.min(), cvd.ts.max()
    ev = e[(e.ts >= lo + lookback * 300000) & (e.ts <= hi)].sort_values("ts")
    rows = []
    for _, r in ev.iterrows():
        j = int(np.searchsorted(cvd_ts, r.ts))          # CAUSAL
        w = cvd.iloc[max(0, j - lookback):j]
        if len(w) < n_bars:
            continue
        d = int(r.direction)
        wall = _persist_ok(w.tail(n_bars), d, n_bars, thr)            # reloj de PARED (tiempo igual)
        flow = _persist_ok(to_flow_bars(w, n_bars), d, n_bars, thr)  # reloj de FLUJO (volumen igual)
        if wall is None or flow is None:
            continue
        fc = fetch_cvd.cvd_features(w, win=min(24, len(w)))
        rows.append({"pnl_r": float(r.pnl_r), "wall": wall, "flow": flow, "dir": d,
                     "cvd_conf": bool(fetch_cvd.confirms_direction(fc, d, imb_min=imb_min))})
    return pd.DataFrame(rows)


def _dsr(series, base, n_trials):
    if len(series) < 20:
        return None
    srs = [base.mean() / base.std(ddof=1) if base.std(ddof=1) else 0.0,
           series.mean() / series.std(ddof=1) if series.std(ddof=1) else 0.0]
    sr_std = float(np.std(srs, ddof=0)) or 0.02
    return vg.deflated_sharpe_ratio(series.values, n_trials=n_trials, sr_trials_std=max(sr_std, 0.01))


def report(df, n_bars, thr, n_trials=16):
    n = len(df)
    print("=== reloj de flujo vs pared (n_bars=%d, thr=%.3f) — prueba pareada ===" % (n_bars, thr))
    print("eventos con ambos relojes computables: %d" % n)
    if n < 20:
        print("muestra insuficiente (<20) — más historia.")
        return
    base = df["pnl_r"]
    print("  baseline             n=%-4d exp=%+.3fR" % (len(base), base.mean()))
    out = {}
    for clock in ("wall", "flow"):
        cf = df[df[clock]]["pnl_r"]
        d = _dsr(cf, base, n_trials)
        out[clock] = (cf, d)
        nombre = "PARED (5m)" if clock == "wall" else "FLUJO (vol)"
        print("  %-11s persist  n=%-4d exp=%+.3fR  uplift=%+.3fR  DSR=%s" % (
            nombre, len(cf), cf.mean() if len(cf) else float("nan"),
            (cf.mean() - base.mean()) if len(cf) else float("nan"),
            ("%.3f" % d["dsr"]) if d else "n/a"))
    wf, wd = out["wall"]; ff, fd = out["flow"]
    if wd and fd:
        better = fd["dsr"] >= wd["dsr"] and (ff.mean() - base.mean()) > 0
        print("\n  VEREDICTO F3: el reloj de FLUJO %s al de pared (DSR %.3f vs %.3f) -> %s" % (
            "MEJORA/IGUALA" if better else "NO mejora", fd["dsr"], wd["dsr"],
            "candidato a cablear ✓" if (better and fd["significant"]) else "no aporta sobre el reloj de pared — al cementerio"))


def report_orthogonality(df, imb_min, n_trials=20):
    d = df[df.cvd_conf.notna()].copy()
    print("\n=== Ortogonalidad reloj-de-flujo × CVD (imb=%.2f) ===" % imb_min)
    if len(d) < 40:
        print("eventos con flujo Y CVD: %d (<40) — más historia." % len(d))
        return
    d["cvd"] = d.cvd_conf.astype(bool)
    d["mt"] = d.flow.astype(bool)
    cc_y = d[(d.cvd) & (d.mt)]["pnl_r"]
    cc_n = d[(d.cvd) & (~d.mt)]["pnl_r"]
    if len(cc_y) >= 10 and len(cc_n) >= 10:
        up = cc_y.mean() - cc_n.mean()
        print("  DENTRO de CVD-confirmado:  flujo✓ %+.3fR  vs  flujo✗ %+.3fR  ->  uplift %+.3fR" % (
            cc_y.mean(), cc_n.mean(), up))
        print("  -> %s" % ("ORTOGONAL ✓ — el reloj de flujo suma sobre el CVD"
                           if up > 0.02 else "redundante / no suma sobre el CVD"))
    prem = cc_y
    if len(prem) >= 20:
        base = d["pnl_r"]
        dd = _dsr(prem, base, n_trials)
        if dd:
            print("  TIER PREMIUM (CVD✓ & flujo✓): n=%d exp=%+.3fR  DSR=%.3f %s" % (
                len(prem), prem.mean(), dd["dsr"], "✓" if dd["significant"] else ""))


def main(argv):
    p = argparse.ArgumentParser(description="Valida el reloj de flujo (F3) vs el de pared — prueba pareada + DSR.")
    p.add_argument("--cube", required=True)
    p.add_argument("--cvd", required=True, help="cvd_hist_<SYM>.parquet")
    p.add_argument("--n-bars", type=int, default=24, help="nº de barras por ventana (igual en ambos relojes)")
    p.add_argument("--thr", type=float, default=0.0)
    p.add_argument("--imb-min", type=float, default=0.50)
    p.add_argument("--tp", default="tp4")
    p.add_argument("--horizon", type=int, default=576)
    p.add_argument("--lookback", type=int, default=96)
    p.add_argument("--n-trials", type=int, default=16)
    a = p.parse_args(argv)
    df = evaluate(a.cube, a.cvd, n_bars=a.n_bars, thr=a.thr, tp=a.tp, horizon=a.horizon,
                  lookback=a.lookback, imb_min=a.imb_min)
    report(df, a.n_bars, a.thr, n_trials=a.n_trials)
    report_orthogonality(df, a.imb_min, n_trials=a.n_trials)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
