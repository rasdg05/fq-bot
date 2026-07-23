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

# Tipografía propia self-hosteada (Fraunces display + Hanken Grotesk texto). Allowlist
# explícito por nombre exacto -- nunca por path del cliente (sin traversal). woff2
# inmutable con cache de un año: la marca no se ve genérica y no re-descarga por carga.
FONTS_DIR = os.path.join(ROOT, "assets", "fonts")
STATIC_FONTS = {
    "/fonts/fraunces-600.woff2": "fraunces-600.woff2",
    "/fonts/hanken-400.woff2": "hanken-400.woff2",
    "/fonts/hanken-500.woff2": "hanken-500.woff2",
    "/fonts/hanken-700.woff2": "hanken-700.woff2",
}

# Imagen de marca (render 3D de la ola-koru, fondo removido). Mismo criterio que las
# fuentes: allowlist exacto + cache inmutable, servida como webp con alfa.
IMG_DIR = os.path.join(ROOT, "assets", "img")
STATIC_IMAGES = {
    "/assets/koru-3d.webp": ("koru-3d.webp", "image/webp"),
}

# mismo handle del bot que usan cockpit.html/cockpit.py para los CTA del embudo.
_BOT = os.environ.get("FQ_VIP_BOT_USERNAME", "").strip().lstrip("@")

# --- PWA: manifest + service worker + icono. Hace la plataforma instalable en
# móvil/escritorio y habilita notificaciones nativas (alertas VIP, pista 1D). ---
_ICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'>"
    "<rect width='512' height='512' rx='104' fill='#F3EFE4'/>"
    "<g transform='translate(98,98) scale(2.2)'><path d=\"M 75.81 84.01 C 76.09 84.58 76.92 83.87 77.49 83.88 C 78.07 83.90 78.66 83.96 79.24 84.09 C 79.82 84.22 80.41 84.41 80.98 84.65 C 81.56 84.90 82.13 85.21 82.66 85.58 C 83.20 85.94 83.72 86.37 84.20 86.85 C 84.68 87.33 85.13 87.88 85.53 88.47 C 85.93 89.06 86.29 89.70 86.58 90.39 C 86.87 91.07 87.11 91.80 87.28 92.56 C 87.45 93.32 87.55 94.13 87.58 94.94 C 87.60 95.76 87.56 96.61 87.42 97.45 C 87.29 98.30 87.08 99.17 86.78 100.01 C 86.47 100.86 86.09 101.72 85.61 102.54 C 85.14 103.35 84.58 104.17 83.93 104.92 C 83.28 105.68 82.54 106.41 81.72 107.07 C 80.90 107.73 79.99 108.35 79.02 108.88 C 78.04 109.41 76.98 109.88 75.87 110.25 C 74.75 110.61 73.56 110.90 72.32 111.07 C 71.09 111.23 69.79 111.31 68.47 111.25 C 67.16 111.19 65.78 111.02 64.42 110.71 C 63.05 110.40 61.65 109.96 60.28 109.38 C 58.91 108.79 57.52 108.07 56.19 107.20 C 54.86 106.32 53.54 105.31 52.32 104.14 C 51.09 102.97 49.90 101.65 48.83 100.19 C 47.76 98.73 46.75 97.11 45.90 95.37 C 45.06 93.63 44.30 91.74 43.74 89.74 C 43.18 87.74 42.76 85.60 42.53 83.39 C 42.29 81.17 42.22 78.85 42.33 76.45 C 42.45 74.05 42.68 71.54 43.22 68.99 C 43.75 66.44 44.48 63.79 45.53 61.17 C 46.57 58.54 47.87 55.84 49.49 53.23 C 51.12 50.62 53.03 47.98 55.29 45.52 C 57.54 43.05 60.11 40.62 63.01 38.44 C 65.91 36.26 69.15 34.18 72.67 32.45 C 76.20 30.72 80.07 29.17 84.17 28.06 C 88.27 26.95 92.70 26.11 97.28 25.78 C 101.85 25.45 107.69 26.86 111.62 26.09 C 115.56 25.32 121.99 22.65 120.90 21.15 C 119.82 19.64 110.35 17.93 105.12 17.08 C 99.90 16.23 94.62 15.91 89.54 16.03 C 84.46 16.15 79.42 16.79 74.65 17.81 C 69.88 18.84 65.24 20.35 60.92 22.18 C 56.61 24.02 52.50 26.29 48.76 28.81 C 45.03 31.33 41.57 34.24 38.52 37.31 C 35.46 40.38 32.74 43.77 30.44 47.24 C 28.14 50.70 26.21 54.41 24.71 58.11 C 23.20 61.81 22.09 65.66 21.39 69.43 C 20.69 73.19 20.40 77.03 20.51 80.68 C 20.61 84.34 21.20 87.96 22.01 91.35 C 22.83 94.74 24.01 98.01 25.39 101.02 C 26.77 104.04 28.47 106.87 30.31 109.43 C 32.16 111.98 34.26 114.31 36.44 116.36 C 38.62 118.40 41.01 120.19 43.42 121.69 C 45.82 123.20 48.37 124.42 50.88 125.38 C 53.39 126.34 55.98 127.02 58.49 127.45 C 61.00 127.89 63.53 128.04 65.94 127.99 C 68.35 127.94 70.73 127.62 72.96 127.13 C 75.18 126.65 77.33 125.92 79.31 125.07 C 81.29 124.21 83.15 123.15 84.82 122.00 C 86.50 120.85 88.03 119.53 89.38 118.16 C 90.72 116.80 91.90 115.30 92.90 113.79 C 93.90 112.28 94.72 110.69 95.37 109.11 C 96.02 107.54 96.49 105.92 96.81 104.35 C 97.13 102.77 97.28 101.19 97.29 99.69 C 97.30 98.18 97.15 96.69 96.90 95.30 C 96.64 93.91 96.23 92.56 95.75 91.33 C 95.26 90.09 94.65 88.92 93.98 87.87 C 93.32 86.82 92.55 85.85 91.74 85.00 C 90.94 84.15 90.06 83.40 89.18 82.76 C 88.29 82.12 87.35 81.59 86.42 81.15 C 85.49 80.72 84.53 80.40 83.60 80.17 C 82.67 79.93 81.73 79.80 80.84 79.75 C 79.94 79.70 79.06 79.75 78.23 79.86 C 77.40 79.97 76.26 79.73 75.86 80.42 C 75.46 81.11 75.54 83.43 75.81 84.01 Z\" fill='#0B6B6E'/></g>"
    "</svg>")

_MANIFEST = json.dumps({
    "name": "Marea", "short_name": "Marea", "start_url": "/",
    "display": "standalone", "background_color": "#F5F3EC",
    "theme_color": "#0B6B6E", "description": "Copiloto de mercado en español, en vivo",
    "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml",
               "purpose": "any maskable"}],
})

# Service worker: cachea el shell para carga offline y arranque instantáneo.
# No-crítico: si el fetch falla, cae a la red. Versión en el nombre del cache
# para invalidar en cada deploy del shell.
_SW_JS = """
const CACHE = 'fq-shell-v1';
const SHELL = ['/', '/icon.svg', '/manifest.webmanifest'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks =>
    Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  // datos siempre frescos de la red; el shell puede venir del cache
  if (u.pathname.endsWith('.json')) return;
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});
""".lstrip()


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
<title>Marea · Verificación</title>
<style>
body{{margin:0;background:#F5F3EC;color:#12262A;font:15px/1.6 system-ui,-apple-system,"Segoe UI",Arial,sans-serif;
  display:flex;min-height:100vh;align-items:center;justify-content:center;padding:24px}}
.card{{max-width:440px;border:1px solid rgba(11,107,110,.22);border-radius:16px;background:#FFFFFF;
  padding:32px 28px;text-align:center;box-shadow:0 10px 30px rgba(18,38,42,.07)}}
.card b{{color:#0B6B6E;letter-spacing:.14em;font-size:11px;text-transform:uppercase;display:block;margin-bottom:14px}}
h1{{font-size:22px;margin:0 0 12px;font-family:ui-serif,Georgia,"Times New Roman",serif;font-weight:600}}
p{{color:#5D6E6D;margin:0 0 8px}}
.btn{{display:inline-block;text-decoration:none;font-weight:700;font-size:12px;letter-spacing:.06em;
  text-transform:uppercase;padding:12px 20px;border-radius:10px}}
.btn.gold{{background:#0B6B6E;color:#fff}}
.btn.ghost{{background:transparent;color:#0B6B6E;border:1px solid rgba(11,107,110,.42);margin-top:10px}}
a{{color:#0B6B6E}}
</style></head><body>
<div class="card"><b>Marea</b><h1>{heading}</h1>{body}</div>
</body></html>""").format(heading=heading, body=body)


class _H(BaseHTTPRequestHandler):
    server_version = "fq-cockpit"

    def _send(self, code, body, ctype, cache="no-store"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
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
            elif path == "/manifest.webmanifest":
                self._send(200, _MANIFEST, "application/manifest+json")
            elif path == "/sw.js":
                self._send(200, _SW_JS, "text/javascript")
            elif path == "/icon.svg":
                self._send(200, _ICON_SVG, "image/svg+xml")
            elif path == "/health":
                self._send(200, "ok", "text/plain")
            elif path in STATIC_PDFS:
                try:
                    with open(os.path.join(MARKETING_DIR, STATIC_PDFS[path]), "rb") as fh:
                        self._send(200, fh.read(), "application/pdf")
                except FileNotFoundError:
                    self._send(404, "guía no encontrada", "text/plain")
            elif path in STATIC_FONTS:
                try:
                    with open(os.path.join(FONTS_DIR, STATIC_FONTS[path]), "rb") as fh:
                        self._send(200, fh.read(), "font/woff2",
                                   cache="public, max-age=31536000, immutable")
                except FileNotFoundError:
                    self._send(404, "fuente no encontrada", "text/plain")
            elif path in STATIC_IMAGES:
                fname, ctype = STATIC_IMAGES[path]
                try:
                    with open(os.path.join(IMG_DIR, fname), "rb") as fh:
                        self._send(200, fh.read(), ctype,
                                   cache="public, max-age=31536000, immutable")
                except FileNotFoundError:
                    self._send(404, "imagen no encontrada", "text/plain")
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
