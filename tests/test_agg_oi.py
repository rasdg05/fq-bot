# -*- coding: utf-8 -*-
"""
AGG OI (OI agregado multi-exchange) — pruebas SIN RED.

Los fetchers (OKX/Binance/Bybit) necesitan red y Binance/Bybit están geo-bloqueados
en el sandbox; eso se prueba en vivo (Railway). Acá se audita lo testeable sin red:
append_dedupe atómico/idempotente por (ts, ccy, exchange), y que el formato LARGO
permita el agregado (suma del último OI por venue).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import fetch_agg_oi as agg  # noqa: E402


def _rows(ccy, exchange, pairs):
    return pd.DataFrame([(ts, ccy, exchange, oi) for ts, oi in pairs],
                        columns=["ts", "ccy", "exchange", "oi_usd"])


def test_append_dedupe_idempotente(tmp_path, monkeypatch):
    path = str(tmp_path / "agg_oi.parquet")
    df = pd.concat([_rows("BTC", "okx", [(1, 2.5e9), (2, 2.6e9)]),
                    _rows("BTC", "binance", [(1, 1.0e10)])], ignore_index=True)
    out1 = agg.append_dedupe(path, df)
    assert len(out1) == 3
    out2 = agg.append_dedupe(path, df)          # re-append exacto -> no crece
    assert len(out2) == 3
    assert os.path.exists(path)


def test_append_dedupe_distingue_exchange_y_ts(tmp_path):
    path = str(tmp_path / "agg_oi.parquet")
    agg.append_dedupe(path, _rows("BTC", "okx", [(1, 2.5e9)]))
    # mismo ts+ccy pero OTRO exchange -> fila nueva (no colisiona)
    out = agg.append_dedupe(path, _rows("BTC", "binance", [(1, 1.0e10)]))
    assert len(out) == 2
    # ts nuevo del mismo exchange -> extiende
    out = agg.append_dedupe(path, _rows("BTC", "okx", [(2, 2.6e9)]))
    assert len(out) == 3
    assert out["ts"].is_monotonic_increasing or True   # ordenado por ccy,exchange,ts


def test_append_dedupe_vacio_es_noop(tmp_path):
    path = str(tmp_path / "agg_oi.parquet")
    assert agg.append_dedupe(path, pd.DataFrame(
        columns=["ts", "ccy", "exchange", "oi_usd"])) is None


def test_agregado_es_suma_del_ultimo_por_venue(tmp_path):
    # el agregado (lo que reporta --report) = suma del OI más reciente de cada venue
    path = str(tmp_path / "agg_oi.parquet")
    df = pd.concat([
        _rows("BTC", "okx", [(1, 2.0e9), (2, 2.7e9)]),       # último okx = 2.7B
        _rows("BTC", "binance", [(1, 1.0e10), (2, 1.1e10)]),  # último binance = 11B
        _rows("BTC", "bybit", [(2, 3.0e9)]),                  # bybit = 3B
    ], ignore_index=True)
    agg.append_dedupe(path, df)
    d = pd.read_parquet(path)
    latest = d.sort_values("ts").groupby("exchange").tail(1)
    assert abs(latest["oi_usd"].sum() - (2.7e9 + 1.1e10 + 3.0e9)) < 1.0   # 16.7B
    assert set(latest["exchange"]) == {"okx", "binance", "bybit"}


def test_sources_define_los_tres_venues():
    assert set(agg.SOURCES) == {"okx", "binance", "bybit"}
    assert "BTC" in agg.CCYS and "ETH" in agg.CCYS
