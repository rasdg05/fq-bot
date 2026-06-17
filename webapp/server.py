# -*- coding: utf-8 -*-
"""
App Flask de la Mini App FQ.

Sirve la SPA (webapp/static) y una API JSON de SOLO LECTURA sobre el ledger.
Cada request a /api/* exige el initData firmado de Telegram (cabecera
X-Telegram-Init-Data), que se valida con HMAC contra el token del bot. El rol
(admin/vip/trial/free) se resuelve del lado servidor; las rutas /api/admin/*
exigen rol admin. Nada aqui escribe en las BDs.

Factory: create_app() -> Flask. Config por env (override en tests):
  FQ_WEBAPP_BOT_TOKEN  token para validar initData (default TELEGRAM_TOKEN)
  FQ_WEBAPP_MAX_AGE_SEC frescura del initData (default 86400; 0 = sin chequeo)
  FQ_WEBAPP_DEV        '1' habilita bypass de auth para desarrollo local
  FQ_WEBAPP_DEV_USER   chat_id a impersonar en modo dev (default TELEGRAM_CHAT_ID)
"""
import os
import functools

from flask import Flask, g, jsonify, request, send_from_directory

from . import auth
from . import data

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def _truthy(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def create_app(config=None):
    app = Flask(__name__, static_folder=_STATIC_DIR, static_url_path="/static")

    cfg = {
        "BOT_TOKEN": (os.environ.get("FQ_WEBAPP_BOT_TOKEN")
                      or os.environ.get("TELEGRAM_TOKEN", "")).strip(),
        "MAX_AGE": int(os.environ.get("FQ_WEBAPP_MAX_AGE_SEC", "86400")),
        "DEV": _truthy(os.environ.get("FQ_WEBAPP_DEV")),
        "DEV_USER": (os.environ.get("FQ_WEBAPP_DEV_USER")
                     or os.environ.get("TELEGRAM_CHAT_ID", "")).strip(),
    }
    if config:
        cfg.update(config)
    app.config.update(cfg)

    # --------------------------------------------------------------
    # Auth
    # --------------------------------------------------------------
    def _resolve_user():
        """Devuelve (uid, user_dict) o (None, None). Aplica bypass dev si toca."""
        init_data = (
            request.headers.get("X-Telegram-Init-Data")
            or request.values.get("initData")
            or ""
        )
        if init_data:
            res = auth.validate_init_data(
                init_data, app.config["BOT_TOKEN"],
                max_age_seconds=app.config["MAX_AGE"],
            )
            if res["ok"]:
                u = res["user"]
                return u.get("id"), u
            # initData presente pero invalido: no caer a dev salvo modo dev.
        if app.config["DEV"] and app.config["DEV_USER"]:
            try:
                dev_id = int(app.config["DEV_USER"])
            except (TypeError, ValueError):
                dev_id = app.config["DEV_USER"]
            return dev_id, {"id": dev_id, "first_name": "Dev", "username": "dev"}
        return None, None

    def require_auth(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            uid, user = _resolve_user()
            if uid is None:
                return jsonify({"error": "unauthorized"}), 401
            g.uid = uid
            g.user = user
            g.role = data.role_for(uid)
            return fn(*args, **kwargs)
        return wrapper

    def require_admin(fn):
        @functools.wraps(fn)
        @require_auth
        def wrapper(*args, **kwargs):
            if g.role != data.ROLE_ADMIN:
                return jsonify({"error": "forbidden"}), 403
            return fn(*args, **kwargs)
        return wrapper

    # --------------------------------------------------------------
    # SPA
    # --------------------------------------------------------------
    @app.route("/")
    def index():
        return send_from_directory(_STATIC_DIR, "index.html")

    @app.route("/healthz")
    def healthz():
        return jsonify({"ok": True})

    # --------------------------------------------------------------
    # API cliente (cualquier usuario autenticado)
    # --------------------------------------------------------------
    @app.route("/api/me")
    @require_auth
    def api_me():
        return jsonify(data.me(g.uid, user=g.user))

    @app.route("/api/signals")
    @require_auth
    def api_signals():
        limit = _clamp(request.args.get("limit"), default=20, lo=1, hi=100)
        return jsonify(data.client_signals(g.uid, limit=limit))

    @app.route("/api/track-record")
    @require_auth
    def api_track_record():
        return jsonify({"summary": data.track_record()})

    # --------------------------------------------------------------
    # API admin
    # --------------------------------------------------------------
    @app.route("/api/admin/overview")
    @require_admin
    def api_admin_overview():
        return jsonify(data.admin_overview())

    @app.route("/api/admin/signals")
    @require_admin
    def api_admin_signals():
        limit = _clamp(request.args.get("limit"), default=30, lo=1, hi=200)
        return jsonify(data.admin_signals(limit=limit))

    @app.route("/api/admin/stats")
    @require_admin
    def api_admin_stats():
        return jsonify(data.admin_stats())

    @app.route("/api/admin/subs")
    @require_admin
    def api_admin_subs():
        limit = _clamp(request.args.get("limit"), default=20, lo=1, hi=200)
        return jsonify(data.admin_subs(limit=limit))

    return app


def _clamp(raw, default, lo, hi):
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))
