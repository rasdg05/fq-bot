# -*- coding: utf-8 -*-
"""
maker_fill_test.py - El test make-or-break: el fill de la limite maker.

El edge neto maker (+0.109R) asume que una limite pasiva en entry_price SE LLENA.
Aca lo simulamos contra el OHLC 5m real: para cada senal, una limite en entry_price
¿se habria tocado dentro de una ventana?, y los NO-fills ¿son desproporcionadamente
ganadores (adverse selection)?

Limitacion honesta: el OHLC 5m que tengo cubre ~7 meses (2025-11..2026-06); el cube
va a 2019/2021 -> solo se testea el overlap reciente (~200 senales). Suficiente para
ver la DIRECCION de la seleccion adversa, no para un numero de precision.

Modelo de fill (causal): senal en bar i. Limite descansa en bars i+1..i+W. Llena si
el rango de algun bar toca entry_price (long: low<=ep ; short: high>=ep). Si no toca
en W bars -> NO-fill (la oportunidad se fue sin vos).

Pure numpy/pandas. CONSTRAINTS 7.
"""
import numpy as np
import pandas as pd

CUBES = {"SOL": "cosecha_cubes/tp_cube_SOL_USDT.parquet",
         "BTC": "cosecha_cubes/tp_cube_BTC_USDT.parquet"}
OHLC = "data/okx/{}-USDT-SWAP_5m.parquet"
FEE_MAKER = 0.0004
WINDOWS = [3, 6, 12, 24, 48]


def atr_wilder(df, n=14):
    h = df.high.to_numpy(float); l = df.low.to_numpy(float); c = df.close.to_numpy(float)
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def per_signal():
    df = pd.concat([pd.read_parquet(p).assign(symbol=s) for s, p in CUBES.items()], ignore_index=True)
    df = df[(df.fired == True) & df.pnl_r.notna()].copy()
    g = df.groupby(["symbol", "entry_index"])
    per = g.agg(entry_ts=("entry_ts", "first"), entry_price=("entry_price", "first"),
                stop_price=("stop_price", "first"), direction=("direction", "first"),
                pnl=("pnl_r", "mean")).reset_index()
    return per


def build(symbol, per):
    oh = pd.read_parquet(OHLC.format(symbol))
    t = oh.timestamp.to_numpy(); c = oh.close.to_numpy(float)
    h = oh.high.to_numpy(float); l = oh.low.to_numpy(float)
    atr = atr_wilder(oh)
    sub = per[per.symbol == symbol].copy()
    sub["ms"] = sub.entry_ts.astype("datetime64[ms]").astype("int64")
    sub = sub[(sub.ms >= t.min()) & (sub.ms <= t.max())].reset_index(drop=True)
    if len(sub) == 0:
        return sub
    idx = np.clip(np.searchsorted(t, sub.ms.to_numpy()), 1, len(oh) - 2)
    ep = sub.entry_price.to_numpy(); dirn = sub.direction.to_numpy()
    risk = np.abs(ep - sub.stop_price.to_numpy())
    fee = np.clip(FEE_MAKER * ep / np.where(risk > 0, risk, np.nan), 0, 2)
    sub["net"] = sub.pnl.to_numpy() - fee
    sub["off_atr"] = (ep - c[idx]) / atr[idx] * dirn   # >0 = limite mas alla en direccion
    for W in WINDOWS:
        filled = np.zeros(len(sub), bool)
        for k in range(len(sub)):
            i = idx[k]
            for j in range(i + 1, min(i + 1 + W, len(oh))):
                if (dirn[k] == 1 and l[j] <= ep[k]) or (dirn[k] == -1 and h[j] >= ep[k]):
                    filled[k] = True; break
        sub[f"fill_{W}"] = filled
    return sub


def main():
    per = per_signal()
    parts = [build(s, per) for s in CUBES]
    df = pd.concat([p for p in parts if len(p)], ignore_index=True)
    print(f"OVERLAP cube<->OHLC 5m: {len(df)} senales "
          f"({pd.to_datetime(df.entry_ts).min().date()} -> {pd.to_datetime(df.entry_ts).max().date()})")
    print(f"offset (entry-close)/ATR en direccion: mediana={df.off_atr.median():+.2f} "
          f"| limite que descansa (>0.1): {(df.off_atr>0.1).mean():.0%}  marketable(<=0.1): {(df.off_atr<=0.1).mean():.0%}")
    base = df.net.mean()
    print(f"\nexpectancy si TODAS llenan (neto maker) = {base:+.3f}R  (n={len(df)})\n")
    print(f"{'W bars':>6} {'fill%':>6} {'exp FILLED':>11} {'exp MISSED':>11} {'adverse':>8} {'exp realista*':>13}")
    print("-" * 62)
    for W in WINDOWS:
        f = df[f"fill_{W}"]
        ef = df[f].net.mean() if f.any() else np.nan
        em = df[~f].net.mean() if (~f).any() else np.nan
        adv = (em - ef)
        # realista: solo cobras los fills; las no-fills no generan pnl (oportunidad perdida)
        print(f"{W:>6} {f.mean():>6.0%} {ef:>+11.3f} {em:>+11.3f} {adv:>+8.3f} {ef:>+13.3f}")
    print("\n* exp realista = expectancy de las que SI llenan (lo unico que cobras).")
    print("  adverse>0 => las no-fills eran mejores (perdes ganadores). Si exp FILLED")
    print("  sigue ~ +0.10R y > 0 con holgura, el edge sobrevive al fill.")
    # por simbolo a W=12
    print("\nPor simbolo (W=12):")
    for s in CUBES:
        d = df[df.symbol == s]; f = d["fill_12"]
        if len(d):
            print(f"  {s}: n={len(d)} fill={f.mean():.0%} exp_filled={d[f].net.mean():+.3f}R exp_missed={d[~f].net.mean() if (~f).any() else float('nan'):+.3f}R")


if __name__ == "__main__":
    main()
