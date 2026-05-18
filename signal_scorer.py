# -*- coding: utf-8 -*-
"""
================================================================================
  SIGNAL SCORER - Ensemble + Shapley attribution
  by RasDG_Sol + Claude (FQ v4.3)

  Capa de scoring/ranking POR ENCIMA del motor FQ.
  NUNCA sustituye P_master, Theta(D), kappa_evo — sólo enriquece la decisión
  cuando P_master ya pasó el umbral (≥ phi² ≈ 2.618 ≈ 7/10).

  Inspirado en:
  - Gradient boosting: ensemble de weak learners (cada scorer mira un aspecto)
  - LightGBM/XGBoost: weighted average con pesos ajustables (booster updates)
  - Shapley values: atribución por feature (linear ensemble → trivial)

  5 scorers independientes, cada uno emite 0.0-1.0:
    1. volume       — confirma volumen institucional (PDF Order Blocks tip #3)
    2. structure    — alineación multi-TF, profundidad PD zone
    3. liquidity    — sweep quality, pool freshness, reaction strength
    4. concept_stack— cuántos conceptos ICT confirmados
    5. history      — Thompson posterior + expectancy histórica del bucket

  Salida: dict con score_total, breakdown, shapley_attribution.
================================================================================
"""
import os
import logging
from datetime import datetime, timezone

log = logging.getLogger("fq_signal_scorer")

# ============================================================
# CONFIG - pesos del ensemble (env-overridable)
# ============================================================
def _parse_weights(env_value, default):
    """Parsea "0.20,0.20,0.20,0.20,0.20" -> [0.20]*5, normaliza a sum=1"""
    if not env_value:
        return default
    try:
        parts = [float(x.strip()) for x in env_value.split(",")]
        if len(parts) != len(default):
            return default
        s = sum(parts)
        if s <= 0:
            return default
        return [p / s for p in parts]
    except Exception:
        return default

DEFAULT_WEIGHTS = [0.20, 0.20, 0.20, 0.20, 0.20]
SCORER_NAMES    = ["volume", "structure", "liquidity", "concept_stack", "history"]
WEIGHTS = _parse_weights(os.environ.get("FQ_SCORER_WEIGHTS", ""), DEFAULT_WEIGHTS)

# Umbral del ensemble - por debajo, la senal se "downgradea" o veta
ENSEMBLE_MIN_FOR_FIRE     = float(os.environ.get("FQ_ENSEMBLE_MIN", "0.55"))
ENSEMBLE_MIN_FOR_HIGHTIER = float(os.environ.get("FQ_ENSEMBLE_HIGH", "0.70"))

# Solo se ACTIVA el scorer cuando P_master ya superó phi^2 (~7/10 en conviction_score)
PHI = 1.6180339887
PHI_SQ = PHI * PHI

# ============================================================
# SCORER 1: VOLUME (PDF Order Blocks #3 - confirmación institucional)
# ============================================================
def score_volume(df_15m, lookback=20, target_mult=1.5):
    """
    Score 0-1 basado en cuánto excede el volumen reciente al baseline.
    1.0 si ratio >= target_mult, 0.0 si ratio <= 1.0, lineal entremedio.
    """
    try:
        if df_15m is None or len(df_15m) < lookback + 3 or "volume" not in df_15m.columns:
            return 0.5, "sin volume data (neutral)"
        recent = float(df_15m["volume"].iloc[-3:].mean())
        baseline = float(df_15m["volume"].iloc[-lookback:-3].mean())
        if baseline <= 0:
            return 0.5, "baseline 0 (neutral)"
        ratio = recent / baseline
        if ratio >= target_mult:
            score = 1.0
        elif ratio <= 1.0:
            score = 0.0
        else:
            score = (ratio - 1.0) / (target_mult - 1.0)
        return max(0.0, min(1.0, score)), "vol {:.2f}x baseline".format(ratio)
    except Exception as e:
        return 0.5, "vol error: {}".format(str(e)[:40])

# ============================================================
# SCORER 2: STRUCTURE (alineación 4H+1H + profundidad PD zone)
# ============================================================
def score_structure(field):
    try:
        score = 0.0
        # +0.40 si bias_4h y 1h alineados
        if field.bias_aligned and field.bias_4h != "rango":
            score += 0.40
        # +0.30 si PD zone es discount/premium profundo (>70% del rango opuesto)
        if field.pd_zone == "discount" and field.pd_pct < 0.30:
            score += 0.30
        elif field.pd_zone == "premium" and field.pd_pct > 0.70:
            score += 0.30
        elif field.pd_zone in ("discount", "premium"):
            score += 0.15
        # +0.30 por score_4h fuerte (>=3) que confirma tendencia clara
        if abs(field.score_4h) >= 3:
            score += 0.30
        elif abs(field.score_4h) >= 2:
            score += 0.15
        score = max(0.0, min(1.0, score))
        return score, "bias={} pd={}({:.0%}) score4h={}".format(
            "Y" if field.bias_aligned else "N", field.pd_zone,
            field.pd_pct, field.score_4h)
    except Exception as e:
        return 0.5, "struct error: {}".format(str(e)[:40])

# ============================================================
# SCORER 3: LIQUIDITY (sweep + reaction + pool freshness)
# ============================================================
def score_liquidity(field, direction):
    try:
        score = 0.0
        # +0.50 por sweep reciente CON reacción
        sweep = field.recent_sweep
        if sweep and sweep.get("reaction", False):
            score += 0.50
        elif sweep:
            score += 0.20
        # +0.30 por pool objetivo intacto en la dirección operable
        if direction == "long" and field.pool_low and not field.pool_low.swept:
            score += 0.30
        elif direction == "short" and field.pool_high and not field.pool_high.swept:
            score += 0.30
        # +0.20 por CRT confirmado en TF bajo en la dirección correcta
        if field.crt and field.crt.confirmed:
            expected = "bullish_crt" if direction == "long" else "bearish_crt"
            if field.crt.crt_type == expected:
                score += 0.20
        score = max(0.0, min(1.0, score))
        return score, "sweep={} pool_obj={} crt={}".format(
            "Y" if (sweep and sweep.get("reaction")) else "N",
            "Y" if field.has_fuel else "N",
            "Y" if (field.crt and field.crt.confirmed) else "N")
    except Exception as e:
        return 0.5, "liq error: {}".format(str(e)[:40])

# ============================================================
# SCORER 4: CONCEPT STACK (cuántos conceptos ICT confirmados)
# ============================================================
def score_concept_stack(concepts_flags):
    try:
        n_active = sum(1 for v in concepts_flags.values() if v)
        total = len(concepts_flags) if concepts_flags else 7
        # Score = n_active / 5 (5 conceptos confirmados = score 1.0)
        score = min(1.0, n_active / 5.0)
        active_list = [k for k, v in concepts_flags.items() if v]
        return score, "{} conceptos ({})".format(
            n_active, "+".join(active_list[:4]) if active_list else "ninguno")
    except Exception as e:
        return 0.5, "concept error: {}".format(str(e)[:40])

# ============================================================
# SCORER 5: HISTORY (Thompson posterior + expectancy del bucket)
# ============================================================
def score_history(kappa_stats, bucket_memory):
    """
    kappa_stats: dict de Thompson (alpha, beta, p_mean, n)
    bucket_memory: BucketMemory legacy (win_rate, expectancy_r, confidence)
    """
    try:
        # Si hay data Thompson (preferred)
        if kappa_stats and kappa_stats.get("n", 0) >= 8:
            p_mean = kappa_stats.get("p_mean", 0.5)
            n = kappa_stats["n"]
            confidence_factor = min(1.0, n / 20.0)  # full confidence at 20 samples
            # Score = (p_mean - 0.5) * confidence + 0.5, mapped to [0,1]
            raw = (p_mean - 0.3) / 0.5  # 0.3 -> 0, 0.8 -> 1
            score = raw * confidence_factor + 0.5 * (1 - confidence_factor)
            return max(0.0, min(1.0, score)), "p_mean={:.2f} n={} conf={:.0%}".format(
                p_mean, n, confidence_factor)
        # Fallback a bucket memory legacy
        if bucket_memory and bucket_memory.confidence != "empty":
            wr = bucket_memory.win_rate
            exp = bucket_memory.expectancy_r
            # score = win_rate ajustado por expectancy
            score = wr * 0.6 + max(0, min(1, (exp + 1) / 3)) * 0.4
            return max(0.0, min(1.0, score)), "WR={:.0%} Exp={:+.2f}R".format(wr, exp)
        # Sin historia -> neutral
        return 0.5, "sin historia (neutral)"
    except Exception as e:
        return 0.5, "history error: {}".format(str(e)[:40])

# ============================================================
# ENSEMBLE - combinación lineal + Shapley attribution
# ============================================================
def evaluate(df_15m, field, direction, concepts_flags=None,
              kappa_stats=None, bucket_memory=None):
    """
    Computa el ensemble score completo con atribución Shapley.

    Returns dict:
      total_score: float 0-1
      breakdown:   list of (name, score, weight, contribution, detail)
      shapley:     list of (name, contribution_pct) ordenado por importancia
      verdict:     'high'|'medium'|'low'  (mapping desde total_score)
      reasons:     list de strings (top 2 contribuciones)
    """
    if concepts_flags is None:
        concepts_flags = {}

    s1, d1 = score_volume(df_15m)
    s2, d2 = score_structure(field)
    s3, d3 = score_liquidity(field, direction)
    s4, d4 = score_concept_stack(concepts_flags)
    s5, d5 = score_history(kappa_stats, bucket_memory)

    scores  = [s1, s2, s3, s4, s5]
    details = [d1, d2, d3, d4, d5]

    # Ensemble lineal
    contributions = [w * s for w, s in zip(WEIGHTS, scores)]
    total_score = sum(contributions)

    # Shapley en ensemble lineal = contribución directa (es trivial pero correcto)
    total_for_pct = total_score if total_score > 0 else 1e-9
    shapley = [
        (SCORER_NAMES[i], contributions[i],
         100.0 * contributions[i] / total_for_pct)
        for i in range(5)
    ]
    shapley_sorted = sorted(shapley, key=lambda x: -x[1])

    # Verdict
    if total_score >= ENSEMBLE_MIN_FOR_HIGHTIER:
        verdict = "high"
    elif total_score >= ENSEMBLE_MIN_FOR_FIRE:
        verdict = "medium"
    else:
        verdict = "low"

    reasons = ["{}: {}".format(SCORER_NAMES[i], details[i])
               for i in range(5) if scores[i] >= 0.55][:3]
    weak    = ["{}: {}".format(SCORER_NAMES[i], details[i])
               for i in range(5) if scores[i] < 0.35][:2]

    breakdown = [
        {"name": SCORER_NAMES[i], "score": scores[i],
         "weight": WEIGHTS[i], "contribution": contributions[i],
         "detail": details[i]}
        for i in range(5)
    ]

    return {
        "total_score":   total_score,
        "verdict":       verdict,
        "breakdown":     breakdown,
        "shapley":       shapley_sorted,
        "strengths":     reasons,
        "weaknesses":    weak,
        "weights_used":  list(WEIGHTS),
        "ts":            datetime.now(timezone.utc).isoformat(),
    }

# ============================================================
# SCORER ACCURACY TRACKING - MSBoost-style scorer selection
# Fuente: MSBoost (Moitra 2024) - "train multiple base estimators in
# parallel, select the one with least validation error per layer"
# Adaptacion: trackeamos accuracy reciente de cada scorer, atenuamos
# pesos de los que estan mas de 30% peor que la media reciente.
# ============================================================
def compute_scorer_accuracies(closed_signals, n_recent=30):
    """
    Para cada scorer, computa "directional accuracy" sobre las N ultimas
    cerradas: si scorer>=0.5 y pnl_r>0 (o scorer<0.5 y pnl_r<=0) = acierto.

    Returns dict {scorer_name: accuracy_0_to_1}
    """
    if not closed_signals:
        return None
    recent = closed_signals[-n_recent:] if len(closed_signals) > n_recent else closed_signals
    hits = [0] * 5
    total = 0
    for sig in recent:
        breakdown = sig.get("score_breakdown")
        pnl = sig.get("pnl_r")
        if not breakdown or pnl is None or len(breakdown) != 5:
            continue
        total += 1
        positive = pnl > 0
        for i in range(5):
            s = breakdown[i].get("score", 0.5)
            scorer_says_positive = s >= 0.5
            if scorer_says_positive == positive:
                hits[i] += 1
    if total < 10:
        return None
    return {SCORER_NAMES[i]: hits[i] / total for i in range(5)}

def apply_msboost_attenuation(weights, accuracies, atten_factor=0.5):
    """
    MSBoost-style: si un scorer esta significativamente peor que la media,
    atenua su peso en este ensemble (no lo elimina - solo reduce).

    Returns weights_attenuated (normalized to sum=1)
    """
    if not accuracies:
        return list(weights), {}
    accs = [accuracies.get(SCORER_NAMES[i], 0.5) for i in range(5)]
    mean_acc = sum(accs) / 5.0
    attenuations = {}
    new_weights = []
    for i, w in enumerate(weights):
        # Si scorer i esta >= 0.10 abajo de la media -> atenua
        if accs[i] < mean_acc - 0.10:
            new_w = w * atten_factor
            attenuations[SCORER_NAMES[i]] = "atten {:.1f}x (acc {:.0%} vs mean {:.0%})".format(
                atten_factor, accs[i], mean_acc)
        else:
            new_w = w
        new_weights.append(new_w)
    # Renormalize
    s = sum(new_weights)
    if s > 0:
        new_weights = [w / s for w in new_weights]
    return new_weights, attenuations

# ============================================================
# WEIGHT UPDATER (boosting + GOSS spirit) - usado por /retrain admin
# Fuente: LightGBM (Ke et al. 2017) - "instances with larger gradients
# contribute more to information gain". Aplicado a outcomes: SL recientes
# pesan mas en el update (residual grande = scorer fallo).
# ============================================================
def suggest_weights_from_ledger(closed_signals, current_weights=None):
    """
    Dado el ledger cerrado con score breakdowns guardados, sugiere pesos
    nuevos basados en correlación de cada scorer con outcome (pnl_r).

    Boosting básico: scorer con mayor correlación + outcome positivo
    sube peso; scorer con baja correlación o anti-correlación baja peso.

    closed_signals: list de dict con 'score_breakdown' (lista de dicts por scorer)
                    y 'pnl_r'.
    """
    if current_weights is None:
        current_weights = list(WEIGHTS)
    if not closed_signals or len(closed_signals) < 10:
        return current_weights, "insuficiente data (n={})".format(len(closed_signals or []))

    correlations = [0.0] * 5
    n_used = 0
    for sig in closed_signals:
        breakdown = sig.get("score_breakdown")
        pnl = sig.get("pnl_r")
        if not breakdown or pnl is None or len(breakdown) != 5:
            continue
        # GOSS-inspired weight: SL outcomes pesan 1.0 (residual grande),
        # TP1 con pnl<1.0 pesan 0.7, TP2/3/4 pesan 0.5 (residual chico)
        outcome = sig.get("outcome", "")
        if outcome == "sl":
            sample_weight = 1.0
        elif outcome == "tp1" and (pnl or 0) < 1.0:
            sample_weight = 0.7
        elif outcome in ("tp2", "tp3", "tp4"):
            sample_weight = 0.5
        elif outcome == "timeout":
            sample_weight = 0.6
        else:
            sample_weight = 0.6
        n_used += 1
        for i in range(5):
            scorer_score = breakdown[i].get("score", 0.5)
            # Correlación simple con peso GOSS
            correlations[i] += (scorer_score - 0.5) * pnl * sample_weight

    if n_used < 10:
        return current_weights, "insuficiente data utilizable (n={})".format(n_used)

    # Normaliza correlaciones a pesos (softmax suave)
    correlations = [c / n_used for c in correlations]
    min_corr = min(correlations)
    shifted = [c - min_corr + 0.1 for c in correlations]  # todos positivos
    total = sum(shifted)
    new_weights = [s / total for s in shifted]
    # Suavizar: 70% nuevo + 30% anterior (evita oscilaciones)
    blended = [0.7 * new_weights[i] + 0.3 * current_weights[i] for i in range(5)]
    s = sum(blended)
    blended = [b / s for b in blended]
    return blended, "actualizado con n={} cerradas".format(n_used)

# ============================================================
# GREEDY THRESHOLD SWEEP (post-hoc audit, no modifica nada vivo)
# Fuente: Friedman 2001 "Greedy Function Approximation" §3
# ============================================================
def threshold_sweep(closed_signals, lo=1.5, hi=3.5, step=0.05,
                     min_n_above=10):
    """
    Dado el ledger cerrado, barre PMASTER_MIN en [lo, hi] y reporta
    el threshold que habria maximizado expectancy_R.

    Returns dict con:
      best_threshold: float
      best_expectancy: float
      best_n: int
      sweep: list of (threshold, n, win_rate, expectancy)
    """
    if not closed_signals:
        return None
    sweep = []
    t = lo
    best_thr = None
    best_exp = -999
    best_n = 0
    while t <= hi:
        kept = [s for s in closed_signals
                if (s.get("p_master_final", 0) or 0) >= t and s.get("pnl_r") is not None]
        n = len(kept)
        if n >= min_n_above:
            pnls = [s["pnl_r"] for s in kept]
            wins = sum(1 for p in pnls if p > 0)
            wr = wins / n
            exp = sum(pnls) / n
            sweep.append((round(t, 3), n, wr, exp))
            if exp > best_exp:
                best_exp = exp
                best_thr = round(t, 3)
                best_n = n
        t += step
    if best_thr is None:
        return None
    return {
        "best_threshold":  best_thr,
        "best_expectancy": best_exp,
        "best_n":          best_n,
        "sweep":           sweep,
    }

def format_sweep_telegram(sweep_result, current_threshold=1.80):
    """Formato para /sweep admin"""
    rule = "━" * 30
    if not sweep_result:
        return "Sweep: ledger insuficiente."
    sweep = sweep_result["sweep"]
    best = sweep_result["best_threshold"]
    lines = [
        rule,
        "  ◆ FQ · Greedy Threshold Sweep",
        rule,
        "  Threshold actual:  {:.2f}".format(current_threshold),
        "  Threshold optimo:  {:.2f}  (Exp={:+.2f}R n={})".format(
            best, sweep_result["best_expectancy"], sweep_result["best_n"]),
        "",
        "  Comparacion (PMASTER >= thr):",
    ]
    # Show 5 around current + best
    targets = set()
    for delta in (-0.30, -0.15, 0.0, 0.15, 0.30):
        targets.add(round(current_threshold + delta, 2))
    targets.add(best)
    for thr, n, wr, exp in sweep:
        if round(thr, 2) in targets:
            marker = "  -> " if abs(thr - best) < 0.001 else "     "
            lines.append("  {}{:.2f}  n={:<3} WR={:.0%} Exp={:+.2f}R".format(
                marker, thr, n, wr, exp))
    lines.append(rule)
    lines.append("  Solo SUGERENCIA. Subir threshold reduce volumen,")
    lines.append("  bajarlo viola CONSTRAINTS §6 (P_master >= 7/10).")
    return "\n".join(lines)

def format_attribution_telegram(score_result):
    """Formato Telegram del breakdown Shapley para /atribucion"""
    rule = "━" * 30
    lines = [
        rule,
        "  ◆ FQ · Atribucion Shapley",
        rule,
        "  Score ensemble: {:.3f}  [{}]".format(
            score_result["total_score"], score_result["verdict"].upper()),
        "",
        "  Contribucion por feature:",
    ]
    for name, contrib, pct in score_result["shapley"]:
        bar_len = int(pct / 5)
        bar = "█" * bar_len + "·" * max(0, 20 - bar_len)
        lines.append("  {:<14} {:.3f}  {:5.1f}%".format(name, contrib, pct))
        lines.append("  {}".format(bar))
    lines.append("")
    if score_result["strengths"]:
        lines.append("  Fortalezas:")
        for r in score_result["strengths"]:
            lines.append("  ▪ {}".format(r))
    if score_result["weaknesses"]:
        lines.append("")
        lines.append("  Debilidades:")
        for r in score_result["weaknesses"]:
            lines.append("  ▪ {}".format(r))
    lines.append(rule)
    return "\n".join(lines)
