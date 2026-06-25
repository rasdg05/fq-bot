# -*- coding: utf-8 -*-
"""
pairs_backtest — stat-arb BTC-ETH market-neutral (cointegracion + z-score).

El motor del bot es DIRECCIONAL (Sharpe ~0.8). La investigacion 2026: el dinero
durable esta MARKET-NEUTRAL (carry/basis/pairs, Sharpe 2-5). Esto prototipa el
pairs BTC-ETH:
  spread = logETH - beta*logBTC   (beta = hedge ratio ROLLING, causal)
  z = (spread - rolling_mean)/rolling_std
  entra al extremo (|z|>=enter), sale a la media (|z|<=exit). Dollar-neutral via
  el hedge ratio -> exposicion direccional ~0.

CAUSAL: beta y z usan SOLO ventana pasada (sin look-ahead). NETO de costos
(fee por pierna x 2 piernas x entrada/salida). ADF manual (sin statsmodels):
t-stat del coef de reversion + half-life OU. Walk-forward IS/OOS + sweep.

Uso: python tools/pairs_backtest.py [A B]   (default BTC ETH)
"""
import sys
import numpy as np
import pandas as pd

ANN = np.sqrt(288 * 365)   # anualizacion de Sharpe sobre retornos 5m


def load_pair(a, b):
    da = pd.read_parquet("data/okx/%s-USDT-SWAP_5m.parquet" % a)[["timestamp", "close"]]
    db = pd.read_parquet("data/okx/%s-USDT-SWAP_5m.parquet" % b)[["timestamp", "close"]]
    df = da.rename(columns={"close": "a"}).merge(
        db.rename(columns={"close": "b"}), on="timestamp").sort_values("timestamp").reset_index(drop=True)
    df["la"] = np.log(df["a"]); df["lb"] = np.log(df["b"])
    return df


def adf_tstat(x):
    """ADF-ish: regresa d(x) ~ x_lag (+const). t-stat del coef de reversion + half-life.
    t-stat < ~-2.86 => estacionario al 5% (cointegrado)."""
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    dx = np.diff(x); xl = x[:-1]
    X = np.column_stack([np.ones_like(xl), xl])
    beta, *_ = np.linalg.lstsq(X, dx, rcond=None)
    resid = dx - X @ beta
    s2 = (resid @ resid) / (len(dx) - 2)
    se = np.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
    lam = beta[1]
    t = lam / se
    hl = -np.log(2) / lam if lam < 0 else np.inf
    return t, hl


def _rolling_beta(la, lb, win):
    s = pd.Series(la); t = pd.Series(lb)
    return (t.rolling(win).cov(s) / s.rolling(win).var()).values


def backtest(df, beta_win=2016, z_win=288, enter=2.0, exit=0.5, fee=0.0005):
    la, lb = df["la"].values, df["lb"].values
    beta = _rolling_beta(la, lb, beta_win)
    spread = lb - beta * la
    sp = pd.Series(spread)
    z = ((sp - sp.rolling(z_win).mean()) / sp.rolling(z_win).std()).values
    n = len(z)
    pos = np.zeros(n); cur = 0
    for i in range(1, n):
        if np.isnan(z[i]) or np.isnan(beta[i]):
            cur = 0
        elif cur == 0:
            if z[i] >= enter: cur = -1          # spread caro -> short spread (short B / long A)
            elif z[i] <= -enter: cur = 1         # spread barato -> long spread
        elif abs(z[i]) <= exit:
            cur = 0
        pos[i] = cur
    # retorno TRADEABLE: pos * (dlogB - beta*dlogA) con cambios de PRECIO y el hedge
    # al inicio de la barra. NO usar d(nivel del spread): mete el drift de beta (spurio).
    dla = np.diff(la, prepend=la[0])
    dlb = np.diff(lb, prepend=lb[0])
    beta_prev = np.roll(beta, 1)
    gross = np.roll(pos, 1) * (dlb - beta_prev * dla)
    gross[0] = 0
    turn = np.abs(np.diff(pos, prepend=0))
    cost = 2.0 * turn * fee                       # 2 piernas por unidad de cambio
    net = gross - cost
    valid = ~np.isnan(net)
    net = np.where(valid, net, 0.0)
    rt = int((np.diff(pos, prepend=0) != 0).sum() / 2)  # round-trips aprox
    sharpe = (net.mean() / net.std() * ANN) if net.std() > 0 else 0.0
    eq = np.cumsum(net)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    days = n / 288.0
    apy = float(net.sum() / days * 365)           # retorno log anualizado (por notional A)
    in_mkt = float((pos != 0).mean())
    return {"sharpe": sharpe, "apy": apy, "maxdd": dd, "rt": rt,
            "in_mkt": in_mkt, "net_sum": float(net.sum()), "n": n}


def main(argv):
    a, b = (argv[1], argv[2]) if len(argv) > 2 else ("BTC", "ETH")
    df = load_pair(a, b)
    print("================ PAIRS %s-%s  (%d velas 5m, %.0f dias) ================"
          % (a, b, len(df), len(df) / 288))

    # 1) cointegracion (spread con beta OLS global, solo para el test)
    beta_g = np.polyfit(df["la"], df["lb"], 1)[0]
    t, hl = adf_tstat(df["lb"] - beta_g * df["la"])
    print("\n[1] COINTEGRACION (ADF manual):  beta=%.3f  t-stat=%.2f  (%s)  half-life=%.0f velas (%.1f h)"
          % (beta_g, t, "ESTACIONARIO/cointegra" if t < -2.86 else "NO claro", hl, hl * 5 / 60))

    # 2) backtest base + maker vs taker
    print("\n[2] BACKTEST base (beta_win=2016/1sem, z_win=288/1d, enter=2, exit=0.5)")
    for lab, fee in [("taker 5bps", 0.0005), ("maker 2bps", 0.0002), ("sin costo", 0.0)]:
        r = backtest(df, fee=fee)
        print("    %-11s Sharpe=%5.2f  APY=%+6.1f%%  maxDD=%.3f  round-trips=%d  %%enmercado=%.0f%%"
              % (lab, r["sharpe"], r["apy"] * 100, r["maxdd"], r["rt"], r["in_mkt"] * 100))

    # 3) walk-forward IS/OOS (maker)
    print("\n[3] WALK-FORWARD IS/OOS (maker 2bps)")
    mid = len(df) // 2
    for lab, d in [("IS (1a mitad)", df.iloc[:mid]), ("OOS (2a mitad)", df.iloc[mid:].reset_index(drop=True))]:
        r = backtest(d, fee=0.0002)
        print("    %-15s Sharpe=%5.2f  APY=%+6.1f%%  round-trips=%d" % (lab, r["sharpe"], r["apy"] * 100, r["rt"]))

    # 4) sweep de params (maker)
    print("\n[4] SWEEP (maker 2bps) — Sharpe por config")
    print("    %-9s %-7s %-6s %-6s | Sharpe   APY     RT" % ("beta_win", "z_win", "enter", "exit"))
    best = None
    for bw in (576, 2016, 4032):
        for zw in (144, 288, 576):
            for en in (2.0, 2.5):
                for ex in (0.25, 0.5):
                    r = backtest(df, beta_win=bw, z_win=zw, enter=en, exit=ex, fee=0.0002)
                    if best is None or r["sharpe"] > best[0]:
                        best = (r["sharpe"], bw, zw, en, ex, r)
    print("    -> MEJOR: beta_win=%d z_win=%d enter=%.1f exit=%.1f | Sharpe=%.2f APY=%+.1f%% RT=%d"
          % (best[1], best[2], best[3], best[4], best[0], best[5]["apy"] * 100, best[5]["rt"]))
    print("\n(radar: 7 meses, una ventana. El Sharpe direccional del motor ~0.8 es la vara a batir.)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
