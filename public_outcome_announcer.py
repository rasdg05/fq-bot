# -*- coding: utf-8 -*-
"""
================================================================================
  PUBLIC OUTCOME ANNOUNCER - lee ledger VIP en read-only y anuncia cierres +1R
  by RasDG_Sol + Claude

  - Abre vip ledger con mode=ro via URI (zero risk de escribir)
  - Detecta cierres nuevos (no anunciados aun) con pnl_r >= 1.0
  - Mantiene tabla local de "ya anunciados" en su propia BD
  - Devuelve mensajes formateados (no envia - lo hace el caller)
================================================================================
"""
import os
import sys
import sqlite3
import logging
import threading
from datetime import datetime, timezone, timedelta

log = logging.getLogger("fq_public_announcer")

# ============================================================
# CONFIG
# ============================================================
def _resolve_vip_db_path():
    forced = os.environ.get("FQ_VIP_LEDGER_PATH")
    if forced:
        return forced
    if os.path.isfile("/data/fq_ledger.db"):
        return "/data/fq_ledger.db"
    if os.path.isfile("/tmp/fq_ledger.db"):
        return "/tmp/fq_ledger.db"
    return "/data/fq_ledger.db"  # default optimista

def _resolve_public_db_path():
    forced = os.environ.get("FQ_PUBLIC_DB_PATH")
    if forced:
        return forced
    if os.path.isdir("/data") and os.access("/data", os.W_OK):
        return "/data/fq_public.db"
    sys.stderr.write(
        "[WARN] /data no montado - public DB en /tmp (efimera)\n"
    )
    return "/tmp/fq_public.db"

VIP_DB_PATH    = _resolve_vip_db_path()
PUBLIC_DB_PATH = _resolve_public_db_path()
MIN_PNL_R_TO_ANNOUNCE = 1.0
ANNOUNCE_LOOKBACK_HOURS = 48   # solo anuncia cierres recientes (no historicos)

# Para teasers de senales nuevas (sin niveles)
NEW_SIGNAL_LOOKBACK_MIN = 30   # solo senales emitidas en los ultimos N min
# Filtrar conviction baja (phi^1 = 1.618). Solo anunciamos MEDIA+
MIN_PMASTER_FOR_TEASER = 1.6180339887

_lock = threading.Lock()

# ============================================================
# PUBLIC DB - tracking de chats suscritos + anuncios ya enviados
# ============================================================
PUBLIC_SCHEMA = """
CREATE TABLE IF NOT EXISTS public_subscribers (
    chat_id      INTEGER PRIMARY KEY,
    username     TEXT,
    first_name   TEXT,
    ts_joined    TEXT NOT NULL,
    active       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS announced_signals (
    vip_signal_id  INTEGER PRIMARY KEY,
    ts_announced   TEXT NOT NULL,
    outcome        TEXT,
    pnl_r          REAL
);

CREATE TABLE IF NOT EXISTS announced_new_signals (
    vip_signal_id  INTEGER PRIMARY KEY,
    ts_announced   TEXT NOT NULL,
    direction      TEXT,
    tier           TEXT
);

CREATE TABLE IF NOT EXISTS public_content_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    kind         TEXT NOT NULL,   -- 'lectura','cta','closure','stats','welcome','new_signal','mantra'
    title        TEXT,
    n_sent       INTEGER DEFAULT 0,
    n_failed     INTEGER DEFAULT 0
);
"""

def _connect_public():
    conn = sqlite3.connect(PUBLIC_DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_public_db():
    with _lock:
        conn = _connect_public()
        try:
            conn.executescript(PUBLIC_SCHEMA)
            conn.commit()
            log.info("Public DB inicializada: {}".format(PUBLIC_DB_PATH))
        finally:
            conn.close()

def _connect_vip_readonly():
    """Acceso read-only al ledger VIP via URI - no puede escribir"""
    if not os.path.isfile(VIP_DB_PATH):
        return None
    uri = "file:{}?mode=ro".format(VIP_DB_PATH)
    conn = sqlite3.connect(uri, uri=True, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================
# SUBSCRIBERS
# ============================================================
def add_subscriber(chat_id, username=None, first_name=None):
    """Idempotente. Si ya existe, lo reactiva."""
    with _lock:
        conn = _connect_public()
        try:
            conn.execute("""
                INSERT INTO public_subscribers (chat_id, username, first_name, ts_joined, active)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(chat_id) DO UPDATE SET
                    active=1,
                    username=excluded.username,
                    first_name=excluded.first_name
            """, (int(chat_id), username or "", first_name or "",
                  datetime.now(timezone.utc).isoformat()))
            conn.commit()
        finally:
            conn.close()

def remove_subscriber(chat_id):
    with _lock:
        conn = _connect_public()
        try:
            conn.execute(
                "UPDATE public_subscribers SET active=0 WHERE chat_id=?",
                (int(chat_id),)
            )
            conn.commit()
        finally:
            conn.close()

def get_active_subscribers():
    """Lista de chat_ids activos para broadcast"""
    with _lock:
        conn = _connect_public()
        try:
            rows = conn.execute(
                "SELECT chat_id FROM public_subscribers WHERE active=1"
            ).fetchall()
            return [int(r["chat_id"]) for r in rows]
        finally:
            conn.close()

def count_subscribers():
    with _lock:
        conn = _connect_public()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM public_subscribers WHERE active=1"
            ).fetchone()
            return int(row["n"]) if row else 0
        finally:
            conn.close()

# ============================================================
# ANUNCIOS DE CIERRE +1R
# ============================================================
def get_new_closures_to_announce():
    """
    Devuelve lista de signals cerrados con pnl_r >= MIN que NO han sido anunciados.
    Solo mira las ultimas ANNOUNCE_LOOKBACK_HOURS para evitar spam historico.
    """
    vip_conn = _connect_vip_readonly()
    if vip_conn is None:
        log.warning("VIP ledger no existe en {} - cero anuncios posibles".format(VIP_DB_PATH))
        return []

    cutoff = (datetime.now(timezone.utc) -
              timedelta(hours=ANNOUNCE_LOOKBACK_HOURS)).isoformat()
    try:
        with _lock:
            pub_conn = _connect_public()
            try:
                already_rows = pub_conn.execute(
                    "SELECT vip_signal_id FROM announced_signals"
                ).fetchall()
                already_ids = set(r["vip_signal_id"] for r in already_rows)
            finally:
                pub_conn.close()

        cur = vip_conn.execute("""
            SELECT id, direction, entry_price, sl, tp1, tp2, tp3, tp4,
                   ts_emitted, ts_closed, outcome, exit_price, pnl_r, minutes_open
            FROM signals
            WHERE outcome IS NOT NULL
              AND pnl_r >= ?
              AND ts_closed >= ?
            ORDER BY ts_closed ASC
        """, (MIN_PNL_R_TO_ANNOUNCE, cutoff))
        candidates = [dict(r) for r in cur.fetchall()]
    finally:
        vip_conn.close()

    new_ones = [c for c in candidates if c["id"] not in already_ids]
    return new_ones

def mark_announced(vip_signal_id, outcome=None, pnl_r=None):
    with _lock:
        conn = _connect_public()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO announced_signals
                    (vip_signal_id, ts_announced, outcome, pnl_r)
                VALUES (?, ?, ?, ?)
            """, (int(vip_signal_id),
                  datetime.now(timezone.utc).isoformat(),
                  outcome, pnl_r))
            conn.commit()
        finally:
            conn.close()

# ============================================================
# TEASERS DE SENAL NUEVA (sin niveles)
# ============================================================
def get_new_signals_to_announce():
    """
    Devuelve lista de signals recien emitidas (outcome IS NULL) que NO han sido
    anunciadas en el bot publico, filtrando conviction baja para no spamear.
    Solo mira las ultimas NEW_SIGNAL_LOOKBACK_MIN minutos.
    """
    vip_conn = _connect_vip_readonly()
    if vip_conn is None:
        return []

    cutoff = (datetime.now(timezone.utc) -
              timedelta(minutes=NEW_SIGNAL_LOOKBACK_MIN)).isoformat()
    try:
        with _lock:
            pub_conn = _connect_public()
            try:
                already_rows = pub_conn.execute(
                    "SELECT vip_signal_id FROM announced_new_signals"
                ).fetchall()
                already_ids = set(r["vip_signal_id"] for r in already_rows)
            finally:
                pub_conn.close()

        cur = vip_conn.execute("""
            SELECT id, direction, ts_emitted, session, tier, p_master_final
            FROM signals
            WHERE outcome IS NULL
              AND ts_emitted >= ?
              AND p_master_final >= ?
            ORDER BY ts_emitted ASC
        """, (cutoff, MIN_PMASTER_FOR_TEASER))
        candidates = [dict(r) for r in cur.fetchall()]
    finally:
        vip_conn.close()

    return [c for c in candidates if c["id"] not in already_ids]

def mark_new_announced(vip_signal_id, direction=None, tier=None):
    with _lock:
        conn = _connect_public()
        try:
            conn.execute("""
                INSERT OR IGNORE INTO announced_new_signals
                    (vip_signal_id, ts_announced, direction, tier)
                VALUES (?, ?, ?, ?)
            """, (int(vip_signal_id),
                  datetime.now(timezone.utc).isoformat(),
                  direction, tier))
            conn.commit()
        finally:
            conn.close()

# ============================================================
# STATS de la semana (7 dias) - leyendo VIP ledger read-only
# ============================================================
def compute_weekly_stats():
    """Lee ledger VIP read-only y calcula stats de los ultimos 7 dias"""
    vip_conn = _connect_vip_readonly()
    if vip_conn is None:
        return None
    cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    try:
        rows = vip_conn.execute("""
            SELECT outcome, pnl_r, direction
            FROM signals
            WHERE outcome IS NOT NULL AND ts_closed >= ?
        """, (cutoff_7d,)).fetchall()
    finally:
        vip_conn.close()

    if not rows:
        return None
    n = len(rows)
    wins = sum(1 for r in rows if r["outcome"] in ("tp1","tp2","tp3","tp4"))
    sls  = sum(1 for r in rows if r["outcome"] == "sl")
    pnls = [r["pnl_r"] for r in rows if r["pnl_r"] is not None]
    win_rate = wins / n
    expectancy = sum(pnls) / len(pnls) if pnls else 0
    win_pnl = sum(p for p in pnls if p > 0)
    loss_pnl = abs(sum(p for p in pnls if p < 0)) or 0.01
    profit_factor = win_pnl / loss_pnl
    best_pnl = max(pnls) if pnls else 0
    return {
        "n_closed_7d":    n,
        "wins":           wins,
        "sls":            sls,
        "win_rate":       win_rate,
        "expectancy":     expectancy,
        "profit_factor":  profit_factor,
        "best_pnl":       best_pnl,
    }

def compute_short_stats_7d():
    """Version compacta para incluir en anuncios de cierre"""
    full = compute_weekly_stats()
    if not full:
        return None
    return {
        "n_closed_7d":   full["n_closed_7d"],
        "win_rate_7d":   full["win_rate"],
        "expectancy_7d": full["expectancy"],
    }

# ============================================================
# LOGGING DE CONTENIDO ENVIADO (analitica interna)
# ============================================================
def log_content_sent(kind, title, n_sent, n_failed=0):
    with _lock:
        conn = _connect_public()
        try:
            conn.execute("""
                INSERT INTO public_content_log (ts, kind, title, n_sent, n_failed)
                VALUES (?, ?, ?, ?, ?)
            """, (datetime.now(timezone.utc).isoformat(),
                  kind, title or "", int(n_sent), int(n_failed)))
            conn.commit()
        finally:
            conn.close()

def get_content_stats(days=7):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _lock:
        conn = _connect_public()
        try:
            rows = conn.execute("""
                SELECT kind, COUNT(*) AS n, SUM(n_sent) AS sent
                FROM public_content_log WHERE ts >= ?
                GROUP BY kind
            """, (cutoff,)).fetchall()
            return {r["kind"]: {"n": r["n"], "sent": r["sent"]} for r in rows}
        finally:
            conn.close()
