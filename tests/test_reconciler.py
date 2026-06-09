# -*- coding: utf-8 -*-
"""
reconciler: lazo de seguridad operativo. Se prueba con un ledger sintético
(HashLedger real, payloads sellados a mano) -> sin red, determinista.
"""
import pytest

import execution as ex
import reconciler as rc


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _ledger_with_r(pnls_r, with_opens=False):
    """Construye un HashLedger real con un CLOSE por cada pnl_r (cadena válida).
    Si with_opens, intercala un OPEN antes de cada CLOSE para probar el filtro."""
    led = ex.HashLedger()
    for i, r in enumerate(pnls_r):
        if with_opens:
            led.append({"event": "OPEN", "pid": i, "risk_frac": 0.0025})
        led.append({"event": "CLOSE", "pid": i, "pnl_r": float(r),
                    "pnl_quote": float(r) * 25.0})
    return led


def _governor():
    return ex.RiskGovernor(ex.GovernorConfig())


# --------------------------------------------------------------------------
# extract_closed_r
# --------------------------------------------------------------------------
def test_extract_ignores_opens():
    led = _ledger_with_r([1.0, -1.0, 2.0], with_opens=True)
    assert rc.extract_closed_r(led) == [1.0, -1.0, 2.0]


def test_extract_empty_ledger():
    assert rc.extract_closed_r(ex.HashLedger()) == []


# --------------------------------------------------------------------------
# cadena íntegra + consistente -> NO mata
# --------------------------------------------------------------------------
def test_consistent_does_not_kill():
    led = _ledger_with_r([0.5, 0.6, 0.4, 0.5, 0.55, 0.45] * 5)   # media ~0.5R
    g = _governor()
    r = rc.Reconciler(led, g, backtest_expectancy_r=0.5, min_trades=10)
    rep = r.check()
    assert rep["killed"] is False
    assert g.cfg.kill_switch is False
    assert rep["reconcile"]["within"] is True


# --------------------------------------------------------------------------
# ledger manipulado -> MATA y cortocircuita
# --------------------------------------------------------------------------
def test_tampered_ledger_kills():
    led = _ledger_with_r([0.5, 0.5, 0.5])
    led.records[1]["payload"]["pnl_r"] = 99.0     # edita el pasado
    g = _governor()
    rep = rc.Reconciler(led, g, backtest_expectancy_r=0.5, min_trades=2).check()
    assert rep["chain_ok"] is False
    assert rep["killed"] is True
    assert g.cfg.kill_switch is True
    assert rep["reconcile"] is None               # cortocircuitó


# --------------------------------------------------------------------------
# drift a la baja -> MATA
# --------------------------------------------------------------------------
def test_drift_down_kills():
    led = _ledger_with_r([-0.2, -0.3, -0.1, -0.25, -0.15] * 6)   # viva muy por debajo
    g = _governor()
    rep = rc.Reconciler(led, g, backtest_expectancy_r=0.5, min_trades=10).check()
    assert rep["killed"] is True
    assert g.cfg.kill_switch is True
    assert rep["reconcile"]["within"] is False
    assert any("DRIFT" in s for s in rep["reasons"])


# --------------------------------------------------------------------------
# viva supera al backtest -> NO mata (solo avisa)
# --------------------------------------------------------------------------
def test_live_better_than_backtest_does_not_kill():
    led = _ledger_with_r([1.4, 1.6, 1.5, 1.45, 1.55] * 6)        # muy por encima
    g = _governor()
    rep = rc.Reconciler(led, g, backtest_expectancy_r=0.5, min_trades=10).check()
    assert rep["killed"] is False
    assert g.cfg.kill_switch is False
    assert rep["reconcile"]["within"] is False                  # fuera del IC pero al alza


# --------------------------------------------------------------------------
# DD diario por cuenta -> MATA
# --------------------------------------------------------------------------
def test_daily_dd_breach_kills():
    led = _ledger_with_r([0.5, 0.5])
    a = ex.Account("A1", 10_000.0)
    a.equity = 9_500.0                                            # -5% del día
    g = _governor()
    rep = rc.Reconciler(led, g, backtest_expectancy_r=0.5,
                        max_daily_loss_frac=0.04, min_trades=2).check(accounts=[a])
    assert rep["dd_breach"] is True
    assert rep["killed"] is True
    assert g.cfg.kill_switch is True


def test_daily_dd_within_limit_does_not_kill():
    led = _ledger_with_r([0.5, 0.6, 0.4, 0.5, 0.55, 0.45] * 5)
    a = ex.Account("A1", 10_000.0)
    a.equity = 9_900.0                                            # -1% del día (ok)
    g = _governor()
    rep = rc.Reconciler(led, g, backtest_expectancy_r=0.5,
                        max_daily_loss_frac=0.04, min_trades=10).check(accounts=[a])
    assert rep["dd_breach"] is False
    assert rep["killed"] is False


# --------------------------------------------------------------------------
# muestra insuficiente -> NO mata, espera
# --------------------------------------------------------------------------
def test_insufficient_sample_does_not_kill():
    led = _ledger_with_r([-1.0, -1.0, -1.0])                      # malísimo pero poco
    g = _governor()
    rep = rc.Reconciler(led, g, backtest_expectancy_r=0.5, min_trades=20).check()
    assert rep["killed"] is False
    assert g.cfg.kill_switch is False
    assert "insuficiente" in rep["reconcile"]["verdict"]


# --------------------------------------------------------------------------
# estructura del reporte
# --------------------------------------------------------------------------
def test_report_structure():
    led = _ledger_with_r([0.5] * 12)
    rep = rc.Reconciler(led, _governor(), backtest_expectancy_r=0.5, min_trades=10).check()
    for k in ("chain_ok", "n_trades", "dd_breach", "reconcile", "killed", "reasons"):
        assert k in rep
    assert rep["n_trades"] == 12
    assert isinstance(rep["reasons"], list)
