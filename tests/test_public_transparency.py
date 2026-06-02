# -*- coding: utf-8 -*-
"""
Transparencia del bot publico (peticion RasDG, jun-2026): se anuncian wins Y
losses, no solo los cierres +1R. Track record honesto = confianza.
"""
import importlib
import sqlite3
from datetime import datetime, timezone, timedelta

import pytest


def _seed_closed_signals(path):
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT, entry_price REAL, sl REAL,
            tp1 REAL, tp2 REAL, tp3 REAL, tp4 REAL,
            ts_emitted TEXT, ts_closed TEXT, outcome TEXT,
            exit_price REAL, pnl_r REAL, minutes_open INTEGER
        )
    """)
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=2)).isoformat()
    rows = [
        ("long",  "tp3", 4.0, 90),    # win grande
        ("short", "sl", -1.0, 30),    # loss
        ("long",  "tp1", 0.9, 20),    # win chico
    ]
    for direction, outcome, pnl, mins in rows:
        conn.execute(
            "INSERT INTO signals (direction, entry_price, sl, tp1, tp2, tp3, tp4, "
            "ts_emitted, ts_closed, outcome, exit_price, pnl_r, minutes_open) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (direction, 79.0, 79.8, 78.0, 77.0, 76.0, 75.0,
             recent, recent, outcome, 76.0, pnl, mins))
    conn.commit()
    conn.close()


@pytest.fixture
def poa(tmp_path, monkeypatch):
    vip_db = tmp_path / "ledger.db"
    pub_db = tmp_path / "public.db"
    _seed_closed_signals(vip_db)
    monkeypatch.setenv("FQ_VIP_LEDGER_PATH", str(vip_db))
    monkeypatch.setenv("FQ_PUBLIC_DB_PATH", str(pub_db))
    import public_outcome_announcer as mod
    importlib.reload(mod)
    mod.init_public_db()
    return mod


def test_announces_wins_and_losses(poa):
    closures = poa.get_new_closures_to_announce()
    outcomes = sorted(c["outcome"] for c in closures)
    # incluye el SL (loss) ademas de los wins
    assert "sl" in outcomes
    assert "tp3" in outcomes
    assert "tp1" in outcomes
    assert len(closures) == 3


def test_loss_is_idempotent(poa):
    closures = poa.get_new_closures_to_announce()
    loss = next(c for c in closures if c["outcome"] == "sl")
    poa.mark_announced(loss["id"], outcome="sl", pnl_r=loss["pnl_r"])
    remaining = [c["outcome"] for c in poa.get_new_closures_to_announce()]
    assert "sl" not in remaining


def test_loss_renders_honestly():
    import public_format as pf
    msg = pf.build_closure_announcement(
        {"direction": "short", "outcome": "sl", "pnl_r": -1.0,
         "minutes_open": 30, "ts_emitted": "2026-06-01T13:00:00Z",
         "ts_closed": "2026-06-01T13:30:00Z"})
    assert "SL" in msg
    assert "-1.00R" in msg
