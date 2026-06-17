# -*- coding: utf-8 -*-
"""
Validacion del initData de Telegram WebApp (Mini App).

Puro: sin red, sin estado, solo stdlib. Recibe el string initData que el
cliente Telegram firma y el token del bot, y verifica el HMAC-SHA256 segun
la especificacion oficial de Telegram. Si valida, devuelve el usuario.

Spec (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app):
  data_check_string = todos los campos excepto `hash` (y `signature`),
                      ordenados alfabeticamente, unidos con '\\n' como 'k=v'
  secret_key        = HMAC_SHA256(key="WebAppData", msg=bot_token)
  hash_esperado     = HMAC_SHA256(key=secret_key, msg=data_check_string)
  valido si hex(hash_esperado) == hash recibido (comparacion constante)

Ademas se valida frescura via `auth_date` para mitigar replay.
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

# Campos que NO entran al data_check_string:
#  - hash: es el propio HMAC recibido.
#  - signature: firma Ed25519 para validacion por terceros; Telegram la excluye
#    del calculo HMAC con bot_token.
_EXCLUDED_FROM_CHECK = ("hash", "signature")


def parse_init_data(init_data):
    """Parsea el query-string initData en un dict {clave: valor} ya URL-decoded.

    Mantiene el ultimo valor si hubiera claves repetidas (no deberia haberlas).
    """
    if not init_data:
        return {}
    # keep_blank_values para no perder campos vacios legitimos.
    return dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))


def _data_check_string(fields):
    """Construye el data_check_string canonico (orden alfabetico, sin hash/signature)."""
    parts = [
        "{}={}".format(k, v)
        for k, v in sorted(fields.items())
        if k not in _EXCLUDED_FROM_CHECK
    ]
    return "\n".join(parts)


def _expected_hash(bot_token, data_check_string):
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def validate_init_data(init_data, bot_token, max_age_seconds=86400, now=None):
    """Valida initData. Devuelve dict con el resultado.

    Args:
        init_data: string crudo de Telegram.WebApp.initData
        bot_token: token del bot que sirve la Mini App
        max_age_seconds: rechaza si auth_date es mas viejo (0/None = sin chequeo)
        now: epoch override para tests

    Returns:
        {
          "ok": bool,
          "user": dict|None,        # {id, first_name, username, ...}
          "auth_date": int|None,
          "error": str|None,
        }
    """
    if not bot_token:
        return {"ok": False, "user": None, "auth_date": None,
                "error": "bot_token ausente"}

    fields = parse_init_data(init_data)
    if not fields:
        return {"ok": False, "user": None, "auth_date": None,
                "error": "initData vacio"}

    received_hash = fields.get("hash")
    if not received_hash:
        return {"ok": False, "user": None, "auth_date": None,
                "error": "falta hash"}

    expected = _expected_hash(bot_token, _data_check_string(fields))
    if not hmac.compare_digest(expected, received_hash):
        return {"ok": False, "user": None, "auth_date": None,
                "error": "hash invalido"}

    # Frescura (anti-replay).
    auth_date = None
    raw_auth = fields.get("auth_date")
    if raw_auth is not None:
        try:
            auth_date = int(raw_auth)
        except (TypeError, ValueError):
            return {"ok": False, "user": None, "auth_date": None,
                    "error": "auth_date invalido"}
    if max_age_seconds and auth_date is not None:
        ref = now if now is not None else time.time()
        if ref - auth_date > max_age_seconds:
            return {"ok": False, "user": None, "auth_date": auth_date,
                    "error": "initData expirado"}

    # Usuario (viene como JSON URL-encoded dentro del campo `user`).
    user = None
    raw_user = fields.get("user")
    if raw_user:
        try:
            user = json.loads(raw_user)
        except (TypeError, ValueError):
            return {"ok": False, "user": None, "auth_date": auth_date,
                    "error": "user json invalido"}

    if not user or "id" not in user:
        return {"ok": False, "user": None, "auth_date": auth_date,
                "error": "user ausente"}

    return {"ok": True, "user": user, "auth_date": auth_date, "error": None}
