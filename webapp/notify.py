# -*- coding: utf-8 -*-
"""
Notificaciones con boton "Abrir app".

La Mini App no tiene push propio: la notificacion es un mensaje normal del bot.
El valor que agrega esta capa es un boton inline `web_app` que abre la Mini App
directamente en la vista relevante (senal, resultados, salud, suscriptores).

Aislado y best-effort: cualquier fallo de red se traga (nunca rompe el motor ni
el broadcast). No importa el monolito; recibe el token por parametro o del env.

URL de la Mini App: env FQ_WEBAPP_URL (https). Sin ella, las funciones de envio
hacen fallback a un mensaje sin boton.
"""
import os
import logging

import requests

log = logging.getLogger("fq_webapp_notify")

# Vistas validas para deep-link (?startapp / #hash las consume el frontend).
VIEWS = ("signals", "results", "health", "subs")


def webapp_url():
    return (os.environ.get("FQ_WEBAPP_URL") or "").strip()


def _token(token=None):
    return (token
            or os.environ.get("FQ_WEBAPP_BOT_TOKEN")
            or os.environ.get("TELEGRAM_TOKEN")
            or "").strip()


def app_button(label="Abrir app", view=None):
    """Inline keyboard con un boton web_app. None si no hay URL configurada."""
    url = webapp_url()
    if not url:
        return None
    if view:
        sep = "&" if "?" in url else "?"
        url = "{}{}startapp={}".format(url, sep, view)
    return {"inline_keyboard": [[{"text": label, "web_app": {"url": url}}]]}


def send_with_app_button(chat_id, text, view=None, label="Abrir app",
                         token=None, parse_mode="HTML"):
    """Envia `text` a chat_id con boton "Abrir app". Best-effort -> bool.

    Si no hay URL configurada, envia el texto sin boton (sigue notificando).
    """
    tok = _token(token)
    if not tok:
        return False
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    markup = app_button(label=label, view=view)
    if markup:
        payload["reply_markup"] = markup
    url = "https://api.telegram.org/bot{}/sendMessage".format(tok)
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            return True
        log.warning("notify send %s HTTP %s: %s", chat_id, r.status_code, r.text[:160])
    except Exception as e:
        log.warning("notify send %s exception: %s", chat_id, e)
    return False
