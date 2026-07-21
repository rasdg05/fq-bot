# -*- coding: utf-8 -*-
"""Ajuste de pesos de cierre parcial del RADAR segun el ledger real
(2026-07-21, RasDG: "ajusta el battle planner/RADAR para priorizar TP2 como
objetivo principal SI EL DATO LO RESPALDA"). El picker tactico (
_compute_tactical_tps) usaba 40/35/25 fijo, calibrado sobre solo DOS
ganadoras historicas que cerraron en TP2 (ver su propio docstring). Con
/tphits ya medible, _empirical_tp_weights reemplaza ese fijo por un ajuste
condicionado a datos reales -- nunca a ciegas, nunca sin muestra suficiente.

Kill switch FQ_TP_WEIGHT_EMPIRICAL, default OFF: el codigo YA sabe calcular
el ajuste, pero no se enciende solo -- RasDG lo activa cuando /tphits
confirme el patron con mas de 2 señales."""
import inspect

import fq_bot_v3_2 as b


def test_flag_off_por_defecto():
    assert b.TP_WEIGHT_EMPIRICAL_ENABLED is False


def test_default_cuando_flag_apagado(monkeypatch):
    """Aun con datos que respaldarian el boost, si el flag esta OFF (default)
    no se toca nada -- comportamiento historico intacto."""
    monkeypatch.setattr(b, "TP_WEIGHT_EMPIRICAL_ENABLED", False)
    monkeypatch.setattr(b.ev, "get_tp_distribution_by_tf",
                        lambda symbol=None: {"5m": {"n": 100, "top_tp": "tp2",
                                                     "top_tp_pct": 0.9}})
    assert b._empirical_tp_weights(tf_id="5m") == b._DEFAULT_TACTICAL_TP_WEIGHTS


def test_default_cuando_muestra_insuficiente(monkeypatch):
    monkeypatch.setattr(b, "TP_WEIGHT_EMPIRICAL_ENABLED", True)
    monkeypatch.setattr(b.ev, "get_tp_distribution_by_tf",
                        lambda symbol=None: {"5m": {"n": 5, "top_tp": "tp2",
                                                     "top_tp_pct": 0.9}})
    assert b._empirical_tp_weights(tf_id="5m") == b._DEFAULT_TACTICAL_TP_WEIGHTS


def test_default_cuando_top_tp_no_es_tp2(monkeypatch):
    """La hipotesis es especifica de TP2 -- si domina TP1 o TP3, no se boostea
    (ese caso no es el que RasDG observo)."""
    monkeypatch.setattr(b, "TP_WEIGHT_EMPIRICAL_ENABLED", True)
    monkeypatch.setattr(b.ev, "get_tp_distribution_by_tf",
                        lambda symbol=None: {"5m": {"n": 100, "top_tp": "tp1",
                                                     "top_tp_pct": 0.9}})
    assert b._empirical_tp_weights(tf_id="5m") == b._DEFAULT_TACTICAL_TP_WEIGHTS


def test_default_cuando_pct_debajo_del_umbral(monkeypatch):
    monkeypatch.setattr(b, "TP_WEIGHT_EMPIRICAL_ENABLED", True)
    monkeypatch.setattr(b.ev, "get_tp_distribution_by_tf",
                        lambda symbol=None: {"5m": {"n": 100, "top_tp": "tp2",
                                                     "top_tp_pct": 0.30}})
    assert b._empirical_tp_weights(tf_id="5m") == b._DEFAULT_TACTICAL_TP_WEIGHTS


def test_default_cuando_tf_no_esta_en_la_distribucion(monkeypatch):
    monkeypatch.setattr(b, "TP_WEIGHT_EMPIRICAL_ENABLED", True)
    monkeypatch.setattr(b.ev, "get_tp_distribution_by_tf",
                        lambda symbol=None: {"15m": {"n": 100, "top_tp": "tp2",
                                                      "top_tp_pct": 0.9}})
    assert b._empirical_tp_weights(tf_id="5m") == b._DEFAULT_TACTICAL_TP_WEIGHTS


def test_boost_cuando_todo_alinea(monkeypatch):
    monkeypatch.setattr(b, "TP_WEIGHT_EMPIRICAL_ENABLED", True)
    monkeypatch.setattr(b.ev, "get_tp_distribution_by_tf",
                        lambda symbol=None: {"5m": {"n": 23, "top_tp": "tp2",
                                                     "top_tp_pct": 0.68}})
    w = b._empirical_tp_weights(tf_id="5m")
    assert w != b._DEFAULT_TACTICAL_TP_WEIGHTS
    assert sum(w) == 100
    assert w[1] > b._DEFAULT_TACTICAL_TP_WEIGHTS[1]   # slot medio pesa mas


def test_excepcion_en_ev_cae_a_default(monkeypatch):
    """Un fallo del ledger (DB no lista, etc.) jamas debe romper una alerta
    tactica en vivo -- cae al default silenciosamente."""
    monkeypatch.setattr(b, "TP_WEIGHT_EMPIRICAL_ENABLED", True)
    def _boom(symbol=None):
        raise RuntimeError("db lock")
    monkeypatch.setattr(b.ev, "get_tp_distribution_by_tf", _boom)
    assert b._empirical_tp_weights(tf_id="5m") == b._DEFAULT_TACTICAL_TP_WEIGHTS


def test_compute_tactical_tps_usa_weights_override():
    tps = b._compute_tactical_tps("long", 100.0, 98.0, weights=(30, 45, 25))
    assert [t["weight_pct"] for t in tps] == [30, 45, 25]


def test_compute_tactical_tps_sin_weights_usa_default():
    tps = b._compute_tactical_tps("long", 100.0, 98.0)
    assert [t["weight_pct"] for t in tps] == list(b._DEFAULT_TACTICAL_TP_WEIGHTS)


def test_radar_check_llama_empirical_weights_y_lo_pasa_al_picker():
    """radar_check es un loop grande y dificil de disparar end-to-end (ver
    test_radar_candle_minutes.py); se sella por inspeccion de fuente que la
    rama de promocion consulta _empirical_tp_weights y lo pasa a
    _compute_tactical_tps, igual criterio que otros loops de este archivo."""
    src = inspect.getsource(b.radar_check)
    assert "_empirical_tp_weights(" in src
    idx = src.index("_compute_tactical_tps(")
    call = src[idx: src.index(")", src.index("weights=", idx))]
    assert "weights=tp_weights" in call
