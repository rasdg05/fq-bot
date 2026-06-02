# -*- coding: utf-8 -*-
"""
Veredicto canonico del QTE - UNA sola fuente de verdad.

Antes habia tres clasificadores con thresholds distintos (vip_format._market_tone,
quantum_timelines.qte_verdict y la linea cruda de Phase E), asi que el VIP podia
decir "confluencia confirmada" mientras el admin decia otra cosa sobre el MISMO
setup. Este modulo unifica la lectura: una funcion pura, sin numpy ni I/O, que
ambas superficies consumen. quantum_analysis la hornea en el dict `qa` (clave
"verdict") para que admin, VIP y la lectura de Claude cuenten la misma historia.

compute() devuelve dict:
  grade      -> "favorable" | "moderado" | "adverso" | "neutro"
  label      -> headline para admin ("EDGE FAVORABLE", ...)
  tone       -> linea cualitativa para VIP (sin numeros crudos)
  admin_body -> descripcion con numeros (solo vistas admin)
"""

_BODIES = {
    "favorable": ("La mayoria de timelines alcanza TP antes que SL "
                  "(EV {ev:+.2f}R, P(SL) {psl:.0%}). Setup con ventaja estadistica."),
    "moderado":  ("Balance inclinado a favor pero con riesgo real "
                  "(EV {ev:+.2f}R, P(SL) {psl:.0%}). Considerar tamano reducido."),
    "adverso":   ("Casi todas las timelines tocan SL antes que cualquier TP "
                  "(EV {ev:+.2f}R, P(SL) {psl:.0%}). Sin edge: manos quietas."),
    "neutro":    ("Probabilidades mixtas, ninguna direccion domina "
                  "(EV {ev:+.2f}R, P(SL) {psl:.0%}, TP1 {ptp1:.0%}). Esperar confirmacion."),
}


def _f(d, key, default=0.0):
    v = d.get(key, default)
    return float(v) if v is not None else default


def compute(qa, direction=None):
    """Clasifica el resultado del QTE en un veredicto unico. Devuelve None si
    qa es falsy (sin QTE)."""
    if not qa:
        return None
    probs = qa.get("probabilities") or {}
    regs = qa.get("regimes") or {}

    p_sl = _f(probs, "p_sl")
    ev = _f(probs, "expected_R")
    p_tp1 = float(probs.get("p_reach_tp1", probs.get("p_tp1", 0.0)) or 0.0)
    coh = _f(qa, "coherence")

    bull = _f(regs, "bull_continuation")
    bear = _f(regs, "bear_reversal")
    if direction == "long":
        fav = bull
    elif direction == "short":
        fav = bear
    else:
        fav = max(bull, bear)

    if ev >= 1.2 and p_sl <= 0.30 and fav >= 0.40 and coh >= 0.55:
        grade, label = "favorable", "EDGE FUERTE"
        tone = "Sesgo dominante a favor · confluencia alta"
    elif ev >= 1.0 and p_sl <= 0.35:
        grade, label = "favorable", "EDGE FAVORABLE"
        tone = "Confluencia confirmada"
    elif ev >= 0.3 and p_sl <= 0.55:
        grade, label = "moderado", "EDGE MODERADO"
        tone = "Confluencia media · ejecutar con disciplina"
    elif p_sl >= 0.80 or ev <= -0.6:
        grade, label = "adverso", "ESCENARIO ADVERSO"
        tone = "Campo adverso · las timelines tocan SL primero"
    else:
        grade, label = "neutro", "SIN EDGE CLARO"
        tone = "Campo neutro · esperar confirmacion"

    return {
        "grade": grade,
        "label": label,
        "tone": tone,
        "admin_body": _BODIES[grade].format(ev=ev, psl=p_sl, ptp1=p_tp1),
    }


def coherence_label(coh):
    """Traduce la coherencia (0-1) a la dispersion legible de las timelines."""
    if coh >= 0.66:
        return "timelines convergentes, escenario definido"
    if coh >= 0.40:
        return "dispersion media, escenario abierto"
    return "timelines dispersas, alta incertidumbre"
