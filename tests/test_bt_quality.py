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


# --------------------------------------------------------------------------
# segment_expectancy: edge condicional por segmento (fractales legibles)
# --------------------------------------------------------------------------
def _seg_df():
    import pandas as pd
    # killzone 'ny' paga (+0.5 x12), 'asia' pierde (-0.4 x12), 'raro' n=2
    rows = []
    rows += [{"field_killzone": "ny", "pnl_r": 0.5}] * 12
    rows += [{"field_killzone": "asia", "pnl_r": -0.4}] * 12
    rows += [{"field_killzone": "raro", "pnl_r": 3.0}] * 2
    rows += [{"field_killzone": None, "pnl_r": 0.1}] * 3
    return pd.DataFrame(rows)


def test_segment_expectancy_ordena_y_marca_min_n():
    t = q.segment_expectancy(_seg_df(), "field_killzone", min_n=10)
    assert list(t.columns) == ["field_killzone", "n", "wr", "expectancy_r",
                               "total_r", "max_dd_r", "ok_n"]
    # los grupos con n>=10 van primero, ordenados por expectancy
    assert t.iloc[0]["field_killzone"] == "ny" and bool(t.iloc[0]["ok_n"])
    assert t.iloc[1]["field_killzone"] == "asia"
    # 'raro' tiene mejor expectancy pero n<10 -> ok_n False y va despues
    raro = t[t["field_killzone"] == "raro"].iloc[0]
    assert not bool(raro["ok_n"]) and raro["expectancy_r"] == 3.0
    # NaN del segmento agrupado como '(nan)'
    assert "(nan)" in set(t["field_killzone"])


def test_segment_expectancy_columna_ausente_o_vacio():
    import pandas as pd
    assert len(q.segment_expectancy(pd.DataFrame(), "x")) == 0
    assert len(q.segment_expectancy(_seg_df(), "no_existe")) == 0


def test_segment_expectancy_stats_correctos():
    t = q.segment_expectancy(_seg_df(), "field_killzone", min_n=10)
    ny = t[t["field_killzone"] == "ny"].iloc[0]
    assert ny["n"] == 12
    assert abs(ny["expectancy_r"] - 0.5) < 1e-9
    assert abs(ny["total_r"] - 6.0) < 1e-9
    assert ny["wr"] == 1.0
