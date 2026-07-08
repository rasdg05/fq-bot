# -*- coding: utf-8 -*-
"""Contexto cross-asset NASDAQ->cripto para la convicción VIP (FQ_CROSS_ASSET, default OFF).
La señal de reversión cripto que se ALINEA con el move reciente de NASDAQ es subset premium
(validado OOS 2021-26: alineada +0.431R vs contra +0.169R, gap TEST +0.274, DSR 1.000). Badge de
convicción, no señal nueva. Default OFF y todo fallo de red -> {} (señal byte-idéntica)."""
import types

import fq_bot_v3_2 as bot
import vip_format as vf


def _long():
    return {"direction": "long"}


def _short():
    return {"direction": "short"}


# --------- candado default OFF ---------

def test_off_no_kwargs(monkeypatch):
    monkeypatch.setattr(bot, "CROSS_ASSET_ENABLED", False)
    assert bot._cross_asset_vip_kwargs(_long()) == {}


# --------- alineación (el edge validado) ---------

def test_long_con_nasdaq_arriba_confirma(monkeypatch):
    monkeypatch.setattr(bot, "CROSS_ASSET_ENABLED", True)
    monkeypatch.setattr(bot, "_nasdaq_direction", lambda: 1)
    assert bot._cross_asset_vip_kwargs(_long()) == {"cross_asset_confirmed": True}


def test_short_con_nasdaq_abajo_confirma(monkeypatch):
    monkeypatch.setattr(bot, "CROSS_ASSET_ENABLED", True)
    monkeypatch.setattr(bot, "_nasdaq_direction", lambda: -1)
    assert bot._cross_asset_vip_kwargs(_short()) == {"cross_asset_confirmed": True}


def test_long_con_nasdaq_abajo_no_confirma(monkeypatch):
    monkeypatch.setattr(bot, "CROSS_ASSET_ENABLED", True)
    monkeypatch.setattr(bot, "_nasdaq_direction", lambda: -1)
    assert bot._cross_asset_vip_kwargs(_long()) == {}


def test_short_con_nasdaq_arriba_no_confirma(monkeypatch):
    monkeypatch.setattr(bot, "CROSS_ASSET_ENABLED", True)
    monkeypatch.setattr(bot, "_nasdaq_direction", lambda: 1)
    assert bot._cross_asset_vip_kwargs(_short()) == {}


# --------- defensividad: sin data / red caída -> neutral ---------

def test_sin_data_nasdaq_neutral(monkeypatch):
    monkeypatch.setattr(bot, "CROSS_ASSET_ENABLED", True)
    monkeypatch.setattr(bot, "_nasdaq_direction", lambda: None)
    assert bot._cross_asset_vip_kwargs(_long()) == {}


def test_fetch_error_es_none(monkeypatch):
    monkeypatch.setattr(bot, "_NASDAQ_CACHE", {"ts": 0.0, "dir": None})
    def boom(*a, **k):
        raise RuntimeError("red caída")
    monkeypatch.setattr(bot, "requests", types.SimpleNamespace(get=boom))
    assert bot._nasdaq_direction() is None       # jamás lanza


def test_direccion_rara_neutral(monkeypatch):
    monkeypatch.setattr(bot, "CROSS_ASSET_ENABLED", True)
    monkeypatch.setattr(bot, "_nasdaq_direction", lambda: 1)
    assert bot._cross_asset_vip_kwargs({"direction": "n/a"}) == {}


# --------- render: badge SOLO cuando confirma; OFF byte-idéntico ---------

def _field():
    return types.SimpleNamespace(
        bias_aligned=True, pd_zone="discount", has_fuel=True, recent_sweep="low",
        pool_low=True, pool_high=False, confluence_count=4, node_type="colapso",
        pd_hierarchy="OTE", killzone="ny_am_kz")


def _report():
    return {"direction": "long", "p_master_data": {"p_master": 2.5},
            "levels": {"entry": 100.0, "sl": 98.0, "risk": 2.0, "tp1": 103.0, "rr_tp1": 1.5,
                       "tp2": 105.0, "rr_tp2": 2.5, "tp3": 107.0, "rr_tp3": 3.5,
                       "tp4": 109.0, "rr_tp4": 4.5}}


def test_badge_aparece_cuando_confirma():
    base = vf.build_vip_signal(_field(), _report(), pair="BTC/USDT")
    conf = vf.build_vip_signal(_field(), _report(), pair="BTC/USDT", cross_asset_confirmed=True)
    assert "NASDAQ CONFIRMA" not in base
    assert "NASDAQ CONFIRMA" in conf


def test_off_byte_identico():
    a = vf.build_vip_signal(_field(), _report(), pair="BTC/USDT")
    b = vf.build_vip_signal(_field(), _report(), pair="BTC/USDT", cross_asset_confirmed=False)
    assert a == b
