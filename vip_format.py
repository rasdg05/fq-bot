# -*- coding: utf-8 -*-
"""
VIP format. Construye strings de cara al cliente.

Regla: las vistas VIP no exponen formulas, versiones ni jerga interna.
La vista admin permanece en bloque separado para evitar fugas accidentales.
Modulo inerte: no envia, no consulta DB.
"""
from datetime import datetime, timezone, timedelta

from branding import PRODUCT, PAIR, HASHTAGS_SIGNAL, RULE, GLYPHS, DISCLAIMER
import qte_verdict  # veredicto canonico compartido con el bloque QTE admin

CDMX_TZ = timezone(timedelta(hours=-6))

PHI    = 1.6180339887
PHI_SQ = PHI * PHI
PHI_CB = PHI ** 3

# ============================================================
# Etiquetas cualitativas (la superficie nunca muestra el numero crudo).
# ============================================================
def conviction_label(p_master):
    if p_master is None:        return "Exploratoria"
    if p_master >= PHI_CB:      return "Extrema"
    if p_master >= PHI_SQ:      return "Alta"
    if p_master >= PHI:         return "Media"
    return "Exploratoria"

def tier_label(p_master):
    if p_master >= PHI_CB:      return "Conviccion maxima"
    if p_master >= PHI_SQ:      return "Conviccion estandar"
    return "Conviccion exploratoria"

def risk_band(risk_pct):
    """Banda cualitativa de riesgo a partir del % de la cuenta arriesgado."""
    if risk_pct is None:        return "—"
    if risk_pct < 1.0:          return "Bajo"
    if risk_pct < 2.0:          return "Medio"
    return "Alto"

def leverage_for_tier(p_master):
    if p_master >= PHI_CB:      return "8x", "10%"
    if p_master >= PHI_SQ:      return "5x", "5%"
    return "3x", "2%"

# ============================================================
# SENAL VIP - simplificada, ejecutable sin exponer motor
# ============================================================
def build_vip_signal(field, decision_report, tf_label=None, tf_id=None):
    """
    Senal lista para copy-paste. NO expone P_master, kappa_evo, Theta(D),
    f_confluencia ni constantes phi/alpha. Solo lo que el VIP necesita ejecutar.

    Las 3 abstracciones (Estructura/Liquidez/Momentum) mapean internamente a
    pilares del motor, pero el usuario VIP no ve la fuente.

    Este ES el formato unico de la SENAL real gateada: admin y VIP reciben lo
    mismo (limpio). El encabezado iconico (🎯 Senal FQ VIP ◆) + la insignia de
    CALIDAD la distinguen de un vistazo de las alertas tacticas y las lecturas
    de campo. tf_label/tf_id son opcionales (contexto en el header).
    """
    direction = decision_report["direction"]
    pm     = decision_report["p_master_data"]
    levels = decision_report["levels"]

    side  = "LONG" if direction == "long" else "SHORT"
    arrow = GLYPHS["long"] if direction == "long" else GLYPHS["short"]

    conviction = conviction_label(pm["p_master"])
    lev, sizing = leverage_for_tier(pm["p_master"])

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
    # Contexto del header: TF (si se pasa) + hora.
    tf_str = " ".join(x for x in (tf_label, tf_id) if x).strip()
    ctx_line = (tf_str + " · " + when) if tf_str else when
    # Insignia de CALIDAD: distingue las TOP entre las reales de un vistazo
    # (jerarquia PD + tipo de nodo + numero de confluencias). getattr defensivo
    # para no romper si llega un field minimo.
    hier = (getattr(field, "pd_hierarchy", "") or "").upper() or "BASE"
    node = (getattr(field, "node_type", "") or "").upper() or "—"
    cc   = getattr(field, "confluence_count", 0)
    quality = "CALIDAD {} · {} · {} confluencias".format(hier, node, cc)

    risk_pct = (levels["risk"] / levels["entry"]) * 100 if levels.get("risk") else 0
    risk_lbl = risk_band(risk_pct)

    return (
        "{rule}\n"
        "  🎯 Senal {product} VIP ◆ {pair}\n"
        "  {quality}\n"
        "  {ctx}\n"
        "{rule}\n"
        "  {arrow} {side}        Conviccion {conv}\n"
        "\n"
        "  ▸ Entry    ${entry:.2f}\n"
        "  ▸ Stop     ${sl:.2f}    Riesgo {risk}\n"
        "\n"
        "  ▸ TP1      ${tp1:.2f}    R {rr1:.2f}\n"
        "  ▸ TP2      ${tp2:.2f}    R {rr2:.2f}\n"
        "  ▸ TP3      ${tp3:.2f}    R {rr3:.2f}\n"
        "  ▸ TP4      ${tp4:.2f}    R {rr4:.2f}\n"
        "{rule}\n"
        "{pilares}\n"
        "{rule}\n"
        "  Leverage {lev}   Size {sizing}\n"
        "  SL inmutable.\n"
        "\n"
        "  {tags} #{side}"
    ).format(
        rule=RULE, product=PRODUCT, pair=PAIR, quality=quality, ctx=ctx_line,
        arrow=arrow, side=side, conv=conviction, risk=risk_lbl,
        entry=levels["entry"], sl=levels["sl"],
        tp1=levels["tp1"], rr1=levels.get("rr_tp1", 0),
        tp2=levels["tp2"], rr2=levels.get("rr_tp2", 0),
        tp3=levels["tp3"], rr3=levels.get("rr_tp3", 0),
        tp4=levels["tp4"], rr4=levels.get("rr_tp4", 0),
        pilares=pilares, lev=lev, sizing=sizing,
        tags=HASHTAGS_SIGNAL,
    )

# ============================================================
# /analisis VIP - 3 TPs, sin formulas
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

def _prob_label(p):
    """Probabilidad cruda -> etiqueta cualitativa."""
    if p is None:               return "—"
    if p >= 0.65:               return "Alta"
    if p >= 0.45:               return "Media"
    return "Baja"

def _ev_label(ev):
    """EV en R -> etiqueta cualitativa."""
    if ev is None:              return "—"
    if ev >= 1.5:               return "Edge fuerte"
    if ev >= 1.0:               return "Edge"
    if ev >= 0.0:               return "Marginal"
    return "Negativo"

def build_battle_block(plan):
    """
    Veredicto del battle_planner como bloque lider del /analisis.
    Sin EV crudo ni P(SL) crudo en la superficie VIP.
    """
    if not plan:
        return ""
    v = plan["verdict"]
    mkt = plan["market"]
    tps = plan.get("tps") or []
    tps_str = " / ".join("${:.2f}".format(t) for t in tps[:3]) if tps else "-"

    p_market = _prob_label(1.0 - (mkt.get("p_sl") or 0.5))
    ev_market = _ev_label(mkt.get("ev"))

    lines = [
        RULE,
        "  ▰ Plan · {}".format(PAIR),
        RULE,
        "  {} <b>{}</b>".format(plan["emoji"], plan["headline"]),
        "",
    ]

    if v == "EJECUTAR_AHORA":
        lines += [
            "  ▸ Entry      ${:.2f}".format(mkt["entry"]),
            "  ▸ Invalida   ${:.2f}".format(plan["invalidation"]),
            "  ▸ Objetivos  {}".format(tps_str),
            "",
            "  ◆ {} · probabilidad {}".format(ev_market, p_market.lower()),
        ]
    elif v == "ACUMULAR_EN_ZONA":
        z = plan["primary_zone"]
        acc = "\n".join(
            "     {:>3}%  ${:.2f}".format(a["weight_pct"], a["price"])
            for a in z["accumulate"]
        )
        p_zone = _prob_label(1.0 - (z.get("p_sl_cond") or 0.5))
        ev_zone = _ev_label(z.get("ev_cond"))
        p_reach = _prob_label(z.get("reach_prob"))
        lines += ["  ▸ Acumula", acc]
        if plan.get("trigger"):
            lines.append("  ▸ Gatillo    {}".format(plan["trigger"]))
        lines += [
            "  ▸ Invalida   ${:.2f}".format(plan["invalidation"]),
            "  ▸ Objetivos  {}".format(tps_str),
            "",
            "  ◆ Regreso a zona: {}".format(p_reach.lower()),
            "  ◆ Desde zona:    {} · prob. {}".format(ev_zone, p_zone.lower()),
            "  ◆ A mercado:     {} · prob. {}".format(ev_market, p_market.lower()),
            "  → Mejor entrar acumulando en zona.",
        ]
    elif v == "ESPERAR_GATILLO":
        lines += [
            "  ▸ Gatillo    {}".format(plan.get("trigger") or "confirmacion a favor"),
            "  ▸ Invalida   ${:.2f}".format(plan["invalidation"]),
            "  ▸ Objetivos  {}".format(tps_str),
            "",
            "  ◆ {}".format(plan["rationale"]),
        ]
    else:  # STAND_DOWN
        lines += [
            "  ◆ {}".format(plan["rationale"]),
        ]

    return "\n".join(lines) + "\n"


# ============================================================
# ALERTA TACTICA FQ - promueve battle_planner a VIP con TPs cortos
# FQ v5.2 - resuelve falsos positivos en franjas dudosas usando TPs reales
# que la practica demostro alcanzables (RR 1.0 / 1.5 / 2.2 en vez de
# estructurales lejanos donde TP3 ~1:6 casi nunca se llega en intradia).
# ============================================================
def build_tactical_alert(plan, tps_short, vol_label=None, killzone_name=None,
                         tf_label=None):
    """
    Render de la ALERTA TACTICA FQ para el VIP.

    Args:
        plan: dict del battle_planner.build_battle_plan
              (verdict, headline, market, primary_zone, invalidation, direction)
        tps_short: lista de 3 dicts [{"price","rr","weight_pct","kind"}, ...]
                   con TPs (mezcla de estructurales + sinteticos segun contexto).
        vol_label: etiqueta de volumen ("Alto"/"Normal"/"Bajo"/...) opcional.
        killzone_name: nombre de la killzone activa para contexto.
        tf_label: timeframe del setup ("1m"/"3m"/"15m") para etiquetar en header.

    El mensaje NO sustituye la senal automatica - la frase final lo hace
    explicito para no diluir la marca de la senal clasica.
    """
    if not plan or not tps_short:
        return ""

    v = plan["verdict"]
    side = "LONG" if plan["direction"] == "long" else "SHORT"
    mkt = plan.get("market") or {}
    invalidation = plan.get("invalidation")

    # Etiquetas cualitativas (sin numeros crudos)
    p_market = _prob_label(1.0 - (mkt.get("p_sl") or 0.5))
    if v == "ACUMULAR_EN_ZONA" and plan.get("primary_zone"):
        z = plan["primary_zone"]
        p_label = _prob_label(1.0 - (z.get("p_sl_cond") or 0.5))
        ev_label_str = _ev_label(z.get("ev_cond"))
    else:
        p_label = p_market
        ev_label_str = _ev_label(mkt.get("ev"))

    # Headline segun veredicto
    if v == "EJECUTAR_AHORA":
        entry_str = "${:.2f}".format(mkt.get("entry") or 0)
        emoji_head = "🟢"
        headline = "EJECUTA {} a mercado ~{}".format(side, entry_str)
    elif v == "ACUMULAR_EN_ZONA":
        z = plan["primary_zone"]
        emoji_head = "🟡"
        headline = "ACUMULA {} en {} ${:.2f}-${:.2f}".format(
            side, z["label"], z["low"], z["high"])
        entry_str = "${:.2f}".format(z["ref"])
    else:
        # No deberia llegar otro verdict, pero defensive
        emoji_head = "⚡"
        headline = plan.get("headline", "ALERTA TACTICA")
        entry_str = "${:.2f}".format(mkt.get("entry") or 0)

    # Contexto: killzone + volumen + TF + hora. Omite limpio lo ausente.
    ctx_bits = []
    if killzone_name and killzone_name != "fuera":
        ctx_bits.append("Killzone {}".format(killzone_name))
    if vol_label:
        ctx_bits.append("Volumen {}".format(vol_label.lower()))
    ctx_bits.append(tf_label or "intradia")
    ctx_bits.append(datetime.now(CDMX_TZ).strftime("%H:%M CDMX"))
    ctx_line = " · ".join(ctx_bits)

    arrow = GLYPHS["long"] if plan["direction"] == "long" else GLYPHS["short"]

    # Mismo acabado premium que la senal FQ VIP, con CLASE propia (⚡ TACTICA):
    # encabezado iconico, regla, flecha de lado. Sin tags ni jerga.
    lines = [
        RULE,
        "  ⚡ ALERTA TACTICA FQ ◆ {}".format(PAIR),
        "  {} {}".format(emoji_head, headline),
        "  {}".format(ctx_line),
        RULE,
        "  {} {}".format(arrow, side),
        "",
    ]

    # Entrada / acumulacion
    if v == "EJECUTAR_AHORA":
        lines.append("  ▸ Entry      {}".format(entry_str))
    elif v == "ACUMULAR_EN_ZONA":
        acc = plan["primary_zone"].get("accumulate") or []
        lines.append("  ▸ Acumula")
        for a in acc:
            lines.append("     {:>3}%  ${:.2f}".format(a.get("weight_pct", 0),
                                                          a.get("price", 0)))
        if plan.get("trigger"):
            lines.append("  ▸ Gatillo    {}".format(plan["trigger"]))

    if invalidation is not None:
        lines.append("  ▸ Invalida   ${:.2f}".format(invalidation))

    # TPs cortos con % de cierre (40/35/25) y RR
    for i, tp in enumerate(tps_short, start=1):
        wp = tp.get("weight_pct", 0)
        lines.append("  ▸ TP{} ({:>2}%) ${:.2f}    R:R {:.2f}".format(
            i, wp, tp.get("price", 0), tp.get("rr", 0)))

    # Resumen cualitativo
    summary_bits = [ev_label_str, "prob. {}".format(p_label.lower())]
    if vol_label:
        summary_bits.append("volumen {}".format(vol_label.lower()))
    lines.append(RULE)
    lines.append("  ◆ " + " · ".join(summary_bits))
    lines.append("  Tactica rapida · no sustituye la senal FQ VIP.")
    lines.append(RULE)
    lines.append("  #FQ #SOLUSDT #Tactica #{}".format(side))

    return "\n".join(lines)


def _market_tone(qa, direction):
    """
    Compacta el resultado del QTE en UNA linea cualitativa que el VIP puede
    leer sin tocar formulas. Cero numeros crudos en la superficie.

    Delega en qte_verdict.compute() - la MISMA fuente que usa el bloque admin -
    para que VIP y admin nunca cuenten historias distintas del mismo setup.
    Prefiere el veredicto ya horneado en qa["verdict"]; recomputa si falta.
    """
    if qa is None:
        return None
    verdict = qa.get("verdict") or qte_verdict.compute(qa, direction)
    return verdict["tone"] if verdict else None


def _quality_note(qa):
    """Nota de certeza: evita presentar niveles con falsa confianza cuando el
    QTE no esta disponible o las timelines estan muy dispersas."""
    if qa is None:
        return "Lectura probabilistica no disponible · opera con cautela"
    coh = qa.get("coherence", 0) or 0
    if coh < 0.35:
        return "Baja certeza · escenario muy disperso"
    return None


def _decision_hint(qa, direction):
    """Una linea de 'que hacer ahora' derivada del veredicto, para cuando NO
    hay plan de batalla que lidere (el battle block ya trae su propia accion)."""
    if not qa:
        return None
    v = qa.get("verdict") or qte_verdict.compute(qa, direction)
    if not v:
        return None
    side = "LONG" if direction == "long" else "SHORT"
    return {
        "favorable": "Buscar entrada {} a favor".format(side),
        "moderado":  "Entrada {} selectiva · tamano reducido".format(side),
        "adverso":   "Sin edge ahora · mejor esperar",
        "neutro":    "Esperar confirmacion antes de entrar",
    }.get(v["grade"])


def build_vip_analisis(direction, levels, bias, pm_est, last, qa=None, plan=None):
    """
    /analisis VIP. Una pantalla, sin formulas, sin score numerico.
    El veredicto del battle planner lidera si esta presente.
    """
    side  = "LONG" if direction == "long" else "SHORT"
    arrow = GLYPHS["long"] if direction == "long" else GLYPHS["short"]

    conviction = conviction_label(pm_est)

    when = datetime.now(CDMX_TZ).strftime("%H:%M CDMX")

    entry    = levels["entry"]
    sl       = levels["sl"]
    risk_pct = (levels["risk"] / entry) * 100 if entry > 0 else 0
    risk_lbl = risk_band(risk_pct)
    sla_lbl  = SL_ANCHOR_LABEL_VIP.get(
        levels.get("sl_anchor", ""), levels.get("sl_anchor", "estructura"))

    tp_meta = levels.get("tp_meta") or []
    tp_lines = []
    for i in range(min(3, len(tp_meta))):
        kind_lbl = TP_KIND_LABEL_VIP.get(tp_meta[i]["kind"], tp_meta[i]["kind"])
        tp_lines.append("  ▸ TP{n}     ${p:.2f}   R {rr:.2f}   {k}".format(
            n=i+1, p=tp_meta[i]["price"], rr=tp_meta[i]["rr"], k=kind_lbl))
    if not tp_lines:
        for i in range(1, 4):
            p = levels.get("tp{}".format(i))
            rr = levels.get("rr_tp{}".format(i), 0)
            if p is not None:
                tp_lines.append("  ▸ TP{n}     ${p:.2f}   R {rr:.2f}".format(
                    n=i, p=p, rr=rr))
    tps_block = "\n".join(tp_lines)

    # Bloque cualitativo: tono + horizonte + nota de certeza (sin numeros crudos)
    tone = _market_tone(qa, direction)
    horizon_h = qa.get("horizon_hours") if qa else None
    quality = _quality_note(qa)
    tbits = []
    if tone:
        tbits.append("  ◆ {}".format(tone))
    if horizon_h:
        tbits.append("  ◆ Horizonte ~{:.0f}h".format(horizon_h))
    if quality:
        tbits.append("  ◆ {}".format(quality))
    tone_block = ("\n".join(tbits) + "\n{}\n".format(RULE)) if tbits else ""

    battle = build_battle_block(plan)
    detalle_hdr = "  ▰ Detalle" if battle else "  ▰ Analisis · {}".format(PAIR)
    # Si no hay plan que lidere, una linea de accion clara desde el veredicto.
    hint = None if battle else _decision_hint(qa, direction)
    decision_line = "  → {}\n".format(hint) if hint else ""

    return battle + (
        "{rule}\n"
        "{dhdr}\n"
        "  {when}    ${px:.2f}\n"
        "{rule}\n"
        "  {arrow} Sesgo {side}     Conviccion {conv}\n"
        "{decision}"
        "\n"
        "  ▸ Entry   ${entry:.2f}\n"
        "  ▸ Stop    ${sl:.2f}   Riesgo {risk} ({riskpct:.1f}% al stop)\n"
        "    anclado a {sla}\n"
        "\n"
        "{tps}\n"
        "{rule}\n"
        "{tone}"
        "  ◆ SL estructural\n"
        "  ◆ TPs en liquidez real\n"
        "{rule}\n"
        "  {tags}"
    ).format(
        rule=RULE, dhdr=detalle_hdr, when=when, px=float(last["close"]),
        decision=decision_line, riskpct=risk_pct,
        arrow=arrow, side=side, conv=conviction, risk=risk_lbl,
        entry=entry, sl=sl, sla=sla_lbl,
        tps=tps_block, tone=tone_block, tags=HASHTAGS_SIGNAL,
    )

# ============================================================
# /resultados - track record verificable (VIP/admin)
# ============================================================
def _fmt_results_window(label, w):
    if not w:
        return "  {}\n  ▪ sin cierres aun".format(label)
    pf = w["profit_factor"]
    pf_str = "inf" if pf == float("inf") else "{:.2f}".format(pf)
    return (
        "  {label}\n"
        "  ▪ Senales      {n}\n"
        "  ▪ Win rate     {wr:.0%}\n"
        "  ▪ Expectancy   {ex:+.2f}R\n"
        "  ▪ Profit fctr  {pf}"
    ).format(label=label, n=w["n"], wr=w["win_rate"], ex=w["expectancy"], pf=pf_str)

def build_resultados(summary):
    """Track record VIP. summary = dict de get_results_summary, o None."""
    if not summary or not summary.get("total"):
        return (
            "{rule}\n  ◆ {product} · Resultados\n{rule}\n"
            "  Aun no hay cierres registrados.\n{rule}"
        ).format(rule=RULE, product=PRODUCT)
    lines = [
        RULE,
        "  ◆ {} · Resultados".format(PRODUCT),
        RULE,
        _fmt_results_window("Ultimos 30 dias", summary.get("w30")),
        "",
        _fmt_results_window("Ultimos 90 dias", summary.get("w90")),
        "",
        _fmt_results_window("Historico total", summary.get("total")),
    ]
    streak = summary.get("longest_streak") or 0
    if streak >= 2:
        lines += ["", "  ▪ Mejor racha   {} cierres".format(streak)]
    lines += [RULE, "  {}".format(DISCLAIMER)]
    return "\n".join(lines)

# ============================================================
# /help y /about
# ============================================================
def build_help_vip():
    return (
        "{rule}\n"
        "  ◆ {product} · Comandos\n"
        "{rule}\n"
        "  ▸ /status      Estado del sistema\n"
        "  ▸ /lectura     Analisis on-demand\n"
        "  ▸ /miestado    Tu cuenta\n"
        "  ▸ /renovar     Renovar acceso\n"
        "  ▸ /about       Sobre el sistema\n"
        "  ▸ /legal       Aviso de riesgo\n"
        "{rule}\n"
        "  Calidad sobre cantidad."
    ).format(rule=RULE, product=PRODUCT)

def build_help_admin():
    return (
        "{rule}\n"
        "  ◆ {product} · Comandos (admin)\n"
        "{rule}\n"
        "  Cliente:\n"
        "  ▸ /status /lectura /miestado /renovar /about /legal\n"
        "\n"
        "  Alias:\n"
        "  ▸ /analisis /niveles /pspace /claude /ia → /lectura\n"
        "  ▸ /sesion /macro → /status\n"
        "\n"
        "  Admin:\n"
        "  ▸ /audit       Self-audit\n"
        "  ▸ /entropy     Drift\n"
        "  ▸ /metrics     Win rate · expectancy · PF\n"
        "  ▸ /ledger      Ultimas 10 senales\n"
        "  ▸ /evolve      Buckets\n"
        "  ▸ /concepts    Edge por concepto\n"
        "  ▸ /weekend     Filtro fin de semana\n"
        "  ▸ /campo       FieldState on-demand\n"
        "  ▸ /gencode /grant /broadcast\n"
        "{rule}"
    ).format(rule=RULE, product=PRODUCT)

def build_help_free():
    return (
        "{rule}\n"
        "  ◆ {product} · Acceso\n"
        "{rule}\n"
        "  ▸ /precio      Tarifas\n"
        "  ▸ /vip         Activar acceso\n"
        "  ▸ /codigo XXXX Canjear codigo\n"
        "  ▸ /miestado    Tu estado\n"
        "  ▸ /about       Sobre el sistema\n"
        "{rule}"
    ).format(rule=RULE, product=PRODUCT)

def build_about_vip():
    """About VIP. Una pantalla, sin mecanica interna, sin versionado."""
    return (
        "{rule}\n"
        "  ◆ {product}\n"
        "{rule}\n"
        "\n"
        "  Senales {pair} con disciplina\n"
        "  sistematica.\n"
        "\n"
        "  Cuando hay edge, dispara.\n"
        "  Cuando no, calla.\n"
        "\n"
        "  ▪ SL anclado a estructura\n"
        "  ▪ TPs en liquidez real\n"
        "  ▪ Resultados auditables\n"
        "  ▪ Veto fin de semana\n"
        "\n"
        "  Par         {pair}\n"
        "  Exchange    OKX\n"
        "  Ventana     24/5 (lun-vie)\n"
        "{rule}\n"
        "  {disclaimer}"
    ).format(rule=RULE, product=PRODUCT, pair=PAIR, disclaimer=DISCLAIMER)

def build_about_admin():
    """Vista admin con sustrato matematico. NO se expone a clientes."""
    return (
        "{rule}\n"
        "  ◆ {product} · admin\n"
        "{rule}\n"
        "\n"
        "  MASTER EQUATION:\n"
        "  P_master = Theta(D) * kappa_evo * phi *\n"
        "             W_eff * H_lap * f_conf * f_ict\n"
        "\n"
        "  W_eff = w_clock * alpha + w_kz * (1-alpha)\n"
        "  alpha = max(0, 1 - n_closed / 50)\n"
        "  f_ict = 1.0 + n_concepts * 0.04   (cap 4)\n"
        "\n"
        "  GATE FINAL:\n"
        "  EMIT iff P(SL) ≤ 0.35 AND EV ≥ 1.0R\n"
        "\n"
        "  TIMELINES:\n"
        "  paths      500 (admin 2000)\n"
        "  horizon    96 velas (24h / 15m)\n"
        "  optimizer  grid QAOA-inspired\n"
        "\n"
        "  CONSTANTES:\n"
        "  phi    = 1.6180339887\n"
        "  phi^2  = 2.6180\n"
        "  phi^3  = 4.2360\n"
        "  alpha  = 1/137.507\n"
        "\n"
        "  THRESHOLDS:\n"
        "  PMASTER_MIN     = 1.80\n"
        "  RR_MIN_TP3      = 1.80\n"
        "  CONFLUENCE_MIN  = 3\n"
        "  KAPPA cap       = +-15%\n"
        "  QTE_MAX_P_SL    = 0.35\n"
        "  QTE_MIN_EV_R    = 1.00\n"
        "  Cooldown        = 1h\n"
        "{rule}"
    ).format(rule=RULE, product=PRODUCT)

# ============================================================
# WELCOME
# ============================================================
def build_welcome():
    return (
        "{rule}\n"
        "  ◆ {product}\n"
        "{rule}\n"
        "\n"
        "  Senales {pair} con disciplina\n"
        "  sistematica.\n"
        "\n"
        "  Cuando hay edge, dispara.\n"
        "  Cuando no, calla.\n"
        "\n"
        "  ▸ /precio      Tarifas\n"
        "  ▸ /codigo XXXX Canjear codigo\n"
        "  ▸ /miestado    Tu estado\n"
        "  ▸ /about       Sobre el sistema\n"
        "{rule}\n"
        "  {disclaimer}"
    ).format(rule=RULE, product=PRODUCT, pair=PAIR, disclaimer=DISCLAIMER)

def build_welcome_for_tier(tier):
    if tier in ("vip", "admin", "trial"):
        return (
            "{rule}\n"
            "  ◆ {product} · Acceso activo\n"
            "{rule}\n"
            "  Tu canal de senales esta activo.\n"
            "\n"
            "  ▸ /status      Estado\n"
            "  ▸ /lectura     Analisis\n"
            "  ▸ /miestado    Tu cuenta\n"
            "  ▸ /help        Comandos\n"
            "{rule}"
        ).format(rule=RULE, product=PRODUCT)
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
