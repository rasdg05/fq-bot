# -*- coding: utf-8 -*-
"""
================================================================================
  TACTICAL TRACKER - seguimiento en vivo de las ALERTAS TACTICAS del VIP
  by RasDG_Sol + Claude

  Problema que resuelve:
    Las ALERTAS TACTICAS / RADAR que se promueven al VIP NO entran al ledger
    (no son senales automaticas), asi que el progress tracker clasico nunca las
    seguia: eran fire-and-forget. Resultado: una tactica podia tocar TP1 y el
    usuario no recibia el aviso de "recorre el SL a entry (break-even)".

  Que hace:
    - Persiste cada tactica promovida como entidad ligera (tactical_signals).
    - En cada vela revisa las tacticas ABIERTAS y, reusando la deteccion de
      signal_progress_tracker, emite la MISMA guia operativa:
        tp1_hit / be_suggested -> mueve SL a entry (break-even)
        tp2_hit / partial      -> toma parcial + trailing
        tp3_hit                -> trailing agresivo
    - Cierra la tactica (deja de escanearla) al tocar TP3, al tocar SL
      (invalidacion) o al expirar el horizonte de seguimiento.

  NO toca el ledger, ni las metricas del motor, ni cierra senales reales.
  Idempotente via UNIQUE(tactical_id, event). Tablas creadas por
  entropy_cognition.init_db (SCHEMA_SQL).
================================================================================
"""
import os
import logging
import sqlite3
from datetime import datetime, timezone, timedelta

import entropy_cognition as ev
import signal_progress_tracker as spt

try:
    import pandas as pd
except ImportError:
    pd = None

log = logging.getLogger("fq_tactical_tracker")

# Horizonte de seguimiento. Las tacticas usan TPs cortos; pasado esto se cierran
# para no escanear indefinidamente. Override via env.
TACTICAL_TRACK_HOURS = float(os.environ.get("FQ_TACTICAL_TRACK_HOURS", "12"))

# Etiqueta de cara al cliente en los mensajes de progreso (no "Senal", que es
# del ledger). El id se prefija con 'T' para no confundir con senales reales.
LABEL = "Tactica"


# ============================================================
# PERSISTENCIA
# ============================================================
def _connect():
    conn = sqlite3.connect(ev.DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def record_tactical(tf, direction, entry, sl, tp1, tp2, tp3, ts_emitted=None):
    """Persiste una tactica recien promovida al VIP. Devuelve su id (o None)."""
    if entry is None or tp1 is None:
        return None
    ts = ts_emitted or datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        cur = conn.execute("""
            INSERT INTO tactical_signals
                (tf, direction, entry, sl, tp1, tp2, tp3, ts_emitted, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """, (tf, direction, float(entry),
              float(sl)  if sl  is not None else None,
              float(tp1) if tp1 is not None else None,
              float(tp2) if tp2 is not None else None,
              float(tp3) if tp3 is not None else None,
              ts))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_open_tacticals():
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM tactical_signals WHERE status='open'").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_sent_events(tactical_id):
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT event FROM tactical_progress WHERE tactical_id=?",
            (int(tactical_id),)).fetchall()
        return set(r["event"] for r in rows)
    finally:
        conn.close()


def mark_event(tactical_id, event, price):
    """INSERT OR IGNORE idempotente. True si se inserto, False si ya existia."""
    conn = _connect()
    try:
        cur = conn.execute("""
            INSERT OR IGNORE INTO tactical_progress
                (tactical_id, event, ts_event, price)
            VALUES (?, ?, ?, ?)
        """, (int(tactical_id), event,
              datetime.now(timezone.utc).isoformat(),
              float(price) if price is not None else None))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def close_tactical(tactical_id, reason):
    conn = _connect()
    try:
        conn.execute("UPDATE tactical_signals SET status=? WHERE id=?",
                     ("closed:" + reason, int(tactical_id)))
        conn.commit()
    finally:
        conn.close()


# ============================================================
# DETECCION / CIERRE
# ============================================================
def _expired(ts_emitted, now=None):
    try:
        ts_em = datetime.fromisoformat(ts_emitted)
    except Exception:
        return False
    if ts_em.tzinfo is None:
        ts_em = ts_em.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return (now - ts_em) > timedelta(hours=TACTICAL_TRACK_HOURS)


def _sl_touched(direction, sl, df_post):
    """True si el SL (invalidacion) fue tocado en alguna vela post-emision."""
    if sl is None or df_post is None or len(df_post) == 0:
        return False
    for _, row in df_post.iterrows():
        if direction == "long" and float(row["low"]) <= sl:
            return True
        if direction == "short" and float(row["high"]) >= sl:
            return True
    return False


def check_tactical_progress(df):
    """
    Revisa todas las tacticas ABIERTAS contra ``df`` (velas recientes con
    columnas timestamp/high/low/close). Devuelve lista de (display_sig, event,
    price) NUEVOS, ya marcados como enviados, lista para spt.build_progress_alert.

    Cierra (status != open) las tacticas que tocaron TP3, SL o expiraron, para
    dejar de escanearlas.
    """
    if pd is None or df is None or len(df) == 0:
        return []
    out = []
    for tac in get_open_tacticals():
        try:
            signal_row = {
                "id":         tac["id"],
                "ts_emitted": tac["ts_emitted"],
                "direction":  tac["direction"],
                "tp1": tac["tp1"], "tp2": tac["tp2"], "tp3": tac["tp3"],
            }
            sent = get_sent_events(tac["id"])
            events = spt.check_progress_events(signal_row, df, sent=sent)

            display = {"id": "T{}".format(tac["id"]),
                       "direction": tac["direction"]}
            tp3_hit = False
            for kind, price in events:
                if not mark_event(tac["id"], kind, price):
                    continue
                if kind == "tp3_hit":
                    tp3_hit = True
                out.append((display, kind, price))

            # Cierre: TP3 corrido, SL tocado (invalidacion) o expiro el horizonte.
            df_post = spt.post_emission_candles(df, tac["ts_emitted"])
            if tp3_hit:
                close_tactical(tac["id"], "tp3")
            elif _sl_touched(tac["direction"], tac.get("sl"), df_post):
                close_tactical(tac["id"], "sl")
            elif _expired(tac["ts_emitted"]):
                close_tactical(tac["id"], "expiry")
        except Exception as e:
            log.warning("check_tactical_progress [id=%s]: %s", tac.get("id"), e)
    return out
