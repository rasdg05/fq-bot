#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  FQ COMBINED LAUNCHER - arranca VIP + Public en el mismo container
  by RasDG_Sol + Claude

  Railway no permite volumenes compartidos entre servicios (feature pendiente
  desde 2024). Para que el bot publico pueda leer /data/fq_ledger.db del bot
  VIP, ambos corren en el MISMO servicio Railway, sobre el mismo volumen.

  Este launcher:
   - Lanza entry_vip.py y entry_public.py como subprocesos hijos
   - Hereda stdout/stderr (Railway captura logs de ambos)
   - Si cualquier hijo muere, sale con rc != 0 -> Railway reinicia el container
   - Propaga SIGTERM/SIGINT a ambos hijos en shutdown

  ENV vars que deben estar presentes en el servicio Railway:
   VIP:    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_API_KEY, FQ_LEDGER_PATH
   PUBLIC: TELEGRAM_TOKEN_PUBLIC, FQ_VIP_BOT_USERNAME,
           FQ_PUBLIC_DB_PATH (/data/fq_public.db),
           FQ_VIP_LEDGER_PATH (/data/fq_ledger.db, mismo path que el VIP)
================================================================================
"""
import os
import sys
import signal
import subprocess
import time

BOTS = [
    ("vip",         [sys.executable, "-u", "entry_vip.py"]),
    ("public",      [sys.executable, "-u", "entry_public.py"]),
    ("maintenance", [sys.executable, "-u", "-m", "ops.maintenance"]),
    # Mini App (Telegram WebApp): panel admin + app cliente. Sirve el puerto
    # $PORT del servicio. Disenado para NUNCA salir (idle ante cualquier fallo),
    # asi un bug de la web no gatilla el restart del container. Off: FQ_WEBAPP_ENABLED=0.
    ("web",         [sys.executable, "-u", "entry_web.py"]),
]

GRACE_SECONDS = 8       # tiempo para que los hijos atiendan SIGTERM
POLL_INTERVAL = 3       # cada cuantos segundos chequeamos si murio alguien

_processes = []         # list of (name, Popen)
_shutting_down = False


def _ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _log(msg):
    sys.stdout.write("{} [launcher] {}\n".format(_ts(), msg))
    sys.stdout.flush()


def _spawn(name, cmd):
    _log("starting {}: {}".format(name, " ".join(cmd)))
    return subprocess.Popen(
        cmd,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=os.environ.copy(),
    )


def _shutdown(signum=None, frame=None):
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    _log("shutdown (signal={}) - terminando hijos".format(signum))

    for name, p in _processes:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception as e:
                _log("terminate {} fallo: {}".format(name, e))

    deadline = time.time() + GRACE_SECONDS
    while time.time() < deadline:
        if all(p.poll() is not None for _, p in _processes):
            break
        time.sleep(0.5)

    for name, p in _processes:
        if p.poll() is None:
            _log("{} no respondio en {}s - kill -9".format(name, GRACE_SECONDS))
            try:
                p.kill()
            except Exception:
                pass

    sys.exit(0)


def main():
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    _log("FQ launcher arrancando {} bots".format(len(BOTS)))
    for name, cmd in BOTS:
        _processes.append((name, _spawn(name, cmd)))

    while True:
        time.sleep(POLL_INTERVAL)
        for name, p in _processes:
            rc = p.poll()
            if rc is not None:
                _log("{} salio con rc={} - saliendo para que Railway reinicie".format(name, rc))
                _shutdown()
                sys.exit(rc if rc not in (None, 0) else 1)


if __name__ == "__main__":
    main()
