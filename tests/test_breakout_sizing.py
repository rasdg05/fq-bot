# -*- coding: utf-8 -*-
"""Sizing de Breakout: la matemática de riesgo para no romper el 6% DD con un edge de WR bajo."""
import sys

sys.path.insert(0, "tools")
import breakout_sizing as bs


def test_self_test():
    assert bs._self_test() == 0


def test_sizing_streak_and_gating():
    # $10k, riesgo 0.5%, stop a $5 -> $50/$5 = 10 unidades
    assert bs.position_size(10000, 100, 95, risk_pct=0.5) == 10.0
    assert bs.position_size(10000, 100, 100) == 0.0          # sin distancia -> 0
    # rachas para romper el 6% (robusto a flotantes)
    assert bs.streak_to_breach(0.4) == 15
    assert bs.streak_to_breach(0.5) == 12
    assert bs.streak_to_breach(1.0) == 6
    # gating: stop diario (2%) y piso de DD (94% del inicial)
    assert bs.trade_allowed(10000, 10000, day_pnl_pct=-1.0) is True
    assert bs.trade_allowed(10000, 10000, day_pnl_pct=-2.0) is False
    assert bs.trade_allowed(9399, 10000, day_pnl_pct=0.0) is False    # bajo el piso 9400
    # el riesgo recomendado a WR 28% sobrevive una racha P99
    rec = bs.risk_pct_for_survival(0.28)
    assert 0.3 <= rec <= 0.5
    assert bs.streak_prob(0.28, bs.streak_to_breach(rec)) <= 0.01


def test_no_edge_never_reaches_target():
    assert bs.trades_to_target(0.0) == float("inf")
    assert bs.trades_to_target(-0.1) == float("inf")
    assert bs.trades_to_target(0.20, risk_pct=0.4) == 125            # 10% / (0.2*0.4)
