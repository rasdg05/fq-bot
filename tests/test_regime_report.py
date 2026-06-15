# -*- coding: utf-8 -*-
"""Régimen report (N8.5): detecta la columna, segmenta y ranquea — el régimen
ganador queda arriba con mayor expectancy. Sin red ni cubo.
"""
import numpy as np
import pandas as pd

import bt_engine as eng
import tools.regime_report as rr


def _labeled_regime(n=500, seed=1):
    rng = np.random.default_rng(seed)
    regime = rng.choice(["trend", "range"], size=n)
    p = np.where(regime == "trend", 0.70, 0.35)   # trend gana, range pierde
    win = rng.random(n) < p
    return pd.DataFrame({
        "entry_index": np.arange(n), "entry_price": 100.0, "stop_price": 95.0,
        "exit_price": np.where(win, 110.0, 95.0), "direction": eng.LONG,
        "bars_held": 1, "outcome": np.where(win, "win", "loss"),
        "pnl_r": np.where(win, 2.0, -1.0), "regime": regime,
    })


def _no_cost():
    return {"cost": eng.CostModel(taker_fee=0.0, slippage_bps=0.0,
                                  apply_funding=False)}


def test_detect_and_rank():
    df = _labeled_regime(500)
    rep, col = rr.run(df, sim_kwargs=_no_cost())
    assert col == "regime"
    assert rep.iloc[0]["regime"] == "trend"            # el mejor arriba
    trend = rep[rep["regime"] == "trend"].iloc[0]["expectancy_r"]
    rng_ = rep[rep["regime"] == "range"].iloc[0]["expectancy_r"]
    assert trend > rng_


def test_lamina_png(tmp_path):
    df = _labeled_regime(300)
    rep, _ = rr.run(df, sim_kwargs=_no_cost())
    p = tmp_path / "reg.png"
    rr.lamina(rep, str(p))
    assert p.exists() and p.stat().st_size > 0
