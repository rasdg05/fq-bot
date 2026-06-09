# -*- coding: utf-8 -*-
"""
bt_quality (FASE B): gate de calidad "VIP oro" sobre walk-forward OOS.
Pieza pura -> tests directos. Validamos: agregados de subset, drawdown en R, y
que con senal sembrada el decil superior SUBE la expectancy vs base mientras un
score placebo (barajado) NO la mueve.
"""
import numpy as np
import pytest

import bt_quality as q


def test_max_drawdown_r_known_sequence():
    # equity acumulada en R: 0,2,1,0,3 -> pico 2, fondo 0 (idx3) => dd = -2 R
    pnl_r = [2.0, -1.0, -1.0, 3.0]
    assert q.max_drawdown_r(pnl_r) == pytest.approx(-2.0)


def test_max_drawdown_r_monotonic_is_zero():
    assert q.max_drawdown_r([1.0, 2.0, 0.5]) == pytest.approx(0.0)
    assert q.max_drawdown_r([]) == pytest.approx(0.0)


def test_subset_stats_basic():
    st = q.subset_stats([2.0, -1.0, -1.0, 3.0])
    assert st["n"] == 4
    assert st["wr"] == pytest.approx(0.5)
    assert st["expectancy_r"] == pytest.approx(0.75)
    assert st["total_r"] == pytest.approx(3.0)
    assert st["max_dd_r"] == pytest.approx(-2.0)
    assert st["calmar_r"] == pytest.approx(3.0 / 2.0)


def test_subset_stats_empty_is_nan():
    st = q.subset_stats([])
    assert st["n"] == 0
    assert np.isnan(st["expectancy_r"])


def test_quality_gate_isolates_top_decile():
    # score = pnl_r + ruido pequeno -> ordena bien: el top decil debe ganar mas.
    rng = np.random.default_rng(0)
    n = 500
    pnl_r = rng.normal(0.0, 1.0, n)
    scores = pnl_r + rng.normal(0.0, 0.05, n)   # senal fuerte
    grid = q.quality_gate(scores, pnl_r, quantiles=(0.5, 0.9))
    base = grid[grid["subset"] == "base"].iloc[0]
    top10 = grid[grid["subset"] == "top10%"].iloc[0]
    assert top10["expectancy_r"] > base["expectancy_r"]
    assert top10["edge_vs_base_r"] > 0
    assert top10["n"] == pytest.approx(round(n * 0.1), abs=2)


def test_quality_gate_placebo_no_edge():
    # score placebo (barajado, sin relacion con pnl_r) -> edge ~ 0 (no sistematico).
    rng = np.random.default_rng(1)
    n = 2000
    pnl_r = rng.normal(0.0, 1.0, n)
    placebo = rng.permutation(pnl_r.copy())   # independiente del desenlace
    grid = q.quality_gate(placebo, pnl_r, quantiles=(0.9,))
    top10 = grid[grid["subset"] == "top10%"].iloc[0]
    # el edge del placebo debe ser pequeno en magnitud (no aisla nada real)
    assert abs(top10["edge_vs_base_r"]) < 0.15


def test_quality_gate_real_beats_placebo():
    rng = np.random.default_rng(7)
    n = 1500
    pnl_r = rng.normal(0.0, 1.0, n)
    real = pnl_r + rng.normal(0.0, 0.1, n)
    placebo = rng.permutation(pnl_r.copy())
    g_real = q.quality_gate(real, pnl_r, quantiles=(0.9,))
    g_pl = q.quality_gate(placebo, pnl_r, quantiles=(0.9,))
    edge_real = g_real[g_real["subset"] == "top10%"].iloc[0]["edge_vs_base_r"]
    edge_pl = g_pl[g_pl["subset"] == "top10%"].iloc[0]["edge_vs_base_r"]
    assert edge_real > edge_pl
    assert edge_real > 0.3


def test_format_gate_renders():
    grid = q.quality_gate([1.0, 2.0, 3.0, 4.0], [-1.0, 0.5, 1.0, 2.0],
                          quantiles=(0.5,))
    txt = q.format_gate(grid)
    assert "VIP" in txt and "base" in txt
