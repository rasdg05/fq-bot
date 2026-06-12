# -*- coding: utf-8 -*-
"""Tests del proxy de CVD y su detector de divergencia (cvd.py).

Sintetico y determinista: construimos velas donde la divergencia existe POR
CONSTRUCCION y verificamos que el detector la ve (y que no inventa una donde
no la hay). Sin red, sin reloj de pared.
"""
import numpy as np
import pandas as pd
import pytest

import cvd


def _candles(closes, volumes=None, spread=0.5):
    """Velas sinteticas: open = close previo; high/low envuelven el cuerpo."""
    closes = np.asarray(closes, dtype="float64")
    opens = np.concatenate([[closes[0]], closes[:-1]])
    highs = np.maximum(opens, closes) + spread
    lows = np.minimum(opens, closes) - spread
    vols = (np.full(len(closes), 100.0) if volumes is None
            else np.asarray(volumes, dtype="float64"))
    return pd.DataFrame({"open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": vols})


def test_delta_proxy_range_signo_y_magnitud():
    # cierra exactamente en el high -> delta = +vol; en el low -> -vol
    df = pd.DataFrame({
        "open":   [10.0, 10.0],
        "high":   [12.0, 12.0],
        "low":    [9.0, 9.0],
        "close":  [12.0, 9.0],
        "volume": [50.0, 80.0],
    })
    d = cvd.delta_proxy(df, mode="range")
    assert d[0] == pytest.approx(50.0)
    assert d[1] == pytest.approx(-80.0)


def test_delta_proxy_rango_cero_no_divide():
    df = pd.DataFrame({"open": [5.0], "high": [5.0], "low": [5.0],
                       "close": [5.0], "volume": [99.0]})
    d = cvd.delta_proxy(df, mode="range")
    assert d[0] == 0.0


def test_delta_proxy_body_es_signo_del_cuerpo():
    df = pd.DataFrame({
        "open":   [10.0, 10.0, 10.0],
        "high":   [11.0, 11.0, 11.0],
        "low":    [9.0, 9.0, 9.0],
        "close":  [10.5, 9.5, 10.0],
        "volume": [10.0, 20.0, 30.0],
    })
    d = cvd.delta_proxy(df, mode="body")
    assert list(d) == [10.0, -20.0, 0.0]


def test_delta_proxy_mode_invalido():
    df = _candles([1.0] * 12)
    with pytest.raises(ValueError):
        cvd.delta_proxy(df, mode="tick")


def test_divergencia_bullish_por_construccion():
    # Precio: baja a 90, rebota, y hace LL a 88 en la 2a mitad.
    closes = [100, 98, 96, 94, 92, 90, 93, 95, 92, 90, 89, 88, 90, 92, 94, 96]
    # Volumen: las velas del primer minimo caen con volumen ALTO (delta muy
    # negativo); las del segundo minimo con volumen casi nulo -> el CVD del
    # segundo minimo queda por ENCIMA del primero = bullish divergence.
    vols = [100, 900, 900, 900, 900, 900, 100, 100, 5, 5, 5, 5, 100, 100, 100, 100]
    out = cvd.detect_cvd_divergence(_candles(closes, vols), lookback=16)
    assert out is not None and out["type"] == "DIVERGENCIA BULLISH"
    assert out["cvd_change"] > 0


def test_divergencia_bearish_por_construccion():
    closes = [100, 102, 104, 106, 108, 110, 107, 105, 108, 110, 111, 112, 110, 108, 106, 104]
    vols = [100, 900, 900, 900, 900, 900, 100, 100, 5, 5, 5, 5, 100, 100, 100, 100]
    out = cvd.detect_cvd_divergence(_candles(closes, vols), lookback=16)
    assert out is not None and out["type"] == "DIVERGENCIA BEARISH"
    assert out["cvd_change"] > 0


def test_sin_divergencia_cuando_volumen_confirma():
    # LL de precio CON volumen vendedor creciente -> CVD tambien hace LL: nada.
    closes = [100, 98, 96, 94, 92, 90, 93, 95, 92, 90, 89, 88, 90, 92, 94, 96]
    vols = [100, 100, 100, 100, 100, 100, 50, 50, 900, 900, 900, 900, 50, 50, 50, 50]
    assert cvd.detect_cvd_divergence(_candles(closes, vols), lookback=16) is None


def test_ventana_corta_devuelve_none():
    assert cvd.detect_cvd_divergence(_candles([1, 2, 3]), lookback=96) is None
    assert cvd.detect_cvd_divergence(None) is None


def test_lookback_recorta_la_ventana():
    # Divergencia SOLO visible en las ultimas 16 velas; con lookback que
    # incluye 60 velas previas planas el detector sigue mirando mitades de la
    # ventana recortada, no debe romperse.
    closes = [100.0] * 60 + [100, 98, 96, 94, 92, 90, 93, 95, 92, 90, 89, 88, 90, 92, 94, 96]
    vols = [10.0] * 60 + [100, 900, 900, 900, 900, 900, 100, 100, 5, 5, 5, 5, 100, 100, 100, 100]
    out16 = cvd.detect_cvd_divergence(_candles(closes, vols), lookback=16)
    assert out16 is not None and out16["type"] == "DIVERGENCIA BULLISH"


def test_alignment():
    bull = {"type": "DIVERGENCIA BULLISH"}
    bear = {"type": "DIVERGENCIA BEARISH"}
    assert cvd.divergence_alignment(bull, +1) == "alineada"
    assert cvd.divergence_alignment(bull, -1) == "contra"
    assert cvd.divergence_alignment(bear, -1) == "alineada"
    assert cvd.divergence_alignment(bear, +1) == "contra"
    assert cvd.divergence_alignment(None, +1) == "sin_div"
