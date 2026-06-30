# -*- coding: utf-8 -*-
"""Boost de convicción VIP por POC-distance (FQ_POC_VIP_CONVICTION).

OFF (poc_far=False) -> senal BYTE-IDENTICA a la histórica. poc_far=True -> agrega
"FUERA DEL VALOR PREVIO" + sube +1 tier; apilable con el boost de CVD (dos
confirmaciones independientes -> dos bumps, topado en 8x)."""
import vip_format


class _F:
    bias_aligned = True
    pd_zone = "discount"
    has_fuel = True
    recent_sweep = True
    pool_low = True
    pool_high = False
    confluence_count = 4
    node_type = "colapso"


def _decision(pm=2.0):
    return {
        "direction": "long",
        "p_master_data": {"p_master": pm},
        "levels": {"entry": 145.0, "sl": 142.0, "risk": 3.0,
                   "tp1": 148.0, "rr_tp1": 1.0, "tp2": 151.0, "rr_tp2": 2.0,
                   "tp3": 154.0, "rr_tp3": 3.0, "tp4": 157.0, "rr_tp4": 4.0}}


def test_poc_off_es_byte_identica():
    base = vip_format.build_vip_signal(_F(), _decision())
    off = vip_format.build_vip_signal(_F(), _decision(), poc_far=False)
    assert base == off
    assert "FUERA DEL VALOR" not in base


def test_poc_far_agrega_badge_y_sube_un_tier():
    dec = _decision(2.0)                          # Media (3x / 2%)
    base = vip_format.build_vip_signal(_F(), dec)
    boosted = vip_format.build_vip_signal(_F(), dec, poc_far=True)
    assert "Conviccion Media" in base
    assert "FUERA DEL VALOR PREVIO" in boosted
    assert "Conviccion Alta" in boosted and "Leverage 5x" in boosted


def test_cvd_y_poc_apilan_dos_bumps():
    dec = _decision(2.0)                          # Media -> +CVD -> Alta -> +POC -> Extrema
    both = vip_format.build_vip_signal(_F(), dec, cvd_confirmed=True, boost_tier=True, poc_far=True)
    assert "Conviccion Extrema" in both and "Leverage 8x" in both
    assert "ORDER-FLOW CONFIRMADO" in both and "FUERA DEL VALOR PREVIO" in both
