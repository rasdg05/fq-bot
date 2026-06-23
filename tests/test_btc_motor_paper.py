# -*- coding: utf-8 -*-
"""
BTC MOTOR PAPER — guarda de SEGURIDAD del pipeline paralelo.

El pipeline BTC (paper-only, 0% real) corre fusion_engine.evaluate_signal sobre
barras BTC y alimenta un motor paper propio. Invariante CRITICO: con
FQ_MOTOR_PAPER_BTC sin setear (default), la pasada es un NO-OP INMEDIATO que ni
toca el exchange — desplegar el codigo NO cambia nada en el bot vivo hasta que se
prende el env. Estos tests sellan esa garantia.
"""
import fq_bot_v3_2 as b


def test_btc_motor_paper_off_by_default():
    """Default OFF: la pasada BTC no hace nada y NO toca el exchange.
    Si tocara el exchange (None), reventaria -> debe retornar None sin error."""
    assert b.BTC_MOTOR_PAPER_ENABLED is False
    assert b._btc_motor_paper_scan(None) is None


def test_btc_motor_paper_guard_when_runtime_none(monkeypatch):
    """Aun 'prendido', si el runtime no se arma (p.ej. sin Volume), retorna sin
    tocar el exchange (exchange=None no se usa) -> nunca rompe el loop."""
    monkeypatch.setattr(b, "BTC_MOTOR_PAPER_ENABLED", True)
    monkeypatch.setattr(b, "_btc_motor_runtime", lambda: None)
    assert b._btc_motor_paper_scan(None) is None


def test_btc_motor_tf_is_research_tf():
    """El TF del pipeline BTC default = 5m (el TF del research/cosecha), no el
    15m del bot vivo. Igualar la poblacion medida es la condicion de validez."""
    assert b.BTC_MOTOR_TF == "5m"


def _fake_btc_df():
    import pandas as pd
    n = 60
    return pd.DataFrame({
        "timestamp": list(range(n)), "open": [100.0] * n, "high": [101.0] * n,
        "low": [99.0] * n, "close": [100.0] * n, "volume": [1.0] * n,
    })


def _wire_fire(monkeypatch, on_bar_sink):
    """Motor BTC prendido + un FIRE forzado, con exchange/indicadores/runtime
    mockeados (cero red). on_bar_sink recibe 1 por cada medicion al ledger."""
    class _RT:
        def on_bar(self, *a, **k):
            on_bar_sink.append(1)
    monkeypatch.setattr(b, "BTC_MOTOR_PAPER_ENABLED", True)
    monkeypatch.setattr(b, "_btc_motor_runtime", lambda: _RT())
    monkeypatch.setattr(b, "fetch_ohlcv", lambda *a, **k: _fake_btc_df())
    monkeypatch.setattr(b, "add_indicators", lambda d: d)
    monkeypatch.setattr(b.fusion_engine, "evaluate_signal",
                        lambda *a, **k: (True, object(), {"direction": "long"}))


def test_btc_fusion_broadcasts_with_btc_pair(monkeypatch):
    """FUSION BTC->VIP prendida: un fire BTC llama broadcast_to_subscribers con el
    builder VIP y par BTC/USDT (no SOL). La medicion (on_bar) tambien corre."""
    measured, sent, captured = [], [], {}
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "BTC_VIP_BROADCAST_ENABLED", True)
    monkeypatch.setattr(b, "VIP_FORMAT_AVAILABLE", True)
    monkeypatch.setattr(b.vip_format, "build_vip_signal",
                        lambda field, report, **kw: captured.update(pair=kw.get("pair")) or "BTC-MSG")
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._btc_motor_paper_scan("EX")
    assert sent == ["BTC-MSG"]              # se entrego al cliente
    assert captured["pair"] == "BTC/USDT"   # como BTC, no SOL
    assert measured == [1]                  # y se midio igual (ledger intacto)


def test_btc_fusion_killswitch_measures_but_silent(monkeypatch):
    """Kill-switch FQ_BTC_VIP_BROADCAST=0: el motor BTC SIGUE midiendo (on_bar)
    pero NO broadcastea. Entrega y ledger son independientes."""
    measured, sent = [], []
    _wire_fire(monkeypatch, measured)
    monkeypatch.setattr(b, "BTC_VIP_BROADCAST_ENABLED", False)
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: sent.append(msg))
    b._btc_motor_paper_scan("EX")
    assert sent == []        # silencio en clientes
    assert measured == [1]   # pero midio igual
