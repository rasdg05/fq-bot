# -*- coding: utf-8 -*-
"""
Tests del tactical_tracker (v5.4): seguimiento en vivo de las ALERTAS TACTICAS
del VIP, que NO viven en el ledger. Verifica:

  - record_tactical / get_open_tacticals (round trip).
  - check_tactical_progress detecta tp1_hit + be_suggested (mueve SL a BE) y es
    idempotente (no re-emite).
  - cierre por SL tocado y por expiry (deja de escanear).
  - robustez de zona horaria (df naive de fetch_ohlcv vs ts_emitted tz-aware).
  - etiqueta 'Tactica #T<id>' en el mensaje (no 'Senal').
"""
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

# Shim pandas-ta (no se usa aqui pero entropy_cognition lo arrastra indirecto)
try:
    import pandas_ta  # noqa: F401
except ImportError:
    try:
        import pandas_ta_classic as _ta
        sys.modules["pandas_ta"] = _ta
    except ImportError:
        pass

import pandas as pd


# SHORT del screenshot real
ENTRY, SL = 74.44, 75.15
TP1, TP2, TP3 = 73.31, 71.99, 71.15


@pytest.fixture
def tdb(tmp_path, monkeypatch):
    """DB temporal con el esquema completo (incl. tablas tactical_*)."""
    import entropy_cognition as ev
    db = tmp_path / "ledger.db"
    monkeypatch.setattr(ev, "DB_PATH", str(db))
    ev.init_db()
    return ev


def _emitted_iso(minutes_ago=30):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def _make_df(emitted_iso, candles, step_min=5):
    """candles: lista de (high, low, close). Timestamps NAIVE UTC posteriores a
    emitted (como los produce fetch_ohlcv)."""
    em = datetime.fromisoformat(emitted_iso)
    start_ms = int(em.timestamp() * 1000)
    rows = []
    for i, (hi, lo, cl) in enumerate(candles):
        ts_ms = start_ms + (i + 1) * step_min * 60 * 1000
        rows.append({"timestamp": pd.to_datetime(ts_ms, unit="ms"),
                     "high": hi, "low": lo, "close": cl, "open": cl,
                     "volume": 100.0})
    return pd.DataFrame(rows)


def test_record_and_get_open(tdb):
    import tactical_tracker as tt
    em = _emitted_iso()
    tid = tt.record_tactical("5m", "short", ENTRY, SL, TP1, TP2, TP3, ts_emitted=em)
    assert tid is not None
    open_ = tt.get_open_tacticals()
    assert len(open_) == 1
    row = open_[0]
    assert row["direction"] == "short"
    assert abs(row["entry"] - ENTRY) < 1e-9
    assert row["status"] == "open"


def test_tp1_triggers_breakeven_and_is_idempotent(tdb):
    import tactical_tracker as tt
    em = _emitted_iso(minutes_ago=30)
    tt.record_tactical("5m", "short", ENTRY, SL, TP1, TP2, TP3, ts_emitted=em)

    # Dos velas que tocan TP1 (low<=73.31) pero no TP2; sin tocar SL.
    df = _make_df(em, [(74.50, 73.20, 73.40),
                       (73.50, 73.25, 73.45)])
    events = tt.check_tactical_progress(df)
    kinds = {k for (_disp, k, _p) in events}
    assert "tp1_hit" in kinds
    assert "be_suggested" in kinds          # "mueve SL a entry"
    assert "tp2_hit" not in kinds

    # Sigue abierta (no TP3, no SL, no expiry) y NO re-emite.
    assert len(tt.get_open_tacticals()) == 1
    again = tt.check_tactical_progress(df)
    assert again == []


def test_sl_touch_closes_tactical(tdb):
    import tactical_tracker as tt
    em = _emitted_iso(minutes_ago=20)
    tt.record_tactical("5m", "short", ENTRY, SL, TP1, TP2, TP3, ts_emitted=em)
    # SHORT: high>=SL (75.15) invalida; no toca TPs.
    df = _make_df(em, [(75.20, 74.10, 74.80)])
    tt.check_tactical_progress(df)
    assert tt.get_open_tacticals() == []


def test_expiry_closes_tactical(tdb):
    import tactical_tracker as tt
    em = _emitted_iso(minutes_ago=13 * 60)  # 13h > horizonte default 12h
    tt.record_tactical("5m", "short", ENTRY, SL, TP1, TP2, TP3, ts_emitted=em)
    # Velas neutras: ni TP ni SL.
    df = _make_df(em, [(74.60, 74.20, 74.40), (74.55, 74.25, 74.45)])
    tt.check_tactical_progress(df)
    assert tt.get_open_tacticals() == []


def test_post_emission_candles_tz_robust():
    """df naive (fetch_ohlcv) + ts_emitted tz-aware no debe lanzar TypeError."""
    import signal_progress_tracker as spt
    em = _emitted_iso(minutes_ago=10)
    df = _make_df(em, [(74.5, 73.2, 73.4), (73.5, 73.25, 73.45)])
    assert getattr(df["timestamp"].dtype, "tz", None) is None  # naive
    post = spt.post_emission_candles(df, em)  # em trae offset +00:00
    assert post is not None and len(post) == 2


def test_progress_alert_uses_tactica_label():
    import signal_progress_tracker as spt
    msg = spt.build_progress_alert({"id": "T7", "direction": "short"},
                                   "tp1_hit", 73.31, label="Tactica")
    assert "Tactica #T7" in msg
    assert "Senal #" not in msg
    assert "Mueve SL a entry" in msg
