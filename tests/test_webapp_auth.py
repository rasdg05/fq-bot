# -*- coding: utf-8 -*-
"""
Validacion del initData de Telegram (webapp/auth.py). Pura, sin red.
Firma payloads con el mismo algoritmo de Telegram y verifica aceptacion/rechazo.
"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from webapp import auth

TOKEN = "123456:TEST-bot-token"


def _sign(fields, token=TOKEN):
    """Construye un initData firmado valido a partir de campos crudos (decoded)."""
    dcs = "\n".join("{}={}".format(k, fields[k]) for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    payload = dict(fields)
    payload["hash"] = h
    return urlencode(payload)


def _fields(uid=42, auth_date=None):
    return {
        "user": json.dumps({"id": uid, "first_name": "Sol", "username": "sol"}),
        "auth_date": str(int(auth_date if auth_date is not None else time.time())),
        "query_id": "AAabc",
    }


def test_valid_init_data():
    init = _sign(_fields(uid=99))
    res = auth.validate_init_data(init, TOKEN)
    assert res["ok"] is True
    assert res["user"]["id"] == 99
    assert res["error"] is None


def test_tampered_hash_rejected():
    init = _sign(_fields()) + "0"  # ensucia el hash
    res = auth.validate_init_data(init, TOKEN)
    assert res["ok"] is False


def test_wrong_token_rejected():
    init = _sign(_fields(), token=TOKEN)
    res = auth.validate_init_data(init, "999:OTHER-token")
    assert res["ok"] is False
    assert res["error"] == "hash invalido"


def test_missing_hash_rejected():
    res = auth.validate_init_data(urlencode(_fields()), TOKEN)
    assert res["ok"] is False
    assert res["error"] == "falta hash"


def test_empty_rejected():
    assert auth.validate_init_data("", TOKEN)["ok"] is False
    assert auth.validate_init_data(None, TOKEN)["ok"] is False


def test_expired_rejected():
    old = time.time() - 10000
    init = _sign(_fields(auth_date=old))
    res = auth.validate_init_data(init, TOKEN, max_age_seconds=3600)
    assert res["ok"] is False
    assert res["error"] == "initData expirado"


def test_max_age_zero_skips_freshness():
    old = time.time() - 10_000_000
    init = _sign(_fields(auth_date=old))
    res = auth.validate_init_data(init, TOKEN, max_age_seconds=0)
    assert res["ok"] is True


def test_signature_field_excluded_from_check():
    """Si Telegram incluye 'signature' (validacion Ed25519 de terceros), no debe
    romper el HMAC: se excluye del data_check_string igual que 'hash'."""
    fields = _fields(uid=7)
    init = _sign(fields)  # firma SIN signature
    # Inyecta un signature arbitrario; el hash sigue siendo valido.
    init = init + "&" + urlencode({"signature": "ed25519sig"})
    res = auth.validate_init_data(init, TOKEN)
    assert res["ok"] is True
    assert res["user"]["id"] == 7


def test_no_bot_token():
    init = _sign(_fields())
    res = auth.validate_init_data(init, "")
    assert res["ok"] is False
