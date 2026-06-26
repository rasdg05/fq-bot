# -*- coding: utf-8 -*-
"""Badge de order-flow en la senal VIP (capa 3, FQ_CVD_VIP_CONVICTION).

OFF/None -> senal BYTE-IDENTICA a la historica. Confirmado -> agrega la linea
"ORDER-FLOW CONFIRMADO" sin tocar el resto. Es un HECHO (no promesa de R)."""
import vip_format
import motor_paper as mp


class _F:
    bias_aligned = True
    pd_zone = "discount"
    has_fuel = True
    recent_sweep = True
    pool_low = True
    pool_high = False
    confluence_count = 4
    node_type = "colapso"


def _decision():
    return {
        "direction": "long",
        "p_master_data": {"p_master": 3.0},
        "levels": {"entry": 145.0, "sl": 142.0, "risk": 3.0,
                   "tp1": 148.0, "rr_tp1": 1.0, "tp2": 151.0, "rr_tp2": 2.0,
                   "tp3": 154.0, "rr_tp3": 3.0, "tp4": 157.0, "rr_tp4": 4.0}}


def test_sin_cvd_la_senal_es_identica_a_la_historica():
    base = vip_format.build_vip_signal(_F(), _decision())
    none_ = vip_format.build_vip_signal(_F(), _decision(), cvd_confirmed=None)
    false_ = vip_format.build_vip_signal(_F(), _decision(), cvd_confirmed=False)
    assert base == none_ == false_              # backward-compat: byte-identica
    assert "ORDER-FLOW" not in base


def test_cvd_confirmado_agrega_el_badge():
    msg = vip_format.build_vip_signal(_F(), _decision(), cvd_confirmed=True)
    assert "ORDER-FLOW CONFIRMADO" in msg
    assert "◆" in msg                       # glyph premium ◆ (CONSTRAINTS §10)
    # el badge NO rompe el resto de la senal
    assert "Senal VIP" in msg and "Entry" in msg and "SL inmutable" in msg


def test_cvd_confirm_live_off_devuelve_none(monkeypatch):
    # sin FQ_CVD_FILTER el badge nunca se computa (None) -> defensivo, no badge
    monkeypatch.delenv("FQ_CVD_FILTER", raising=False)
    assert mp.cvd_confirm_live("BTC/USDT", 1_700_000_000_000, "long") is None


def test_cvd_confirm_live_sin_direccion_es_none(monkeypatch):
    monkeypatch.setenv("FQ_CVD_FILTER", "1")
    assert mp.cvd_confirm_live("BTC/USDT", 1_700_000_000_000, None) is None


def test_hashtag_dinamico_por_par():
    # antes HASHTAGS_SIGNAL hardcodeado a #SOLUSDT -> BTC/ETH salian con tag de SOL
    btc = vip_format.build_vip_signal(_F(), _decision(), pair="BTC/USDT")
    assert "#BTCUSDT" in btc and "#SOLUSDT" not in btc
    eth = vip_format.build_vip_signal(_F(), _decision(), pair="ETH/USDT")
    assert "#ETHUSDT" in eth
    sol = vip_format.build_vip_signal(_F(), _decision())   # default -> SOL/USDT
    assert "#SOLUSDT" in sol
