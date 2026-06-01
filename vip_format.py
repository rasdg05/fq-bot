# -*- coding: utf-8 -*-
"""
================================================================================
  VIP FORMAT - Mistral Emergent Time Edition (curated, minimalist, formula-hidden, v5.1)
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
# /analisis VIP - F1 v5.0 (curated, 3 TPs, sin formulas)
# ============================================================
SL_ANCHOR_LABEL_VIP = {
    "OB_bullish":      "Order Block alcista",
    "OB_bearish":      "Order Block bajista",
    "pool_low":        "liquidez sin barrer",
    "pool_high":       "liquidez sin barrer",
    "post_sweep_low":  "reaccion post-sweep",
    "post_sweep_high": "reaccion post-sweep",
    "swing_low":       "swing low estructural",
    "swing_high":      "swing high estructural",
    "FVG_bottom":      "FVG (borde inferior)",
    "FVG_top":         "FVG (borde superior)",
    "EMA50":           "EMA50",
    "low_20":          "low de 20 velas",
    "high_20":         "high de 20 velas",
    "ATR_clamp":       "clamp ATR",
}

TP_KIND_LABEL_VIP = {
    "pspace_R":     "resistencia",
    "pspace_S":     "soporte",
    "BSL_target":   "liquidez",
    "SSL_target":   "liquidez",
    "OB_bear":      "Order Block opuesto",
    "OB_bull":      "Order Block opuesto",
    "FVG_bear":     "FVG opuesto",
    "FVG_bull":     "FVG opuesto",
    "fib_1272":     "extension 1.27",
    "fib_1618":     "extension 1.62",
    "fib_fallback": "extension Fib",
}

def build_vip_analisis(direction, levels, bias, pm_est, last, qa=None):
    """
    Formato VIP del /analisis. Una pantalla, 3 TPs, glyphs Mistral.
    NO expone P_master crudo - solo conviction score derivado.

    qa (opcional): dict resultante de quantum_timelines.quantum_analysis.
    Si esta presente, anade bloque de probabilidades reales.
    """
    side  = "LONG" if direction == "long" else "SHORT"
    arrow = "▴" if direction == "long" else "▾"

    score = conviction_score(pm_est)
    label = tier_label(pm_est)

    when = datetime.now(CDMX_TZ).strftime("%H:%M CDMX")
    rule = "━" * 30

    entry    = levels["entry"]
    sl       = levels["sl"]
    risk_pct = (levels["risk"] / entry) * 100 if entry > 0 else 0
    sla_lbl  = SL_ANCHOR_LABEL_VIP.get(
        levels.get("sl_anchor", ""), levels.get("sl_anchor", "estructura"))

    tp_meta = levels.get("tp_meta") or []
    tp_lines = []
    for i in range(min(3, len(tp_meta))):
        kind_lbl = TP_KIND_LABEL_VIP.get(tp_meta[i]["kind"], tp_meta[i]["kind"])
        tp_lines.append("  ▸ TP{n}     ${p:.2f}   R {rr:.2f}   {k}".format(
            n=i+1, p=tp_meta[i]["price"], rr=tp_meta[i]["rr"], k=kind_lbl))
    # Si no hay tp_meta (legacy levels), usa keys directas
    if not tp_lines:
        for i in range(1, 4):
            p = levels.get("tp{}".format(i))
            rr = levels.get("rr_tp{}".format(i), 0)
            if p is not None:
                tp_lines.append("  ▸ TP{n}     ${p:.2f}   R {rr:.2f}".format(
                    n=i, p=p, rr=rr))
    tps_block = "\n".join(tp_lines)

    # Bloque QTE opcional (F2 v5.0)
    qte_block = ""
    if qa is not None:
        probs = qa["probabilities"]
        regs = qa["regimes"]
        qte_block = (
            "\n  ◆ Timelines simuladas: {n}\n"
            "  ▴ Bull {bp}%   ▾ Bear {brp}%   ◇ Sweep {sp}%\n"
            "  ◆ P(TP1) {p1:.0%}   P(TP2) {p2:.0%}   P(SL) {ps:.0%}\n"
            "  ◆ EV {ev:+.2f}R   Coherencia {coh:.0%}\n"
            "{rule}\n"
        ).format(
            n=qa["n_paths"],
            bp=int(regs.get("bull_continuation", 0) * 100),
            brp=int(regs.get("bear_reversal", 0) * 100),
            sp=int(regs.get("sweep_and_reverse", 0) * 100),
            p1=probs.get("p_reach_tp1", probs["p_tp1"]),
            p2=probs.get("p_reach_tp2", probs["p_tp2"]),  # P(toca TP2<SL); p_tp2 era 0
            ps=probs["p_sl"],
            ev=probs["expected_R"], coh=qa["coherence"],
            rule=rule,
        )

    return (
        "{rule}\n"
        "  ▰ ANALISIS FQ · SOL/USDT\n"
        "  {when}    ${px:.2f}\n"
        "{rule}\n"
        "  {arrow} Sesgo {side}      Conviccion {score}/10\n"
        "  {label}\n"
        "\n"
        "  ▸ Entry   ${entry:.2f}\n"
        "  ▸ Stop    ${sl:.2f}   ({risk:.2f}%)\n"
        "    anclado a {sla}\n"
        "\n"
        "{tps}\n"
        "{rule}"
        "{qte}"
        "  ◆ SL estructural (anti stop-hunt)\n"
        "  ◆ TPs en liquidez real\n"
        "{rule}\n"
        "  #FQv51 #MistralEmergentTime #QTE #TauPostulate"
    ).format(
        rule=rule, when=when, px=float(last["close"]),
        arrow=arrow, side=side, score=score, label=label,
        entry=entry, sl=sl, risk=risk_pct, sla=sla_lbl,
        tps=tps_block, qte=qte_block if qte_block else "\n",
    )

# ============================================================
# /help y /about TIER-AWARE
# ============================================================
def build_help_vip():
    """6 comandos visibles. Mistral Emergent Time minimalist."""
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
        "  FQ v5.1 Mistral Emergent Time — RasDG_Sol"
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
    """About curado para VIP - narrativa Mistral Emergent Time, cero formulas crudas"""
    rule = "━" * 30
    return (
        "{rule}\n"
        "  ◆ FIBONACCI CUANTICO v5.0\n"
        "  Mistral Emergent Time · RasDG_Sol\n"
        "{rule}\n"
        "\n"
        "  El mercado no es una linea.\n"
        "  Es un abanico de futuros posibles.\n"
        "  Cada vela es una nueva medicion\n"
        "  que colapsa probabilidades en\n"
        "  realidad.\n"
        "\n"
        "  ◆ QUANTUM TIMELINES ENGINE\n"
        "  Antes de cada senal, el motor\n"
        "  simula 500 lineas de tiempo bajo\n"
        "  restricciones estructurales reales\n"
        "  (Order Blocks, liquidez, FVGs).\n"
        "  Mide en cuantas el TP llega antes\n"
        "  que el SL, identifica el escenario\n"
        "  dominante y solo dispara si el\n"
        "  Valor Esperado supera 1R.\n"
        "\n"
        "  ◆ ANTI STOP-HUNT\n"
        "  El SL ya no usa buffer fijo.\n"
        "  Se ancla al nivel estructural mas\n"
        "  cercano (Order Block, swing low,\n"
        "  reaccion post-sweep). El precio\n"
        "  puede mecerlo. No cazarlo.\n"
        "\n"
        "  ◆ FUNDAMENTOS\n"
        "  ▪ 14 conceptos ICT integrados\n"
        "  ▪ Memoria autoevolutiva por bucket\n"
        "  ▪ Thompson sampling sobre concepts\n"
        "  ▪ Audit Opus cada 25 cierres\n"
        "  ▪ Veto fin de semana automatico\n"
        "\n"
        "  ◆ DISCIPLINA\n"
        "  ▪ SL inmutable (Regla 4)\n"
        "  ▪ Probabilidades reales, no scores\n"
        "  ▪ Setups con EV<1R: descartados\n"
        "  ▪ Confirmacion de volumen institucional\n"
        "{rule}\n"
        "  Par:        SOL/USDT Perpetual\n"
        "  Exchange:   OKX (datos en vivo)\n"
        "  Timeframe:  15 min (con 4H/1H/1m)\n"
        "  Ventana:    24/7 menos fin de semana\n"
        "{rule}\n"
        "  #FQv51 #MistralEmergentTime #QTE #TauPostulate"
    ).format(rule=rule)

def build_about_admin():
    """Admin ve la salsa completa: ecuacion, constantes, thresholds + QTE"""
    rule = "━" * 30
    return (
        "{rule}\n"
        "  ◆ FIBONACCI CUANTICO v5.1 (admin)\n"
        "  Mistral Emergent Time Edition\n"
        "{rule}\n"
        "\n"
        "  MASTER EQUATION v4.2 (sustrato):\n"
        "  P_master = Theta(D) * kappa_evo * phi *\n"
        "             W_eff * H_lap * f_conf * f_ict\n"
        "\n"
        "  W_eff = w_clock_legacy * alpha +\n"
        "          w_killzone * (1 - alpha)\n"
        "  alpha = max(0, 1 - n_closed_v3 / 50)\n"
        "  f_ict = 1.0 + n_concepts * 0.04   (cap 4)\n"
        "\n"
        "  GATE QTE v5.0 (capa final):\n"
        "  EMIT  iff  P(SL) <= 0.35  AND  EV >= 1.0R\n"
        "\n"
        "  QUANTUM TIMELINES ENGINE:\n"
        "  paths simulados   = 500 (admin 2000)\n"
        "  horizon           = 96 velas (24h en 15m)\n"
        "  optimizer         QAOA-inspired grid\n"
        "  regimenes         bull/bear/chop/sweep/range\n"
        "  modulo            quantum_timelines.py\n"
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
        "  QTE_MAX_P_SL    = 0.35\n"
        "  QTE_MIN_EV_R    = 1.00\n"
        "  Cooldown        = 1h\n"
        "\n"
        "  FLAGS:\n"
        "  FQ_ENABLE_ICT, FQ_WEEKEND_VETO,\n"
        "  FQ_USE_THOMPSON, FQ_REQUIRE_OTE\n"
        "{rule}\n"
        "  #FQv51 #MistralEmergentTime #Admin"
    ).format(rule=rule)

# ============================================================
# WELCOME (suscriptor nuevo) - una sola version, narrativa limpia
# ============================================================
def build_welcome():
    rule = "━" * 30
    return (
        "{rule}\n"
        "  ◆ FQ v5.1 · Mistral Emergent Time\n"
        "{rule}\n"
        "\n"
        "  Senales SOL/USDT con motor\n"
        "  Quantum Timelines + ICT/SMC.\n"
        "\n"
        "  El sistema simula 500 lineas\n"
        "  de tiempo futuras antes de\n"
        "  cada senal. Dispara solo cuando\n"
        "  el Valor Esperado supera 1R y\n"
        "  P(SL) baja del 35%. El resto\n"
        "  del tiempo, silencio.\n"
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
            "  ◆ FQ v5.1 · Acceso activo\n"
            "  Mistral Emergent Time\n"
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
