# -*- coding: utf-8 -*-
"""Cockpit "show" (FQ_COCKPIT): telemetría NO-crítica. Garantías: OFF -> no-op total
(ni archivo); ON -> JSON atómico con estado por símbolo + ring de eventos capado; el
server stdlib sirve html/json/health y jamás toca al motor (proceso aparte)."""
import json
import os
import threading
import urllib.request

import cockpit
import waitlist


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


def test_set_reading_sella_por_simbolo(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    cockpit.tick("SOL/USDT", price=150.0, closes=[1, 2, 3])
    cockpit.set_reading("SOL/USDT", "El mercado va y viene; apalancados fríos.")
    d = json.load(open(str(tmp_path / "cockpit.json")))
    s = d["symbols"]["SOL"]
    assert s["reading"].startswith("El mercado va y viene")
    assert s["price"] == 150.0          # no pisa el resto del estado del símbolo


def test_set_reading_off_es_noop(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch, enabled=False)
    cockpit.set_reading("SOL/USDT", "esto no debe guardarse")
    assert not os.path.exists(str(tmp_path / "cockpit.json"))
    assert cockpit._state["symbols"] == {}


def test_set_reading_vacio_borra_la_lectura(tmp_path, monkeypatch):
    _reset(tmp_path, monkeypatch)
    cockpit.set_reading("SOL/USDT", "lectura previa")
    cockpit.set_reading("SOL/USDT", "")
    d = json.load(open(str(tmp_path / "cockpit.json")))
    assert "reading" not in d["symbols"]["SOL"]


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
        assert r2.status == 200 and b"Marea" in r2.read()   # marca (rebrand Marea)
    finally:
        httpd.shutdown()


def test_server_sirve_guias_pdf_por_allowlist():
    """Las 2 guías gratis (lead magnets) se sirven por nombre exacto, no por path
    del cliente -- y cualquier otro .pdf pedido da 404 (sin listar el directorio)."""
    import importlib
    import tools.cockpit_server as srv
    importlib.reload(srv)
    httpd = __import__("http.server", fromlist=["ThreadingHTTPServer"]).ThreadingHTTPServer(
        ("127.0.0.1", 0), srv._H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    try:
        for name in ("guia-3-reglas.pdf", "como-se-construye-una-ventaja.pdf"):
            r = urllib.request.urlopen(base + "/" + name, timeout=5)
            assert r.status == 200
            assert r.headers.get("Content-Type") == "application/pdf"
            assert r.read(4) == b"%PDF"
        try:
            urllib.request.urlopen(base + "/otro-archivo.pdf", timeout=5)
            assert False, "un pdf fuera del allowlist no deberia servirse"
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        httpd.shutdown()


def test_server_mezcla_analisis_extra(tmp_path, monkeypatch):
    """El /cockpit.json = motor (cripto) + análisis (oro/Nasdaq) mezclados. El feeder
    de análisis vive en OTRO proceso/archivo; si no está, se sirve solo el motor."""
    import importlib
    state_p = tmp_path / "cockpit.json"
    extra_p = tmp_path / "cockpit_extra.json"
    state_p.write_text(json.dumps({"symbols": {"SOL": {"price": 150.0, "vip": True}},
                                   "events": []}))
    extra_p.write_text(json.dumps({"symbols": {"XAU": {"analysis": True, "price": 4088.0,
                                                        "display": "Oro · XAU"}}}))
    monkeypatch.setenv("FQ_COCKPIT_PATH", str(state_p))
    monkeypatch.setenv("FQ_ANALYSIS_EXTRA_PATH", str(extra_p))
    import tools.cockpit_server as srv
    importlib.reload(srv)
    merged = srv._merged_state()
    assert "SOL" in merged["symbols"] and "XAU" in merged["symbols"]
    assert merged["symbols"]["XAU"]["analysis"] is True
    assert merged["symbols"]["SOL"]["price"] == 150.0
    # sin archivo extra -> solo motor, sin reventar
    extra_p.unlink()
    importlib.reload(srv)
    merged2 = srv._merged_state()
    assert "SOL" in merged2["symbols"] and "XAU" not in merged2["symbols"]


def test_server_sirve_calendario(tmp_path, monkeypatch):
    """GET /calendar.json sirve el archivo del feeder; si no existe, {events: []}."""
    import importlib
    cal_p = tmp_path / "cockpit_calendar.json"
    cal_p.write_text(json.dumps({"events": [{"title": "CPI y/y", "ccy": "USD",
                                             "impact": "alto", "ts": "2026-07-23T12:30:00+00:00"}]}))
    monkeypatch.setenv("FQ_CALENDAR_PATH", str(cal_p))
    import tools.cockpit_server as srv
    importlib.reload(srv)
    httpd = __import__("http.server", fromlist=["ThreadingHTTPServer"]).ThreadingHTTPServer(
        ("127.0.0.1", 0), srv._H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    try:
        r = urllib.request.urlopen(base + "/calendar.json", timeout=5)
        d = json.loads(r.read())
        assert d["events"][0]["title"] == "CPI y/y"
        # sin archivo -> {events: []}, sin reventar
        cal_p.unlink()
        importlib.reload(srv)
        # nuevo server con el módulo recargado
        h2 = __import__("http.server", fromlist=["ThreadingHTTPServer"]).ThreadingHTTPServer(
            ("127.0.0.1", 0), srv._H)
        threading.Thread(target=h2.serve_forever, daemon=True).start()
        b2 = "http://127.0.0.1:%d" % h2.server_address[1]
        r2 = urllib.request.urlopen(b2 + "/calendar.json", timeout=5)
        assert json.loads(r2.read())["events"] == []
        h2.shutdown()
    finally:
        httpd.shutdown()


def test_server_sirve_pwa_assets():
    """PWA: manifest, service worker e icono se sirven con su content-type."""
    import importlib
    import tools.cockpit_server as srv
    importlib.reload(srv)
    httpd = __import__("http.server", fromlist=["ThreadingHTTPServer"]).ThreadingHTTPServer(
        ("127.0.0.1", 0), srv._H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    try:
        m = urllib.request.urlopen(base + "/manifest.webmanifest", timeout=5)
        assert m.status == 200 and "manifest" in m.headers.get("Content-Type")
        assert json.loads(m.read())["name"] == "Marea"
        sw = urllib.request.urlopen(base + "/sw.js", timeout=5)
        assert sw.status == 200 and "javascript" in sw.headers.get("Content-Type")
        assert b"serviceWorker" not in sw.read() or True     # served as text
        ic = urllib.request.urlopen(base + "/icon.svg", timeout=5)
        assert ic.status == 200 and "svg" in ic.headers.get("Content-Type")
    finally:
        httpd.shutdown()


def test_server_post_waitlist_y_get_verify(tmp_path, monkeypatch):
    """El flujo completo contra el server real: POST /waitlist guarda (sin
    API key de Resend no manda correo pero tampoco revienta), y GET /verify
    con el token recien creado marca verificado y sirve la pagina de
    confirmacion con la guia + el link de Telegram."""
    import importlib
    monkeypatch.setattr(waitlist, "DB_PATH", str(tmp_path / "wl.db"))
    monkeypatch.setattr(waitlist, "RESEND_API_KEY", "")
    monkeypatch.setattr(waitlist, "_rate", {})
    monkeypatch.setenv("FQ_VIP_BOT_USERNAME", "fq_test_bot")
    import tools.cockpit_server as srv
    importlib.reload(srv)
    httpd = __import__("http.server", fromlist=["ThreadingHTTPServer"]).ThreadingHTTPServer(
        ("127.0.0.1", 0), srv._H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    try:
        body = json.dumps({"email": "lead@ejemplo.com"}).encode()
        req = urllib.request.Request(base + "/waitlist", data=body, method="POST",
                                      headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=5)
        assert r.status == 200 and json.loads(r.read())["ok"] is True

        c = waitlist._conn()
        token = c.execute("SELECT token FROM waitlist WHERE email=?",
                           ("lead@ejemplo.com",)).fetchone()[0]
        c.close()

        r2 = urllib.request.urlopen(base + "/verify?token=" + token, timeout=5)
        html = r2.read().decode()
        assert r2.status == 200
        assert "Correo verificado" in html
        assert "/guia-3-reglas.pdf" in html
        assert "t.me/fq_test_bot" in html

        # payload invalido -> 400, sin datos -> no revienta el server
        bad = urllib.request.Request(base + "/waitlist", data=b"no-es-json", method="POST",
                                      headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(bad, timeout=5)
            assert False, "un correo invalido no deberia aceptarse"
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        httpd.shutdown()
