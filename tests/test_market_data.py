# -*- coding: utf-8 -*-
"""
fq_market_data (etapa 2 de la migracion): acceso a velas + indicadores aislado
del runtime del bot. Se testea con un exchange falso (sin red).
"""
import pandas as pd

import fq_market_data as md


class _FakeExchange:
    """Exchange minimo estilo ccxt: devuelve OHLCV sinteticos."""
    def __init__(self):
        self.calls = []

    def fetch_ohlcv(self, symbol, timeframe, limit):
        self.calls.append((symbol, timeframe, limit))
        base_ms = 1_700_000_000_000
        # precio en rampa para que los indicadores tengan algo que masticar
        return [[base_ms + i * 60_000, 10.0 + i, 11.0 + i, 9.0 + i,
                 10.5 + i, 100.0 + i] for i in range(limit)]


def test_fetch_ohlcv_builds_dataframe():
    ex = _FakeExchange()
    df = md.fetch_ohlcv(ex, "SOL/USDT", "5m", limit=50)
    assert list(df.columns) == md.OHLCV_COLUMNS
    assert len(df) == 50
    assert str(df["timestamp"].dtype).startswith("datetime")
    # el timeframe/limit se propagan al exchange
    assert ex.calls == [("SOL/USDT", "5m", 50)]


def test_add_indicators_adds_columns_without_mutating():
    ex = _FakeExchange()
    df = md.fetch_ohlcv(ex, "SOL/USDT", "15m", limit=60)
    out = md.add_indicators(df)
    for col in ("rsi6", "rsi14", "ema9", "ema200", "sma20",
                "atr14", "vol_ma20"):
        assert col in out.columns, col
    # no muta el df original
    assert "rsi14" not in df.columns
    # misma cantidad de filas
    assert len(out) == len(df)


def test_monolith_reexports_same_objects():
    """El monolito reexporta las mismas funciones (no copias)."""
    import fq_bot_v3_2 as b
    assert b.fetch_ohlcv is md.fetch_ohlcv
    assert b.add_indicators is md.add_indicators
