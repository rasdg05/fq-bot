# -*- coding: utf-8 -*-
"""
MOTOR PAPER GENÉRICO (LINK / BNB, tier Calidad-KL) — guarda de SEGURIDAD.

Mismo invariante que BTC/ETH/BCH: con FQ_MOTOR_PAPER_LINK / _BNB sin setear
(default), la pasada es NO-OP INMEDIATO — desplegar NO cambia nada hasta prender
el env. A DIFERENCIA de BCH (sin KL), LINK/BNB van con kl_gated=True -> el
broadcast SOLO sale en régimen KL-bajo (tier Calidad, honra FQ_KL_FILTER).
"""
import fq_bot_v3_2 as b


def test_link_bnb_off_by_default():
    """Default OFF en ambos flags."""
    assert b.LINK_MOTOR_PAPER_ENABLED is False
    assert b.BNB_MOTOR_PAPER_ENABLED is False


def test_xsym_scan_noop_when_disabled():
    """enabled=False -> no hace nada y NO toca el exchange."""
    assert b._xsym_motor_paper_scan(
        None, enabled=False, symbol_inst=b.SYMBOL_LINK, pair="LINK/USDT",
        tf_id="5m", ledger_path="/tmp/x.jsonl", broadcast_enabled=True, kl_gated=True) is None


def test_xsym_scan_guard_when_runtime_none(monkeypatch):
    """enabled pero runtime None -> retorna sin tocar el exchange."""
    monkeypatch.setattr(b, "_xsym_motor_runtime", lambda pair, lp: None)
    assert b._xsym_motor_paper_scan(
        None, enabled=True, symbol_inst=b.SYMBOL_BNB, pair="BNB/USDT",
        tf_id="5m", ledger_path="/tmp/x.jsonl", broadcast_enabled=True, kl_gated=True) is None


def _fake_df():
    import pandas as pd
    n = 60
    return pd.DataFrame({
        "timestamp": list(range(n)), "open": [100.0] * n, "high": [101.0] * n,
        "low": [99.0] * n, "close": [100.0] * n, "volume": [1.0] * n,
    })


def _wire_fire(monkeypatch, on_bar_sink):
    """Runtime + un FIRE forzado, todo mockeado (cero red)."""
    class _RT:
        def on_bar(self, *a, **k):
            on_bar_sink.append(1)
    monkeypatch.setattr(b, "_xsym_motor_runtime", lambda pair, lp: _RT())
    monkeypatch.setattr(b, "fetch_ohlcv", lambda *a, **k: _fake_df())
    monkeypatch.setattr(b, "add_indicators", lambda d: d)
    monkeypatch.setattr(b, "SEGMENT_VETO", None)
    monkeypatch.setattr(b.fusion_engine, "evaluate_signal",
                        lambda *a, **k: (True, object(), {"direction": "long"}))
    monkeypatch.setattr(b, "VIP_FORMAT_AVAILABLE", True)
    monkeypatch.setattr(b.vip_format, "build_vip_signal",
                        lambda field, report, **kw: ("MSG:%s" % kw.get("pair")))


def _scan(pair, sym, broadcast=True, kl_gated=True):
    return dict(enabled=True, symbol_inst=sym, pair=pair, tf_id="5m",
                ledger_path="/tmp/x.jsonl", broadcast_enabled=broadcast, kl_gated=kl_gated)


def test_link_broadcasts_with_link_pair_when_kl_pass(monkeypatch):
    """Calidad: con _kl_pass=True (régimen KL-bajo) difunde con par LINK/USDT y mide."""
    measured, sent = [], []
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "_kl_pass", lambda df, pair: True)
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._xsym_motor_paper_scan(b, **_scan("LINK/USDT", b.SYMBOL_LINK))
    assert sent == ["MSG:LINK/USDT"]   # difundió con su par
    assert measured == [1]             # y midió (ledger intacto)


def test_calidad_kl_gate_suppresses_broadcast(monkeypatch):
    """kl_gated=True + _kl_pass=False (régimen trending) -> SUPRIME el broadcast
    pero SIGUE midiendo (tier Calidad real)."""
    measured, sent, kl_calls = [], [], []
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "_kl_pass", lambda df, pair: kl_calls.append(pair) or False)
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._xsym_motor_paper_scan(b, **_scan("BNB/USDT", b.SYMBOL_BNB))
    assert sent == []              # NO difundió (régimen no-KL-bajo)
    assert kl_calls == ["BNB/USDT"]  # SÍ consultó el filtro (es calidad)
    assert measured == [1]         # pero midió igual


def test_xsym_killswitch_measures_but_silent(monkeypatch):
    """broadcast_enabled=False -> mide (on_bar) pero NO broadcastea."""
    measured, sent = [], []
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "_kl_pass", lambda df, pair: True)
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._xsym_motor_paper_scan(b, **_scan("LINK/USDT", b.SYMBOL_LINK, broadcast=False))
    assert sent == []
    assert measured == [1]


def test_xsym_segment_veto_blocks_broadcast(monkeypatch):
    """Veto de sesión en vivo -> corta el broadcast pero mide."""
    measured, sent = [], []
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "_kl_pass", lambda df, pair: True)

    class _Veto:
        active = True
        def reason(self, **k):
            return "killzone=asia_open"

    monkeypatch.setattr(b, "SEGMENT_VETO", _Veto())
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._xsym_motor_paper_scan(b, **_scan("BNB/USDT", b.SYMBOL_BNB))
    assert sent == []
    assert measured == [1]
