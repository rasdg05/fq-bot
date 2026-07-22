#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cockpit_server — servidor NO-CRÍTICO de la interfaz "show" (FQ_COCKPIT=1).

Hijo OPCIONAL del launcher (critical=False): si muere, el launcher lo deja morir y
el bot VIP sigue intacto — la regla de RasDG ("que por la interfaz jamás se caiga la
señal"). stdlib puro (http.server), cero dependencias, cero cómputo: sirve DOS cosas:

  GET /              -> cockpit.html (la interfaz; archivo estático del repo)
  GET /cockpit.json  -> el JSON que el motor deja caer (cockpit.py, write atómico)
  GET /health        -> ok
  GET /<guia>.pdf    -> guías gratis (lead magnets), allowlist de MEMORY/marketing/
  POST /waitlist     -> {"email": "..."} -> guarda + manda verificación (waitlist.py)
  GET /verify        -> ?token=... marca verificado y entrega la guía + Telegram

Puerto: FQ_COCKPIT_PORT > PORT > 8080. En Railway: exponer el puerto en el servicio
(Settings -> Networking -> Generate Domain) y la URL pública muestra el cockpit.
"""
import json
import os
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "cockpit.html")
STATE = os.environ.get("FQ_COCKPIT_PATH") or (
    "/data/cockpit.json" if os.path.isdir("/data") else "data/cockpit.json")
# Capa de ANÁLISIS (oro/Nasdaq, no señales) — la escribe tools/analysis_feeder.py en
# OTRO proceso. Se MEZCLA aquí al servir: el motor y el feeder nunca comparten estado,
# así por la interfaz jamás se cae la señal. Si el archivo no está, se sirve solo el motor.
EXTRA = os.environ.get("FQ_ANALYSIS_EXTRA_PATH") or (
    "/data/cockpit_extra.json" if os.path.isdir("/data") else "data/cockpit_extra.json")
# Calendario económico (lo escribe analysis_feeder desde el feed gratis de ForexFactory).
CALENDAR = os.environ.get("FQ_CALENDAR_PATH") or (
    "/data/cockpit_calendar.json" if os.path.isdir("/data") else "data/cockpit_calendar.json")

# waitlist.py vive en la raíz del repo, no en tools/ -- al correr este archivo
# directo (python tools/cockpit_server.py, como lo lanza launcher.py) sys.path[0]
# es tools/, no la raíz. Sin esto el import falla incluso con el módulo presente.
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
try:
    import waitlist
except Exception:          # el resto del server debe seguir sirviendo igual
    waitlist = None

# Guías gratis (lead magnets, PR "plataforma completa"): allowlist explícito de
# archivos estáticos servidos por su nombre exacto -- nunca por path del cliente,
# para no abrir un directorio-listing ni traversal.
MARKETING_DIR = os.path.join(ROOT, "MEMORY", "marketing")
STATIC_PDFS = {
    "/guia-3-reglas.pdf": "guia-3-reglas.pdf",
    "/como-se-construye-una-ventaja.pdf": "como-se-construye-una-ventaja.pdf",
}

# mismo handle del bot que usan cockpit.html/cockpit.py para los CTA del embudo.
_BOT = os.environ.get("FQ_VIP_BOT_USERNAME", "").strip().lstrip("@")


def _merged_state():
    """Estado del panel = motor (cripto, cockpit.json) + análisis (oro/Nasdaq,
    cockpit_extra.json), mezclados al servir. Desacoplado y defensivo: si el motor
    aún no escribe, base vacía; si el feeder de análisis no está, se omite. Un
    archivo corrupto de una capa jamás tumba la otra."""
    state = {"symbols": {}, "events": [], "note": "sin telemetría aún"}
    try:
        with open(STATE) as fh:
            base = json.load(fh)
        if isinstance(base, dict):
            state = base
            state.setdefault("symbols", {})
            state.setdefault("events", [])
    except Exception:
        pass
    try:
        with open(EXTRA) as fh:
            extra = json.load(fh)
        exs = (extra or {}).get("symbols") or {}
        if exs:
            # el análisis se suma; no pisa un símbolo del motor si por algo coincidiera
            for k, v in exs.items():
                state["symbols"].setdefault(k, v)
    except Exception:
        pass
    return state


def _verify_page(status):
    """Página de confirmación server-rendered (no depende de cockpit.html):
    entrega la guía + el link de Telegram apenas se verifica el correo."""
    tg = ("https://t.me/" + _BOT) if _BOT else "#"
    if status in ("ok", "already"):
        heading = "Correo verificado." if status == "ok" else "Ya estabas verificado."
        body = (
            '<p>Aquí tienes tu guía gratis y tu acceso al motor en vivo.</p>'
            '<p style="margin:22px 0"><a class="btn gold" href="/guia-3-reglas.pdf" target="_blank" '
            'rel="noopener">Descargar guía →</a></p>'
            '<p><a class="btn ghost" href="{tg}" target="_blank" rel="noopener">Únete gratis en Telegram →</a></p>'
        ).format(tg=tg)
    elif status == "expired":
        heading = "Este link expiró."
        body = "<p>Vuelve al sitio y regístrate de nuevo — te mandamos uno nuevo.</p>"
    else:
        heading = "Link inválido."
        body = "<p>Revisa que copiaste el link completo, o vuelve al sitio y regístrate de nuevo.</p>"
    return ("""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FQ CAPITAL · Verificación</title>
<style>
body{{margin:0;background:#050705;color:#f4f2ea;font:15px/1.6 -apple-system,"Helvetica Neue",Arial,sans-serif;
  display:flex;min-height:100vh;align-items:center;justify-content:center;padding:24px}}
.card{{max-width:440px;border:1px solid rgba(201,162,39,.22);border-radius:12px;background:rgba(12,15,12,.92);
  padding:32px 28px;text-align:center}}
.card b{{color:#d4af37;letter-spacing:.2em;font-size:11px;text-transform:uppercase;display:block;margin-bottom:14px}}
h1{{font-size:20px;margin:0 0 12px}}
p{{color:#b9b6a6;margin:0 0 8px}}
.btn{{display:inline-block;text-decoration:none;font-weight:700;font-size:12px;letter-spacing:.06em;
  text-transform:uppercase;padding:12px 20px;border-radius:8px}}
.btn.gold{{background:linear-gradient(180deg,#e7c452,#c9a227);color:#0a0c0a}}
.btn.ghost{{background:transparent;color:#d4af37;border:1px solid rgba(212,175,55,.42);margin-top:10px}}
a{{color:#d4af37}}
</style></head><body>
<div class="card"><b>FQ CAPITAL</b><h1>{heading}</h1>{body}</div>
</body></html>""").format(heading=heading, body=body)


class _H(BaseHTTPRequestHandler):
    server_version = "fq-cockpit"

    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            path = self.path.split("?")[0]
            if path in ("/", "/index.html", "/cockpit", "/cockpit.html"):
                try:
                    with open(HTML, "rb") as fh:
                        self._send(200, fh.read(), "text/html; charset=utf-8")
                except FileNotFoundError:
                    self._send(404, "cockpit.html no encontrado", "text/plain")
            elif path == "/cockpit.json":
                self._send(200, json.dumps(_merged_state()), "application/json")
            elif path == "/calendar.json":
                try:
                    with open(CALENDAR, "rb") as fh:
                        self._send(200, fh.read(), "application/json")
                except Exception:
                    self._send(200, json.dumps({"events": []}), "application/json")
            elif path == "/health":
                self._send(200, "ok", "text/plain")
            elif path in STATIC_PDFS:
                try:
                    with open(os.path.join(MARKETING_DIR, STATIC_PDFS[path]), "rb") as fh:
                        self._send(200, fh.read(), "application/pdf")
                except FileNotFoundError:
                    self._send(404, "guía no encontrada", "text/plain")
            elif path == "/verify":
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                token = (qs.get("token") or [""])[0]
                status = waitlist.verify(token) if waitlist else "invalid"
                self._send(200, _verify_page(status), "text/html; charset=utf-8")
            else:
                self._send(404, "not found", "text/plain")
        except Exception:
            pass                      # un cliente roto jamás tumba el server

    def do_POST(self):
        try:
            path = self.path.split("?")[0]
            if path != "/waitlist":
                self._send(404, "not found", "text/plain")
                return
            if waitlist is None:
                self._send(503, json.dumps({"ok": False, "error": "no disponible"}),
                           "application/json")
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 4096:
                self._send(400, json.dumps({"ok": False, "error": "payload inválido"}),
                           "application/json")
                return
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = {}
            ip = self.client_address[0] if self.client_address else "?"
            if waitlist.rate_limited(ip):
                self._send(429, json.dumps({"ok": False, "error": "demasiados intentos, prueba en un rato"}),
                           "application/json")
                return
            base = "{}://{}".format("https", self.headers.get("Host", ""))
            result = waitlist.subscribe(data.get("email", ""), base_url=base)
            self._send(200 if result.get("ok") else 400, json.dumps(result), "application/json")
        except Exception:
            pass                      # un cliente roto jamás tumba el server

    def log_message(self, fmt, *args):  # silencio: sin spam al stdout del launcher
        pass


def main():
    port = int(os.environ.get("FQ_COCKPIT_PORT") or os.environ.get("PORT") or 8080)
    srv = ThreadingHTTPServer(("0.0.0.0", port), _H)
    sys.stdout.write("[cockpit] sirviendo en :%d (html=%s, state=%s)\n"
                     % (port, os.path.exists(HTML), STATE))
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
