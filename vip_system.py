# -*- coding: utf-8 -*-
"""
================================================================================
  VIP SYSTEM - FQ
  Sistema de acceso multiusuario con codigos, suscripciones y panel admin
================================================================================

  Caracteristicas:
    - SQLite users table (chat_id PK, plan, expires_at, source, etc)
    - Codigos de acceso (regalo / promo / venta) con duracion configurable
    - Verificacion de acceso por comando (decorator)
    - Tiers: free / trial / vip / admin
    - Panel admin: /gencode /usuarios /broadcast /revoke
    - Self-service: /vip /codigo /renovar /miestado
    - Tracking de uso, fuente, conversion

  El admin se identifica por TELEGRAM_CHAT_ID (env var).
  Todos los demas usuarios entran como 'free' por defecto.
================================================================================
"""
import os
import sqlite3
import secrets
import logging
import json
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

log = logging.getLogger("fq_vip")

# ============================================================
# CONFIG
# ============================================================
VIP_DB_PATH = os.environ.get("FQ_VIP_DB_PATH", "/tmp/fq_vip.db").strip()
ADMIN_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# Planes y precios (USD)
PLAN_PRICES = {
    "trial_7d":   {"days": 7,   "price_usd": 0,    "label": "Trial 7 dias"},
    "vip_30d":    {"days": 30,  "price_usd": 49,   "label": "VIP Mensual"},
    "vip_90d":    {"days": 90,  "price_usd": 129,  "label": "VIP Trimestral (12% off)"},
    "vip_365d":   {"days": 365, "price_usd": 449,  "label": "VIP Anual (24% off)"},
    "lifetime":   {"days": 36500, "price_usd": 1200, "label": "Lifetime"},
}

# Tiers de acceso
TIER_FREE  = "free"
TIER_TRIAL = "trial"
TIER_VIP   = "vip"
TIER_ADMIN = "admin"

# Comandos por tier
COMMANDS_FREE  = ["/start", "/help", "/about", "/precio", "/vip", "/codigo", "/miestado", "/sesion"]
COMMANDS_TRIAL = COMMANDS_FREE + ["/status", "/macro"]
COMMANDS_VIP   = COMMANDS_TRIAL + [
    "/analisis", "/niveles", "/pspace", "/claude", "/ia",
    "/metrics", "/entropy", "/ledger", "/evolve", "/audit",
    "/renovar",
]
COMMANDS_ADMIN = COMMANDS_VIP + [
    "/gencode", "/usuarios", "/broadcast", "/revoke",
    "/grant", "/stats", "/admin",
]

# ============================================================
# DB SETUP
# ============================================================
@contextmanager
def _conn():
    c = sqlite3.connect(VIP_DB_PATH, timeout=20)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()

def init_vip_db():
    """Crea tablas si no existen"""
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id        TEXT PRIMARY KEY,
            username       TEXT,
            first_name     TEXT,
            tier           TEXT NOT NULL DEFAULT 'free',
            plan           TEXT,
            expires_at     TEXT,
            created_at     TEXT NOT NULL,
            last_seen_at   TEXT,
            source         TEXT,
            referrer       TEXT,
            total_paid_usd REAL DEFAULT 0,
            notes          TEXT
        );

        CREATE TABLE IF NOT EXISTS codes (
            code           TEXT PRIMARY KEY,
            kind           TEXT NOT NULL,
            duration_days  INTEGER NOT NULL,
            plan           TEXT,
            created_at     TEXT NOT NULL,
            created_by     TEXT,
            used_by        TEXT,
            used_at        TEXT,
            expires_at     TEXT,
            note           TEXT
        );

        CREATE TABLE IF NOT EXISTS payments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id        TEXT NOT NULL,
            plan           TEXT NOT NULL,
            amount_usd     REAL NOT NULL,
            method         TEXT NOT NULL,
            tx_hash        TEXT,
            stripe_id      TEXT,
            status         TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            confirmed_at   TEXT,
            metadata       TEXT
        );

        CREATE TABLE IF NOT EXISTS access_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id        TEXT NOT NULL,
            command        TEXT NOT NULL,
            tier           TEXT,
            allowed        INTEGER NOT NULL,
            ts             TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_users_tier   ON users(tier);
        CREATE INDEX IF NOT EXISTS idx_codes_used   ON codes(used_by);
        CREATE INDEX IF NOT EXISTS idx_payments_uid ON payments(chat_id);
        CREATE INDEX IF NOT EXISTS idx_log_uid      ON access_log(chat_id);
        """)
    log.info("VIP DB initialized at {}".format(VIP_DB_PATH))

# ============================================================
# USER MANAGEMENT
# ============================================================
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def is_admin(chat_id):
    return str(chat_id) == ADMIN_CHAT_ID

def get_or_create_user(chat_id, username=None, first_name=None):
    """Crea usuario si no existe, devuelve dict con su info"""
    chat_id = str(chat_id)
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
        if row is None:
            tier = TIER_ADMIN if is_admin(chat_id) else TIER_FREE
            c.execute(
                """INSERT INTO users
                   (chat_id, username, first_name, tier, created_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (chat_id, username, first_name, tier, now_iso(), now_iso())
            )
            log.info("New user: {} ({}) tier={}".format(chat_id, username, tier))
            return {
                "chat_id": chat_id, "username": username, "first_name": first_name,
                "tier": tier, "plan": None, "expires_at": None,
                "created_at": now_iso(), "is_new": True,
            }
        # Update last_seen
        c.execute("UPDATE users SET last_seen_at = ? WHERE chat_id = ?",
                  (now_iso(), chat_id))
        # Si es admin pero la BD no lo refleja, corregir
        if is_admin(chat_id) and row["tier"] != TIER_ADMIN:
            c.execute("UPDATE users SET tier = ? WHERE chat_id = ?",
                      (TIER_ADMIN, chat_id))
        d = dict(row)
        d["is_new"] = False
        return d

def get_user(chat_id):
    """Get user dict or None"""
    chat_id = str(chat_id)
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
        return dict(row) if row else None

def get_effective_tier(chat_id):
    """
    Tier efectivo considerando expires_at.
    Si la suscripcion expiro, devuelve 'free' aunque el campo tier diga 'vip'.
    """
    if is_admin(chat_id):
        return TIER_ADMIN
    u = get_user(chat_id)
    if not u:
        return TIER_FREE
    tier = u["tier"]
    if tier in (TIER_VIP, TIER_TRIAL) and u["expires_at"]:
        try:
            exp = datetime.fromisoformat(u["expires_at"])
            if exp < datetime.now(timezone.utc):
                return TIER_FREE
        except Exception:
            return TIER_FREE
    return tier

def days_remaining(chat_id):
    """Dias restantes de suscripcion o None si no aplica"""
    u = get_user(chat_id)
    if not u or not u["expires_at"]:
        return None
    try:
        exp = datetime.fromisoformat(u["expires_at"])
        delta = exp - datetime.now(timezone.utc)
        return max(0, delta.days + (1 if delta.seconds > 0 else 0))
    except Exception:
        return None

def grant_subscription(chat_id, plan, days, source="manual", referrer=None):
    """Otorga o extiende suscripcion"""
    chat_id = str(chat_id)
    u = get_user(chat_id)
    if not u:
        get_or_create_user(chat_id)
        u = get_user(chat_id)

    # Si ya tiene suscripcion vigente, extender desde su expires_at
    now = datetime.now(timezone.utc)
    base = now
    if u["expires_at"]:
        try:
            exp = datetime.fromisoformat(u["expires_at"])
            if exp > now:
                base = exp
        except Exception:
            pass

    new_exp = base + timedelta(days=days)
    tier = TIER_TRIAL if plan == "trial_7d" else TIER_VIP

    with _conn() as c:
        c.execute(
            """UPDATE users SET tier = ?, plan = ?, expires_at = ?, source = ?, referrer = ?
               WHERE chat_id = ?""",
            (tier, plan, new_exp.isoformat(), source, referrer, chat_id)
        )
    log.info("Granted {} days ({}) to {} until {}".format(days, plan, chat_id, new_exp))
    return new_exp

def revoke_subscription(chat_id, reason="admin_revoke"):
    chat_id = str(chat_id)
    with _conn() as c:
        c.execute(
            """UPDATE users SET tier = ?, expires_at = NULL, notes = ?
               WHERE chat_id = ?""",
            (TIER_FREE, "revoked: " + reason, chat_id)
        )
    log.info("Revoked subscription for {}: {}".format(chat_id, reason))
    return True

# ============================================================
# CODES SYSTEM
# ============================================================
def generate_code(duration_days=7, plan="trial_7d", kind="gift",
                  created_by="admin", note=None, expires_in_days=30):
    """Genera codigo unico de acceso"""
    code = "RASDG-" + secrets.token_hex(4).upper()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat()
    with _conn() as c:
        c.execute(
            """INSERT INTO codes
               (code, kind, duration_days, plan, created_at, created_by, expires_at, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, kind, duration_days, plan, now_iso(), created_by, expires_at, note)
        )
    log.info("Generated code {}: {}d {} ({})".format(code, duration_days, plan, kind))
    return code

def redeem_code(code, chat_id, username=None):
    """
    Intenta canjear codigo. Retorna (success, message, days).
    """
    code = code.strip().upper()
    chat_id = str(chat_id)
    with _conn() as c:
        row = c.execute("SELECT * FROM codes WHERE code = ?", (code,)).fetchone()
        if row is None:
            return False, "Codigo no existe.", 0
        if row["used_by"]:
            if row["used_by"] == chat_id:
                return False, "Ya canjeaste este codigo el {}.".format(row["used_at"][:10]), 0
            return False, "Codigo ya fue canjeado.", 0
        # Check expiration
        if row["expires_at"]:
            try:
                exp = datetime.fromisoformat(row["expires_at"])
                if exp < datetime.now(timezone.utc):
                    return False, "Codigo expiro el {}.".format(row["expires_at"][:10]), 0
            except Exception:
                pass

        # Marcar usado
        c.execute(
            """UPDATE codes SET used_by = ?, used_at = ? WHERE code = ?""",
            (chat_id, now_iso(), code)
        )

    # Aplicar al usuario
    new_exp = grant_subscription(
        chat_id, row["plan"], row["duration_days"],
        source="code:" + code, referrer=row["created_by"]
    )
    return True, "Codigo aplicado: {} dias hasta {}".format(
        row["duration_days"], new_exp.strftime("%Y-%m-%d %H:%M UTC")), row["duration_days"]

def list_codes(unused_only=True, limit=20):
    with _conn() as c:
        q = "SELECT * FROM codes"
        if unused_only:
            q += " WHERE used_by IS NULL"
        q += " ORDER BY created_at DESC LIMIT ?"
        rows = c.execute(q, (limit,)).fetchall()
        return [dict(r) for r in rows]

# ============================================================
# PAYMENTS
# ============================================================
def record_payment(chat_id, plan, amount_usd, method, tx_hash=None,
                   stripe_id=None, status="pending", metadata=None):
    chat_id = str(chat_id)
    md = json.dumps(metadata) if metadata else None
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO payments
               (chat_id, plan, amount_usd, method, tx_hash, stripe_id, status, created_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (chat_id, plan, amount_usd, method, tx_hash, stripe_id, status, now_iso(), md)
        )
        return cur.lastrowid

def confirm_payment(payment_id):
    """Marca pago confirmado y otorga suscripcion"""
    with _conn() as c:
        row = c.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if not row or row["status"] == "confirmed":
            return False
        c.execute(
            "UPDATE payments SET status = 'confirmed', confirmed_at = ? WHERE id = ?",
            (now_iso(), payment_id)
        )
        plan_info = PLAN_PRICES.get(row["plan"])
        if plan_info:
            grant_subscription(
                row["chat_id"], row["plan"], plan_info["days"],
                source="payment:" + row["method"]
            )
            # Update total_paid
            c.execute(
                "UPDATE users SET total_paid_usd = total_paid_usd + ? WHERE chat_id = ?",
                (row["amount_usd"], row["chat_id"])
            )
        return True

def get_pending_payments(method=None, max_age_hours=72):
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    with _conn() as c:
        if method:
            q = "SELECT * FROM payments WHERE status = 'pending' AND method = ? AND created_at > ?"
            rows = c.execute(q, (method, cutoff)).fetchall()
        else:
            q = "SELECT * FROM payments WHERE status = 'pending' AND created_at > ?"
            rows = c.execute(q, (cutoff,)).fetchall()
        return [dict(r) for r in rows]

# ============================================================
# ACCESS CONTROL
# ============================================================
def check_access(chat_id, command):
    """
    Devuelve (allowed: bool, tier: str, message: str|None).
    Si allowed=False, message contiene el rechazo formateado.
    """
    chat_id = str(chat_id)
    cmd = command.split("@")[0].split()[0].lower()
    tier = get_effective_tier(chat_id)

    if tier == TIER_ADMIN:
        allowed_cmds = COMMANDS_ADMIN
    elif tier == TIER_VIP:
        allowed_cmds = COMMANDS_VIP
    elif tier == TIER_TRIAL:
        allowed_cmds = COMMANDS_TRIAL
    else:
        allowed_cmds = COMMANDS_FREE

    allowed = cmd in allowed_cmds

    # Log
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO access_log (chat_id, command, tier, allowed, ts) VALUES (?, ?, ?, ?, ?)",
                (chat_id, cmd, tier, 1 if allowed else 0, now_iso())
            )
    except Exception as e:
        log.warning("access_log write error: {}".format(e))

    if allowed:
        return True, tier, None

    # Build rejection message
    days_left = days_remaining(chat_id)
    if tier == TIER_FREE:
        msg = (
            "<b>Acceso VIP requerido</b>\n"
            "{fence}\n\n"
            "El comando {cmd} requiere suscripcion VIP.\n\n"
            "<b>Opciones:</b>\n"
            "{b} /precio - Ver planes y precios\n"
            "{b} /codigo XXXX - Canjear codigo de acceso\n"
            "{b} /vip - Adquirir suscripcion\n\n"
            "La mesa opera con disciplina y datos en tiempo real.\n"
            "El VIP da acceso a:\n"
            "{b} /analisis y /niveles con lectura asistida\n"
            "{b} /pspace con orderbook y muros de liquidez\n"
            "{b} Senales automaticas de alta conviccion\n"
            "{b} Co-piloto de IA en los mejores setups\n"
            "{b} Metricas y auditoria del track record\n"
        ).format(
            fence="─" * 30,
            cmd=cmd, b="›",
        )
    elif tier in (TIER_VIP, TIER_TRIAL) and days_left is not None and days_left <= 0:
        msg = (
            "<b>SUSCRIPCION EXPIRADA</b>\n"
            "Tu acceso vencio. Usa /renovar para extender."
        )
    else:
        msg = "Comando no disponible en tu plan actual."

    return False, tier, msg

# ============================================================
# ADMIN QUERIES
# ============================================================
def get_all_users(tier=None, limit=200):
    with _conn() as c:
        if tier:
            rows = c.execute(
                "SELECT * FROM users WHERE tier = ? ORDER BY last_seen_at DESC LIMIT ?",
                (tier, limit)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM users ORDER BY last_seen_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

def get_stats():
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        free  = c.execute("SELECT COUNT(*) FROM users WHERE tier = 'free'").fetchone()[0]
        trial = c.execute("SELECT COUNT(*) FROM users WHERE tier = 'trial'").fetchone()[0]
        vip   = c.execute("SELECT COUNT(*) FROM users WHERE tier = 'vip'").fetchone()[0]

        # Active VIPs (not expired)
        now_iso_v = now_iso()
        active_vip = c.execute(
            "SELECT COUNT(*) FROM users WHERE tier IN ('vip','trial') AND expires_at > ?",
            (now_iso_v,)
        ).fetchone()[0]

        revenue = c.execute(
            "SELECT COALESCE(SUM(amount_usd),0) FROM payments WHERE status = 'confirmed'"
        ).fetchone()[0]

        revenue_month = c.execute(
            """SELECT COALESCE(SUM(amount_usd),0) FROM payments
               WHERE status = 'confirmed' AND confirmed_at > ?""",
            ((datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),)
        ).fetchone()[0]

        codes_total = c.execute("SELECT COUNT(*) FROM codes").fetchone()[0]
        codes_used  = c.execute("SELECT COUNT(*) FROM codes WHERE used_by IS NOT NULL").fetchone()[0]

        return {
            "users_total":   total,
            "users_free":    free,
            "users_trial":   trial,
            "users_vip":     vip,
            "active_vips":   active_vip,
            "revenue_total": revenue,
            "revenue_30d":   revenue_month,
            "codes_total":   codes_total,
            "codes_used":    codes_used,
            "codes_unused":  codes_total - codes_used,
            "conversion_rate": (vip / total * 100) if total > 0 else 0,
        }

# ============================================================
# TELEGRAM FORMATTERS
# ============================================================
def format_precio_message():
    """Pagina de planes VIP."""
    rule = "─" * 30
    lines = [
        "<b>FQ · VIP</b>",
        rule,
        "  Senales multi-símbolo (SOL · BTC · ETH …) con disciplina sistematica.",
        "",
        "  · Entry, SL y TPs exactos",
        "  · SL anclado a estructura",
        "  · Analisis tactico on-demand",
        "  · Resultados verificables",
        "",
        "<b>Planes:</b>",
    ]
    for plan_id, info in PLAN_PRICES.items():
        if plan_id == "trial_7d":
            continue
        lines.append("  · {:<12} <b>${} USD</b>   {} dias".format(
            info["label"], info["price_usd"], info["days"]))
    lines.extend([
        "",
        rule,
        "  › /vip          Iniciar pago",
        "  › /codigo XXXX  Canjear codigo",
        "",
        "  Tarjeta (Stripe) o USDT (TRC20).",
    ])
    return "\n".join(lines)

def format_user_status(chat_id):
    """/miestado - estado del usuario"""
    u = get_user(chat_id)
    if not u:
        return "Sin registro. Usa /start primero."
    tier = get_effective_tier(chat_id)
    days = days_remaining(chat_id)

    lines = [
        "<b>MI ESTADO</b>",
        "─" * 30,
        "",
        "Usuario: {}".format(u.get("username") or u.get("first_name") or "anonimo"),
        "Tier:    <b>{}</b>".format(tier.upper()),
    ]
    if u.get("plan"):
        plan_info = PLAN_PRICES.get(u["plan"], {})
        lines.append("Plan:    {}".format(plan_info.get("label", u["plan"])))
    if days is not None:
        if days > 0:
            lines.append("Expira:  en {} dias ({})".format(
                days, u["expires_at"][:10]))
        else:
            lines.append("Expira:  EXPIRADA")
    if u.get("source"):
        lines.append("Fuente:  {}".format(u["source"]))
    lines.extend([
        "Desde:   {}".format(u["created_at"][:10]),
        "",
        "─" * 30,
    ])
    if tier == TIER_FREE:
        lines.append("Sin acceso VIP. Usa /precio o /vip.")
    elif tier == TIER_TRIAL:
        lines.append("Trial activo. /renovar para upgrade.")
    elif tier == TIER_VIP:
        lines.append("VIP activo. Disfruta el sistema completo.")
    elif tier == TIER_ADMIN:
        lines.append("ADMIN. Acceso total ilimitado.")
    return "\n".join(lines)

def format_admin_stats():
    s = get_stats()
    return (
        "<b>ADMIN STATS</b>\n"
        + ("─" * 30) + "\n\n"
        "<b>USUARIOS:</b>\n"
        "Total:        {ut}\n"
        "Free:         {uf}\n"
        "Trial:        {utr}\n"
        "VIP:          {uv}\n"
        "Activos:      {av}\n"
        "Conversion:   {conv:.1f}%\n\n"
        "<b>REVENUE:</b>\n"
        "Total:        ${rt:.2f}\n"
        "Ultimos 30d:  ${r30:.2f}\n\n"
        "<b>CODIGOS:</b>\n"
        "Generados:    {ct}\n"
        "Canjeados:    {cu}\n"
        "Sin usar:     {cn}\n"
    ).format(
        ut=s["users_total"], uf=s["users_free"],
        utr=s["users_trial"], uv=s["users_vip"],
        av=s["active_vips"], conv=s["conversion_rate"],
        rt=s["revenue_total"], r30=s["revenue_30d"],
        ct=s["codes_total"], cu=s["codes_used"], cn=s["codes_unused"],
    )

def format_users_list(limit=20):
    users = get_all_users(limit=limit)
    if not users:
        return "Sin usuarios aun."
    lines = ["<b>USUARIOS RECIENTES (top {})</b>".format(limit), "─" * 30, ""]
    for u in users:
        days = "-"
        if u.get("expires_at"):
            try:
                exp = datetime.fromisoformat(u["expires_at"])
                d = (exp - datetime.now(timezone.utc)).days
                days = "{}d".format(d) if d > 0 else "EXP"
            except Exception:
                pass
        name = (u.get("username") or u.get("first_name") or u["chat_id"])[:18]
        lines.append("[{tier:5}] {name:<18} {days:<6} {created}".format(
            tier=u["tier"][:5], name=name, days=days,
            created=u["created_at"][:10]
        ))
    return "\n".join(lines)
