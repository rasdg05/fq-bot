# -*- coding: utf-8 -*-
"""
Backup del ledger SQLite. Copia consistente (sqlite backup API) y la envia
como documento por Telegram al admin; opcionalmente sube a S3 si esta
configurado. Con clientes reales, un DM cada N senales no basta: esto corre
por tiempo (cada 6h), no por conteo.

Sin dependencias nuevas: requests para Telegram, boto3 solo si hay S3 config.
"""
import os
import sqlite3
import tempfile
import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger("fq_backup")


def _resolve_ledger_path():
    forced = os.environ.get("FQ_LEDGER_PATH")
    if forced:
        return forced
    for cand in ("/data/fq_ledger.db", "/tmp/fq_ledger.db"):
        if os.path.isfile(cand):
            return cand
    return "/data/fq_ledger.db"


def _consistent_copy(src_path, dst_path):
    """Copia consistente del SQLite aunque haya escrituras concurrentes."""
    src = sqlite3.connect("file:{}?mode=ro".format(src_path), uri=True, timeout=15)
    try:
        dst = sqlite3.connect(dst_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _send_to_telegram(file_path, caption):
    token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log.warning("backup: sin TELEGRAM_TOKEN/CHAT_ID, no se envia DM")
        return False
    url = "https://api.telegram.org/bot{}/sendDocument".format(token)
    try:
        with open(file_path, "rb") as f:
            r = requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"document": (os.path.basename(file_path), f)},
                timeout=60,
            )
        ok = r.status_code == 200
        if not ok:
            log.error("backup telegram fallo: {} {}".format(r.status_code, r.text[:160]))
        return ok
    except Exception as e:
        log.error("backup telegram error: {}".format(e))
        return False


def _maybe_upload_s3(file_path, key):
    bucket = os.environ.get("S3_BUCKET", "").strip()
    if not bucket:
        return False
    try:
        import boto3  # opcional, solo si hay S3 configurado
    except ImportError:
        log.warning("S3_BUCKET seteado pero boto3 no instalado")
        return False
    try:
        boto3.client("s3").upload_file(file_path, bucket, key)
        log.info("backup subido a s3://{}/{}".format(bucket, key))
        return True
    except Exception as e:
        log.error("backup s3 error: {}".format(e))
        return False


def run_backup():
    """Ejecuta un backup completo. Devuelve True si al menos un destino recibio."""
    src = _resolve_ledger_path()
    if not os.path.isfile(src):
        log.warning("backup: ledger no existe en {}".format(src))
        return False

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    fname = "fq_ledger-{}.db".format(stamp)
    tmp_path = os.path.join(tempfile.gettempdir(), fname)

    try:
        _consistent_copy(src, tmp_path)
        size_kb = os.path.getsize(tmp_path) / 1024.0
        caption = "FQ backup ledger · {} · {:.0f} KB".format(stamp, size_kb)
        sent_tg = _send_to_telegram(tmp_path, caption)
        sent_s3 = _maybe_upload_s3(tmp_path, "ledger/{}".format(fname))
        ok = sent_tg or sent_s3
        log.info("backup {} -> telegram={} s3={}".format(fname, sent_tg, sent_s3))
        return ok
    except Exception as e:
        log.error("backup fallo: {}".format(e))
        return False
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_backup()
