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
            outcome TEXT, pnl_r REAL, minutes_open INTEGER,
            symbol TEXT NOT NULL DEFAULT 'SOL'
        )
    """)
    now = datetime.now(timezone.utc)
    # (outcome, pnl_r, dias_atras, minutes_open). minutes_open dentro del
    # horizonte auditable (<= 8h + gracia) -> las 5 cuentan.
    data = [
        ("tp3", 1.8, 5, 120), ("tp1", 0.9, 10, 45), ("sl", -1.0, 25, 14),
        ("tp2", 1.4, 50, 300), ("sl", -1.0, 200, 30),
    ]
    for outcome, pnl, days, mins in data:
        ts = (now - timedelta(days=days)).isoformat()
        conn.execute(
            "INSERT INTO signals (ts_emitted, ts_closed, outcome, pnl_r, minutes_open) "
            "VALUES (?,?,?,?,?)",
            (ts, ts, outcome, pnl, mins))
    # una senal abierta (no debe contar)
    conn.execute(
        "INSERT INTO signals (ts_emitted, ts_closed, outcome, pnl_r) VALUES (?,?,?,?)",
        (now.isoformat(), None, None, None))
    # Cierre NO AUDITABLE: vida registrada de 30 dias, imposible bajo un tracker
    # correcto (horizonte 8h). Es la firma del bloque fantasma del 10-jun-2026 y
    # NO debe entrar en ninguna metrica publicada, ni siquiera como perdida.
    ts_ghost = (now - timedelta(days=7)).isoformat()
    conn.execute(
        "INSERT INTO signals (ts_emitted, ts_closed, outcome, pnl_r, minutes_open) "
        "VALUES (?,?,?,?,?)",
        (ts_ghost, ts_ghost, "tp4", 10.9, 43611))
    conn.commit()
    conn.close()

    # Re-importar entropy_cognition para que tome el FQ_LEDGER_PATH del fixture.
    import entropy_cognition
    importlib.reload(entropy_cognition)
    return entropy_cognition


def test_get_results_summary_counts(ledger):
    s = ledger.get_results_summary()
    assert s is not None
    # 5 cerradas auditables. Ni la abierta ni el cierre fantasma (minutes_open
    # 43611 > horizonte) cuentan.
    assert s["total"]["n"] == 5
    assert s["w30"]["n"] == 3            # 5,10,25 dias
    assert s["w90"]["n"] == 4            # + 50 dias


def test_cierre_no_auditable_excluido(ledger):
    """Una senal cuya vida registrada excede su horizonte no pudo producirla un
    tracker correcto -> fuera de las metricas, y su +10.9R no infla nada."""
    s = ledger.get_results_summary()
    assert s["total"]["n"] == 5
    assert s["total"]["best_pnl"] < 2.0        # el 10.9R fantasma no aparece
    assert s["total"]["expectancy"] < 1.0


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
            minutes_open INTEGER,
            symbol TEXT NOT NULL DEFAULT 'SOL')
    """)
    conn.commit()
    conn.close()
    import entropy_cognition
    importlib.reload(entropy_cognition)
    assert entropy_cognition.get_results_summary() is None
