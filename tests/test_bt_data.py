# -*- coding: utf-8 -*-
"""
bt_data (etapa 1 del harness de research): descarga paginada de OHLCV
historico, deduplicacion, verificacion de continuidad y persistencia Parquet.
Se testea con un exchange falso (sin red), igual que test_market_data.
"""
import pandas as pd
import pytest

import bt_data as bt


class _FakeRangeExchange:
    """Exchange estilo ccxt que sirve un histgrico sintetico continuo.

    Mantiene `total` velas de 1m desde base_ms. fetch_ohlcv(since, limit)
    devuelve la pagina que arranca en/ tras `since`, como hace ccxt.
    """
    def __init__(self, base_ms=1_700_000_000_000, total=5000, tf_ms=60_000,
                 drop=None):
        self.base_ms = base_ms
        self.total = total
        self.tf_ms = tf_ms
        self.drop = set(drop or ())   # indices de vela a omitir (simula gaps)
        self.calls = []
        self._all = [
            [base_ms + i * tf_ms, 10.0 + i, 11.0 + i, 9.0 + i, 10.5 + i, 100.0 + i]
            for i in range(total)
            if i not in self.drop
        ]

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        self.calls.append((symbol, timeframe, since, limit))
        page = [c for c in self._all if c[0] >= since][:limit]
        return page


def test_fetch_range_paginates_and_dedupes():
    ex = _FakeRangeExchange(total=5000)
    until = ex.base_ms + 5000 * ex.tf_ms
    df = bt.fetch_ohlcv_range(ex, "SOL/USDT", "1m", ex.base_ms, until,
                              page_limit=1000)
    assert list(df.columns) == bt.OHLCV_COLUMNS
    assert len(df) == 5000               # cubrio todo el rango
    assert ex.calls and len(ex.calls) >= 5  # pagino (5000/1000)
    assert df["timestamp"].is_monotonic_increasing
    assert df["timestamp"].duplicated().sum() == 0
    assert str(df["timestamp"].dtype).startswith("datetime")


def test_fetch_range_respects_until_bound():
    ex = _FakeRangeExchange(total=5000)
    until = ex.base_ms + 100 * ex.tf_ms   # solo 100 velas
    df = bt.fetch_ohlcv_range(ex, "SOL/USDT", "1m", ex.base_ms, until)
    assert len(df) == 100
    # ninguna vela alcanza o supera el limite superior
    assert (df["timestamp"].astype("int64") // 1_000_000 < until).all()


def test_fetch_range_empty_when_until_before_since():
    ex = _FakeRangeExchange()
    df = bt.fetch_ohlcv_range(ex, "SOL/USDT", "1m", 1000, 1000)
    assert len(df) == 0
    assert list(df.columns) == bt.OHLCV_COLUMNS


def test_check_continuity_clean_series():
    ex = _FakeRangeExchange(total=500)
    until = ex.base_ms + 500 * ex.tf_ms
    df = bt.fetch_ohlcv_range(ex, "SOL/USDT", "1m", ex.base_ms, until)
    rep = bt.check_continuity(df, "1m")
    assert rep["n"] == 500
    assert rep["duplicates"] == 0
    assert rep["gaps"] == []
    assert rep["missing_bars"] == 0
    assert rep["completeness"] == 1.0


def test_check_continuity_detects_gap():
    # Omitimos 5 velas en medio -> un gap de 5 barras faltantes.
    ex = _FakeRangeExchange(total=500, drop=range(100, 105))
    until = ex.base_ms + 500 * ex.tf_ms
    df = bt.fetch_ohlcv_range(ex, "SOL/USDT", "1m", ex.base_ms, until)
    rep = bt.check_continuity(df, "1m")
    assert rep["n"] == 495
    assert rep["missing_bars"] == 5
    assert len(rep["gaps"]) == 1
    ts_before, ts_after, missing = rep["gaps"][0]
    assert missing == 5
    assert ts_before < ts_after
    assert rep["completeness"] < 1.0


def test_timeframe_ms_known_and_unknown():
    assert bt.timeframe_ms("15m") == 15 * 60_000
    assert bt.timeframe_ms("1h") == 3_600_000
    with pytest.raises(ValueError):
        bt.timeframe_ms("7m")


def test_dataset_path_sanitizes_symbol():
    p = bt.dataset_path("data", "binance", "SOL/USDT", "15m")
    assert p == "data/binance/SOL-USDT_15m.parquet"
    p2 = bt.dataset_path("data", "bybit", "SOL/USDT:USDT", "1m")
    assert "SOL-USDT_USDT_1m.parquet" in p2


def test_build_dataset_persists_parquet_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    ex = _FakeRangeExchange(total=300)
    until = ex.base_ms + 300 * ex.tf_ms
    out = tmp_path / "binance" / "SOL-USDT_1m.parquet"
    df, rep = bt.build_dataset(
        ex, "SOL/USDT", "1m", ex.base_ms, until, out_path=str(out),
    )
    assert rep["saved_to"] == str(out)
    assert out.exists()
    reloaded = bt.load_parquet(str(out))
    assert len(reloaded) == len(df) == 300
    assert list(reloaded.columns) == bt.OHLCV_COLUMNS


def test_build_dataset_default_path_from_exchange_name(tmp_path):
    pytest.importorskip("pyarrow")
    ex = _FakeRangeExchange(total=120)
    until = ex.base_ms + 120 * ex.tf_ms
    df, rep = bt.build_dataset(
        ex, "SOL/USDT", "1m", ex.base_ms, until,
        exchange_name="bybit", data_dir=str(tmp_path),
    )
    assert rep["saved_to"].endswith("bybit/SOL-USDT_1m.parquet")
    assert rep["completeness"] == 1.0
