# -*- coding: utf-8 -*-
"""
Heartbeat / watchdog. Cada componente toca su latido; un vigilante externo
detecta si un componente se colgo (proceso vivo pero atascado) sin que el
launcher lo note (el launcher solo ve muerte de proceso, no cuelgues).

Latido = un archivo por componente con mtime actualizado. Simple, sin DB,
sobrevive en el volumen /data si esta montado.
"""
import os
import time

_DIR = os.environ.get("FQ_HEARTBEAT_DIR") or (
    "/data/heartbeat" if os.path.isdir("/data") and os.access("/data", os.W_OK)
    else "/tmp/fq_heartbeat"
)


def _path(component):
    return os.path.join(_DIR, "{}.beat".format(component))


def beat(component):
    """Registra un latido del componente. Best-effort, nunca lanza."""
    try:
        os.makedirs(_DIR, exist_ok=True)
        with open(_path(component), "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass


def age_seconds(component):
    """Segundos desde el ultimo latido, o None si nunca latio."""
    try:
        return time.time() - os.path.getmtime(_path(component))
    except OSError:
        return None


def is_stale(component, max_age_seconds):
    """True si el componente no late hace mas de max_age_seconds.
       Un componente que nunca latio NO se considera stale (aun no arranco)."""
    age = age_seconds(component)
    if age is None:
        return False
    return age > max_age_seconds
