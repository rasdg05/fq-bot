# -*- coding: utf-8 -*-
"""
================================================================================
  ENTROPY COGNITION MODULE - FQ v5.1 Bot "EVOLUTION PATCH"
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

import ledger_stats

log = logging.getLogger("fq_entropy")

# ============================================================
# CONFIG
# ============================================================
def _resolve_db_path():
    """Default persistente: /data si existe (Railway volume), si no /tmp con warning"""
    forced = os.environ.get("FQ_LEDGER_PATH")
    if forced:
        return forced
    if os.path.isdir("/data") and os.access("/data", os.W_OK):
        return "/data/fq_ledger.db"
    sys.stderr.write(
        "[WARN] /data no montado - ledger en /tmp/fq_ledger.db (EFIMERO en Railway)\n"
        "       Monta un Railway Volume en /data o setea FQ_LEDGER_PATH explicito.\n"
    )
    return "/tmp/fq_ledger.db"

DB_PATH               = _resolve_db_path()
KAPPA_EVO_MAX         = 0.15           # +-15% modulador
KAPPA_EVO_MIN_SAMPLES = 8              # min senales cerradas en bucket para modular
AUDIT_EVERY_N_CLOSED  = 25             # trigger self-audit
OUTCOME_TIMEOUT_HOURS = int(os.environ.get("FQ_OUTCOME_TIMEOUT_HOURS", "8"))

# --- Auditabilidad: un solo predicado para TODO lo que lee outcomes ---------
# Mismo invariante que ledger_stats.is_auditable, expresado en SQL para las
# rutas que agregan en la base. Importa que este filtro cubra tambien el
# APRENDIZAJE (kappa, buckets, entropia), no solo el numero publicado: si el
# bloque corrupto del 10-jun alimenta la evolucion de kappa, el sistema no
# solo miente hacia fuera — se ajusta hacia dentro contra desenlaces que nunca
# ocurrieron. Se compone con AND sobre las clausulas existentes.
AUDITABLE_SQL = (
    "outcome IS NOT NULL "
    "AND outcome != 'stale' "
    "AND (minutes_open IS NULL OR minutes_open <= {}) ".format(
        ledger_stats.MAX_AUDITABLE_MINUTES)
)
BACKUP_EVERY_N_SIGNED = int(os.environ.get("FQ_BACKUP_EVERY_N", "50"))
PHI                   = 1.6180339887
PHI_SQ                = PHI * PHI
PHI_CB                = PHI ** 3

# Guard para evitar re-envio del mismo backup en cada tick del hook.
# evolution_periodic_hook se llama por cada cierre de vela en cada TF; sin este
# guard, mientras n no cambie, should_trigger_backup() retorna True en cada tick.
_last_backup_n_sent = None

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
    outcome         TEXT,           -- 'tp1'..'tp4','sl','timeout','stale'
                                    -- (stale = la ventana de velas no cubre el
                                    --  inicio de la senal: outcome no auditable,
                                    --  pnl_r=0 y NO cuenta como win)
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

CREATE TABLE IF NOT EXISTS signal_progress (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER NOT NULL,
    event       TEXT NOT NULL,        -- 'tp1_hit','tp2_hit','tp3_hit','be_suggested','partial_suggested'
    ts_event    TEXT NOT NULL,
    price       REAL,
    UNIQUE(signal_id, event)
);

CREATE INDEX IF NOT EXISTS idx_progress_sig ON signal_progress(signal_id);

-- ALERTAS TACTICAS (v5.4): el RADAR/alerta tactica no entra a 'signals' (no es
-- senal automatica del ledger). Se persiste aparte para seguirla en vivo y
-- emitir guia operativa (SL a BE en TP1, parcial en TP2, trailing en TP3) sin
-- tocar el ledger ni las metricas del motor.
CREATE TABLE IF NOT EXISTS tactical_signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tf          TEXT,
    direction   TEXT NOT NULL,
    entry       REAL NOT NULL,
    sl          REAL,
    tp1         REAL,
    tp2         REAL,
    tp3         REAL,
    ts_emitted  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open'   -- 'open' | 'closed:tp3|sl|expiry'
);

CREATE TABLE IF NOT EXISTS tactical_progress (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tactical_id INTEGER NOT NULL,
    event       TEXT NOT NULL,        -- 'tp1_hit','tp2_hit','tp3_hit','be_suggested','partial_suggested'
    ts_event    TEXT NOT NULL,
    price       REAL,
    UNIQUE(tactical_id, event)
);

CREATE INDEX IF NOT EXISTS idx_tactical_status ON tactical_signals(status);
CREATE INDEX IF NOT EXISTS idx_tactical_prog   ON tactical_progress(tactical_id);
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

_BUCKET_ANCHOR_TF = "15m"  # TF que preserva memoria historica (sin sufijo)

def make_bucket_key(session, tier, direction, curvature_sign, tf_id=None):
    """
    bucket = sesion + tier + direccion + signo de curvatura [+ timeframe]
    curvature_sign: 'pos' si support_w > resistance_w, 'neg' al reves, 'flat' si ~0
    tf_id: timeframe opcional. Si es '15m' (anchor) se omite el sufijo para
    preservar continuidad con buckets historicos pre-multi-TF; 5m y 1h
    reciben sufijo para segregar memoria (cold start intencional).
    """
    base = "{}|{}|{}|{}".format(session, tier, direction, curvature_sign)
    if tf_id and tf_id != _BUCKET_ANCHOR_TF:
        return "{}|{}".format(base, tf_id)
    return base

def curvature_sign(support_w, resistance_w):
    diff = support_w - resistance_w
    if abs(diff) < 0.3:
        return "flat"
    return "pos" if diff > 0 else "neg"

# ============================================================
# LEDGER - registro de senales
# ============================================================
def log_signal(signal_data, symbol="SOL"):
    """
    Inserta una senal nueva al ledger. Devuelve signal_id.

    signal_data debe incluir:
      direction, entry, sl, tp1, tp2, tp3, tp4,
      p_master_raw, p_master_final, kappa_evo,
      session, w_clock, pspace_count,
      support_weight, resistance_weight,
      macro_btc, macro_eth, rsi6, rsi12, rsi24, h_lap_active,
      snapshot (dict completo)

    symbol: 'SOL' (default, comportamiento historico) / 'BTC' / 'ETH'. Cerebro
    Etapa 0 (2026-07-20): permite grabar fires BTC/ETH en el mismo ledger rico
    sin tocar bucket_key_v2/v3 (quedan NULL para estas filas a proposito, asi
    quedan fuera de la maquinaria de auto-evolucion/Thompson-kappa de SOL sin
    necesidad de filtrar ahi tambien).
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
                    bucket_key, snapshot_json, symbol
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                symbol,
            ))
            conn.commit()
            sid = cur.lastrowid
            log.info("Ledger: senal #{} registrada bucket={} symbol={}".format(
                sid, bucket, symbol))
            return sid
        except Exception as e:
            log.error("Ledger insert error: {}".format(e))
            return None
        finally:
            conn.close()

def get_open_signals(symbol="SOL"):
    """Devuelve lista de senales sin outcome cerrado. symbol default 'SOL'
    (comportamiento historico byte-identico); pasa 'BTC'/'ETH' para
    reconciliar esos motores contra su propio OHLCV."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM signals WHERE outcome IS NULL AND symbol = ? ORDER BY id",
                (symbol,)
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

def count_signals(closed_only=False, symbol="SOL"):
    """symbol default 'SOL': la cadencia de self-audit/backup (should_trigger_
    audit/backup) sigue atada SOLO al conteo de SOL, no al total mezclado con
    BTC/ETH."""
    with _lock:
        conn = _connect()
        try:
            if closed_only:
                row = conn.execute(
                    "SELECT COUNT(*) as n FROM signals WHERE " + AUDITABLE_SQL + "AND symbol = ?",
                    (symbol,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) as n FROM signals WHERE symbol = ?", (symbol,)
                ).fetchone()
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
    al ts_emitted y ANTERIORES O IGUALES al horizonte (ts_emitted +
    OUTCOME_TIMEOUT_HOURS): la senal solo puede resolverse dentro de su propia
    vida util.

    HORIZONTE DURO (fix del 'fantasma' de jun-2026)
    -----------------------------------------------
    Antes este barrido recorria TODAS las velas posteriores a la emision sin
    tope, y el timeout se evaluaba DESPUES del bucle (solo si no se habia
    tocado nada). Consecuencia: una senal que debia morir por timeout a las 8h
    seguia "viva" indefinidamente hasta encontrar su TP, y al volver el tracker
    tras un downtime se le acreditaba un TP4 tocado semanas mas tarde. El
    10-jun-2026 eso cerro 23 senales de mayo en 763 ms, todas tp4 (shorts) o sl
    (longs) — el resultado era una funcion de la direccion y de una caida del
    -21% en SOL, no del sistema. Ese bloque inflaba el track record publico a
    E[R]=+1.84 mientras el motor con fees marcaba -0.51R.

    Ahora el horizonte se aplica ANTES de iterar: si ninguna vela DENTRO de la
    ventana de vida toca un nivel, el outcome es 'timeout' al cierre de la
    ultima vela del horizonte. Un TP tocado despues del horizonte ya no existe
    para el ledger, que es exactamente el trade que el usuario habria cerrado.
    """
    ts_emitted = _ts_emitted_utc(signal_row)
    now = datetime.now(timezone.utc)
    horizon = ts_emitted + timedelta(hours=OUTCOME_TIMEOUT_HOURS)

    # Filtra velas post-emision. Las velas OHLCV vienen en UTC pero tz-naive
    # (datetime64[ms]); ts_emitted es tz-aware. Pandas NO compara naive vs aware
    # ("Invalid comparison between dtype=datetime64[ms] and Timestamp"), asi que
    # normalizamos AMBOS lados a UTC tz-naive antes de comparar.
    cutoff = pd.Timestamp(ts_emitted).tz_localize(None)
    horizon_naive = pd.Timestamp(horizon).tz_localize(None)
    ts_col = df["timestamp"]
    if getattr(ts_col.dtype, "tz", None) is not None:
        ts_col = ts_col.dt.tz_convert("UTC").dt.tz_localize(None)
    df_post = df[ts_col > cutoff]
    if len(df_post) == 0:
        return None  # aun no hay velas posteriores

    # Ventana de vida: solo las velas hasta el horizonte pueden resolver la
    # senal. df_life se re-filtra sobre la misma columna normalizada.
    life_mask = (ts_col > cutoff) & (ts_col <= horizon_naive)
    df_life = df[life_mask]
    ts_life = ts_col[life_mask]

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
    # Iteramos vela por vela en orden cronologico DENTRO DEL HORIZONTE.
    # Si en la misma vela tocan SL y TP, conservadoramente asumimos SL primero (peor caso).
    for pos, (_, row) in enumerate(df_life.iterrows()):
        hi = float(row["high"])
        lo = float(row["low"])
        ts_bar = ts_life.iloc[pos]
        if direction == "long":
            if lo <= sl:
                return _build_outcome("sl", sl, entry, sl, direction, ts_emitted, ts_bar)
            if hi >= tp4:
                return _build_outcome("tp4", tp4, entry, sl, direction, ts_emitted, ts_bar)
            if hi >= tp3:
                return _build_outcome("tp3", tp3, entry, sl, direction, ts_emitted, ts_bar)
            if hi >= tp2:
                return _build_outcome("tp2", tp2, entry, sl, direction, ts_emitted, ts_bar)
            if hi >= tp1:
                return _build_outcome("tp1", tp1, entry, sl, direction, ts_emitted, ts_bar)
        else:  # short
            if hi >= sl:
                return _build_outcome("sl", sl, entry, sl, direction, ts_emitted, ts_bar)
            if lo <= tp4:
                return _build_outcome("tp4", tp4, entry, sl, direction, ts_emitted, ts_bar)
            if lo <= tp3:
                return _build_outcome("tp3", tp3, entry, sl, direction, ts_emitted, ts_bar)
            if lo <= tp2:
                return _build_outcome("tp2", tp2, entry, sl, direction, ts_emitted, ts_bar)
            if lo <= tp1:
                return _build_outcome("tp1", tp1, entry, sl, direction, ts_emitted, ts_bar)

    # Ninguna vela DENTRO del horizonte resolvio la senal.
    #   - Si el horizonte ya paso y TENEMOS velas de su vida: timeout honesto,
    #     al cierre de la ultima vela del horizonte.
    #   - Si el horizonte paso pero la ventana no alcanza ninguna vela de su
    #     vida, no es auditable -> 'stale' (pnl_r=0, no ensucia expectancy).
    #     En la practica reconcile_outcomes ya lo filtra con _covers_signal;
    #     esto es el cinturon por si se llama a la funcion directamente.
    #   - Si aun no paso: la senal sigue viva, no se decide nada.
    if now >= horizon:
        if len(df_life) > 0:
            return _build_outcome("timeout", float(df_life["close"].iloc[-1]),
                                  entry, sl, direction, ts_emitted,
                                  ts_life.iloc[-1])
        return {"outcome": "stale", "exit_price": float(df_post["close"].iloc[-1]),
                "pnl_r": 0.0, "minutes_open": OUTCOME_TIMEOUT_HOURS * 60}

    return None  # sigue abierta

def _build_outcome(outcome, exit_price, entry, sl, direction, ts_emitted,
                   ts_exit=None):
    """Construye el outcome. ts_exit es el timestamp de la VELA que resolvio la
    senal: minutes_open se mide contra el, no contra datetime.now(). Medirlo
    contra 'ahora' era lo que producia los 43.611 minutos abiertos del bloque
    fantasma (una senal cerrada por una vela de hace tres semanas figuraba
    abierta hasta el instante del reconcile)."""
    risk = abs(entry - sl)
    if direction == "long":
        pnl = exit_price - entry
    else:
        pnl = entry - exit_price
    pnl_r = pnl / risk if risk > 0 else 0
    ref = _as_utc(ts_exit) if ts_exit is not None else datetime.now(timezone.utc)
    minutes_open = max(0, int((ref - ts_emitted).total_seconds() / 60))
    # Cota dura: por construccion una senal no puede vivir mas que su horizonte.
    minutes_open = min(minutes_open, OUTCOME_TIMEOUT_HOURS * 60)
    return {
        "outcome":      outcome,
        "exit_price":   exit_price,
        "pnl_r":        pnl_r,
        "minutes_open": minutes_open,
    }


def _as_utc(ts):
    """Normaliza a datetime tz-aware UTC. Acepta pd.Timestamp (tz-naive, que es
    como llegan las velas), datetime naive o datetime aware."""
    if isinstance(ts, datetime):
        return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    ts = pd.Timestamp(ts)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.to_pydatetime()

# Necesita pandas - import local para evitar circulos
try:
    import pandas as pd
except ImportError:
    pd = None

# --- ventana del reconcile -------------------------------------------------
# El limite fijo de 50 velas (15m ~12.5h; 5m ~4.2h) era MENOR que la vida
# posible de una senal (timeout 8h + downtime del bot): las velas del hueco no
# se veian y la senal se cerraba contra precio reciente -> outcome inventado y
# sesgado optimista. Ahora la ventana se dimensiona por la senal abierta mas
# vieja (cap FQ_RECONCILE_MAX_CANDLES: una sola llamada al exchange, OKX capea
# ~300 velas por request) y, si aun asi la ventana NO cubre el inicio de una
# senal, se cierra como 'stale' (no auditable) en vez de inventar.
RECONCILE_BASE_CANDLES = 50
RECONCILE_MAX_CANDLES  = int(os.environ.get("FQ_RECONCILE_MAX_CANDLES", "300"))
RECONCILE_MARGIN_BARS  = 5
RECONCILE_RUNT_MIN     = 40   # fetch sospechosamente corto: no decidir 'stale'

_TF_MINUTES = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
               "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720,
               "1d": 1440}

# tf_id NULL en el ledger = senal anterior a schema v4 (ancla 15m, igual que
# el backfill de la migracion y _BUCKET_ANCHOR_TF).
_RECONCILE_ANCHOR_TF = "15m"


def _tf_minutes(timeframe):
    tf = (timeframe or "").strip().lower()
    if tf in _TF_MINUTES:
        return _TF_MINUTES[tf]
    try:
        if tf.endswith("m"):
            return max(1, int(tf[:-1]))
        if tf.endswith("h"):
            return int(tf[:-1]) * 60
        if tf.endswith("d"):
            return int(tf[:-1]) * 1440
    except ValueError:
        pass
    return 15


def _ts_emitted_utc(sig):
    ts = datetime.fromisoformat(sig["ts_emitted"])
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _bars_to_cover(open_sigs, timeframe, now=None):
    """Velas necesarias para que la ventana llegue a la senal abierta mas
    vieja (+margen). Clampa a [RECONCILE_BASE_CANDLES, RECONCILE_MAX_CANDLES]."""
    now = now or datetime.now(timezone.utc)
    tf_min = _tf_minutes(timeframe)
    oldest_min = 0.0
    for sig in open_sigs:
        try:
            age = (now - _ts_emitted_utc(sig)).total_seconds() / 60.0
            oldest_min = max(oldest_min, age)
        except Exception:
            continue
    bars = int(math.ceil(oldest_min / tf_min)) + RECONCILE_MARGIN_BARS
    return min(max(bars, RECONCILE_BASE_CANDLES), RECONCILE_MAX_CANDLES)


def _coverage_start_naive(df):
    """Primer timestamp de la ventana, normalizado a UTC tz-naive (misma
    convencion que check_outcome_against_candles)."""
    ts_col = df["timestamp"]
    if getattr(ts_col.dtype, "tz", None) is not None:
        ts_col = ts_col.dt.tz_convert("UTC").dt.tz_localize(None)
    return ts_col.min()


def _covers_signal(sig, coverage_start, tf_minutes_):
    """True si la ventana alcanza el inicio de vida de la senal. Tolerancia de
    UNA vela: la primera vela que el tracker necesita es la primera con
    timestamp > ts_emitted (estrictamente posterior, como en
    check_outcome_against_candles)."""
    cutoff = pd.Timestamp(_ts_emitted_utc(sig)).tz_localize(None)
    return coverage_start <= cutoff + pd.Timedelta(minutes=tf_minutes_)


def _stale_outcome(sig, df):
    """Cierre 'stale': la vida temprana de la senal cayo FUERA de la ventana
    (un TP/SL pudo tocarse en el hueco y no es verificable). pnl_r=0 neutral:
    ningun consumidor lo cuenta como win y no ensucia la expectancy."""
    last_close = float(df["close"].iloc[-1])
    # minutes_open acotado al horizonte: una senal 'stale' no vivio mas que su
    # timeout, solo que no pudimos verla morir. Sin la cota, un downtime largo
    # escribia vidas de semanas en el ledger (ver check_outcome_against_candles).
    elapsed = int(
        (datetime.now(timezone.utc) - _ts_emitted_utc(sig)).total_seconds() / 60)
    minutes_open = max(0, min(elapsed, OUTCOME_TIMEOUT_HOURS * 60))
    return {"outcome": "stale", "exit_price": last_close, "pnl_r": 0.0,
            "minutes_open": minutes_open}


def reconcile_outcomes(fetch_ohlcv_fn, exchange, symbol, timeframe="15m", ccy="SOL"):
    """
    Recorre las senales abiertas de UN symbol (ccy: 'SOL' default/'BTC'/'ETH'),
    fetchea velas recientes de ESE symbol y resuelve outcomes posibles.
    Devuelve lista de senales recien cerradas.

    ccy DEBE coincidir con el symbol/exchange-symbol que se esta fetcheando
    (ej. ccy='BTC' junto a symbol=SYMBOL_BTC): reconciliar senales BTC contra
    velas de SOL (o viceversa) produciria outcomes basura (escalas de precio
    incompatibles). Default 'SOL' preserva el comportamiento historico de las
    llamadas existentes (SOL es el unico symbol que reconciliaba hasta ahora).

    Ventana: dimensionada para cubrir la senal abierta mas vieja (una sola
    fetch, cap FQ_RECONCILE_MAX_CANDLES). Si una senal nacio ANTES de la
    primera vela disponible, su outcome no es auditable (el hueco nunca sana:
    la ventana solo avanza) -> se cierra como 'stale', pero SOLO en el pase
    del TF que origino la senal (tf_id; NULL = ancla 15m): asi el pase 5m no
    mata senales de 15m/1h que su propio pase, con ventana mas larga en
    tiempo-pared, si puede auditar. Las senales cubiertas se resuelven igual
    que siempre (cualquier pase puede cerrarlas).
    """
    if pd is None:
        log.error("pandas no disponible para reconcile_outcomes")
        return []

    open_sigs = get_open_signals(symbol=ccy)
    if not open_sigs:
        return []

    # Una sola fetch, dimensionada por la senal abierta mas vieja.
    limit = _bars_to_cover(open_sigs, timeframe)
    try:
        df = fetch_ohlcv_fn(exchange, symbol, timeframe, limit=limit)
    except Exception as e:
        log.error("reconcile fetch_ohlcv error: {}".format(e))
        return []
    if df is None or len(df) == 0:
        log.warning("reconcile [{}]: fetch devolvio 0 velas (skip)".format(timeframe))
        return []

    tf_min = _tf_minutes(timeframe)
    coverage_start = _coverage_start_naive(df)
    # Guard anti-runt: si el fetch volvio sospechosamente corto (hiccup del
    # exchange), este ciclo no toma decisiones de 'stale' (las senales siguen
    # abiertas y el proximo tick decide).
    can_stale = len(df) >= min(limit, RECONCILE_RUNT_MIN)

    closed = []
    for sig in open_sigs:
        try:
            if not _covers_signal(sig, coverage_start, tf_min):
                sig_tf = sig.get("tf_id") or _RECONCILE_ANCHOR_TF
                if not can_stale or sig_tf != timeframe:
                    continue   # lo juzga el pase de su propio TF
                result = _stale_outcome(sig, df)
                close_signal(sig["id"], result["outcome"], result["exit_price"],
                             result["pnl_r"], result["minutes_open"])
                log.warning(
                    "reconcile [{}]: senal #{} mas vieja que la ventana "
                    "({} velas desde {}): outcome=stale (no auditable)".format(
                        timeframe, sig["id"], len(df), coverage_start))
                closed.append({**sig, **result})
                continue
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

def get_bucket_distribution(closed_only=False, last_n=None, symbol="SOL"):
    """Cuenta senales por bucket. last_n recorta a las N mas recientes.
    symbol default 'SOL': la entropia/self-audit de SOL queda byte-identica
    (no se mezcla con la distribucion de buckets de BTC/ETH)."""
    with _lock:
        conn = _connect()
        try:
            sql = "SELECT bucket_key FROM signals"
            conds = ["symbol = ?"]
            params = [symbol]
            if closed_only:
                conds.append(AUDITABLE_SQL)
            sql += " WHERE " + " AND ".join(conds)
            sql += " ORDER BY id DESC"
            if last_n:
                sql += " LIMIT {}".format(int(last_n))
            rows = conn.execute(sql, params).fetchall()
            return Counter(r["bucket_key"] for r in rows)
        finally:
            conn.close()

def compute_entropy_metrics(symbol="SOL"):
    """Devuelve dict con H, drift y composicion por dimensiones. symbol
    default 'SOL' (byte-identico; ver get_bucket_distribution)."""
    all_dist = get_bucket_distribution(closed_only=False, symbol=symbol)
    closed_dist = get_bucket_distribution(closed_only=True, symbol=symbol)

    # Drift: ultimas 25 vs anteriores 25
    last_25 = get_bucket_distribution(closed_only=False, last_n=25, symbol=symbol)
    prev_25 = _get_prev_window_distribution(25, 25, symbol=symbol)
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

def _get_prev_window_distribution(n, offset, symbol="SOL"):
    """Ventana de senales anterior a las ultimas N (skip primeros offset).
    symbol default 'SOL' (ver get_bucket_distribution)."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT bucket_key FROM signals WHERE symbol = ? "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (symbol, int(n), int(offset))
            ).fetchall()
            return Counter(r["bucket_key"] for r in rows)
        finally:
            conn.close()

# ============================================================
# KAPPA EVO - modulador suave
# ============================================================
def get_bucket_stats(bucket_key, symbol="SOL"):
    """
    Calcula win-rate y expectancy_R para un bucket dado.
    Solo cuenta senales cerradas.
    Retorna None si insuficientes muestras.

    symbol default 'SOL': protege el modulador kappa_evo (que afila P_master
    EN VIVO) de mezclarse con el historico de BTC/ETH -- un bucket_key
    coarse (session|tier|direction|curvatura) puede coincidir entre simbolos.
    """
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT outcome, pnl_r FROM signals "
                "WHERE bucket_key = ? AND " + AUDITABLE_SQL + "AND symbol = ?",
                (bucket_key, symbol)
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

def compute_kappa_evo(session, tier, direction, curvature_sign_str, symbol="SOL"):
    """
    Devuelve modulador kappa_evo en [1-KAPPA_EVO_MAX, 1+KAPPA_EVO_MAX].

    Logica:
    - Sin data suficiente -> 1.0 (neutral)
    - Bucket con expectancy positiva alta -> hasta 1.15 (afila, da mas peso)
    - Bucket con expectancy negativa -> hasta 0.85 (recorta peso)

    Mapeo: expectancy en [-1.5R, +1.5R] -> kappa en [0.85, 1.15] linealmente,
    clamped en los extremos. symbol default 'SOL' (ver get_bucket_stats).
    """
    bucket = make_bucket_key(session, tier, direction, curvature_sign_str)
    stats = get_bucket_stats(bucket, symbol=symbol)
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
def get_global_metrics(symbol="SOL"):
    """Win-rate global, expectancy, R-distribution. symbol default 'SOL'
    (/metrics admin sigue mostrando SOLO SOL, byte-identico)."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT outcome, pnl_r, tier, session, direction FROM signals "
                "WHERE " + AUDITABLE_SQL + "AND symbol = ?",
                (symbol,)
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

def get_recent_signals(n=10, symbol=None):
    """/ledger admin: feed crudo de actividad reciente. symbol=None (default)
    -> TODOS los simbolos mezclados (Cerebro Etapa 0: admin ve BTC/ETH ahora
    que se registran, no solo SOL); pasa 'SOL'/'BTC'/'ETH' para filtrar uno.
    A diferencia de las metricas agregadas (get_global_metrics/
    get_results_summary), este es un feed de EVENTOS, no un numero de
    track-record -- mezclar simbolos aqui no cambia el significado de nada."""
    with _lock:
        conn = _connect()
        try:
            if symbol:
                rows = conn.execute(
                    "SELECT id, ts_emitted, direction, entry_price, p_master_final, "
                    "kappa_evo, tier, outcome, pnl_r, symbol FROM signals "
                    "WHERE symbol = ? ORDER BY id DESC LIMIT ?",
                    (symbol, int(n))
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, ts_emitted, direction, entry_price, p_master_final, "
                    "kappa_evo, tier, outcome, pnl_r, symbol FROM signals "
                    "ORDER BY id DESC LIMIT ?",
                    (int(n),)
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

# ============================================================
# AUDITORIA DEL LEDGER DE SENALES (Reconciler cableado a lo que se publica)
# ============================================================
# Estado de salud del ledger de senales. Lo escribe audit_signal_ledger() y lo
# leen get_results_summary() / el bot publico ANTES de publicar nada.
_ledger_health = {
    "ok": True,          # False -> el tracker esta produciendo cierres imposibles
    "reasons": [],
    "ts": None,
    "n": None,
    "live_expectancy_r": None,
}


def get_closed_rows_for_audit(symbol="SOL"):
    """Filas cerradas crudas (SIN filtrar) para el auditor. Sin filtrar a
    proposito: el auditor necesita VER las filas malas para detectarlas."""
    with _lock:
        conn = _connect()
        try:
            return conn.execute(
                "SELECT outcome, pnl_r, ts_closed, minutes_open FROM signals "
                "WHERE outcome IS NOT NULL AND symbol = ? ORDER BY ts_closed ASC",
                (symbol,)
            ).fetchall()
        finally:
            conn.close()


def signal_ledger_is_trusted():
    """True si el ultimo audit no encontro cierres imposibles recientes."""
    return bool(_ledger_health.get("ok", True))


def get_ledger_health():
    return dict(_ledger_health)


def audit_signal_ledger(symbol="SOL", baseline_r=None, min_trades=20,
                        lookback_days=7):
    """Corre el Reconciler contra el ledger de SENALES (lo que se publica).

    Hasta ahora el Reconciler solo auditaba los HashLedger de gold/funding
    paper — y apagado por defecto. El track record de clientes salia de
    fq_ledger.db sin auditor alguno, y por ahi entro el bloque del 10-jun.
    Esto cierra el lazo.

    Consecuencia de un fallo de integridad: se marca el ledger como NO fiable
    y get_results_summary() deja de devolver numeros. Es deliberado que la
    consecuencia sea "callar" y no "seguir emitiendo un numero con asterisco":
    un track record que no se puede defender no se publica.

    baseline_r: expectancy de referencia (p.ej. la del motor paper con fees).
    Si es None solo se comprueba integridad, no drift.
    """
    import reconciler as rc

    view = rc.SignalLedgerView(
        fetch_rows=lambda: get_closed_rows_for_audit(symbol),
        lookback_days=lookback_days,
    )
    reasons = []
    ok = True

    if not view.verify():
        ok = False
        reasons.append(
            "cierres NO auditables en los ultimos {}d: minutes_open supera el "
            "horizonte de {}h. El tracker de outcomes esta roto -> track "
            "record suspendido.".format(lookback_days, OUTCOME_TIMEOUT_HOURS))

    live = rc.extract_closed_r(view)
    n = len(live)
    live_exp = (sum(live) / n) if n else None

    if ok and baseline_r is not None and n >= min_trades:
        try:
            import bt_forward
            recon = bt_forward.reconcile(float(baseline_r), live, ci=0.90)
            if (recon.get("within") is False
                    and live_exp is not None
                    and live_exp < float(baseline_r)):
                reasons.append(
                    "DRIFT a la baja: expectancy viva {:+.3f}R < baseline "
                    "{:+.3f}R y fuera del IC (n={})".format(
                        live_exp, float(baseline_r), n))
        except Exception as e:
            log.warning("audit_signal_ledger: reconcile fallo (%s)", e)

    # E4: el audit no solo escribe un flag, CORTA EL NODO. Todo lo que cuelgue
    # de `tracker.outcomes` deja de ser publicable automaticamente, sin que
    # nadie tenga que acordarse de que afirmaciones caen — que es exactamente
    # lo que fallo en julio (el repo sabia y siguio publicando).
    try:
        import provenance
        if ok:
            provenance.heal_node("tracker.outcomes")
        else:
            provenance.break_node("tracker.outcomes", reasons[0] if reasons
                                  else "audit sin veredicto")
    except Exception as e:
        log.warning("audit_signal_ledger: procedencia no actualizada (%s)", e)

    _ledger_health.update({
        "ok": ok,
        "reasons": reasons,
        "ts": datetime.now(timezone.utc).isoformat(),
        "n": n,
        "live_expectancy_r": live_exp,
    })
    if reasons:
        for r in reasons:
            log.error("[audit ledger senales] %s", r)
    return dict(_ledger_health)


def get_results_summary(symbol="SOL"):
    """
    Track record verificable desde el ledger propio (acceso directo VIP).
    Misma forma de dict que public_outcome_announcer.compute_results_summary,
    via la estadistica compartida de ledger_stats. None si no hay cierres.

    symbol default 'SOL': /resultados es el numero que se le muestra a
    CLIENTES -- no se diluye/mezcla con BTC/ETH sin una decision explicita
    de producto (RasDG). Combinar los 3 track records es un cambio de
    producto deliberado, no un efecto secundario de cerrar el gap del ledger.

    Devuelve None si el ultimo audit marco el ledger como NO fiable: un track
    record que no se puede defender no se publica (ver audit_signal_ledger).
    """
    if not signal_ledger_is_trusted():
        log.error("get_results_summary: ledger NO fiable -> no se publica (%s)",
                  "; ".join(_ledger_health.get("reasons") or []))
        return None
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT outcome, pnl_r, ts_closed, minutes_open FROM signals "
                "WHERE " + AUDITABLE_SQL + "AND symbol = ? ORDER BY ts_closed ASC",
                (symbol,)
            ).fetchall()
        finally:
            conn.close()
    return ledger_stats.summarize(rows)

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
        "AUDITORIA SELF-EVOLUCION FQ v5.1 - {} SENALES CERRADAS\n"
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
        "3. CANDIDATOS A VIGILAR: hay buckets que APUNTAN a algo? Nombralos con su n,\n"
        "   pero NO recomiendes subirles exposicion si n<30: con esa muestra la\n"
        "   expectancy de un bucket es indistinguible del ruido, y ordenar por\n"
        "   expectancy selecciona precisamente los extremos del azar. La accion\n"
        "   correcta ante un bucket prometedor con n bajo es esperar muestra.\n\n"
        "4. SUGERENCIA DE THRESHOLD: el PMASTER_MIN actual es 2.30. Con esta data,\n"
        "   subirias o bajarias? Justifica con numeros.\n\n"
        "5. SUGERENCIA DE COOLDOWN: el cooldown es 1h. Demasiado corto/largo?\n\n"
        "Estas son SUGERENCIAS, no instrucciones. RasDG decide. Maximo 6 parrafos.\n"
        "Se brutalmente honesto - si el edge es marginal, dilo. Si hay un bucket\n"
        "que se ve a leguas que es un casino, exponlo.\n\n"
        "Cita la n en la que te apoyas en cada afirmacion. Si la muestra global no\n"
        "da para responder algo, di 'aun no se puede afirmar' en vez de dar una\n"
        "version suavizada de la conclusion optimista. Y si la distribucion de\n"
        "outcomes se ve imposible (p.ej. cero tp1/tp2/tp3, o separacion perfecta por\n"
        "direccion), reportalo como fallo de medicion ANTES que cualquier lectura de\n"
        "edge: una metrica demasiado limpia casi siempre es un bug."
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

def _bucket_performance_table(symbol="SOL"):
    """Tabla de desempeno por bucket con n>=4. symbol default 'SOL': el
    self-audit (build_audit_prompt) no debe sugerir cambios de threshold de
    SOL basado en buckets de BTC/ETH."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute("""
                SELECT bucket_key,
                       COUNT(*) as n,
                       SUM(CASE WHEN outcome IN ('tp1','tp2','tp3','tp4') THEN 1 ELSE 0 END) as wins,
                       AVG(pnl_r) as expectancy
                FROM signals
                WHERE """ + AUDITABLE_SQL + """AND symbol = ?
                GROUP BY bucket_key
                HAVING n >= 4
            """, (symbol,)).fetchall()
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
    # compute_entropy_metrics() hace su PROPIA conexión y toma _lock por dentro
    # (vía _get_prev_window_distribution). Si se llamara con _lock ya tomado ->
    # DEADLOCK (threading.Lock no es reentrante) y colgaba el bot al disparar el
    # audit. Se calcula ANTES de tomar el lock.
    entropy = compute_entropy_metrics()
    with _lock:
        conn = _connect()
        try:
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
    """Exporta ledger a CSV string para mensajes ligeros. SIN filtrar por
    symbol a proposito: es un backup, debe incluir SOL/BTC/ETH completos."""
    if pd is None:
        return None
    with _lock:
        conn = _connect()
        try:
            df = pd.read_sql_query(
                "SELECT id, ts_emitted, symbol, direction, entry_price, p_master_final, "
                "kappa_evo, tier, session, bucket_key, outcome, pnl_r FROM signals "
                "ORDER BY id DESC",
                conn
            )
        finally:
            conn.close()
    return df.to_csv(index=False)

def should_trigger_backup():
    """
    Cada N senales totales (abiertas o cerradas) hace backup, pero SOLO UNA VEZ
    por cada n alcanzado. Sin este guard, el hook reenviaba el backup en cada
    cierre de vela mientras n no cambiara.
    """
    global _last_backup_n_sent
    n = count_signals(closed_only=False)
    if n == 0 or n % BACKUP_EVERY_N_SIGNED != 0:
        return False
    if _last_backup_n_sent == n:
        return False
    return True

def mark_backup_done():
    """Llamar despues de un send_db_backup_to_telegram exitoso."""
    global _last_backup_n_sent
    _last_backup_n_sent = count_signals(closed_only=False)

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

def format_ledger_telegram(n=10, symbol=None):
    """Ultimas N senales del ledger. symbol=None (default) mezcla SOL/BTC/ETH
    (Cerebro Etapa 0: admin ve la actividad real de los 3 en /ledger); pasa
    un symbol para filtrar a uno solo."""
    rows = get_recent_signals(n, symbol=symbol)
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
        sym = r.get("symbol") or "SOL"
        lines.append("#{} {} {} {} P={:.2f}{} [{}] {}{}".format(
            r["id"], ts, sym, r["direction"].upper()[0],
            r["p_master_final"], kappa_marker, r["tier"],
            outcome, pnl
        ))
    return "\n".join(lines)# -*- coding: utf-8 -*-
"""
================================================================================
  ENTROPY COGNITION v2 PATCH - FQ v4.1.1 Refactor
  
  PARCHE AL FINAL de entropy_cognition.py existente.
  NO reemplaza nada — solo agrega:
    - Columnas nuevas en signals (NULL-tolerantes, migracion suave)
    - count_closed_v2_buckets()
    - log_signal_v2() con FieldState completo
    - close_signal_v2() inyecta outcome al bucket memory loop
================================================================================

  INSTRUCCIONES: Pegar ESTE bloque al FINAL de entropy_cognition.py
  Las funciones legacy quedan vivas para compatibilidad con buckets viejos.
"""
# ============================================================
# PEGAR DESDE AQUI HASTA EL FINAL EN entropy_cognition.py
# ============================================================

# ============================================================
# SCHEMA v2 - columnas extra para FieldState
# ============================================================
SCHEMA_V2_MIGRATION = """
-- Columnas v4.1.1 (todas NULL-tolerantes para migracion suave)
ALTER TABLE signals ADD COLUMN killzone        TEXT;
ALTER TABLE signals ADD COLUMN killzone_priority TEXT;
ALTER TABLE signals ADD COLUMN pd_zone         TEXT;
ALTER TABLE signals ADD COLUMN pd_pct          REAL;
ALTER TABLE signals ADD COLUMN pd_hierarchy    TEXT;
ALTER TABLE signals ADD COLUMN confluence_count INTEGER;
ALTER TABLE signals ADD COLUMN confluence_list TEXT;
ALTER TABLE signals ADD COLUMN bias_4h         TEXT;
ALTER TABLE signals ADD COLUMN bias_1h         TEXT;
ALTER TABLE signals ADD COLUMN bias_aligned    INTEGER;
ALTER TABLE signals ADD COLUMN had_sweep       INTEGER;
ALTER TABLE signals ADD COLUMN crt_confirmed   INTEGER;
ALTER TABLE signals ADD COLUMN bucket_key_v2   TEXT;
ALTER TABLE signals ADD COLUMN alpha_hybrid    REAL;
ALTER TABLE signals ADD COLUMN w_killzone      REAL;
ALTER TABLE signals ADD COLUMN field_snapshot  TEXT;

CREATE INDEX IF NOT EXISTS idx_bucket_v2 ON signals(bucket_key_v2);
CREATE INDEX IF NOT EXISTS idx_killzone  ON signals(killzone);
"""

def migrate_schema_v2():
    """Aplica migracion v2 ignorando columnas que ya existen.
       Idempotente — safe correr varias veces."""
    with _lock:
        conn = _connect()
        try:
            for stmt in SCHEMA_V2_MIGRATION.strip().split(";"):
                s = stmt.strip()
                if not s:
                    continue
                try:
                    conn.execute(s)
                except sqlite3.OperationalError as e:
                    # "duplicate column name" cuando ya migrado
                    if "duplicate column" not in str(e).lower():
                        log.warning("schema_v2 migration: {}".format(e))
            conn.commit()
            log.info("Schema v2 migrado/verificado")
        finally:
            conn.close()

# ============================================================
# CONTADORES v2
# ============================================================
def count_closed_v2_buckets(symbol="SOL"):
    """Total de senales cerradas que tienen bucket_key_v2 (usado para alpha
    decay). symbol default 'SOL': hoy solo SOL escribe bucket_key_v2
    (log_signal_v2/v3); BTC/ETH se graban via log_signal simple y dejan esta
    columna NULL a proposito, asi que este filtro es un no-op de seguridad,
    no un cambio de comportamiento."""
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM signals "
                "WHERE bucket_key_v2 IS NOT NULL AND " + AUDITABLE_SQL + "AND symbol = ?",
                (symbol,)
            ).fetchone()
            return int(row["c"]) if row else 0
        finally:
            conn.close()

def get_bucket_stats_v2(bucket_key_v2, symbol="SOL"):
    """Como get_bucket_stats pero usando bucket_key_v2. symbol default 'SOL'
    (ver count_closed_v2_buckets)."""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT outcome, pnl_r FROM signals "
                "WHERE bucket_key_v2 = ? AND " + AUDITABLE_SQL + "AND symbol = ?",
                (bucket_key_v2, symbol)
            ).fetchall()
        finally:
            conn.close()
    n = len(rows)
    if n < KAPPA_EVO_MIN_SAMPLES:
        return None
    wins = sum(1 for r in rows if r["outcome"] in ("tp1","tp2","tp3","tp4"))
    pnls = [r["pnl_r"] for r in rows if r["pnl_r"] is not None]
    win_rate = wins / n
    expectancy = sum(pnls) / len(pnls) if pnls else 0.0
    return {"n": n, "win_rate": win_rate, "expectancy": expectancy}

# ============================================================
# LOG SIGNAL V2 - registra con FieldState completo
# ============================================================
def log_signal_v2(signal_data, field_state):
    """
    Logea senal con FieldState completo.
    signal_data: igual estructura que log_signal legacy
    field_state: objeto FieldState de ict_smc
    """
    import json as _json
    try:
        # Serializar field para snapshot
        field_dict = field_state.to_dict() if hasattr(field_state, "to_dict") else {}
        field_json = _json.dumps(field_dict, default=str)[:50000]

        # bucket_key viejo + bucket_key_v2 nuevo coexisten
        bucket_key_legacy = signal_data.get("bucket_key", make_bucket_key(
            signal_data["session"],
            tier_from_pmaster(signal_data["p_master_raw"]),
            signal_data["direction"],
            curvature_sign(signal_data.get("support_weight", 0),
                          signal_data.get("resistance_weight", 0))
        ))
        bucket_key_v2 = field_state.bucket_key_v2(
            tier_from_pmaster(signal_data["p_master_raw"]),
            signal_data["direction"]
        )

        with _lock:
            conn = _connect()
            try:
                cur = conn.execute("""
                    INSERT INTO signals (
                        ts_emitted, direction, entry_price, sl, tp1, tp2, tp3, tp4,
                        p_master_raw, p_master_final, kappa_evo, session, w_clock,
                        tier, pspace_count, curvature_bal, macro_btc, macro_eth,
                        rsi6, rsi12, rsi24, h_lap_active, bucket_key, snapshot_json,
                        killzone, killzone_priority, pd_zone, pd_pct, pd_hierarchy,
                        confluence_count, confluence_list, bias_4h, bias_1h,
                        bias_aligned, had_sweep, crt_confirmed, bucket_key_v2,
                        alpha_hybrid, w_killzone, field_snapshot
                    ) VALUES (?,?,?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?,?,
                              ?,?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?)
                """, (
                    datetime.now(timezone.utc).isoformat(),
                    signal_data["direction"], signal_data["entry"], signal_data["sl"],
                    signal_data["tp1"], signal_data["tp2"], signal_data["tp3"], signal_data["tp4"],
                    signal_data["p_master_raw"], signal_data["p_master_final"],
                    signal_data["kappa_evo"], signal_data["session"],
                    signal_data["w_clock"], tier_from_pmaster(signal_data["p_master_raw"]),
                    signal_data.get("pspace_count", 0),
                    signal_data.get("support_weight", 0) - signal_data.get("resistance_weight", 0),
                    signal_data.get("macro_btc", 0), signal_data.get("macro_eth", 0),
                    signal_data.get("rsi6", 0), signal_data.get("rsi12", 0),
                    signal_data.get("rsi24", 0), signal_data.get("h_lap_active", 0),
                    bucket_key_legacy, _json.dumps(signal_data.get("snapshot", {}))[:10000],
                    # columnas v2
                    field_state.killzone, field_state.killzone_priority,
                    field_state.pd_zone, field_state.pd_pct, field_state.pd_hierarchy,
                    field_state.confluence_count,
                    ",".join(field_state.confluence_list)[:500],
                    field_state.bias_4h, field_state.bias_1h,
                    1 if field_state.bias_aligned else 0,
                    1 if field_state.recent_sweep else 0,
                    1 if (field_state.crt and field_state.crt.confirmed) else 0,
                    bucket_key_v2, signal_data.get("alpha_hybrid", 1.0),
                    field_state.w_killzone, field_json,
                ))
                sid = cur.lastrowid
                conn.commit()
                log.info("log_signal_v2 #{} bucket_v2={}".format(sid, bucket_key_v2))
                return sid
            finally:
                conn.close()
    except Exception as e:
        log.error("log_signal_v2: {}".format(e))
        return None

# ============================================================
# V3 EVOLUTION - Thompson sampling, concept-aware buckets, enriched audit
# Activado siempre - coexiste con v1/v2 sin romper backward compat
# ============================================================

SCHEMA_V3_MIGRATION = """
ALTER TABLE signals ADD COLUMN bucket_key_v3      TEXT;
ALTER TABLE signals ADD COLUMN concepts_flags     TEXT;
ALTER TABLE signals ADD COLUMN had_breaker        INTEGER;
ALTER TABLE signals ADD COLUMN had_mss            INTEGER;
ALTER TABLE signals ADD COLUMN had_inducement     INTEGER;
ALTER TABLE signals ADD COLUMN had_pwr3           INTEGER;
ALTER TABLE signals ADD COLUMN had_bpr            INTEGER;
ALTER TABLE signals ADD COLUMN had_ote_strict     INTEGER;
ALTER TABLE signals ADD COLUMN had_displacement   INTEGER;
ALTER TABLE signals ADD COLUMN weekend_flag       INTEGER;
ALTER TABLE signals ADD COLUMN kappa_method       TEXT;

CREATE INDEX IF NOT EXISTS idx_bucket_v3 ON signals(bucket_key_v3);
"""

# ============================================================
# SCHEMA v4 - dimension TF para emision multi-timeframe
# ============================================================
SCHEMA_V4_MIGRATION = """
ALTER TABLE signals ADD COLUMN tf_id TEXT;

CREATE INDEX IF NOT EXISTS idx_tf_id ON signals(tf_id);
"""

# ============================================================
# SCHEMA v5 - Cerebro Etapa 0: columna symbol (SOL/BTC/ETH)
# ============================================================
# Additiva, no destructiva: filas viejas (todas SOL, pre-multi-simbolo)
# quedan symbol='SOL' via el DEFAULT. Cierra el gap de ESTADO.md: "BTC/ETH
# se broadcastean a clientes pero su unico registro es el motor paper de
# 1 TP -- una senal puede salir a VIP y no quedar en ningun registro con
# outcome". Ahora BTC/ETH se graban en el MISMO ledger rico (4 TP) via
# log_signal(signal_data, symbol=ccy) -- ver _record_vip_signal en el bot.
#
# IMPORTANTE: toda funcion de analitica/self-audit/kappa-evolucion de SOL
# (get_bucket_stats, compute_kappa_evo, get_global_metrics,
# get_results_summary, _bucket_performance_table, count_signals, etc.)
# ahora filtra symbol='SOL' por DEFAULT -- el comportamiento para SOL es
# BYTE-IDENTICO a antes de esta migracion. BTC/ETH acumulan su propio
# track record en las mismas tablas, aislado.
SCHEMA_V5_MIGRATION = """
ALTER TABLE signals ADD COLUMN symbol TEXT NOT NULL DEFAULT 'SOL';

CREATE INDEX IF NOT EXISTS idx_symbol ON signals(symbol);
"""

def migrate_schema_v5():
    """Agrega columna symbol (default 'SOL', filas viejas quedan SOL).
    Idempotente. Safe correr varias veces."""
    with _lock:
        conn = _connect()
        try:
            for stmt in SCHEMA_V5_MIGRATION.strip().split(";"):
                s = stmt.strip()
                if not s:
                    continue
                try:
                    conn.execute(s)
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        log.warning("schema_v5 migration: {}".format(e))
            conn.commit()
            log.info("Schema v5 (symbol) migrado/verificado")
        finally:
            conn.close()

def migrate_schema_v4():
    """Agrega columna tf_id y backfilla filas historicas a '15m' (SOL/15m era el
    universo pre-refactor). Idempotente."""
    with _lock:
        conn = _connect()
        try:
            for stmt in SCHEMA_V4_MIGRATION.strip().split(";"):
                s = stmt.strip()
                if not s:
                    continue
                try:
                    conn.execute(s)
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        log.warning("schema_v4 migration: {}".format(e))
            # Backfill: filas pre-refactor son todas SOL/15m
            try:
                conn.execute("UPDATE signals SET tf_id='15m' WHERE tf_id IS NULL")
            except sqlite3.OperationalError as e:
                log.warning("schema_v4 backfill: {}".format(e))
            conn.commit()
            log.info("Schema v4 (tf_id) migrado/verificado")
        finally:
            conn.close()

def migrate_schema_v3():
    """Idempotente. Safe correr varias veces."""
    with _lock:
        conn = _connect()
        try:
            for stmt in SCHEMA_V3_MIGRATION.strip().split(";"):
                s = stmt.strip()
                if not s:
                    continue
                try:
                    conn.execute(s)
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        log.warning("schema_v3 migration: {}".format(e))
            conn.commit()
            log.info("Schema v3 migrado/verificado")
        finally:
            conn.close()

# ============================================================
# BUCKET KEY V3 - dimensiones por concepto ICT
# ============================================================
ICT_CONCEPT_KEYS = [
    "breaker", "mss", "inducement", "pwr3", "bpr", "ote_strict", "displacement"
]

def encode_concepts_flags(concepts_dict):
    """
    concepts_dict: dict[concept_name -> bool/int]
    Devuelve string compacto tipo "br1.ms0.in1.p30.bp0.ot1.di1"
    """
    parts = []
    for k in ICT_CONCEPT_KEYS:
        v = 1 if concepts_dict.get(k) else 0
        parts.append("{}{}".format(k[:2], v))
    return ".".join(parts)

def decode_concepts_flags(flags_str):
    """Inverso de encode_concepts_flags"""
    if not flags_str:
        return {}
    out = {}
    for part in flags_str.split("."):
        if len(part) < 3:
            continue
        prefix = part[:2]
        val = part[2:] == "1"
        for k in ICT_CONCEPT_KEYS:
            if k.startswith(prefix):
                out[k] = val
                break
    return out

def make_bucket_key_v3(killzone, tier, direction, pd_zone, hierarchy, concepts_dict, tf_id=None):
    """
    Bucket multi-dimensional. Concepts compactado al final.
    Granular pero manageable - el audit puede agregar por dimension.
    tf_id: 15m (anchor) omite sufijo para continuidad con buckets historicos;
    5m y 1h reciben sufijo para segregar memoria.
    """
    base = "{}|{}|{}|{}|{}".format(
        killzone, tier, direction, pd_zone, hierarchy
    )
    concepts = encode_concepts_flags(concepts_dict)
    key = "{}|{}".format(base, concepts)
    if tf_id and tf_id != _BUCKET_ANCHOR_TF:
        return "{}|{}".format(key, tf_id)
    return key

def make_bucket_key_v3_coarse(killzone, tier, direction, tf_id=None):
    """Coarse: usado para fallback cuando v3 detallado no tiene n suficiente"""
    base = "{}|{}|{}|coarse".format(killzone, tier, direction)
    if tf_id and tf_id != _BUCKET_ANCHOR_TF:
        return "{}|{}".format(base, tf_id)
    return base

# ============================================================
# THOMPSON SAMPLING - bandit kappa_evo
# ============================================================
# Cada bucket tiene posterior Beta(alpha, beta):
#   alpha = 1 + sum(wins)        (donde win = outcome in tp1..tp4)
#   beta  = 1 + sum(losses)      (donde loss = outcome == sl)
# timeouts cuentan como 0.5 win + 0.5 loss (neutral)
# Sample p ~ Beta(alpha, beta), traduce a kappa en [0.85, 1.15]
# Cuando hay POCA data, alpha=beta=1 -> sample disperso (exploracion)
# Cuando hay MUCHA data, sample concentrado -> explotacion

import random as _random

def _bucket_beta_counts(bucket_key_v3, fallback_coarse=None):
    """Cuenta wins/losses para bucket v3 (con fallback a coarse si vacio)"""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT outcome, pnl_r FROM signals "
                "WHERE bucket_key_v3 = ? AND " + AUDITABLE_SQL,
                (bucket_key_v3,)
            ).fetchall()
        finally:
            conn.close()

    if len(rows) < KAPPA_EVO_MIN_SAMPLES and fallback_coarse:
        with _lock:
            conn = _connect()
            try:
                rows = conn.execute(
                    "SELECT outcome, pnl_r FROM signals "
                    "WHERE bucket_key_v3 = ? AND " + AUDITABLE_SQL,
                    (fallback_coarse,)
                ).fetchall()
            finally:
                conn.close()

    wins = losses = 0.0
    for r in rows:
        o = r["outcome"]
        if o in ("tp1", "tp2", "tp3", "tp4"):
            wins += 1.0
        elif o == "sl":
            losses += 1.0
        elif o == "timeout":
            pnl = r["pnl_r"] or 0
            if pnl > 0:
                wins += 0.5; losses += 0.5
            else:
                losses += 1.0
    return wins, losses, len(rows)

def _sample_beta(alpha, beta):
    """Sample numerico de Beta(alpha, beta) sin scipy"""
    try:
        # random.betavariate existe en stdlib
        return _random.betavariate(alpha, beta)
    except Exception:
        # fallback con normal aproximada
        mean = alpha / (alpha + beta)
        return max(0.0, min(1.0, mean))

def compute_kappa_thompson(bucket_key_v3, bucket_key_coarse=None,
                            min_kappa=0.85, max_kappa=1.15, seed=None):
    """
    Thompson sampling para kappa_evo.

    p_sample ~ Beta(1+wins, 1+losses)
    p_baseline = 0.5  (neutral)
    delta = p_sample - p_baseline   en [-0.5, +0.5]
    kappa = 1.0 + delta * 0.3       en [0.85, 1.15]

    Returns (kappa, stats_dict)
    """
    if seed is not None:
        _random.seed(seed)

    wins, losses, n = _bucket_beta_counts(bucket_key_v3, bucket_key_coarse)
    alpha = 1.0 + wins
    beta  = 1.0 + losses
    p_sample = _sample_beta(alpha, beta)
    p_mean = alpha / (alpha + beta)

    # Mapeo: p en [0,1] -> kappa en [min_kappa, max_kappa]
    # p=0.5 -> 1.0 ; p=1.0 -> max_kappa ; p=0.0 -> min_kappa
    delta = p_sample - 0.5
    kappa = 1.0 + delta * (max_kappa - min_kappa)
    kappa = max(min_kappa, min(max_kappa, kappa))

    return kappa, {
        "n":         int(n),
        "wins":      wins,
        "losses":    losses,
        "alpha":     alpha,
        "beta":      beta,
        "p_sample":  p_sample,
        "p_mean":    p_mean,
        "method":    "thompson",
    }

# ============================================================
# LOG SIGNAL V3 - con concepts y bucket v3
# ============================================================
def log_signal_v3(signal_data, field_state, concepts_dict, weekend_flag=False,
                   kappa_method="thompson"):
    """
    Log enriquecido v3. concepts_dict tiene flags por concepto ICT
    (breaker, mss, inducement, pwr3, bpr, ote_strict, displacement).
    """
    import json as _json
    try:
        field_dict = field_state.to_dict() if hasattr(field_state, "to_dict") else {}
        field_json = _json.dumps(field_dict, default=str)[:50000]

        tier = tier_from_pmaster(signal_data["p_master_raw"])
        tf_id = signal_data.get("tf_id")  # opcional: separa memorias 5m/15m/1h
        bucket_key_legacy = signal_data.get("bucket_key", make_bucket_key(
            signal_data["session"], tier, signal_data["direction"],
            curvature_sign(signal_data.get("support_weight", 0),
                          signal_data.get("resistance_weight", 0)),
            tf_id=tf_id,
        ))
        bucket_key_v2 = field_state.bucket_key_v2(tier, signal_data["direction"], tf_id=tf_id)
        bucket_key_v3 = make_bucket_key_v3(
            field_state.killzone, tier, signal_data["direction"],
            field_state.pd_zone, field_state.pd_hierarchy, concepts_dict,
            tf_id=tf_id,
        )
        concepts_flags = encode_concepts_flags(concepts_dict)

        with _lock:
            conn = _connect()
            try:
                cur = conn.execute("""
                    INSERT INTO signals (
                        ts_emitted, direction, entry_price, sl, tp1, tp2, tp3, tp4,
                        p_master_raw, p_master_final, kappa_evo, session, w_clock,
                        tier, pspace_count, curvature_bal, macro_btc, macro_eth,
                        rsi6, rsi12, rsi24, h_lap_active, bucket_key, snapshot_json,
                        killzone, killzone_priority, pd_zone, pd_pct, pd_hierarchy,
                        confluence_count, confluence_list, bias_4h, bias_1h,
                        bias_aligned, had_sweep, crt_confirmed, bucket_key_v2,
                        alpha_hybrid, w_killzone, field_snapshot,
                        bucket_key_v3, concepts_flags, had_breaker, had_mss,
                        had_inducement, had_pwr3, had_bpr, had_ote_strict,
                        had_displacement, weekend_flag, kappa_method, tf_id
                    ) VALUES (?,?,?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?,?,
                              ?,?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,
                              ?,?,?,?, ?,?,?,?, ?,?,?, ?)
                """, (
                    datetime.now(timezone.utc).isoformat(),
                    signal_data["direction"], signal_data["entry"], signal_data["sl"],
                    signal_data["tp1"], signal_data["tp2"], signal_data["tp3"], signal_data["tp4"],
                    signal_data["p_master_raw"], signal_data["p_master_final"],
                    signal_data["kappa_evo"], signal_data["session"],
                    signal_data["w_clock"], tier,
                    signal_data.get("pspace_count", 0),
                    signal_data.get("support_weight", 0) - signal_data.get("resistance_weight", 0),
                    signal_data.get("macro_btc", 0), signal_data.get("macro_eth", 0),
                    signal_data.get("rsi6", 0), signal_data.get("rsi12", 0),
                    signal_data.get("rsi24", 0), signal_data.get("h_lap_active", 0),
                    bucket_key_legacy, _json.dumps(signal_data.get("snapshot", {}))[:10000],
                    # v2
                    field_state.killzone, field_state.killzone_priority,
                    field_state.pd_zone, field_state.pd_pct, field_state.pd_hierarchy,
                    field_state.confluence_count,
                    ",".join(field_state.confluence_list)[:500],
                    field_state.bias_4h, field_state.bias_1h,
                    1 if field_state.bias_aligned else 0,
                    1 if field_state.recent_sweep else 0,
                    1 if (field_state.crt and field_state.crt.confirmed) else 0,
                    bucket_key_v2, signal_data.get("alpha_hybrid", 1.0),
                    field_state.w_killzone, field_json,
                    # v3
                    bucket_key_v3, concepts_flags,
                    1 if concepts_dict.get("breaker") else 0,
                    1 if concepts_dict.get("mss") else 0,
                    1 if concepts_dict.get("inducement") else 0,
                    1 if concepts_dict.get("pwr3") else 0,
                    1 if concepts_dict.get("bpr") else 0,
                    1 if concepts_dict.get("ote_strict") else 0,
                    1 if concepts_dict.get("displacement") else 0,
                    1 if weekend_flag else 0,
                    kappa_method,
                    # v4
                    tf_id or "15m",
                ))
                sid = cur.lastrowid
                conn.commit()
                log.info("log_signal_v3 #{} bucket_v3={} tf={}".format(sid, bucket_key_v3, tf_id or "15m"))
                return sid
            finally:
                conn.close()
    except Exception as e:
        log.error("log_signal_v3: {}".format(e))
        return None

# ============================================================
# AUDIT ENRIQUECIDO V3 - desglose por concepto ICT
# ============================================================
def get_concept_performance():
    """Devuelve win-rate/expectancy por cada concepto ICT individual"""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT had_breaker, had_mss, had_inducement, had_pwr3, had_bpr, "
                "had_ote_strict, had_displacement, outcome, pnl_r "
                "FROM signals WHERE " + AUDITABLE_SQL + "AND bucket_key_v3 IS NOT NULL"
            ).fetchall()
        finally:
            conn.close()

    if not rows:
        return {}

    out = {}
    for concept_col, concept_label in [
        ("had_breaker", "breaker_block"),
        ("had_mss", "mss"),
        ("had_inducement", "inducement"),
        ("had_pwr3", "power_of_3"),
        ("had_bpr", "balanced_price_range"),
        ("had_ote_strict", "ote_strict_62_79"),
        ("had_displacement", "displacement"),
    ]:
        with_concept    = [r for r in rows if r[concept_col] == 1]
        without_concept = [r for r in rows if r[concept_col] == 0]

        def _stats(rs):
            if not rs:
                return None
            n = len(rs)
            wins = sum(1 for r in rs if r["outcome"] in ("tp1","tp2","tp3","tp4"))
            pnls = [r["pnl_r"] for r in rs if r["pnl_r"] is not None]
            return {
                "n":          n,
                "win_rate":   wins / n,
                "expectancy": sum(pnls) / len(pnls) if pnls else 0.0,
            }

        with_stats = _stats(with_concept)
        without_stats = _stats(without_concept)
        out[concept_label] = {
            "with":    with_stats,
            "without": without_stats,
            "edge":    (with_stats["expectancy"] - without_stats["expectancy"])
                       if with_stats and without_stats else None,
        }
    return out

def get_weekend_performance():
    """Compare weekday vs weekend performance"""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT weekend_flag, outcome, pnl_r FROM signals "
                "WHERE " + AUDITABLE_SQL + "AND weekend_flag IS NOT NULL"
            ).fetchall()
        finally:
            conn.close()
    if not rows:
        return None
    weekend = [r for r in rows if r["weekend_flag"] == 1]
    weekday = [r for r in rows if r["weekend_flag"] == 0]
    def _stats(rs):
        if not rs:
            return None
        n = len(rs)
        wins = sum(1 for r in rs if r["outcome"] in ("tp1","tp2","tp3","tp4"))
        pnls = [r["pnl_r"] for r in rs if r["pnl_r"] is not None]
        return {"n": n, "win_rate": wins/n, "expectancy": sum(pnls)/len(pnls) if pnls else 0}
    return {"weekend": _stats(weekend), "weekday": _stats(weekday)}


def get_tp_distribution_by_tf(symbol=None):
    """Desglose de outcomes (tp1..tp4/sl/timeout) por tf_id -- valida
    hipotesis del tipo "en 5m, TP2 es el objetivo mas repetible" con datos
    del ledger en vez de anecdota (RasDG, 2026-07-21).

    symbol=None (default): mezcla SOL/BTC/ETH -- la muestra por TF ya es
    chica, partirla mas sin pedirlo explicito la deja sin señal. Pasa
    'SOL'/'BTC'/'ETH' para aislar un simbolo.

    'stale' se excluye (outcome no auditable, no es ni win ni loss real).
    tf_id NULL (señales pre-schema-v4) cae al anchor historico "15m" -- ver
    _RECONCILE_ANCHOR_TF, mismo criterio que reconcile_outcomes.

    Devuelve {tf_id: {n, win_rate, expectancy, dist, win_dist, top_tp,
    top_tp_pct}} o {} si no hay cierres. top_tp/top_tp_pct: el outcome
    ganador mas frecuente ENTRE LOS WINS de ese TF y su proporcion (None/0
    si ese TF no tiene ningun win todavia)."""
    with _lock:
        conn = _connect()
        try:
            if symbol:
                rows = conn.execute(
                    "SELECT tf_id, outcome, pnl_r FROM signals "
                    "WHERE " + AUDITABLE_SQL + "AND symbol = ?",
                    (symbol,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT tf_id, outcome, pnl_r FROM signals "
                    "WHERE " + AUDITABLE_SQL
                ).fetchall()
        finally:
            conn.close()

    if not rows:
        return {}

    by_tf = defaultdict(list)
    for r in rows:
        by_tf[r["tf_id"] or _RECONCILE_ANCHOR_TF].append(r)

    out = {}
    for tf, rs in by_tf.items():
        n = len(rs)
        wins = [r for r in rs if r["outcome"] in ("tp1", "tp2", "tp3", "tp4")]
        dist = Counter(r["outcome"] for r in rs)
        win_dist = Counter(r["outcome"] for r in wins)
        top = win_dist.most_common(1)
        pnls = [r["pnl_r"] for r in rs if r["pnl_r"] is not None]
        out[tf] = {
            "n": n,
            "win_rate": len(wins) / n,
            "expectancy": sum(pnls) / len(pnls) if pnls else 0,
            "dist": dict(dist),
            "win_dist": dict(win_dist),
            "top_tp": top[0][0] if top else None,
            "top_tp_pct": (top[0][1] / len(wins)) if top and wins else 0,
        }
    return out


def format_tp_distribution_telegram(symbol=None):
    """Formato admin de get_tp_distribution_by_tf. None si no hay cierres."""
    data = get_tp_distribution_by_tf(symbol=symbol)
    if not data:
        return None
    label = symbol or "SOL+BTC+ETH"
    lines = [
        "<b>DISTRIBUCION DE TP POR TIMEFRAME</b> ({})".format(label),
        "",
    ]
    for tf in sorted(data.keys()):
        d = data[tf]
        dist_str = " ".join(
            "{}={}".format(k, v) for k, v in sorted(d["dist"].items())
        )
        top_line = ""
        if d["top_tp"]:
            top_line = "  TP mas frecuente entre wins: <b>{}</b> ({:.0%} de los wins)".format(
                d["top_tp"].upper(), d["top_tp_pct"])
        lines.append(
            "[{tf}]  n={n}  WR={wr:.0%}  Exp={exp:+.2f}R\n"
            "  {dist}\n"
            "{top}".format(
                tf=tf, n=d["n"], wr=d["win_rate"], exp=d["expectancy"],
                dist=dist_str, top=top_line,
            )
        )
        lines.append("")
    return "\n".join(lines).rstrip()


def build_audit_prompt_v3():
    """
    Audit enriquecido con desglose por concepto ICT.
    Si v3 data esta vacio, cae al prompt v2 legacy.
    """
    metrics = get_global_metrics()
    entropy = compute_entropy_metrics()
    if metrics["n"] == 0:
        return None

    # Si no hay data v3, usa legacy
    concept_perf = get_concept_performance()
    has_v3 = any(
        cp.get("with") and cp["with"]["n"] >= 4
        for cp in concept_perf.values()
    )
    if not has_v3:
        return build_audit_prompt()

    weekend_perf = get_weekend_performance()

    # Concepto-por-concepto: cual aporta edge?
    concept_lines = []
    for concept, data in sorted(
        concept_perf.items(),
        key=lambda x: -(x[1].get("edge") or -99)
    ):
        wstats = data.get("with")
        wostats = data.get("without")
        edge = data.get("edge")
        if not wstats or wstats["n"] < 3:
            concept_lines.append("  {}: data insuficiente (n_with={})".format(
                concept, wstats["n"] if wstats else 0))
            continue
        wo_n = wostats["n"] if wostats else 0
        wo_wr = wostats["win_rate"] if wostats else 0
        wo_exp = wostats["expectancy"] if wostats else 0
        concept_lines.append(
            "  {}:\n"
            "    CON concepto:  n={} WR={:.0%} Exp={:+.2f}R\n"
            "    SIN concepto:  n={} WR={:.0%} Exp={:+.2f}R\n"
            "    Edge (con-sin): {:+.2f}R".format(
                concept, wstats["n"], wstats["win_rate"], wstats["expectancy"],
                wo_n, wo_wr, wo_exp,
                edge if edge is not None else 0
            )
        )

    weekend_line = ""
    if weekend_perf:
        wkd = weekend_perf.get("weekday")
        wke = weekend_perf.get("weekend")
        if wkd and wke and wkd["n"] > 0 and wke["n"] > 0:
            weekend_line = (
                "\n\nWEEKDAY vs WEEKEND:\n"
                "  weekday: n={} WR={:.0%} Exp={:+.2f}R\n"
                "  weekend: n={} WR={:.0%} Exp={:+.2f}R".format(
                    wkd["n"], wkd["win_rate"], wkd["expectancy"],
                    wke["n"], wke["win_rate"], wke["expectancy"]
                )
            )

    bucket_perf = _bucket_performance_table()
    winners = sorted(bucket_perf, key=lambda x: x["expectancy"], reverse=True)[:5]
    losers  = sorted(bucket_perf, key=lambda x: x["expectancy"])[:5]
    winners_lines = "\n".join(
        "  {} | n={} WR={:.0%} Exp={:+.2f}R".format(
            w["bucket"], w["n"], w["win_rate"], w["expectancy"])
        for w in winners) or "  (sin data)"
    losers_lines = "\n".join(
        "  {} | n={} WR={:.0%} Exp={:+.2f}R".format(
            l["bucket"], l["n"], l["win_rate"], l["expectancy"])
        for l in losers) or "  (sin data)"

    return (
        "AUDITORIA SELF-EVOLUCION FQ v5.1 (V3 ENRICHED) - {} SENALES CERRADAS\n"
        "=======================================================================\n\n"
        "DESEMPENO GLOBAL:\n"
        "  Win rate:      {:.1%}\n"
        "  Expectancy:    {:+.2f}R / trade\n"
        "  Avg ganador:   {:+.2f}R   Avg perdedor: {:+.2f}R\n"
        "  Profit factor: {:.2f}\n"
        "  TP distribution: {}\n\n"
        "EDGE POR CONCEPTO ICT (CON vs SIN):\n"
        "  -- Aqui esta el oro: que conceptos del PDF agregan probabilidad real --\n"
        "{}\n\n"
        "ENTROPIA SHANNON (0=colapso, 1=diverso):\n"
        "  H_total={:.3f}  H_sesion={:.3f}  H_tier={:.3f}\n"
        "  H_direccion={:.3f}  KL drift 25v25={:.3f}\n\n"
        "TOP 5 BUCKETS GANADORES:\n{}\n\n"
        "TOP 5 BUCKETS PERDEDORES:\n{}{}\n\n"
        "----\n"
        "Como auditor del sistema cuantico-ICT FQ:\n\n"
        "1. CONCEPT EDGE: cuales de los 7 conceptos ICT del PDF estan dando edge REAL\n"
        "   (Exp con > Exp sin por >0.3R)? Cuales estan no aportando o son ruido?\n"
        "   Nombralos uno por uno con tu juicio.\n\n"
        "2. ATRACTORES TOXICOS: hay buckets v3 con muchas senales y expectancy negativa?\n"
        "   Sugiere: subir threshold de ese bucket, o vetarlo entirely?\n\n"
        "3. CANDIDATOS A VIGILAR: hay combinaciones de conceptos (ej: breaker+ote_strict)\n"
        "   que apunten a algo? Dilas con su n. NO recomiendes mas exposicion con n<30:\n"
        "   cruzar conceptos multiplica los cortes y por tanto el ruido, asi que la\n"
        "   combinacion mas vistosa suele ser la mas sobreajustada. Esperar muestra es\n"
        "   la recomendacion correcta, no asignar riesgo.\n\n"
        "4. WEEKEND: el filtro fin de semana se justifica con la data? (si hay data v3 de\n"
        "   weekend). Si veto es conservador, podemos relajar?\n\n"
        "5. PMASTER_MIN sugerido (actual 1.80). Subir/bajar y por que.\n\n"
        "6. KAPPA EVO METHOD: actual es Thompson sampling con prior Beta(1,1).\n"
        "   El prior es razonable o muy ancho? Sugiere si vale concentrar (prior(2,2)).\n\n"
        "Maximo 8 parrafos. Brutalmente honesto. Si un concepto del PDF no aporta edge,\n"
        "dilo (esto es ciencia, no fe).\n\n"
        "Cita la n en la que te apoyas en cada afirmacion; una afirmacion sin su n no\n"
        "vale. El punto 1 en particular exige muestra: una diferencia de 0.3R entre\n"
        "'con' y 'sin' un concepto no significa nada si cualquiera de los dos lados\n"
        "tiene n<30 -- en ese caso el veredicto correcto es 'sin muestra suficiente',\n"
        "no 'aporta' ni 'es ruido'. Y si la distribucion de outcomes se ve imposible\n"
        "(p.ej. cero tp1/tp2/tp3, o separacion perfecta por direccion), reportalo como\n"
        "fallo de medicion ANTES que cualquier lectura de edge: una metrica demasiado\n"
        "limpia casi siempre es un bug."
    ).format(
        metrics["n"],
        metrics["win_rate"], metrics["expectancy_r"],
        metrics["avg_win_r"], metrics["avg_loss_r"],
        metrics["profit_factor"], metrics["tp_dist"],
        "\n".join(concept_lines),
        entropy["h_total"], entropy["h_session"], entropy["h_tier"],
        entropy["h_direction"], entropy["kl_drift_25v25"],
        winners_lines, losers_lines, weekend_line,
    )

# ============================================================
# FORMATEO TELEGRAM V3
# ============================================================
def format_concepts_telegram():
    """Telegram-friendly desglose de edge por concepto"""
    cp = get_concept_performance()
    if not cp:
        return "Sin data v3 aun. Necesita senales cerradas con flags de concepto."
    lines = ["<b>EDGE POR CONCEPTO ICT</b>", ""]
    for concept, data in sorted(
        cp.items(),
        key=lambda x: -(x[1].get("edge") or -99)
    ):
        wstats = data.get("with")
        if not wstats or wstats["n"] < 3:
            lines.append("{}: n={} (insuficiente)".format(
                concept, wstats["n"] if wstats else 0))
            continue
        edge = data.get("edge") or 0
        edge_tag = "[+]" if edge > 0.1 else ("[-]" if edge < -0.1 else "[~]")
        lines.append("{} {}:".format(edge_tag, concept))
        lines.append("  con: n={} WR={:.0%} Exp={:+.2f}R".format(
            wstats["n"], wstats["win_rate"], wstats["expectancy"]))
        wostats = data.get("without")
        if wostats:
            lines.append("  sin: n={} WR={:.0%} Exp={:+.2f}R".format(
                wostats["n"], wostats["win_rate"], wostats["expectancy"]))
        lines.append("  edge: {:+.2f}R".format(edge))
        lines.append("")
    return "\n".join(lines)

