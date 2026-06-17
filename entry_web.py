#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  FQ WEB / MINI APP - entrypoint
  by RasDG_Sol + Claude

  Sirve la Mini App de Telegram (panel admin + app cliente) sobre el mismo
  container que el bot VIP, para leer el mismo /data/fq_ledger.db.

  SEGURIDAD OPERATIVA: el launcher reinicia TODO el container si cualquier hijo
  muere. Este proceso por tanto NUNCA sale por un fallo de la web: si no puede
  arrancar (o el server cae), registra el error y queda en idle latiendo. Asi un
  bug de la app jamas tumba el motor de senales en vivo.

  Desactivable en caliente con FQ_WEBAPP_ENABLED=0 (queda idle, no sale).

  ENV:
    PORT                 puerto a exponer (Railway lo inyecta; default 8080)
    FQ_WEBAPP_ENABLED    '0' para no servir (idle). Default: on.
    FQ_WEBAPP_BOT_TOKEN  token para validar initData (default TELEGRAM_TOKEN)
    FQ_WEBAPP_URL        url https publica de la Mini App (para deep-links)
================================================================================
"""
import os
import sys
import time
import logging
import threading

try:
    import fq_logging
    fq_logging.setup()
except Exception:
    logging.basicConfig(level=logging.INFO)
log = logging.getLogger("fq_web")

HEARTBEAT_SEC = 60


def _truthy(v):
    return str(v if v is not None else "1").strip().lower() in ("1", "true", "yes", "on")


def _heartbeat_loop():
    try:
        from ops import heartbeat as hb
    except Exception:
        hb = None
    while True:
        if hb is not None:
            try:
                hb.beat("web")
            except Exception:
                pass
        time.sleep(HEARTBEAT_SEC)


def _idle_forever(reason):
    """Mantiene el proceso vivo sin servir, para no gatillar el restart del
    launcher. Late 'web' para que el panel marque el estado real."""
    log.warning("FQ web en IDLE: %s (no se sirve la Mini App)", reason)
    _heartbeat_loop()  # bloquea para siempre


def main():
    if not _truthy(os.environ.get("FQ_WEBAPP_ENABLED", "1")):
        _idle_forever("FQ_WEBAPP_ENABLED=0")
        return

    port = int(os.environ.get("PORT", "8080"))
    host = "0.0.0.0"

    try:
        from webapp.server import create_app
        app = create_app()
    except Exception as e:
        log.error("No se pudo crear la app Flask: %s", e, exc_info=True)
        _idle_forever("create_app fallo")
        return

    # Heartbeat en thread aparte (el server bloquea).
    threading.Thread(target=_heartbeat_loop, daemon=True).start()

    log.info("FQ Mini App escuchando en %s:%s", host, port)
    try:
        try:
            from waitress import serve
            serve(app, host=host, port=port, threads=8, _quiet=True)
        except ImportError:
            log.warning("waitress no disponible; uso el server de Flask (dev)")
            app.run(host=host, port=port, threaded=True)
    except Exception as e:
        log.error("El server web cayo: %s", e, exc_info=True)
        _idle_forever("server cayo")
        return

    # serve() no deberia retornar; si lo hace, idle en vez de salir.
    _idle_forever("server retorno inesperadamente")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
