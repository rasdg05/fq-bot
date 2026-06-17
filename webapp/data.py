# -*- coding: utf-8 -*-
"""
Capa de datos de la Mini App. SOLO LECTURA sobre el ledger y la BD VIP.

Dos roles:
  - admin: ve todo (matematica del motor incluida) — metricas, salud, subs.
  - cliente (vip/trial/free): ve senales filtradas y SIN jerga de motor.

Reutiliza las funciones existentes (entropy_cognition, vip_system, ledger_stats)
como unica fuente de verdad. Para `signal_progress` (sin getter propio) abre una
conexion RO directa al mismo path del ledger. Nunca escribe.

Las superficies de cliente pasan por whitelist explicita: jamas exponen
p_master, kappa, bucket_key, snapshot ni otra jerga interna (lo blinda
tests/test_webapp_client_surface.py, en linea con test_client_surfaces.py).
"""
import os
import sqlite3

import entropy_cognition as ec
import vip_system as vip
import ledger_stats

# ------------------------------------------------------------------
# Roles
# ------------------------------------------------------------------
ROLE_ADMIN = "admin"
ROLE_VIP   = "vip"
ROLE_TRIAL = "trial"
ROLE_FREE  = "free"

# Tiers con acceso completo a niveles de senal en vivo.
_FULL_ACCESS = (ROLE_ADMIN, ROLE_VIP, ROLE_TRIAL)


def role_for(chat_id):
    """admin | vip | trial | free. No crea usuario (lectura pura).

    Degrada a 'free' si la BD VIP aun no existe (arranque en frio): la app es RO
    y nunca crea/migra las BDs de produccion — eso lo hacen sus procesos dueños.
    """
    if vip.is_admin(chat_id):
        return ROLE_ADMIN
    try:
        return vip.get_effective_tier(chat_id)
    except Exception:
        return ROLE_FREE


def is_admin(chat_id):
    return vip.is_admin(chat_id)


def me(chat_id, user=None):
    """Identidad + suscripcion del usuario actual (para cabecera de la app)."""
    role = role_for(chat_id)
    try:
        days = vip.days_remaining(chat_id)
    except Exception:
        days = None
    out = {
        "id":             chat_id,
        "role":           role,
        "is_admin":       role == ROLE_ADMIN,
        "days_remaining": days,
    }
    if user:
        out["first_name"] = user.get("first_name")
        out["username"]   = user.get("username")
    return out


# ------------------------------------------------------------------
# Acceso RO directo (para columnas/tablas sin getter en los modulos)
# ------------------------------------------------------------------
def _ledger_path():
    # entropy_cognition.DB_PATH es la unica fuente de verdad del path.
    return getattr(ec, "DB_PATH", None) or os.environ.get("FQ_LEDGER_PATH", "")


def _ro_conn():
    """Conexion de solo lectura al ledger. None si el archivo no existe aun."""
    path = _ledger_path()
    if not path or not os.path.exists(path):
        return None
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _recent_rows(limit):
    """Filas completas de las ultimas `limit` senales (orden desc)."""
    conn = _ro_conn()
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def progress_for(signal_ids):
    """Mapa {signal_id: [{event, ts, price}, ...]} desde signal_progress."""
    ids = [int(i) for i in signal_ids if i is not None]
    if not ids:
        return {}
    conn = _ro_conn()
    if conn is None:
        return {}
    try:
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            "SELECT signal_id, event, ts_event, price FROM signal_progress "
            "WHERE signal_id IN ({}) ORDER BY ts_event".format(placeholders),
            ids,
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()
    out = {}
    for r in rows:
        out.setdefault(r["signal_id"], []).append(
            {"event": r["event"], "ts": r["ts_event"], "price": r["price"]}
        )
    return out


# ------------------------------------------------------------------
# Vistas de senal
# ------------------------------------------------------------------
# Campos seguros para clientes: la senal en si, su resultado y su progreso.
# NADA de p_master, kappa, bucket, session, snapshot ni otra jerga de motor.
_CLIENT_SIGNAL_FIELDS = (
    "id", "ts_emitted", "direction", "entry_price",
    "sl", "tp1", "tp2", "tp3", "tp4",
    "ts_closed", "outcome", "pnl_r", "minutes_open",
)

# El admin ve, ademas, la matematica del motor (curada; sin snapshot_json crudo).
_ADMIN_EXTRA_FIELDS = (
    "p_master_raw", "p_master_final", "kappa_evo",
    "session", "tier", "w_clock", "bucket_key", "pspace_count",
)


def client_signal_view(row, progress_map, locked=False):
    """Proyeccion segura para cliente. Si locked y la senal esta abierta,
    oculta niveles (teaser para tier free)."""
    status = "closed" if row.get("outcome") else "open"
    if locked and status == "open":
        return {
            "id":         row.get("id"),
            "ts_emitted": row.get("ts_emitted"),
            "direction":  row.get("direction"),
            "status":     "open",
            "locked":     True,
        }
    view = {k: row.get(k) for k in _CLIENT_SIGNAL_FIELDS}
    view["status"]   = status
    view["locked"]   = False
    view["progress"] = progress_map.get(row.get("id"), [])
    return view


def admin_signal_view(row, progress_map):
    """Proyeccion admin: campos de cliente + matematica del motor + progreso."""
    view = {k: row.get(k) for k in _CLIENT_SIGNAL_FIELDS}
    for k in _ADMIN_EXTRA_FIELDS:
        view[k] = row.get(k)
    view["status"]   = "closed" if row.get("outcome") else "open"
    view["progress"] = progress_map.get(row.get("id"), [])
    return view


# ------------------------------------------------------------------
# API de cliente
# ------------------------------------------------------------------
def client_signals(chat_id, limit=20):
    """Senales recientes filtradas por tier (sin jerga de motor)."""
    role = role_for(chat_id)
    rows = _recent_rows(limit)
    prog = progress_for([r.get("id") for r in rows])
    locked = role not in _FULL_ACCESS
    return {
        "role":    role,
        "locked":  locked,
        "signals": [client_signal_view(r, prog, locked=locked) for r in rows],
    }


def track_record():
    """Resumen verificable (ventanas 30/90/total + racha). None si vacio.
    Mismo dict que el bot publico: seguro para cualquier tier."""
    conn = _ro_conn()
    if conn is None:
        return None
    try:
        rows = conn.execute(
            "SELECT outcome, pnl_r, ts_closed FROM signals "
            "WHERE outcome IS NOT NULL ORDER BY ts_closed ASC"
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    return ledger_stats.summarize(rows)


# ------------------------------------------------------------------
# API de admin
# ------------------------------------------------------------------
def admin_overview():
    """Salud del motor (heartbeats) + conteos de senales."""
    health = _engine_health()
    open_rows = []
    try:
        open_rows = ec.get_open_signals()
    except Exception:
        open_rows = []
    return {
        "health":          health,
        "open_count":      len(open_rows),
        "signals_total":   _safe_count(closed_only=False),
        "signals_closed":  _safe_count(closed_only=True),
    }


def _safe_count(closed_only):
    try:
        return ec.count_signals(closed_only=closed_only)
    except Exception:
        return 0


# Umbral de "sin latido" por componente (segundos). Override por env.
def _stale_after():
    vip_min    = float(os.environ.get("FQ_VIP_STALE_MIN", "15"))
    public_min = float(os.environ.get("FQ_PUBLIC_STALE_MIN", "20"))
    return {
        "vip":         vip_min * 60,
        "public":      public_min * 60,
        "maintenance": 900,
        "web":         900,
    }


def _engine_health():
    try:
        from ops import heartbeat as hb
    except Exception:
        return {}
    thresholds = _stale_after()
    out = {}
    for comp, stale_after in thresholds.items():
        age = hb.age_seconds(comp)
        out[comp] = {
            "age_seconds": age,
            "stale_after": stale_after,
            "stale":       (age is not None and age > stale_after),
            "seen":        age is not None,
        }
    return out


def admin_signals(limit=30):
    """Senales abiertas + recientes, con la matematica del motor."""
    try:
        open_rows = ec.get_open_signals()
    except Exception:
        open_rows = []
    recent = _recent_rows(limit)
    ids = [r.get("id") for r in open_rows] + [r.get("id") for r in recent]
    prog = progress_for(ids)
    return {
        "open":   [admin_signal_view(r, prog) for r in open_rows],
        "recent": [admin_signal_view(r, prog) for r in recent],
    }


def admin_stats():
    """Metricas globales del motor + track record."""
    out = {"global": None, "summary": None}
    try:
        out["global"] = ec.get_global_metrics()
    except Exception:
        pass
    try:
        out["summary"] = ec.get_results_summary()
    except Exception:
        pass
    return out


_SAFE_USER_FIELDS = (
    "chat_id", "username", "first_name", "tier", "plan",
    "expires_at", "total_paid_usd", "created_at", "last_seen_at", "source",
)


def _safe_user(u):
    return {k: u.get(k) for k in _SAFE_USER_FIELDS}


def admin_subs(limit=20):
    """Stats de suscriptores + ultimos usuarios + pagos pendientes."""
    out = {"stats": None, "recent_users": [], "pending_payments": []}
    try:
        out["stats"] = vip.get_stats()
    except Exception:
        pass
    try:
        out["recent_users"] = [_safe_user(u) for u in vip.get_all_users(limit=limit)]
    except Exception:
        pass
    try:
        out["pending_payments"] = vip.get_pending_payments()
    except Exception:
        pass
    return out
