# -*- coding: utf-8 -*-
"""Cerebro Etapa 0: cableado de _record_vip_signal + reconcile_outcomes
dentro de _btc_motor_paper_scan / _eth_motor_paper_scan. Complementa
test_btc_motor_paper.py / test_eth_motor_paper.py (que cubren el broadcast)
con el aspecto nuevo: ¿la senal que SI llego al VIP queda grabada en el
ledger rico, y se reconcilia contra SU PROPIO symbol?"""
import types

import pandas as pd

import fq_bot_v3_2 as b


def _fake_df():
    n = 60
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="5min"),
        "open": [100.0] * n, "high": [101.0] * n,
        "low": [99.0] * n, "close": [100.0] * n, "volume": [1.0] * n,
    })


def _field():
    f = types.SimpleNamespace(killzone="ny_am_kz", confluence_count=3)
    f.summary_line = lambda: "campo"
    return f


def _report():
    return {"direction": "long",
            "levels": {"entry": 100.0, "sl": 95.0, "tp1": 105.0,
                      "tp2": 110.0, "tp3": 115.0, "tp4": 120.0},
            "p_master_data": {"p_master": 2.6, "p_master_raw": 2.5,
                              "kappa_evo": 1.0, "w_effective": 0.8}}


def _wire_common(monkeypatch, prefix):
    """prefix: 'btc' o 'eth'. Cablea fire forzado + mocks minimos, sin
    tocar red. Devuelve sinks para inspeccionar llamadas."""
    class _RT:
        def on_bar(self, *a, **k):
            pass
    monkeypatch.setattr(b, "{}_MOTOR_PAPER_ENABLED".format(prefix.upper()), True)
    monkeypatch.setattr(b, "_{}_motor_runtime".format(prefix), lambda: _RT())
    monkeypatch.setattr(b, "fetch_ohlcv", lambda *a, **k: _fake_df())
    monkeypatch.setattr(b, "add_indicators", lambda d: d)
    monkeypatch.setattr(b, "SEGMENT_VETO", None)
    monkeypatch.setattr(b, "{}_VIP_BROADCAST_ENABLED".format(prefix.upper()), True)
    monkeypatch.setattr(b, "VIP_FORMAT_AVAILABLE", True)
    monkeypatch.setattr(b.vip_format, "build_vip_signal", lambda field, report, **kw: "MSG")
    monkeypatch.setattr(b, "broadcast_to_subscribers", lambda msg, *a, **k: (1, 0))
    monkeypatch.setattr(b.fusion_engine, "evaluate_signal",
                        lambda *a, **k: (True, _field(), _report()))

    reconcile_calls = []
    monkeypatch.setattr(b.ev, "reconcile_outcomes",
                        lambda *a, **k: reconcile_calls.append((a, k)) or [])
    record_calls = []
    monkeypatch.setattr(b, "_record_vip_signal",
                        lambda *a, **k: record_calls.append((a, k)))
    return reconcile_calls, record_calls


def test_btc_scan_graba_y_reconcilia_su_propio_symbol(monkeypatch):
    reconcile_calls, record_calls = _wire_common(monkeypatch, "btc")
    b._btc_motor_paper_scan("EX")

    assert len(record_calls) == 1
    args, _ = record_calls[0]
    assert args[0] == "BTC"                       # ccy correcto, no SOL

    assert len(reconcile_calls) == 1
    args, kwargs = reconcile_calls[0]
    # reconcile_outcomes(fetch_ohlcv, exchange, SYMBOL_BTC, tf_id, ccy="BTC")
    assert args[2] == b.SYMBOL_BTC
    assert kwargs.get("ccy") == "BTC"


def test_eth_scan_graba_y_reconcilia_su_propio_symbol(monkeypatch):
    reconcile_calls, record_calls = _wire_common(monkeypatch, "eth")
    b._eth_motor_paper_scan("EX")

    assert len(record_calls) == 1
    args, _ = record_calls[0]
    assert args[0] == "ETH"

    assert len(reconcile_calls) == 1
    args, kwargs = reconcile_calls[0]
    assert args[2] == b.SYMBOL_ETH
    assert kwargs.get("ccy") == "ETH"


def test_btc_scan_no_graba_si_broadcast_esta_apagado(monkeypatch):
    """Kill-switch FQ_BTC_VIP_BROADCAST=0: no se difunde -> tampoco se graba
    (solo se registra lo que el VIP realmente recibio)."""
    reconcile_calls, record_calls = _wire_common(monkeypatch, "btc")
    monkeypatch.setattr(b, "BTC_VIP_BROADCAST_ENABLED", False)
    b._btc_motor_paper_scan("EX")

    assert record_calls == []
    # pero el reconcile SIGUE corriendo (cierra senales previas igual)
    assert len(reconcile_calls) == 1


def test_btc_scan_no_graba_si_kl_suprime(monkeypatch):
    reconcile_calls, record_calls = _wire_common(monkeypatch, "btc")
    monkeypatch.setattr(b, "_kl_pass", lambda df, pair: False)
    b._btc_motor_paper_scan("EX")

    assert record_calls == []
    assert len(reconcile_calls) == 1


def test_btc_scan_reconcile_error_no_rompe_el_scan(monkeypatch):
    """Defensivo: si reconcile_outcomes explota, el scan sigue vivo."""
    _wire_common(monkeypatch, "btc")

    def _boom(*a, **k):
        raise RuntimeError("db lock")
    monkeypatch.setattr(b.ev, "reconcile_outcomes", _boom)
    b._btc_motor_paper_scan("EX")   # no debe lanzar
