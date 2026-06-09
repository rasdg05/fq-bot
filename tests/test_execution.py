# -*- coding: utf-8 -*-
"""
execution: capa de paper + gobernador de riesgo. Piezas puras -> tests directos.
"""
import pytest

import execution as ex


def _acct(eq=10_000.0):
    return ex.Account("A1", eq)


def _sig(direction=ex.LONG, entry=100.0, stop=99.0, tp=103.0, symbol="BTC/USDT"):
    return {"symbol": symbol, "direction": direction, "entry": entry, "stop": stop, "tp": tp}


# --------------------------------------------------------------------------
# RiskGovernor
# --------------------------------------------------------------------------
def test_governor_caps_risk_per_trade():
    g = ex.RiskGovernor(ex.GovernorConfig(max_risk_frac=0.0025))
    d = g.decide(_acct(), requested_risk=0.05)     # pide 5%
    assert d["approved"] and d["risk_frac"] == 0.0025   # capado al 0.25%


def test_governor_blocks_on_daily_loss():
    a = _acct(10_000)
    a.equity = 9_500                                # -5% del día
    g = ex.RiskGovernor(ex.GovernorConfig(max_daily_loss_frac=0.04))
    d = g.decide(a)
    assert not d["approved"] and "diaria" in d["reason"]


def test_governor_blocks_on_max_positions():
    a = _acct()
    g = ex.RiskGovernor(ex.GovernorConfig(max_open_positions=2))
    a.open = [object(), object()]
    assert not g.decide(a)["approved"]


def test_governor_respects_total_risk_room():
    a = _acct()
    g = ex.RiskGovernor(ex.GovernorConfig(max_risk_frac=0.01, max_total_risk_frac=0.015))
    # ya hay 0.01 abierto -> solo queda 0.005 de margen
    p = ex.Position("A1", "X", ex.LONG, 100, 99, 103, 1.0, 0.01)
    a.open.append(p)
    d = g.decide(a, requested_risk=0.01)
    assert d["approved"] and d["risk_frac"] == pytest.approx(0.005)


def test_governor_kill_switch():
    g = ex.RiskGovernor(ex.GovernorConfig(kill_switch=True))
    assert not g.decide(_acct())["approved"]


# --------------------------------------------------------------------------
# PaperBroker — sizing y PnL
# --------------------------------------------------------------------------
def test_paper_open_sizes_by_risk():
    a, b = _acct(10_000), ex.PaperBroker()
    pos = b.open(a, _sig(entry=100, stop=99), risk_frac=0.0025)
    # riesgo = 10000*0.0025 = 25 quote; dist = 1 -> size = 25 unidades
    assert pos.size == pytest.approx(25.0)


def test_paper_resolve_win_and_loss_in_R():
    a, b = _acct(10_000), ex.PaperBroker()
    pos = b.open(a, _sig(entry=100, stop=99, tp=103), risk_frac=0.0025)
    r = b.resolve(a, pos, 103.0, "tp")             # +3R
    assert r["pnl_r"] == pytest.approx(3.0)
    assert a.equity == pytest.approx(10_000 + 25 * 3)   # +75 quote
    assert pos not in a.open

    pos2 = b.open(a, _sig(entry=100, stop=99), risk_frac=0.0025)
    r2 = b.resolve(a, pos2, 99.0, "stop")          # -1R
    assert r2["pnl_r"] == pytest.approx(-1.0)


def test_paper_resolve_on_bar_pessimistic_tie():
    a, b = _acct(), ex.PaperBroker()
    pos = b.open(a, _sig(ex.LONG, 100, 99, 103), 0.0025)
    r = b.resolve_on_bar(a, pos, high=103, low=99)   # toca TP y SL -> pesimista=stop
    assert r["reason"] == "stop" and r["pnl_r"] == pytest.approx(-1.0)


def test_paper_resolve_on_bar_no_touch_returns_none():
    a, b = _acct(), ex.PaperBroker()
    pos = b.open(a, _sig(ex.LONG, 100, 99, 103), 0.0025)
    assert b.resolve_on_bar(a, pos, high=101, low=99.5) is None
    assert pos in a.open


# --------------------------------------------------------------------------
# HashLedger — commit-then-reveal / tamper-evidence
# --------------------------------------------------------------------------
def test_ledger_chain_verifies():
    a, b = _acct(), ex.PaperBroker()
    pos = b.open(a, _sig(), 0.0025)
    b.resolve(a, pos, 103.0, "tp")
    assert len(b.ledger.records) == 2
    assert b.ledger.verify() is True


def test_ledger_tamper_is_detected():
    a, b = _acct(), ex.PaperBroker()
    pos = b.open(a, _sig(), 0.0025)
    b.resolve(a, pos, 103.0, "tp")
    # alguien edita el desenlace a posteriori:
    b.ledger.records[0]["payload"]["entry"] = 1.0
    assert b.ledger.verify() is False


# --------------------------------------------------------------------------
# fan_out — cuentas encadenadas
# --------------------------------------------------------------------------
def test_fan_out_applies_to_each_account():
    accts = [ex.Account(f"A{i}", 10_000) for i in range(3)]
    g, b = ex.RiskGovernor(), ex.PaperBroker()
    res = ex.fan_out(_sig(), accts, g, b)
    assert all(r["approved"] for r in res)
    assert all(len(a.open) == 1 for a in accts)


def test_fan_out_correlation_cap():
    accts = [ex.Account(f"A{i}", 10_000) for i in range(4)]
    g, b = ex.RiskGovernor(), ex.PaperBroker()
    res = ex.fan_out(_sig(), accts, g, b, max_correlated=2)
    approved = [r for r in res if r["approved"]]
    assert len(approved) == 2                       # solo 2 cuentas toman la señal
    assert sum(len(a.open) for a in accts) == 2
