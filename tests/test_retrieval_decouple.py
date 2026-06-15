# -*- coding: utf-8 -*-
"""Decoupling test del gate ORO (§6.6): FQ_RETRIEVAL_DECOUPLE agrega variantes
'no_scorer'/'no_regime' que dropean esas features del vector, dejando el resto
(y la base) intactos. Default OFF.
"""
import bt_retrieval as rt


def test_no_decouple_by_default(monkeypatch):
    monkeypatch.delenv("FQ_RETRIEVAL_DECOUPLE", raising=False)
    assert set(rt.vector_variants()) == {"base", "quantum"}


def test_decouple_drops_scorer_and_regime(monkeypatch):
    monkeypatch.setenv("FQ_RETRIEVAL_DECOUPLE", "scorer,regime")
    v = rt.vector_variants()
    assert "no_scorer" in v and "no_regime" in v
    # no_scorer: ninguna feature scorer_* en el numérico; la base SÍ las tiene
    assert not any(c.startswith("scorer_") for c in v["no_scorer"].numeric)
    assert any(c.startswith("scorer_") for c in v["base"].numeric)
    # no_regime: regime_score fuera de numeric, regime_state fuera de categorical
    assert "regime_score" not in v["no_regime"].numeric
    assert "regime_state" not in v["no_regime"].categorical
    assert "regime_score" in v["base"].numeric
    # el resto del vector queda intacto
    assert "p_master" in v["no_scorer"].numeric


def test_unknown_group_ignored(monkeypatch):
    monkeypatch.setenv("FQ_RETRIEVAL_DECOUPLE", "scorer,bogus")
    v = rt.vector_variants()
    assert "no_scorer" in v and "no_bogus" not in v
