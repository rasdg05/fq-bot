# -*- coding: utf-8 -*-
"""
BCH MOTOR PAPER — guarda de SEGURIDAD del 4o pipeline (mirror de ETH), SIN KL.

Mismo invariante critico: con FQ_MOTOR_PAPER_BCH sin setear (default), la pasada
BCH es un NO-OP INMEDIATO que ni toca el exchange — desplegar el codigo NO cambia
nada hasta prender el env. La FUSION BCH->VIP entrega con par BCH/USDT cuando el
broadcast esta prendido. A DIFERENCIA de BTC/SOL/ETH, BCH va SIN filtro KL
(su edge no vive en irrev-BAJO): difunde aunque FQ_KL_FILTER lo incluyera.
"""
import fq_bot_v3_2 as b


def test_bch_motor_paper_off_by_default():
    """Default OFF: la pasada BCH no hace nada y NO toca el exchange (None)."""
    assert b.BCH_MOTOR_PAPER_ENABLED is False
    assert b._bch_motor_paper_scan(None) is None


def test_bch_motor_paper_guard_when_runtime_none(monkeypatch):
    """Aun 'prendido', si el runtime no se arma, retorna sin tocar el exchange."""
    monkeypatch.setattr(b, "BCH_MOTOR_PAPER_ENABLED", True)
    monkeypatch.setattr(b, "_bch_motor_runtime", lambda: None)
    assert b._bch_motor_paper_scan(None) is None


def test_bch_motor_tf_is_research_tf():
    """El TF del pipeline BCH default = 5m (el TF del research), igual que ETH."""
    assert b.BCH_MOTOR_TF == "5m"


def _fake_bch_df():
    import pandas as pd
    n = 60
    return pd.DataFrame({
        "timestamp": list(range(n)), "open": [100.0] * n, "high": [101.0] * n,
        "low": [99.0] * n, "close": [100.0] * n, "volume": [1.0] * n,
    })


def _wire_fire(monkeypatch, on_bar_sink):
    """Motor BCH prendido + un FIRE forzado, con exchange/indicadores/runtime
    mockeados (cero red). on_bar_sink recibe 1 por cada medicion al ledger."""
    class _RT:
        def on_bar(self, *a, **k):
            on_bar_sink.append(1)
    monkeypatch.setattr(b, "BCH_MOTOR_PAPER_ENABLED", True)
    monkeypatch.setattr(b, "_bch_motor_runtime", lambda: _RT())
    monkeypatch.setattr(b, "fetch_ohlcv", lambda *a, **k: _fake_bch_df())
    monkeypatch.setattr(b, "add_indicators", lambda d: d)
    monkeypatch.setattr(b, "SEGMENT_VETO", None)   # sin veto de sesion por default
    monkeypatch.setattr(b.fusion_engine, "evaluate_signal",
                        lambda *a, **k: (True, object(), {"direction": "long"}))


def test_bch_fusion_broadcasts_with_bch_pair(monkeypatch):
    """FUSION BCH->VIP prendida: un fire BCH llama broadcast_to_subscribers con el
    builder VIP y par BCH/USDT. La medicion (on_bar) tambien corre."""
    measured, sent, captured = [], [], {}
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "BCH_VIP_BROADCAST_ENABLED", True)
    monkeypatch.setattr(b, "VIP_FORMAT_AVAILABLE", True)
    monkeypatch.setattr(b.vip_format, "build_vip_signal",
                        lambda field, report, **kw: captured.update(pair=kw.get("pair")) or "BCH-MSG")
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._bch_motor_paper_scan("EX")
    assert sent == ["BCH-MSG"]              # se entrego al cliente
    assert captured["pair"] == "BCH/USDT"   # como BCH
    assert measured == [1]                  # y se midio igual (ledger intacto)


def test_bch_is_sin_kl(monkeypatch):
    """SIN filtro KL: aunque _kl_pass devolveria False (y BCH estuviera en el
    FQ_KL_FILTER), el broadcast BCH SIGUE saliendo — el scan NO consulta KL."""
    measured, sent, kl_calls = [], [], []
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "BCH_VIP_BROADCAST_ENABLED", True)
    monkeypatch.setattr(b, "VIP_FORMAT_AVAILABLE", True)
    monkeypatch.setattr(b, "KL_FILTER", {"BCH"})   # aunque alguien lo metiera al filtro
    monkeypatch.setattr(b, "_kl_pass", lambda df, pair: kl_calls.append(pair) or False)  # suprimiria
    monkeypatch.setattr(b.vip_format, "build_vip_signal", lambda field, report, **kw: "BCH-MSG")
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._bch_motor_paper_scan("EX")
    assert sent == ["BCH-MSG"]   # difundio igual (sin KL)
    assert kl_calls == []        # y NUNCA consulto _kl_pass


def test_bch_fusion_killswitch_measures_but_silent(monkeypatch):
    """Kill-switch FQ_BCH_VIP_BROADCAST=0: el motor BCH SIGUE midiendo (on_bar)
    pero NO broadcastea. Entrega y ledger son independientes."""
    measured, sent = [], []
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "BCH_VIP_BROADCAST_ENABLED", False)
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._bch_motor_paper_scan("EX")
    assert sent == []        # silencio en clientes
    assert measured == [1]   # pero midio igual


def test_bch_fusion_segment_veto_blocks_broadcast(monkeypatch):
    """Veto de sesion EN VIVO (SEGMENT_VETO): si la killzone de la vela esta
    vetada, el broadcast BCH se CORTA (paridad con SOL/ETH) pero la medicion sigue."""
    measured, sent = [], []
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "BCH_VIP_BROADCAST_ENABLED", True)
    monkeypatch.setattr(b, "VIP_FORMAT_AVAILABLE", True)

    class _Veto:
        active = True
        def reason(self, **k):
            return "killzone=asia_open"   # SIEMPRE vetea

    monkeypatch.setattr(b, "SEGMENT_VETO", _Veto())
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._bch_motor_paper_scan("EX")
    assert sent == []        # NO difundido (vetado en vivo)
    assert measured == [1]   # pero SI medido (ledger intacto)
