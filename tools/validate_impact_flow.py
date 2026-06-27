# -*- coding: utf-8 -*-
"""
validate_impact_flow — F1 del research de física moderna: el RESIDUAL DE IMPACTO
RAÍZ-CUADRADA (absorción vs fragilidad).

La ley de raíz cuadrada del impacto (impacto ∝ σ·√(Q/V), δ≈0.5) es el núcleo robusto
y EMPÍRICAMENTE UNIVERSAL de la microestructura — confirmada en BTC (Donier-Bonart,
>1M metaórdenes) y reconfirmada 2025 (Sato-Kanazawa, PRL 135, δ=0.489±0.0015). El CVD
da el SIGNO del flujo; la raíz cuadrada dice cuánto DEBERÍA moverse el precio por ese
flujo. La divergencia es samplable:

  real  = movimiento normalizado realizado en la ventana = logret / (σ·√win)
  pred  = √(participación firmada)                       = √(Σ|signed|/Σvol)   (Y unitaria)
  resid = real − sign(netflow)·pred
    resid<0  -> el precio se movió MENOS de lo que el flujo justifica = ABSORCIÓN
                (muro pasivo soaking it up; resorte comprimido)
    resid>0  -> el precio se movió MÁS de lo que el flujo justifica  = FRAGILIDAD
                (libro fino; sobre-extensión)

Tres hipótesis a falsar con el MISMO gate que validó el CVD (DSR/CPCV/PBO):
  coiled    — bajo-reacción (absorción) -> la presión continúa en su dirección.
  extended  — sobre-reacción -> reversión.
  fragile   — alta eficiencia de impacto (libro fino) -> momentum alineado al flujo.

Data GRATIS: klines 5m (fetch_binance_vision_klines) — trae taker_buy_base, así que el
flujo firmado sale del mismo archivo. La ortogonalidad cruza contra el CVD (aggTrades).

Uso:
  python tools/validate_impact_flow.py --cube cosecha_cubes/tp_cube_ETH_USDT.parquet \
      --klines data/kl_hist_ETHUSDT.parquet --rule coiled --thr 0.10 \
      --cvd data/cvd_hist_ETHUSDT.parquet
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validation_gate as vg  # noqa: E402


def impact_features(df, win=24):
    """Residual de impacto raíz-cuadrada de las últimas `win` barras klines.
    df: [ts, close, volume, taker_buy_base] (UN símbolo). Puro, causal, sin red."""
    d = df.sort_values("ts")
    close = pd.to_numeric(d["close"], errors="coerce").to_numpy(float)
    vol = pd.to_numeric(d["volume"], errors="coerce").to_numpy(float)
    tbb = pd.to_numeric(d["taker_buy_base"], errors="coerce").to_numpy(float)
    m = np.isfinite(close) & np.isfinite(vol) & (vol > 0)
    close, vol, tbb = close[m], vol[m], tbb[m]
    w = min(int(win), len(close))
    if w < 3:
        return {"netflow": 0.0, "flow_mag": 0.0, "real": 0.0, "pred": 0.0,
                "resid": 0.0, "eff": 0.0, "n": int(len(close))}
    close, vol, tbb = close[-w:], vol[-w:], tbb[-w:]
    signed = 2.0 * tbb - vol                          # taker_buy − taker_sell por barra
    netflow = float(signed.sum())
    sumvol = float(vol.sum())
    flow_mag = float(np.abs(signed).sum() / sumvol) if sumvol > 0 else 0.0
    r = np.diff(np.log(close))                        # retornos log por barra
    sigma = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    ret = float(np.log(close[-1] / close[0]))
    real = ret / (sigma * np.sqrt(len(r))) if sigma > 0 else 0.0   # move normalizado random-walk
    real = float(np.clip(real, -8.0, 8.0))            # >8σ ya es saturación; acota el blow-up con σ→0
    pred = float(np.sqrt(max(flow_mag, 0.0)))         # ley raíz-cuadrada, Y unitaria
    resid = float(real - np.sign(netflow) * pred)
    eff = float(abs(real) / pred) if pred > 0 else 0.0            # impacto por unidad de √flujo
    return {"netflow": netflow, "flow_mag": flow_mag, "real": real, "pred": pred,
            "resid": resid, "eff": eff, "n": int(len(close))}


def impact_confirms(feat, direction, rule="coiled", thr=0.0):
    """¿El residual de impacto confirma la dirección del trade? (signo netflow = presión).
      coiled    — absorción (resid<0): la presión continúa -> LONG si netflow>0 & resid<−thr.
      extended  — sobre-extensión (resid>0): reversión       -> SHORT si netflow>0 & resid>thr.
      fragile   — libro fino (eff alto): momentum con el flujo -> LONG si netflow>0 & eff>thr.
    """
    nf = feat["netflow"]
    is_long = direction in (1, "long", "buy")
    if nf == 0.0:
        return False
    if rule == "coiled":
        if is_long:
            return nf > 0 and feat["resid"] < -thr
        return nf < 0 and feat["resid"] > thr
    if rule == "extended":
        if is_long:
            return nf < 0 and feat["resid"] < -thr      # caída sobre-extendida -> rebote long
        return nf > 0 and feat["resid"] > thr           # subida sobre-extendida -> short
    if rule == "fragile":
        aligned = (nf > 0) if is_long else (nf < 0)
        return aligned and feat["eff"] > thr
    raise ValueError("regla desconocida: %s" % rule)


def evaluate(cube_path, klines_path, rule="coiled", thr=0.0, tp="tp4", horizon=576,
             win=24, lookback=48, cvd_path=None, imb_min=0.50):
    """Confirma el residual de impacto por evento (causal). Si cvd_path, también confirma
    el CVD en el mismo evento -> habilita la ortogonalidad (¿F1 suma DENTRO del CVD?)."""
    cube = pd.read_parquet(cube_path)
    cube["tp"] = cube["tp"].astype(str)
    cube["horizon"] = cube["horizon"].astype(int)
    e = cube[(cube.tp == tp) & (cube.horizon == horizon)].drop_duplicates("entry_index").copy()
    e["ts"] = pd.to_datetime(e["entry_ts"]).values.astype("datetime64[ms]").astype("int64")
    kl = pd.read_parquet(klines_path).sort_values("ts").reset_index(drop=True)
    for c in ("close", "volume", "taker_buy_base"):
        if c not in kl.columns:
            raise SystemExit("klines sin columna '%s' (tiene: %s)" % (c, list(kl.columns)))
    kl_ts = kl.ts.values
    cvd = cvd_ts = fetch_cvd = None
    if cvd_path and os.path.exists(cvd_path):
        import fetch_cvd  # noqa: F811
        cvd = pd.read_parquet(cvd_path).sort_values("ts").reset_index(drop=True)
        cvd_ts = cvd.ts.values
    lo, hi = kl.ts.min(), kl.ts.max()
    ev = e[(e.ts >= lo + lookback * 300000) & (e.ts <= hi)].sort_values("ts")
    rows = []
    for _, r in ev.iterrows():
        j = int(np.searchsorted(kl_ts, r.ts))           # CAUSAL: barras con ts < entrada
        w = kl.iloc[max(0, j - lookback):j]
        if len(w) < win:
            continue
        f = impact_features(w, win=win)
        row = {"pnl_r": float(r.pnl_r),
               "confirma": bool(impact_confirms(f, int(r.direction), rule=rule, thr=thr)),
               "dir": int(r.direction), "cvd_conf": None}
        if cvd is not None:
            k = int(np.searchsorted(cvd_ts, r.ts))
            wc = cvd.iloc[max(0, k - lookback):k]
            if len(wc) >= win:
                fc = fetch_cvd.cvd_features(wc, win=win)
                row["cvd_conf"] = bool(fetch_cvd.confirms_direction(fc, int(r.direction), imb_min=imb_min))
        rows.append(row)
    return pd.DataFrame(rows)


def report_orthogonality(df, imb_min, n_trials=20):
    """¿F1 apila con el CVD? 2×2 + el test clave: DENTRO de CVD-confirmado, ¿F1-confirmado
    bate al no-confirmado? Si sí -> ortogonal (premium tier candidato a capa 3)."""
    d = df[df.cvd_conf.notna()].copy()
    print("\n=== Ortogonalidad impacto × CVD (imb=%.2f) ===" % imb_min)
    if len(d) < 40:
        print("eventos con impacto Y CVD: %d (<40) — más historia." % len(d))
        return
    d["cvd"] = d.cvd_conf.astype(bool)
    d["mt"] = d.confirma.astype(bool)
    print("eventos con impacto Y CVD: %d" % len(d))
    for cv in (True, False):
        s1 = d[(d.cvd == cv) & (d.mt)]["pnl_r"]
        s0 = d[(d.cvd == cv) & (~d.mt)]["pnl_r"]
        print("  CVD%s |  F1✓ n=%-4d %+.3fR    F1✗ n=%-4d %+.3fR" % (
            "✓" if cv else "✗", len(s1), s1.mean() if len(s1) else float("nan"),
            len(s0), s0.mean() if len(s0) else float("nan")))
    cc_y = d[(d.cvd) & (d.mt)]["pnl_r"]
    cc_n = d[(d.cvd) & (~d.mt)]["pnl_r"]
    if len(cc_y) >= 10 and len(cc_n) >= 10:
        up = cc_y.mean() - cc_n.mean()
        print("\n  DENTRO de CVD-confirmado:  F1✓ %+.3fR  vs  F1✗ %+.3fR  ->  uplift %+.3fR" % (
            cc_y.mean(), cc_n.mean(), up))
        print("  -> %s" % ("ORTOGONAL ✓ — suma algo distinto, APILAN"
                           if up > 0.02 else "redundante / no suma sobre el CVD"))
    else:
        print("\n  pocos en CVD✓ para el test interno.")
    prem = d[(d.cvd) & (d.mt)]["pnl_r"]
    if len(prem) >= 20:
        base = d["pnl_r"]
        sr_std = float(np.std([base.mean() / base.std(ddof=1) if base.std(ddof=1) else 0.0,
                               prem.mean() / prem.std(ddof=1) if prem.std(ddof=1) else 0.0], ddof=0)) or 0.02
        dd = vg.deflated_sharpe_ratio(prem.values, n_trials=n_trials, sr_trials_std=max(sr_std, 0.01))
        print("  TIER PREMIUM (CVD✓ & F1✓): n=%d exp=%+.3fR  DSR=%.3f %s" % (
            len(prem), prem.mean(), dd["dsr"], "✓" if dd["significant"] else ""))


def report(df, rule, thr, n_trials=16):
    n = len(df)
    print("=== impacto raíz-cuadrada (%s, thr=%.3f) vs cube (dato REAL) ===" % (rule, thr))
    print("eventos con klines reales cubriendo la entrada: %d" % n)
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
    p = argparse.ArgumentParser(description="Valida el residual de impacto raíz-cuadrada (real + DSR).")
    p.add_argument("--cube", required=True)
    p.add_argument("--klines", required=True, help="kl_hist_<SYM>.parquet (dataset klines)")
    p.add_argument("--rule", default="coiled", choices=["coiled", "extended", "fragile"])
    p.add_argument("--thr", type=float, default=0.0)
    p.add_argument("--cvd", default=None, help="cvd_hist_<SYM>.parquet -> activa la ortogonalidad impacto×CVD")
    p.add_argument("--imb-min", type=float, default=0.50)
    p.add_argument("--tp", default="tp4")
    p.add_argument("--horizon", type=int, default=576)
    p.add_argument("--n-trials", type=int, default=16)
    a = p.parse_args(argv)
    df = evaluate(a.cube, a.klines, rule=a.rule, thr=a.thr, tp=a.tp, horizon=a.horizon,
                  cvd_path=a.cvd, imb_min=a.imb_min)
    report(df, a.rule, a.thr, n_trials=a.n_trials)
    if a.cvd:
        report_orthogonality(df, a.imb_min)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
