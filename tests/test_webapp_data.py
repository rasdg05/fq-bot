# -*- coding: utf-8 -*-
"""
Capa de datos de la Mini App (webapp/data.py). Ledger + BD VIP temporales.
Verifica resolucion de roles, whitelist de cliente y matematica de admin.
"""
import importlib
import sqlite3
from datetime import datetime, timezone, timedelta

import pytest

ADMIN_ID = "999"


@pytest.fixture
def app_data(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.db"
    vipdb = tmp_path / "vip.db"
    monkeypatch.setenv("FQ_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("FQ_VIP_DB_PATH", str(vipdb))
    monkeypatch.setenv("TELEGRAM_CHAT_ID", ADMIN_ID)

    conn = sqlite3.connect(str(ledger))
    conn.execute("""
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_emitted TEXT, ts_closed TEXT,
            direction TEXT, entry_price REAL, sl REAL,
            tp1 REAL, tp2 REAL, tp3 REAL, tp4 REAL,
            p_master_final REAL, kappa_evo REAL, session TEXT, tier TEXT,
            bucket_key TEXT, snapshot_json TEXT,
            outcome TEXT, exit_price REAL, pnl_r REAL, minutes_open INTEGER
        )""")
    conn.execute("""
        CREATE TABLE signal_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER, event TEXT, ts_event TEXT, price REAL,
            UNIQUE(signal_id, event))""")
    now = datetime.now(timezone.utc)
    # 1: abierta long
    conn.execute(
        "INSERT INTO signals (id, ts_emitted, direction, entry_price, sl, tp1, tp2, tp3, tp4, "
        "p_master_final, kappa_evo, session, tier, bucket_key, snapshot_json) "
        "VALUES (1, ?, 'long', 145.0, 142.0, 148.0, 151.0, 154.0, 157.0, "
        "3.0, 0.05, 'ny', 'A', 'ny|A|long', '{\"secret\":1}')",
        (now.isoformat(),))
    conn.execute("INSERT INTO signal_progress (signal_id, event, ts_event, price) "
                 "VALUES (1, 'tp1_hit', ?, 148.0)", (now.isoformat(),))
    # 2: cerrada win
    conn.execute(
        "INSERT INTO signals (id, ts_emitted, ts_closed, direction, entry_price, sl, "
        "tp1, tp2, tp3, tp4, session, tier, outcome, pnl_r, minutes_open) "
        "VALUES (2, ?, ?, 'long', 140.0, 138.0, 142.0, 144.0, 146.0, 148.0, 'london', 'B', 'tp3', 1.8, 90)",
        ((now - timedelta(days=2)).isoformat(), (now - timedelta(days=2)).isoformat()))
    # 3: cerrada loss
    conn.execute(
        "INSERT INTO signals (id, ts_emitted, ts_closed, direction, entry_price, sl, "
        "tp1, tp2, tp3, tp4, session, tier, outcome, pnl_r, minutes_open) "
        "VALUES (3, ?, ?, 'short', 150.0, 152.0, 148.0, 146.0, 144.0, 142.0, 'asia', 'C', 'sl', -1.0, 30)",
        ((now - timedelta(days=3)).isoformat(), (now - timedelta(days=3)).isoformat()))
    conn.commit()
    conn.close()

    import entropy_cognition
    importlib.reload(entropy_cognition)
    import vip_system
    importlib.reload(vip_system)
    vip_system.init_vip_db()
    # un VIP activo y un free implicito
    vip_system.grant_subscription("555", "vip_30d", 30, source="test")

    import webapp.data as data
    importlib.reload(data)
    return data


# ---- roles ----
def test_role_admin(app_data):
    assert app_data.role_for(ADMIN_ID) == "admin"
    assert app_data.is_admin(ADMIN_ID) is True


def test_role_vip(app_data):
    assert app_data.role_for("555") == "vip"


def test_role_free_unknown(app_data):
    assert app_data.role_for("123456") == "free"


# ---- client signals ----
def test_client_vip_sees_levels(app_data):
    out = app_data.client_signals("555")
    assert out["role"] == "vip"
    assert out["locked"] is False
    open_sig = [s for s in out["signals"] if s["status"] == "open"][0]
    assert open_sig["entry_price"] == 145.0
    assert open_sig["sl"] == 142.0


def test_client_free_open_is_locked(app_data):
    out = app_data.client_signals("123456")
    assert out["locked"] is True
    open_sig = [s for s in out["signals"] if s["status"] == "open"][0]
    assert open_sig["locked"] is True
    assert "entry_price" not in open_sig          # nivel oculto
    # los cierres (resultados) si son visibles
    closed = [s for s in out["signals"] if s["status"] == "closed"]
    assert closed and closed[0]["outcome"] in ("tp3", "sl")


def test_client_view_has_no_engine_jargon(app_data):
    out = app_data.client_signals("555")
    blob = repr(out).lower()
    for tok in ("p_master", "kappa", "bucket_key", "snapshot", "secret"):
        assert tok not in blob, "fuga de jerga: " + tok


def test_progress_attached(app_data):
    out = app_data.client_signals("555")
    open_sig = [s for s in out["signals"] if s["status"] == "open"][0]
    events = [p["event"] for p in open_sig["progress"]]
    assert "tp1_hit" in events


# ---- admin ----
def test_admin_signal_view_has_math(app_data):
    out = app_data.admin_signals()
    open_sig = out["open"][0]
    assert open_sig["p_master_final"] == 3.0
    assert open_sig["kappa_evo"] == 0.05
    assert open_sig["session"] == "ny"


def test_admin_stats(app_data):
    st = app_data.admin_stats()
    assert st["global"]["n"] == 2           # 2 cerradas
    assert abs(st["global"]["win_rate"] - 0.5) < 1e-9
    assert st["summary"]["total"]["n"] == 2


def test_admin_overview_counts(app_data):
    ov = app_data.admin_overview()
    assert ov["open_count"] == 1
    assert ov["signals_total"] == 3
    assert ov["signals_closed"] == 2
    assert "vip" in ov["health"]


def test_admin_subs(app_data):
    subs = app_data.admin_subs()
    assert subs["stats"]["users_total"] >= 1
    assert any(u["tier"] == "vip" for u in subs["recent_users"])


# ---- track record ----
def test_track_record(app_data):
    tr = app_data.track_record()
    assert tr is not None
    assert tr["total"]["n"] == 2


# ---- robustez en arranque en frio (BDs aun sin tablas/archivos) ----
def test_cold_start_no_dbs(tmp_path, monkeypatch):
    """La app es RO: si las BDs no existen todavia, degrada sin reventar."""
    monkeypatch.setenv("FQ_LEDGER_PATH", str(tmp_path / "missing_ledger.db"))
    monkeypatch.setenv("FQ_VIP_DB_PATH", str(tmp_path / "missing_vip.db"))
    monkeypatch.setenv("TELEGRAM_CHAT_ID", ADMIN_ID)
    import entropy_cognition
    importlib.reload(entropy_cognition)
    import vip_system
    importlib.reload(vip_system)
    import webapp.data as data
    importlib.reload(data)

    assert data.role_for("123") == "free"          # sin tabla users -> free
    assert data.role_for(ADMIN_ID) == "admin"      # admin es env, no BD
    assert data.me("123")["days_remaining"] is None
    assert data.client_signals("123")["signals"] == []
    assert data.track_record() is None
    ov = data.admin_overview()
    assert ov["signals_total"] == 0
    assert ov["open_count"] == 0
