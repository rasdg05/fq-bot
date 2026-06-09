# -*- coding: utf-8 -*-
"""
live_driver: cableado señal -> gobernador -> bróker -> precios reales. Se prueba
con dobles (FakeExchange para ccxt, signal_source de cola) -> sin red. El bróker
es un CcxtBroker(paper) real para ejercitar sizing/ledger/fan_out de verdad.
"""
import pytest

import execution as ex
import exchange_adapter as xa
import reconciler as rc
import live_driver as ld


# --------------------------------------------------------------------------
# dobles
# --------------------------------------------------------------------------
class FakeExchange:
    """Doble de ccxt: sirve una vela mutable (para forzar hit de tp/sl)."""
    def __init__(self, bar=None):
        self.bar = bar or {"high": 101.0, "low": 99.5}    # sin tocar tp(103)/sl(99)
        self.orders = []

    def create_order(self, *a, **k):
        self.orders.append((a, k))
        return {"id": "x"}

    def fetch_ticker(self, symbol):
        return {"last": self.bar["high"]}

    def fetch_ohlcv(self, symbol, timeframe, limit=1):
        return [[0, 100.0, self.bar["high"], self.bar["low"], 100.0, 1.0]]


def seq_source(items):
    """signal_source de cola: devuelve cada item y luego None."""
    box = list(items)

    def _src():
        return box.pop(0) if box else None
    return _src


def _signal(direction=ex.LONG, entry=100.0, stop=99.0, tp=103.0):
    return {"symbol": "BTC/USDT:USDT", "direction": direction,
            "entry": entry, "stop": stop, "tp": tp}


def _accts(n=2, eq=10_000.0):
    return [ex.Account(f"A{i}", eq) for i in range(n)]


def _ledger_with_r(pnls_r):
    led = ex.HashLedger()
    for i, r in enumerate(pnls_r):
        led.append({"event": "CLOSE", "pid": i, "pnl_r": float(r)})
    return led


# --------------------------------------------------------------------------
# normalize_fire_report
# --------------------------------------------------------------------------
def test_normalize_fire_maps_levels_and_direction():
    report = {"decision": "fire", "direction": "long",
              "levels": {"entry": 100.0, "sl": 99.0, "tp1": 103.0, "tp3": 110.0}}
    sig = ld.normalize_fire_report(report, "BTC/USDT:USDT")
    assert sig == {"symbol": "BTC/USDT:USDT", "direction": ex.LONG,
                   "entry": 100.0, "stop": 99.0, "tp": 103.0}      # tp1 por defecto


def test_normalize_tp_key_override_and_short():
    report = {"decision": "fire", "direction": "short",
              "levels": {"entry": 100.0, "sl": 101.0, "tp1": 98.0, "tp3": 95.0}}
    sig = ld.normalize_fire_report(report, "ETH/USDT:USDT", tp_key="tp3")
    assert sig["direction"] == ex.SHORT and sig["tp"] == 95.0


def test_normalize_non_fire_returns_none():
    assert ld.normalize_fire_report({"decision": "silence"}, "X") is None
    assert ld.normalize_fire_report({"decision": "fire", "direction": "long",
                                     "levels": {"entry": 100.0}}, "X") is None  # sin sl


# --------------------------------------------------------------------------
# cableado: abrir
# --------------------------------------------------------------------------
def test_step_opens_signal_across_accounts():
    broker = xa.CcxtBroker(mode="paper", exchange=FakeExchange())
    g = ex.RiskGovernor(ex.GovernorConfig())
    accts = _accts(2)
    drv = ld.LiveDriver(seq_source([_signal()]), g, broker, accts)
    rep = drv.step()
    assert rep["opened"] is not None
    assert all(r["approved"] for r in rep["opened"])
    assert all(len(a.open) == 1 for a in accts)         # una posición por cuenta


def test_step_no_signal_opens_nothing():
    broker = xa.CcxtBroker(mode="paper", exchange=FakeExchange())
    drv = ld.LiveDriver(seq_source([]), ex.RiskGovernor(), broker, _accts(1))
    rep = drv.step()
    assert rep["opened"] is None


# --------------------------------------------------------------------------
# cableado: resolver contra precios reales
# --------------------------------------------------------------------------
def test_step_resolves_open_against_real_bar():
    fx = FakeExchange()
    broker = xa.CcxtBroker(mode="paper", exchange=fx)
    g = ex.RiskGovernor(ex.GovernorConfig())
    accts = _accts(1)
    drv = ld.LiveDriver(seq_source([_signal(), None]), g, broker, accts)
    drv.step()                                          # abre (vela no toca)
    assert len(accts[0].open) == 1
    fx.bar = {"high": 103.5, "low": 102.0}              # ahora la vela toca el TP
    rep = drv.step()                                    # resuelve
    assert len(accts[0].open) == 0
    assert rep["resolved"][0]["reason"] == "tp"
    assert rep["resolved"][0]["pnl_r"] == pytest.approx(3.0)


# --------------------------------------------------------------------------
# cableado: reconciler periódico flipea el kill-switch -> fan_out rechaza
# --------------------------------------------------------------------------
def test_reconciler_kill_blocks_opens():
    broker = xa.CcxtBroker(mode="paper", exchange=FakeExchange())
    g = ex.RiskGovernor(ex.GovernorConfig())
    drift = _ledger_with_r([-0.2, -0.3, -0.1, -0.25, -0.15] * 6)   # drift a la baja
    recon = rc.Reconciler(drift, g, backtest_expectancy_r=0.5, min_trades=10)
    drv = ld.LiveDriver(seq_source([_signal()]), g, broker, _accts(2),
                        reconciler=recon, reconcile_every=1)
    rep = drv.step()
    assert rep["reconcile"]["killed"] is True
    assert g.cfg.kill_switch is True
    assert all(not r["approved"] for r in rep["opened"])  # fan_out rechaza solo


def test_reconcile_runs_only_every_n_ticks():
    broker = xa.CcxtBroker(mode="paper", exchange=FakeExchange())
    g = ex.RiskGovernor(ex.GovernorConfig())
    recon = rc.Reconciler(ex.HashLedger(), g, backtest_expectancy_r=0.5, min_trades=10)
    drv = ld.LiveDriver(seq_source([None, None, None]), g, broker, _accts(1),
                        reconciler=recon, reconcile_every=2)
    r0 = drv.step()                                     # tick 0 -> corre
    r1 = drv.step()                                     # tick 1 -> no
    r2 = drv.step()                                     # tick 2 -> corre
    assert r0["reconcile"] is not None
    assert r1["reconcile"] is None
    assert r2["reconcile"] is not None


# --------------------------------------------------------------------------
# correlación y run()
# --------------------------------------------------------------------------
def test_max_correlated_limits_accounts():
    broker = xa.CcxtBroker(mode="paper", exchange=FakeExchange())
    g = ex.RiskGovernor(ex.GovernorConfig())
    accts = _accts(3)
    drv = ld.LiveDriver(seq_source([_signal()]), g, broker, accts, max_correlated=1)
    rep = drv.step()
    approved = [r for r in rep["opened"] if r["approved"]]
    assert len(approved) == 1                           # solo una cuenta toma la señal


def test_run_executes_bounded_steps():
    broker = xa.CcxtBroker(mode="paper", exchange=FakeExchange())
    drv = ld.LiveDriver(seq_source([]), ex.RiskGovernor(), broker, _accts(1))
    reports = drv.run(max_steps=3)
    assert len(reports) == 3
    assert [r["tick"] for r in reports] == [1, 2, 3]
