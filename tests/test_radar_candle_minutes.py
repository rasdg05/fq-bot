# -*- coding: utf-8 -*-
"""Auditoria (2026-07-21, RasDG: "audita otros callers de quantum_analysis
por el mismo bug de horizon_hours -- puntualmente radar_check en 5m") tras
el fix de candle_minutes tras el cambio de anchor de /analisis a 5m.

radar_check(tf_id) corre con adaptive=True (SI ejecuta adaptive_horizon())
sobre TFs de FIELD_TIMEFRAMES, cuyo default incluye "5m" -- el canal de
campo afinado, activo en produccion. Sin candle_minutes, ese canal usaba los
pisos/techos del horizonte adaptativo calibrados para velas de 15m (6h-40h)
como si fueran de 5m, simulando solo 1/3 del horizonte real. A diferencia de
/analisis, RADAR no muestra "Horizonte ~Nh" al cliente -- pero SI usa esas
probabilidades (p_sl/EV) para decidir el veredicto y la promocion a VIP, asi
que el bug afectaba la decision, no solo un texto."""
import numpy as np
import pandas as pd

import fq_bot_v3_2 as b


def _synth_df(n=220, seed=1):
    rng = np.random.default_rng(seed)
    close = 100.0 + rng.normal(0.02, 1.0, n).cumsum()
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = close - np.abs(rng.normal(0, 0.5, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = np.abs(rng.normal(1000, 200, n))
    ts = pd.date_range("2026-01-01", periods=n, freq="5min")
    return pd.DataFrame({"timestamp": ts, "open": open_, "high": high,
                          "low": low, "close": close, "volume": vol})


def test_tf_candle_minutes_conocidos():
    assert b._tf_candle_minutes("1m") == 1
    assert b._tf_candle_minutes("3m") == 3
    assert b._tf_candle_minutes("5m") == 5
    assert b._tf_candle_minutes("15m") == 15
    assert b._tf_candle_minutes("1h") == 60


def test_tf_candle_minutes_desconocido_cae_a_15():
    assert b._tf_candle_minutes("2w") == 15
    assert b._tf_candle_minutes(None) == 15


def _wire_radar(monkeypatch):
    monkeypatch.setattr(b, "RADAR_ENABLED", True)
    monkeypatch.setattr(b, "QTE_AVAILABLE", True)
    monkeypatch.setattr(b, "BATTLE_PLANNER_AVAILABLE", True)
    monkeypatch.setattr(b, "VIP_FORMAT_AVAILABLE", True)
    monkeypatch.setattr(b, "fetch_ohlcv", lambda ex, sym, tf, limit=200: _synth_df())
    monkeypatch.setattr(b, "add_indicators", lambda d: d)

    captured = {}

    def fake_quantum_analysis(*a, **k):
        captured.update(k)
        return {"paths": None}   # corta radar_check justo despues de la llamada

    monkeypatch.setattr(b.qt, "quantum_analysis", fake_quantum_analysis)
    return captured


def test_radar_check_5m_pasa_candle_minutes_5(monkeypatch):
    captured = _wire_radar(monkeypatch)
    b.radar_check(None, tf_id="5m")
    assert captured.get("candle_minutes") == 5
    assert captured.get("adaptive") is True


def test_radar_check_15m_pasa_candle_minutes_15(monkeypatch):
    captured = _wire_radar(monkeypatch)
    b.radar_check(None, tf_id="15m")
    assert captured.get("candle_minutes") == 15


def test_radar_check_1m_pasa_candle_minutes_1(monkeypatch):
    captured = _wire_radar(monkeypatch)
    b.radar_check(None, tf_id="1m")
    assert captured.get("candle_minutes") == 1
