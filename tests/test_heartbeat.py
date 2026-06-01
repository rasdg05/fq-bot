# -*- coding: utf-8 -*-
"""Heartbeat / watchdog: beat, age, staleness."""
import importlib


def _fresh_heartbeat(tmp_path, monkeypatch):
    monkeypatch.setenv("FQ_HEARTBEAT_DIR", str(tmp_path / "hb"))
    from ops import heartbeat
    importlib.reload(heartbeat)
    return heartbeat


def test_beat_then_not_stale(tmp_path, monkeypatch):
    hb = _fresh_heartbeat(tmp_path, monkeypatch)
    hb.beat("vip")
    assert hb.age_seconds("vip") is not None
    assert hb.age_seconds("vip") < 5
    assert hb.is_stale("vip", 60) is False


def test_never_beat_is_not_stale(tmp_path, monkeypatch):
    hb = _fresh_heartbeat(tmp_path, monkeypatch)
    # Un componente que nunca latio no se marca stale (aun no arranco).
    assert hb.age_seconds("public") is None
    assert hb.is_stale("public", 60) is False


def test_old_beat_is_stale(tmp_path, monkeypatch):
    import os
    import time
    hb = _fresh_heartbeat(tmp_path, monkeypatch)
    hb.beat("vip")
    # Envejecer el archivo artificialmente.
    path = hb._path("vip")
    old = time.time() - 3600
    os.utime(path, (old, old))
    assert hb.is_stale("vip", 60) is True
