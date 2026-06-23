# -*- coding: utf-8 -*-
"""
edge_htf.py - El ultimo lever: timeframe mas alto.

A 5m los costos/ruido se comen el edge fino de confluencia. En TF mas alto el ATR
por trade es mayor -> el costo fijo (bps) pesa relativamente menos y la senal
estructural es mas limpia. Resampleamos 5m -> 1h y 4h y corremos el MISMO fade MR
con gradiente de confluencia (maker), IS/OOS. Si conf>=3 es positivo y ESTABLE
IS<->OOS en TF alto, ahi vive el edge.

Pure numpy/pandas. CONSTRAINTS 7.
"""
import numpy as np
import pandas as pd

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LTC"]
PATH = "data/okx/{}-USDT-SWAP_5m.parquet"
THETA = 2.0
STOP = 1.5
FEE_RT = 0.0001
OOS_FRAC = 0.30
# TF -> (vwap_bars, er_bars, sweep_bars, time_stop_bars)
TFS = {"1h": (3600000, 24, 24, 24, 48), "4h": (14400000, 12, 12, 12, 24)}


def resample(df, tf_ms):
    g = (df.timestamp // tf_ms) * tf_ms
    out = df.groupby(g).agg(open=("open", "first"), high=("high", "max"),
                            low=("low", "min"), close=("close", "last"),
                            volume=("volume", "sum"))
    out.index.name = "timestamp"
    return out.reset_index()


def atr_wilder(df, n=14):
    h = df.high.to_numpy(float); l = df.low.to_numpy(float); c = df.close.to_numpy(float)
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def rolling_vwap(df, win):
    pv = (df.close * df.volume).to_numpy(float); v = df.volume.to_numpy(float)
    s = pd.Series(pv).rolling(win, min_periods=max(2, win // 2)).sum().to_numpy()
    sv = pd.Series(v).rolling(win, min_periods=max(2, win // 2)).sum().to_numpy()
    return s / np.where(sv > 0, sv, np.nan)


def eff_ratio(c, K):
    prev = np.concatenate([np.full(K, np.nan), c[:-K]])
    vol = pd.Series(np.abs(np.diff(c, prepend=c[0]))).rolling(K).sum().to_numpy()
    return np.abs(c - prev) / np.where(vol > 0, vol, np.nan)


def run_symbol(df, wins, split_ts):
    vwap_b, er_b, sweep_b, time_b = wins
    o = df.open.to_numpy(float); c = df.close.to_numpy(float)
    h = df.high.to_numpy(float); l = df.low.to_numpy(float)
    vol = df.volume.to_numpy(float); ts = df.timestamp.to_numpy()
    atr = atr_wilder(df); vwap = rolling_vwap(df, vwap_b)
    z = (c - vwap) / np.where(atr > 0, atr, np.nan); er = eff_ratio(c, er_b)
    volbase = pd.Series(vol).rolling(20).mean().to_numpy()
    hh = pd.Series(h).rolling(sweep_b).max().to_numpy(); ll = pd.Series(l).rolling(sweep_b).min().to_numpy()
    n = len(df); trades = []; i = max(vwap_b, er_b, sweep_b)
    while i < n - 1:
        if atr[i] <= 0 or not np.isfinite(z[i]) or not np.isfinite(er[i]):
            i += 1; continue
        side = -1 if z[i] >= THETA else (1 if z[i] <= -THETA else 0)
        if side == 0:
            i += 1; continue
        c1 = er[i] < 0.30; c2 = abs(z[i]) >= 2.5
        c3 = volbase[i] > 0 and vol[i] > 1.5 * volbase[i]
        c4 = (h[i] > hh[i - 1]) if side == -1 else (l[i] < ll[i - 1])
        conf = int(c1) + int(c2) + int(c3) + int(c4)
        a = atr[i]; entry = o[i + 1]; risk = STOP * a
        target = c[i] - z[i] * a; stop = entry - side * STOP * a
        exitp = None; jend = min(i + 1 + time_b, n - 1); jhit = jend
        for j in range(i + 1, jend + 1):
            if side == -1:
                if h[j] >= stop: exitp, jhit = stop, j; break
                if l[j] <= target: exitp, jhit = target, j; break
            else:
                if l[j] <= stop: exitp, jhit = stop, j; break
                if h[j] >= target: exitp, jhit = target, j; break
        if exitp is None:
            exitp, jhit = c[jend], jend
        trades.append((conf, (side * (exitp - entry) - FEE_RT * entry) / risk,
                       "IS" if ts[i] < split_ts else "OOS"))
        i = jhit + 1
    return trades


def stat(R):
    R = np.asarray(R, float)
    if len(R) == 0:
        return dict(n=0, exp=0, wr=0, pf=0, sumR=0)
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    return dict(n=len(R), wr=(R > 0).mean(), exp=R.mean(), pf=(gp / gl if gl > 0 else np.inf), sumR=R.sum())


def main():
    for tf, (tf_ms, *wins) in TFS.items():
        allt = []
        for s in SYMBOLS:
            try:
                df = resample(pd.read_parquet(PATH.format(s)), tf_ms)
                allt += run_symbol(df, wins, df.timestamp.quantile(1 - OOS_FRAC))
            except Exception as e:
                print(f"(sin {s}@{tf}: {e})")
        print(f"\n{'='*72}\nTF = {tf}   (fade MR + confluencia, maker {FEE_RT*1e4:.0f}bps)\n{'='*72}")
        print(f"{'conf':>4} | {'IS n':>6} {'IS exp':>8} {'IS PF':>5} | {'OOS n':>6} {'OOS exp':>8} {'OOS PF':>6}")
        print("-" * 60)
        for conf in range(5):
            a = stat([t[1] for t in allt if t[0] == conf and t[2] == "IS"])
            b = stat([t[1] for t in allt if t[0] == conf and t[2] == "OOS"])
            print(f"{conf:>4} | {a['n']:>6} {a['exp']:>+8.3f} {a['pf']:>5.2f} | {b['n']:>6} {b['exp']:>+8.3f} {b['pf']:>6.2f}")
        ai = stat([t[1] for t in allt if t[0] >= 3 and t[2] == "IS"])
        bo = stat([t[1] for t in allt if t[0] >= 3 and t[2] == "OOS"])
        print(f"  conf>=3:  IS exp={ai['exp']:+.3f} (n={ai['n']}, PF {ai['pf']:.2f})  |  "
              f"OOS exp={bo['exp']:+.3f} (n={bo['n']}, PF {bo['pf']:.2f})")
        estable = "ESTABLE y POSITIVO" if (ai['exp'] > 0 and bo['exp'] > 0) else "no estable/insuf"
        print(f"  -> conf>=3 IS<->OOS: {estable}")


if __name__ == "__main__":
    main()
