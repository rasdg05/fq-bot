# -*- coding: utf-8 -*-
"""Tier FREE + candado anti-mezcla (reglas de RasDG 2026-06-30):
- Una señal VIP JAMÁS llega a FREE -> free_leak_guard la BLOQUEA.
- Una FREE sí puede llegar a VIP -> siempre etiquetada 'Señal FREE' (audience='vip', sin upsell).
- Texto distintivo: FREE dice 'Señal FREE'; VIP dice 'Senal VIP'; nunca se confunden."""
import types

import vip_format as vf


def _field():
    return types.SimpleNamespace(
        bias_aligned=True, pd_zone="discount", has_fuel=True, recent_sweep="low",
        pool_low=True, pool_high=False, confluence_count=4, node_type="colapso",
        pd_hierarchy="OTE", killzone="ny_am_kz")


def _report():
    return {"direction": "short",
            "p_master_data": {"p_master": 2.5},
            "levels": {"entry": 199.20, "sl": 199.70, "risk": 0.50,
                       "tp1": 196.72, "rr_tp1": 4.98, "tp2": 195.18, "rr_tp2": 8.06,
                       "tp3": 193.94, "rr_tp3": 10.55, "tp4": 192.70, "rr_tp4": 13.04}}


def test_free_solo_tp1_sin_boosts():
    m = vf.build_free_signal(_report(), "SOL/USDT", kl_passed=True)
    assert "Señal FREE" in m and "SOL/USDT" in m
    assert "$199.20" in m and "$196.72" in m               # entry + TP1
    assert "TP2" not in m and "TP3" not in m and "TP4" not in m   # FREE = SOLO TP1
    assert "P_master" not in m and "kappa" not in m        # sin internos


def test_free_etiqueta_por_filtro():
    passed = vf.build_free_signal(_report(), "BTC/USDT", kl_passed=True)
    filtered = vf.build_free_signal(_report(), "BTC/USDT", kl_passed=False)
    assert "CALIDAD VIP" in passed and "FILTRADA" not in passed
    assert "FILTRADA del VIP" in filtered and "CALIDAD VIP" not in filtered


def test_candado_bloquea_mensaje_vip():
    """SEGURIDAD: el mensaje VIP real (4 TPs, convicción, leverage) NO pasa el candado."""
    vip_msg = vf.build_vip_signal(_field(), _report(), pair="SOL/USDT")
    assert "Senal VIP" in vip_msg                          # distintivo del tier VIP
    assert "Señal FREE" not in vip_msg                     # y jamás se hace pasar por FREE
    assert vf.free_leak_guard(vip_msg) is False            # <- el candado lo BLOQUEA


def test_candado_acepta_free_puro():
    for kp in (True, False):
        m = vf.build_free_signal(_report(), "ETH/USDT", kl_passed=kp)
        assert vf.free_leak_guard(m) is True
        for marker in vf.VIP_ONLY_MARKERS:                 # cero marcadores premium
            assert marker not in m


def test_free_hacia_vip_etiquetada_sin_upsell():
    """FREE sí puede llegar a VIP: etiquetada 'Señal FREE', informativa, SIN upsell."""
    m = vf.build_free_signal(_report(), "ETH/USDT", kl_passed=False, audience="vip")
    assert "Señal FREE" in m                               # regla: siempre marcada como free
    assert "NO pasó el filtro" in m and "Informativa" in m
    assert "⭐ VIP:" not in m                               # sin upsell para quien ya paga
    assert vf.free_leak_guard(m) is True
