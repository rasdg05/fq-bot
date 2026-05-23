# -*- coding: utf-8 -*-
"""
================================================================================
  PUBLIC BOT FORMAT - Estetica Mistral Emergent Time con glyphs Unicode
  by RasDG_Sol + Claude

  Glyphs sutiles (no emoji-style): ━ ◆ ▰ ▸ ▪ ▴ ▾
  Renderea identico en Telegram Android/iOS/desktop.
================================================================================
"""
from datetime import datetime, timezone, timedelta

CDMX_TZ = timezone(timedelta(hours=-6))

# ============================================================
# GLYPHS - todos Unicode solido, no emoji-style
# ============================================================
G = {
    "rule":       "━" * 30,   # ━━━...
    "title":      "◆",         # ◆
    "event":      "▰",         # ▰
    "bullet_act": "▸",         # ▸
    "bullet_chk": "▪",         # ▪
    "long":       "▴",         # ▴
    "short":      "▾",         # ▾
}

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
        G["rule"],
        "  {} FQ · Cierre confirmado".format(G["title"]),
        G["rule"],
        "  {} {} SOL/USDT".format(side_glyph, side_label),
        "  {} Disparada    {}".format(G["bullet_act"], ts_emit),
        "  {} Cerrada      {}".format(G["bullet_act"], ts_close),
        "  {} Resultado    {}  ·  {:+.2f}R".format(G["bullet_act"], outcome, pnl_r),
        "  {} Duracion     {}".format(G["bullet_act"], duration),
        G["rule"],
    ]

    if stats_7d and stats_7d.get("n_closed_7d", 0) > 0:
        n = stats_7d.get("n_closed_7d", 0)
        plural = "es" if n != 1 else ""
        lines.extend([
            "  {} senal{} cerrada{} esta".format(n, plural, plural),
            "  semana en el canal VIP.",
            "  {} Win rate 7d     {:.0%}".format(G["bullet_chk"], stats_7d["win_rate_7d"]),
            "  {} Expectancy      {:+.2f}R".format(G["bullet_chk"], stats_7d["expectancy_7d"]),
            G["rule"],
        ])

    lines.append("  {} Acceso al VIP   /unirme".format(G["bullet_act"]))
    return "\n".join(lines)

# ============================================================
# TEASER DE SENAL NUEVA - sin niveles, solo direccion/sesion/conviccion
# ============================================================
SESSION_LABELS = {
    "asia":    "Asia",
    "london":  "Londres",
    "ny":      "NY killzone",
    "overlap": "Overlap LDN/NY",
}

def build_new_signal_teaser(signal_row):
    """
    signal_row: dict con direction, ts_emitted, session, p_master_final
    Nunca expone entry/SL/TPs - solo crea expectativa.
    """
    direction = (signal_row.get("direction") or "").lower()
    side_glyph = G["long"] if direction == "long" else G["short"]
    side_label = direction.upper() or "?"

    session = (signal_row.get("session") or "").lower()
    session_label = SESSION_LABELS.get(session, session.capitalize() or "?")

    p_master = float(signal_row.get("p_master_final") or 0.0)
    label = conviction_label(p_master)
    score = conviction_score(p_master)

    ts_emit = _fmt_dt(signal_row.get("ts_emitted"))

    return "\n".join([
        G["rule"],
        "  {} FQ · Senal disparada".format(G["title"]),
        G["rule"],
        "  {} {} SOL/USDT".format(side_glyph, side_label),
        "  {} Sesion       {}".format(G["bullet_act"], session_label),
        "  {} Conviccion   {} · {}/10".format(G["bullet_act"], label, score),
        "  {} Disparada    {}".format(G["bullet_act"], ts_emit),
        G["rule"],
        "  Entry, SL y 4 TPs ya",
        "  publicados en el canal VIP.",
        "",
        "  {} Acceso al VIP    /unirme".format(G["bullet_act"]),
    ])

# ============================================================
# MOCKUP C: LECTURA DEL DIA (generada por Claude Sonnet)
# ============================================================
def wrap_lectura(titulo, cuerpo):
    """Envuelve la lectura generada por Claude en el formato Mistral Emergent Time"""
    return "\n".join([
        G["rule"],
        "  {} FQ · Lectura del dia".format(G["title"]),
        G["rule"],
        "  " + titulo.strip(),
        "",
        cuerpo.strip(),
        G["rule"],
        "  {} Mas lecturas    /info".format(G["bullet_act"]),
        "  {} VIP             /unirme".format(G["bullet_act"]),
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
        G["rule"],
        "  {} FQ · VIP".format(G["title"]),
        G["rule"],
    ]
    for label, price, off in PRICE_TIERS:
        if off:
            lines.append("  {} {:<13} {:<10} {}".format(
                G["bullet_act"], label, price, off))
        else:
            lines.append("  {} {:<13} {}".format(
                G["bullet_act"], label, price))
    lines.extend([
        G["rule"],
        "  Lo que recibes:",
        "  {} Senales SOL/USDT en vivo".format(G["bullet_chk"]),
        "  {} Niveles exactos: entry, SL, TPs".format(G["bullet_chk"]),
        "  {} Analisis tactico bajo demanda".format(G["bullet_chk"]),
        "  {} Auditoria sistemica cada 25 trades".format(G["bullet_chk"]),
        G["rule"],
        "  {} Tarjeta      /stripe".format(G["bullet_act"]),
        "  {} USDT         /crypto".format(G["bullet_act"]),
        "  {} Codigo       /codigo XXXX".format(G["bullet_act"]),
    ])
    return "\n".join(lines)

# ============================================================
# MOCKUP E: COMANDO DESCONOCIDO / WELCOME
# ============================================================
def build_welcome():
    return "\n".join([
        G["rule"],
        "  {} FQ · Bot publico".format(G["title"]),
        G["rule"],
        "  Este canal emite reportes",
        "  y resultados del canal VIP.",
        "",
        "  Para senales en vivo, niveles,",
        "  y analisis tactico:",
        "",
        "  {} /unirme    al VIP".format(G["bullet_act"]),
        "  {} /info      saber mas".format(G["bullet_act"]),
        "  {} /precio    tarifas".format(G["bullet_act"]),
        G["rule"],
    ])

def build_unknown():
    """Cualquier comando no reconocido"""
    return build_welcome()

# ============================================================
# MOCKUP F: STATS SEMANALES (cada domingo)
# ============================================================
def build_weekly_stats(stats):
    """
    stats: dict con n_total_7d, n_closed_7d, wins, sls, win_rate,
           expectancy, profit_factor, best_pnl, longest_streak
    """
    lines = [
        G["rule"],
        "  {} FQ · Reporte semanal".format(G["title"]),
        G["rule"],
        "  Cierre de semana en VIP:",
        "",
        "  {} Senales cerradas   {}".format(G["bullet_chk"], stats.get("n_closed_7d", 0)),
        "  {} Win rate           {:.0%}".format(G["bullet_chk"], stats.get("win_rate", 0)),
        "  {} Expectancy         {:+.2f}R".format(G["bullet_chk"], stats.get("expectancy", 0)),
        "  {} Profit factor      {:.2f}".format(G["bullet_chk"], stats.get("profit_factor", 0)),
    ]
    if stats.get("best_pnl"):
        lines.append("  {} Mejor cierre       {:+.2f}R".format(
            G["bullet_chk"], stats["best_pnl"]))
    lines.extend([
        G["rule"],
        "  La proxima semana,",
        "  mismo sistema.",
        "",
        "  {} Acceso al VIP    /unirme".format(G["bullet_act"]),
    ])
    return "\n".join(lines)

# ============================================================
# CTAS ROTATIVOS (texto plano, sin LLM)
# ============================================================
CTA_VARIANTS = [
    (
        "{} FQ · Recordatorio".format(G["title"]),
        "El edge del sistema no espera.",
        "Cada senal del VIP llega con",
        "entry, SL y 4 TPs ya calculados.",
        "Cero ambiguedad, cero opinion.",
    ),
    (
        "{} FQ · Disciplina sistemica".format(G["title"]),
        "El sistema no opera con miedo",
        "ni con codicia. Solo con datos.",
        "Cada trade del VIP pasa por 4",
        "fases antes de disparar.",
    ),
    (
        "{} FQ · Edge medible".format(G["title"]),
        "No vendemos predicciones.",
        "Vendemos expectancy positiva",
        "auditada cada 25 trades por",
        "el motor evolutivo Opus 4.6.",
    ),
    (
        "{} FQ · Estructura no opinion".format(G["title"]),
        "Liquidez, killzones, OTE.",
        "Cada nivel viene de la lectura",
        "del campo, no de la corazonada",
        "del operador del momento.",
    ),
    (
        "{} FQ · Memoria que evoluciona".format(G["title"]),
        "El bot recuerda cada cierre.",
        "Cada bucket aprende. Cada",
        "concepto ICT se valida con data.",
        "Thompson sampling al timon.",
    ),
    (
        "{} FQ · Mientras lees esto".format(G["title"]),
        "El motor escanea SOL/USDT",
        "cada minuto. Sin pausa.",
        "Las senales del VIP no esperan",
        "a que abras el chat.",
    ),
    (
        "{} FQ · Cinco capas".format(G["title"]),
        "Macro, tecnica, liquidez,",
        "P-space, Quantum Timelines.",
        "Cinco filtros antes de que",
        "una senal toque el VIP.",
    ),
    (
        "{} FQ · El silencio del bot".format(G["title"]),
        "Cuando no hay edge, calla.",
        "Cuando habla, ya paso por las",
        "cinco capas. No es ruido:",
        "es probabilidad calculada.",
    ),
    (
        "{} FQ · Cada killzone cuenta".format(G["title"]),
        "Cada cierre afina al motor.",
        "Cada bucket actualiza pesos.",
        "El sistema que entra al VIP",
        "manana, no es el de hoy.",
    ),
    (
        "{} FQ · Otros venden senales".format(G["title"]),
        "Aqui se mide expectancy.",
        "Se auditan resultados cada 25",
        "trades. Se publican stats reales.",
        "El edge es verificable.",
    ),
]

def build_cta(variant_idx):
    """variant_idx: int para rotar; modulo len(CTA_VARIANTS)"""
    v = CTA_VARIANTS[variant_idx % len(CTA_VARIANTS)]
    lines = [G["rule"], "  " + v[0], G["rule"]]
    for ln in v[1:]:
        lines.append("  " + ln)
    lines.extend([
        G["rule"],
        "  {} Conocer mas    /info".format(G["bullet_act"]),
        "  {} Unirse al VIP  /unirme".format(G["bullet_act"]),
    ])
    return "\n".join(lines)

# ============================================================
# /info detallado (template estatico)
# ============================================================
def build_info():
    return "\n".join([
        G["rule"],
        "  {} FQ · Sistema cuantico-ICT".format(G["title"]),
        G["rule"],
        "  FQ es un sistema de senales para",
        "  SOL/USDT operado por RasDG_Sol.",
        "",
        "  No es un grupo. No es analisis.",
        "  Es un motor cerrado que emite",
        "  setups con entry, SL y 4 TPs.",
        "",
        "  {} 14 conceptos ICT/SMC".format(G["bullet_chk"]),
        "  {} Killzones Silver Bullet".format(G["bullet_chk"]),
        "  {} Memoria autoevolutiva".format(G["bullet_chk"]),
        "  {} Audit Opus cada 25 trades".format(G["bullet_chk"]),
        "  {} Disciplina: SL inmutable".format(G["bullet_chk"]),
        "",
        "  El edge se mide. No se cree.",
        G["rule"],
        "  {} Ver precios    /precio".format(G["bullet_act"]),
        "  {} Unirse al VIP  /unirme".format(G["bullet_act"]),
    ])

# ============================================================
# Deep link al bot VIP con codigo embedded
# ============================================================
def build_codigo_response(codigo, vip_bot_username):
    """Cuando alguien escribe /codigo XXXX en el bot publico, se le manda
       un deep link al bot VIP con el codigo pre-llenado en /start."""
    if not codigo or not vip_bot_username:
        return "\n".join([
            G["rule"],
            "  {} FQ · Codigo".format(G["title"]),
            G["rule"],
            "  Formato: /codigo XXXX-XXXX",
            "",
            "  Si tu codigo es valido, el",
            "  bot te dara un link al VIP.",
            G["rule"],
        ])
    link = "https://t.me/{}?start={}".format(vip_bot_username, codigo)
    return "\n".join([
        G["rule"],
        "  {} FQ · Codigo recibido".format(G["title"]),
        G["rule"],
        "  El bot VIP validara tu codigo.",
        "  Toca el siguiente link para",
        "  abrirlo con el codigo cargado:",
        "",
        "  {}".format(link),
        "",
        "  Si el codigo es valido, se",
        "  activa tu acceso al VIP.",
        G["rule"],
    ])

# ============================================================
# /unirme - menu rapido (sin disclaim de precios)
# ============================================================
def build_unirme(vip_bot_username):
    if vip_bot_username:
        link = "https://t.me/{}?start=public_signup".format(vip_bot_username)
    else:
        link = "@RasDG_Sol"
    return "\n".join([
        G["rule"],
        "  {} FQ · Unirse al VIP".format(G["title"]),
        G["rule"],
        "  3 formas de entrar:",
        "",
        "  {} /stripe    pago con tarjeta".format(G["bullet_act"]),
        "  {} /crypto    pago con USDT".format(G["bullet_act"]),
        "  {} /codigo    tienes un codigo?".format(G["bullet_act"]),
        "",
        "  Tambien puedes hablar directo",
        "  con el bot VIP:",
        "  {}".format(link),
        G["rule"],
    ])

# ============================================================
# /stripe y /crypto - placeholders con links configurables
# ============================================================
def build_stripe(stripe_link):
    link = stripe_link or "(pendiente de configurar)"
    return "\n".join([
        G["rule"],
        "  {} FQ · Pago con tarjeta".format(G["title"]),
        G["rule"],
        "  Stripe seguro.",
        "  Activacion inmediata.",
        "",
        "  {}".format(link),
        "",
        "  Despues del pago recibiras",
        "  un codigo de activacion via",
        "  email. Usalo con /codigo XXXX",
        "  en el bot VIP.",
        G["rule"],
    ])

def build_crypto(usdt_address, network="TRC20"):
    addr = usdt_address or "(pendiente)"
    return "\n".join([
        G["rule"],
        "  {} FQ · Pago con USDT".format(G["title"]),
        G["rule"],
        "  USDT {} (rapido y barato)".format(network),
        "",
        "  Direccion:",
        "  {}".format(addr),
        "",
        "  Tras tu transferencia, envia",
        "  el TXID a @RasDG_Sol y se te",
        "  genera tu codigo de activacion.",
        G["rule"],
    ])

# ============================================================
# MANTRAS MISTRAL QUANTUM - pildoras filosoficas del trading
# Rotacion deterministica por dia del ano - una al amanecer, otra al cierre.
# ============================================================
MANTRAS = [
    "El edge no se busca. Se mide. El que mide gana.",
    "El stop loss es la unica certeza que un trader controla.",
    "Paciencia es un activo descontado: paga al final del ciclo.",
    "Cinco gates antes de disparar. Esa es la diferencia entre operar y rezar.",
    "Mercado no premia opinion. Premia estructura.",
    "El sistema no recuerda tu ultima perdida. Su edge tampoco.",
    "Liquidez se forma donde la mayoria coloca su stop.",
    "Killzone NY: dos horas donde el dinero institucional se mueve. El resto es ruido.",
    "Una senal sin probabilidad declarada es una opinion disfrazada.",
    "El precio no respeta tu entry. Respeta la estructura que lo sostiene.",
    "Mover el SL para 'darle aire' es destruir el edge con tus propias manos.",
    "El displacement marca decision. El ranging marca indecision. Lee la diferencia.",
    "Inducement: liquidez creada para ser barrida. No te pares ahi.",
    "OTE 70.5: el punto donde el riesgo es estructural, no emocional.",
    "Power of 3: acumulacion, manipulacion, distribucion. En ese orden.",
    "Cada cierre en TP4 vale lo mismo que el ultimo. Cero memoria emocional.",
    "El edge probabilistico se cobra en miles de trades, no en cinco.",
    "Confluencia no es coincidencia. Es estructura repetida en tres timeframes.",
    "Asia acumula. Londres manipula. NY distribuye. Conoce la fase, conoce el trade.",
    "El SL inmutable es la prueba de que el sistema, no tu, opera.",
    "El bot que opera con miedo no es bot. Es operador disfrazado.",
    "Edge medible vence a intuicion no auditada. Siempre.",
    "Una senal selectiva pesa mas que cien senales optimistas.",
    "Premium para vender. Discount para comprar. El resto es zona gris.",
    "Market Structure Shift: la primera huella del giro. No la ultima.",
    "El weekend no opera. Spreads anchos, liquidez delgada, sin volumen real.",
    "Thompson sampling decide por que bucket es turno. No lo decide la corazonada.",
    "Cada concepto ICT vale lo que su backtest probabilistico declara.",
    "Si una senal no pasa los cinco gates, no es senal. Es ansiedad.",
    "El sistema no aprende rapido. Aprende correcto.",
]

def build_mantra(idx):
    """idx: int para rotar; modulo len(MANTRAS)"""
    frase = MANTRAS[idx % len(MANTRAS)]
    return "\n".join([
        G["rule"],
        "  {} FQ · Lectura breve".format(G["title"]),
        G["rule"],
        "",
        "  " + frase,
        "",
        G["rule"],
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
