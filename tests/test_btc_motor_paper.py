# -*- coding: utf-8 -*-
"""
BTC MOTOR PAPER — guarda de SEGURIDAD del pipeline paralelo.

El pipeline BTC (paper-only, 0% real) corre fusion_engine.evaluate_signal sobre
barras BTC y alimenta un motor paper propio. Invariante CRITICO: con
FQ_MOTOR_PAPER_BTC sin setear (default), la pasada es un NO-OP INMEDIATO que ni
toca el exchange — desplegar el codigo NO cambia nada en el bot vivo hasta que se
prende el env. Estos tests sellan esa garantia.
"""
import fq_bot_v3_2 as b


def test_btc_motor_paper_off_by_default():
    """Default OFF: la pasada BTC no hace nada y NO toca el exchange.
    Si tocara el exchange (None), reventaria -> debe retornar None sin error."""
    assert b.BTC_MOTOR_PAPER_ENABLED is False
    assert b._btc_motor_paper_scan(None) is None


def test_btc_motor_paper_guard_when_runtime_none(monkeypatch):
    """Aun 'prendido', si el runtime no se arma (p.ej. sin Volume), retorna sin
    tocar el exchange (exchange=None no se usa) -> nunca rompe el loop."""
    monkeypatch.setattr(b, "BTC_MOTOR_PAPER_ENABLED", True)
    monkeypatch.setattr(b, "_btc_motor_runtime", lambda: None)
    assert b._btc_motor_paper_scan(None) is None


def test_btc_motor_tf_is_research_tf():
    """El TF del pipeline BTC default = 5m (el TF del research/cosecha), no el
    15m del bot vivo. Igualar la poblacion medida es la condicion de validez."""
    assert b.BTC_MOTOR_TF == "5m"
