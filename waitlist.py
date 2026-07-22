# -*- coding: utf-8 -*-
"""waitlist -- captura de correo NO-CRITICA para el embudo del portal FQ
(FQ_COCKPIT). Mismo principio que cockpit.py: si esto falla, el server
sigue sirviendo el resto de rutas -- todo try/except, todo best-effort,
nada bloquea al bot (vive en el proceso hijo no-critico del cockpit).

Flujo: POST /waitlist {email} -> guarda + manda link de verificacion
(Resend, API HTTP simple via urllib -- sin SDK/dependencias nuevas).
GET /verify?token=... -> marca verificado; el server entrega ahi mismo
la guia + el link de Telegram (ver tools/cockpit_server.py).

A proposito NO otorga codigos de VIP/trial: un formulario publico no debe
poder acuñar trials solo -- eso sigue siendo decision manual de un admin
(vip_system.generate_code / /grant). Esto es el TOF del embudo ya descrito
en presentaciones/marketing-kit-2026-07.md: captura -> entrega del
lead-magnet -> nurture -> conversion a VIP (esa parte sigue igual).
"""
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.request

log = logging.getLogger("fq.waitlist")

DB_PATH = os.environ.get("FQ_WAITLIST_DB_PATH") or (
    "/data/fq_waitlist.db" if os.path.isdir("/data") else "data/fq_waitlist.db")

# Resend (https://resend.com): API HTTP simple, sin dominio propio solo manda
# en modo sandbox (a tu propio correo verificado). Con dominio propio
# verificado, cambia FQ_MAIL_FROM -- cero cambios de codigo.
RESEND_API_KEY = os.environ.get("FQ_RESEND_API_KEY", "").strip()
MAIL_FROM = os.environ.get("FQ_MAIL_FROM", "FQ Capital <onboarding@resend.dev>").strip()
# Base publica para el link de verificacion. Si no esta seteada, el server
# la arma con el Host de la request (ver cockpit_server.py).
PUBLIC_BASE_URL = os.environ.get("FQ_PUBLIC_BASE_URL", "").strip().rstrip("/")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TOKEN_TTL_S = 48 * 3600
_RESEND_COOLDOWN_S = 60

_lock = threading.Lock()
_rate = {}          # ip -> [timestamps]: ventana simple en memoria, no-critica
_RATE_MAX = 5
_RATE_WINDOW_S = 3600


def _conn():
    d = os.path.dirname(DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=20)
    c.execute("""CREATE TABLE IF NOT EXISTS waitlist(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        token TEXT NOT NULL,
        created_at REAL NOT NULL,
        verified_at REAL,
        last_sent_at REAL,
        send_count INTEGER NOT NULL DEFAULT 0)""")
    return c


def valid_email(email):
    email = (email or "").strip()
    return bool(email) and len(email) <= 254 and bool(_EMAIL_RE.match(email))


def rate_limited(ip):
    """True si esa IP ya paso el limite en la ventana. Best-effort: se
    resetea si el proceso reinicia (es anti-spam, no una garantia dura)."""
    now = time.time()
    with _lock:
        hits = [t for t in _rate.get(ip, []) if now - t < _RATE_WINDOW_S]
        hits.append(now)
        _rate[ip] = hits
        return len(hits) > _RATE_MAX


def _verify_link(token, base_url=None):
    base = (base_url or PUBLIC_BASE_URL or "").rstrip("/")
    return "{}/verify?token={}".format(base, token)


def _send_verification_email(email, token, base_url=None):
    if not RESEND_API_KEY:
        log.info("[waitlist] FQ_RESEND_API_KEY no configurada -- correo NO enviado (queda guardado igual)")
        return False
    link = _verify_link(token, base_url)
    html = (
        '<div style="font-family:Helvetica,Arial,sans-serif;max-width:480px;margin:0 auto;'
        'padding:32px 24px;color:#111">'
        '<p style="font-size:20px;font-weight:700;margin:0 0 18px;letter-spacing:.04em">FQ CAPITAL</p>'
        '<p style="font-size:15px;line-height:1.6">Confirma tu correo para recibir la guía '
        'gratis y tu acceso.</p>'
        '<p style="margin:26px 0"><a href="{link}" '
        'style="background:#c9a227;color:#0a0c0a;text-decoration:none;font-weight:700;'
        'padding:12px 22px;border-radius:8px;display:inline-block">Confirmar correo</a></p>'
        '<p style="font-size:12px;color:#777">El link expira en 48 horas. Si no fuiste tú, '
        'ignora este correo.</p></div>'
    ).format(link=link)
    body = json.dumps({"from": MAIL_FROM, "to": [email],
                        "subject": "Confirma tu correo — FQ Capital",
                        "html": html}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=body, method="POST",
        headers={"Authorization": "Bearer " + RESEND_API_KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return 200 <= r.status < 300
    except Exception as e:
        log.warning("[waitlist] fallo enviando verificacion a %s: %s", email, e)
        return False


def subscribe(email, base_url=None):
    """Guarda el correo (o reenvia si aun no se verifico). SIEMPRE devuelve
    un mensaje generico de exito para un correo con formato valido -- no
    delata si ya existia (evita enumeracion de correos)."""
    email = (email or "").strip().lower()
    if not valid_email(email):
        return {"ok": False, "error": "ese correo no parece válido"}
    try:
        c = _conn()
        try:
            row = c.execute(
                "SELECT token, verified_at, last_sent_at FROM waitlist WHERE email=?",
                (email,)).fetchone()
            now = time.time()
            if row is None:
                token = secrets.token_urlsafe(24)
                c.execute(
                    "INSERT INTO waitlist(email, token, created_at, last_sent_at, send_count) "
                    "VALUES (?,?,?,?,1)", (email, token, now, now))
                c.commit()
                _send_verification_email(email, token, base_url)
            else:
                token, verified_at, last_sent_at = row
                if not verified_at and (not last_sent_at or now - last_sent_at > _RESEND_COOLDOWN_S):
                    c.execute(
                        "UPDATE waitlist SET last_sent_at=?, send_count=send_count+1 WHERE email=?",
                        (now, email))
                    c.commit()
                    _send_verification_email(email, token, base_url)
        finally:
            c.close()
        return {"ok": True}
    except Exception as e:
        log.warning("[waitlist] subscribe fallo: %s", e)
        return {"ok": True}   # nunca delatamos el error interno al cliente


def verify(token):
    """'ok' | 'already' | 'expired' | 'invalid'."""
    token = (token or "").strip()
    if not token:
        return "invalid"
    try:
        c = _conn()
        try:
            row = c.execute(
                "SELECT created_at, verified_at FROM waitlist WHERE token=?",
                (token,)).fetchone()
            if row is None:
                return "invalid"
            created_at, verified_at = row
            if verified_at:
                return "already"
            if time.time() - created_at > _TOKEN_TTL_S:
                return "expired"
            c.execute("UPDATE waitlist SET verified_at=? WHERE token=?", (time.time(), token))
            c.commit()
            return "ok"
        finally:
            c.close()
    except Exception as e:
        log.warning("[waitlist] verify fallo: %s", e)
        return "invalid"
