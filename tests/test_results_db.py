# -*- coding: utf-8 -*-
"""
End-to-end del track record: crea un ledger SQLite temporal, inserta cierres
y verifica que entropy_cognition.get_results_summary lo resume bien.
"""
import os
import sqlite3
import importlib
from datetime import datetime, timezone, timedelta

import pytest


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Ledger SQLite temporal con esquema minimo y unas senales cerradas."""
    db = tmp_path / "ledger.db"
    monkeypatch.setenv("FQ_LEDGER_PATH", str(db))

    # Esquema minimo compatible con get_results_summary.
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_emitted TEXT, ts_closed TEXT,
            outcome TEXT, pnl_r REAL,
            symbol TEXT NOT NULL DEFAULT 'SOL'
        )
    """)
    now = datetime.now(timezone.utc)
    data = [
        ("tp3", 1.8, 5), ("tp1", 0.9, 10), ("sl", -1.0, 25),
        ("tp2", 1.4, 50), ("sl", -1.0, 200),
    ]
    for outcome, pnl, days in data:
        ts = (now - timedelta(days=days)).isoformat()
        conn.execute(
            "INSERT INTO signals (ts_emitted, ts_closed, outcome, pnl_r) VALUES (?,?,?,?)",
            (ts, ts, outcome, pnl))
    # una senal abierta (no debe contar)
    conn.execute(
        "INSERT INTO signals (ts_emitted, ts_closed, outcome, pnl_r) VALUES (?,?,?,?)",
        (now.isoformat(), None, None, None))
    conn.commit()
    conn.close()

    # Re-importar entropy_cognition para que tome el FQ_LEDGER_PATH del fixture.
    import entropy_cognition
    importlib.reload(entropy_cognition)
    return entropy_cognition


def test_get_results_summary_counts(ledger):
    s = ledger.get_results_summary()
    assert s is not None
    assert s["total"]["n"] == 5          # 5 cerradas, la abierta no cuenta
    assert s["w30"]["n"] == 3            # 5,10,25 dias
    assert s["w90"]["n"] == 4            # + 50 dias


def test_get_results_summary_winrate(ledger):
    s = ledger.get_results_summary()
    # 3 wins (tp) de 5 = 60%
    assert abs(s["total"]["win_rate"] - 0.6) < 1e-9


def test_get_results_summary_empty(tmp_path, monkeypatch):
    db = tmp_path / "empty.db"
    monkeypatch.setenv("FQ_LEDGER_PATH", str(db))
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_emitted TEXT, ts_closed TEXT, outcome TEXT, pnl_r REAL,
            symbol TEXT NOT NULL DEFAULT 'SOL')
    """)
    conn.commit()
    conn.close()
    import entropy_cognition
    importlib.reload(entropy_cognition)
    assert entropy_cognition.get_results_summary() is None
