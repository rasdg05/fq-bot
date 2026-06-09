# -*- coding: utf-8 -*-
"""
gold_paper: runtime en papel del gate ORO. Engine con gate inyectable + notify
espia -> sin red ni monolito. Verifica abrir-en-ORO, avisar admin, resolver
contra la vela, y que el gobernador puede vetar.
"""
from types import SimpleNamespace

import pytest

import execution as ex
import retrieval_gate as rg
import gold_live as gl
import gold_paper as gp


class FakeGate:
    def __init__(self, tier):
        self.tier = tier

    def classify(self, state):
        return {"tier": self.tier, "expectancy_r": 1.0, "abstain": False,
                "n_in_radius": 40, "confidence": 0.9}


def _field(direction="long"):
    return SimpleNamespace(propose_direction=lambda: direction,
                           confluence_count=2, pd_pct=0.1, w_effective=1.0,
                           node_type="OB", killzone="ny", killzone_priority=1,
                           bias_4h="alcista", bias_1h="alcista", choch=False,
                           has_fuel=True)


def _report():
    return {"p_master_data": {"p_master": 3.9}, "score": {"breakdown": []},
            "regime": {"state": "tendencia"}}


def _levels(df, direction):
    return {"sl": 99.0 if str(direction).lower() == "long" else 101.0, "tp1": 101.0}


def _runtime(tier, **kw):
    eng = gl.GoldLiveEngine(FakeGate(tier), "BTC/USDT:USDT",
                            calculate_levels_fn=_levels, tp_r=1.0)
    return gp.GoldPaperRuntime(eng, account=ex.Account("paper", 10_000.0), **kw)


def test_opens_paper_position_and_notifies_on_gold():
    notes = []
    rt = _runtime(rg.GOLD, notify_fn=lambda sig, verdict, pos: notes.append((sig, pos.pid)))
    rep = rt.on_bar(_field("long"), _report(), None, 100.0)
    assert rep["tier"] == rg.GOLD
    assert rep["opened"] is not None and rep["opened"]["stop"] == 99.0
    assert len(rt.account.open) == 1
    assert len(notes) == 1                       # aviso admin disparado
    # sellado en el ledger del broker (track record forward)
    assert rt.broker.ledger.verify()
    assert rt.broker.ledger.records[-1]["payload"]["event"] == "OPEN"


def test_no_open_on_base():
    rt = _runtime(rg.BASE)
    rep = rt.on_bar(_field(), _report(), None, 100.0)
    assert rep["opened"] is None and len(rt.account.open) == 0


def test_resolves_open_against_bar():
    rt = _runtime(rg.GOLD)
    rt.on_bar(_field("long"), _report(), None, 100.0)        # abre (entry100/sl99/tp101)
    assert len(rt.account.open) == 1
    # vela que toca TP1
    rep = rt.on_bar(_field("long"), _report(), None, 100.0, high=101.5, low=100.2)
    assert any(r["reason"] == "tp" for r in rep["resolved"])


def test_governor_can_veto_gold():
    rt = _runtime(rg.GOLD, governor=ex.RiskGovernor(ex.GovernorConfig(kill_switch=True)))
    rep = rt.on_bar(_field("long"), _report(), None, 100.0)
    assert rep["opened"] is None                 # kill-switch -> no abre aunque sea ORO


def test_reconcile_runs_every_n():
    calls = []
    recon = SimpleNamespace(check=lambda accounts=None: calls.append(1))
    rt = _runtime(rg.BASE, reconciler=recon, reconcile_every=2)
    rt.on_bar(_field(), _report(), None, 100.0)   # tick 1 -> no
    rt.on_bar(_field(), _report(), None, 100.0)   # tick 2 -> si
    assert len(calls) == 1
