# -*- coding: utf-8 -*-
"""
bt_optimize (FASE C): grid post-replay SL(xATR) x TP. Validamos que re-etiqueta
el mismo conjunto fired variando SL/TP sin re-replicar, que la tabla tiene una
celda por (SL,TP), que el TP cercano (tp1) gana mas seguido que el lejano (tp4)
en una serie alcista, y que choose_optimum elige el maximo.
"""
import numpy as np
import pandas as pd
import pytest

import bt_optimize as opt
import bt_engine as eng


def _rising_df(n=400, start=100.0, slope=0.1):
    """Serie OHLCV alcista deterministica (5m) para etiquetado predecible."""
    ts = pd.date_range("2024-01-01", periods=n, freq="5min")
    close = start + slope * np.arange(n)
    high = close + 0.2
    low = close - 0.2
    return pd.DataFrame({"timestamp": ts, "open": close, "high": high,
                         "low": low, "close": close})


def _events(df, idxs):
    """Eventos LONG sinteticos con px_tp1<px_tp2<px_tp4 (px_tp3 se deja == px_tp2
    aqui solo por simplicidad del fixture; el grid barre tp1/tp2/tp4)."""
    recs = []
    c = df["close"].to_numpy()
    for i in idxs:
        e = float(c[i])
        recs.append({
            "entry_index": i, "entry_ts": df["timestamp"].iloc[i],
            "entry_price": e, "direction": 1,
            "px_tp1": e + 1.0, "px_tp2": e + 3.0,
            "px_tp3": e + 3.0, "px_tp4": e + 8.0,
        })
    return pd.DataFrame(recs)


def test_grid_shape_and_cells():
    df = _rising_df()
    events = _events(df, list(range(50, 300, 12)))
    sl_mults = [0.5, 1.0, 2.0]
    tp_levels = ["tp1", "tp2", "tp4"]
    grid = opt.tp_sl_grid(df, events, sl_mults, tp_levels, horizon=120,
                          sim_kwargs={"cost": eng.CostModel(
                              taker_fee=0.0, slippage_bps=0.0, apply_funding=False)},
                          bar_minutes=5.0)
    assert len(grid) == len(sl_mults) * len(tp_levels)
    assert set(grid["TP"]) == set(tp_levels)
    assert {"exp_R", "WR", "total_R", "calmar", "max_dd", "n"}.issubset(grid.columns)


def test_near_tp_wins_more_than_far_tp():
    # En una serie alcista, el TP cercano (tp1) se alcanza mas que el lejano (tp4).
    df = _rising_df()
    events = _events(df, list(range(50, 320, 9)))
    grid = opt.tp_sl_grid(df, events, [1.0], ["tp1", "tp4"], horizon=200,
                          sim_kwargs={"cost": eng.CostModel(
                              taker_fee=0.0, slippage_bps=0.0, apply_funding=False)},
                          bar_minutes=5.0)
    wr_tp1 = grid[grid["TP"] == "tp1"].iloc[0]["WR"]
    wr_tp4 = grid[grid["TP"] == "tp4"].iloc[0]["WR"]
    assert wr_tp1 >= wr_tp4


def test_choose_optimum_picks_max():
    grid = pd.DataFrame([
        {"SL_xATR": 1.0, "TP": "tp1", "exp_R": 0.2, "calmar": 1.0,
         "total_R": 5.0, "WR": 0.6, "max_dd": -0.1, "n": 10, "oos": False},
        {"SL_xATR": 2.0, "TP": "tp4", "exp_R": 0.5, "calmar": 3.0,
         "total_R": 9.0, "WR": 0.3, "max_dd": -0.2, "n": 10, "oos": False},
    ])
    best = opt.choose_optimum(grid, by="calmar")
    assert best["TP"] == "tp4" and best["calmar"] == pytest.approx(3.0)
    best_exp = opt.choose_optimum(grid, by="exp_R")
    assert best_exp["exp_R"] == pytest.approx(0.5)


def test_choose_optimum_empty():
    assert opt.choose_optimum(pd.DataFrame()) is None


def test_grid_skips_missing_px():
    # Si un nivel de TP falta (None), esa celda se omite sin romper.
    df = _rising_df()
    events = _events(df, list(range(50, 200, 10)))
    events["px_tp4"] = None
    grid = opt.tp_sl_grid(df, events, [1.0], ["tp1", "tp4"], horizon=100,
                          sim_kwargs={"cost": eng.CostModel(
                              taker_fee=0.0, slippage_bps=0.0, apply_funding=False)},
                          bar_minutes=5.0)
    assert set(grid["TP"]) == {"tp1"}   # tp4 sin px -> celda omitida


def test_tp_horizon_grid_frontier():
    """Frontera (TP x horizonte): una celda por (TP, horizonte), esquema con
    costes/OOS, y el TP cercano gana mas que el lejano en serie alcista."""
    df = _rising_df()
    events = _events(df, list(range(50, 320, 9)))
    # tp_horizon_grid usa el stop del motor (no lo deriva de ATR como tp_sl_grid).
    events["stop_price"] = events["entry_price"] - 1.0   # riesgo 1.0 por trade
    grid = opt.tp_horizon_grid(
        df, events, ["tp1", "tp4"], [60, 200],
        sim_kwargs={"cost": eng.CostModel(
            taker_fee=0.0, slippage_bps=0.0, apply_funding=False)},
        bar_minutes=5.0)
    assert len(grid) == 2 * 2                      # 2 TP x 2 horizontes
    assert {"TP", "horizon", "exp_R", "WR", "total_R", "n"}.issubset(grid.columns)
    wr_tp1 = grid[grid["TP"] == "tp1"]["WR"].astype(float).mean()
    wr_tp4 = grid[grid["TP"] == "tp4"]["WR"].astype(float).mean()
    assert wr_tp1 >= wr_tp4
    # choose_optimum opera igual sobre esta tabla
    best = opt.choose_optimum(grid, by="exp_R")
    assert best is not None and "horizon" in best


def test_tp_horizon_grid_empty_events():
    df = _rising_df()
    grid = opt.tp_horizon_grid(df, pd.DataFrame(), ["tp1"], [60])
    assert len(grid) == 0
