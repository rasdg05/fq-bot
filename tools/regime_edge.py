# -*- coding: utf-8 -*-
"""
regime_edge.py - El edge, parte 3: condicionar por REGIMEN (la leccion de las
partes 1 y 2).

MR pierde en tendencia; momentum pierde en rango. La hipotesis: cada uno gana en
SU regimen. Clasificamos regimen con el Efficiency Ratio de Kaufman:
  ER = |close[i]-close[i-K]| / sum|delta close|   en [0,1]
  ER bajo  = choppy/rango  -> MR deberia funcionar.
  ER alto  = tendencia     -> momentum deberia funcionar.

Test: MR (fade z>theta) SOLO si ER<er_lo ; MOM (breakout) SOLO si ER>er_hi.
Mismo rigor: split IS/OOS, costos, sweep chico, pooled + por simbolo. OOS juzga.
Si tras condicionar SIGUE negativo despues de costos -> no hay edge mono/dual-factor
a 5m, y el edge real exige el stack de confluencia (el del bot).

Pure numpy/pandas. CONSTRAINTS 7.
"""
import numpy as np
import pandas as pd

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LTC"]
PATH = "data/okx/{}-USDT-SWAP_5m.parquet"
W_VWAP = 288
K_ER = 48
THETA = 2.0
K_BO = 48
INIT_STOP = 1.5
TRAIL = 2.0
TIME_STOP = 192
FEE_RT = 0.0006
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
    change = np.abs(c - prev)
    vol = pd.Series(np.abs(np.diff(c, prepend=c[0]))).rolling(K).sum().to_numpy()
    return change / np.where(vol > 0, vol, np.nan)


def run(df, mode, er_thr, split_ts):
    o = df.open.to_numpy(float); c = df.close.to_numpy(float)
    h = df.high.to_numpy(float); l = df.low.to_numpy(float); ts = df.timestamp.to_numpy()
    atr = atr_wilder(df); er = eff_ratio(c, K_ER)
    if mode == "mr":
        vwap = rolling_vwap(df, W_VWAP); z = (c - vwap) / np.where(atr > 0, atr, np.nan)
    else:
        hh = pd.Series(h).rolling(K_BO).max().to_numpy(); ll = pd.Series(l).rolling(K_BO).min().to_numpy()
    n = len(df); trades = []; i = max(W_VWAP, K_ER, K_BO)
    while i < n - 1:
        if atr[i] <= 0 or not np.isfinite(er[i]):
            i += 1; continue
        side = 0
        if mode == "mr":
            if er[i] < er_thr and np.isfinite(z[i]):
                side = -1 if z[i] >= THETA else (1 if z[i] <= -THETA else 0)
        else:
            if er[i] > er_thr and np.isfinite(hh[i]):
                side = 1 if c[i] > hh[i - 1] else (-1 if c[i] < ll[i - 1] else 0)
        if side == 0:
            i += 1; continue
        a = atr[i]; entry = o[i + 1]; risk = INIT_STOP * a; jend = min(i + 1 + TIME_STOP, n - 1)
        exitp = None; jhit = jend
        if mode == "mr":
            target = c[i] - z[i] * a  # = vwap[i] (hacia el valor)
            stop = entry - side * INIT_STOP * a
            for j in range(i + 1, jend + 1):
                if side == -1:
                    if h[j] >= stop: exitp, jhit = stop, j; break
                    if l[j] <= target: exitp, jhit = target, j; break
                else:
                    if l[j] <= stop: exitp, jhit = stop, j; break
                    if h[j] >= target: exitp, jhit = target, j; break
        else:
            init_stop = entry - side * INIT_STOP * a; peak = entry
            for j in range(i + 1, jend + 1):
                if side == 1:
                    peak = max(peak, h[j]); stop = max(init_stop, peak - TRAIL * a)
                    if l[j] <= stop: exitp, jhit = stop, j; break
                else:
                    peak = min(peak, l[j]); stop = min(init_stop, peak + TRAIL * a)
                    if h[j] >= stop: exitp, jhit = stop, j; break
        if exitp is None:
            exitp, jhit = c[jend], jend
        pnl = side * (exitp - entry) - FEE_RT * entry
        trades.append((ts[i], pnl / risk, "IS" if ts[i] < split_ts else "OOS"))
        i = jhit + 1
    return trades


def stat(R):
    R = np.asarray(R, float)
    if len(R) == 0:
        return None
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    return dict(n=len(R), wr=(R > 0).mean(), exp=R.mean(), pf=(gp / gl if gl > 0 else np.inf),
                sumR=R.sum(), sh=R.mean() / (R.std() + 1e-9))


def main():
    data = {}
    for s in SYMBOLS:
        try:
            df = pd.read_parquet(PATH.format(s)); df["split"] = df.timestamp.quantile(1 - OOS_FRAC)
            data[s] = df
        except Exception as e:
            print(f"(sin {s}: {e})")
    print(f"REGIME-conditional | theta={THETA} K_bo={K_BO} ER(K={K_ER}) stop={INIT_STOP} fee={FEE_RT*1e4:.0f}bps\n")
    grid = [("mr", 0.20), ("mr", 0.30), ("mom", 0.40), ("mom", 0.50)]
    print(f"{'modo':>5} {'er_thr':>7} | {'IS n':>6} {'IS exp':>8} {'IS wr':>6} {'IS PF':>5} | "
          f"{'OOS n':>6} {'OOS exp':>8} {'OOS wr':>6} {'OOS PF':>6}")
    print("-" * 78)
    for mode, er in grid:
        allt = []
        for s, df in data.items():
            allt += run(df, mode, er, df.split.iloc[0])
        a = stat([t[1] for t in allt if t[2] == "IS"]); b = stat([t[1] for t in allt if t[2] == "OOS"])
        tag = "rango" if mode == "mr" else "tend"
        if a and b:
            print(f"{mode+'('+tag+')':>5} {er:>7.2f} | {a['n']:>6} {a['exp']:>+8.3f} {a['wr']:>6.1%} {a['pf']:>5.2f} | "
                  f"{b['n']:>6} {b['exp']:>+8.3f} {b['wr']:>6.1%} {b['pf']:>6.2f}")
    print("\n(exp en R por trade, neto de fee. OOS = juez. exp>0 = edge real.)")


if __name__ == "__main__":
    main()
