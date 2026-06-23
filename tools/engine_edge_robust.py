# -*- coding: utf-8 -*-
"""
engine_edge_robust.py - Validacion ROBUSTA del edge del motor + de DONDE sale.

Corrige el cube a UNA fila por senal (mean entre las 12 variantes de TP -> no
cherry-pick). Responde "de donde viene el edge?" con la descomposicion
gross / maker / taker, y lo valida con herramientas para retornos CORRELACIONADOS:
  - block bootstrap (resamplea bloques temporales -> IC honesto del expectancy)
  - walk-forward (folds temporales consecutivos -> estable o artefacto de 1 split?)
  - sensibilidad al fee, por simbolo.

Pure numpy/pandas. CONSTRAINTS 7.
"""
import numpy as np
import pandas as pd

CUBES = {"SOL": "cosecha_cubes/tp_cube_SOL_USDT.parquet",
         "BTC": "cosecha_cubes/tp_cube_BTC_USDT.parquet"}
FEE_MAKER = 0.0004
FEE_TAKER = 0.0010


def per_signal():
    df = pd.concat([pd.read_parquet(p).assign(symbol=s) for s, p in CUBES.items()], ignore_index=True)
    df = df[(df.fired == True) & df.pnl_r.notna()].copy()
    df["entry_ts"] = pd.to_datetime(df.entry_ts)
    risk = (df.entry_price - df.stop_price).abs()
    df["fee_m"] = (FEE_MAKER * df.entry_price / risk.replace(0, np.nan)).clip(0, 2)
    df["fee_t"] = (FEE_TAKER * df.entry_price / risk.replace(0, np.nan)).clip(0, 2)
    g = df.groupby(["symbol", "entry_index"])
    per = g.agg(entry_ts=("entry_ts", "first"), direction=("direction", "first"),
                gross=("pnl_r", "mean"), fee_m=("fee_m", "first"), fee_t=("fee_t", "first")).reset_index()
    per["net_m"] = per.gross - per.fee_m
    per["net_t"] = per.gross - per.fee_t
    return per.sort_values("entry_ts").reset_index(drop=True)


def block_boot(x, L=20, B=4000, seed=0):
    x = np.asarray(x, float); x = x[np.isfinite(x)]; n = len(x)
    rng = np.random.default_rng(seed); nb = int(np.ceil(n / L)); out = np.empty(B)
    for b in range(B):
        idx = np.concatenate([np.arange(s, s + L) for s in rng.integers(0, max(1, n - L + 1), nb)])[:n]
        out[b] = x[idx].mean()
    return out


def line(tag, R):
    R = np.asarray(R, float); R = R[np.isfinite(R)]
    pf = R[R > 0].sum() / max(-R[R < 0].sum(), 1e-9)
    print(f"  {tag:<26} n={len(R):>4} exp={R.mean():+.3f}R wr={(R>0).mean():.1%} PF={pf:.2f}")


def main():
    per = per_signal()
    n = len(per)
    print(f"SENALES DISTINTAS: {n}  ({per.entry_ts.min().date()} -> {per.entry_ts.max().date()})\n")

    print("== DE DONDE SALE EL EDGE? (descomposicion) ==")
    line("GROSS (sin costo)", per.gross)
    line("neto MAKER (limite)", per.net_m)
    line("neto TAKER (mercado)", per.net_t)
    print(f"  -> edge PREDICTIVO (gross) = +{per.gross.mean():.3f}R  [lo aporta la SELECCION]")
    print(f"  -> el maker MANTIENE {per.net_m.mean()/per.gross.mean()*100:.0f}% del gross; el taker lo funde a {per.net_t.mean():+.3f}R")

    print("\n== BLOCK BOOTSTRAP (neto maker, IC robusto a correlacion) ==")
    bm = block_boot(per.net_m.values)
    lo, hi = np.percentile(bm, [2.5, 97.5])
    print(f"  exp={per.net_m.mean():+.3f}R  IC95% = [{lo:+.3f}, {hi:+.3f}]  P(exp<=0)={(bm<=0).mean():.3f}")
    print(f"  -> {'IC por ENCIMA de 0: edge robusto' if lo>0 else 'IC cruza 0: edge no concluyente'}")
    # gross para contraste
    bg = block_boot(per.gross.values); glo, ghi = np.percentile(bg, [2.5, 97.5])
    print(f"  gross IC95% = [{glo:+.3f}, {ghi:+.3f}]  P(gross<=0)={(bg<=0).mean():.3f}")

    print("\n== WALK-FORWARD (6 folds temporales consecutivos, neto maker) ==")
    folds = np.array_split(np.arange(len(per)), 6)
    pos = 0
    for i, idx in enumerate(folds):
        f = per.iloc[idx]
        m = f.net_m.mean(); pos += m > 0
        print(f"  fold {i+1} [{f.entry_ts.min().date()}..{f.entry_ts.max().date()}] "
              f"n={len(f):>3} exp={m:+.3f}R {'+' if m>0 else '-'}")
    print(f"  -> {pos}/6 folds positivos")

    print("\n== por simbolo (neto maker, IC bootstrap) ==")
    for s in CUBES:
        sub = per[per.symbol == s]
        b = block_boot(sub.net_m.values); l, h = np.percentile(b, [2.5, 97.5])
        print(f"  {s}: exp={sub.net_m.mean():+.3f}R IC95%=[{l:+.3f},{h:+.3f}] n={len(sub)}")

    print("\n== sensibilidad al fee (neto, bps round-trip) ==")
    for bps in (0, 2, 4, 6, 8, 10):
        fee = bps / 1e4
        risk_proxy = per.fee_m / FEE_MAKER  # = entry/risk
        netR = per.gross - (fee * risk_proxy).clip(0, 2)
        print(f"  {bps:>2}bps: exp={netR.mean():+.3f}R")
    print("\n  (maker real ~2-4bps; taker ~8-10bps -> el fee decide signo)")


if __name__ == "__main__":
    main()
