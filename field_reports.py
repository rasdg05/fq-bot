# -*- coding: utf-8 -*-
"""
================================================================================
  FIELD REPORTS - FQ v4.1.1 Refactor
  Plantilla "LECTURA DE CAMPO" (Capa 5 spec)
================================================================================

  Reemplaza alertas binarias por reportes estructurados.
  Modos:
    - SENAL ALINEADA: reporte completo con ACCION
    - CAMPO SIN SENAL: reporte solo lectura (Fase A/B/C/D fallo)
"""
from datetime import datetime, timezone, timedelta

CDMX_TZ = timezone(timedelta(hours=-6))

def _cdmx_now_str():
    return datetime.now(CDMX_TZ).strftime("%Y-%m-%d %H:%M CDMX")

def _fmt_phase_verdict(decision, failed_at=None):
    """Veredicto visual"""
    if decision == "fire":
        return "[ALINEADO] Senal emitida"
    if decision in ("field_only",):
        return "[DESALINEADO] Fase {} fallida".format(failed_at)
    if decision == "math_below_threshold":
        return "[AMBIGUO] 4 fases OK, P_master bajo umbral"
    if decision == "rr_insufficient":
        return "[AMBIGUO] P_master OK, R:R insuficiente"
    return "[SILENCIO] Campo sin claridad"

# ============================================================
# REPORTE COMPLETO (senal disparada)
# ============================================================
def build_signal_report(field, decision_report, tf_label="SCALPING", tf_id="15m", pmin=1.80):
    """Reporte de campo con SENAL ACTIVA. Usado cuando decision='fire'.
    tf_label: clase de estrategia (INTRADIA/SCALPING/SWING).
    tf_id: timeframe primario ('5m'/'15m'/'1h').
    pmin: umbral PMASTER_MIN del perfil del TF (para mostrar en el reporte)."""
    direction = decision_report["direction"]
    pm = decision_report["p_master_data"]
    levels = decision_report["levels"]
    side = "LONG" if direction == "long" else "SHORT"
    side_glyph = "[LONG]" if direction == "long" else "[SHORT]"

    # Tier + leverage
    PHI_CB = 1.6180339887 ** 3
    PHI_SQ = 1.6180339887 ** 2
    if pm["p_master"] >= PHI_CB:
        leverage, sizing, tier_label = "8x", "10%", "phi^3 alta conviccion"
    elif pm["p_master"] >= PHI_SQ:
        leverage, sizing, tier_label = "5x", "5%",  "phi^2 standard"
    else:
        leverage, sizing, tier_label = "3x", "2%",  "phi scalp"

    # Confluencia formateada
    conf_str = ", ".join(field.confluence_list[:6]) if field.confluence_list else "—"

    # Pools
    pool_h = "${:.2f} [{}]".format(field.pool_high.price,
                                    "barrido" if field.pool_high.swept else "intacto"
                                    ) if field.pool_high else "—"
    pool_l = "${:.2f} [{}]".format(field.pool_low.price,
                                    "barrido" if field.pool_low.swept else "intacto"
                                    ) if field.pool_low else "—"
    sweep_str = "—"
    if field.recent_sweep:
        sweep_str = "{} a ${:.2f} (reaccion {})".format(
            field.recent_sweep["direction"].upper(),
            field.recent_sweep["price"],
            "SI" if field.recent_sweep.get("reaction") else "NO")

    # MSS/BOS - soporta dict legacy y MSSEvent dataclass v3
    mss_str = "—"
    if field.last_mss:
        if hasattr(field.last_mss, "confirmed") and field.last_mss.confirmed:
            mss_str = "${:.2f} {}".format(
                field.last_mss.price, field.last_mss.direction or "")
        elif isinstance(field.last_mss, dict):
            mss_str = "${:.2f} {}".format(
                field.last_mss.get("price", 0), field.last_mss.get("direction", ""))

    # Bucket memory
    bm = pm.get("bucket_memory") or field.bucket_memory
    if bm and bm.confidence != "empty":
        bm_str = "n={} WR={:.0%} Exp={:+.2f}R streak={:+d}".format(
            bm.n_closed, bm.win_rate, bm.expectancy_r, bm.streak)
    else:
        bm_str = "(sin historico suficiente)"

    # ICT concepts v3 (PDF "14 Most Important ICT Concepts")
    concepts = pm.get("concepts", {})
    f_ict = pm.get("f_ict", 1.0)
    n_concepts = pm.get("n_concepts", 0)
    concept_labels = [
        ("breaker",      "Breaker Block"),
        ("mss",          "Market Structure Shift"),
        ("inducement",   "Inducement (LTF liq)"),
        ("pwr3",         "Power of 3 (AMD)"),
        ("bpr",          "Balanced Price Range"),
        ("ote_strict",   "OTE 62-79% (sweet 70.5)"),
        ("displacement", "Displacement"),
    ]
    concepts_block = "\n".join(
        "  {} {}".format("[+]" if concepts.get(k) else "[.]", label)
        for k, label in concept_labels
    )
    kappa_method = pm.get("kappa_method", "legacy")

    # Mapa de contexto multi-TF segun primario
    _ctx_map = {
        "5m":  "1H+15m+5m+1m",
        "15m": "4H+1H+15m+1m",
        "1h":  "1D+4H+1h+5m",
    }
    tf_ctx = _ctx_map.get(tf_id, "4H+1H+15m+1m")

    msg = (
        "<b>FQ — [{tf_label} {tf_id}] LECTURA DE CAMPO</b>\n"
        "================================\n"
        "{when} | Killzone: <b>{kz}</b>\n"
        "SOL/USDT | TFs: {tf_ctx}\n\n"
        "<b>━━ ESTADO DEL CAMPO ━━</b>\n"
        "Sesgo 4H: {b4} (score {s4:+d})\n"
        "Sesgo 1H: {b1} (score {s1:+d})\n"
        "Alineacion: {al}\n"
        "Rango: ${rl:.2f} — ${rh:.2f}\n"
        "Zona PD: <b>{pd}</b> ({pp:.0%})\n"
        "MSS: {mss}\n\n"
        "<b>━━ LIQUIDEZ ━━</b>\n"
        "Pool superior: {ph}\n"
        "Pool inferior: {pl}\n"
        "Sweep reciente: {sw}\n\n"
        "<b>━━ NODO EN OBSERVACION ━━</b>\n"
        "Nivel: ${cn:.2f}\n"
        "Confluencia ({cc}): {conf}\n"
        "Tipo: <b>{nt}</b>\n"
        "Jerarquia PD: <b>{hi}</b>\n\n"
        "<b>━━ MATEMATICA CUANTICA ━━</b>\n"
        "P_base (phi): 1.618\n"
        "W_killzone: {wkz:.2f}  W_legacy: {wleg:.2f}\n"
        "W_eff: {weff:.2f}  alpha={alpha:.2f}\n"
        "f_CHoCH: {fch}  f_Confluencia: {fcon:.3f}\n"
        "H_lap: {hl}\n"
        "<b>P_master_raw: {pmr:.3f}</b>\n"
        "kappa_evo: {kev:.3f}\n"
        "<b>P_master final: {pm:.3f}</b> / min {pmin:.2f}\n\n"
        "<b>━━ VEREDICTO ━━</b>\n"
        "[ALINEADO] {tier_label}\n\n"
        "<b>━━ ACCION ({side_g} {side}) ━━</b>\n"
        "ENTRY: ${entry:.2f}\n"
        "SL: ${sl:.2f} (anclado a EMA50/estructura)\n"
        "TP1 30%: ${tp1:.2f}  R:R {rr1:.2f}\n"
        "TP2 30%: ${tp2:.2f}  R:R {rr2:.2f}\n"
        "TP3 25%: ${tp3:.2f}  R:R {rr3:.2f}\n"
        "TP4 15%: ${tp4:.2f}  R:R {rr4:.2f}\n"
        "Leverage: <b>{lev}</b>  Size: {size}\n\n"
        "<b>━━ CONCEPTOS ICT (14 PDF) ━━</b>\n"
        "{concepts_block}\n"
        "Bonus ICT: x{f_ict:.3f} ({n_concepts} activos)\n\n"
        "<b>━━ MEMORIA DEL BUCKET ━━</b>\n"
        "Bucket v2: {bk}\n"
        "Bucket v3: {bk3}\n"
        "Conf: {bcf}  {bms}\n"
        "Kappa metodo: {kmethod}\n\n"
        "<b>━━ INVALIDACION ━━</b>\n"
        "- Cierre {tf_id} {cmp} ${sl:.2f} -> CERRAR\n"
        "- 90 min sin progreso a TP1 -> REVISAR\n"
        "- SL nunca se mueve (Regla 4)\n\n"
        "#FQ #SOLUSDT #{tf_label} #{tf_id} #{side}"
    ).format(
        tf_label=tf_label, tf_id=tf_id, tf_ctx=tf_ctx,
        when=_cdmx_now_str(),
        kz=field.killzone.upper(),
        b4=field.bias_4h, s4=field.score_4h,
        b1=field.bias_1h, s1=field.score_1h,
        al="SI" if field.bias_aligned else "NO",
        rl=field.range_low, rh=field.range_high,
        pd=field.pd_zone.upper(), pp=field.pd_pct,
        mss=mss_str,
        ph=pool_h, pl=pool_l, sw=sweep_str,
        cn=field.current_node or field.price,
        cc=field.confluence_count, conf=conf_str,
        nt=field.node_type.upper(), hi=field.pd_hierarchy.upper(),
        wkz=field.w_killzone, wleg=field.w_clock_legacy,
        weff=field.w_effective, alpha=pm["alpha_hybrid"],
        fch="1.618" if field.choch else "1.000",
        fcon=pm["f_confluence"], hl=pm["h_factor"],
        pmr=pm["p_master_raw"], kev=pm["kappa_evo"], pm=pm["p_master"],
        pmin=pmin, tier_label=tier_label,
        side_g=side_glyph, side=side,
        entry=levels["entry"], sl=levels["sl"],
        tp1=levels["tp1"], rr1=levels["rr_tp1"],
        tp2=levels["tp2"], rr2=levels["rr_tp2"],
        tp3=levels["tp3"], rr3=levels["rr_tp3"],
        tp4=levels["tp4"], rr4=levels["rr_tp4"],
        lev=leverage, size=sizing,
        bk=pm["bucket_key_v2"],
        bk3=pm.get("bucket_key_v3", "—"),
        bcf=(bm.confidence.upper() if bm else "EMPTY"), bms=bm_str,
        kmethod=kappa_method,
        concepts_block=concepts_block,
        f_ict=f_ict, n_concepts=n_concepts,
        cmp="<" if direction == "long" else ">",
    )
    return msg

# ============================================================
# REPORTE SIN SENAL (solo lectura de campo)
# ============================================================
def build_field_only_report(field, decision_report):
    """Reporte de campo cuando alguna fase fallo o no hay senal viable.
       Solo a admin/VIP, no al free tier."""
    direction_inf = decision_report.get("direction_inferred", "?")
    failed_at = decision_report.get("failed_at", "?")
    reason = decision_report.get("reason", "")
    decision = decision_report.get("decision", "silence")

    verdict = _fmt_phase_verdict(decision, failed_at)

    # Condicion de espera segun fase fallida
    wait_cond = _build_wait_condition(field, failed_at, direction_inf)

    pool_h = "${:.2f}".format(field.pool_high.price) if field.pool_high else "—"
    pool_l = "${:.2f}".format(field.pool_low.price) if field.pool_low else "—"
    conf_str = ", ".join(field.confluence_list[:5]) if field.confluence_list else "—"

    msg = (
        "<b>FQ — REPORTE DE CAMPO</b>\n"
        "================================\n"
        "{when} | Killzone: {kz}\n\n"
        "<b>━━ ESTADO ━━</b>\n"
        "Sesgo 4H: {b4} | 1H: {b1} | Align: {al}\n"
        "Rango: ${rl:.2f}—${rh:.2f}  PD: <b>{pd}</b> ({pp:.0%})\n"
        "Pool sup: {ph} | Pool inf: {pl}\n"
        "Confluencia ({cc}): {conf}\n"
        "Jerarquia PD: {hi} | Nodo: {nt}\n\n"
        "<b>━━ VEREDICTO ━━</b>\n"
        "{verdict}\n"
        "Direccion inferida: {dir}\n"
        "Razon: {reason}\n\n"
        "<b>━━ CONDICION DE ESPERA ━━</b>\n"
        "{wait}\n\n"
        "#FQ #FieldOnly"
    ).format(
        when=_cdmx_now_str(),
        kz=field.killzone.upper(),
        b4=field.bias_4h, b1=field.bias_1h,
        al="SI" if field.bias_aligned else "NO",
        rl=field.range_low, rh=field.range_high,
        pd=field.pd_zone.upper(), pp=field.pd_pct,
        ph=pool_h, pl=pool_l,
        cc=field.confluence_count, conf=conf_str,
        hi=field.pd_hierarchy.upper(), nt=field.node_type.upper(),
        verdict=verdict,
        dir=direction_inf.upper() if direction_inf else "?",
        reason=reason, wait=wait_cond,
    )
    return msg

def _build_wait_condition(field, failed_at, direction):
    """Genera la condicion de espera especifica segun la fase que fallo"""
    if failed_at == "A":
        if field.bias_4h == "rango":
            return "Esperar que 4H defina sesgo direccional (MSS o BOS claro)"
        if not field.bias_aligned:
            return "Esperar que 1H se alinee con 4H ({})".format(field.bias_4h)
        if field.pd_zone == "equilibrium":
            return "Esperar pullback profundo: precio en equilibrium (~50%)"
        return "Zona PD incorrecta para direccion propuesta — esperar reverso"
    if failed_at == "B":
        if direction == "long" and field.pool_low:
            return "Esperar sweep del pool inferior ${:.2f} con reaccion alcista".format(
                field.pool_low.price)
        if direction == "short" and field.pool_high:
            return "Esperar sweep del pool superior ${:.2f} con reaccion bajista".format(
                field.pool_high.price)
        return "Sin liquidez identificable — esperar formacion de pools"
    if failed_at == "C":
        return "Esperar precio en confluencia ICT (>=3 elementos: Fib + OB/FVG + estructura)"
    if failed_at == "D":
        if field.killzone == "fuera":
            return "Esperar killzone activa (London Open / NY AM / Silver Bullet)"
        return "Esperar trigger CRT en TF bajo o validacion de memoria de bucket"
    if failed_at == "p_master":
        return "P_master bajo umbral — esperar mejor confluencia o killzone superior"
    if failed_at == "rr":
        return "R:R insuficiente — esperar mejor punto de entrada"
    return "Esperar condiciones operables"
