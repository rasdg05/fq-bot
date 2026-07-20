# -*- coding: utf-8 -*-
"""Eliminacion de niveles crudos en /lectura y /analisis on-demand
(2026-07-20, RasDG: "los niveles ya me parecen poco efectivos ... es mejor
esperar el precio con el analisis en lugar de forzar entrada con niveles
crudos"). Scope explicito confirmado por RasDG: "Solo /lectura y /analisis
(on-demand)" -- la senal automatica disparada al VIP/FREE (build_vip_signal,
con sus 4 TP) y el RADAR (build_battle_plan/build_battle_block) NO se tocan,
son otras superficies.

Estos tests sellan que el camino on-demand (build_analisis_context ->
cmd_analisis_vip / claude_followup_analisis_vip -> vip_format /
claude_integration) ya no calcula ni expone Entry/SL/TP ni el battle plan."""
import numpy as np
import pandas as pd

import fq_bot_v3_2 as b
import vip_format as vf
import claude_integration as ci


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


def test_build_analisis_context_nunca_arma_battle_plan(monkeypatch):
    """Aun con QTE disponible y paths simulados, build_analisis_context ya no
    debe invocar battle_planner.build_battle_plan -- ese plan de $ es del
    RADAR, no de este on-demand."""
    monkeypatch.setattr(b, "fetch_ohlcv", lambda ex, sym, tf, limit=200: _synth_df())
    monkeypatch.setattr(b, "QTE_AVAILABLE", True)
    monkeypatch.setattr(b, "BATTLE_PLANNER_AVAILABLE", True)

    fake_qa = {"paths": [1, 2, 3], "probabilities": {"p_tp1": 0.5, "p_tp2": 0.3,
               "p_sl": 0.3, "expected_R": 1.1}, "n_paths": 2000,
               "dominant_regime": "bull_continuation", "dominant_regime_pct": 0.5,
               "regimes": {"bull_continuation": 0.5}, "coherence": 0.6,
               "verdict": None, "optimized_levels": None, "vs_baseline": None}
    monkeypatch.setattr(b.qt, "quantum_analysis", lambda *a, **k: fake_qa)

    calls = []
    monkeypatch.setattr(b.battle_planner, "build_battle_plan",
                        lambda *a, **k: calls.append(1) or {"verdict": "EJECUTAR_AHORA"})

    ctx = b.build_analisis_context(None, "SOL")
    assert ctx is not None
    assert ctx["plan"] is None
    assert calls == []          # build_battle_plan jamas se llamo


def test_claude_followup_snapshot_sin_niveles_ni_battle(monkeypatch):
    """El snapshot que ve Claude en /analisis on-demand no debe traer
    entry/sl/tp*/qte_opt_*/qte_vs_*/battle -- solo sesgo + probabilidades
    cualitativas."""
    monkeypatch.setattr(b, "fetch_ohlcv", lambda ex, sym, tf, limit=200: _synth_df())
    monkeypatch.setattr(b, "QTE_AVAILABLE", False)  # ctx sin QTE -> el caso mas simple
    ctx = b.build_analisis_context(None, "SOL")
    assert ctx is not None and ctx["plan"] is None

    captured = {}

    class _FakeClaude:
        def is_available(self):
            return True

        def tactical_analisis_vip(self, snapshot):
            captured.update(snapshot)
            return "lectura ok"

    monkeypatch.setattr(b, "claude_ai", _FakeClaude())
    out = b.claude_followup_analisis_vip(None, ctx=ctx)
    assert out is not None

    forbidden = ("entry", "sl", "sl_anchor", "tp1", "tp2", "tp3",
                 "rr_tp1", "rr_tp2", "rr_tp3", "battle",
                 "qte_opt_sl", "qte_opt_tp1", "qte_opt_tp2", "qte_opt_tp3",
                 "qte_opt_ev", "qte_opt_p_sl",
                 "qte_vs_delta_R", "qte_vs_baseline_p_sl", "qte_vs_baseline_ev")
    for key in forbidden:
        assert key not in captured, "snapshot no debe traer '{}'".format(key)


def test_build_vip_analisis_sin_niveles_crudos():
    """La salida de /analisis VIP no debe traer etiquetas Entry/Stop/TP ni
    figuras de $ distintas al precio actual."""
    levels = {"entry": 145.0, "sl": 142.0, "risk": 3.0,
              "tp1": 149.0, "rr_tp1": 1.33, "tp2": 153.0, "rr_tp2": 2.67,
              "tp3": 158.0, "rr_tp3": 4.33, "sl_anchor": "OB_bullish"}
    out = vf.build_vip_analisis("long", levels, "alcista", 3.0, {"close": 145.0})
    assert "Entry" not in out
    assert "Stop" not in out
    assert "TP1" not in out and "TP2" not in out and "TP3" not in out
    assert "$142" not in out and "$149" not in out and "$153" not in out


def test_build_analisis_vip_prompt_sin_niveles_crudos():
    """El prompt que recibe Claude ya no lista Entry/Stop/TP1-3 ni battle
    plan; y las reglas ahora piden NO citar precios exactos (antes pedian lo
    contrario)."""
    snapshot = {
        "price": 145.0, "pair": "SOL/USDT", "direction": "long",
        "bias": "alcista", "pspace_count": 3, "rsi14": 55.0,
    }
    out = ci.build_analisis_vip_prompt(snapshot)
    assert "Entry:" not in out
    assert "Stop:" not in out
    assert "TP1:" not in out and "TP2:" not in out and "TP3:" not in out
    assert "VEREDICTO DEL MOTOR" not in out   # battle_block ya no existe
    assert "QTE OPTIMIZER" not in out          # qte_opt_block ya no existe
    assert "NO cites precios exactos" in out
    assert "precios exactos: entry, SL" not in out   # regla vieja invertida
