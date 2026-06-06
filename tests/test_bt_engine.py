# -*- coding: utf-8 -*-
"""
bt_engine (etapa 4): motor de backtest con costes. Pieza pura -> tests directos
sobre DataFrames de trades construidos a mano.
"""
import numpy as np
import pandas as pd
import pytest

import bt_engine as eng


def _trade(entry, stop, exit_px, direction, bars_held=1, **extra):
    row = {"entry_price": entry, "stop_price": stop, "exit_price": exit_px,
           "direction": direction, "bars_held": bars_held}
    row.update(extra)
    return row


def _no_cost():
    return eng.CostModel(taker_fee=0.0, slippage_bps=0.0, apply_funding=False)


def test_single_winning_long_no_costs():
    # entry 100, stop 95 (R=5), exit 110 (+2R). risk 1% de 10k = 100 -> qty 20.
    trades = pd.DataFrame([_trade(100, 95, 110, eng.LONG)])
    r = eng.simulate(trades, equity0=10_000, risk_frac=0.01, cost=_no_cost())
    assert r["n_trades"] == 1
    tr = r["trades"].iloc[0]
    assert tr["qty"] == pytest.approx(20.0)             # 100 / 5
    assert tr["gross_pnl"] == pytest.approx(200.0)      # 20 * 10
    assert tr["net_pnl"] == pytest.approx(200.0)
    assert tr["net_pnl_r"] == pytest.approx(2.0)
    assert r["final_equity"] == pytest.approx(10_200.0)


def test_single_losing_long_is_minus_one_r():
    trades = pd.DataFrame([_trade(100, 95, 95, eng.LONG)])
    r = eng.simulate(trades, equity0=10_000, risk_frac=0.01, cost=_no_cost())
    assert r["trades"].iloc[0]["net_pnl_r"] == pytest.approx(-1.0)
    assert r["final_equity"] == pytest.approx(9_900.0)


def test_short_winning():
    # SHORT entry 100, stop 105 (R=5), exit 90 (+2R).
    trades = pd.DataFrame([_trade(100, 105, 90, eng.SHORT)])
    r = eng.simulate(trades, equity0=10_000, risk_frac=0.01, cost=_no_cost())
    assert r["trades"].iloc[0]["net_pnl_r"] == pytest.approx(2.0)


def test_fees_reduce_pnl():
    trades = pd.DataFrame([_trade(100, 95, 110, eng.LONG)])
    cost = eng.CostModel(taker_fee=0.0005, slippage_bps=0.0, apply_funding=False)
    r = eng.simulate(trades, equity0=10_000, risk_frac=0.01, cost=cost)
    tr = r["trades"].iloc[0]
    # fees = 0.0005 * (notional_entry + notional_exit) = 0.0005*(2000+2200)=2.1
    assert tr["fees"] == pytest.approx(2.1)
    assert tr["net_pnl"] == pytest.approx(200.0 - 2.1)
    assert r["total_fees"] == pytest.approx(2.1)


def test_slippage_makes_fills_worse():
    trades = pd.DataFrame([_trade(100, 95, 110, eng.LONG)])
    cost = eng.CostModel(taker_fee=0.0, slippage_bps=10.0, apply_funding=False)
    r = eng.simulate(trades, equity0=10_000, risk_frac=0.01, cost=cost)
    tr = r["trades"].iloc[0]
    # entra a 100.1, sale a 109.89 -> gross < 200
    assert tr["gross_pnl"] < 200.0
    assert tr["slippage_cost"] > 0.0


def test_funding_charges_longs_when_positive():
    # 48 velas de 60 min = 48h = 6 ventanas de funding.
    trades = pd.DataFrame([_trade(100, 95, 110, eng.LONG, bars_held=48)])
    cost = eng.CostModel(taker_fee=0.0, slippage_bps=0.0,
                         funding_rate_8h=0.0001, apply_funding=True)
    r = eng.simulate(trades, equity0=10_000, risk_frac=0.01, bar_minutes=60,
                     cost=cost)
    tr = r["trades"].iloc[0]
    assert tr["funding_cost"] > 0.0          # el long paga
    assert tr["net_pnl"] < 200.0


def test_funding_pays_shorts_when_positive():
    trades = pd.DataFrame([_trade(100, 105, 90, eng.SHORT, bars_held=48)])
    cost = eng.CostModel(taker_fee=0.0, slippage_bps=0.0,
                         funding_rate_8h=0.0001, apply_funding=True)
    r = eng.simulate(trades, equity0=10_000, risk_frac=0.01, bar_minutes=60,
                     cost=cost)
    # funding_cost negativo => el short COBRA
    assert r["trades"].iloc[0]["funding_cost"] < 0.0


def test_compounding_and_equity_curve():
    trades = pd.DataFrame([
        _trade(100, 95, 110, eng.LONG),   # +2R
        _trade(100, 95, 110, eng.LONG),   # +2R sobre equity mayor
    ])
    r = eng.simulate(trades, equity0=10_000, risk_frac=0.01, cost=_no_cost())
    assert len(r["equity_curve"]) == 3                  # inicial + 2
    assert r["equity_curve"].iloc[0] == 10_000
    # segundo trade arriesga 1% de 10_200 -> gana mas que el primero
    pnls = r["trades"]["net_pnl"].tolist()
    assert pnls[1] > pnls[0]
    assert r["final_equity"] == pytest.approx(10_404.0)


def test_skips_unresolved_trades():
    trades = pd.DataFrame([
        _trade(100, 95, 110, eng.LONG),
        {"entry_price": 100, "stop_price": 95, "exit_price": np.nan,
         "direction": eng.LONG, "bars_held": np.nan},
    ])
    r = eng.simulate(trades, cost=_no_cost())
    assert r["n_trades"] == 1


def test_ruin_stops_simulation():
    # risk_frac enorme + perdidas: fuerza bancarrota.
    trades = pd.DataFrame([
        _trade(100, 50, 50, eng.LONG),   # -1R con risk_frac 1.0 -> equity 0
        _trade(100, 95, 110, eng.LONG),
    ])
    r = eng.simulate(trades, equity0=10_000, risk_frac=1.0, cost=_no_cost())
    assert r["ruin"] is True
    assert r["n_trades"] == 1
    assert r["final_equity"] <= 0


def test_max_leverage_caps_notional():
    # stop muy pegado -> qty enorme; el cap de leverage la limita.
    trades = pd.DataFrame([_trade(100, 99.9, 100.5, eng.LONG)])
    r = eng.simulate(trades, equity0=10_000, risk_frac=0.01,
                     cost=_no_cost(), max_leverage=3.0)
    tr = r["trades"].iloc[0]
    assert tr["notional_entry"] <= 10_000 * 3.0 + 1e-6
