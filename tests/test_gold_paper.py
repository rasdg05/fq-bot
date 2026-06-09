# -*- coding: utf-8 -*-
"""
gold_paper: runtime en papel del gate ORO. Engine con gate inyectable + notify
espia -> sin red ni monolito. Verifica abrir-en-ORO, avisar admin, resolver
contra la vela, y que el gobernador puede vetar.
"""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import execution as ex
import retrieval_gate as rg
import gold_live as gl
import gold_paper as gp


class Spy:
    """notify_fn que registra TODAS las llamadas (incl. alert/digest con sig=None)."""
    def __init__(self):
        self.calls = []

    def __call__(self, sig, verdict, pos):
        self.calls.append((sig, verdict, pos))


def _make_gate_dir(tmp_path, *, bad_feature=False):
    rng = np.random.default_rng(0)
    n = 120
    feat = rng.uniform(-1.0, 1.0, n)
    df = pd.DataFrame({"entry_index": np.arange(n),
                       "pnl_r": feat * 1.2 + rng.normal(0, 0.1, n),
                       "p_master": feat + 3.0, "scorer_structure": feat * 0.8,
                       "direction": ex.LONG})
    numeric = ["p_master", "scorer_structure"] + (["feature_inexistente"] if bad_feature else [])
    vec = rg.btr.StateVectorizer(numeric=numeric, categorical=["direction"])
    idx = rg.StateIndex.build(df, vectorizer=vec)
    gate = rg.GoldGate(idx, gold_threshold=0.5, k=30, sim_floor=0.0, n_floor=3)
    d = str(tmp_path / "okx" / "BTC_USDT")
    gate.save(d, meta_extra={"symbol": "BTC/USDT"})
    return d


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


# --------------------------------------------------------------------------
# from_env: ledger durable + reconciler auto (gated) + telemetria
# --------------------------------------------------------------------------
def test_from_env_durable_ledger_and_reconciler_gated(tmp_path, monkeypatch):
    d = _make_gate_dir(tmp_path)
    led = str(tmp_path / "gold_led.jsonl")
    monkeypatch.setenv("FQ_RETRIEVAL_DIR", d)
    monkeypatch.setenv("FQ_GOLD_LEDGER_PATH", led)
    monkeypatch.setenv("FQ_GOLD_BASELINE_R", "0.3")     # enciende el reconciler
    rt = gp.GoldPaperRuntime.from_env("BTC/USDT", calculate_levels_fn=_levels)
    assert isinstance(rt.broker.ledger, ex.DurableHashLedger)
    assert rt.reconciler is not None                    # baseline -> reconcile ON
    rep = rt.on_bar(_field("long"), _report(), None, 100.0)
    assert rep["tier"] == rg.GOLD and rep["opened"] is not None
    # el track record sobrevive a un "restart"
    assert ex.DurableHashLedger.load(led).verify()


def test_from_env_no_baseline_disables_reconciler(tmp_path, monkeypatch):
    d = _make_gate_dir(tmp_path)
    monkeypatch.setenv("FQ_RETRIEVAL_DIR", d)
    monkeypatch.setenv("FQ_GOLD_LEDGER_PATH", str(tmp_path / "l.jsonl"))
    monkeypatch.delenv("FQ_GOLD_BASELINE_R", raising=False)
    rt = gp.GoldPaperRuntime.from_env("BTC/USDT", calculate_levels_fn=_levels)
    assert rt.reconciler is None                        # sin baseline -> no kill espurio


def test_coverage_alert_when_vector_feature_missing(tmp_path, monkeypatch):
    d = _make_gate_dir(tmp_path, bad_feature=True)       # el vector espera una feature ausente
    monkeypatch.setenv("FQ_RETRIEVAL_DIR", d)
    monkeypatch.setenv("FQ_GOLD_LEDGER_PATH", str(tmp_path / "l.jsonl"))
    spy = Spy()
    rt = gp.GoldPaperRuntime.from_env("BTC/USDT", calculate_levels_fn=_levels, notify_fn=spy)
    rt.on_bar(_field("long"), _report(), None, 100.0)
    alerts = [v for s, v, p in spy.calls if isinstance(v, dict) and v.get("alert")]
    assert alerts and "feature_inexistente" in alerts[0]["missing"]


def test_digest_emitted_every_n():
    spy = Spy()
    rt = _runtime(rg.BASE, notify_fn=spy)
    rt.digest_every = 2
    rt.on_bar(_field(), _report(), None, 100.0)          # tick 1
    rt.on_bar(_field(), _report(), None, 100.0)          # tick 2 -> digest
    digests = [v for s, v, p in spy.calls if isinstance(v, dict) and "digest" in v]
    assert digests and digests[0]["digest"]["base"] == 2


def test_counts_track_tiers():
    rt = _runtime(rg.GOLD)
    rt.on_bar(_field("long"), _report(), None, 100.0)
    assert rt.counts["gold"] == 1 and rt.counts["base"] == 0
