# -*- coding: utf-8 -*-
"""
Veredicto QTE unificado: una sola fuente de verdad.

Antes, vip_format._market_tone y el bloque admin clasificaban el setup con
thresholds distintos -> VIP y admin podian contradecirse. Estos tests fijan
que ambas superficies derivan del MISMO qte_verdict.compute().
"""
import pytest

import qte_verdict
import quantum_timelines as qt
import vip_format


def _qa(p_sl, ev, coh=0.55, bull=0.5, bear=0.3, with_verdict=True, direction="long"):
    qa = {
        "n_paths": 500, "horizon_candles": 96, "horizon_hours": 24.0,
        "elapsed_ms": 70.0, "coherence": coh,
        "probabilities": {
            "p_sl": p_sl, "p_tp1": max(0.0, 1 - p_sl), "p_tp2": 0.0, "p_tp3": 0.0,
            "p_reach_tp1": max(0.0, 1 - p_sl), "p_reach_tp2": 0.0, "p_reach_tp3": 0.0,
            "p_timeout": 0.0, "expected_R": ev, "win_rate": max(0.0, 1 - p_sl),
        },
        "regimes": {"bull_continuation": bull, "bear_reversal": bear, "chop": 0.1},
        "dominant_regime": "bull_continuation", "dominant_regime_pct": bull,
        "vs_baseline": None,
    }
    if with_verdict:
        qa["verdict"] = qte_verdict.compute(qa, direction)
    return qa


# (p_sl, ev, grade esperado)
_GRADE_CASES = [
    (0.20, 1.5, "favorable"),   # edge fuerte
    (0.32, 1.1, "favorable"),   # edge favorable
    (0.50, 0.6, "moderado"),
    (1.00, -1.0, "adverso"),
    (0.62, 0.10, "neutro"),
]


@pytest.mark.parametrize("p_sl,ev,grade", _GRADE_CASES)
def test_compute_grades(p_sl, ev, grade):
    v = qte_verdict.compute(_qa(p_sl, ev, with_verdict=False), "long")
    assert v["grade"] == grade
    # Todas las claves presentes y no vacias
    assert v["label"] and v["tone"] and v["admin_body"]


def test_compute_none_si_no_hay_qa():
    assert qte_verdict.compute(None) is None
    assert qte_verdict.compute({}) is None


def test_compute_direction_aware():
    # Mismo p_sl/ev limite: la rama "edge fuerte" exige regimen a favor >=40%.
    qa_long_ok = _qa(0.28, 1.3, coh=0.6, bull=0.45, bear=0.05, with_verdict=False)
    qa_long_no = _qa(0.28, 1.3, coh=0.6, bull=0.05, bear=0.45, with_verdict=False)
    assert qte_verdict.compute(qa_long_ok, "long")["label"] == "EDGE FUERTE"
    # Sin regimen alcista a favor, no llega a "fuerte" (cae a favorable normal)
    assert qte_verdict.compute(qa_long_no, "long")["label"] == "EDGE FAVORABLE"


@pytest.mark.parametrize("p_sl,ev,grade", _GRADE_CASES)
def test_vip_y_admin_misma_fuente(p_sl, ev, grade):
    """El tono VIP y el veredicto admin salen del mismo qa['verdict']."""
    qa = _qa(p_sl, ev)
    tone = vip_format._market_tone(qa, "long")
    admin = qt.build_qte_block_admin(qa, "long")
    assert tone == qa["verdict"]["tone"]
    assert qa["verdict"]["label"] in admin
    assert "<" not in admin  # sigue libre de HTML roto


def test_market_tone_none_si_no_hay_qa():
    assert vip_format._market_tone(None, "long") is None


def test_optimizer_note_escala_con_delta():
    fuerte = qt._optimizer_note({"delta_R": 0.8})
    marginal = qt._optimizer_note({"delta_R": 0.2})
    nulo = qt._optimizer_note({"delta_R": 0.0})
    assert fuerte != marginal != nulo
    assert "<" not in (fuerte + marginal + nulo)
