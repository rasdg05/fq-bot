# -*- coding: utf-8 -*-
"""magnet_backtest: etiqueta senales del motor de imanes y mide drawdown via
bt_engine. Pipeline self-contained (sin pandas_ta) -> testeable en sandbox."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import magnet_backtest as mb


def _wave(n=400, period=40, amp=10.0, base=100.0):
    """Onda (rango oscilante): el motor dispara hacia los max/min previos y la
    oscilacion resuelve TP/STOP -> genera trades y un drawdown real."""
    i = np.arange(n)
    close = base + amp * np.sin(2 * np.pi * i / period)
    high = close + 0.3
    low = close - 0.3
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": np.full(n, 100.0)})


def test_max_drawdown_conocido():
    assert mb._max_drawdown([100, 110, 90, 95]) == pytest.approx(20.0 / 110.0)
    assert mb._max_drawdown([100, 101, 102]) == 0.0
    assert mb._max_drawdown([]) == 0.0


def test_label_devuelve_columnas_para_bt_engine():
    trades = mb.label_magnet_trades(_wave(), step=1, min_rr=1.0)
    if not trades.empty:
        for col in ("entry_price", "stop_price", "exit_price", "direction",
                    "bars_held", "mode", "outcome"):
            assert col in trades.columns
        assert set(trades["direction"].unique()) <= {1, -1}


def test_run_pipeline_devuelve_metricas_validas():
    r = mb.run(_wave(), step=1, min_rr=1.0)
    assert isinstance(r["n_trades"], int) and r["n_trades"] >= 0
    assert 0.0 <= r["max_drawdown"] <= 1.0
    if r["n_trades"] > 0:
        assert 0.0 <= r["win_rate"] <= 1.0
        assert r["expectancy_r"] is not None
        assert isinstance(r["by_mode"], dict)


def test_run_sin_trades_no_crashea():
    # df plano: sin estructura -> sin imanes utiles -> sin trades, pero responde
    flat = pd.DataFrame({"open": [100.0] * 80, "high": [100.0] * 80,
                         "low": [100.0] * 80, "close": [100.0] * 80,
                         "volume": [100.0] * 80})
    r = mb.run(flat, step=1, min_rr=1.5)
    assert r["n_trades"] == 0 and r["max_drawdown"] == 0.0
