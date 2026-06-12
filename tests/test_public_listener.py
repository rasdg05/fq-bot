# -*- coding: utf-8 -*-
"""Bug 409 (jun-2026): dos consumidores de getUpdates con el mismo token.

El bot publico spameaba 'getUpdates HTTP 409' cada ~11s. Dos causas posibles
con el mismo sintoma:
 1) un servicio Railway duplicado polleando con el MISMO token publico, o
 2) TELEGRAM_TOKEN_PUBLIC ausente en el worker -> entry_public caia al
    fallback del token VIP y peleaba contra el poller del VIP en el MISMO
    container (el 409 del lado VIP es silencioso: telegram_get_updates
    devuelve [] sin loguear el status).

Cubre: resolucion del token (sin fallback VIP bajo launcher) y el backoff
exponencial ante 409 consecutivos.
"""
import entry_public as epub


# --------------------------------------------------------------------------
# _resolve_public_token
# --------------------------------------------------------------------------
def test_resolve_token_public_set():
    tok, src = epub._resolve_public_token({"TELEGRAM_TOKEN_PUBLIC": " abc "})
    assert tok == "abc"
    assert src == "public"


def test_resolve_token_fallback_solo_standalone():
    # legacy: un solo bot en el proceso -> el fallback al token VIP se conserva
    tok, src = epub._resolve_public_token({"TELEGRAM_TOKEN": "vip-tok"})
    assert tok == "vip-tok"
    assert src == "vip_fallback"


def test_resolve_token_sin_fallback_bajo_launcher():
    # REGRESION 409: bajo el launcher el VIP ya esta polleando este token en
    # el mismo container; robarlo = guerra de getUpdates. No hay fallback.
    tok, src = epub._resolve_public_token(
        {"TELEGRAM_TOKEN": "vip-tok", "FQ_LAUNCHER": "1"})
    assert tok == ""
    assert src is None


def test_resolve_token_public_gana_bajo_launcher():
    tok, src = epub._resolve_public_token(
        {"TELEGRAM_TOKEN_PUBLIC": "pub-tok", "TELEGRAM_TOKEN": "vip-tok",
         "FQ_LAUNCHER": "1"})
    assert tok == "pub-tok"
    assert src == "public"


def test_resolve_token_vacio_sin_envs():
    tok, src = epub._resolve_public_token({})
    assert tok == ""
    assert src is None


# --------------------------------------------------------------------------
# _conflict_backoff (espera tras 409 consecutivos)
# --------------------------------------------------------------------------
def test_conflict_backoff_escala_y_capea():
    waits = [epub._conflict_backoff(n) for n in range(1, 10)]
    assert waits[0] == epub.CONFLICT_BACKOFF_BASE_SEC      # 1er 409 -> 5s
    assert waits == sorted(waits)                          # nunca decrece
    assert waits[-1] == epub.CONFLICT_BACKOFF_MAX_SEC      # capea en 300s
    assert epub._conflict_backoff(1000) == epub.CONFLICT_BACKOFF_MAX_SEC


def test_conflict_backoff_cero_sin_conflictos():
    assert epub._conflict_backoff(0) == 0
