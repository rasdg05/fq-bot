# -*- coding: utf-8 -*-
"""
Servidor Flask de la Mini App (webapp/server.py) via test client.
Cubre auth (401/403), enrutado por rol y que las superficies de cliente no
filtren jerga de motor.
"""
import hashlib
import hmac
import importlib
import json
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import pytest

ADMIN_ID = 999
TOKEN = "123456:TEST-bot-token"

# Jerga de motor que NUNCA debe aparecer en respuestas de cliente.
CLIENT_BANNED = [
    "p_master", "kappa", "bucket_key", "snapshot", "w_clock",
    "pspace", "curvature", "macro_btc", "rsi6", "secret",
]


def _sign(uid):
    fields = {
        "user": json.dumps({"id": uid, "first_name": "Sol", "username": "sol"}),
        "auth_date": str(int(time.time())),
        "query_id": "AAabc",
    }
    dcs = "\n".join("{}={}".format(k, fields[k]) for k in sorted(fields))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
def client(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.db"
    vipdb = tmp_path / "vip.db"
    monkeypatch.setenv("FQ_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("FQ_VIP_DB_PATH", str(vipdb))
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(ADMIN_ID))

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
    conn.execute(
        "INSERT INTO signals (id, ts_emitted, direction, entry_price, sl, tp1, tp2, tp3, tp4, "
        "p_master_final, kappa_evo, session, tier, bucket_key, snapshot_json) "
        "VALUES (1, ?, 'long', 145.0, 142.0, 148.0, 151.0, 154.0, 157.0, "
        "3.0, 0.05, 'ny', 'A', 'ny|A|long', '{\"secret\":1}')",
        (now.isoformat(),))
    conn.execute(
        "INSERT INTO signals (id, ts_emitted, ts_closed, direction, entry_price, sl, tp1, tp2, tp3, tp4, "
        "session, tier, outcome, pnl_r, minutes_open) "
        "VALUES (2, ?, ?, 'long', 140.0, 138.0, 142.0, 144.0, 146.0, 148.0, 'london', 'B', 'tp3', 1.8, 90)",
        ((now - timedelta(days=2)).isoformat(), (now - timedelta(days=2)).isoformat()))
    conn.commit()
    conn.close()

    import entropy_cognition
    importlib.reload(entropy_cognition)
    import vip_system
    importlib.reload(vip_system)
    vip_system.init_vip_db()
    vip_system.grant_subscription("555", "vip_30d", 30, source="test")

    import webapp.data as data
    importlib.reload(data)
    import webapp.server as server
    importlib.reload(server)
    app = server.create_app({"BOT_TOKEN": TOKEN, "MAX_AGE": 0, "DEV": False})
    app.testing = True
    return app.test_client()


def _get(client, path, uid=None):
    headers = {}
    if uid is not None:
        headers["X-Telegram-Init-Data"] = _sign(uid)
    return client.get(path, headers=headers)


# ---- auth ----
def test_healthz_no_auth(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_api_requires_auth(client):
    assert _get(client, "/api/me").status_code == 401


def test_invalid_initdata_rejected(client):
    r = client.get("/api/me", headers={"X-Telegram-Init-Data": "user=x&hash=bad"})
    assert r.status_code == 401


def test_me_admin(client):
    r = _get(client, "/api/me", uid=ADMIN_ID)
    assert r.status_code == 200
    body = r.get_json()
    assert body["role"] == "admin"
    assert body["is_admin"] is True


def test_me_vip(client):
    r = _get(client, "/api/me", uid=555)
    assert r.get_json()["role"] == "vip"


# ---- admin gating ----
def test_admin_route_allows_admin(client):
    r = _get(client, "/api/admin/overview", uid=ADMIN_ID)
    assert r.status_code == 200
    assert r.get_json()["signals_total"] == 2


def test_admin_route_forbids_non_admin(client):
    r = _get(client, "/api/admin/overview", uid=555)
    assert r.status_code == 403


def test_admin_route_requires_auth(client):
    assert _get(client, "/api/admin/stats").status_code == 401


# ---- client surfaces no leak ----
def test_client_signals_vip(client):
    r = _get(client, "/api/signals", uid=555)
    assert r.status_code == 200
    body = r.get_json()
    assert body["locked"] is False
    blob = r.get_data(as_text=True).lower()
    for tok in CLIENT_BANNED:
        assert tok not in blob, "fuga en /api/signals: " + tok


def test_client_signals_free_locked(client):
    r = _get(client, "/api/signals", uid=123456)
    body = r.get_json()
    assert body["locked"] is True
    open_sig = [s for s in body["signals"] if s["status"] == "open"][0]
    assert "entry_price" not in open_sig


def test_track_record_no_leak(client):
    r = _get(client, "/api/track-record", uid=555)
    assert r.status_code == 200
    blob = r.get_data(as_text=True).lower()
    for tok in CLIENT_BANNED:
        assert tok not in blob
