# -*- coding: utf-8 -*-
"""_record_vip_signal (Cerebro Etapa 0, fq_bot_v3_2.py): el puente entre un
fire BTC/ETH que SI llego al VIP y el ledger rico de entropy_cognition.
Defensivo (nunca debe romper el broadcast) y debe pasar el symbol/ccy
correcto para que la fila quede aislada de SOL."""
import types

import fq_bot_v3_2 as b


def _field(killzone="ny_am_kz", confluence_count=3):
    f = types.SimpleNamespace(killzone=killzone, confluence_count=confluence_count)
    f.summary_line = lambda: "campo de prueba"
    return f


def test_record_vip_signal_llama_log_signal_con_symbol_correcto(monkeypatch):
    captured = {}

    def fake_log_signal(signal_data, symbol="SOL"):
        captured["signal_data"] = signal_data
        captured["symbol"] = symbol
        return 42

    monkeypatch.setattr(b.ev, "log_signal", fake_log_signal)

    levels = {"entry": 100.0, "sl": 95.0, "tp1": 105.0, "tp2": 110.0,
              "tp3": 115.0, "tp4": 120.0}
    p_master_data = {"p_master": 2.8, "p_master_raw": 2.5, "kappa_evo": 1.1,
                     "w_effective": 0.9}

    b._record_vip_signal("BTC", "long", levels, p_master_data, "5m", _field())

    assert captured["symbol"] == "BTC"
    sd = captured["signal_data"]
    assert sd["direction"] == "long"
    assert sd["entry"] == 100.0 and sd["sl"] == 95.0
    assert sd["tp1"] == 105.0 and sd["tp4"] == 120.0
    assert sd["p_master_final"] == 2.8
    assert sd["p_master_raw"] == 2.5
    assert sd["kappa_evo"] == 1.1
    assert sd["session"] == "ny_am_kz"          # viene del field.killzone
    assert sd["pspace_count"] == 3              # viene del field.confluence_count


def test_record_vip_signal_defensivo_ante_datos_incompletos(monkeypatch):
    """Nunca debe lanzar -- un broadcast BTC/ETH jamas se cae porque el
    ledger-write fallo."""
    def fake_log_signal(signal_data, symbol="SOL"):
        raise RuntimeError("boom")
    monkeypatch.setattr(b.ev, "log_signal", fake_log_signal)

    # No debe lanzar pese al error interno de log_signal
    b._record_vip_signal("ETH", "short", {}, {}, "5m", _field())


def test_record_vip_signal_sin_field_util_no_rompe(monkeypatch):
    captured = {}
    monkeypatch.setattr(b.ev, "log_signal",
                        lambda signal_data, symbol="SOL": captured.update(sd=signal_data) or 1)

    levels = {"entry": 100.0, "sl": 95.0, "tp1": 105.0, "tp2": 110.0,
              "tp3": 115.0, "tp4": 120.0}
    # field sin killzone/confluence_count/summary_line -- objeto vacio
    b._record_vip_signal("BTC", "long", levels, {"p_master": 2.0}, "5m", object())
    assert captured["sd"]["pspace_count"] == 0
