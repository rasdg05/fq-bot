# -*- coding: utf-8 -*-
"""
retrieval_gate (F2): núcleo de decisión ORO por expectancy del vecindario.
Datos sintéticos -> índice k-NN exacto, determinista, sin red. Verifica que el
gate discrimina oro/base/abstain y que la señal oro es consumible por la capa
de ejecución (paper).
"""
import numpy as np
import pandas as pd
import pytest

import execution as ex
import retrieval_gate as rg


# --------------------------------------------------------------------------
# dataset sintético: pnl_r correlaciona con el estado -> vecindarios discriminan
# --------------------------------------------------------------------------
def _past(n=120, seed=0):
    rng = np.random.default_rng(seed)
    feat = rng.uniform(-1.0, 1.0, n)
    pnl = feat * 1.2 + rng.normal(0, 0.1, n)          # estado bueno -> pnl alto
    return pd.DataFrame({
        "entry_index": np.arange(n),
        "pnl_r": pnl,
        "p_master": feat + 3.0,
        "scorer_structure": feat * 0.8,
        "direction": np.where(feat >= 0, "long", "short"),
    })


_HIGH = {"p_master": 3.95, "scorer_structure": 0.78, "direction": "long",
         "entry_index": 500}
_LOW = {"p_master": 2.05, "scorer_structure": -0.78, "direction": "short",
        "entry_index": 501}


# --------------------------------------------------------------------------
# calibrate_gold_threshold
# --------------------------------------------------------------------------
def test_calibrate_threshold_is_quantile():
    vals = list(np.linspace(0.0, 1.0, 101))      # 0.00..1.00
    thr = rg.calibrate_gold_threshold(vals, top_pct=0.05)
    assert thr == pytest.approx(0.95, abs=1e-9)


def test_calibrate_threshold_empty():
    assert rg.calibrate_gold_threshold([None, float("nan")]) is None


# --------------------------------------------------------------------------
# StateIndex.query: el vecindario discrimina por estado
# --------------------------------------------------------------------------
def test_index_query_discriminates():
    idx = rg.StateIndex.build(_past())
    hi = idx.query(_HIGH, k=30, sim_floor=0.0, n_floor=3)
    lo = idx.query(_LOW, k=30, sim_floor=0.0, n_floor=3)
    assert not hi["abstain"] and not lo["abstain"]
    assert hi["expectancy_r"] > lo["expectancy_r"]      # estado bueno paga más
    assert hi["expectancy_r"] > 0 > lo["expectancy_r"]


def test_index_query_returns_stats_fields():
    idx = rg.StateIndex.build(_past())
    st = idx.query(_HIGH, k=20, sim_floor=0.0, n_floor=3)
    for kf in ("expectancy_r", "wr", "dispersion", "n_in_radius",
               "confidence", "abstain"):
        assert kf in st


# --------------------------------------------------------------------------
# GoldGate.classify: oro / base / abstain
# --------------------------------------------------------------------------
def test_gate_classifies_gold_and_base():
    idx = rg.StateIndex.build(_past())
    gate = rg.GoldGate(idx, gold_threshold=0.5, k=30, sim_floor=0.0, n_floor=3)
    assert gate.classify(_HIGH)["tier"] == rg.GOLD     # exp alto >= 0.5
    assert gate.classify(_LOW)["tier"] == rg.BASE      # exp bajo < 0.5


def test_gate_abstains_on_sparse_neighborhood():
    idx = rg.StateIndex.build(_past())
    gate = rg.GoldGate(idx, gold_threshold=0.0, k=30, sim_floor=0.0,
                       n_floor=10_000)                 # exige más vecinos que hay
    assert gate.classify(_HIGH)["tier"] == rg.ABSTAIN


def test_gate_no_threshold_never_gold():
    idx = rg.StateIndex.build(_past())
    gate = rg.GoldGate(idx, gold_threshold=None, k=30, sim_floor=0.0, n_floor=3)
    assert gate.classify(_HIGH)["tier"] == rg.BASE     # sin umbral, no hay oro


# --------------------------------------------------------------------------
# build_gold_signal: TP1 a tp_r del riesgo
# --------------------------------------------------------------------------
def test_build_gold_signal_long():
    s = rg.build_gold_signal("BTC/USDT:USDT", rg.LONG, 100.0, 99.0, tp_r=1.0)
    assert s == {"symbol": "BTC/USDT:USDT", "direction": 1,
                 "entry": 100.0, "stop": 99.0, "tp": 101.0}


def test_build_gold_signal_short_and_zero_risk():
    s = rg.build_gold_signal("X", rg.SHORT, 100.0, 101.0, tp_r=2.0)
    assert s["tp"] == pytest.approx(98.0)              # short: entry - 2*risk
    assert rg.build_gold_signal("X", rg.LONG, 100.0, 100.0) is None


# --------------------------------------------------------------------------
# gold_signal_source: solo emite en ORO, y la señal es consumible por el broker
# --------------------------------------------------------------------------
def test_gate_save_load_roundtrip(tmp_path):
    idx = rg.StateIndex.build(_past())
    gate = rg.GoldGate(idx, gold_threshold=0.5, k=30, sim_floor=0.0, n_floor=3)
    out = str(tmp_path / "BTC")
    gate.save(out, meta_extra={"symbol": "BTC/USDT", "gold_top_pct": 0.05})
    g2 = rg.GoldGate.from_dir(out)
    # mismo umbral/params y misma decision tras el roundtrip
    assert g2.gold_threshold == pytest.approx(0.5)
    assert g2.k == 30 and g2.n_floor == 3
    assert g2.classify(_HIGH)["tier"] == rg.GOLD
    assert g2.classify(_LOW)["tier"] == rg.BASE


def test_gold_signal_source_emits_only_on_gold_and_is_broker_ready():
    idx = rg.StateIndex.build(_past())
    gate = rg.GoldGate(idx, gold_threshold=0.5, k=30, sim_floor=0.0, n_floor=3)
    feed = iter([_HIGH, _LOW, None])

    def state_feed():
        return next(feed, None)

    def level_fn(state):
        return ("BTC/USDT:USDT", rg.LONG, 100.0, 99.0)

    src = rg.gold_signal_source(gate, state_feed, level_fn=level_fn, tp_r=1.0)
    sig = src()                                        # _HIGH -> ORO -> señal
    assert sig is not None and sig["direction"] == 1
    assert src() is None                               # _LOW -> BASE -> no señal
    assert src() is None                               # feed agotado

    # la señal oro la abre el PaperBroker sin adaptaciones
    broker = ex.PaperBroker()
    acc = ex.Account("A1", 10_000.0)
    pos = broker.open(acc, sig, 0.0025)
    assert pos.symbol == "BTC/USDT:USDT" and pos.tp == 101.0
