# -*- coding: utf-8 -*-
"""Multi-simbolo (2026-07-20): snapshot_for_general/pspace/niveles llamaban a
get_funding_rate()/get_open_interest()/get_oi_history()/get_long_short_ratio()/
get_order_book() SIN symbol -> siempre traian los derivados de SOL (default de
esas funciones), sin importar que /analisis estuviera mostrando precio e
indicadores de BTC o ETH. Estos tests sellan que el symbol/ccy pedido llega
hasta la llamada real; sin argumento, cae al comportamiento historico (SOL)."""
import pandas as pd

import market_context as mctx


def _df():
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=30, freq="5min"),
        "open": [100.0] * 30, "high": [101.0] * 30,
        "low": [99.0] * 30, "close": [100.0] * 30, "volume": [10.0] * 30,
    })


def _recorder(seen, key):
    """Fake get_* que registra el symbol recibido y siempre devuelve None
    (rama 'no disponible', la mas simple de ejercitar)."""
    def _fake(symbol=None):
        seen[key] = symbol
        return None
    return _fake


def test_snapshot_for_general_pasa_symbol_y_ccy(monkeypatch):
    seen = {}
    monkeypatch.setattr(mctx, "get_funding_rate", _recorder(seen, "funding"))
    monkeypatch.setattr(mctx, "get_open_interest", _recorder(seen, "oi"))
    monkeypatch.setattr(mctx, "get_oi_history", _recorder(seen, "oi_hist"))
    monkeypatch.setattr(mctx, "get_long_short_ratio", _recorder(seen, "ls"))
    monkeypatch.setattr(mctx, "detect_all_events", lambda df: [])
    monkeypatch.setattr(mctx, "candle_evolution", lambda df, n=5: [])

    mctx.snapshot_for_general(_df(), {"price": 100.0}, symbol="BTC-USDT-SWAP", ccy="BTC")

    assert seen["funding"] == "BTC-USDT-SWAP"
    assert seen["oi"] == "BTC-USDT-SWAP"
    assert seen["oi_hist"] == "BTC-USDT-SWAP"
    assert seen["ls"] == "BTC"


def test_snapshot_for_general_sin_symbol_cae_a_default(monkeypatch):
    """Comportamiento historico intacto: sin symbol/ccy, se llama sin args
    (usa el default SOL de cada funcion get_*)."""
    called_bare = []

    def fake_funding():
        called_bare.append(True)
        return None
    monkeypatch.setattr(mctx, "get_funding_rate", fake_funding)
    monkeypatch.setattr(mctx, "get_open_interest", lambda: None)
    monkeypatch.setattr(mctx, "get_oi_history", lambda: None)
    monkeypatch.setattr(mctx, "get_long_short_ratio", lambda: None)
    monkeypatch.setattr(mctx, "detect_all_events", lambda df: [])
    monkeypatch.setattr(mctx, "candle_evolution", lambda df, n=5: [])

    mctx.snapshot_for_general(_df(), {"price": 100.0})
    assert called_bare == [True]


def test_snapshot_for_pspace_pasa_symbol_al_order_book(monkeypatch):
    seen = {}
    monkeypatch.setattr(mctx, "get_order_book", _recorder(seen, "ob"))
    monkeypatch.setattr(mctx, "detect_all_events", lambda df: [])

    mctx.snapshot_for_pspace(_df(), {"price": 100.0}, {"masses": []}, symbol="ETH-USDT-SWAP")
    assert seen["ob"] == "ETH-USDT-SWAP"


def test_snapshot_for_niveles_pasa_symbol_a_funding_y_order_book(monkeypatch):
    seen = {}
    monkeypatch.setattr(mctx, "get_funding_rate", _recorder(seen, "funding"))
    monkeypatch.setattr(mctx, "get_order_book", _recorder(seen, "ob"))
    monkeypatch.setattr(mctx, "detect_all_events", lambda df: [])
    monkeypatch.setattr(mctx, "candle_evolution", lambda df, n=3: [])

    mctx.snapshot_for_niveles(_df(), {"price": 100.0}, {}, {}, symbol="BTC-USDT-SWAP")
    assert seen["funding"] == "BTC-USDT-SWAP"
    assert seen["ob"] == "BTC-USDT-SWAP"
