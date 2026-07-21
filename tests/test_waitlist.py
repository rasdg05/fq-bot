# -*- coding: utf-8 -*-
"""waitlist: captura de correo NO-CRITICA del embudo (FQ_COCKPIT). Garantias:
sin FQ_RESEND_API_KEY el correo NO se envia pero el registro SI se guarda (no
revienta); duplicados no crean filas nuevas; los tokens expiran; el rate
limit es una ventana simple en memoria."""
import time

import pytest

import waitlist as wl


def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(wl, "DB_PATH", str(tmp_path / "wl.db"))
    monkeypatch.setattr(wl, "RESEND_API_KEY", "")   # sin key -> nunca intenta la red
    monkeypatch.setattr(wl, "_rate", {})


@pytest.mark.parametrize("email,ok", [
    ("a@b.com", True),
    ("nombre.apellido@dominio.co", True),
    ("sin-arroba.com", False),
    ("@sin-usuario.com", False),
    ("a@b", False),
    ("", False),
    (None, False),
    ("a" * 260 + "@b.com", False),
])
def test_valid_email(email, ok):
    assert wl.valid_email(email) == ok


def test_subscribe_guarda_aunque_no_haya_api_key(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    r = wl.subscribe("nuevo@ejemplo.com")
    assert r == {"ok": True}
    c = wl._conn()
    row = c.execute("SELECT email, verified_at FROM waitlist WHERE email=?",
                     ("nuevo@ejemplo.com",)).fetchone()
    c.close()
    assert row is not None and row[1] is None


def test_subscribe_correo_invalido_no_guarda(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    r = wl.subscribe("esto-no-es-un-correo")
    assert r["ok"] is False
    c = wl._conn()
    n = c.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]
    c.close()
    assert n == 0


def test_subscribe_dedup_no_crea_fila_nueva(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    wl.subscribe("repetido@ejemplo.com")
    wl.subscribe("REPETIDO@ejemplo.com")   # normaliza a minusculas
    c = wl._conn()
    n = c.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]
    c.close()
    assert n == 1


def test_verify_ok_luego_already(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    wl.subscribe("verificar@ejemplo.com")
    c = wl._conn()
    token = c.execute("SELECT token FROM waitlist WHERE email=?",
                       ("verificar@ejemplo.com",)).fetchone()[0]
    c.close()
    assert wl.verify(token) == "ok"
    assert wl.verify(token) == "already"


def test_verify_token_invalido():
    assert wl.verify("no-existe-este-token") == "invalid"
    assert wl.verify("") == "invalid"
    assert wl.verify(None) == "invalid"


def test_verify_token_expirado(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    monkeypatch.setattr(wl, "_TOKEN_TTL_S", 0.01)
    wl.subscribe("expira@ejemplo.com")
    c = wl._conn()
    token = c.execute("SELECT token FROM waitlist WHERE email=?",
                       ("expira@ejemplo.com",)).fetchone()[0]
    c.close()
    time.sleep(0.05)
    assert wl.verify(token) == "expired"


def test_rate_limited_por_ip(monkeypatch):
    monkeypatch.setattr(wl, "_rate", {})
    ip = "10.0.0.1"
    hits = [wl.rate_limited(ip) for _ in range(wl._RATE_MAX + 2)]
    assert hits[:wl._RATE_MAX] == [False] * wl._RATE_MAX
    assert hits[-1] is True


def test_rate_limited_no_mezcla_ips(monkeypatch):
    monkeypatch.setattr(wl, "_rate", {})
    for _ in range(wl._RATE_MAX):
        wl.rate_limited("1.1.1.1")
    assert wl.rate_limited("2.2.2.2") is False
