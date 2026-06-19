# -*- coding: utf-8 -*-
"""
================================================================================
  magnet_multibt — backtest MULTI-SIMBOLO del motor de imanes (OKX 5m real)
  by RasDG_Sol + Claude
================================================================================
Prueba la tesis liquidez-seeking en varios pares para ver DONDE rinde/paga mejor.
Baja (o cachea) el historico de cada instId, corre el backtest vectorizado y arma
una tabla RANKEADA por expectancy (edge por trade), con drawdown, WR, R total y
desglose por modo. Guarda un reporte markdown objetivo.

Uso:
    python tools/magnet_multibt.py              # canasta default, n=15000, rr=1.5
    python tools/magnet_multibt.py --n 20000 --min-rr 2.0 --out research/magnet_multi.md
================================================================================
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import fetch_okx
import magnet_backtest as mb

BASKET = [
    "BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "XRP-USDT-SWAP",
    "DOGE-USDT-SWAP", "BNB-USDT-SWAP", "LTC-USDT-SWAP", "ADA-USDT-SWAP",
]


def _load(sym, bar, n, cache_dir):
    path = os.path.join(cache_dir, "%s_%s.parquet" % (sym, bar))
    if os.path.exists(path):
        df = pd.read_parquet(path)
        if len(df) >= n * 0.8:
            return df
    df = fetch_okx.fetch(sym, bar, n)
    if not df.empty:
        os.makedirs(cache_dir, exist_ok=True)
        df.to_parquet(path, index=False)
    return df


def run_basket(symbols, *, bar="5m", n=15000, step=1, min_rr=1.5,
               cache_dir="data/okx"):
    out = []
    for s in symbols:
        df = _load(s, bar, n, cache_dir)
        if df.empty or len(df) < 300:
            print("[multi] %s: sin data suficiente, skip" % s)
            continue
        r = mb.run(df, step=step, min_rr=min_rr)
        days = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]) / 8.64e7 \
            if "timestamp" in df.columns else len(df) * 5 / 1440.0
        r.update({"symbol": s, "bars": len(df), "days": days})
        out.append(r)
        print("[multi] %-16s trades=%-4d WR=%4.0f%% exp=%+.3fR total=%+6.1fR DD=%4.1f%%" % (
            s, r["n_trades"], (r["win_rate"] or 0) * 100,
            r["expectancy_r"] or 0, r["total_r"], r["max_drawdown"] * 100))
    out.sort(key=lambda r: (r["expectancy_r"] if r["expectancy_r"] is not None else -9),
             reverse=True)
    return out


def to_markdown(results, *, bar, n, min_rr):
    lines = []
    lines.append("# Backtest multi-simbolo — Motor de Imanes (v1)\n")
    lines.append("OKX %s, ~%d velas/par, paso 1, min_rr=%.2f, trades NO solapados, "
                 "etiquetado pesimista (empate TP/SL -> SL), costes via bt_engine.\n"
                 % (bar, n, min_rr))
    lines.append("> v1 honesto: el stop ('apenas pasado el iman opuesto cercano') es "
                 "demasiado ajustado. Esta tabla es la LINEA BASE para iterar.\n")
    lines.append("| Par | dias | trades | WR | exp (R) | total (R) | maxDD | mejor modo |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for r in results:
        bm = max(r["by_mode"].items(), key=lambda kv: kv[1]["expectancy_r"],
                 default=("-", {"expectancy_r": 0, "n": 0}))
        lines.append("| %s | %.0f | %d | %.0f%% | %+.3f | %+.1f | %.1f%% | %s (%+.2fR n%d) |" % (
            r["symbol"], r["days"], r["n_trades"], (r["win_rate"] or 0) * 100,
            r["expectancy_r"] or 0, r["total_r"], r["max_drawdown"] * 100,
            bm[0], bm[1]["expectancy_r"], bm[1]["n"]))
    return "\n".join(lines) + "\n"


def main(argv):
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 15000
    min_rr = float(argv[argv.index("--min-rr") + 1]) if "--min-rr" in argv else 1.5
    out = argv[argv.index("--out") + 1] if "--out" in argv else "research/magnet_multi.md"
    bar = argv[argv.index("--bar") + 1] if "--bar" in argv else "5m"
    res = run_basket(BASKET, bar=bar, n=n, min_rr=min_rr)
    if not res:
        print("[multi] sin resultados")
        return 1
    md = to_markdown(res, bar=bar, n=n, min_rr=min_rr)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        f.write(md)
    with open(out.replace(".md", ".json"), "w") as f:
        json.dump(res, f, indent=2, default=float)
    print("\n" + md)
    print("[multi] reporte -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
