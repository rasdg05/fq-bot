# -*- coding: utf-8 -*-
"""Tier FREE (jugada de marketing): build_free_signal — el fire CRUDO del motor (solo TP1),
etiquetado según pase o no el filtro de calidad KL. El VIP sigue recibiendo solo las filtradas."""
import vip_format as vf


def _dr():
    return {"direction": "short",
            "levels": {"entry": 199.20, "sl": 199.70, "tp1": 196.72, "rr_tp1": 4.98}}


def test_free_solo_tp1_sin_boosts():
    m = vf.build_free_signal(_dr(), "SOL/USDT", kl_passed=True)
    assert "Señal FREE" in m and "SOL/USDT" in m
    assert "$199.20" in m and "$196.72" in m              # entry + TP1
    assert "TP2" not in m and "TP3" not in m and "TP4" not in m   # FREE = SOLO TP1
    assert "P_master" not in m and "kappa" not in m       # sin internos


def test_free_etiqueta_por_filtro():
    passed = vf.build_free_signal(_dr(), "BTC/USDT", kl_passed=True)
    filtered = vf.build_free_signal(_dr(), "BTC/USDT", kl_passed=False)
    assert "CALIDAD VIP" in passed and "FILTRADA" not in passed
    assert "FILTRADA del VIP" in filtered and "CALIDAD VIP" not in filtered
