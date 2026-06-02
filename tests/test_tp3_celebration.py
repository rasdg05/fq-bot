# -*- coding: utf-8 -*-
"""
TP3 celebration (animo para los usuarios):
  - Formatters VIP (signal_progress_tracker) y publico (public_format).
  - Pipeline del bot publico: lee 'tp3_hit' de signal_progress (ledger VIP RO),
    celebra una sola vez (idempotente via announced_tp3).
"""
import importlib
import sqlite3
from datetime import datetime, timezone, timedelta

import pytest


# ---------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------
def test_vip_tp3_celebration_message():
    import signal_progress_tracker as spt
    sig = {"id": 42, "direction": "long"}
    msg = spt.build_tp3_celebration(sig, 152.30)
    assert "TP3 ALCANZADO" in msg
    assert "#42" in msg
    assert "+3.00R" in msg
    assert "\U0001F973" in msg  # 🥳


def test_vip_tp3_dispatch_via_build_progress_alert():
    """El dispatcher reconoce el evento celebratorio explicito."""
    import signal_progress_tracker as spt
    sig = {"id": 7, "direction": "short"}
    msg = spt.build_progress_alert(sig, "tp3_celebration", 78.10)
    assert "TP3 ALCANZADO" in msg
    assert "#7" in msg


def test_public_tp3_celebration_message():
    import public_format as pf
    msg = pf.build_tp3_celebration(
        {"direction": "long", "ts_emitted": "2026-06-01T13:00:00Z",
         "hit_price": 152.30})
    assert "TP3 ALCANZADO" in msg
    assert "+3R" in msg
    assert "/unirme" in msg          # CTA de conversion presente
    assert "LONG" in msg


# ---------------------------------------------------------------
# Pipeline del bot publico (ledger VIP read-only -> announced_tp3)
# ---------------------------------------------------------------
def _seed_vip_ledger(path):
    """Ledger VIP minimo con una senal y su evento tp3_hit reciente."""
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT, entry_price REAL, tp3 REAL,
            ts_emitted TEXT, outcome TEXT, pnl_r REAL
        )
    """)
    conn.execute("""
        CREATE TABLE signal_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            ts_event TEXT NOT NULL,
            price REAL,
            UNIQUE(signal_id, event)
        )
    """)
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO signals (id, direction, entry_price, tp3, ts_emitted) "
        "VALUES (1, 'long', 145.0, 152.3, ?)",
        ((now - timedelta(hours=2)).isoformat(),))
    # tp3 reciente (dentro de la ventana)
    conn.execute(
        "INSERT INTO signal_progress (signal_id, event, ts_event, price) "
        "VALUES (1, 'tp3_hit', ?, 152.3)",
        ((now - timedelta(minutes=20)).isoformat(),))
    # un tp1 que NO debe celebrarse como tp3
    conn.execute(
        "INSERT INTO signal_progress (signal_id, event, ts_event, price) "
        "VALUES (1, 'tp1_hit', ?, 147.0)",
        ((now - timedelta(minutes=40)).isoformat(),))
    conn.commit()
    conn.close()


@pytest.fixture
def poa_with_ledger(tmp_path, monkeypatch):
    vip_db = tmp_path / "ledger.db"
    pub_db = tmp_path / "public.db"
    _seed_vip_ledger(vip_db)
    monkeypatch.setenv("FQ_VIP_LEDGER_PATH", str(vip_db))
    monkeypatch.setenv("FQ_PUBLIC_DB_PATH", str(pub_db))
    import public_outcome_announcer as poa
    importlib.reload(poa)
    poa.init_public_db()
    return poa


def test_public_detects_new_tp3(poa_with_ledger):
    poa = poa_with_ledger
    rows = poa.get_new_tp3_to_announce()
    assert len(rows) == 1
    assert rows[0]["id"] == 1
    assert rows[0]["direction"] == "long"
    assert rows[0]["hit_price"] == pytest.approx(152.3)


def test_public_tp3_idempotent(poa_with_ledger):
    poa = poa_with_ledger
    first = poa.get_new_tp3_to_announce()
    assert len(first) == 1
    poa.mark_tp3_announced(first[0]["id"], direction="long", hit_price=152.3)
    # Ya celebrado -> no reaparece
    assert poa.get_new_tp3_to_announce() == []


def test_public_tp3_respects_lookback(tmp_path, monkeypatch):
    vip_db = tmp_path / "ledger.db"
    pub_db = tmp_path / "public.db"
    conn = sqlite3.connect(str(vip_db))
    conn.execute("CREATE TABLE signals (id INTEGER PRIMARY KEY, direction TEXT, "
                 "entry_price REAL, tp3 REAL, ts_emitted TEXT, outcome TEXT, pnl_r REAL)")
    conn.execute("CREATE TABLE signal_progress (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "signal_id INTEGER, event TEXT, ts_event TEXT, price REAL, "
                 "UNIQUE(signal_id, event))")
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    conn.execute("INSERT INTO signals (id, direction, tp3, ts_emitted) VALUES (1,'long',152.3,?)", (old,))
    conn.execute("INSERT INTO signal_progress (signal_id, event, ts_event, price) "
                 "VALUES (1,'tp3_hit',?,152.3)", (old,))
    conn.commit()
    conn.close()
    monkeypatch.setenv("FQ_VIP_LEDGER_PATH", str(vip_db))
    monkeypatch.setenv("FQ_PUBLIC_DB_PATH", str(pub_db))
    import public_outcome_announcer as poa
    importlib.reload(poa)
    poa.init_public_db()
    # TP3 de hace 48h queda fuera de la ventana (12h) -> no se celebra
    assert poa.get_new_tp3_to_announce() == []


def test_public_tp3_handles_legacy_ledger_without_progress(tmp_path, monkeypatch):
    """Ledger viejo sin tabla signal_progress -> no rompe, devuelve []."""
    vip_db = tmp_path / "ledger.db"
    pub_db = tmp_path / "public.db"
    conn = sqlite3.connect(str(vip_db))
    conn.execute("CREATE TABLE signals (id INTEGER PRIMARY KEY, direction TEXT, "
                 "tp3 REAL, ts_emitted TEXT)")
    conn.commit()
    conn.close()
    monkeypatch.setenv("FQ_VIP_LEDGER_PATH", str(vip_db))
    monkeypatch.setenv("FQ_PUBLIC_DB_PATH", str(pub_db))
    import public_outcome_announcer as poa
    importlib.reload(poa)
    poa.init_public_db()
    assert poa.get_new_tp3_to_announce() == []
