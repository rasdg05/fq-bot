# -*- coding: utf-8 -*-
"""carry_backtest.carry_metrics: la matematica del funding carry (pura)."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import carry_backtest as cb


def test_carry_constante_da_apy_esperado():
    # 0.01%/8h constante -> 1095 intervalos/ano * 0.0001 = ~10.95% APY (menos coste)
    f = np.full(1095, 0.0001)
    m = cb.carry_metrics(f, selective=False, entry_cost_bps=0.0)
    assert m["apy"] == pytest.approx(0.1095, abs=2e-3)
    assert m["pct_positive"] == 1.0
    assert m["max_dd_frac"] == 0.0           # carry siempre sube -> sin drawdown
    assert m["mean_funding_bps"] == pytest.approx(1.0)


def test_carry_negativo_tiene_drawdown():
    # tramo positivo y luego negativo -> el carry acumulado cae -> drawdown > 0
    f = np.concatenate([np.full(100, 0.0002), np.full(100, -0.0003)])
    m = cb.carry_metrics(f, selective=False, entry_cost_bps=0.0)
    assert m["max_dd_frac"] > 0.0
    assert m["pct_positive"] == pytest.approx(0.5)


def test_selective_evita_los_negativos():
    # selective (causal) deberia evitar la mayoria del tramo negativo -> mejor que always
    f = np.concatenate([np.full(200, 0.0002), np.full(200, -0.0004)])
    always = cb.carry_metrics(f, selective=False, entry_cost_bps=0.0)
    sel = cb.carry_metrics(f, selective=True, threshold=0.0, cost_bps_per_switch=0.0)
    assert sel["total_return"] > always["total_return"]


def test_carry_vacio_no_crashea():
    m = cb.carry_metrics([])
    assert m["n"] == 0 and m["apy"] == 0.0
