# -*- coding: utf-8 -*-
"""
mom_edge.py - El edge, parte 2: MOMENTUM (la reversion naive perdio -> seguir).

mr_edge.py mostro que fadear z=1.5-3 pierde (-0.3R) en los 8 simbolos: a esos
umbrales el regimen es EXPANSION (lo confirma el mapa de contraccion). Aca testeo
lo contrario: breakout de Donchian + trailing stop (dejar correr al ganador).

Regla: close rompe el extremo de las ultimas K velas -> entrar EN LA DIRECCION del
breakout (apertura siguiente). Stop inicial = 1.5 ATR. Trailing chandelier = 2 ATR
desde el pico favorable. Time-stop. risk(1R) = 1.5 ATR.

Mismo rigor: split IS/OOS por simbolo, costos de fee, sweep de K, detalle por
simbolo. El OOS es el juez.

Pure numpy/pandas. CONSTRAINTS 7.
"""
import numpy as np
import pandas as pd

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LTC"]
PATH = "data/okx/{}-USDT-SWAP_5m.parquet"
K_LIST = [24, 48, 96]      # lookback del breakout (2h, 4h, 8h)
INIT_STOP = 1.5            # ATR (=1R)
TRAIL = 2.0               # ATR del chandelier
TIME_STOP = 192           # 16h
FEE_RT = 0.0006
OOS_FRAC = 0.30
BARS_YR = 105120


def atr_wilder(df, n=14):
    h = df.high.to_numpy(float); l = df.low.to_numpy(float); c = df.close.to_numpy(float)
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def run_symbol(df, K, split_ts):
    o = df.open.to_numpy(float); c = df.close.to_numpy(float)
    h = df.high.to_numpy(float); l = df.low.to_numpy(float); ts = df.timestamp.to_numpy()
    atr = atr_wilder(df)
    hh = pd.Series(h).rolling(K).max().to_numpy()
    ll = pd.Series(l).rolling(K).min().to_numpy()
    n = len(df); trades = []; i = K
    while i < n - 1:
        if atr[i] <= 0 or not np.isfinite(hh[i]):
            i += 1; continue
        side = 0
        if c[i] > hh[i - 1]: side = 1
        elif c[i] < ll[i - 1]: side = -1
        if side == 0:
            i += 1; continue
        a = atr[i]; entry = o[i + 1]; risk = INIT_STOP * a
        init_stop = entry - side * INIT_STOP * a
        peak = entry; exitp = None; jhit = min(i + 1 + TIME_STOP, n - 1)
        for j in range(i + 1, min(i + 1 + TIME_STOP, n - 1) + 1):
            if side == 1:
                peak = max(peak, h[j])
                stop = max(init_stop, peak - TRAIL * a)
                if l[j] <= stop: exitp, jhit = stop, j; break
            else:
                peak = min(peak, l[j])
                stop = min(init_stop, peak + TRAIL * a)
                if h[j] >= stop: exitp, jhit = stop, j; break
        if exitp is None:
            exitp, jhit = c[min(i + 1 + TIME_STOP, n - 1)], min(i + 1 + TIME_STOP, n - 1)
        pnl = side * (exitp - entry) - FEE_RT * entry
        trades.append((ts[i], pnl / risk, "IS" if ts[i] < split_ts else "OOS", side))
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
            df = pd.read_parquet(PATH.format(s))
            df["split"] = df.timestamp.quantile(1 - OOS_FRAC)
            data[s] = df
        except Exception as e:
            print(f"(sin {s}: {e})")
    print(f"MOMENTUM breakout | stop={INIT_STOP}ATR trail={TRAIL}ATR time={TIME_STOP} fee={FEE_RT*1e4:.0f}bps\n")
    print(f"{'K':>4} | {'IS n':>6} {'IS exp':>8} {'IS wr':>6} {'IS PF':>5} | "
          f"{'OOS n':>6} {'OOS exp':>8} {'OOS wr':>6} {'OOS PF':>6} {'OOS Sh/t':>8}")
    print("-" * 80)
    is_exp = {}
    for K in K_LIST:
        allt = []
        for s, df in data.items():
            allt += run_symbol(df, K, df.split.iloc[0])
        a = stat([t[1] for t in allt if t[2] == "IS"]); b = stat([t[1] for t in allt if t[2] == "OOS"])
        is_exp[K] = a["exp"] if a else -9
        if a and b:
            print(f"{K:>4} | {a['n']:>6} {a['exp']:>+8.3f} {a['wr']:>6.1%} {a['pf']:>5.2f} | "
                  f"{b['n']:>6} {b['exp']:>+8.3f} {b['wr']:>6.1%} {b['pf']:>6.2f} {b['sh']:>+8.3f}")
    best = max(is_exp, key=is_exp.get)
    print(f"\n>> K elegido en IS = {best}")
    allt = []
    for s, df in data.items():
        allt += [(s,) + t for t in run_symbol(df, best, df.split.iloc[0])]
    oos = [t for t in allt if t[3] == "OOS"]
    so = stat([t[2] for t in oos])
    if so:
        yrs = (max(t[1] for t in oos) - min(t[1] for t in oos)) / (BARS_YR * 5 * 60 * 1000)
        tpy = so["n"] / max(yrs, 1e-9)
        print(f"\nVEREDICTO OOS (K={best}): trades={so['n']} exp={so['exp']:+.3f}R wr={so['wr']:.1%} "
              f"PF={so['pf']:.2f} sumR={so['sumR']:+.1f} Sh/trade={so['sh']:+.3f}")
        print(f"  Sharpe anualizado aprox = {so['sh']*np.sqrt(max(tpy,1)):+.2f}  (~{tpy:.0f} trades/ano)")
    print(f"\n  Por simbolo (OOS, K={best}):")
    for s in data:
        st = stat([t[2] for t in oos if t[0] == s])
        if st:
            print(f"    {s:>4}: n={st['n']:>4} exp={st['exp']:+.3f}R wr={st['wr']:.1%} "
                  f"PF={st['pf']:.2f} sumR={st['sumR']:+.1f}")


if __name__ == "__main__":
    main()
