# -*- coding: utf-8 -*-
"""
ETH MOTOR PAPER — guarda de SEGURIDAD del 3er pipeline (mirror de BTC).

Mismo invariante critico: con FQ_MOTOR_PAPER_ETH sin setear (default), la pasada
ETH es un NO-OP INMEDIATO que ni toca el exchange — desplegar el codigo NO cambia
nada hasta prender el env. Y la FUSION ETH->VIP entrega con par ETH/USDT (no SOL)
cuando el broadcast esta prendido, midiendo en paralelo.
"""
import fq_bot_v3_2 as b


def test_eth_motor_paper_off_by_default():
    """Default OFF: la pasada ETH no hace nada y NO toca el exchange (None)."""
    assert b.ETH_MOTOR_PAPER_ENABLED is False
    assert b._eth_motor_paper_scan(None) is None


def test_eth_motor_paper_guard_when_runtime_none(monkeypatch):
    """Aun 'prendido', si el runtime no se arma, retorna sin tocar el exchange."""
    monkeypatch.setattr(b, "ETH_MOTOR_PAPER_ENABLED", True)
    monkeypatch.setattr(b, "_eth_motor_runtime", lambda: None)
    assert b._eth_motor_paper_scan(None) is None


def test_eth_motor_tf_is_research_tf():
    """El TF del pipeline ETH default = 5m (el TF del research), igual que BTC."""
    assert b.ETH_MOTOR_TF == "5m"


def _fake_eth_df():
    import pandas as pd
    n = 60
    return pd.DataFrame({
        "timestamp": list(range(n)), "open": [100.0] * n, "high": [101.0] * n,
        "low": [99.0] * n, "close": [100.0] * n, "volume": [1.0] * n,
    })


def _wire_fire(monkeypatch, on_bar_sink):
    """Motor ETH prendido + un FIRE forzado, con exchange/indicadores/runtime
    mockeados (cero red). on_bar_sink recibe 1 por cada medicion al ledger."""
    class _RT:
        def on_bar(self, *a, **k):
            on_bar_sink.append(1)
    monkeypatch.setattr(b, "ETH_MOTOR_PAPER_ENABLED", True)
    monkeypatch.setattr(b, "_eth_motor_runtime", lambda: _RT())
    monkeypatch.setattr(b, "fetch_ohlcv", lambda *a, **k: _fake_eth_df())
    monkeypatch.setattr(b, "add_indicators", lambda d: d)
    monkeypatch.setattr(b, "SEGMENT_VETO", None)   # sin veto de sesion por default
    monkeypatch.setattr(b.fusion_engine, "evaluate_signal",
                        lambda *a, **k: (True, object(), {"direction": "long"}))


def test_eth_fusion_broadcasts_with_eth_pair(monkeypatch):
    """FUSION ETH->VIP prendida: un fire ETH llama broadcast_to_subscribers con el
    builder VIP y par ETH/USDT (no SOL). La medicion (on_bar) tambien corre."""
    measured, sent, captured = [], [], {}
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "ETH_VIP_BROADCAST_ENABLED", True)
    monkeypatch.setattr(b, "VIP_FORMAT_AVAILABLE", True)
    monkeypatch.setattr(b.vip_format, "build_vip_signal",
                        lambda field, report, **kw: captured.update(pair=kw.get("pair")) or "ETH-MSG")
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._eth_motor_paper_scan("EX")
    assert sent == ["ETH-MSG"]              # se entrego al cliente
    assert captured["pair"] == "ETH/USDT"   # como ETH, no SOL
    assert measured == [1]                  # y se midio igual (ledger intacto)


def test_eth_fusion_killswitch_measures_but_silent(monkeypatch):
    """Kill-switch FQ_ETH_VIP_BROADCAST=0: el motor ETH SIGUE midiendo (on_bar)
    pero NO broadcastea. Entrega y ledger son independientes."""
    measured, sent = [], []
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "ETH_VIP_BROADCAST_ENABLED", False)
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._eth_motor_paper_scan("EX")
    assert sent == []        # silencio en clientes
    assert measured == [1]   # pero midio igual


def test_eth_fusion_segment_veto_blocks_broadcast(monkeypatch):
    """Veto de sesion EN VIVO (SEGMENT_VETO): si la killzone de la vela esta
    vetada, el broadcast ETH se CORTA (paridad con SOL) pero la medicion sigue."""
    measured, sent = [], []
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "ETH_VIP_BROADCAST_ENABLED", True)
    monkeypatch.setattr(b, "VIP_FORMAT_AVAILABLE", True)

    class _Veto:
        active = True
        def reason(self, **k):
            return "killzone=asia_open"   # SIEMPRE vetea

    monkeypatch.setattr(b, "SEGMENT_VETO", _Veto())
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._eth_motor_paper_scan("EX")
    assert sent == []        # NO difundido (vetado en vivo)
    assert measured == [1]   # pero SI medido (ledger intacto)
