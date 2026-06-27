# -*- coding: utf-8 -*-
"""
Backup del ledger SQLite. Copia consistente (sqlite backup API) y la envia
como documento por Telegram al admin; opcionalmente sube a S3 si esta
configurado. Con clientes reales, un DM cada N senales no basta: esto corre
por tiempo (cada 6h), no por conteo.

Sin dependencias nuevas: requests para Telegram, boto3 solo si hay S3 config.
"""
import os
import glob
import shutil
import sqlite3
import tarfile
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


def _resolve_jsonl_ledgers():
    """Los ledgers motor_paper (JSONL hash-chain) de TODOS los símbolos — el único
    registro forward de BTC/ETH (2/3 del producto), que antes NO se respaldaba."""
    paths = set()
    for env in ("FQ_MOTOR_PAPER_LEDGER_PATH", "FQ_MOTOR_PAPER_BTC_LEDGER_PATH",
                "FQ_MOTOR_PAPER_ETH_LEDGER_PATH"):
        v = os.environ.get(env, "").strip()
        if v:
            paths.add(v)
    base = "/data" if os.path.isdir("/data") else tempfile.gettempdir()
    for p in glob.glob(os.path.join(base, "motor_paper_*.jsonl")):
        paths.add(p)
    return sorted(x for x in paths if os.path.isfile(x))


def _resolve_sqlite_motor_dbs():
    """El SQLite multi-símbolo del motor (fq_motor.db) — el registro forward CONSOLIDADO
    tras el corte FQ_LEDGER_SQLITE. Antes no se respaldaba (solo el VIP y los JSONL)."""
    paths = set()
    v = os.environ.get("FQ_MOTOR_DB", "").strip()
    if v:
        paths.add(v)
    base = "/data" if os.path.isdir("/data") else tempfile.gettempdir()
    for p in glob.glob(os.path.join(base, "fq_motor*.db")):
        paths.add(p)
    return sorted(x for x in paths if os.path.isfile(x))


def _backup_one(tmp_path, fname, caption, s3_key):
    sent_tg = _send_to_telegram(tmp_path, caption)
    sent_s3 = _maybe_upload_s3(tmp_path, s3_key)
    log.info("backup {} -> telegram={} s3={}".format(fname, sent_tg, sent_s3))
    return sent_tg or sent_s3


def run_backup():
    """Backup completo en UN SOLO archivo (tar.gz): el SQLite VIP (SOL) + los JSONL
    motor_paper de TODOS los símbolos. Antes mandaba un archivo por ledger -> con
    10-20 símbolos eso spamea el DM. Ahora = 1 documento por corrida, escale a lo que
    escale. Devuelve True si al menos un destino recibió algo."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    staging = tempfile.mkdtemp(prefix="fqbk-")
    staged = []
    try:
        # 1) SQLite (ledger VIP, SOL) — copia consistente
        src = _resolve_ledger_path()
        if os.path.isfile(src):
            dst = os.path.join(staging, "fq_ledger.db")
            try:
                _consistent_copy(src, dst)
                staged.append(dst)
            except Exception as e:
                log.error("backup sqlite fallo: {}".format(e))
        else:
            log.warning("backup: SQLite no existe en {}".format(src))

        # 1b) SQLite motor consolidado (fq_motor.db) — el registro forward unificado
        for mdb in _resolve_sqlite_motor_dbs():
            dst = os.path.join(staging, os.path.basename(mdb))
            try:
                _consistent_copy(mdb, dst)
                staged.append(dst)
            except Exception as e:
                log.error("backup motor-sqlite {} error: {}".format(mdb, e))

        # 2) JSONL motor_paper (BTC/ETH/SOL/...) — snapshot estable de cada append-only (legacy)
        for j in _resolve_jsonl_ledgers():
            try:
                shutil.copy2(j, os.path.join(staging, os.path.basename(j)))
                staged.append(os.path.join(staging, os.path.basename(j)))
            except Exception as e:
                log.error("backup jsonl {} error: {}".format(j, e))

        if not staged:
            log.warning("backup: nada que respaldar")
            return False

        # 3) UN solo tar.gz con todo
        arch = os.path.join(tempfile.gettempdir(), "fq_backup-{}.tar.gz".format(stamp))
        with tarfile.open(arch, "w:gz") as tar:
            for f in staged:
                tar.add(f, arcname=os.path.basename(f))
        try:
            kb = os.path.getsize(arch) / 1024.0
            cap = "FQ backup · {} · {} ledgers · {:.0f} KB".format(stamp, len(staged), kb)
            ok = _backup_one(arch, os.path.basename(arch), cap,
                             "ledger/{}".format(os.path.basename(arch)))
        finally:
            try:
                os.remove(arch)
            except OSError:
                pass
        return ok
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_backup()
