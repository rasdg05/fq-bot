# -*- coding: utf-8 -*-
"""liquidation_feed: buffer + parser de liquidaciones (Binance). El runner
websocket no se testea (red); el buffer/parser/normalizacion si (puros)."""
import pytest

import liquidation_feed as lf


# --------------------------------------------------------------------------
# normalizacion de simbolo
# --------------------------------------------------------------------------
def test_binance_symbol_normaliza_formatos():
    assert lf._binance_symbol("SOL-USDT-SWAP") == "SOLUSDT"   # OKX
    assert lf._binance_symbol("SOL/USDT:USDT") == "SOLUSDT"   # ccxt perp
    assert lf._binance_symbol("BTC/USDT") == "BTCUSDT"        # ccxt spot
    assert lf._binance_symbol("ETHUSDT") == "ETHUSDT"         # ya binance
    assert lf._binance_symbol(None) is None


# --------------------------------------------------------------------------
# parser de forceOrder (side mapping: SELL=long liquidado, BUY=short liquidado)
# --------------------------------------------------------------------------
def test_parse_sell_es_long_liquidado():
    msg = {"e": "forceOrder", "o": {"s": "SOLUSDT", "S": "SELL", "ap": "100", "q": "50"}}
    sym, side, usd = lf.parse_force_order(msg)
    assert sym == "SOLUSDT" and side == "long" and usd == pytest.approx(5000.0)


def test_parse_buy_es_short_liquidado():
    msg = {"o": {"s": "BTCUSDT", "S": "BUY", "ap": "20000", "q": "0.5"}}
    sym, side, usd = lf.parse_force_order(msg)
    assert side == "short" and usd == pytest.approx(10000.0)


def test_parse_invalido_es_none():
    assert lf.parse_force_order({}) is None
    assert lf.parse_force_order({"o": {"s": "X", "S": "SELL", "ap": "0", "q": "0"}}) is None
    assert lf.parse_force_order({"o": {"s": "X", "S": "OTHER", "ap": "1", "q": "1"}}) is None


# --------------------------------------------------------------------------
# buffer: intensity, skew, ventana, filtro por simbolo
# --------------------------------------------------------------------------
def test_buffer_intensity_y_skew():
    buf = lf.LiquidationBuffer(window_sec=300, intensity_ref_usd=10000.0)
    now = 1_000_000
    buf.ingest(now, "SOLUSDT", "short", 6000.0)   # mas SHORT liquidado -> skew>0
    buf.ingest(now, "SOLUSDT", "long", 2000.0)
    snap = buf.snapshot("SOLUSDT", now)
    assert snap["fresh"] is True
    assert snap["intensity"] == pytest.approx(0.8)               # 8000/10000
    assert snap["skew"] == pytest.approx((6000 - 2000) / 8000)   # +0.5


def test_buffer_intensity_capada_en_1():
    buf = lf.LiquidationBuffer(window_sec=300, intensity_ref_usd=1000.0)
    buf.ingest(1, "SOLUSDT", "short", 50000.0)
    assert buf.snapshot("SOLUSDT", 1)["intensity"] == 1.0


def test_buffer_prune_por_ventana():
    buf = lf.LiquidationBuffer(window_sec=60, intensity_ref_usd=10000.0)
    buf.ingest(1_000_000, "SOLUSDT", "short", 5000.0)
    snap = buf.snapshot("SOLUSDT", 1_000_000 + 61_000)   # 61s despues -> fuera
    assert snap["fresh"] is False and snap["intensity"] == 0.0


def test_buffer_filtra_por_simbolo():
    buf = lf.LiquidationBuffer(window_sec=300, intensity_ref_usd=10000.0)
    buf.ingest(2_000_000, "BTCUSDT", "short", 9000.0)
    assert buf.snapshot("SOLUSDT", 2_000_000)["fresh"] is False


# --------------------------------------------------------------------------
# snapshot(): off por default -> no-fresh (degrada a vol-only), no arranca el feed
# --------------------------------------------------------------------------
def test_snapshot_disabled_no_fresh(monkeypatch):
    monkeypatch.setattr(lf, "ENABLED", False)
    snap = lf.snapshot("SOL/USDT")
    assert snap["fresh"] is False and snap["intensity"] == 0.0
