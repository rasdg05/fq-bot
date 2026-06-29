#!/usr/bin/env python3
"""gate_poc_distance — gatea el POC-distance (DSR + ortogonalidad vs KL + CPCV/PBO).

POC-distance = |entry - POC(día previo)| / (mitad del ancho de la Value Area previa).
Hipótesis (de measure_vp_tier): LEJOS del POC (fuera del chop de ayer) -> mejor edge.
Esto lo PRUEBA contra el gate honesto:
  - DSR del tier "lejos" deflactado por los umbrales barridos (n_trials real).
  - ORTOGONALIDAD vs KL: ¿suma DENTRO de irrev-bajo (el filtro KL ya validado) o es
    redundante? (uplift (KL-bajo & lejos) - (KL-bajo)).
  - CPCV: por cada camino purgado, mejor umbral IS -> uplift OOS (lejos - base).
  - PBO: ¿la mejor selección in-sample se cae out-of-sample?
Pooled cross-símbolo (el premium falló por BTC-only) + consistencia por símbolo. Causal.

  python tools/gate_poc_distance.py \
    --pair BTC cosecha_cubes/tp_cube_BTC_USDT.parquet data/kl_hist_BTCUSDT.parquet \
    --pair ETH cosecha_cubes/tp_cube_ETH_USDT.parquet data/kl_hist_ETHUSDT.parquet \
    --pair SOL cosecha_cubes/tp_cube_SOL_USDT.parquet data/kl_hist_SOLUSDT.parquet
"""
import argparse
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import volume_profile as vpm  # noqa: E402
from validate_regime_irreversibility import irreversibility  # noqa: E402
from validation_gate import deflated_from_trials, cpcv_paths, pbo  # noqa: E402

MS_5M = 300000
KL_LOOKBACK = 64
QS = [0.50, 0.60, 0.667, 0.70, 0.75, 0.80]  # umbrales de "lejos" (cuantil de poc_dist)


def _sharpe(r):
    r = np.asarray(r, float)
    r = r[~np.isnan(r)]
    if r.size < 2 or r.std(ddof=1) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=1))


def tag(label, cube_path, kl_path, *, tp="tp4", horizon=576, n_bins=50):
    c = pd.read_parquet(cube_path)
    c["tp"] = c["tp"].astype(str)
    c["horizon"] = c["horizon"].astype(int)
    e = c[(c.tp == tp) & (c.horizon == horizon)].drop_duplicates("entry_index").copy()
    tsd = pd.to_datetime(e["entry_ts"])
    e["ts"] = tsd.values.astype("datetime64[ms]").astype("int64")
    e["day"] = tsd.dt.normalize()

    k = pd.read_parquet(kl_path)
    if "ts" not in k.columns and "timestamp" in k.columns:   # schema Dukascopy (datetime)
        t = pd.to_datetime(k["timestamp"])
        if getattr(t.dt, "tz", None) is not None:
            t = t.dt.tz_convert("UTC").dt.tz_localize(None)
        k["ts"] = t.values.astype("datetime64[ns]").astype("int64") // 1_000_000
    k = k.sort_values("ts").reset_index(drop=True)
    k["day"] = pd.to_datetime(k["ts"], unit="ms", utc=True).dt.tz_localize(None).dt.normalize()
    kl_ts = k.ts.values
    kl_close = pd.to_numeric(k["close"], errors="coerce").to_numpy(float)

    profiles, order = {}, []
    for day, g in k.groupby("day"):
        p = vpm.volume_profile(g, n_bins=n_bins)
        if p is not None:
            profiles[day] = p
            order.append(day)
    prior = {d: (profiles[order[i - 1]] if i > 0 else None) for i, d in enumerate(order)}

    lo = kl_ts.min() + KL_LOOKBACK * MS_5M
    rows = []
    for _, r in e.iterrows():
        if r.ts < lo or r.ts > kl_ts.max():
            continue
        prof = prior.get(r.day)
        if prof is None:
            continue
        half = max((prof.vah - prof.val) / 2.0, 1e-9)
        poc_dist = abs(float(r.entry_price) - prof.poc) / half
        j = int(np.searchsorted(kl_ts, r.ts))
        w = kl_close[max(0, j - KL_LOOKBACK):j]
        if len(w) < 16:
            continue
        rows.append({"sym": label, "ts": int(r.ts), "pnl_r": float(r.pnl_r),
                     "poc_dist": poc_dist, "irrev": float(irreversibility(w))})
    return pd.DataFrame(rows)


def gate(df):
    df = df.sort_values("ts").reset_index(drop=True)
    R = df.pnl_r.values
    dist = df.poc_dist.values
    kl_bajo = (df.irrev < df.irrev.median()).values
    base_mean = float(R.mean())

    # barrido de umbrales "lejos" -> sharpe de cada tier
    trials = []
    for q in QS:
        thr = float(np.quantile(dist, q))
        far = dist >= thr
        trials.append(dict(q=q, thr=thr, far=far, sh=_sharpe(R[far]),
                           mean=float(R[far].mean()), n=int(far.sum())))
    best = max(trials, key=lambda t: t["sh"])
    all_sh = [t["sh"] for t in trials]

    dsr_far = deflated_from_trials(R[best["far"]], all_sh)
    combo = kl_bajo & best["far"]
    dsr_combo = deflated_from_trials(R[combo], all_sh)
    upl_far = best["mean"] - base_mean
    upl_within_kl = float(R[combo].mean()) - float(R[kl_bajo].mean())

    # CPCV: mejor umbral IS -> uplift OOS (lejos - base) en el test purgado
    oos = []
    for tr, te in cpcv_paths(len(df), n_groups=6, n_test_groups=2):
        bsh, bthr = -9.0, None
        for q in QS:
            thr = np.quantile(dist[tr], q)
            f = dist[tr] >= thr
            s = _sharpe(R[tr][f])
            if s > bsh:
                bsh, bthr = s, thr
        f_oos = dist[te] >= bthr
        if f_oos.sum() > 5:
            oos.append(float(R[te][f_oos].mean() - R[te].mean()))
    oos = np.array(oos)

    # PBO: matriz (tiempo x umbral)
    T = 16
    M = np.zeros((T, len(QS)))
    for ti, b in enumerate(np.array_split(np.arange(len(df)), T)):
        for ci, q in enumerate(QS):
            thr = float(np.quantile(dist, q))
            f = dist[b] >= thr
            M[ti, ci] = R[b][f].mean() if f.sum() > 0 else R[b].mean()
    pbo_val = pbo(M, n_splits=8)

    return dict(base_mean=base_mean, base_n=len(R), best=best, dsr_far=dsr_far,
                dsr_combo=dsr_combo, upl_far=upl_far, upl_within_kl=upl_within_kl,
                kl_mean=float(R[kl_bajo].mean()), combo_mean=float(R[combo].mean()),
                combo_n=int(combo.sum()), oos_med=float(np.median(oos)) if len(oos) else float("nan"),
                oos_pos=float((oos > 0).mean()) if len(oos) else float("nan"),
                oos_n=len(oos), pbo=float(pbo_val))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--pair", nargs=3, action="append", metavar=("LABEL", "CUBE", "KLINES"),
                   required=True)
    a = p.parse_args(argv)

    frames = []
    print("== POC-distance GATE ==", flush=True)
    for label, cube, kl in a.pair:
        t = tag(label, cube, kl)
        frames.append(t)
        far = t.poc_dist >= t.poc_dist.quantile(0.70)
        print("  %-4s n=%4d  far>near: meanR %+.3f vs %+.3f  (consistencia)"
              % (label, len(t), t[far].pnl_r.mean(), t[~far].pnl_r.mean()), flush=True)

    df = pd.concat(frames, ignore_index=True)
    g = gate(df)
    b = g["best"]
    print("\n--- POOLED (%d eventos) ---" % g["base_n"])
    print("  base meanR              %+.3f" % g["base_mean"])
    print("  mejor tier 'lejos'      q=%.3f thr=%.2f  n=%d  meanR=%+.3f  (uplift vs base %+.3f)"
          % (b["q"], b["thr"], b["n"], b["mean"], g["upl_far"]))
    print("  DSR(lejos)              sr=%.3f  sr0=%.3f  DSR=%.3f  %s  (n_trials=%d)"
          % (g["dsr_far"]["sr"], g["dsr_far"]["sr0"], g["dsr_far"]["dsr"],
             "✓" if g["dsr_far"]["significant"] else "✗", g["dsr_far"]["n_trials"]))
    print("  -- ortogonalidad vs KL (irrev-bajo) --")
    print("  KL-bajo meanR           %+.3f" % g["kl_mean"])
    print("  KL-bajo & lejos meanR   %+.3f  n=%d  (uplift within-KL %+.3f)  DSR=%.3f %s"
          % (g["combo_mean"], g["combo_n"], g["upl_within_kl"], g["dsr_combo"]["dsr"],
             "✓" if g["dsr_combo"]["significant"] else "✗"))
    print("  -- robustez OOS --")
    print("  CPCV uplift OOS (lejos-base)  mediana %+.3f  %%paths>0 %.0f%%  (n=%d paths)"
          % (g["oos_med"], g["oos_pos"] * 100, g["oos_n"]))
    print("  PBO                     %.2f  %s" % (g["pbo"], "✓ (<0.5)" if g["pbo"] < 0.5 else "🚩 (≥0.5)"))

    ok_dsr = g["dsr_far"]["significant"]
    ok_orth = g["upl_within_kl"] > 0.02
    ok_oos = (g["oos_med"] > 0) and (g["oos_pos"] >= 0.6)
    ok_pbo = g["pbo"] < 0.5
    verdict = "PASA (al motor, forward primero)" if (ok_dsr and ok_orth and ok_oos and ok_pbo) \
        else "NO PASA"
    print("\n  VEREDICTO: %s  [DSR %s · ortho-KL %s · OOS %s · PBO %s]" % (
        verdict, "✓" if ok_dsr else "✗", "✓" if ok_orth else "✗",
        "✓" if ok_oos else "✗", "✓" if ok_pbo else "✗"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
