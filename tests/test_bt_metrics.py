# -*- coding: utf-8 -*-
"""
bt_metrics (etapa 5): metricas de riesgo. Pieza pura -> tests directos.
"""
import numpy as np
import pandas as pd
import pytest

import bt_metrics as m


def test_drawdown_and_max_dd():
    eq = [100, 120, 90, 110, 80]      # pico 120, fondo 80 -> dd = 80/120-1
    mdd, peak, trough = m.max_drawdown(eq)
    assert mdd == pytest.approx(80 / 120 - 1)
    assert peak == 1                  # el pico fue 120 en idx 1
    assert trough == 4


def test_drawdown_zero_when_monotonic():
    eq = [100, 101, 102, 103]
    mdd, _, _ = m.max_drawdown(eq)
    assert mdd == pytest.approx(0.0)


def test_sharpe_positive_for_consistent_gains():
    r = [0.01, 0.012, 0.009, 0.011, 0.010]
    s = m.sharpe(r)
    assert s is not None and s > 0


def test_sharpe_annualization_scales():
    r = [0.01, -0.005, 0.008, 0.002, 0.006, -0.001]
    base = m.sharpe(r)
    ann = m.sharpe(r, periods_per_year=252)
    assert ann == pytest.approx(base * np.sqrt(252))


def test_sharpe_none_on_zero_std_or_tiny_sample():
    assert m.sharpe([0.01, 0.01, 0.01]) is None      # std 0
    assert m.sharpe([0.01]) is None                  # muestra chica


def test_sortino_penalizes_downside_only():
    # misma media que una serie simetrica pero con menos downside -> Sortino > Sharpe
    r = [0.02, 0.02, -0.01, 0.02, 0.02]
    so = m.sortino(r)
    sh = m.sharpe(r)
    assert so is not None and sh is not None
    assert so > sh


def test_profit_factor_and_win_rate():
    pnls = [100, -50, 200, -100, 50]
    assert m.profit_factor(pnls) == pytest.approx(350 / 150)
    assert m.win_rate(pnls) == pytest.approx(3 / 5)


def test_profit_factor_inf_without_losses():
    assert m.profit_factor([10, 20, 30]) == float("inf")


def test_cagr_and_calmar():
    # equity duplica en 252 'periodos' -> CAGR ~ 100% anual si ppy=252
    eq = list(np.linspace(10_000, 20_000, 253))
    c = m.cagr(eq, periods_per_year=252)
    assert c is not None and c > 0
    cal = m.calmar(eq, periods_per_year=252)
    # serie monotona creciente -> dd 0 -> calmar None
    assert cal is None


def test_calmar_finite_with_drawdown():
    eq = [10_000, 12_000, 9_000, 15_000, 14_000, 20_000]
    cal = m.calmar(eq, periods_per_year=252)
    assert cal is not None and np.isfinite(cal)


def test_compute_metrics_full_bundle():
    returns = [0.02, -0.01, 0.02, -0.01, 0.03]
    equity = [10_000, 10_200, 10_098, 10_300, 10_197, 10_503]
    pnl = [200, -102, 202, -103, 306]
    pnl_r = [2.0, -1.0, 2.0, -1.0, 3.0]
    out = m.compute_metrics(returns=returns, equity_curve=equity, pnl=pnl,
                            pnl_r=pnl_r, periods_per_year=252)
    assert out["n_trades"] == 5
    assert out["win_rate"] == pytest.approx(3 / 5)
    assert out["expectancy_r"] == pytest.approx(1.0)
    assert out["total_r"] == pytest.approx(5.0)
    assert out["sharpe"] is not None
    assert out["sortino"] is not None
    assert out["max_drawdown"] <= 0
    assert "calmar" in out and "cagr" in out
    assert out["final_equity"] == pytest.approx(10_503)


def test_excursion_stats_aggregates():
    # FASE D: agregados de la distribucion mfe_r/mae_r del labeler.
    out = m.excursion_stats(mfe_r=[1.0, 2.0, 3.0], mae_r=[-0.5, -1.0, -1.5])
    assert out["avg_mfe_r"] == pytest.approx(2.0)
    assert out["median_mfe_r"] == pytest.approx(2.0)
    assert out["avg_mae_r"] == pytest.approx(-1.0)
    assert out["median_mae_r"] == pytest.approx(-1.0)
    assert out["mfe_p90_r"] == pytest.approx(np.percentile([1.0, 2.0, 3.0], 90))
    # nan-safe: insumos no finitos se descartan
    clean = m.excursion_stats(mfe_r=[1.0, np.nan, 3.0])
    assert clean["avg_mfe_r"] == pytest.approx(2.0)


def test_compute_metrics_exposure_and_excursions():
    # FASE D: exposure + mfe/mae entran en el dict y en el reporte.
    out = m.compute_metrics(pnl_r=[1.0, -1.0, 2.0], mfe_r=[1.5, 0.2, 2.5],
                            mae_r=[-0.3, -1.0, -0.1], exposure=0.42)
    assert out["exposure"] == pytest.approx(0.42)
    assert out["avg_mfe_r"] == pytest.approx((1.5 + 0.2 + 2.5) / 3)
    assert "avg_mae_r" in out
    assert "exposure" in m.format_report(out)
    assert "avg_mfe_r" in m.format_report(out)


def test_known_pnl_r_drawdown_and_calmar():
    # FASE D: serie de pnl_r conocida -> equity y max_dd/calmar correctos.
    # pnl_r en R, equity multiplicativa con risk 1R = 100 sobre equity0=1000.
    pnl_r = [2.0, -1.0, -1.0, 3.0]   # equity: +200,-100,-100,+300
    equity = [1000, 1200, 1100, 1000, 1300]
    # pico 1200 -> fondo 1000 (idx 3) => dd = 1000/1200 - 1
    mdd, peak, trough = m.max_drawdown(equity)
    assert mdd == pytest.approx(1000 / 1200 - 1)
    assert peak == 1 and trough == 3
    out = m.compute_metrics(equity_curve=equity, pnl_r=pnl_r, periods_per_year=252)
    assert out["total_r"] == pytest.approx(3.0)
    assert out["max_drawdown"] == pytest.approx(1000 / 1200 - 1)
    assert out["calmar"] is not None and np.isfinite(out["calmar"])


def test_metrics_from_engine_result():
    import bt_engine as eng
    trades = pd.DataFrame([
        {"entry_price": 100, "stop_price": 95, "exit_price": 110,
         "direction": eng.LONG, "bars_held": 1},
        {"entry_price": 100, "stop_price": 95, "exit_price": 95,
         "direction": eng.LONG, "bars_held": 1},
    ])
    res = eng.simulate(trades, cost=eng.CostModel(
        taker_fee=0.0, slippage_bps=0.0, apply_funding=False))
    out = m.metrics_from_result(res)
    assert out["n_trades"] == 2
    assert out["win_rate"] == pytest.approx(0.5)
    assert "max_drawdown" in out
    # render no rompe
    assert isinstance(m.format_report(out), str)
