# -*- coding: utf-8 -*-
"""
gold_live (F2 2b): adaptador del gate ORO al loop. Gate y calculate_levels
inyectables -> se prueba sin red ni monolito. Verifica que el state-row vivo lleva
las features del motor, que solo emite en ORO con direccion de campo, y que la
senal es consumible por el PaperBroker. Un test de integracion usa un gate real.
"""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import execution as ex
import retrieval_gate as rg
import gold_live as gl


# --------------------------------------------------------------------------
# dobles
# --------------------------------------------------------------------------
class FakeGate:
    def __init__(self, tier):
        self.tier = tier

    def classify(self, state):
        self.last_state = state
        return {"tier": self.tier, "expectancy_r": 1.0, "abstain": False,
                "n_in_radius": 40, "confidence": 0.9}


def _field(direction="long"):
    return SimpleNamespace(
        propose_direction=lambda: direction,
        confluence_count=3, pd_pct=0.2, w_effective=1.0, node_type="OB",
        killzone="ny", killzone_priority=1, bias_4h="alcista", bias_1h="alcista",
        choch=False, has_fuel=True)


def _report(p_master=3.9, structure=0.8):
    return {"p_master_data": {"p_master": p_master, "p_master_raw": p_master,
                              "kappa_evo": 1.0},
            "score": {"total_score": 1.2,
                      "breakdown": [{"name": "structure", "score": structure},
                                    {"name": "volume", "score": 0.5}]},
            "regime": {"state": "tendencia", "score": 0.6}}


def _levels(df, direction):
    return {"sl": 99.0 if str(direction).lower() == "long" else 101.0,
            "tp1": 101.0, "tp2": 102.0, "tp3": 103.0}


# --------------------------------------------------------------------------
# state-row vivo == features del motor
# --------------------------------------------------------------------------
def test_live_state_row_carries_engine_features():
    row = gl.live_state_row(_field(), _report(p_master=3.9, structure=0.8))
    assert row["direction"] == ex.LONG          # convencion del indice denso
    assert row["p_master"] == 3.9
    assert row["scorer_structure"] == 0.8
    assert row["field_killzone"] == "ny"


# --------------------------------------------------------------------------
# emite solo en ORO, con lectura de campo
# --------------------------------------------------------------------------
def test_emits_signal_on_gold_long():
    eng = gl.GoldLiveEngine(FakeGate(rg.GOLD), "BTC/USDT:USDT",
                            calculate_levels_fn=_levels, tp_r=1.0)
    sig, verdict = eng.evaluate(_field("long"), _report(), df_primary=None, price=100.0)
    assert verdict["tier"] == rg.GOLD
    assert sig == {"symbol": "BTC/USDT:USDT", "direction": ex.LONG,
                   "entry": 100.0, "stop": 99.0, "tp": 101.0}


def test_emits_short_with_field_direction():
    eng = gl.GoldLiveEngine(FakeGate(rg.GOLD), "ETH/USDT:USDT",
                            calculate_levels_fn=_levels, tp_r=2.0)
    sig, _ = eng.evaluate(_field("short"), _report(), df_primary=None, price=100.0)
    assert sig["direction"] == ex.SHORT
    assert sig["stop"] == 101.0 and sig["tp"] == pytest.approx(98.0)  # 100-2*1


def test_no_signal_on_base_or_abstain():
    for tier in (rg.BASE, rg.ABSTAIN):
        eng = gl.GoldLiveEngine(FakeGate(tier), "X",
                                calculate_levels_fn=_levels)
        sig, verdict = eng.evaluate(_field(), _report(), None, 100.0)
        assert sig is None and verdict["tier"] == tier


def test_gold_but_no_field_direction_skips():
    eng = gl.GoldLiveEngine(FakeGate(rg.GOLD), "X", calculate_levels_fn=_levels)
    sig, verdict = eng.evaluate(_field(direction=None), _report(), None, 100.0)
    assert sig is None and "skip" in verdict


def test_signal_source_feeds_broker():
    eng = gl.GoldLiveEngine(FakeGate(rg.GOLD), "BTC/USDT:USDT",
                            calculate_levels_fn=_levels)
    feed = iter([(_field("long"), _report(), None, 100.0), None])
    src = eng.signal_source(lambda: next(feed, None))
    sig = src()
    assert sig is not None
    broker = ex.PaperBroker()
    pos = broker.open(ex.Account("A1", 10_000.0), sig, 0.0025)
    assert pos.tp == 101.0
    assert src() is None                         # feed agotado


# --------------------------------------------------------------------------
# integracion con un GATE REAL (indice sintetico con el MISMO esquema de vector)
# --------------------------------------------------------------------------
def _past_same_schema(n=120, seed=0):
    rng = np.random.default_rng(seed)
    feat = rng.uniform(-1.0, 1.0, n)
    return pd.DataFrame({
        "entry_index": np.arange(n),
        "pnl_r": feat * 1.2 + rng.normal(0, 0.1, n),
        "p_master": feat + 3.0,
        "scorer_structure": feat * 0.8,
        "direction": ex.LONG,                    # misma convencion que live_state_row
    })


def test_integration_real_gate_emits_on_high_state():
    idx = rg.StateIndex.build(_past_same_schema())
    gate = rg.GoldGate(idx, gold_threshold=0.5, k=30, sim_floor=0.0, n_floor=3)
    eng = gl.GoldLiveEngine(gate, "BTC/USDT:USDT", calculate_levels_fn=_levels)
    # estado "bueno": p_master alto + scorer_structure alto -> vecindario paga -> ORO
    sig_hi, v_hi = eng.evaluate(_field("long"), _report(p_master=3.95, structure=0.78),
                                None, 100.0)
    sig_lo, v_lo = eng.evaluate(_field("long"), _report(p_master=2.05, structure=-0.78),
                                None, 100.0)
    assert v_hi["tier"] == rg.GOLD and sig_hi is not None
    assert v_lo["tier"] == rg.BASE and sig_lo is None
