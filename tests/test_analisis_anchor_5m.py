# -*- coding: utf-8 -*-
"""TF anchor de /lectura y /analisis on-demand: 15m -> 5m (2026-07-20, RasDG:
"mas adoc al uso real" -- el motor paper BTC/ETH ya corre en 5m, el TF de la
cosecha/research real). Alcance identico al de test_analisis_sin_niveles.py:
solo el chequeo manual on-demand (build_analisis_context / cmd_lectura), no
la senal automatica VIP/FREE ni el RADAR.

Sella tres cosas:
1) ANALISIS_ANCHOR_TF (y su companero ANALISIS_ANCHOR_CANDLE_MINUTES) es la
   unica fuente de verdad -- cambiarlo mueve el anchor de ambos comandos.
2) build_analisis_context pide velas del anchor nuevo y pasa
   candle_minutes=5 al QTE (sin esto, "Horizonte ~Nh" mentiria 3x, ver
   tests/test_tp_wavelength.py para la garantia del lado quantum_timelines).
3) cmd_lectura captura el precio/df de ancla del TF nuevo, no del viejo."""
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


def test_analisis_anchor_tf_es_5m():
    assert b.ANALISIS_ANCHOR_TF == "5m"
    assert b.ANALISIS_ANCHOR_CANDLE_MINUTES == 5


def test_build_analisis_context_pide_velas_del_anchor(monkeypatch):
    calls = []

    def fake_fetch(exchange, symbol, tf_id, limit=200):
        calls.append(tf_id)
        return _synth_df()

    monkeypatch.setattr(b, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(b, "QTE_AVAILABLE", False)

    ctx = b.build_analisis_context(None, "SOL")
    assert ctx is not None
    assert calls and all(tf == b.ANALISIS_ANCHOR_TF for tf in calls)


def test_build_analisis_context_qte_usa_candle_minutes_del_anchor(monkeypatch):
    """Con QTE disponible, quantum_analysis debe recibir
    candle_minutes=ANALISIS_ANCHOR_CANDLE_MINUTES -- de lo contrario
    horizon_hours asumiria velas de 15m aunque el df sea de 5m."""
    monkeypatch.setattr(b, "fetch_ohlcv", lambda ex, sym, tf, limit=200: _synth_df())
    monkeypatch.setattr(b, "QTE_AVAILABLE", True)

    captured = {}

    def fake_quantum_analysis(*a, **k):
        captured.update(k)
        return {"paths": [1, 2, 3],
                "probabilities": {"p_tp1": 0.5, "p_tp2": 0.3, "p_sl": 0.3,
                                  "expected_R": 1.1},
                "n_paths": 2000, "dominant_regime": "bull_continuation",
                "dominant_regime_pct": 0.5,
                "regimes": {"bull_continuation": 0.5}, "coherence": 0.6,
                "verdict": None, "optimized_levels": None, "vs_baseline": None}

    monkeypatch.setattr(b.qt, "quantum_analysis", fake_quantum_analysis)
    ctx = b.build_analisis_context(None, "SOL")
    assert ctx is not None
    assert captured.get("candle_minutes") == b.ANALISIS_ANCHOR_CANDLE_MINUTES


def test_cmd_lectura_anchor_price_viene_del_tf_nuevo(monkeypatch):
    """El header de /lectura muestra el precio del TF anchor -- debe ser el
    close del df de ANALISIS_ANCHOR_TF (5m), no el de 15m."""
    dfs_by_tf = {}

    def fake_fetch(exchange, symbol, tf_id, limit=200):
        df = _synth_df(seed=abs(hash(tf_id)) % 1000)
        dfs_by_tf[tf_id] = df
        return df

    monkeypatch.setattr(b, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(b.claude_ai, "is_available", lambda: False)

    out = b.cmd_lectura(None, "SOL")
    anchor_close = float(dfs_by_tf[b.ANALISIS_ANCHOR_TF]["close"].iloc[-1])
    assert "${:.2f}".format(anchor_close) in out


def test_cmd_lectura_claude_block_menciona_anchor_5m(monkeypatch):
    """El texto visible al cliente ('TF anchor {ANALISIS_ANCHOR_TF}') debe
    reflejar el anchor real, no quedar hardcodeado a 15m."""
    monkeypatch.setattr(b, "fetch_ohlcv", lambda ex, sym, tf, limit=200: _synth_df())
    monkeypatch.setattr(b.claude_ai, "is_available", lambda: True)
    monkeypatch.setattr(b, "test_macro", lambda ex: {
        "direction": "long", "passed": True, "btc_change": 0.0, "eth_change": 0.0})
    monkeypatch.setattr(b, "test_technical", lambda df, d: {
        "aligned": 5, "total": 7, "passed": True})
    monkeypatch.setattr(b, "test_liquidity", lambda df, d: {
        "rsi6": 50.0, "rsi12": 50.0, "rsi24": 50.0, "passed": True})
    monkeypatch.setattr(b.claude_ai, "tactical_general", lambda snapshot: "lectura ok")

    out = b.cmd_lectura(None, "SOL")
    assert "TF anchor {}".format(b.ANALISIS_ANCHOR_TF) in out
    assert "TF anchor 15m" not in out
