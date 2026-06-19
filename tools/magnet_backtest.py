# -*- coding: utf-8 -*-
"""
================================================================================
  magnet_backtest — backtest del MOTOR DE IMANES sobre 5m (alta densidad, paso 1)
  by RasDG_Sol + Claude
================================================================================
Mide el DRAWDOWN (y expectancy / win-rate / R total) de las senales del motor de
imanes (liquidity_magnet.best_target), recorriendo el historico vela a vela (paso 1)
y pasando cada trade por bt_engine (costes reales -> curva de equity neta).

Honestidad: NO reimplementa costes (bt_engine es la fuente). Mide la propia
estrategia (los imanes) tal cual dispara, con etiquetado pesimista (si una vela toca
TP y SL, gana el STOP) = misma convencion que el research.

Uso:
    python tools/magnet_backtest.py <ruta.csv|.parquet> [--step 1] [--min-rr 1.5]
    # el archivo debe traer columnas: open, high, low, close, volume (5m)

El motor usa solo VWAP/cloud de MAs/max-min previos cuando field=None (esta version);
los pools de ict_smc se inyectan con --field (refinamiento posterior).
================================================================================
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

import liquidity_magnet as lm
import bt_engine

WARMUP = 50          # velas de calentamiento (MAs / imanes)


def label_magnet_trades(df, *, step=1, min_rr=1.5, max_hold=200, field_fn=None):
    """Recorre el df (paso `step`) generando senales del motor y etiqueta el
    desenlace mirando ADELANTE (que toca primero, TP o STOP; empate -> STOP).
    Devuelve un DataFrame listo para bt_engine.simulate (entry_price, stop_price,
    exit_price, direction in {+1,-1}, bars_held) + columnas mode/outcome."""
    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    closes = df["close"].astype(float).to_numpy()
    n = len(df)
    rows = []
    i = WARMUP
    while i < n - 1:
        sub = df.iloc[:i + 1]
        field = field_fn(sub) if field_fn else None
        sig = lm.best_target(sub, field, closes[i], min_rr=min_rr)
        if sig:
            d = 1 if sig["direction"] == "long" else -1
            entry, stop, tp = sig["entry"], sig["stop"], sig["tp"]
            exit_px = bars = outcome = None
            for j in range(i + 1, min(i + 1 + max_hold, n)):
                if d > 0:
                    hit_sl, hit_tp = lows[j] <= stop, highs[j] >= tp
                else:
                    hit_sl, hit_tp = highs[j] >= stop, lows[j] <= tp
                if hit_sl:                      # pesimista: el stop gana el empate
                    exit_px, bars, outcome = stop, j - i, "loss"
                    break
                if hit_tp:
                    exit_px, bars, outcome = tp, j - i, "win"
                    break
            if exit_px is not None:
                rows.append({"entry_price": entry, "stop_price": stop,
                             "exit_price": exit_px, "direction": d,
                             "bars_held": bars, "outcome": outcome, "mode": sig["mode"]})
        i += step
    return pd.DataFrame(rows)


def _max_drawdown(equity):
    eq = np.asarray(equity, dtype=float)
    if len(eq) == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.where(peak > 0, peak, 1.0)
    return float(dd.max())


def run(df, *, step=1, min_rr=1.5, bar_minutes=5.0, cost=None):
    """Backtest completo: etiqueta -> bt_engine -> metricas. Devuelve dict con
    n_trades, win_rate, expectancy_r (gross), total_r, max_drawdown (neto),
    final_equity y desglose por modo (continuation/reversal)."""
    trades = label_magnet_trades(df, step=step, min_rr=min_rr)
    out = {"n_trades": int(len(trades))}
    if trades.empty:
        out.update({"win_rate": None, "expectancy_r": None, "total_r": 0.0,
                    "max_drawdown": 0.0, "final_equity": None, "by_mode": {}})
        return out
    # R gross por trade (precio puro, sin costes) para expectancy/WR
    d = trades["direction"].to_numpy(dtype=float)
    rdist = (trades["entry_price"] - trades["stop_price"]).abs().to_numpy()
    pnl_r = d * (trades["exit_price"].to_numpy() - trades["entry_price"].to_numpy()) / rdist
    trades = trades.assign(pnl_r=pnl_r)
    # equity NETA via bt_engine (costes reales) -> drawdown
    res = bt_engine.simulate(trades, bar_minutes=bar_minutes, cost=cost or bt_engine.CostModel())
    by_mode = {m: {"n": int((trades["mode"] == m).sum()),
                   "expectancy_r": float(trades.loc[trades["mode"] == m, "pnl_r"].mean())}
               for m in sorted(trades["mode"].unique())}
    out.update({
        "win_rate": float((trades["outcome"] == "win").mean()),
        "expectancy_r": float(pnl_r.mean()),
        "total_r": float(pnl_r.sum()),
        "max_drawdown": _max_drawdown(res["equity_curve"]),
        "final_equity": float(res["final_equity"]),
        "by_mode": by_mode,
    })
    return out


def _load(path):
    if path.endswith(".parquet"):
        return pd.read_parquet(path)
    return pd.read_csv(path)


def main(argv):
    if len(argv) < 2:
        print("uso: python tools/magnet_backtest.py <ruta.csv|.parquet> [--step N] [--min-rr R]")
        return 2
    path = argv[1]
    step = int(argv[argv.index("--step") + 1]) if "--step" in argv else 1
    min_rr = float(argv[argv.index("--min-rr") + 1]) if "--min-rr" in argv else 1.5
    if not os.path.exists(path):
        print("[magnet-bt] no existe: %s" % path)
        return 2
    df = _load(path)
    r = run(df, step=step, min_rr=min_rr)
    print("[magnet-bt] %s  velas=%d  step=%d  min_rr=%.2f" % (path, len(df), step, min_rr))
    if not r["n_trades"]:
        print("  sin trades (subi la densidad o baja --min-rr).")
        return 1
    print("  trades=%d  WR=%.1f%%  exp=%+.3fR  total=%+.1fR" % (
        r["n_trades"], r["win_rate"] * 100, r["expectancy_r"], r["total_r"]))
    print("  MAX DRAWDOWN (neto) = %.1f%%   equity_final=%.0f" % (
        r["max_drawdown"] * 100, r["final_equity"]))
    for m, s in r["by_mode"].items():
        print("    [%s] n=%d  exp=%+.3fR" % (m, s["n"], s["expectancy_r"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
