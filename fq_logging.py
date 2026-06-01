# -*- coding: utf-8 -*-
"""
Logging estructurado opcional. Emite una linea JSON por evento cuando
FQ_JSON_LOGS=1; en caso contrario mantiene el formato legible de siempre.

Se aplica a nivel de root logger, asi que todos los log.info()/log.error()
existentes pasan a JSON sin tocar cada call site. Bajo riesgo, alto valor:
con clientes reales se puede grep/parsear "que paso con la senal X".

Uso (una linea en cada entry point):
    import fq_logging
    fq_logging.setup()
"""
import os
import sys
import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Formatea cada record como una linea JSON compacta."""

    def format(self, record):
        payload = {
            "ts":    datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "mod":   record.name,
            "event": record.getMessage(),
        }
        # Campos extra inyectados via logger.info(..., extra={"signal_id": ...})
        for key in ("signal_id", "user_id", "tf", "outcome", "pnl_r", "component"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _level_from_env():
    name = os.environ.get("FQ_LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


def setup():
    """
    Configura el root logger. Idempotente: limpia handlers previos.
    JSON si FQ_JSON_LOGS=1, legible si no.
    """
    root = logging.getLogger()
    root.setLevel(_level_from_env())

    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if os.environ.get("FQ_JSON_LOGS", "0").strip() == "1":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
    root.addHandler(handler)
    return root
