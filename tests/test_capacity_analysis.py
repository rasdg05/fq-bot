# -*- coding: utf-8 -*-
"""Capacidad (N8.4): el edge degrada monótono con el capital, C½ llega antes que
C0, y más impacto = menos capacidad. Sin red ni cubo: serie de R sintética.
"""
import numpy as np
import pytest

from tools.capacity_analysis import capacity_curve


def _rs(mean_R=0.10, n=400, seed=0):
    rng = np.random.default_rng(seed)
    return list(rng.normal(mean_R, 1.0, size=n))


def test_edge_degrades_monotonically_with_capital():
    rep = capacity_curve(_rs(), avg_bar_notional=3e6)
    edge = np.asarray(rep["curve"]["edge_r"])
    # a capital chico el edge ~ bruto; a capital grande, menor
    assert edge[0] > edge[-1]
    assert np.all(np.diff(edge) <= 1e-9)            # no-creciente
    assert abs(edge[0] - rep["mean_R_gross"]) < abs(edge[-1] - rep["mean_R_gross"])


def test_half_capacity_before_zero():
    rep = capacity_curve(_rs(mean_R=0.12), avg_bar_notional=3e6)
    assert rep["capital_half"] is not None
    assert rep["capital_zero"] is not None
    assert rep["capital_half"] < rep["capital_zero"]   # mitad antes que cero


def test_more_impact_means_less_capacity():
    soft = capacity_curve(_rs(), impact_coef=40.0, avg_bar_notional=3e6)
    hard = capacity_curve(_rs(), impact_coef=160.0, avg_bar_notional=3e6)
    assert hard["capital_half"] < soft["capital_half"]  # más impacto, antes cae


def test_requires_minimum_series():
    with pytest.raises(ValueError):
        capacity_curve([0.1])
