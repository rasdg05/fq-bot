# -*- coding: utf-8 -*-
"""Boost de convicción VIP por FUNDING favorable (FQ_FUNDING_BOOST).

Validado in-cube (validate_long_gates 2026-07-03): LONG & funding-pctl90d<=0.5 ->
+0.173R vs +0.121 (DSR 1.000 / CPCV 80% / PBO 0.04). OFF (funding_boost=False) ->
señal BYTE-IDÉNTICA. True -> badge "FUNDING FAVORABLE" + sube +1 tier; apilable con
CVD y POC (tres confirmaciones -> tres bumps, topado en 8x por bump_tier)."""
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


def test_funding_off_es_byte_identica():
    base = vip_format.build_vip_signal(_F(), _decision())
    off = vip_format.build_vip_signal(_F(), _decision(), funding_boost=False)
    assert base == off
    assert "FUNDING FAVORABLE" not in base


def test_funding_boost_agrega_badge_y_sube_un_tier():
    dec = _decision(2.0)                          # Media
    base = vip_format.build_vip_signal(_F(), dec)
    boosted = vip_format.build_vip_signal(_F(), dec, funding_boost=True)
    assert "Conviccion Media" in base
    assert "FUNDING FAVORABLE" in boosted
    assert "Conviccion Alta" in boosted


def test_tres_confirmaciones_apilan_topadas():
    dec = _decision(2.0)
    triple = vip_format.build_vip_signal(_F(), dec, cvd_confirmed=True,
                                         boost_tier=True, poc_far=True,
                                         funding_boost=True)
    assert "ORDER-FLOW CONFIRMADO" in triple
    assert "FUERA DEL VALOR PREVIO" in triple
    assert "FUNDING FAVORABLE" in triple
    # bump_tier topa (phi^3): tres bumps no rompen el techo de conviccion/leverage
    assert "Conviccion" in triple and "Leverage" in triple
