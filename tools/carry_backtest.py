# -*- coding: utf-8 -*-
"""
================================================================================
  carry_backtest — backtest de FUNDING CARRY (delta-neutral) sobre OKX perps
  by RasDG_Sol + Claude
================================================================================
La ruta con edge COMPROBADO (research): short perp + long spot (delta-neutral) cobra
el funding cuando es positivo. Mide, con funding-rate real de OKX:
  - always-on: mantener siempre la posicion (cobras funding+ , pagas funding-)
  - selective: mantener solo cuando el funding viene positivo (persistencia, causal),
    flat el resto, pagando coste al cambiar de estado.
Reporta APY neto, Sharpe (del retorno de funding), drawdown del carry acumulado,
% de intervalos con funding positivo. carry_metrics() es PURO -> testeable.

OKX paga funding cada 8h (3/dia). El retorno modelado es el funding cobrado/pagado
(la pata de precio esta hedgeada por el spot); costes = apertura + cambios de estado.

Uso: python tools/carry_backtest.py [--n 3000] [--threshold 0.0] [--out research/carry.md]
================================================================================
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

import fetch_okx_funding

BASKET = [
    "BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "XRP-USDT-SWAP",
    "DOGE-USDT-SWAP", "BNB-USDT-SWAP", "LTC-USDT-SWAP", "ADA-USDT-SWAP",
]

# Subconjunto VALIDADO multi-régimen (funding profundo Binance 2021-2026, por año):
# estos 6 cobran funding POSITIVO en TODOS los años, incluido el bear 2022 (+1.7% APY).
# Se excluyen SOL (carry muerto: Sharpe 0.27, maxDD 43%) y BNB (funding MEDIO negativo:
# 22% positivo -> es anti-carry, el long cobra). Fuente: fetch_binance_vision_funding.
# Basket CLEAN always-on full-history: +12.5% APY, Sharpe 13.6, maxDD 1.7%, 82% positivo.
CLEAN_BASKET = [
    "BTC-USDT-SWAP", "ETH-USDT-SWAP", "XRP-USDT-SWAP",
    "LTC-USDT-SWAP", "DOGE-USDT-SWAP", "ADA-USDT-SWAP",
]
ANTI_CARRY = ["SOL-USDT-SWAP", "BNB-USDT-SWAP"]   # excluidos del basket (medido)


def carry_metrics(funding, *, intervals_per_day=3, cost_bps_per_switch=5.0,
                  entry_cost_bps=5.0, threshold=0.0, selective=False):
    """funding: tasas por intervalo (8h). Short-perp delta-neutral: cobras funding>0,
    pagas funding<0. Devuelve apy (neto), sharpe (anualizado), max_dd_frac (drawdown
    del carry acumulado), pct_positive, total_return, mean_funding_bps, n."""
    f = np.asarray(funding, dtype=float)
    out = {"apy": 0.0, "sharpe": 0.0, "max_dd_frac": 0.0, "pct_positive": 0.0,
           "total_return": 0.0, "mean_funding_bps": 0.0, "n": int(len(f))}
    if len(f) == 0:
        return out
    if selective:
        held = np.zeros(len(f), dtype=bool)
        held[1:] = f[:-1] > threshold              # causal: decide con el funding previo
        ret = np.where(held, f, 0.0)
        switches = int(np.sum(held[1:] != held[:-1])) + int(held[0])
        cost = switches * (cost_bps_per_switch / 1e4)
    else:
        ret = f.copy()                             # always-on
        cost = entry_cost_bps / 1e4
    periods_year = intervals_per_day * 365.0
    years = len(f) / periods_year
    total = float(ret.sum() - cost)
    cum = np.cumsum(ret)
    peak = np.maximum.accumulate(cum)
    out.update({
        "apy": (total / years) if years > 0 else 0.0,
        "sharpe": float(ret.mean() / ret.std() * np.sqrt(periods_year)) if ret.std() > 0 else 0.0,
        "max_dd_frac": float((peak - cum).max()),
        "pct_positive": float((f > 0).mean()),
        "total_return": total,
        "mean_funding_bps": float(f.mean() * 1e4),
        "n": int(len(f)),
    })
    return out


def _load(sym, n, cache_dir):
    path = os.path.join(cache_dir, "%s_funding.parquet" % sym)
    if os.path.exists(path):
        df = pd.read_parquet(path)
        if len(df) >= n * 0.8:
            return df
    df = fetch_okx_funding.fetch(sym, n)
    if not df.empty:
        os.makedirs(cache_dir, exist_ok=True)
        df.to_parquet(path, index=False)
    return df


def run_basket(symbols, *, n=3000, threshold=0.0, cache_dir="data/okx"):
    out = []
    for s in symbols:
        df = _load(s, n, cache_dir)
        if df.empty or len(df) < 100:
            print("[carry] %s: sin data, skip" % s)
            continue
        f = df["fundingRate"].to_numpy()
        always = carry_metrics(f, selective=False)
        sel = carry_metrics(f, selective=True, threshold=threshold)
        days = (df["fundingTime"].iloc[-1] - df["fundingTime"].iloc[0]) / 8.64e7
        out.append({"symbol": s, "days": days, "always": always, "selective": sel})
        print("[carry] %-14s %4.0fd  always APY %+5.1f%% (Sh %.2f, DD %.1f%%, %+.3fbps, %3.0f%%+)  "
              "selective APY %+5.1f%% (DD %.1f%%)" % (
                  s, days, always["apy"] * 100, always["sharpe"], always["max_dd_frac"] * 100,
                  always["mean_funding_bps"], always["pct_positive"] * 100,
                  sel["apy"] * 100, sel["max_dd_frac"] * 100))
    out.sort(key=lambda r: r["always"]["apy"], reverse=True)
    return out


def to_markdown(results, *, n, threshold):
    lines = ["# Backtest de FUNDING CARRY — OKX perps (ruta con edge comprobado)\n"]
    lines.append("Funding real OKX (8h), ~%d puntos/par. 'always' = short-perp delta-"
                 "neutral siempre; 'selective' = solo cuando el funding previo > %.4f%%. "
                 "APY neto de costes (apertura/cambios 5bps). DD = del carry acumulado.\n"
                 % (n, threshold * 100))
    lines.append("> Honesto: el carry es una PRIMA DE RIESGO, no arbitraje sin riesgo "
                 "(funding puede ir negativo en bear; hay riesgo de contraparte/liquidacion "
                 "de la pata short). Pero a diferencia del direccional, no te liquida la cuenta.\n")
    lines.append("| Par | dias | APY always | Sharpe | DD carry | funding medio | %+ | APY selective |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in results:
        a, s = r["always"], r["selective"]
        lines.append("| %s | %.0f | %+.1f%% | %.2f | %.1f%% | %+.3f bps | %.0f%% | %+.1f%% |" % (
            r["symbol"], r["days"], a["apy"] * 100, a["sharpe"], a["max_dd_frac"] * 100,
            a["mean_funding_bps"], a["pct_positive"] * 100, s["apy"] * 100))
    return "\n".join(lines) + "\n"


def main(argv):
    def opt(flag, d, cast=str):
        return cast(argv[argv.index(flag) + 1]) if flag in argv else d
    n = opt("--n", 3000, int)
    threshold = opt("--threshold", 0.0, float)
    out = opt("--out", "research/carry.md")
    res = run_basket(BASKET, n=n, threshold=threshold)
    if not res:
        print("[carry] sin resultados")
        return 1
    md = to_markdown(res, n=n, threshold=threshold)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        f.write(md)
    with open(out.replace(".md", ".json"), "w") as f:
        json.dump(res, f, indent=2, default=float)
    print("\n" + md)
    print("[carry] reporte -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
