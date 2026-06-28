# -*- coding: utf-8 -*-
"""
VIP format. Construye strings de cara al cliente.

Regla: las vistas VIP no exponen formulas, versiones ni jerga interna.
La vista admin permanece en bloque separado para evitar fugas accidentales.
Modulo inerte: no envia, no consulta DB.
"""
from datetime import datetime, timezone, timedelta

from branding import (
    PRODUCT, PAIR, MARKETS, DESK, HASHTAGS_SIGNAL, RULE, LUX_RULE, GLYPHS, DISCLAIMER,
    lux_header, lux_block, lux_item, lux_check, lux_footer,
)
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

def bump_tier(p_master):
    """Sube p_master al SIGUIENTE umbral de tier — el boost de order-flow confirmado
    (FQ_CVD_BOOST_TIER): una senal con order-flow a favor sube +1 nivel de conviccion
    y de size. Topa en phi^3 (= leverage cap 8x, CONSTRAINTS §1.5: nunca lo rebasa)."""
    if p_master is None:        return None
    if p_master < PHI:          return PHI       # Exploratoria -> Media
    if p_master < PHI_SQ:       return PHI_SQ    # Media -> Alta (3x -> 5x)
    if p_master < PHI_CB:       return PHI_CB    # Alta  -> Extrema (5x -> 8x)
    return p_master                              # Extrema: ya en el tope

# ============================================================
# SENAL VIP - simplificada, ejecutable sin exponer motor
# ============================================================
def build_vip_signal(field, decision_report, tf_label=None, tf_id=None, pair=None,
                     cvd_confirmed=None, boost_tier=False):
    """
    Senal lista para copy-paste. NO expone P_master, kappa_evo, Theta(D),
    f_confluencia ni constantes phi/alpha. Solo lo que el VIP necesita ejecutar.

    Las 3 abstracciones (Estructura/Liquidez/Momentum) mapean internamente a
    pilares del motor, pero el usuario VIP no ve la fuente.

    Este ES el formato unico de la SENAL real gateada: admin y VIP reciben lo
    mismo (limpio). El encabezado (│ Senal VIP) + la insignia de
    CALIDAD la distinguen de un vistazo de las alertas tacticas y las lecturas
    de campo. tf_label/tf_id son opcionales (contexto en el header).
    """
    direction = decision_report["direction"]
    pm     = decision_report["p_master_data"]
    levels = decision_report["levels"]

    side  = "LONG" if direction == "long" else "SHORT"
    arrow = GLYPHS["long"] if direction == "long" else GLYPHS["short"]

    # Boost de order-flow (capa 3 -> motor 1, FQ_CVD_BOOST_TIER): la senal con
    # order-flow CONFIRMADO sube +1 tier de conviccion y de size. Es lo que vuelve
    # el +0.34R del backtest en producto (la confirmada PESA mas, no solo se marca).
    p_eff = bump_tier(pm["p_master"]) if boost_tier else pm["p_master"]
    conviction = conviction_label(p_eff)
    lev, sizing = leverage_for_tier(p_eff)

    estruct_ok  = field.bias_aligned and field.pd_zone in ("discount", "premium")
    liquidez_ok = field.has_fuel and (
        bool(field.recent_sweep) or
        (field.pool_low if direction == "long" else field.pool_high)
    )
    momentum_ok = field.confluence_count >= 3 and field.node_type == "colapso"

    chk = GLYPHS["bullet_chk"]
    pilares = "\n".join([
        "  {} Estructura   {}".format(chk, "OK" if estruct_ok else "—"),
        "  {} Liquidez     {}".format(chk, "OK" if liquidez_ok else "—"),
        "  {} Momentum     {}".format(chk, "OK" if momentum_ok else "—"),
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
    pair_label = pair or PAIR   # BTC/USDT en la fusion BTC->VIP; SOL/USDT por defecto
    # Hashtag DINAMICO por par. Antes era HASHTAGS_SIGNAL hardcodeado a #SOLUSDT -> las
    # senales BTC/ETH salian con el tag de SOL. BTC/USDT -> "#FQ #BTCUSDT".
    sym_tags = "#FQ #" + (pair_label or PAIR).split(":")[0].replace("/", "")
    # Insignia de order-flow (capa 3, FQ_CVD_VIP_CONVICTION): SOLO si el flujo firmado
    # CONFIRMA la direccion en vivo. Es un HECHO (no promesa de R): la senal pertenece
    # al subset premium que en backtest 5y (DSR) rinde mas. "" cuando no -> la senal
    # queda byte-identica a la historica (default OFF en el monolito).
    cvd_line = ""
    if cvd_confirmed:
        cvd_line = "  {d} ORDER-FLOW CONFIRMADO\n".format(d=GLYPHS["premium"])

    return (
        "{rule}\n"
        "  {bar} {product} · Senal VIP · {pair}\n"
        "  {quality}\n"
        "{cvd_line}"
        "  {ctx}\n"
        "{rule}\n"
        "  {arrow} {side}        Conviccion {conv}\n"
        "\n"
        "  Entry    ${entry:.2f}\n"
        "  Stop     ${sl:.2f}    Riesgo {risk}\n"
        "\n"
        "  TP1      ${tp1:.2f}    R {rr1:.2f}\n"
        "  TP2      ${tp2:.2f}    R {rr2:.2f}\n"
        "  TP3      ${tp3:.2f}    R {rr3:.2f}\n"
        "  TP4      ${tp4:.2f}    R {rr4:.2f}\n"
        "{rule}\n"
        "{pilares}\n"
        "{rule}\n"
        "  Leverage {lev}   ·   Size {sizing}\n"
        "  SL inmutable.\n"
        "\n"
        "  {tags} #{side}"
    ).format(
        rule=RULE, bar=GLYPHS["title"], product=PRODUCT, pair=pair_label, quality=quality,
        cvd_line=cvd_line, ctx=ctx_line,
        arrow=arrow, side=side, conv=conviction, risk=risk_lbl,
        entry=levels["entry"], sl=levels["sl"],
        tp1=levels["tp1"], rr1=levels.get("rr_tp1", 0),
        tp2=levels["tp2"], rr2=levels.get("rr_tp2", 0),
        tp3=levels["tp3"], rr3=levels.get("rr_tp3", 0),
        tp4=levels["tp4"], rr4=levels.get("rr_tp4", 0),
        pilares=pilares, lev=lev, sizing=sizing,
        tags=sym_tags,
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

    c = GLYPHS["bullet_chk"]
    lines = [
        RULE,
        "  {} Plan · {}".format(GLYPHS["event"], PAIR),
        RULE,
        "  <b>{}</b>".format(plan["headline"]),
        "",
    ]

    if v == "EJECUTAR_AHORA":
        lines += [
            "  Entry      ${:.2f}".format(mkt["entry"]),
            "  Invalida   ${:.2f}".format(plan["invalidation"]),
            "  Objetivos  {}".format(tps_str),
            "",
            "  {} {} · probabilidad {}".format(c, ev_market, p_market.lower()),
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
        lines += ["  Acumula", acc]
        if plan.get("trigger"):
            lines.append("  Gatillo    {}".format(plan["trigger"]))
        lines += [
            "  Invalida   ${:.2f}".format(plan["invalidation"]),
            "  Objetivos  {}".format(tps_str),
            "",
            "  {} Regreso a zona: {}".format(c, p_reach.lower()),
            "  {} Desde zona:    {} · prob. {}".format(c, ev_zone, p_zone.lower()),
            "  {} A mercado:     {} · prob. {}".format(c, ev_market, p_market.lower()),
            "  → Mejor entrar acumulando en zona.",
        ]
    elif v == "ESPERAR_GATILLO":
        lines += [
            "  Gatillo    {}".format(plan.get("trigger") or "confirmacion a favor"),
            "  Invalida   ${:.2f}".format(plan["invalidation"]),
            "  Objetivos  {}".format(tps_str),
            "",
            "  {} {}".format(c, plan["rationale"]),
        ]
    else:  # STAND_DOWN
        lines += [
            "  {} {}".format(c, plan["rationale"]),
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
        headline = "EJECUTA {} con LÍMITE (maker) ~{}".format(side, entry_str)
    elif v == "ACUMULAR_EN_ZONA":
        z = plan["primary_zone"]
        headline = "ACUMULA {} en {} ${:.2f}-${:.2f}".format(
            side, z["label"], z["low"], z["high"])
        entry_str = "${:.2f}".format(z["ref"])
    else:
        # No deberia llegar otro verdict, pero defensive
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

    # Mismo acabado institucional que la senal FQ VIP, con CLASE propia
    # (ALERTA TACTICA): encabezado, regla, flecha de lado. Sin jerga de motor.
    lines = [
        RULE,
        "  {} {} · ALERTA TACTICA · {}".format(GLYPHS["title"], PRODUCT, PAIR),
        "  {}".format(headline),
        "  {}".format(ctx_line),
        RULE,
        "  {} {}".format(arrow, side),
        "",
    ]

    # Entrada / acumulacion
    if v == "EJECUTAR_AHORA":
        lines.append("  Entry      {}".format(entry_str))
    elif v == "ACUMULAR_EN_ZONA":
        acc = plan["primary_zone"].get("accumulate") or []
        lines.append("  Acumula")
        for a in acc:
            lines.append("     {:>3}%  ${:.2f}".format(a.get("weight_pct", 0),
                                                          a.get("price", 0)))
        if plan.get("trigger"):
            lines.append("  Gatillo    {}".format(plan["trigger"]))

    if invalidation is not None:
        lines.append("  Invalida   ${:.2f}".format(invalidation))

    # TPs cortos con % de cierre (40/35/25) y RR
    for i, tp in enumerate(tps_short, start=1):
        wp = tp.get("weight_pct", 0)
        lines.append("  TP{} ({:>2}%) ${:.2f}    R:R {:.2f}".format(
            i, wp, tp.get("price", 0), tp.get("rr", 0)))

    # Resumen cualitativo
    summary_bits = [ev_label_str, "prob. {}".format(p_label.lower())]
    if vol_label:
        summary_bits.append("volumen {}".format(vol_label.lower()))
    lines.append(RULE)
    lines.append("  {} ".format(GLYPHS["bullet_chk"]) + " · ".join(summary_bits))
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
        tp_lines.append("  TP{n}     ${p:.2f}   R {rr:.2f}   {k}".format(
            n=i+1, p=tp_meta[i]["price"], rr=tp_meta[i]["rr"], k=kind_lbl))
    if not tp_lines:
        for i in range(1, 4):
            p = levels.get("tp{}".format(i))
            rr = levels.get("rr_tp{}".format(i), 0)
            if p is not None:
                tp_lines.append("  TP{n}     ${p:.2f}   R {rr:.2f}".format(
                    n=i, p=p, rr=rr))
    tps_block = "\n".join(tp_lines)

    # Bloque cualitativo: tono + horizonte + nota de certeza (sin numeros crudos)
    tone = _market_tone(qa, direction)
    horizon_h = qa.get("horizon_hours") if qa else None
    quality = _quality_note(qa)
    c = GLYPHS["bullet_chk"]
    tbits = []
    if tone:
        tbits.append("  {} {}".format(c, tone))
    if horizon_h:
        tbits.append("  {} Horizonte ~{:.0f}h".format(c, horizon_h))
    if quality:
        tbits.append("  {} {}".format(c, quality))
    tone_block = ("\n".join(tbits) + "\n{}\n".format(RULE)) if tbits else ""

    battle = build_battle_block(plan)
    detalle_hdr = ("  {} Detalle".format(GLYPHS["event"]) if battle
                   else "  {} Analisis · {}".format(GLYPHS["event"], PAIR))
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
        "  Entry   ${entry:.2f}\n"
        "  Stop    ${sl:.2f}   Riesgo {risk} ({riskpct:.1f}% al stop)\n"
        "    anclado a {sla}\n"
        "\n"
        "{tps}\n"
        "{rule}\n"
        "{tone}"
        "  {c} SL estructural\n"
        "  {c} TPs en liquidez real\n"
        "{rule}\n"
        "  {tags}"
    ).format(
        rule=RULE, dhdr=detalle_hdr, when=when, px=float(last["close"]),
        decision=decision_line, riskpct=risk_pct,
        arrow=arrow, side=side, conv=conviction, risk=risk_lbl,
        entry=entry, sl=sl, sla=sla_lbl,
        tps=tps_block, tone=tone_block, tags=HASHTAGS_SIGNAL, c=c,
    )

# ============================================================
# /resultados - track record verificable (VIP/admin)
# ============================================================
def _fmt_results_window(label, w):
    c = GLYPHS["bullet_chk"]
    if not w:
        return "  {}\n  {} sin cierres aun".format(label, c)
    pf = w["profit_factor"]
    pf_str = "inf" if pf == float("inf") else "{:.2f}".format(pf)
    return (
        "  {label}\n"
        "  {c} Senales      {n}\n"
        "  {c} Win rate     {wr:.0%}\n"
        "  {c} Expectancy   {ex:+.2f}R\n"
        "  {c} Profit fctr  {pf}"
    ).format(label=label, n=w["n"], wr=w["win_rate"], ex=w["expectancy"], pf=pf_str, c=c)

def build_resultados(summary):
    """Track record VIP. summary = dict de get_results_summary, o None."""
    if not summary or not summary.get("total"):
        return (
            "{rule}\n  {bar} {product} · Resultados\n{rule}\n"
            "  Aun no hay cierres registrados.\n{rule}"
        ).format(rule=RULE, product=PRODUCT, bar=GLYPHS["title"])
    lines = [
        RULE,
        "  {} {} · Resultados".format(GLYPHS["title"], PRODUCT),
        RULE,
        _fmt_results_window("Ultimos 30 dias", summary.get("w30")),
        "",
        _fmt_results_window("Ultimos 90 dias", summary.get("w90")),
        "",
        _fmt_results_window("Historico total", summary.get("total")),
    ]
    streak = summary.get("longest_streak") or 0
    if streak >= 2:
        lines += ["", "  {} Mejor racha   {} cierres".format(GLYPHS["bullet_chk"], streak)]
    lines += [RULE, "  {}".format(DISCLAIMER)]
    return "\n".join(lines)

# ============================================================
# /help y /about
# ============================================================
def build_help_vip():
    return "\n".join([
        lux_header("{} · Tablero".format(PRODUCT), "Comandos VIP"),
        "",
        lux_item("/status", "Estado del sistema"),
        lux_item("/lectura", "Analisis on-demand"),
        lux_item("/miestado", "Tu cuenta"),
        lux_item("/renovar", "Renovar acceso"),
        lux_item("/about", "El sistema"),
        lux_item("/legal", "Aviso de riesgo"),
        LUX_RULE,
        lux_block("Calidad sobre cantidad."),
    ])

def build_help_admin():
    return "\n".join([
        lux_header("{} · Tablero".format(PRODUCT), "Comandos (admin)"),
        "",
        lux_block("Cliente:"),
        "   /status /lectura /miestado /renovar /about /legal",
        "",
        lux_block("Alias:"),
        "   /analisis /niveles /pspace /claude /ia → /lectura",
        "   /sesion /macro → /status",
        "",
        lux_block("Admin:"),
        lux_item("/audit", "Self-audit"),
        lux_item("/entropy", "Drift"),
        lux_item("/metrics", "Win rate · expectancy · PF"),
        lux_item("/ledger", "Ultimas 10 senales"),
        lux_item("/evolve", "Buckets"),
        lux_item("/concepts", "Edge por concepto"),
        lux_item("/weekend", "Filtro fin de semana"),
        lux_item("/campo", "FieldState on-demand"),
        lux_item("/gencode /grant /broadcast"),
        LUX_RULE,
    ])

def build_help_free():
    return "\n".join([
        lux_header("{} · Acceso".format(PRODUCT), "Activa tu acceso"),
        "",
        lux_item("/precio", "Tarifas"),
        lux_item("/vip", "Activar acceso"),
        lux_item("/codigo XXXX", "Canjear codigo"),
        lux_item("/miestado", "Tu estado"),
        lux_item("/about", "El sistema"),
        LUX_RULE,
    ])

def build_about_vip():
    """About VIP. Una pantalla, sin mecanica interna, sin versionado."""
    return "\n".join([
        lux_header("{} · {}".format(PRODUCT, DESK),
                   "Senales multi-símbolo de grado institucional"),
        "",
        lux_block(
            "Cuando hay ventaja, ejecuta.",
            "Cuando no, espera.",
        ),
        "",
        lux_check("SL anclado a estructura"),
        lux_check("TPs en liquidez real"),
        lux_check("Resultados auditables"),
        lux_check("Sin operar fines de semana"),
        "",
        lux_block(
            "Mercados     {} (SOL · BTC · ETH …)".format(MARKETS),
            "Exchange     OKX",
            "Ventana      24/5 (lun-vie)",
        ),
        LUX_RULE,
        lux_block(DISCLAIMER),
    ])

def build_about_admin():
    """Vista admin: resumen operativo del pipeline, sin volcar formulas
    ni constantes crudas. El detalle matematico vive en el codigo y en
    los comandos de auditoria (/audit, /metrics, /entropy)."""
    return "\n".join([
        lux_header("{} · admin".format(PRODUCT), "Resumen operativo"),
        "",
        lux_block("PIPELINE DE DECISION:"),
        lux_check("Contexto    sesgo, sesion y macro"),
        lux_check("Estructura  zonas, liquidez y confluencias"),
        lux_check("Conviccion  score compuesto del setup"),
        lux_check("Veredicto   proyeccion de escenarios"),
        "",
        lux_block("GATE DE EMISION:"),
        lux_check("Riesgo al stop acotado"),
        lux_check("Esperanza matematica positiva"),
        lux_check("Confluencias y R:R minimos"),
        lux_check("Cooldown y veto de fin de semana"),
        "",
        lux_block("AUDITORIA EN VIVO:"),
        "   /audit /metrics /entropy /ledger /evolve",
        LUX_RULE,
        lux_block("Parametros y formulas: en codigo."),
    ])

# ============================================================
# WELCOME
# ============================================================
def build_welcome():
    return "\n".join([
        lux_header("{} · {}".format(PRODUCT, DESK), MARKETS),
        "",
        lux_block(
            "Bienvenido a la mesa.",
            "",
            "Cuando hay ventaja, ejecuta.",
            "Cuando no, espera.",
        ),
        "",
        lux_footer(
            "/precio      Tarifas",
            "/codigo XXXX Canjear codigo",
            "/miestado    Tu estado",
            "/about       El sistema",
        ),
        "",
        lux_block(DISCLAIMER),
    ])

def build_welcome_for_tier(tier):
    if tier in ("vip", "admin", "trial"):
        return "\n".join([
            lux_header("{} · Acceso activo".format(PRODUCT),
                       "Canal operativo"),
            "",
            lux_block("Tu canal de senales esta encendido."),
            "",
            lux_footer(
                "/status      Estado",
                "/lectura     Analisis",
                "/miestado    Tu cuenta",
                "/help        Comandos",
            ),
        ])
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
