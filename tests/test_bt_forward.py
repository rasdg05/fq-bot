# -*- coding: utf-8 -*-
"""
bt_forward: prueba forward / out-of-time + calibración + reconciliación.
Piezas puras -> tests directos, sin red ni lightgbm (estimador inyectado).
"""
import numpy as np
import pandas as pd
import pytest

import bt_forward as fw


def _labeled(n=120, seed=0):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2024-01-01", periods=n, freq="6h")
    y = rng.integers(0, 2, size=n)
    signal = y * 2.5 + rng.normal(0, 1, size=n)
    pnl = np.where(y == 1, 1.8, -1.0)
    return pd.DataFrame({
        "entry_ts": ts, "signal": signal, "noise": rng.normal(0, 1, size=n),
        "outcome": np.where(y == 1, "win", "loss"),
        "pnl_r": pnl,
        "entry_price": 100.0, "stop_price": 99.0, "exit_price": 101.8,
        "direction": 1, "bars_held": 5,
    })


# --------------------------------------------------------------------------
# out_of_time_split
# --------------------------------------------------------------------------
def test_split_by_time_is_disjoint_and_ordered():
    df = _labeled(100)
    cut = df["entry_ts"].iloc[60]
    before, after = fw.out_of_time_split(df, cut)
    assert len(before) == 60 and len(after) == 40
    assert pd.to_datetime(before["entry_ts"]).max() < pd.Timestamp(cut)
    assert pd.to_datetime(after["entry_ts"]).min() >= pd.Timestamp(cut)


def test_split_requires_ts_col():
    with pytest.raises(ValueError):
        fw.out_of_time_split(pd.DataFrame({"x": [1]}), "2024-01-01")


# --------------------------------------------------------------------------
# freeze_predict — el ajuste NO ve el 'after'
# --------------------------------------------------------------------------
def test_freeze_predict_fits_only_on_before():
    df = _labeled(120)
    before, after = fw.out_of_time_split(df, df["entry_ts"].iloc[80])
    seen = {}

    class _Spy:
        def fit(self, X, y):
            seen["n"] = len(X); return self
        def predict_proba(self, X):
            # score monótono en 'signal' (sin mirar y)
            s = 1 / (1 + np.exp(-(X["signal"].to_numpy())))
            return np.column_stack([1 - s, s])

    scored, model = fw.freeze_predict(before, after, ["signal", "noise"],
                                      lambda: _Spy())
    assert seen["n"] == len(before)              # ajustó SOLO con 'before'
    assert "fwd_score" in scored.columns and len(scored) == len(after)
    # con señal fuerte, el score separa ganadoras de perdedoras en el after
    win = scored["outcome"] == "win"
    assert scored.loc[win, "fwd_score"].mean() > scored.loc[~win, "fwd_score"].mean()


def test_freeze_predict_single_class_raises():
    df = _labeled(40)
    df["outcome"] = "win"
    before, after = fw.out_of_time_split(df, df["entry_ts"].iloc[20])
    with pytest.raises(ValueError):
        fw.freeze_predict(before, after, ["signal"], lambda: None)


# --------------------------------------------------------------------------
# calibration_table
# --------------------------------------------------------------------------
def test_calibration_perfect_is_low_error():
    # predicho == realizado -> error ~ 0
    rng = np.random.default_rng(1)
    p = rng.random(400)
    realized = (rng.random(400) < p).astype(float)   # prob real = p
    tab, err = fw.calibration_table(p, realized, n_bins=5)
    assert len(tab) == 5
    assert err is not None and err < 0.08


def test_calibration_detects_miscalibration():
    # modelo sobreconfiado: predice alto pero realiza bajo
    p = np.linspace(0.5, 0.95, 300)
    realized = np.zeros(300)            # nunca acierta -> gap grande
    _, err = fw.calibration_table(p, realized, n_bins=5)
    assert err > 0.4


# --------------------------------------------------------------------------
# reconcile (drift)
# --------------------------------------------------------------------------
def test_reconcile_within_when_consistent():
    rng = np.random.default_rng(2)
    live = rng.normal(0.2, 1.0, size=300)     # expectancy viva ~0.2R
    r = fw.reconcile(0.2, live, n_boot=1000)
    assert r["within"] is True
    assert r["ic_low"] <= 0.2 <= r["ic_high"]


def test_reconcile_flags_downward_drift():
    rng = np.random.default_rng(3)
    live = rng.normal(-0.3, 0.8, size=300)    # viva negativa
    r = fw.reconcile(0.25, live, n_boot=1000)   # backtest prometía +0.25R
    assert r["within"] is False
    assert "DRIFT" in r["verdict"]


def test_reconcile_insufficient_sample():
    r = fw.reconcile(0.2, [0.5])
    assert r["within"] is None


# --------------------------------------------------------------------------
# forward_metrics (net de costes)
# --------------------------------------------------------------------------
def test_forward_metrics_runs_net_of_costs():
    import bt_engine as eng
    df = _labeled(80)
    _, after = fw.out_of_time_split(df, df["entry_ts"].iloc[40])
    m = fw.forward_metrics(after, sim_kwargs={"cost": eng.CostModel(
        taker_fee=0.0, slippage_bps=0.0, apply_funding=False)}, bar_minutes=360.0)
    assert m is not None and "expectancy_r" in m and "win_rate" in m
