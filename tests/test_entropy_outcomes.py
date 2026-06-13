# -*- coding: utf-8 -*-
"""Regresion: check_outcome_against_candles compara fechas tz-safe.

Las velas OHLCV llegan en UTC pero tz-naive (datetime64[ms]); ts_emitted es
tz-aware. Antes esto reventaba con 'Invalid comparison between dtype=
datetime64[ms] and Timestamp' y spameaba ERROR [fq_entropy] reconcile signal.
Cubrimos ambas convenciones de la columna (naive y aware).

+ Endurecimiento del reconcile (jun-2026): la ventana de velas se dimensiona
por la senal abierta mas vieja y, si aun asi no cubre el inicio de una senal
(bot caido mas tiempo que la ventana, cap del exchange), la senal se cierra
como outcome='stale' (no auditable, pnl_r=0) en vez de inventar un outcome
contra precio reciente (sesgo optimista)."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import entropy_cognition as ec


def _signal():
    ts = datetime(2026, 6, 10, 16, 0, 0, tzinfo=timezone.utc)
    return {"ts_emitted": ts.isoformat(), "direction": "long",
            "entry_price": 100.0, "sl": 95.0,
            "tp1": 105, "tp2": 110, "tp3": 115, "tp4": 120}


def _candles(tz_aware):
    idx = pd.to_datetime(["2026-06-10T16:05", "2026-06-10T16:20",
                          "2026-06-10T16:35"], utc=tz_aware)
    ts = idx if tz_aware else idx.astype("datetime64[ms]")
    return pd.DataFrame({"timestamp": ts, "high": [106, 103, 104],
                         "low": [99, 98, 97], "close": [105, 102, 103]})


@pytest.mark.parametrize("tz_aware", [False, True])
def test_outcome_tz_mismatch_no_raise(tz_aware):
    # No debe lanzar y debe resolver TP1 (high 106 >= tp1 105 en la 1a vela post).
    res = ec.check_outcome_against_candles(_signal(), _candles(tz_aware))
    assert res is not None
    assert res["outcome"] == "tp1"


# ==========================================================================
# reconcile_outcomes endurecido: ventana dinamica + outcome 'stale'
# ==========================================================================
def _mk_sig(sig_id, age_minutes, now, tf_id="15m", entry=100.0):
    ts = now - timedelta(minutes=age_minutes)
    return {"id": sig_id, "ts_emitted": ts.isoformat(), "direction": "long",
            "entry_price": entry, "sl": entry - 5.0,
            "tp1": entry + 5.0, "tp2": entry + 10.0,
            "tp3": entry + 15.0, "tp4": entry + 20.0,
            "tf_id": tf_id}


def _mk_candles(n_bars, tf_minutes, now, base=100.0, spread=0.5):
    """n_bars velas planas (no tocan TP/SL de _mk_sig) terminando ~ahora."""
    end = pd.Timestamp(now).tz_localize(None).floor("min")
    idx = pd.date_range(end=end, periods=n_bars, freq="{}min".format(tf_minutes))
    return pd.DataFrame({
        "timestamp": idx.astype("datetime64[ms]"),
        "high": [base + spread] * n_bars,
        "low": [base - spread] * n_bars,
        "close": [base] * n_bars,
    })


def _patch_ledger(monkeypatch, open_sigs):
    """Evita SQLite: get_open_signals/close_signal en memoria."""
    closes = []

    def fake_close(sig_id, outcome, exit_price, pnl_r, minutes_open):
        closes.append({"id": sig_id, "outcome": outcome,
                       "exit_price": exit_price, "pnl_r": pnl_r,
                       "minutes_open": minutes_open})

    monkeypatch.setattr(ec, "get_open_signals", lambda: open_sigs)
    monkeypatch.setattr(ec, "close_signal", fake_close)
    return closes


def test_bars_to_cover_escala_con_la_senal_mas_vieja():
    now = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)
    sigs = [_mk_sig(1, age_minutes=30 * 60, now=now)]      # 30h abierta
    # 30h en 15m = 120 velas + margen 5 = 125
    assert ec._bars_to_cover(sigs, "15m", now=now) == 125
    # sin senales viejas -> piso base
    assert ec._bars_to_cover([_mk_sig(2, 60, now)], "15m", now=now) == \
        ec.RECONCILE_BASE_CANDLES
    # mas alla del cap -> clampa (30h en 5m = 360+5 > 300)
    assert ec._bars_to_cover(sigs, "5m", now=now) == ec.RECONCILE_MAX_CANDLES


def test_reconcile_pide_limit_dinamico(monkeypatch):
    now = datetime.now(timezone.utc)
    sigs = [_mk_sig(1, age_minutes=30 * 60, now=now)]      # 30h abierta
    _patch_ledger(monkeypatch, sigs)
    seen = {}

    def fake_fetch(exchange, symbol, timeframe, limit=None):
        seen["limit"] = limit
        return _mk_candles(limit, 15, now)

    ec.reconcile_outcomes(fake_fetch, None, "SOL/USDT", "15m")
    # ya no 50 fijo: 30h/15m = 120 + margen 5 (+1 por el reloj vivo del now)
    assert 125 <= seen["limit"] <= 126


def test_reconcile_cierra_stale_si_la_ventana_no_cubre(monkeypatch):
    """Senal de 30h con ventana de solo 12h (exchange capeo el fetch): el TP/SL
    pudo tocarse en el hueco -> outcome='stale' con pnl_r=0, NUNCA un win
    inventado contra precio reciente."""
    now = datetime.now(timezone.utc)
    sigs = [_mk_sig(1, age_minutes=30 * 60, now=now, tf_id="15m")]
    closes = _patch_ledger(monkeypatch, sigs)

    # el fake ignora el limit pedido y devuelve solo 48 velas (12h de 15m)
    def fake_fetch(exchange, symbol, timeframe, limit=None):
        return _mk_candles(48, 15, now)

    closed = ec.reconcile_outcomes(fake_fetch, None, "SOL/USDT", "15m")
    assert len(closed) == 1
    assert closed[0]["outcome"] == "stale"
    assert closed[0]["pnl_r"] == 0.0
    assert closes and closes[0]["outcome"] == "stale"


def test_reconcile_stale_solo_en_el_pase_de_su_tf(monkeypatch):
    """El pase 5m NO debe matar como stale una senal de 15m no cubierta: la
    juzga el pase de su propio TF (que cubre mas tiempo-pared por vela)."""
    now = datetime.now(timezone.utc)
    sigs = [_mk_sig(1, age_minutes=30 * 60, now=now, tf_id="15m")]
    closes = _patch_ledger(monkeypatch, sigs)

    def fake_fetch(exchange, symbol, timeframe, limit=None):
        return _mk_candles(min(limit, 300), 5, now)        # ventana 5m: 25h < 30h

    closed = ec.reconcile_outcomes(fake_fetch, None, "SOL/USDT", "5m")
    assert closed == []
    assert closes == []                                    # sigue abierta


def test_reconcile_no_stale_con_fetch_runt(monkeypatch):
    """Hiccup del exchange (fetch raquitico) no debe gatillar cierres stale en
    masa: ese ciclo no decide y la senal sigue abierta."""
    now = datetime.now(timezone.utc)
    sigs = [_mk_sig(1, age_minutes=30 * 60, now=now, tf_id="15m")]
    closes = _patch_ledger(monkeypatch, sigs)

    def fake_fetch(exchange, symbol, timeframe, limit=None):
        return _mk_candles(10, 15, now)                    # 10 velas: runt

    closed = ec.reconcile_outcomes(fake_fetch, None, "SOL/USDT", "15m")
    assert closed == []
    assert closes == []


def test_reconcile_resuelve_normal_si_cubre(monkeypatch):
    """Senal joven cubierta por la ventana: el barrido de barreras funciona
    igual que siempre (aqui toca TP1)."""
    now = datetime.now(timezone.utc)
    sigs = [_mk_sig(1, age_minutes=60, now=now, tf_id="15m")]
    closes = _patch_ledger(monkeypatch, sigs)

    def fake_fetch(exchange, symbol, timeframe, limit=None):
        df = _mk_candles(limit, 15, now)
        df.loc[df.index[-1], "high"] = 106.0               # toca tp1=105
        return df

    closed = ec.reconcile_outcomes(fake_fetch, None, "SOL/USDT", "15m")
    assert len(closed) == 1
    assert closed[0]["outcome"] == "tp1"
    assert closes[0]["outcome"] == "tp1"
