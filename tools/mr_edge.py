# -*- coding: utf-8 -*-
"""
mr_edge.py - El edge, MEDIDO: reversion a la media (oscilador alrededor del VWAP).

Los 3 experimentos convergieron: el precio oscila alrededor del valor (VWAP 24h)
con amplitud caracteristica ~2.5 ATR y revierte desde los extremos. Aca eso se
vuelve una REGLA causal y se mide la expectancy real.

Regla FADE: cuando z=(close-VWAP)/ATR cruza +-theta -> entrar CONTRA (hacia VWAP).
  entry = open de la vela siguiente (sin look-ahead).
  target = VWAP (z=0).  stop = entry -+ stop_margin*ATR.  time-stop = N velas.
  risk (1R) = stop_margin*ATR.

Honestidad:
  - split temporal IS(70%)/OOS(30%) por simbolo: theta se elige en IS, se valida en OOS.
  - costos de fee round-trip.
  - baseline de entradas aleatorias (misma cantidad/brackets) -> el edge debe superarlo.
  - se prueban varios theta -> el OOS es el juez (deflacion implicita).

Pure numpy/pandas. CONSTRAINTS 7.
"""
import numpy as np
import pandas as pd

SYMBOLS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LTC"]
PATH = "data/okx/{}-USDT-SWAP_5m.parquet"
W_VWAP = 288        # 24h en velas de 5m
THRESHOLDS = [1.5, 2.0, 2.5, 3.0]
STOP_MARGIN = 1.0   # ATR mas alla de la entrada (=1R)
TIME_STOP = 96      # 8h
FEE_RT = 0.0006     # round-trip ~6 bps (taker OKX, conservador)
OOS_FRAC = 0.30
BARS_YR = 105120


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


def run_symbol(df, theta, split_ts, random_mode=False, seed=0):
    o = df.open.to_numpy(float); c = df.close.to_numpy(float)
    h = df.high.to_numpy(float); l = df.low.to_numpy(float); ts = df.timestamp.to_numpy()
    atr = atr_wilder(df); vwap = rolling_vwap(df, W_VWAP)
    z = (c - vwap) / np.where(atr > 0, atr, np.nan)
    n = len(df); rng = np.random.default_rng(seed)
    trades = []; i = W_VWAP
    while i < n - 1:
        if not np.isfinite(z[i]) or atr[i] <= 0:
            i += 1; continue
        if random_mode:
            # entrada aleatoria con misma frecuencia base que el umbral
            if rng.random() > 0.01:
                i += 1; continue
            side = rng.choice([-1, 1])
        else:
            side = -1 if z[i] >= theta else (1 if z[i] <= -theta else 0)
            if side == 0:
                i += 1; continue
        a = atr[i]; vw = vwap[i]
        entry = o[i + 1]                       # entrar en la apertura siguiente
        target = vw
        stop = entry - side * STOP_MARGIN * a  # short: arriba; long: abajo
        risk = STOP_MARGIN * a
        res = None; exitp = None; jend = min(i + 1 + TIME_STOP, n - 1); jhit = jend
        for j in range(i + 1, jend + 1):
            if side == -1:
                if h[j] >= stop: exitp, res, jhit = stop, "sl", j; break
                if l[j] <= target: exitp, res, jhit = target, "tp", j; break
            else:
                if l[j] <= stop: exitp, res, jhit = stop, "sl", j; break
                if h[j] >= target: exitp, res, jhit = target, "tp", j; break
        if res is None:
            exitp, res, jhit = c[jend], "time", jend
        pnl = side * (exitp - entry) - FEE_RT * entry
        trades.append((ts[i], pnl / risk, res, "IS" if ts[i] < split_ts else "OOS"))
        i = jhit + 1
    return trades


def stat(R):
    R = np.asarray(R)
    if len(R) == 0:
        return None
    wr = (R > 0).mean(); exp = R.mean()
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    pf = gp / gl if gl > 0 else np.inf
    return dict(n=len(R), wr=wr, exp=exp, pf=pf, sumR=R.sum(), sh=exp / (R.std() + 1e-9))


def main():
    data = {}
    for s in SYMBOLS:
        try:
            df = pd.read_parquet(PATH.format(s))
            df["split"] = df.timestamp.quantile(1 - OOS_FRAC)
            data[s] = df
        except Exception as e:
            print(f"(sin {s}: {e})")
    print(f"simbolos: {list(data)} | VWAP={W_VWAP} stop={STOP_MARGIN}ATR time={TIME_STOP} fee={FEE_RT*1e4:.0f}bps\n")

    print(f"{'theta':>6} | {'IS n':>6} {'IS exp(R)':>9} {'IS wr':>6} {'IS PF':>5} | "
          f"{'OOS n':>6} {'OOS exp(R)':>10} {'OOS wr':>6} {'OOS PF':>6} {'OOS Sharpe/t':>11}")
    print("-" * 92)
    is_exp = {}
    for th in THRESHOLDS:
        allt = []
        for s, df in data.items():
            allt += run_symbol(df, th, df.split.iloc[0])
        Ris = [t[1] for t in allt if t[3] == "IS"]; Roos = [t[1] for t in allt if t[3] == "OOS"]
        a, b = stat(Ris), stat(Roos)
        is_exp[th] = a["exp"] if a else -9
        if a and b:
            print(f"{th:>6.1f} | {a['n']:>6} {a['exp']:>+9.3f} {a['wr']:>6.1%} {a['pf']:>5.2f} | "
                  f"{b['n']:>6} {b['exp']:>+10.3f} {b['wr']:>6.1%} {b['pf']:>6.2f} {b['sh']:>+11.3f}")

    best = max(is_exp, key=is_exp.get)
    print(f"\n>> theta elegido en IS = {best} (mejor expectancy in-sample)")

    # OOS del theta elegido, detalle por simbolo + baseline
    allt, base = [], []
    for s, df in data.items():
        allt += [(s,) + t for t in run_symbol(df, best, df.split.iloc[0])]
        base += run_symbol(df, best, df.split.iloc[0], random_mode=True, seed=hash(s) % 999)
    oos = [t for t in allt if t[4] == "OOS"]
    Roos = [t[2] for t in oos]
    bo = stat([t[1] for t in base if t[3] == "OOS"])
    so = stat(Roos)
    print(f"\nVEREDICTO OOS (theta={best}):")
    if so:
        yrs = (max(t[1] for t in oos) - min(t[1] for t in oos)) / (BARS_YR * 5 * 60 * 1000) if oos else 1
        tpy = so["n"] / max(yrs, 1e-9)
        print(f"  trades={so['n']}  exp={so['exp']:+.3f}R  wr={so['wr']:.1%}  PF={so['pf']:.2f}  "
              f"sumR={so['sumR']:+.1f}  Sharpe/trade={so['sh']:+.3f}  (~{tpy:.0f} trades/ano)")
        print(f"  Sharpe anualizado aprox = {so['sh']*np.sqrt(max(tpy,1)):+.2f}")
    if bo:
        print(f"  baseline ALEATORIO OOS: exp={bo['exp']:+.3f}R wr={bo['wr']:.1%} PF={bo['pf']:.2f} (n={bo['n']})")
    print(f"\n  Por simbolo (OOS, theta={best}):")
    for s in data:
        Rs = [t[2] for t in oos if t[0] == s]
        st = stat(Rs)
        if st:
            print(f"    {s:>4}: n={st['n']:>4} exp={st['exp']:+.3f}R wr={st['wr']:.1%} PF={st['pf']:.2f} sumR={st['sumR']:+.1f}")


if __name__ == "__main__":
    main()
