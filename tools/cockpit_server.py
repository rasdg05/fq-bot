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

Puerto: FQ_COCKPIT_PORT > PORT > 8080. En Railway: exponer el puerto en el servicio
(Settings -> Networking -> Generate Domain) y la URL pública muestra el cockpit.
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "cockpit.html")
STATE = os.environ.get("FQ_COCKPIT_PATH") or (
    "/data/cockpit.json" if os.path.isdir("/data") else "data/cockpit.json")

# Guías gratis (lead magnets, PR "plataforma completa"): allowlist explícito de
# archivos estáticos servidos por su nombre exacto -- nunca por path del cliente,
# para no abrir un directorio-listing ni traversal.
MARKETING_DIR = os.path.join(ROOT, "MEMORY", "marketing")
STATIC_PDFS = {
    "/guia-3-reglas.pdf": "guia-3-reglas.pdf",
    "/como-se-construye-una-ventaja.pdf": "como-se-construye-una-ventaja.pdf",
}


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
                try:
                    with open(STATE, "rb") as fh:
                        self._send(200, fh.read(), "application/json")
                except FileNotFoundError:
                    self._send(200, json.dumps({"symbols": {}, "events": [],
                                                "note": "sin telemetría aún"}),
                               "application/json")
            elif path == "/health":
                self._send(200, "ok", "text/plain")
            elif path in STATIC_PDFS:
                try:
                    with open(os.path.join(MARKETING_DIR, STATIC_PDFS[path]), "rb") as fh:
                        self._send(200, fh.read(), "application/pdf")
                except FileNotFoundError:
                    self._send(404, "guía no encontrada", "text/plain")
            else:
                self._send(404, "not found", "text/plain")
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
