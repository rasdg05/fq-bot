# -*- coding: utf-8 -*-
"""
ops/maintenance.py — las alertas de salud llevan boton "Abrir app" y, si el
boton falla (400 por dominio no configurado), reintentan sin el para no perder
el aviso. requests mockeado.
"""
import json

import pytest

from ops import maintenance


class _Resp:
    def __init__(self, status_code=200):
        self.status_code = status_code


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.delenv("FQ_WEBAPP_URL", raising=False)
    yield


def test_health_alert_has_button(monkeypatch):
    monkeypatch.setenv("FQ_WEBAPP_URL", "https://app.example.com")
    posts = []

    def fake_post(url, data=None, timeout=None):
        posts.append(data)
        return _Resp(200)

    monkeypatch.setattr(maintenance.requests, "post", fake_post)
    maintenance._dm_admin("vip caido", view="health")
    assert len(posts) == 1
    markup = json.loads(posts[0]["reply_markup"])
    assert markup["inline_keyboard"][0][0]["web_app"]["url"].endswith("startapp=health")


def test_button_400_retries_without_button(monkeypatch):
    monkeypatch.setenv("FQ_WEBAPP_URL", "https://app.example.com")
    posts = []

    def fake_post(url, data=None, timeout=None):
        posts.append(dict(data))
        # primer intento (con boton) -> 400; segundo -> 200
        return _Resp(400) if "reply_markup" in data else _Resp(200)

    monkeypatch.setattr(maintenance.requests, "post", fake_post)
    maintenance._dm_admin("vip caido", view="health")
    assert len(posts) == 2
    assert "reply_markup" in posts[0]
    assert "reply_markup" not in posts[1]   # reintento sin boton


def test_no_button_without_url(monkeypatch):
    posts = []

    def fake_post(url, data=None, timeout=None):
        posts.append(data)
        return _Resp(200)

    monkeypatch.setattr(maintenance.requests, "post", fake_post)
    maintenance._dm_admin("vip caido", view="health")
    assert len(posts) == 1
    assert "reply_markup" not in posts[0]


def test_no_post_without_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    called = {"n": 0}

    def fake_post(*a, **k):
        called["n"] += 1
        return _Resp(200)

    monkeypatch.setattr(maintenance.requests, "post", fake_post)
    maintenance._dm_admin("x", view="health")
    assert called["n"] == 0
