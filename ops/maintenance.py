# -*- coding: utf-8 -*-
"""
Loop de mantenimiento. Tercer proceso del launcher.

  - Backup del ledger cada FQ_BACKUP_HOURS (default 6h).
  - Vigila heartbeats: si VIP o Public dejan de latir, DM al admin.

El launcher ya reinicia el container si un proceso muere. Este loop cubre
el otro modo de fallo: proceso vivo pero colgado (no late).

Run: python -m ops.maintenance   (desde la raiz del repo)
"""
import os
import json
import time
import logging

import requests

from ops import heartbeat, backup_ledger

# Boton "Abrir app" en las alertas de salud (opcional, degradado seguro).
try:
    from webapp import notify as webapp_notify
except Exception:
    webapp_notify = None

log = logging.getLogger("fq_maintenance")


def _app_button(view=None):
    if webapp_notify is None:
        return None
    try:
        return webapp_notify.app_button(view=view)
    except Exception:
        return None

BACKUP_INTERVAL_S = int(float(os.environ.get("FQ_BACKUP_HOURS", "6")) * 3600)
CHECK_INTERVAL_S  = 300          # revisa heartbeats cada 5 min

# Umbrales de staleness por componente (segundos).
STALE_THRESHOLDS = {
    "vip":    int(os.environ.get("FQ_VIP_STALE_MIN", "15")) * 60,
    "public": int(os.environ.get("FQ_PUBLIC_STALE_MIN", "20")) * 60,
    "web":    int(os.environ.get("FQ_WEB_STALE_MIN", "15")) * 60,
}

# Estado de alerta para no spamear: solo avisa en la transicion sano->stale.
_alerted = {k: False for k in STALE_THRESHOLDS}


def _dm_admin(text, view=None):
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    url = "https://api.telegram.org/bot{}/sendMessage".format(token)
    data = {"chat_id": chat_id, "text": text}
    markup = _app_button(view)
    if markup:
        data["reply_markup"] = json.dumps(markup)
    try:
        r = requests.post(url, data=data, timeout=20)
        # Una alerta de salud es critica: si el boton esta mal configurado
        # (400), reintentar sin boton para no perder el aviso.
        if markup and r is not None and r.status_code == 400:
            data.pop("reply_markup", None)
            requests.post(url, data=data, timeout=20)
    except Exception as e:
        log.error("dm admin fallo: {}".format(e))


def _check_heartbeats():
    for comp, threshold in STALE_THRESHOLDS.items():
        stale = heartbeat.is_stale(comp, threshold)
        if stale and not _alerted[comp]:
            age = heartbeat.age_seconds(comp)
            _alerted[comp] = True
            msg = "FQ ALERTA: '{}' sin latido hace {:.0f} min.".format(
                comp, (age or 0) / 60.0)
            log.error(msg)
            _dm_admin(msg, view="health")
        elif not stale and _alerted[comp]:
            _alerted[comp] = False
            log.info("'{}' volvio a latir".format(comp))
            _dm_admin("FQ: '{}' recuperado, latiendo de nuevo.".format(comp), view="health")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [maintenance] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log.info("maintenance loop arrancando (backup cada {}h, check cada {}s)".format(
        BACKUP_INTERVAL_S / 3600, CHECK_INTERVAL_S))

    last_backup = 0.0
    while True:
        try:
            now = time.time()
            if now - last_backup >= BACKUP_INTERVAL_S:
                log.info("ejecutando backup programado")
                if backup_ledger.run_backup():
                    last_backup = now
                else:
                    # reintenta en el proximo ciclo, no marca como hecho
                    log.warning("backup sin destino exitoso, se reintentara")
            _check_heartbeats()
        except Exception as e:
            log.error("maintenance ciclo error: {}".format(e))
        time.sleep(CHECK_INTERVAL_S)


if __name__ == "__main__":
    main()
