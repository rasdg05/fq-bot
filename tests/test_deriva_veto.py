# -*- coding: utf-8 -*-
"""
FQ_DERIVA_VETO — el veto de regime "deriva" es REVERSIBLE por env.

Default 1 (comportamiento previo: en lateral, downgrade a no-fire si el scorer no
confirma / si vol-liq no confirma). FQ_DERIVA_VETO=0 lo APAGA por completo -> el
gate de deriva se salta y los setups ESTRUCTURALES disparan también en lateral.
Lo predictivo está muerto OOS (research/edge_externo_2026.md) -> el veto es opcional.

Se testea el flag (el gate vivo es `if DERIVA_VETO_ENABLED and ...` en
fusion_engine.evaluate_signal); reload bajo cada env y se restaura al default.
"""
import importlib

import fusion_engine


def _reload(monkeypatch, val):
    if val is None:
        monkeypatch.delenv("FQ_DERIVA_VETO", raising=False)
    else:
        monkeypatch.setenv("FQ_DERIVA_VETO", val)
    importlib.reload(fusion_engine)
    return fusion_engine.DERIVA_VETO_ENABLED


def test_default_es_on(monkeypatch):
    try:
        assert _reload(monkeypatch, None) is True        # sin env -> veto ON (previo)
    finally:
        importlib.reload(fusion_engine)                  # restaura default


def test_cero_apaga_el_veto(monkeypatch):
    try:
        assert _reload(monkeypatch, "0") is False        # FQ_DERIVA_VETO=0 -> OFF
        assert _reload(monkeypatch, "1") is True         # y se puede volver a prender
    finally:
        importlib.reload(fusion_engine)


def test_gate_usa_el_flag():
    # el gate vivo debe estar condicionado por el flag (no hard-coded)
    import inspect
    src = inspect.getsource(fusion_engine.evaluate_signal)
    assert "DERIVA_VETO_ENABLED" in src
    # y el bloque de deriva sigue ahí (no se borró, sólo se gateó)
    assert 'regime_state["state"] == "deriva"' in src
