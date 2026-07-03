# -*- coding: utf-8 -*-
"""Cockpit "show" (FQ_COCKPIT): telemetría NO-crítica. Garantías: OFF -> no-op total
(ni archivo); ON -> JSON atómico con estado por símbolo + ring de eventos capado; el
server stdlib sirve html/json/health y jamás toca al motor (proceso aparte)."""
import json
import os
import threading
import urllib.request

import cockpit


def _reset(tmp_path, monkeypatch, enabled=True):
    monkeypatch.setattr(cockpit, "_ENABLED", enabled)
    monkeypatch.setattr(cockpit, "_PATH", str(tmp_path / "cockpit.json"))
    monkeypatch.setattr(cockpit, "_last_write", [0.0])
    cockpit._state["symbols"].clear()
    cockpit._state["events"].clear()


def test_off_es_noop_total(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch, enabled=False)
    cockpit.tick("SOL/USDT", price=150.0, closes=[1, 2, 3])
    cockpit.log_event("SOL/USDT", "fire", "x")
    assert not os.path.exists(str(tmp_path / "cockpit.json"))
    assert cockpit._state["symbols"] == {} and cockpit._state["events"] == []


def test_on_escribe_json_atomico(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    cockpit.tick("SOL/USDT", ts="2026-07-03", price=152.31,
                 closes=[150 + i * 0.1 for i in range(80)],
                 killzone="ny_am_kz", counts={"fire": 3}, n_open=1)
    d = json.load(open(str(tmp_path / "cockpit.json")))
    s = d["symbols"]["SOL"]
    assert s["price"] == 152.31 and s["killzone"] == "ny_am_kz"
    assert len(s["spark"]) == 48 and s["counts"]["fire"] == 3 and s["open"] == 1
    # irrev/funding son best-effort (lazy import puede faltar local): si están, sanos
    if "irrev" in s:
        assert 0.0 <= s["irrev"] <= 5.0


def test_ring_de_eventos_capado(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    for i in range(80):
        cockpit.log_event("BTC/USDT", "fire", "evento %d" % i)
    d = json.load(open(str(tmp_path / "cockpit.json")))
    assert len(d["events"]) == 60                      # ring capado
    assert d["events"][-1]["text"].endswith("79")      # conserva los últimos


def test_server_sirve_html_json_health(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("FQ_COCKPIT_PATH", str(tmp_path / "cockpit.json"))
    import tools.cockpit_server as srv
    importlib.reload(srv)
    httpd = __import__("http.server", fromlist=["ThreadingHTTPServer"]).ThreadingHTTPServer(
        ("127.0.0.1", 0), srv._H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    try:
        assert urllib.request.urlopen(base + "/health", timeout=5).status == 200
        r = urllib.request.urlopen(base + "/cockpit.json", timeout=5)
        assert r.status == 200 and "symbols" in json.loads(r.read().decode())
        r2 = urllib.request.urlopen(base + "/", timeout=5)
        assert r2.status == 200 and b"COCKPIT" in r2.read()
    finally:
        httpd.shutdown()
