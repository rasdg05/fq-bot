# -*- coding: utf-8 -*-
"""Monte Carlo de la curva (N8.3): determinismo, rangos y monotonía esperada.

El estadístico debe ser reproducible por seed, los cuantiles ordenados, y un
edge positivo debe arrojar MENOS risk-of-ruin que uno negativo. Sin red, sin
cubo: serie de R sintética.
"""
import pytest

from tools.montecarlo_curve import simulate


def _series(mean_R, n=400, sd=1.0, seed=0):
    import numpy as np
    rng = np.random.default_rng(seed)
    return list(rng.normal(mean_R, sd, size=n))


def test_deterministic_by_seed():
    rs = _series(0.10)
    a = simulate(rs, n_paths=2000, seed=42)
    b = simulate(rs, n_paths=2000, seed=42)
    assert a == b  # mismo seed -> idéntico


def test_keys_and_ranges():
    rep = simulate(_series(0.05), n_paths=3000, seed=1)
    for k in ("max_dd_p50", "risk_of_ruin", "equity_p50", "prob_profit"):
        assert k in rep
    # drawdowns fraccionales en [0,1] y cuantiles ordenados
    assert 0.0 <= rep["max_dd_p50"] <= rep["max_dd_p95"] <= rep["max_dd_p99"] <= 1.0
    # bandas de equity ordenadas
    assert rep["equity_p05"] <= rep["equity_p50"] <= rep["equity_p95"]
    assert 0.0 <= rep["risk_of_ruin"] <= 1.0
    assert 0.0 <= rep["prob_profit"] <= 1.0


def test_positive_edge_safer_than_negative():
    """Un edge positivo arruina menos y gana más que uno negativo (mismo riesgo)."""
    pos = simulate(_series(+0.15, seed=7), n_paths=4000, risk_frac=0.02, seed=3)
    neg = simulate(_series(-0.15, seed=7), n_paths=4000, risk_frac=0.02, seed=3)
    assert pos["risk_of_ruin"] < neg["risk_of_ruin"]
    assert pos["prob_profit"] > neg["prob_profit"]
    assert pos["equity_p50"] > neg["equity_p50"]


def test_requires_minimum_series():
    with pytest.raises(ValueError):
        simulate([0.1])  # n<2
