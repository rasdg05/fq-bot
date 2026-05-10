# -*- coding: utf-8 -*-
"""
================================================================================
  ENTROPY COGNITION MODULE - FQ v4.1 Bot v3.2 "EVOLUTION PATCH"
  Autoevolucion entropica sin puntos de memoria
  by RasDG_Sol + Claude
================================================================================

  Filosofia:
    El bot no recuerda outcomes individuales - los DESTILA en distribuciones.
    Cada senal vive como un punto en un espacio de buckets (sesion x tier x
    direccion x curvatura). El sistema mide la entropia de Shannon sobre
    ese espacio: alta entropia = exploracion sana, baja entropia = atractor
    sobreajustado.

    El modulador kappa_evo afila P_master en +-15% segun el desempeno
    historico de cada bucket. NUNCA toca Theta(D). El gate es sagrado.

    Cada 25 senales cerradas, Opus audita el ledger completo y propone
    ajustes (sugerencias, no autoaplicadas).

  Modulo expone:
    - SignalLedger: SQLite local, append-only, con backup a Telegram
    - OutcomeTracker: monitorea senales abiertas hasta TP/SL/timeout
    - EntropyEngine: Shannon H sobre buckets, KL-divergence drift
    - KappaEvo: modulador suave +-15% sobre P_master
    - SelfAudit: trigger Opus cada N cerradas con backtest sintetico

  ASCII-only source.
================================================================================
"""
import os
import sys
import json
import math
import time
import logging
import sqlite3
import threading
import traceback
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

log = logging.getLogger("fq_entropy")

# ============================================================
# CONFIG
# ============================================================
DB_PATH               = os.environ.get("FQ_LEDGER_PATH", "/tmp/fq_ledger.db")
KAPPA_EVO_MAX         = 0.15           # +-15% modulador
KAPPA_EVO_MIN_SAMPLES = 8              # min senales cerradas en bucket para modular
AUDIT_EVERY_N_CLOSED  = 25             # trigger self-audit
OUTCOME_TIMEOUT_HOURS = 8              # vela 15m -> 8h ~ 32 velas para resolver
BACKUP_EVERY_N_SIGNED = 10             # backup a Telegram cada 10 senales
PHI                   = 1.6180339887
PHI_SQ                = PHI * PHI
PHI_CB                = PHI ** 3

# Buckets dimensionales para entropia
SESSION_BUCKETS = ["asia", "london", "ny", "overlap"]
TIER_BUCKETS    = ["scalp", "standard", "high"]    # phi, phi^2, phi^3
DIR_BUCKETS     = ["long", "short"]

_lock = threading.Lock()

# ============================================================
# SCHEMA
# ============================================================
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_emitted      TEXT NOT NULL,
    direction       TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    sl              REAL NOT NULL,
    tp1             REAL NOT NULL,
    tp2             REAL NOT NULL,
    tp3             REAL NOT NULL,
    tp4             REAL NOT NULL,
    p_master_raw    REAL NOT NULL,
    p_master_final  REAL NOT NULL,
    kappa_evo       REAL NOT NULL,
    session         TEXT NOT NULL,
    w_clock         REAL NOT NULL,
    tier            TEXT NOT NULL,
    pspace_count    INTEGER NOT NULL,
    curvature_bal   REAL,
    macro_btc       REAL,
    macro_eth       REAL,
    rsi6            REAL,
    rsi12           REAL,
    rsi24           REAL,
    h_lap_active    INTEGER,
    bucket_key      TEXT NOT NULL,
    snapshot_json   TEXT NOT NULL,
    -- outcome fields (NULL hasta cerrar)
    ts_closed       TEXT,
    outcome         TEXT,           -- 'tp1','tp2','tp3','tp4','sl','timeout'
    exit_price      REAL,
    pnl_r           REAL,           -- multiplo de R alcanzado
    minutes_open    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_bucket   ON signals(bucket_key);
CREATE INDEX IF NOT EXISTS idx_outcome  ON signals(outcome);
CREATE INDEX IF NOT EXISTS idx_emitted  ON signals(ts_emitted);

CREATE TABLE IF NOT EXISTS audits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT NOT NULL,
    n_closed        INTEGER NOT NULL,
    win_rate        REAL,
    expectancy_r    REAL,
    entropy_h       REAL,
    kl_drift        REAL,
    opus_response   TEXT,
    metrics_json    TEXT
);

CREATE TABLE IF NOT EXISTS evolution_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT NOT NULL,
    bucket_key      TEXT NOT NULL,
    n_samples       INTEGER NOT NULL,
    win_rate        REAL,
    expectancy_r    REAL,
    kappa_applied   REAL NOT NULL
);
"""

# ============================================================
# DB INIT
# ============================================================
def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_db():
    with _lock:
        conn = _connect()
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            log.info("Ledger DB inicializada: {}".format(DB_PATH))
        finally:
            conn.close()

# ============================================================
# BUCKET KEY
# ============================================================
def tier_from_pmaster(p_master):
    """Mapea P_master a tier de conviccion"""
    if p_master >= PHI_CB:    return "high"
    if p_master >= PHI_SQ:    return "standard"
    if p_master >= PHI:       return "scalp"
    return "subthreshold"

def make_bucket_key(session, tier, direction, curvature_sign):
    """
    bucket = sesion + tier + direccion + signo de curvatura
    curvature_sign: 'pos' si support_w > resistance_w, 'neg' al reves, 'flat' si ~0
    """
    return "{}|{}|{}|{}".format(session, tier, direction, curvature_sign)

def curvature_sign(support_w, resistance_w):
    diff = support_w - resistance_w
    if abs(diff) < 0.3:
        return "flat"
    return "pos" if diff > 0 else "neg"

# ============================================================
# LEDGER - registro de senales
# ============================================================
def log_signal(signal_data):
    """
    Inserta una senal nueva al ledger. Devuelve signal_id.

    signal_data debe incluir:
      direction, entry, sl, tp1, tp2, tp3, tp4,
      p_master_raw, p_master_final, kappa_evo,
      session, w_clock, pspace_count,
      support_weight, resistance_weight,
      macro_btc, macro_eth, rsi6, rsi12, rsi24, h_lap_active,
      snapshot (dict completo)
    """
    sd = signal_data
    tier = tier_from_pmaster(sd["p_master_final"])
    csign = curvature_sign(sd.get("support_weight", 0), sd.get("resistance_weight", 0))
    bucket = make_bucket_key(sd["session"], tier, sd["direction"], csign)

    with _lock:
        conn = _connect()
        try:
            cur = conn.execute("""
                INSERT INTO signals (
                    ts_emitted, direction, entry_price, sl, tp1, tp2, tp3, tp4,
                    p_master_raw, p_master_final, kappa_evo,
                    session, w_clock, tier, pspace_count, curvature_bal,
                    macro_btc, macro_eth, rsi6, rsi12, rsi24, h_lap_active,
                    bucket_key, snapshot_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                sd["direction"],
                float(sd["entry"]),
                float(sd["sl"]),
                float(sd["tp1"]),
                float(sd["tp2"]),
                float(sd["tp3"]),
                float(sd["tp4"]),
                float(sd["p_master_raw"]),
                float(sd["p_master_final"]),
                float(sd["kappa_evo"]),
                sd["session"],
                float(sd["w_clock"]),
                tier,
                int(sd["pspace_count"]),
                float(sd.get("support_weight", 0) - sd.get("resistance_weight", 0)),
                float(sd.get("macro_btc", 0)),
                float(sd.get("macro_eth", 0)),
                float(sd.get("rsi6", 0)),
                float(sd.get("rsi12", 0)),
                float(sd.get("rsi24", 0)),
                int(sd.get("h_lap_active", 0)),
                bucket,
                json.dumps(sd.get("snapshot", {}), default=str),
            ))
            conn.commit()
            sid = cur.lastrowid
            log.info("Ledger: senal #{} registrada bucket={}".format(sid, bucket))
            return sid
        except Exception as e:
            log.error("Ledger insert error: {}".format(e))
            return None
        finally:
            conn.close()

def get_open_signals():
    """Devuelve lista de senales sin outcome cerrado"""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM signals WHERE outcome IS NULL ORDER BY id"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

def close_signal(signal_id, outcome, exit_price, pnl_r, minutes_open):
    """Marca una senal como cerrada con su outcome"""
    with _lock:
        conn = _connect()
        try:
            conn.execute("""
                UPDATE signals SET
                    ts_closed = ?,
                    outcome = ?,
                    exit_price = ?,
                    pnl_r = ?,
                    minutes_open = ?
                WHERE id = ?
            """, (
                datetime.now(timezone.utc).isoformat(),
                outcome,
                float(exit_price),
                float(pnl_r),
                int(minutes_open),
                signal_id,
            ))
            conn.commit()
            log.info("Ledger: senal #{} cerrada outcome={} pnl_r={:.2f}".format(
                signal_id, outcome, pnl_r))
        finally:
            conn.close()

def count_signals(closed_only=False):
    with _lock:
        conn = _connect()
        try:
            if closed_only:
                row = conn.execute(
                    "SELECT COUNT(*) as n FROM signals WHERE outcome IS NOT NULL"
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) as n FROM signals").fetchone()
            return int(row["n"])
        finally:
            conn.close()

# ============================================================
# OUTCOME TRACKER
# ============================================================
def check_outcome_against_candles(signal_row, df):
    """
    Dado una senal abierta y un df reciente de OHLCV, determina si
    toco TP1/2/3/4, SL, o si timeout.

    Retorna dict con outcome, exit_price, pnl_r, minutes_open o None si sigue abierta.

    df debe ser 15m con index temporal (timestamp). Usamos las velas POSTERIORES
    al ts_emitted.
    """
    ts_emitted = datetime.fromisoformat(signal_row["ts_emitted"])
    if ts_emitted.tzinfo is None:
        ts_emitted = ts_emitted.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    elapsed_min = (now - ts_emitted).total_seconds() / 60.0

    # Filtra velas post-emision
    df_post = df[df["timestamp"] > pd.Timestamp(ts_emitted)]
    if len(df_post) == 0:
        return None  # aun no hay velas posteriores

    direction = signal_row["direction"]
    entry = signal_row["entry_price"]
    sl    = signal_row["sl"]
    tp1   = signal_row["tp1"]
    tp2   = signal_row["tp2"]
    tp3   = signal_row["tp3"]
    tp4   = signal_row["tp4"]
    risk  = abs(entry - sl)
    if risk <= 0:
        return None

    # Para LONG: SL si low <= sl, TP si high >= tp
    # Para SHORT: SL si high >= sl, TP si low <= tp
    # Iteramos vela por vela en orden cronologico
    # Si en la misma vela tocan SL y TP, conservadoramente asumimos SL primero (peor caso).
    for _, row in df_post.iterrows():
        hi = float(row["high"])
        lo = float(row["low"])
        if direction == "long":
            if lo <= sl:
                return _build_outcome("sl", sl, entry, sl, direction, ts_emitted)
            if hi >= tp4:
                return _build_outcome("tp4", tp4, entry, sl, direction, ts_emitted)
            if hi >= tp3:
                return _build_outcome("tp3", tp3, entry, sl, direction, ts_emitted)
            if hi >= tp2:
                return _build_outcome("tp2", tp2, entry, sl, direction, ts_emitted)
            if hi >= tp1:
                return _build_outcome("tp1", tp1, entry, sl, direction, ts_emitted)
        else:  # short
            if hi >= sl:
                return _build_outcome("sl", sl, entry, sl, direction, ts_emitted)
            if lo <= tp4:
                return _build_outcome("tp4", tp4, entry, sl, direction, ts_emitted)
            if lo <= tp3:
                return _build_outcome("tp3", tp3, entry, sl, direction, ts_emitted)
            if lo <= tp2:
                return _build_outcome("tp2", tp2, entry, sl, direction, ts_emitted)
            if lo <= tp1:
                return _build_outcome("tp1", tp1, entry, sl, direction, ts_emitted)

    # Sin outcome - revisa timeout
    if elapsed_min >= OUTCOME_TIMEOUT_HOURS * 60:
        last_close = float(df_post["close"].iloc[-1])
        return _build_outcome("timeout", last_close, entry, sl, direction, ts_emitted)

    return None  # sigue abierta

def _build_outcome(outcome, exit_price, entry, sl, direction, ts_emitted):
    risk = abs(entry - sl)
    if direction == "long":
        pnl = exit_price - entry
    else:
        pnl = entry - exit_price
    pnl_r = pnl / risk if risk > 0 else 0
    minutes_open = int((datetime.now(timezone.utc) - ts_emitted).total_seconds() / 60)
    return {
        "outcome":      outcome,
        "exit_price":   exit_price,
        "pnl_r":        pnl_r,
        "minutes_open": minutes_open,
    }

# Necesita pandas - import local para evitar circulos
try:
    import pandas as pd
except ImportError:
    pd = None

def reconcile_outcomes(fetch_ohlcv_fn, exchange, symbol, timeframe="15m"):
    """
    Recorre todas las senales abiertas, fetchea velas recientes y resuelve
    outcomes posibles. Devuelve lista de senales recien cerradas.
    """
    if pd is None:
        log.error("pandas no disponible para reconcile_outcomes")
        return []

    open_sigs = get_open_signals()
    if not open_sigs:
        return []

    # Una sola fetch de velas suficientes para cubrir el timeout
    # 8h / 15m = 32 velas, traemos 50 por seguridad
    try:
        df = fetch_ohlcv_fn(exchange, symbol, timeframe, limit=50)
    except Exception as e:
        log.error("reconcile fetch_ohlcv error: {}".format(e))
        return []

    closed = []
    for sig in open_sigs:
        try:
            result = check_outcome_against_candles(sig, df)
            if result is not None:
                close_signal(
                    sig["id"],
                    result["outcome"],
                    result["exit_price"],
                    result["pnl_r"],
                    result["minutes_open"],
                )
                closed.append({**sig, **result})
        except Exception as e:
            log.error("reconcile signal #{} error: {}".format(sig["id"], e))
    if closed:
        log.info("reconcile: {} senales cerradas".format(len(closed)))
    return closed

# ============================================================
# ENTROPY ENGINE - Shannon H y drift
# ============================================================
def shannon_entropy(counts):
    """
    Shannon H = -sum(p_i * log2(p_i)) sobre distribucion de buckets.
    Normalizado a [0,1] dividiendo por log2(N) donde N = numero de buckets ocupados.
    """
    total = sum(counts.values())
    if total == 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c > 0:
            p = c / total
            h -= p * math.log2(p)
    n_occupied = sum(1 for c in counts.values() if c > 0)
    if n_occupied <= 1:
        return 0.0
    h_max = math.log2(n_occupied)
    return h / h_max if h_max > 0 else 0.0

def kl_divergence(p_dist, q_dist, epsilon=1e-9):
    """
    KL(P||Q) sobre dos distribuciones de buckets - mide drift entre periodos.
    epsilon evita log(0).
    """
    keys = set(p_dist.keys()) | set(q_dist.keys())
    p_total = sum(p_dist.values()) or 1
    q_total = sum(q_dist.values()) or 1
    kl = 0.0
    for k in keys:
        p = (p_dist.get(k, 0) + epsilon) / (p_total + epsilon * len(keys))
        q = (q_dist.get(k, 0) + epsilon) / (q_total + epsilon * len(keys))
        kl += p * math.log2(p / q)
    return kl

def get_bucket_distribution(closed_only=False, last_n=None):
    """Cuenta senales por bucket. last_n recorta a las N mas recientes."""
    with _lock:
        conn = _connect()
        try:
            sql = "SELECT bucket_key FROM signals"
            conds = []
            if closed_only:
                conds.append("outcome IS NOT NULL")
            if conds:
                sql += " WHERE " + " AND ".join(conds)
            sql += " ORDER BY id DESC"
            if last_n:
                sql += " LIMIT {}".format(int(last_n))
            rows = conn.execute(sql).fetchall()
            return Counter(r["bucket_key"] for r in rows)
        finally:
            conn.close()

def compute_entropy_metrics():
    """Devuelve dict con H, drift y composicion por dimensiones"""
    all_dist = get_bucket_distribution(closed_only=False)
    closed_dist = get_bucket_distribution(closed_only=True)

    # Drift: ultimas 25 vs anteriores 25
    last_25 = get_bucket_distribution(closed_only=False, last_n=25)
    prev_25 = _get_prev_window_distribution(25, 25)
    kl = kl_divergence(last_25, prev_25) if prev_25 else 0.0

    # Marginales por dimension
    sess_counts = Counter()
    tier_counts = Counter()
    dir_counts  = Counter()
    curv_counts = Counter()
    for bucket, n in all_dist.items():
        parts = bucket.split("|")
        if len(parts) == 4:
            sess_counts[parts[0]] += n
            tier_counts[parts[1]] += n
            dir_counts[parts[2]]  += n
            curv_counts[parts[3]] += n

    return {
        "h_total":        shannon_entropy(all_dist),
        "h_session":      shannon_entropy(sess_counts),
        "h_tier":         shannon_entropy(tier_counts),
        "h_direction":    shannon_entropy(dir_counts),
        "h_curvature":    shannon_entropy(curv_counts),
        "kl_drift_25v25": kl,
        "n_total":        sum(all_dist.values()),
        "n_closed":       sum(closed_dist.values()),
        "n_buckets_active": len(all_dist),
        "session_dist":   dict(sess_counts),
        "tier_dist":      dict(tier_counts),
        "direction_dist": dict(dir_counts),
        "curvature_dist": dict(curv_counts),
    }

def _get_prev_window_distribution(n, offset):
    """Ventana de senales anterior a las ultimas N (skip primeros offset)"""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT bucket_key FROM signals ORDER BY id DESC LIMIT ? OFFSET ?",
                (int(n), int(offset))
            ).fetchall()
            return Counter(r["bucket_key"] for r in rows)
        finally:
            conn.close()

# ============================================================
# KAPPA EVO - modulador suave
# ============================================================
def get_bucket_stats(bucket_key):
    """
    Calcula win-rate y expectancy_R para un bucket dado.
    Solo cuenta senales cerradas.
    Retorna None si insuficientes muestras.
    """
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT outcome, pnl_r FROM signals WHERE bucket_key = ? AND outcome IS NOT NULL",
                (bucket_key,)
            ).fetchall()
        finally:
            conn.close()

    n = len(rows)
    if n < KAPPA_EVO_MIN_SAMPLES:
        return None

    wins = sum(1 for r in rows if r["outcome"] in ("tp1", "tp2", "tp3", "tp4"))
    pnls = [r["pnl_r"] for r in rows if r["pnl_r"] is not None]
    win_rate = wins / n
    expectancy = sum(pnls) / len(pnls) if pnls else 0.0

    return {
        "n":          n,
        "win_rate":   win_rate,
        "expectancy": expectancy,
    }

def compute_kappa_evo(session, tier, direction, curvature_sign_str):
    """
    Devuelve modulador kappa_evo en [1-KAPPA_EVO_MAX, 1+KAPPA_EVO_MAX].

    Logica:
    - Sin data suficiente -> 1.0 (neutral)
    - Bucket con expectancy positiva alta -> hasta 1.15 (afila, da mas peso)
    - Bucket con expectancy negativa -> hasta 0.85 (recorta peso)

    Mapeo: expectancy en [-1.5R, +1.5R] -> kappa en [0.85, 1.15] linealmente,
    clamped en los extremos.
    """
    bucket = make_bucket_key(session, tier, direction, curvature_sign_str)
    stats = get_bucket_stats(bucket)
    if stats is None:
        return 1.0, None

    # Normaliza expectancy a [-1, 1] usando 1.5R como saturacion
    exp_norm = max(-1.0, min(1.0, stats["expectancy"] / 1.5))
    kappa = 1.0 + (exp_norm * KAPPA_EVO_MAX)
    # Clamp duro
    kappa = max(1.0 - KAPPA_EVO_MAX, min(1.0 + KAPPA_EVO_MAX, kappa))

    return kappa, stats

def log_evolution_event(bucket_key, n_samples, win_rate, expectancy_r, kappa_applied):
    with _lock:
        conn = _connect()
        try:
            conn.execute("""
                INSERT INTO evolution_log (ts, bucket_key, n_samples, win_rate, expectancy_r, kappa_applied)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                bucket_key, int(n_samples), float(win_rate),
                float(expectancy_r), float(kappa_applied),
            ))
            conn.commit()
        finally:
            conn.close()

# ============================================================
# REPORTES
# ============================================================
def get_global_metrics():
    """Win-rate global, expectancy, R-distribution"""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT outcome, pnl_r, tier, session, direction FROM signals WHERE outcome IS NOT NULL"
            ).fetchall()
        finally:
            conn.close()

    n = len(rows)
    if n == 0:
        return {"n": 0}

    wins = sum(1 for r in rows if r["outcome"] in ("tp1", "tp2", "tp3", "tp4"))
    sls  = sum(1 for r in rows if r["outcome"] == "sl")
    timeouts = sum(1 for r in rows if r["outcome"] == "timeout")
    pnls = [r["pnl_r"] for r in rows if r["pnl_r"] is not None]
    expectancy = sum(pnls) / len(pnls) if pnls else 0
    avg_win = sum(p for p in pnls if p > 0) / max(1, sum(1 for p in pnls if p > 0))
    avg_loss = sum(p for p in pnls if p < 0) / max(1, sum(1 for p in pnls if p < 0))
    profit_factor = (sum(p for p in pnls if p > 0) /
                     abs(sum(p for p in pnls if p < 0))) if any(p < 0 for p in pnls) else float("inf")

    # TP distribution
    tp_dist = Counter(r["outcome"] for r in rows)

    # Por tier
    tier_perf = defaultdict(lambda: {"n": 0, "wins": 0, "exp": 0})
    for r in rows:
        t = r["tier"]
        tier_perf[t]["n"] += 1
        if r["outcome"] in ("tp1", "tp2", "tp3", "tp4"):
            tier_perf[t]["wins"] += 1
        if r["pnl_r"] is not None:
            tier_perf[t]["exp"] += r["pnl_r"]
    tier_summary = {}
    for t, d in tier_perf.items():
        if d["n"] > 0:
            tier_summary[t] = {
                "n":          d["n"],
                "win_rate":   d["wins"] / d["n"],
                "expectancy": d["exp"] / d["n"],
            }

    return {
        "n":             n,
        "win_rate":      wins / n,
        "wins":          wins,
        "sls":           sls,
        "timeouts":      timeouts,
        "expectancy_r":  expectancy,
        "avg_win_r":     avg_win,
        "avg_loss_r":    avg_loss,
        "profit_factor": profit_factor,
        "tp_dist":       dict(tp_dist),
        "tier_summary":  tier_summary,
    }

def get_recent_signals(n=10):
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT id, ts_emitted, direction, entry_price, p_master_final, "
                "kappa_evo, tier, outcome, pnl_r FROM signals ORDER BY id DESC LIMIT ?",
                (int(n),)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

# ============================================================
# SELF-AUDIT - prompt builder para Opus
# ============================================================
def build_audit_prompt():
    """Construye el prompt de self-audit para Opus"""
    metrics = get_global_metrics()
    entropy = compute_entropy_metrics()

    if metrics["n"] == 0:
        return None

    # Top buckets ganadores y perdedores
    bucket_perf = _bucket_performance_table()
    winners = sorted(bucket_perf, key=lambda x: x["expectancy"], reverse=True)[:5]
    losers  = sorted(bucket_perf, key=lambda x: x["expectancy"])[:5]

    winners_lines = "\n".join(
        "  {} | n={} WR={:.0%} Exp={:+.2f}R".format(
            w["bucket"], w["n"], w["win_rate"], w["expectancy"])
        for w in winners
    )
    losers_lines = "\n".join(
        "  {} | n={} WR={:.0%} Exp={:+.2f}R".format(
            l["bucket"], l["n"], l["win_rate"], l["expectancy"])
        for l in losers
    )

    tier_lines = "\n".join(
        "  {}: n={} WR={:.0%} Exp={:+.2f}R".format(
            t, d["n"], d["win_rate"], d["expectancy"])
        for t, d in metrics["tier_summary"].items()
    )

    return (
        "AUDITORIA SELF-EVOLUCION FQ v4.1 - {} SENALES CERRADAS\n"
        "=========================================================\n\n"
        "DESEMPENO GLOBAL:\n"
        "  Win rate:         {:.1%}\n"
        "  Expectancy:       {:+.2f}R por trade\n"
        "  Avg ganador:      {:+.2f}R\n"
        "  Avg perdedor:     {:+.2f}R\n"
        "  Profit factor:    {:.2f}\n"
        "  TP distribution:  {}\n\n"
        "POR TIER DE CONVICCION:\n{}\n\n"
        "ENTROPIA SHANNON (0=colapsado, 1=diversificado):\n"
        "  H_total:      {:.3f}\n"
        "  H_sesion:     {:.3f}\n"
        "  H_tier:       {:.3f}\n"
        "  H_direccion:  {:.3f}\n"
        "  H_curvatura:  {:.3f}\n"
        "  KL drift 25v25: {:.3f} (>1.5 = cambio de regimen)\n\n"
        "TOP 5 BUCKETS GANADORES:\n{}\n\n"
        "TOP 5 BUCKETS PERDEDORES:\n{}\n\n"
        "DISTRIBUCION DIMENSIONAL:\n"
        "  Sesiones:    {}\n"
        "  Tiers:       {}\n"
        "  Direcciones: {}\n"
        "  Curvatura:   {}\n\n"
        "----\n"
        "Tu trabajo como auditor del sistema:\n\n"
        "1. DIAGNOSTICO: el sistema esta sano, sobreajustado, o en deriva?\n"
        "   Mira H_total, KL drift, y la dispersion de tiers/sesiones/direcciones.\n\n"
        "2. ATRACTORES TOXICOS: hay buckets con muchas senales y expectancy negativa?\n"
        "   Si si, nombralos y propon: subir threshold de ese bucket, o ignorar?\n\n"
        "3. EDGE OCULTO: hay buckets ganadores con pocas muestras (n<8) que valdria\n"
        "   la pena explorar mas? Como invitar a esos setups sin forzar?\n\n"
        "4. SUGERENCIA DE THRESHOLD: el PMASTER_MIN actual es 2.30. Con esta data,\n"
        "   subirias o bajarias? Justifica con numeros.\n\n"
        "5. SUGERENCIA DE COOLDOWN: el cooldown es 1h. Demasiado corto/largo?\n\n"
        "Estas son SUGERENCIAS, no instrucciones. RasDG decide. Maximo 6 parrafos.\n"
        "Se brutalmente honesto - si el edge es marginal, dilo. Si hay un bucket\n"
        "que se ve a leguas que es un casino, exponlo."
    ).format(
        metrics["n"],
        metrics["win_rate"],
        metrics["expectancy_r"],
        metrics["avg_win_r"],
        metrics["avg_loss_r"],
        metrics["profit_factor"],
        metrics["tp_dist"],
        tier_lines,
        entropy["h_total"],
        entropy["h_session"],
        entropy["h_tier"],
        entropy["h_direction"],
        entropy["h_curvature"],
        entropy["kl_drift_25v25"],
        winners_lines or "  (sin data)",
        losers_lines or "  (sin data)",
        entropy["session_dist"],
        entropy["tier_dist"],
        entropy["direction_dist"],
        entropy["curvature_dist"],
    )

def _bucket_performance_table():
    """Tabla de desempeno por bucket con n>=4"""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute("""
                SELECT bucket_key,
                       COUNT(*) as n,
                       SUM(CASE WHEN outcome IN ('tp1','tp2','tp3','tp4') THEN 1 ELSE 0 END) as wins,
                       AVG(pnl_r) as expectancy
                FROM signals
                WHERE outcome IS NOT NULL
                GROUP BY bucket_key
                HAVING n >= 4
            """).fetchall()
        finally:
            conn.close()
    return [
        {
            "bucket":     r["bucket_key"],
            "n":          r["n"],
            "win_rate":   r["wins"] / r["n"] if r["n"] > 0 else 0,
            "expectancy": r["expectancy"] or 0,
        }
        for r in rows
    ]

def save_audit(n_closed, metrics, opus_response):
    with _lock:
        conn = _connect()
        try:
            entropy = compute_entropy_metrics()
            conn.execute("""
                INSERT INTO audits (ts, n_closed, win_rate, expectancy_r, entropy_h, kl_drift, opus_response, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                int(n_closed),
                float(metrics.get("win_rate", 0)),
                float(metrics.get("expectancy_r", 0)),
                float(entropy["h_total"]),
                float(entropy["kl_drift_25v25"]),
                opus_response or "",
                json.dumps({"metrics": metrics, "entropy": entropy}, default=str),
            ))
            conn.commit()
        finally:
            conn.close()

def should_trigger_audit():
    """Devuelve True si toca audit basado en N senales cerradas"""
    n_closed = count_signals(closed_only=True)
    if n_closed == 0:
        return False
    if n_closed % AUDIT_EVERY_N_CLOSED != 0:
        return False
    # Anti-doble-trigger: revisa si ya hubo audit en este threshold
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT MAX(n_closed) as last_n FROM audits"
            ).fetchone()
            last_audit_n = row["last_n"] or 0
        finally:
            conn.close()
    return n_closed > last_audit_n

# ============================================================
# BACKUP
# ============================================================
def export_db_path():
    """Devuelve path del .db para backup via Telegram"""
    return DB_PATH if os.path.exists(DB_PATH) else None

def export_ledger_csv():
    """Exporta ledger a CSV string para mensajes ligeros"""
    if pd is None:
        return None
    with _lock:
        conn = _connect()
        try:
            df = pd.read_sql_query(
                "SELECT id, ts_emitted, direction, entry_price, p_master_final, "
                "kappa_evo, tier, session, bucket_key, outcome, pnl_r FROM signals "
                "ORDER BY id DESC",
                conn
            )
        finally:
            conn.close()
    return df.to_csv(index=False)

def should_trigger_backup():
    """Cada N senales totales (abiertas o cerradas) hace backup"""
    n = count_signals(closed_only=False)
    if n == 0 or n % BACKUP_EVERY_N_SIGNED != 0:
        return False
    return True

# ============================================================
# FORMATEO TELEGRAM
# ============================================================
def format_metrics_telegram():
    """Mensaje compacto de metricas globales"""
    m = get_global_metrics()
    if m["n"] == 0:
        return "Sin senales cerradas aun."
    pf = "{:.2f}".format(m["profit_factor"]) if m["profit_factor"] != float("inf") else "inf"
    lines = [
        "<b>METRICAS FQ EVOLUTION</b>",
        "Senales cerradas: {}".format(m["n"]),
        "Win rate: {:.1%}  ({} W / {} SL / {} timeout)".format(
            m["win_rate"], m["wins"], m["sls"], m["timeouts"]),
        "Expectancy: {:+.2f}R / trade".format(m["expectancy_r"]),
        "Avg ganador: {:+.2f}R | Avg perdedor: {:+.2f}R".format(
            m["avg_win_r"], m["avg_loss_r"]),
        "Profit factor: {}".format(pf),
        "",
        "<b>Por tier:</b>",
    ]
    for t, d in m["tier_summary"].items():
        lines.append("  {}: n={} WR={:.0%} Exp={:+.2f}R".format(
            t, d["n"], d["win_rate"], d["expectancy"]))
    lines.append("")
    lines.append("TPs alcanzados: {}".format(m["tp_dist"]))
    return "\n".join(lines)

def format_entropy_telegram():
    """Mensaje compacto de entropia"""
    e = compute_entropy_metrics()
    if e["n_total"] == 0:
        return "Sin data entropica aun."
    drift_label = "ESTABLE"
    if e["kl_drift_25v25"] > 1.5:
        drift_label = "DERIVA - cambio regimen"
    elif e["kl_drift_25v25"] > 0.7:
        drift_label = "atencion - shift moderado"
    return (
        "<b>COGNICION ENTROPICA FQ</b>\n"
        "Senales totales: {} ({} cerradas)\n"
        "Buckets activos: {}\n\n"
        "<b>Shannon H (0=colapso, 1=diverso):</b>\n"
        "  Total:      {:.3f}\n"
        "  Sesion:     {:.3f}\n"
        "  Tier:       {:.3f}\n"
        "  Direccion:  {:.3f}\n"
        "  Curvatura:  {:.3f}\n\n"
        "<b>Drift KL (25v25):</b> {:.3f}  -> {}\n\n"
        "<b>Distribucion sesiones:</b>\n  {}\n"
        "<b>Distribucion tiers:</b>\n  {}\n"
        "<b>Distribucion direcciones:</b>\n  {}"
    ).format(
        e["n_total"], e["n_closed"], e["n_buckets_active"],
        e["h_total"], e["h_session"], e["h_tier"],
        e["h_direction"], e["h_curvature"],
        e["kl_drift_25v25"], drift_label,
        e["session_dist"], e["tier_dist"], e["direction_dist"],
    )

def format_ledger_telegram(n=10):
    """Ultimas N senales del ledger"""
    rows = get_recent_signals(n)
    if not rows:
        return "Ledger vacio."
    lines = ["<b>ULTIMAS {} SENALES</b>".format(len(rows)), ""]
    for r in rows:
        ts = r["ts_emitted"][:16].replace("T", " ")
        outcome = r["outcome"] or "OPEN"
        pnl = ""
        if r["pnl_r"] is not None:
            pnl = " ({:+.2f}R)".format(r["pnl_r"])
        kappa_marker = ""
        if r["kappa_evo"] != 1.0:
            kappa_marker = " k={:.2f}".format(r["kappa_evo"])
        lines.append("#{} {} {} P={:.2f}{} [{}] {}{}".format(
            r["id"], ts, r["direction"].upper()[0],
            r["p_master_final"], kappa_marker, r["tier"],
            outcome, pnl
        ))
    return "\n".join(lines)
