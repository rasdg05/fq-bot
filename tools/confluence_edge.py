# -*- coding: utf-8 -*-
"""
confluence_edge.py - El capstone: el edge esta en la SELECCION (confluencia).

Las partes 1-3 mostraron: maker + regimen -> breakeven (~0R). Disparar sobre TODA
senal vale ~lo que cuesta. Hipotesis (la del bot): la expectancy vive en el SUBSET
de alta confluencia. Aca lo medimos apilando factores a-priori sobre el fade MR:

  C1 regimen rango   : Efficiency Ratio < 0.30  (no estamos en tendencia)
  C2 extremo profundo: |z| >= 2.5               (lejos del valor)
  C3 calor/exhaustion: volumen de la vela > 1.5x baseline (clima de reversion)
  C4 sweep de liquidez: la vela barre el extremo de las ultimas K (grab + revierte)

conf = C1+C2+C3+C4 (0..4). Medimos expectancy (maker) por nivel de confluencia,
IS/OOS, pooled 8 simbolos. Prediccion: sube con la confluencia; el subset alto
es positivo OOS. Eso seria el edge -- y la validacion empirica de confluencia>=3.

Pure numpy/pandas. CONSTRAINTS 7.
"""
import numpy as np
import pandas as pd

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LTC"]
PATH = "data/okx/{}-USDT-SWAP_5m.parquet"
W_VWAP = 288
K_ER = 48
K_SWEEP = 48
THETA = 2.0
STOP = 1.5
TIME_STOP = 96
FEE_RT = 0.0001     # maker realista ~1 bps
OOS_FRAC = 0.30


def atr_wilder(df, n=14):
    h = df.high.to_numpy(float); l = df.low.to_numpy(float); c = df.close.to_numpy(float)
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def rolling_vwap(df, win):
    pv = (df.close * df.volume).to_numpy(float); v = df.volume.to_numpy(float)
    s = pd.Series(pv).rolling(win, min_periods=win // 2).sum().to_numpy()
    sv = pd.Series(v).rolling(win, min_periods=win // 2).sum().to_numpy()
    return s / np.where(sv > 0, sv, np.nan)


def eff_ratio(c, K):
    prev = np.concatenate([np.full(K, np.nan), c[:-K]])
    vol = pd.Series(np.abs(np.diff(c, prepend=c[0]))).rolling(K).sum().to_numpy()
    return np.abs(c - prev) / np.where(vol > 0, vol, np.nan)


def run_symbol(df, split_ts):
    o = df.open.to_numpy(float); c = df.close.to_numpy(float)
    h = df.high.to_numpy(float); l = df.low.to_numpy(float)
    vol = df.volume.to_numpy(float); ts = df.timestamp.to_numpy()
    atr = atr_wilder(df); vwap = rolling_vwap(df, W_VWAP)
    z = (c - vwap) / np.where(atr > 0, atr, np.nan); er = eff_ratio(c, K_ER)
    volbase = pd.Series(vol).rolling(20).mean().to_numpy()
    hh = pd.Series(h).rolling(K_SWEEP).max().to_numpy()
    ll = pd.Series(l).rolling(K_SWEEP).min().to_numpy()
    n = len(df); trades = []; i = max(W_VWAP, K_ER, K_SWEEP)
    while i < n - 1:
        if atr[i] <= 0 or not np.isfinite(z[i]) or not np.isfinite(er[i]):
            i += 1; continue
        side = -1 if z[i] >= THETA else (1 if z[i] <= -THETA else 0)
        if side == 0:
            i += 1; continue
        # confluencia (causal)
        c1 = er[i] < 0.30
        c2 = abs(z[i]) >= 2.5
        c3 = volbase[i] > 0 and vol[i] > 1.5 * volbase[i]
        c4 = (h[i] > hh[i - 1]) if side == -1 else (l[i] < ll[i - 1])  # barre el extremo
        conf = int(c1) + int(c2) + int(c3) + int(c4)
        a = atr[i]; entry = o[i + 1]; risk = STOP * a
        target = c[i] - z[i] * a  # vwap[i]
        stop = entry - side * STOP * a
        exitp = None; jend = min(i + 1 + TIME_STOP, n - 1); jhit = jend
        for j in range(i + 1, jend + 1):
            if side == -1:
                if h[j] >= stop: exitp, jhit = stop, j; break
                if l[j] <= target: exitp, jhit = target, j; break
            else:
                if l[j] <= stop: exitp, jhit = stop, j; break
                if h[j] >= target: exitp, jhit = target, j; break
        if exitp is None:
            exitp, jhit = c[jend], jend
        pnl = side * (exitp - entry) - FEE_RT * entry
        trades.append((conf, pnl / risk, "IS" if ts[i] < split_ts else "OOS"))
        i = jhit + 1
    return trades


def stat(R):
    R = np.asarray(R, float)
    if len(R) == 0:
        return None
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    return dict(n=len(R), wr=(R > 0).mean(), exp=R.mean(), pf=(gp / gl if gl > 0 else np.inf), sumR=R.sum())


def main():
    allt = []
    for s in SYMBOLS:
        try:
            df = pd.read_parquet(PATH.format(s)); sp = df.timestamp.quantile(1 - OOS_FRAC)
            allt += run_symbol(df, sp)
        except Exception as e:
            print(f"(sin {s}: {e})")
    print(f"CONFLUENCIA sobre fade MR (maker {FEE_RT*1e4:.0f}bps). Expectancy por # de factores.\n")
    print(f"{'conf':>4} | {'IS n':>6} {'IS exp':>8} {'IS wr':>6} {'IS PF':>5} | "
          f"{'OOS n':>6} {'OOS exp':>8} {'OOS wr':>6} {'OOS PF':>6}")
    print("-" * 74)
    for conf in range(0, 5):
        a = stat([t[1] for t in allt if t[0] == conf and t[2] == "IS"])
        b = stat([t[1] for t in allt if t[0] == conf and t[2] == "OOS"])
        ad = a or dict(n=0, exp=0, wr=0, pf=0); bd = b or dict(n=0, exp=0, wr=0, pf=0)
        print(f"{conf:>4} | {ad['n']:>6} {ad['exp']:>+8.3f} {ad['wr']:>6.1%} {ad['pf']:>5.2f} | "
              f"{bd['n']:>6} {bd['exp']:>+8.3f} {bd['wr']:>6.1%} {bd['pf']:>6.2f}")
    # subset alto (>=3) vs bajo (<3)
    hi = stat([t[1] for t in allt if t[0] >= 3 and t[2] == "OOS"])
    lo = stat([t[1] for t in allt if t[0] < 3 and t[2] == "OOS"])
    print("\nOOS  confluencia>=3 :", {k: round(v, 3) for k, v in hi.items()} if hi else "sin trades")
    print("OOS  confluencia<3  :", {k: round(v, 3) for k, v in lo.items()} if lo else "sin trades")


if __name__ == "__main__":
    main()
