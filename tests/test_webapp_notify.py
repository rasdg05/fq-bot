# -*- coding: utf-8 -*-
"""
webapp/notify.py — boton "Abrir app" y envio con boton. requests mockeado.
"""
import importlib

import pytest

import webapp.notify as notify


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("FQ_WEBAPP_URL", raising=False)
    monkeypatch.delenv("FQ_WEBAPP_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    importlib.reload(notify)
    yield


class _Resp:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


# ---- app_button ----
def test_button_none_without_url():
    assert notify.app_button() is None


def test_button_structure_with_url(monkeypatch):
    monkeypatch.setenv("FQ_WEBAPP_URL", "https://app.example.com")
    mk = notify.app_button(label="Abrir", view="signals")
    btn = mk["inline_keyboard"][0][0]
    assert btn["text"] == "Abrir"
    assert btn["web_app"]["url"] == "https://app.example.com?startapp=signals"


def test_button_no_view(monkeypatch):
    monkeypatch.setenv("FQ_WEBAPP_URL", "https://app.example.com")
    mk = notify.app_button()
    assert mk["inline_keyboard"][0][0]["web_app"]["url"] == "https://app.example.com"


def test_button_respects_existing_query(monkeypatch):
    monkeypatch.setenv("FQ_WEBAPP_URL", "https://app.example.com/?x=1")
    mk = notify.app_button(view="subs")
    assert mk["inline_keyboard"][0][0]["web_app"]["url"] == "https://app.example.com/?x=1&startapp=subs"


# ---- send_with_app_button ----
def test_send_includes_button(monkeypatch):
    monkeypatch.setenv("FQ_WEBAPP_URL", "https://app.example.com")
    monkeypatch.setenv("TELEGRAM_TOKEN", "T")
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    ok = notify.send_with_app_button(123, "hola", view="signals")
    assert ok is True
    assert "/botT/sendMessage" in captured["url"]
    assert captured["json"]["chat_id"] == 123
    assert captured["json"]["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"].endswith("startapp=signals")


def test_send_without_url_still_sends(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "T")
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _Resp(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    ok = notify.send_with_app_button(123, "hola", view="signals")
    assert ok is True
    assert "reply_markup" not in captured["json"]   # sin URL -> sin boton, pero envia


def test_send_no_token_returns_false(monkeypatch):
    # sin TELEGRAM_TOKEN ni FQ_WEBAPP_BOT_TOKEN
    called = {"n": 0}

    def fake_post(*a, **k):
        called["n"] += 1
        return _Resp(200)

    monkeypatch.setattr(notify.requests, "post", fake_post)
    ok = notify.send_with_app_button(1, "x")
    assert ok is False
    assert called["n"] == 0   # ni siquiera intenta
