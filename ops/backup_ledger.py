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


def _backup_one(tmp_path, fname, caption, s3_key):
    sent_tg = _send_to_telegram(tmp_path, caption)
    sent_s3 = _maybe_upload_s3(tmp_path, s3_key)
    log.info("backup {} -> telegram={} s3={}".format(fname, sent_tg, sent_s3))
    return sent_tg or sent_s3


def _backup_jsonl_ledgers(stamp):
    """Respalda cada motor_paper_*.jsonl (snapshot estable del append-only)."""
    sent_any = False
    for src in _resolve_jsonl_ledgers():
        stem = os.path.splitext(os.path.basename(src))[0]
        fname = "{}-{}.jsonl".format(stem, stamp)
        tmp_path = os.path.join(tempfile.gettempdir(), fname)
        try:
            shutil.copy2(src, tmp_path)            # snapshot estable (un torn-tail lo sana load())
            kb = os.path.getsize(tmp_path) / 1024.0
            cap = "FQ backup {} · {} · {:.0f} KB".format(os.path.basename(src), stamp, kb)
            sent_any = _backup_one(tmp_path, fname, cap, "ledger/{}".format(fname)) or sent_any
        except Exception as e:
            log.error("backup jsonl {} error: {}".format(src, e))
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return sent_any


def run_backup():
    """Backup completo: el SQLite VIP (SOL) + los JSONL motor_paper de TODOS los
    símbolos (BTC/ETH/SOL). Devuelve True si al menos un destino recibió algo."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    ok = False

    # 1) SQLite (ledger VIP, SOL)
    src = _resolve_ledger_path()
    if os.path.isfile(src):
        fname = "fq_ledger-{}.db".format(stamp)
        tmp_path = os.path.join(tempfile.gettempdir(), fname)
        try:
            _consistent_copy(src, tmp_path)
            kb = os.path.getsize(tmp_path) / 1024.0
            cap = "FQ backup ledger · {} · {:.0f} KB".format(stamp, kb)
            ok = _backup_one(tmp_path, fname, cap, "ledger/{}".format(fname)) or ok
        except Exception as e:
            log.error("backup sqlite fallo: {}".format(e))
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    else:
        log.warning("backup: SQLite no existe en {}".format(src))

    # 2) JSONL motor_paper (BTC/ETH/SOL) — el registro forward que faltaba respaldar
    ok = _backup_jsonl_ledgers(stamp) or ok
    return ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_backup()
