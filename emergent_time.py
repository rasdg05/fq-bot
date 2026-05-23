# -*- coding: utf-8 -*-
"""
================================================================================
  EMERGENT TIME - FQ v5.1 Mistral Edition
  Postulado tau(t) = phi_clock * phi_memory * phi_horizon * phi_refractory
  by RasDG_Sol + Claude

  Modulo INERTE. Funciones puras. Cero imports del bot.
  Solo math/numpy/logging. Importable sin side effects.

  Spec: _POSTULATE_EMERGENT_TIME.md
================================================================================
"""
import math
import os
import logging

log = logging.getLogger("emergent_time")

# ============================================================
# CONSTANTES
# ============================================================
DECAY_N_DEFAULT       = 50       # = HYBRID_DECAY_N de fusion_engine
W_KILLZONE_MAX        = 1.40     # peso Silver Bullet (techo del rango)
COOLDOWN_REF_MINUTES  = 60.0     # = SIGNAL_COOLDOWN_HOURS_V2 * 60

PHI_CLOCK_FLOOR       = 0.43     # asia / fuera de killzone, evita degradar a 0
KAPPA_EVO_FLOOR       = 0.85
KAPPA_EVO_CEIL        = 1.15
PMASTER_INFLATION_CAP = 1.10

SYNC_WEIGHTS_DEFAULT  = (0.30, 0.25, 0.20, 0.15, 0.10)
# (tau, regime_consistency, killzone_alignment, evr_quality, streak_health)

SYNC_TIER_VETO_LO     = 0.30
SYNC_TIER_ATTEN_LO    = 0.50
SYNC_TIER_BOOST_LO    = 0.70
SYNC_TIER_STRONG_LO   = 0.85


# ============================================================
# UTILS
# ============================================================
def _clip(x, lo, hi):
    if x is None:
        return lo
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return lo
        return max(lo, min(hi, v))
    except (TypeError, ValueError):
        return lo


def _safe_float(x, default=0.0):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _load_weights_from_env():
    raw = os.environ.get("FQ_SYNC_WEIGHTS", "").strip()
    if not raw:
        return SYNC_WEIGHTS_DEFAULT
    try:
        parts = [float(x.strip()) for x in raw.split(",")]
        if len(parts) != 5:
            log.warning("FQ_SYNC_WEIGHTS debe tener 5 valores, recibi %d. Usando default.", len(parts))
            return SYNC_WEIGHTS_DEFAULT
        total = sum(parts)
        if total <= 0:
            return SYNC_WEIGHTS_DEFAULT
        return tuple(p / total for p in parts)  # re-normalizar
    except (ValueError, TypeError) as e:
        log.warning("FQ_SYNC_WEIGHTS parse error: %s. Usando default.", e)
        return SYNC_WEIGHTS_DEFAULT


# ============================================================
# PROYECCIONES PHI
# ============================================================
def phi_clock(w_killzone):
    """Fase de sesion renormalizada de W_killzone / W_max.
    None/<=0 -> PHI_CLOCK_FLOOR (asia / fuera de killzone)."""
    if w_killzone is None:
        return PHI_CLOCK_FLOOR
    v = _safe_float(w_killzone, 0.0)
    if v <= 0:
        return PHI_CLOCK_FLOOR
    return _clip(v / W_KILLZONE_MAX, PHI_CLOCK_FLOOR, 1.0)


def phi_memory(n_closed, win_rate, confidence, decay_n=DECAY_N_DEFAULT):
    """Maduracion del bucket. 1 - exp(-N/decay_n) con clausula bucket toxic.
    confidence='active' AND wr<0.30 AND n>=16 -> 0.0 forzado.
    confidence='empty' o n<=0 -> 0.0.
    """
    if confidence == "empty":
        return 0.0
    n = int(n_closed) if n_closed is not None else 0
    if n <= 0:
        return 0.0
    wr = _safe_float(win_rate, 0.0)
    if confidence == "active" and wr < 0.30 and n >= 16:
        return 0.0  # bucket toxic - kill switch
    return _clip(1.0 - math.exp(-n / float(decay_n)), 0.0, 1.0)


def phi_horizon(qte_payload):
    """Convergencia probabilistica del QTE.
    (1 - p_sl) * clip(ev_r / 2.0, 0, 1) * coherence.
    qte_payload=None -> 1.0 (neutral, no penaliza ausencia)."""
    if qte_payload is None:
        return 1.0
    p_sl = _safe_float(qte_payload.get("p_sl"), 0.5)
    ev_r = _safe_float(qte_payload.get("ev_r"), 0.0)
    coh  = _safe_float(qte_payload.get("coherence"), 0.5)
    return _clip((1.0 - p_sl) * _clip(ev_r / 2.0, 0.0, 1.0) * coh, 0.0, 1.0)


def phi_refractory(delta_minutes, cooldown_minutes=COOLDOWN_REF_MINUTES):
    """Recuperacion post-emision. delta=0 -> 0, delta>=cooldown -> 1.
    None (primera senal sin previa) -> 1.0."""
    if delta_minutes is None:
        return 1.0
    d = _safe_float(delta_minutes, -1.0)
    if d < 0:
        return 0.0
    return _clip(d / float(cooldown_minutes), 0.0, 1.0)


# ============================================================
# TAU - PRODUCTO DE LAS 4 PROYECCIONES
# ============================================================
def tau(w_killzone, bucket_memory, qte_payload, delta_minutes,
        decay_n=DECAY_N_DEFAULT):
    """Postulado tau(t) = phi_clock * phi_memory * phi_horizon * phi_refractory.
    Cualquier proyeccion=0 anula tau (Theta(D) generalizado a 4D temporal)."""
    if bucket_memory is None:
        n_closed, win_rate, confidence = 0, 0.0, "empty"
    else:
        n_closed   = getattr(bucket_memory, "n_closed",  0)
        win_rate   = getattr(bucket_memory, "win_rate",  0.0)
        confidence = getattr(bucket_memory, "confidence", "empty")

    pc = phi_clock(w_killzone)
    pm = phi_memory(n_closed, win_rate, confidence, decay_n)
    ph = phi_horizon(qte_payload)
    pr = phi_refractory(delta_minutes)
    return {
        "tau":            pc * pm * ph * pr,
        "phi_clock":      pc,
        "phi_memory":     pm,
        "phi_horizon":    ph,
        "phi_refractory": pr,
    }


# ============================================================
# COMPONENTES DEL SYNC_SCORE
# ============================================================
def regime_consistency(regime_label, direction):
    """Alineacion regimen QTE <-> direccion propuesta."""
    if not regime_label or not direction:
        return 0.0
    r = str(regime_label).lower()
    d = str(direction).lower()
    if r == "bull_continuation" and d == "long":
        return 1.0
    if r == "bear_reversal" and d == "short":
        return 1.0
    if r == "sweep_and_reverse":
        return 0.7  # QTE espera sweep, podria favorecer entry contra-tendencia
    if r in ("chop", "range"):
        return 0.4
    return 0.0


def killzone_priority_alignment(priority):
    """Peso del killzone tier."""
    if not priority:
        return 0.3
    p = str(priority).lower()
    if p == "alta":
        return 1.0
    if p == "media":
        return 0.7
    if p == "baja":
        return 0.3
    return 0.3


def path_evr_quality(qte_payload):
    """Calidad del expected_R post-suavizado. None -> 0.5 (neutral)."""
    if qte_payload is None:
        return 0.5
    ev_r = _safe_float(qte_payload.get("ev_r"), 0.0)
    p_sl = _safe_float(qte_payload.get("p_sl"), 0.5)
    return _clip(_clip(ev_r / 2.0, 0.0, 1.0) * (1.0 - p_sl), 0.0, 1.0)


def bucket_streak_health(streak):
    """streak >= -1 -> 1.0; streak <= -3 -> 0.0; intermedio lineal.
    None -> 1.0 (neutral)."""
    if streak is None:
        return 1.0
    s = int(_safe_float(streak, 0))
    if s >= -1:
        return 1.0
    if s <= -3:
        return 0.0
    # s == -2 -> 0.5
    return 0.5


# ============================================================
# SYNC SCORE
# ============================================================
def compute_sync_score(field, bucket_memory, qte_payload, delta_minutes,
                       direction, weights=None, decay_n=DECAY_N_DEFAULT):
    """Combinacion ponderada de 5 componentes.
    Pesos default (0.30, 0.25, 0.20, 0.15, 0.10), override por env FQ_SYNC_WEIGHTS.
    Retorna dict con sync_score + breakdown completo."""
    if weights is None:
        weights = _load_weights_from_env()

    w_killzone = getattr(field, "w_killzone", None) if field is not None else None
    kz_priority = getattr(field, "killzone_priority", None) if field is not None else None
    streak = getattr(bucket_memory, "streak", None) if bucket_memory is not None else None

    tau_data = tau(w_killzone, bucket_memory, qte_payload, delta_minutes, decay_n)

    regime_label = qte_payload.get("regime_modal") if qte_payload else None
    components = {
        "tau":                tau_data["tau"],
        "regime_consistency": regime_consistency(regime_label, direction),
        "killzone_alignment": killzone_priority_alignment(kz_priority),
        "evr_quality":        path_evr_quality(qte_payload),
        "streak_health":      bucket_streak_health(streak),
    }

    w_tau, w_reg, w_kz, w_evr, w_streak = weights
    sync_score = (
        w_tau    * components["tau"]
      + w_reg    * components["regime_consistency"]
      + w_kz     * components["killzone_alignment"]
      + w_evr    * components["evr_quality"]
      + w_streak * components["streak_health"]
    )
    sync_score = _clip(sync_score, 0.0, 1.0)

    return {
        "sync_score":     sync_score,
        "components":     components,
        "tau_components": tau_data,
        "weights_used":   weights,
    }


# ============================================================
# MODULADORES (tabla 3.2 del postulado)
# ============================================================
def sync_modulators(sync_score):
    """Mapea sync_score -> (sigma_tau, f_conf_mult, kappa_evo_mult, tier).
    Tier veto: sigma_tau=0 (P_master colapsa). Tier neutral: sin cambio."""
    s = _safe_float(sync_score, 0.0)

    if s < SYNC_TIER_VETO_LO:
        return {"sigma_tau": 0.0, "f_conf_mult": 1.0,  "kappa_evo_mult": 1.0,  "tier": "veto"}
    if s < SYNC_TIER_ATTEN_LO:
        return {"sigma_tau": 1.0, "f_conf_mult": 0.85, "kappa_evo_mult": 0.95, "tier": "attenuated"}
    if s < SYNC_TIER_BOOST_LO:
        return {"sigma_tau": 1.0, "f_conf_mult": 1.0,  "kappa_evo_mult": 1.0,  "tier": "neutral"}
    if s < SYNC_TIER_STRONG_LO:
        return {"sigma_tau": 1.05, "f_conf_mult": 1.05, "kappa_evo_mult": 1.0,  "tier": "boost"}
    return {"sigma_tau": 1.10, "f_conf_mult": 1.10, "kappa_evo_mult": 1.05, "tier": "strong_boost"}


# ============================================================
# CAPS DE SEGURIDAD (3.3 del postulado)
# ============================================================
def apply_kappa_cap(kappa):
    """Clip kappa_evo a [0.85, 1.15] siempre."""
    return _clip(kappa, KAPPA_EVO_FLOOR, KAPPA_EVO_CEIL)


def apply_inflation_cap(p_master_pre, p_master_post):
    """P_master post-PhaseE no puede crecer mas de PMASTER_INFLATION_CAP (10%) sobre pre."""
    caps = []
    if p_master_pre <= 0:
        return p_master_post, caps
    ceiling = p_master_pre * PMASTER_INFLATION_CAP
    if p_master_post > ceiling:
        caps.append("inflation_cap")
        return ceiling, caps
    return p_master_post, caps


# ============================================================
# ADAPTER QTE PAYLOAD - resuelve dominant_regime <-> regime_modal
# ============================================================
def build_qte_payload_from_quantum_analysis(qa_result):
    """Normaliza el dict de quantum_analysis() al contrato interno de Phase E.

    Input: dict de quantum_timelines.quantum_analysis() con shape
      {'probabilities': {'p_sl', 'p_tp1', 'p_tp2', 'p_tp3', 'expected_R'},
       'coherence': float, 'dominant_regime': str, ...}

    Output: dict con shape {p_sl, p_tp1, p_tp2, p_tp3, ev_r, coherence,
                            regime_modal, uncertainty} o None si invalido.
    """
    if qa_result is None or not isinstance(qa_result, dict):
        return None
    probs = qa_result.get("probabilities")
    if not probs:
        # QTE call failed o resultado malformado - tratar como ausencia
        return None
    regime = qa_result.get("regime_modal") or qa_result.get("dominant_regime")
    coh = _safe_float(qa_result.get("coherence"), 0.5)
    return {
        "p_sl":         _safe_float(probs.get("p_sl"),    0.5),
        "p_tp1":        _safe_float(probs.get("p_tp1"),   0.0),
        "p_tp2":        _safe_float(probs.get("p_tp2"),   0.0),
        "p_tp3":        _safe_float(probs.get("p_tp3"),   0.0),
        "ev_r":         _safe_float(probs.get("expected_R"), 0.0),
        "coherence":    coh,
        "regime_modal": regime,
        "uncertainty":  _clip(1.0 - coh, 0.0, 1.0),
    }


# ============================================================
# SELF-TESTS
# ============================================================
def _run_self_tests():
    """Tests sinteticos del modulo. Ejecutar con: python emergent_time.py"""
    print("Running emergent_time self-tests...\n")

    # ---- Test 1: tau optimo (Silver Bullet + bucket maduro + QTE bueno + refractario OK)
    class _BM:
        n_closed = 50
        win_rate = 0.55
        confidence = "active"
        streak = 1
    qte_good = {"p_sl": 0.20, "ev_r": 1.8, "coherence": 0.85, "regime_modal": "bull_continuation"}

    class _F:
        w_killzone = 1.40
        killzone_priority = "alta"
    res = compute_sync_score(_F(), _BM(), qte_good, delta_minutes=120, direction="long")
    print("[1] tau optimo: sync={:.3f} tier={}".format(
        res["sync_score"], sync_modulators(res["sync_score"])["tier"]))
    assert res["sync_score"] > 0.70, "tau optimo deberia dar sync>0.70, dio {:.3f}".format(res["sync_score"])
    assert sync_modulators(res["sync_score"])["tier"] in ("boost", "strong_boost")

    # ---- Test 2: bucket toxic veto
    class _BMtoxic:
        n_closed = 20
        win_rate = 0.20
        confidence = "active"
        streak = -3
    res2 = compute_sync_score(_F(), _BMtoxic(), qte_good, delta_minutes=120, direction="long")
    print("[2] bucket toxic: sync={:.3f} phi_mem={:.3f}".format(
        res2["sync_score"], res2["tau_components"]["phi_memory"]))
    assert res2["tau_components"]["phi_memory"] == 0.0, "bucket toxic phi_memory debe ser 0"
    assert res2["tau_components"]["tau"] == 0.0, "tau debe ser 0 si phi_memory=0"

    # ---- Test 3: sin QTE -> phi_horizon neutral, no veta por ausencia
    res3 = compute_sync_score(_F(), _BM(), None, delta_minutes=120, direction="long")
    print("[3] sin QTE: sync={:.3f} phi_hor={:.3f}".format(
        res3["sync_score"], res3["tau_components"]["phi_horizon"]))
    assert res3["tau_components"]["phi_horizon"] == 1.0, "phi_horizon sin QTE debe ser 1.0"
    assert sync_modulators(res3["sync_score"])["tier"] != "veto", "sin QTE no debe vetar"

    # ---- Test 4: refractario - senal recien emitida
    res4 = compute_sync_score(_F(), _BM(), qte_good, delta_minutes=0.0, direction="long")
    print("[4] refractario delta=0: sync={:.3f} phi_ref={:.3f}".format(
        res4["sync_score"], res4["tau_components"]["phi_refractory"]))
    assert res4["tau_components"]["phi_refractory"] == 0.0, "phi_refractory(0) debe ser 0"
    assert res4["tau_components"]["tau"] == 0.0, "tau debe ser 0 si refractario=0"

    # ---- Test 5: inflation cap sweep
    p_pre = 2.0
    for s in [i / 20.0 for i in range(0, 21)]:  # 0.0, 0.05, ..., 1.0
        mods = sync_modulators(s)
        p_post_raw = p_pre * mods["sigma_tau"]
        p_post, caps = apply_inflation_cap(p_pre, p_post_raw)
        ratio = p_post / p_pre if p_pre > 0 else 0
        assert ratio <= PMASTER_INFLATION_CAP + 1e-9, \
            "sync={:.2f}: ratio {:.3f} > cap {:.2f}".format(s, ratio, PMASTER_INFLATION_CAP)
    print("[5] inflation cap sweep [0.0..1.0]: ratio_max <= {:.2f} OK".format(PMASTER_INFLATION_CAP))

    # ---- Test 6: kappa cap
    k = 1.10 * 1.10  # 1.21
    k_capped = apply_kappa_cap(k)
    print("[6] kappa cap: {:.3f} -> {:.3f}".format(k, k_capped))
    assert k_capped == KAPPA_EVO_CEIL, "kappa 1.21 deberia clipearse a {}".format(KAPPA_EVO_CEIL)

    k2 = 0.50
    assert apply_kappa_cap(k2) == KAPPA_EVO_FLOOR, "kappa 0.50 deberia clipearse a floor"

    # ---- Test 7: adapter dominant_regime -> regime_modal
    qa_fake = {
        "probabilities": {"p_sl": 0.25, "p_tp1": 0.50, "p_tp2": 0.30, "p_tp3": 0.15, "expected_R": 1.4},
        "coherence": 0.78,
        "dominant_regime": "bull_continuation",
    }
    payload = build_qte_payload_from_quantum_analysis(qa_fake)
    print("[7] adapter QTE: regime_modal={} ev_r={}".format(payload["regime_modal"], payload["ev_r"]))
    assert payload["regime_modal"] == "bull_continuation"
    assert payload["p_sl"] == 0.25
    assert payload["ev_r"] == 1.4
    assert payload["coherence"] == 0.78
    assert payload["uncertainty"] == _clip(1.0 - 0.78, 0.0, 1.0)

    # ---- Test 7b: adapter rechaza None / dict vacio / probabilities vacios
    assert build_qte_payload_from_quantum_analysis(None) is None
    assert build_qte_payload_from_quantum_analysis({}) is None  # sin probabilities -> None
    assert build_qte_payload_from_quantum_analysis({"probabilities": None}) is None
    # adapter ACEPTA probabilities parciales con defaults
    partial = build_qte_payload_from_quantum_analysis(
        {"probabilities": {"p_sl": 0.3}, "coherence": 0.7, "dominant_regime": "range"})
    assert partial is not None
    assert partial["p_sl"] == 0.3
    assert partial["ev_r"] == 0.0  # default cuando falta

    # ---- Test 8: phi_clock floor cuando w_killzone None o <=0
    assert phi_clock(None) == PHI_CLOCK_FLOOR
    assert phi_clock(0) == PHI_CLOCK_FLOOR
    assert phi_clock(-1) == PHI_CLOCK_FLOOR
    assert phi_clock(1.40) == 1.0
    assert abs(phi_clock(0.70) - 0.5) < 1e-9
    print("[8] phi_clock edges: None/0/-1 -> floor; 1.40 -> 1.0; 0.70 -> 0.5")

    # ---- Test 9: weights override via env
    os.environ["FQ_SYNC_WEIGHTS"] = "1,1,1,1,1"  # uniformes
    w = _load_weights_from_env()
    expected = (0.20, 0.20, 0.20, 0.20, 0.20)
    for a, b in zip(w, expected):
        assert abs(a - b) < 1e-9, "weights uniformes deberian re-normalizar a 0.2"
    print("[9] weights env override + re-normalizacion: OK")
    del os.environ["FQ_SYNC_WEIGHTS"]

    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    _run_self_tests()
