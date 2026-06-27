# -*- coding: utf-8 -*-
"""
validate_persistence_flow — F2 del research de física moderna: la PERSISTENCIA /
MEMORIA LARGA del flujo firmado (autocorrelación del signo de los trades + Hurst).

Hallazgo verificado (Bouchaud-Farmer-Lillo 2008, arXiv:0809.0822; reconfirmado hasta
2026): el order-flow firmado es un proceso de MEMORIA LARGA — autocorrelación positiva
de largo alcance del SIGNO de los trades — porque las órdenes grandes se ejecutan en
pedacitos (order-splitting) durante horas. Es falsable y directamente samplable, de la
MISMA estirpe que el CVD, pero mide algo DISTINTO: el CVD mide el NIVEL/slope del
desbalance; F2 mide si ese signo PERSISTE (una metaorden trabajándose) -> continuación.

Por evento, sobre la ventana causal de CVD [ts, buy_vol, sell_vol]:
  delta_i = buy_i − sell_i           (flujo firmado por barra)
  s_i     = sign(delta_i)            (signo del trade agregado)
  acsum   = Σ_{l=1..k} ρ_l(s)        (fuerza de la memoria: >0 persistente, <0 anti)
  hurst   = Hurst del flujo firmado  (>0.5 persistente; varianza agregada)
  netdir  = sign(Σ delta)            (presión neta reciente)

Tres hipótesis a falsar con el gate DSR/CPCV/PBO:
  persist — acsum>thr (memoria fuerte) & netdir alineado -> la presión CONTINÚA.
  revert  — acsum<−thr (anti-persistente) -> el flujo se revierte (fade a netdir).
  hurst   — hurst>0.5+thr & netdir alineado -> continuación (medida alterna).

Data GRATIS: cvd_hist 5m (fetch_binance_vision_cvd). La ortogonalidad cruza contra el
CVD-imbalance del MISMO archivo (¿la memoria suma DENTRO de lo ya CVD-confirmado?).

Uso:
  python tools/validate_persistence_flow.py --cube cosecha_cubes/tp_cube_ETH_USDT.parquet \
      --cvd data/cvd_hist_ETHUSDT.parquet --rule persist --thr 0.05
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validation_gate as vg  # noqa: E402
import fetch_cvd  # noqa: E402


def _autocorr_sum(s, k):
    """Σ de autocorrelaciones lag 1..k de la serie s (centrada). Mide memoria."""
    s = np.asarray(s, float)
    s = s - s.mean()
    den = float((s * s).sum())
    if den <= 0:
        return 0.0, 0.0
    ac1 = float((s[1:] * s[:-1]).sum() / den) if len(s) > 1 else 0.0
    tot = 0.0
    for l in range(1, int(k) + 1):
        if l >= len(s):
            break
        tot += float((s[l:] * s[:-l]).sum() / den)
    return tot, ac1


def _hurst(x):
    """Hurst por varianza agregada: Var(media de bloques de tamaño m) ∝ m^(2H−2).
    Pendiente log-log -> H. Robusto y sin dependencias. ~0.5 = sin memoria."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 16:
        return 0.5
    ms, vs = [], []
    for m in (1, 2, 4, 8, max(8, n // 8), max(16, n // 4)):
        if m < 1 or m > n // 2:
            continue
        nb = n // m
        blocks = x[:nb * m].reshape(nb, m).mean(axis=1)
        v = float(blocks.var(ddof=1)) if nb > 1 else 0.0
        if v > 0:
            ms.append(np.log(m))
            vs.append(np.log(v))
    if len(ms) < 2:
        return 0.5
    slope = float(np.polyfit(ms, vs, 1)[0])             # = 2H − 2
    return max(0.0, min(1.0, slope / 2.0 + 1.0))


def persistence_features(df, win=24):
    """Memoria del flujo firmado en las últimas `win` barras de CVD [ts, buy_vol, sell_vol]."""
    d = df.sort_values("ts")
    buy = pd.to_numeric(d["buy_vol"], errors="coerce").to_numpy(float)
    sell = pd.to_numeric(d["sell_vol"], errors="coerce").to_numpy(float)
    m = np.isfinite(buy) & np.isfinite(sell)
    buy, sell = buy[m], sell[m]
    w = min(int(win), len(buy))
    if w < 4:
        return {"acsum": 0.0, "ac1": 0.0, "hurst": 0.5, "netdir": 0, "n": int(len(buy))}
    delta = (buy - sell)[-w:]
    sign = np.sign(delta)
    k = max(1, min(3, w // 4))                        # lags CORTOS: la memoria de signos decae lento y positiva
    acsum, ac1 = _autocorr_sum(sign, k)
    hurst = _hurst(delta)
    netdir = int(np.sign(delta.sum()))
    return {"acsum": float(acsum), "ac1": float(ac1), "hurst": float(hurst),
            "netdir": netdir, "n": int(len(buy))}


def persistence_confirms(feat, direction, rule="persist", thr=0.0):
    """¿La memoria del flujo confirma la dirección del trade? (ac1 = autocorrelación lag-1
    del signo = la medida canónica y robusta de order-splitting; hurst = medida alterna):
      persist — ac1>thr & netdir == dir   -> signos agrupados, presión persistente (continuación).
      revert  — ac1<−thr & netdir == −dir -> signos alternantes, el flujo se revierte (fade).
      hurst   — hurst>0.5+thr & netdir == dir -> memoria larga alineada (continuación).
    """
    is_long = direction in (1, "long", "buy")
    want = 1 if is_long else -1
    nd = feat["netdir"]
    if rule == "persist":
        return feat["ac1"] > thr and nd == want
    if rule == "revert":
        return feat["ac1"] < -thr and nd == -want
    if rule == "hurst":
        return feat["hurst"] > 0.5 + thr and nd == want
    raise ValueError("regla desconocida: %s" % rule)


def evaluate(cube_path, cvd_path, rule="persist", thr=0.0, tp="tp4", horizon=576,
             win=24, lookback=48, imb_min=0.50):
    """Confirma la memoria del flujo por evento (causal) y, del MISMO CVD, la confirmación
    de imbalance-nivel -> habilita la ortogonalidad (¿la memoria suma sobre el imbalance?)."""
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
        j = int(np.searchsorted(cvd_ts, r.ts))          # CAUSAL: barras con ts < entrada
        w = cvd.iloc[max(0, j - lookback):j]
        if len(w) < win:
            continue
        f = persistence_features(w, win=win)
        # CVD imbalance-nivel sobre la MISMA ventana (lo ya validado) para la ortogonalidad
        fc = fetch_cvd.cvd_features(w, win=win)
        rows.append({"pnl_r": float(r.pnl_r),
                     "confirma": bool(persistence_confirms(f, int(r.direction), rule=rule, thr=thr)),
                     "dir": int(r.direction),
                     "cvd_conf": bool(fetch_cvd.confirms_direction(fc, int(r.direction), imb_min=imb_min))})
    return pd.DataFrame(rows)


def report_orthogonality(df, imb_min, n_trials=20):
    """¿F2 (memoria) apila con el CVD (imbalance-nivel)? 2×2 + el test clave: DENTRO de
    CVD-confirmado, ¿F2-confirmado bate al no-confirmado? Si sí -> ortogonal."""
    d = df[df.cvd_conf.notna()].copy()
    print("\n=== Ortogonalidad persistencia × CVD-imbalance (imb=%.2f) ===" % imb_min)
    if len(d) < 40:
        print("eventos con persistencia Y CVD: %d (<40) — más historia." % len(d))
        return
    d["cvd"] = d.cvd_conf.astype(bool)
    d["mt"] = d.confirma.astype(bool)
    print("eventos con persistencia Y CVD: %d" % len(d))
    for cv in (True, False):
        s1 = d[(d.cvd == cv) & (d.mt)]["pnl_r"]
        s0 = d[(d.cvd == cv) & (~d.mt)]["pnl_r"]
        print("  CVD%s |  F2✓ n=%-4d %+.3fR    F2✗ n=%-4d %+.3fR" % (
            "✓" if cv else "✗", len(s1), s1.mean() if len(s1) else float("nan"),
            len(s0), s0.mean() if len(s0) else float("nan")))
    cc_y = d[(d.cvd) & (d.mt)]["pnl_r"]
    cc_n = d[(d.cvd) & (~d.mt)]["pnl_r"]
    if len(cc_y) >= 10 and len(cc_n) >= 10:
        up = cc_y.mean() - cc_n.mean()
        print("\n  DENTRO de CVD-confirmado:  F2✓ %+.3fR  vs  F2✗ %+.3fR  ->  uplift %+.3fR" % (
            cc_y.mean(), cc_n.mean(), up))
        print("  -> %s" % ("ORTOGONAL ✓ — la memoria suma sobre el imbalance, APILAN"
                           if up > 0.02 else "redundante / no suma sobre el CVD"))
    else:
        print("\n  pocos en CVD✓ para el test interno.")
    prem = d[(d.cvd) & (d.mt)]["pnl_r"]
    if len(prem) >= 20:
        base = d["pnl_r"]
        sr_std = float(np.std([base.mean() / base.std(ddof=1) if base.std(ddof=1) else 0.0,
                               prem.mean() / prem.std(ddof=1) if prem.std(ddof=1) else 0.0], ddof=0)) or 0.02
        dd = vg.deflated_sharpe_ratio(prem.values, n_trials=n_trials, sr_trials_std=max(sr_std, 0.01))
        print("  TIER PREMIUM (CVD✓ & F2✓): n=%d exp=%+.3fR  DSR=%.3f %s" % (
            len(prem), prem.mean(), dd["dsr"], "✓" if dd["significant"] else ""))


def report(df, rule, thr, n_trials=16):
    n = len(df)
    print("=== persistencia del flujo (%s, thr=%.3f) vs cube (dato REAL) ===" % (rule, thr))
    print("eventos con CVD real cubriendo la entrada: %d" % n)
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
    p = argparse.ArgumentParser(description="Valida la persistencia/memoria del flujo firmado (real + DSR).")
    p.add_argument("--cube", required=True)
    p.add_argument("--cvd", required=True, help="cvd_hist_<SYM>.parquet (ts, buy_vol, sell_vol)")
    p.add_argument("--rule", default="persist", choices=["persist", "revert", "hurst"])
    p.add_argument("--thr", type=float, default=0.0)
    p.add_argument("--imb-min", type=float, default=0.50)
    p.add_argument("--tp", default="tp4")
    p.add_argument("--horizon", type=int, default=576)
    p.add_argument("--n-trials", type=int, default=16)
    a = p.parse_args(argv)
    df = evaluate(a.cube, a.cvd, rule=a.rule, thr=a.thr, tp=a.tp, horizon=a.horizon, imb_min=a.imb_min)
    report(df, a.rule, a.thr, n_trials=a.n_trials)
    report_orthogonality(df, a.imb_min, n_trials=a.n_trials)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
