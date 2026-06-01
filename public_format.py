# -*- coding: utf-8 -*-
"""
Public bot format. Construye strings de cara al cliente publico.
Sin versiones, sin formulas, sin jerga de motor.
"""
from datetime import datetime, timezone, timedelta

from branding import PRODUCT, PAIR, GLYPHS, RULE, DISCLAIMER

CDMX_TZ = timezone(timedelta(hours=-6))

# Alias para compat con codigo existente del modulo.
G = GLYPHS

def _cdmx_now():
    return datetime.now(CDMX_TZ)

def _fmt_dt(dt=None):
    if dt is None:
        dt = _cdmx_now()
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt[:16]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CDMX_TZ).strftime("%H:%M CDMX")

# ============================================================
# DISFRAZ DE FORMULAS - tier label sin numero crudo
# ============================================================
def conviction_label(p_master):
    """P_master interno -> label publico sin formula"""
    PHI = 1.6180339887
    if p_master >= PHI ** 3:    return "EXTREMA"
    elif p_master >= PHI ** 2:  return "ALTA"
    elif p_master >= PHI:       return "MEDIA"
    return "BAJA"

def conviction_score(p_master):
    """P_master -> score 1-10 sin formula expuesta"""
    PHI = 1.6180339887
    return max(1, min(10, round(p_master / (PHI ** 3) * 10)))

# ============================================================
# MOCKUP B: ANUNCIO DE CIERRE +1R (lo que el bot publico mas usa)
# ============================================================
def build_closure_announcement(signal_row, stats_7d=None):
    """
    signal_row: dict con direction, entry_price, exit_price, outcome, pnl_r,
                ts_emitted, ts_closed, minutes_open
    stats_7d:   dict opcional con n_closed_7d, win_rate_7d, expectancy_7d
    """
    direction = signal_row.get("direction", "").lower()
    side_glyph = G["long"] if direction == "long" else G["short"]
    side_label = direction.upper()

    outcome = signal_row.get("outcome", "?").upper()
    pnl_r = signal_row.get("pnl_r", 0)
    minutes = signal_row.get("minutes_open", 0)
    hours = minutes // 60
    mins  = minutes % 60
    duration = "{}h {}m".format(hours, mins) if hours else "{}m".format(mins)

    ts_emit = _fmt_dt(signal_row.get("ts_emitted"))
    ts_close = _fmt_dt(signal_row.get("ts_closed"))

    lines = [
        RULE,
        "  {} {} · Cierre confirmado".format(G["title"], PRODUCT),
        RULE,
        "  {} {} {}".format(side_glyph, side_label, PAIR),
        "  {} Disparada    {}".format(G["bullet_act"], ts_emit),
        "  {} Cerrada      {}".format(G["bullet_act"], ts_close),
        "  {} Resultado    {}  ·  {:+.2f}R".format(G["bullet_act"], outcome, pnl_r),
        "  {} Duracion     {}".format(G["bullet_act"], duration),
        RULE,
    ]

    if stats_7d and stats_7d.get("n_closed_7d", 0) > 0:
        n = stats_7d.get("n_closed_7d", 0)
        plural = "es" if n != 1 else ""
        lines.extend([
            "  {} senal{} cerrada{} esta semana.".format(n, plural, "s" if n != 1 else ""),
            "  {} Win rate 7d     {:.0%}".format(G["bullet_chk"], stats_7d["win_rate_7d"]),
            RULE,
        ])

    lines.append("  {} Acceso VIP    /unirme".format(G["bullet_act"]))
    return "\n".join(lines)

# ============================================================
# TEASER DE SENAL NUEVA - sin niveles, solo direccion/sesion/conviccion
# ============================================================
SESSION_LABELS = {
    "asia":    "Asia",
    "london":  "Londres",
    "ny":      "Nueva York",
    "overlap": "Overlap LDN/NY",
}

def build_new_signal_teaser(signal_row):
    """Teaser publico. No expone niveles. No expone score numerico."""
    direction = (signal_row.get("direction") or "").lower()
    side_glyph = G["long"] if direction == "long" else G["short"]
    side_label = direction.upper() or "?"

    session = (signal_row.get("session") or "").lower()
    session_label = SESSION_LABELS.get(session, session.capitalize() or "?")

    p_master = float(signal_row.get("p_master_final") or 0.0)
    label = conviction_label(p_master)

    ts_emit = _fmt_dt(signal_row.get("ts_emitted"))

    return "\n".join([
        RULE,
        "  {} {} · Senal disparada".format(G["title"], PRODUCT),
        RULE,
        "  {} {} {}".format(side_glyph, side_label, PAIR),
        "  {} Sesion       {}".format(G["bullet_act"], session_label),
        "  {} Conviccion   {}".format(G["bullet_act"], label.title()),
        "  {} Disparada    {}".format(G["bullet_act"], ts_emit),
        RULE,
        "  Niveles publicados en el VIP.",
        "",
        "  {} Acceso VIP    /unirme".format(G["bullet_act"]),
    ])

# ============================================================
# MOCKUP C: LECTURA DEL DIA (generada por Claude Sonnet)
# ============================================================
def wrap_lectura(titulo, cuerpo):
    """Envuelve la lectura editorial generada por el LLM."""
    return "\n".join([
        RULE,
        "  {} {} · Lectura del dia".format(G["title"], PRODUCT),
        RULE,
        "  " + titulo.strip(),
        "",
        cuerpo.strip(),
        RULE,
        "  {} Mas      /info".format(G["bullet_act"]),
        "  {} VIP      /unirme".format(G["bullet_act"]),
    ])

# ============================================================
# MOCKUP D: CTA / PRECIOS
# ============================================================
PRICE_TIERS = [
    ("Mensual",     "$49 USD",    None),
    ("Trimestral",  "$129",       "-12%"),
    ("Anual",       "$449",       "-24%"),
    ("Lifetime",    "$1,200",     None),
]

def build_pricing():
    lines = [
        RULE,
        "  {} {} · VIP".format(G["title"], PRODUCT),
        RULE,
    ]
    for label, price, off in PRICE_TIERS:
        if off:
            lines.append("  {} {:<13} {:<10} {}".format(
                G["bullet_act"], label, price, off))
        else:
            lines.append("  {} {:<13} {}".format(
                G["bullet_act"], label, price))
    lines.extend([
        RULE,
        "  Incluye:",
        "  {} Senales {} en vivo".format(G["bullet_chk"], PAIR),
        "  {} Entry, SL y TPs exactos".format(G["bullet_chk"]),
        "  {} Analisis on-demand".format(G["bullet_chk"]),
        "  {} Resultados verificables".format(G["bullet_chk"]),
        RULE,
        "  {} Tarjeta    /stripe".format(G["bullet_act"]),
        "  {} USDT       /crypto".format(G["bullet_act"]),
        "  {} Codigo     /codigo XXXX".format(G["bullet_act"]),
    ])
    return "\n".join(lines)

# ============================================================
# MOCKUP E: COMANDO DESCONOCIDO / WELCOME
# ============================================================
def build_welcome():
    return "\n".join([
        RULE,
        "  {} {}".format(G["title"], PRODUCT),
        RULE,
        "  Canal publico de reportes y",
        "  resultados verificables del VIP.",
        "",
        "  {} /unirme      Activar VIP".format(G["bullet_act"]),
        "  {} /precio      Tarifas".format(G["bullet_act"]),
        "  {} /resultados  Track record".format(G["bullet_act"]),
        "  {} /info        Sobre el sistema".format(G["bullet_act"]),
        RULE,
    ])

def build_unknown():
    """Cualquier comando no reconocido"""
    return build_welcome()

# ============================================================
# MOCKUP F: STATS SEMANALES (cada domingo)
# ============================================================
def build_weekly_stats(stats):
    """Reporte semanal publico desde ledger real."""
    lines = [
        RULE,
        "  {} {} · Semana".format(G["title"], PRODUCT),
        RULE,
        "  {} Senales cerradas   {}".format(G["bullet_chk"], stats.get("n_closed_7d", 0)),
        "  {} Win rate           {:.0%}".format(G["bullet_chk"], stats.get("win_rate", 0)),
        "  {} Expectancy         {:+.2f}R".format(G["bullet_chk"], stats.get("expectancy", 0)),
        "  {} Profit factor      {:.2f}".format(G["bullet_chk"], stats.get("profit_factor", 0)),
    ]
    if stats.get("best_pnl"):
        lines.append("  {} Mejor cierre       {:+.2f}R".format(
            G["bullet_chk"], stats["best_pnl"]))
    lines.extend([
        RULE,
        "  {}".format(DISCLAIMER),
        "",
        "  {} VIP    /unirme".format(G["bullet_act"]),
    ])
    return "\n".join(lines)

# ============================================================
# /resultados - track record verificable desde ledger real
# ============================================================
def _fmt_window(label, w):
    """Renderiza una ventana de stats. Texto sobrio si vacia."""
    if not w:
        return "  {}\n  {} sin cierres aun".format(label, G["bullet_chk"])
    pf = w["profit_factor"]
    pf_str = "inf" if pf == float("inf") else "{:.2f}".format(pf)
    return (
        "  {label}\n"
        "  {chk} Senales      {n}\n"
        "  {chk} Win rate     {wr:.0%}\n"
        "  {chk} Expectancy   {ex:+.2f}R\n"
        "  {chk} Profit fctr  {pf}"
    ).format(label=label, chk=G["bullet_chk"], n=w["n"],
             wr=w["win_rate"], ex=w["expectancy"], pf=pf_str)

def build_resultados(summary):
    """Track record. summary = dict de compute_results_summary, o None."""
    if not summary or not summary.get("total"):
        return "\n".join([
            RULE,
            "  {} {} · Resultados".format(G["title"], PRODUCT),
            RULE,
            "  Aun no hay cierres registrados.",
            "  El track record se publica aqui",
            "  conforme el sistema opera.",
            RULE,
            "  {} VIP    /unirme".format(G["bullet_act"]),
        ])
    lines = [
        RULE,
        "  {} {} · Resultados".format(G["title"], PRODUCT),
        RULE,
        "  Verificable desde el registro",
        "  interno del sistema.",
        "",
        _fmt_window("Ultimos 30 dias", summary.get("w30")),
        "",
        _fmt_window("Ultimos 90 dias", summary.get("w90")),
        "",
        _fmt_window("Historico total", summary.get("total")),
    ]
    streak = summary.get("longest_streak") or 0
    if streak >= 2:
        lines.append("")
        lines.append("  {} Mejor racha   {} cierres".format(G["bullet_chk"], streak))
    lines.extend([
        RULE,
        "  {}".format(DISCLAIMER),
        "",
        "  {} VIP    /unirme".format(G["bullet_act"]),
    ])
    return "\n".join(lines)

# ============================================================
# CTAS ROTATIVOS (texto plano, sin LLM)
# ============================================================
CTA_VARIANTS = [
    (
        "{} {} · Recordatorio".format(G["title"], PRODUCT),
        "Cada senal del VIP llega con",
        "entry, SL y TPs ya calculados.",
        "Cero ambiguedad.",
    ),
    (
        "{} {} · Disciplina".format(G["title"], PRODUCT),
        "El sistema no opera con miedo",
        "ni con codicia. Solo con datos.",
    ),
    (
        "{} {} · Edge medible".format(G["title"], PRODUCT),
        "No vendemos predicciones.",
        "Vendemos resultados auditables.",
    ),
    (
        "{} {} · Estructura".format(G["title"], PRODUCT),
        "Cada nivel viene de la lectura",
        "del mercado, no de la corazonada.",
    ),
    (
        "{} {} · Mientras lees esto".format(G["title"], PRODUCT),
        "El motor escanea {} sin pausa.".format(PAIR),
        "Las senales del VIP no esperan",
        "a que abras el chat.",
    ),
    (
        "{} {} · El silencio".format(G["title"], PRODUCT),
        "Cuando no hay edge, calla.",
        "Cuando habla, ya paso los filtros.",
    ),
    (
        "{} {} · Cada cierre cuenta".format(G["title"], PRODUCT),
        "El sistema afina con cada trade.",
        "El que entra al VIP manana",
        "no es el de hoy.",
    ),
    (
        "{} {} · Resultados verificables".format(G["title"], PRODUCT),
        "Win rate, expectancy y profit",
        "factor publicados desde el ledger.",
        "Compruebalo en /resultados.",
    ),
]

def build_cta(variant_idx):
    """Rota CTAs deterministicamente."""
    v = CTA_VARIANTS[variant_idx % len(CTA_VARIANTS)]
    lines = [RULE, "  " + v[0], RULE]
    for ln in v[1:]:
        lines.append("  " + ln)
    lines.extend([
        RULE,
        "  {} Conocer mas    /info".format(G["bullet_act"]),
        "  {} Unirse al VIP  /unirme".format(G["bullet_act"]),
    ])
    return "\n".join(lines)

# ============================================================
# /info
# ============================================================
def build_info():
    return "\n".join([
        RULE,
        "  {} {}".format(G["title"], PRODUCT),
        RULE,
        "  Senales {} con disciplina".format(PAIR),
        "  sistematica.",
        "",
        "  {} Entry, SL y TPs exactos".format(G["bullet_chk"]),
        "  {} SL anclado a estructura".format(G["bullet_chk"]),
        "  {} Resultados verificables".format(G["bullet_chk"]),
        "  {} Veto fin de semana".format(G["bullet_chk"]),
        RULE,
        "  {} Tarifas       /precio".format(G["bullet_act"]),
        "  {} Track record  /resultados".format(G["bullet_act"]),
        "  {} VIP           /unirme".format(G["bullet_act"]),
    ])

# ============================================================
# Deep link al bot VIP con codigo embedded
# ============================================================
def build_codigo_response(codigo, vip_bot_username):
    """Deep link al bot VIP con codigo embebido en /start."""
    if not codigo or not vip_bot_username:
        return "\n".join([
            RULE,
            "  {} {} · Codigo".format(G["title"], PRODUCT),
            RULE,
            "  Formato: /codigo XXXX-XXXX",
            "",
            "  Si tu codigo es valido, el bot",
            "  VIP te dara acceso.",
            RULE,
        ])
    link = "https://t.me/{}?start={}".format(vip_bot_username, codigo)
    return "\n".join([
        RULE,
        "  {} {} · Codigo recibido".format(G["title"], PRODUCT),
        RULE,
        "  Toca el siguiente link para",
        "  validar tu codigo en el VIP:",
        "",
        "  {}".format(link),
        RULE,
    ])

# ============================================================
# /unirme
# ============================================================
def build_unirme(vip_bot_username):
    if vip_bot_username:
        link = "https://t.me/{}?start=public_signup".format(vip_bot_username)
    else:
        link = "@RasDG_Sol"
    return "\n".join([
        RULE,
        "  {} {} · Unirse al VIP".format(G["title"], PRODUCT),
        RULE,
        "  {} /stripe    Tarjeta".format(G["bullet_act"]),
        "  {} /crypto    USDT".format(G["bullet_act"]),
        "  {} /codigo    Codigo de acceso".format(G["bullet_act"]),
        "",
        "  Bot VIP: {}".format(link),
        RULE,
    ])

# ============================================================
# /stripe y /crypto
# ============================================================
def build_stripe(stripe_link):
    link = stripe_link or "(pendiente de configurar)"
    return "\n".join([
        RULE,
        "  {} {} · Tarjeta".format(G["title"], PRODUCT),
        RULE,
        "  Stripe seguro.",
        "",
        "  {}".format(link),
        "",
        "  Al completar el pago recibiras",
        "  tu codigo de acceso.",
        RULE,
    ])

def build_crypto(usdt_address, network="TRC20"):
    addr = usdt_address or "(pendiente)"
    return "\n".join([
        RULE,
        "  {} {} · USDT".format(G["title"], PRODUCT),
        RULE,
        "  Red {}".format(network),
        "",
        "  Direccion:",
        "  {}".format(addr),
        "",
        "  Tras la transferencia recibiras",
        "  tu codigo de acceso.",
        RULE,
    ])

# ============================================================
# MANTRAS MISTRAL QUANTUM - pildoras filosoficas del trading
# Rotacion deterministica por dia del ano - una al amanecer, otra al cierre.
# ============================================================
MANTRAS = [
    "El edge no se busca. Se mide. El que mide gana.",
    "El stop loss es la unica certeza que un trader controla.",
    "Paciencia es un activo descontado: paga al final del ciclo.",
    "Mercado no premia opinion. Premia estructura.",
    "El sistema no recuerda tu ultima perdida. Su edge tampoco.",
    "Liquidez se forma donde la mayoria coloca su stop.",
    "Una senal sin probabilidad declarada es una opinion disfrazada.",
    "El precio no respeta tu entry. Respeta la estructura que lo sostiene.",
    "Mover el SL para 'darle aire' es destruir el edge con tus propias manos.",
    "Cada cierre vale lo mismo que el ultimo. Cero memoria emocional.",
    "El edge probabilistico se cobra en miles de trades, no en cinco.",
    "Confluencia no es coincidencia. Es estructura repetida.",
    "El SL inmutable es la prueba de que el sistema, no tu, opera.",
    "El bot que opera con miedo no es bot. Es operador disfrazado.",
    "Edge medible vence a intuicion no auditada. Siempre.",
    "Una senal selectiva pesa mas que cien senales optimistas.",
    "El weekend no opera. Liquidez delgada, sin volumen real.",
    "El sistema no aprende rapido. Aprende correcto.",
    "Calidad sobre cantidad. Siempre.",
    "Cuando hay edge, dispara. Cuando no, calla.",
]

def build_mantra(idx):
    """Rota mantras deterministicamente."""
    frase = MANTRAS[idx % len(MANTRAS)]
    return "\n".join([
        RULE,
        "  {} {}".format(G["title"], PRODUCT),
        RULE,
        "",
        "  " + frase,
        "",
        RULE,
        "  {} Mas /info  ·  VIP /unirme".format(G["bullet_act"]),
    ])

def pick_mantra_idx_for_today(slot_h=None):
    """
    Rota deterministicamente segun dia del ano + slot.
    Asi 06:00 y 22:30 del mismo dia tienen mantras distintos.
    """
    day_of_year = _cdmx_now().timetuple().tm_yday
    base = day_of_year * 2
    if slot_h is not None and slot_h >= 12:
        base += 1
    return base % len(MANTRAS)
