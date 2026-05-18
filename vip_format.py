# -*- coding: utf-8 -*-
"""
================================================================================
  VIP FORMAT - Mistral edition (curated, minimalist, formula-hidden)
  by RasDG_Sol + Claude

  Lo que ve un usuario VIP NO debe permitir reverse-engineering del sistema.
  Lo que ve el admin (tu chat_id) muestra TODO sin filtro.

  Modulo INERTE - solo construye strings. No envia, no consulta DB.
================================================================================
"""
from datetime import datetime, timezone, timedelta

CDMX_TZ = timezone(timedelta(hours=-6))

PHI    = 1.6180339887
PHI_SQ = PHI * PHI
PHI_CB = PHI ** 3

# ============================================================
# DISFRAZ DE METRICAS - sin formulas expuestas
# ============================================================
def conviction_score(p_master):
    """Devuelve int 1-10 sin exponer formula"""
    if p_master is None:
        return 0
    return max(1, min(10, round(p_master / PHI_CB * 10)))

def conviction_label(p_master):
    if p_master is None:
        return "BAJA"
    if p_master >= PHI_CB:   return "EXTREMA"
    if p_master >= PHI_SQ:   return "ALTA"
    if p_master >= PHI:      return "MEDIA"
    return "BAJA"

def tier_label(p_master):
    """Tier publico sin nombrar phi"""
    if p_master >= PHI_CB:   return "Conviccion maxima"
    if p_master >= PHI_SQ:   return "Conviccion estandar"
    return "Conviccion exploratoria"

def leverage_for_tier(p_master):
    if p_master >= PHI_CB:   return "8x", "10%"
    if p_master >= PHI_SQ:   return "5x", "5%"
    return "3x", "2%"

# ============================================================
# SENAL VIP - simplificada, ejecutable sin exponer motor
# ============================================================
def build_vip_signal(field, decision_report):
    """
    Senal lista para copy-paste. NO expone P_master, kappa_evo, Theta(D),
    f_confluencia ni constantes phi/alpha. Solo lo que el VIP necesita ejecutar.

    Las 3 abstracciones (Estructura/Liquidez/Momentum) mapean internamente a
    pilares del motor, pero el usuario VIP no ve la fuente.
    """
    direction = decision_report["direction"]
    pm     = decision_report["p_master_data"]
    levels = decision_report["levels"]

    side  = "LONG" if direction == "long" else "SHORT"
    arrow = "▴" if direction == "long" else "▾"

    score = conviction_score(pm["p_master"])
    label = tier_label(pm["p_master"])
    lev, sizing = leverage_for_tier(pm["p_master"])

    # Las 3 abstracciones - cada una OK si su pilar interno paso
    estruct_ok  = field.bias_aligned and field.pd_zone in ("discount", "premium")
    liquidez_ok = field.has_fuel and (
        bool(field.recent_sweep) or
        (field.pool_low if direction == "long" else field.pool_high)
    )
    momentum_ok = field.confluence_count >= 3 and field.node_type == "colapso"

    pilares = "\n".join([
        "  ▪ Estructura  {}".format("OK" if estruct_ok else "—"),
        "  ▪ Liquidez    {}".format("OK" if liquidez_ok else "—"),
        "  ▪ Momentum    {}".format("OK" if momentum_ok else "—"),
    ])

    when = datetime.now(CDMX_TZ).strftime("%H:%M CDMX")
    rule = "━" * 30

    risk_pct = (levels["risk"] / levels["entry"]) * 100 if levels.get("risk") else 0

    return (
        "{rule}\n"
        "  ▰ SENAL FQ · SOL/USDT\n"
        "  {when}\n"
        "{rule}\n"
        "  {arrow} {side}          Conviccion  {score}/10\n"
        "  {label}\n"
        "\n"
        "  ▸ Entry    ${entry:.2f}\n"
        "  ▸ Stop     ${sl:.2f}      Riesgo  {risk:.2f}%\n"
        "\n"
        "  ▸ TP1      ${tp1:.2f}      R {rr1:.2f}\n"
        "  ▸ TP2      ${tp2:.2f}      R {rr2:.2f}\n"
        "  ▸ TP3      ${tp3:.2f}      R {rr3:.2f}\n"
        "  ▸ TP4      ${tp4:.2f}      R {rr4:.2f}\n"
        "{rule}\n"
        "{pilares}\n"
        "  ◆ Setup confirmado\n"
        "{rule}\n"
        "  Leverage {lev}   Size {sizing}\n"
        "  SL inmutable. Disciplina.\n"
        "\n"
        "  #FQ #SOLUSDT #{side}"
    ).format(
        rule=rule, when=when, arrow=arrow, side=side,
        score=score, label=label,
        entry=levels["entry"], sl=levels["sl"], risk=risk_pct,
        tp1=levels["tp1"], rr1=levels.get("rr_tp1", 0),
        tp2=levels["tp2"], rr2=levels.get("rr_tp2", 0),
        tp3=levels["tp3"], rr3=levels.get("rr_tp3", 0),
        tp4=levels["tp4"], rr4=levels.get("rr_tp4", 0),
        pilares=pilares, lev=lev, sizing=sizing,
    )

# ============================================================
# /help y /about TIER-AWARE
# ============================================================
def build_help_vip():
    """6 comandos visibles. Mistral minimalist."""
    rule = "━" * 30
    return (
        "{rule}\n"
        "  ◆ FQ · Comandos\n"
        "{rule}\n"
        "  ▸ /status      Estado y ultima senal\n"
        "  ▸ /lectura     Analisis Claude on-demand\n"
        "  ▸ /miestado    Tu cuenta VIP\n"
        "  ▸ /renovar     Renovar suscripcion\n"
        "  ▸ /about       Sobre el sistema\n"
        "  ▸ /help        Esta lista\n"
        "{rule}\n"
        "  El silencio es disciplina.\n"
        "  Calidad sobre cantidad."
    ).format(rule=rule)

def build_help_admin():
    """Admin ve todo - la salsa completa"""
    rule = "━" * 30
    return (
        "{rule}\n"
        "  ◆ FQ · Comandos (admin)\n"
        "{rule}\n"
        "  PUBLICOS (visibles VIP):\n"
        "  ▸ /status /lectura /miestado /renovar /about /help\n"
        "\n"
        "  CONSOLIDADOS (alias internos):\n"
        "  ▸ /analisis /niveles /pspace /claude /ia → /lectura\n"
        "  ▸ /sesion /macro → /status\n"
        "\n"
        "  ADMIN ONLY (ocultos a VIP):\n"
        "  ▸ /audit       Trigger Opus self-audit\n"
        "  ▸ /entropy     Shannon H + KL drift\n"
        "  ▸ /metrics     Win rate, expectancy, PF\n"
        "  ▸ /ledger      Ultimas 10 senales con outcome\n"
        "  ▸ /evolve      Buckets kappa_evo\n"
        "  ▸ /concepts    Edge por concepto ICT (v3)\n"
        "  ▸ /weekend     Filtro fin de semana\n"
        "  ▸ /campo       Lectura on-demand del FieldState\n"
        "  ▸ /gencode /grant /broadcast (VIP system)\n"
        "{rule}\n"
        "  FQ v4.2 — RasDG_Sol"
    ).format(rule=rule)

def build_help_free():
    """Free tier: solo lo necesario para comprar"""
    rule = "━" * 30
    return (
        "{rule}\n"
        "  ◆ FQ · Acceso\n"
        "{rule}\n"
        "  ▸ /precio      Tarifas del VIP\n"
        "  ▸ /vip         Activar acceso\n"
        "  ▸ /codigo XXXX Canjear codigo\n"
        "  ▸ /miestado    Tu estado actual\n"
        "  ▸ /about       Sobre el sistema\n"
        "{rule}\n"
        "  Senales SOL/USDT con motor\n"
        "  ICT/SMC + autoevolucion."
    ).format(rule=rule)

def build_about_vip():
    """About curado para VIP - cero formulas crudas, narrativa densa"""
    rule = "━" * 30
    return (
        "{rule}\n"
        "  ◆ FIBONACCI CUANTICO v4.2\n"
        "  Mistral Edition · RasDG_Sol\n"
        "{rule}\n"
        "\n"
        "  El mercado no esta en un estado\n"
        "  definido. Esta en superposicion\n"
        "  de historias competidoras. Una\n"
        "  senal solo existe cuando colapsan.\n"
        "\n"
        "  CUATRO PILARES:\n"
        "  ▪ Estructura multi-TF (4H + 1H + 15m)\n"
        "  ▪ Liquidez institucional (sweeps + pools)\n"
        "  ▪ Confluencia ICT (OB + FVG + Fib + PD)\n"
        "  ▪ Timing por killzone con DST automatico\n"
        "\n"
        "  14 CONCEPTOS ICT INTEGRADOS:\n"
        "  Order Blocks · Breaker · FVG · BPR · MSS\n"
        "  Inducement · Power of 3 · OTE · Killzones\n"
        "  Premium/Discount · Liquidity · Displacement\n"
        "  CHoCH · BOS\n"
        "\n"
        "  AUTOEVOLUCION:\n"
        "  Cada cierre alimenta una memoria por\n"
        "  bucket multidimensional. Thompson\n"
        "  sampling decide cuanta exposicion\n"
        "  merece cada combinacion de concepto.\n"
        "  Opus 4.6 audita cada 25 cierres.\n"
        "\n"
        "  DISCIPLINA:\n"
        "  ▪ SL inmutable (Regla 4)\n"
        "  ▪ Veto fin de semana automatico\n"
        "  ▪ Confirmacion de volumen institucional\n"
        "  ▪ Solo senales con probabilidad real,\n"
        "    no solo probabilidad matematica\n"
        "{rule}\n"
        "  Par:        SOL/USDT Perpetual\n"
        "  Exchange:   OKX (datos en vivo)\n"
        "  Timeframe:  15 min (con 4H/1H/1m)\n"
        "  Ventana:    24/7 menos fin de semana\n"
        "{rule}\n"
        "  #FQv42 #ICT #SMC"
    ).format(rule=rule)

def build_about_admin():
    """Admin ve la salsa completa: ecuacion, constantes, thresholds"""
    rule = "━" * 30
    return (
        "{rule}\n"
        "  ◆ FIBONACCI CUANTICO v4.2 (admin)\n"
        "{rule}\n"
        "\n"
        "  MASTER EQUATION v4.2:\n"
        "  P_master = Theta(D) * kappa_evo * phi *\n"
        "             W_eff * H_lap * f_conf * f_ict\n"
        "\n"
        "  W_eff = w_clock_legacy * alpha +\n"
        "          w_killzone * (1 - alpha)\n"
        "  alpha = max(0, 1 - n_closed_v3 / 50)\n"
        "  f_ict = 1.0 + n_concepts * 0.04   (cap 4)\n"
        "\n"
        "  CONSTANTES:\n"
        "  phi    = 1.6180339887\n"
        "  phi^2  = 2.6180        (tier standard)\n"
        "  phi^3  = 4.2360        (tier high)\n"
        "  alpha  = 1/137.507\n"
        "  B      = phi^2/alpha + e + pi = 364.62\n"
        "\n"
        "  THRESHOLDS (env-overridable):\n"
        "  PMASTER_MIN     = 1.80\n"
        "  RR_MIN_TP3      = 1.80\n"
        "  CONFLUENCE_MIN  = 3\n"
        "  KAPPA_EVO cap   = +-15%\n"
        "  Volume mult     = 1.20x avg(20)\n"
        "  Cooldown        = 1h\n"
        "\n"
        "  FLAGS:\n"
        "  FQ_ENABLE_ICT, FQ_WEEKEND_VETO,\n"
        "  FQ_USE_THOMPSON, FQ_REQUIRE_OTE,\n"
        "  FQ_REQUIRE_VOLUME (nuevo)\n"
        "{rule}\n"
        "  #FQv42 #Admin"
    ).format(rule=rule)

# ============================================================
# WELCOME (suscriptor nuevo) - una sola version, narrativa limpia
# ============================================================
def build_welcome():
    rule = "━" * 30
    return (
        "{rule}\n"
        "  ◆ FQ v4.2 · Mistral\n"
        "{rule}\n"
        "\n"
        "  Senales SOL/USDT con motor\n"
        "  ICT/SMC + autoevolucion.\n"
        "\n"
        "  El sistema solo emite cuando\n"
        "  4 fases (estructura, liquidez,\n"
        "  confluencia, timing) y la\n"
        "  validacion de volumen estan\n"
        "  alineadas. El resto del tiempo,\n"
        "  silencio.\n"
        "\n"
        "  ▸ /precio      Tarifas\n"
        "  ▸ /codigo XXXX Si tienes codigo\n"
        "  ▸ /miestado    Tu estado actual\n"
        "  ▸ /about       Sobre el sistema\n"
        "{rule}\n"
        "  RasDG_Sol"
    ).format(rule=rule)

def build_welcome_for_tier(tier):
    """Misma carcasa pero adapta CTA segun tier"""
    if tier in ("vip", "admin", "trial"):
        rule = "━" * 30
        return (
            "{rule}\n"
            "  ◆ FQ v4.2 · Acceso activo\n"
            "{rule}\n"
            "  Bienvenido. Tu canal de\n"
            "  senales esta activo.\n"
            "\n"
            "  ▸ /status      Estado actual\n"
            "  ▸ /lectura     Analisis Claude\n"
            "  ▸ /miestado    Tu cuenta\n"
            "  ▸ /help        Comandos\n"
            "{rule}"
        ).format(rule=rule)
    return build_welcome()

# ============================================================
# Helper: filtrar contenido segun tier (mantener backward compat)
# ============================================================
def help_for_tier(tier):
    if tier == "admin":
        return build_help_admin()
    if tier in ("vip", "trial"):
        return build_help_vip()
    return build_help_free()

def about_for_tier(tier):
    if tier == "admin":
        return build_about_admin()
    return build_about_vip()
