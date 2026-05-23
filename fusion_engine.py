# -*- coding: utf-8 -*-
"""
================================================================================
  FUSION ENGINE - FQ v4.1.1 Refactor
  Orquestador de las 4 fases A/B/C/D + memoria de outcome
================================================================================

  evaluate_signal() es la UNICA funcion publica.
  Reemplaza la logica monolitica de evaluate_setup() en fq_bot_v3_2.py.
"""
import logging
import os
import traceback
from datetime import datetime, timezone

import ict_smc as ict
import killzones_pd as kzpd
import entropy_cognition as ev

log = logging.getLogger("fq_fusion")

PHI = 1.6180339887
CONFLUENCE_MIN = 3
HYBRID_DECAY_N = 50

# Toggles (env) - todos default ON para "fase final beta" (CONSTRAINTS-compliant)
USE_THOMPSON_KAPPA = os.environ.get("FQ_USE_THOMPSON", "1") == "1"
WEEKEND_VETO       = os.environ.get("FQ_WEEKEND_VETO", "1") == "1"
REQUIRE_OTE_STRICT = os.environ.get("FQ_REQUIRE_OTE", "0") == "1"
ICT_CONCEPT_BONUS  = 0.04   # +4% por concepto ICT activo
ICT_BONUS_MAX_CONCEPTS = 4  # cap a 4 bonus = +16% max

# Gates legacy v3 — DESACTIVADOS por decision RasDG v4.3.
# Razon: con scorer ensemble + regime detector + order flow institucional,
# bloquear Asia/CHoCH/Fib-touches solo descarta setups validos. El sniper
# avanzado lee canal divino antes; estos filtros tarde lo convertian en amateur.
# Disponibles como override manual si se necesitan en debugging.
ASIA_VETO         = os.environ.get("FQ_ASIA_VETO", "0") == "1"
REQUIRE_CHOCH     = os.environ.get("FQ_REQUIRE_CHOCH", "0") == "1"
FIB_MIN_TOUCHES   = int(os.environ.get("FQ_FIB_MIN_TOUCHES", "0"))
PMASTER_HIGH_GATE = float(os.environ.get("FQ_PMASTER_HIGH_GATE", "2.965"))
ENFORCE_HIGH_GATE = os.environ.get("FQ_ENFORCE_HIGH_GATE", "0") == "1"

# Capa ML (FQ v4.3) - scorer + regime, todo additivo
USE_SCORER        = os.environ.get("FQ_USE_SCORER", "1") == "1"
USE_REGIME        = os.environ.get("FQ_USE_REGIME", "1") == "1"

# Phase E - postulado tau(t) emergente (FQ v5.1)
EMERGENT_TIME_ENABLED = os.environ.get("FQ_EMERGENT_TIME_ENABLED", "0").strip() in ("1", "true", "yes")
PHASE_E_QTE_N_PATHS   = int(os.environ.get("FQ_PHASE_E_N_PATHS", "300"))
PHASE_E_VETO_LO       = 0.30   # sync_score < esto -> veto absoluto

# Modulos ML (lazy import)
try:
    import signal_scorer
    import regime_detector
    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False
    signal_scorer = regime_detector = None

# QTE + emergent_time (lazy import) para Phase E
try:
    import quantum_timelines as qt
    import emergent_time
    _QTE_AVAILABLE = True
except ImportError:
    _QTE_AVAILABLE = False
    qt = emergent_time = None

# ============================================================
# CARGAR MEMORIA DE BUCKET (cierre del loop - decision 1)
# ============================================================
def _load_bucket_memory(bucket_key):
    """
    Carga BucketMemory desde el ledger v2. Si el bucket esta vacio,
    devuelve neutral. Si hay data, calcula WR, expectancy, streak.
    """
    bm = ict.BucketMemory(bucket_key=bucket_key)
    try:
        stats = ev.get_bucket_stats(bucket_key)
        if stats is None:
            bm.confidence = "empty"
            bm.kappa_evo = 1.0
            return bm
        bm.n_closed = stats["n"]
        bm.win_rate = stats["win_rate"]
        bm.expectancy_r = stats["expectancy"]
        # Profit factor y streak: lectura adicional al ledger
        outcomes = _fetch_last_n_outcomes(bucket_key, n=10)
        bm.last_n_outcomes = outcomes
        bm.streak = _compute_streak(outcomes)
        bm.profit_factor = _compute_profit_factor(bucket_key)
        if bm.n_closed < 8:
            bm.confidence = "empty"
            bm.kappa_evo = 1.0
        elif bm.n_closed < 16:
            bm.confidence = "watch"
            # kappa atenuado: max 50% de la modulacion
            exp_norm = max(-1.0, min(1.0, bm.expectancy_r / 1.5))
            bm.kappa_evo = 1.0 + (exp_norm * 0.15 * 0.5)
        else:
            bm.confidence = "active"
            exp_norm = max(-1.0, min(1.0, bm.expectancy_r / 1.5))
            bm.kappa_evo = 1.0 + (exp_norm * 0.15)
            bm.kappa_evo = max(0.85, min(1.15, bm.kappa_evo))
    except Exception as e:
        log.warning("load_bucket_memory({}): {}".format(bucket_key, e))
    return bm

def _fetch_last_n_outcomes(bucket_key, n=10):
    """Helper: ultimas N outcomes del bucket"""
    try:
        import sqlite3
        conn = ev._connect()
        try:
            rows = conn.execute(
                "SELECT outcome FROM signals WHERE bucket_key = ? "
                "AND outcome IS NOT NULL ORDER BY ts_closed DESC LIMIT ?",
                (bucket_key, n)
            ).fetchall()
        finally:
            conn.close()
        return [r["outcome"] for r in rows]
    except Exception:
        return []

def _compute_streak(outcomes):
    """Racha actual: + para wins consecutivos, - para SL consecutivos"""
    if not outcomes:
        return 0
    streak = 0
    first = outcomes[0]
    is_win = first.startswith("tp")
    is_loss = first == "sl"
    for o in outcomes:
        if is_win and o.startswith("tp"):
            streak += 1
        elif is_loss and o == "sl":
            streak -= 1
        else:
            break
    return streak

def _compute_profit_factor(bucket_key):
    try:
        conn = ev._connect()
        try:
            rows = conn.execute(
                "SELECT pnl_r FROM signals WHERE bucket_key = ? "
                "AND pnl_r IS NOT NULL", (bucket_key,)
            ).fetchall()
        finally:
            conn.close()
        if not rows:
            return 0.0
        wins = sum(r["pnl_r"] for r in rows if r["pnl_r"] > 0)
        losses = abs(sum(r["pnl_r"] for r in rows if r["pnl_r"] < 0))
        if losses < 0.01:
            return wins * 10 if wins > 0 else 0.0
        return wins / losses
    except Exception:
        return 0.0

def _compute_delta_minutes(last_ts):
    """Minutos desde last_ts. None/timestamp invalido -> None (primera senal)."""
    if last_ts is None:
        return None
    try:
        if isinstance(last_ts, (int, float)):
            last_dt = datetime.fromtimestamp(float(last_ts), tz=timezone.utc)
        else:
            last_dt = last_ts
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - last_dt
        return delta.total_seconds() / 60.0
    except Exception:
        return None

# ============================================================
# FASE A - SESGO ESTRUCTURAL + PD
# ============================================================
def _execute_phase_a(field, direction):
    # CONSTRAINTS §1 - Asia veto duro salvo override explicito
    if ASIA_VETO and field.killzone == "asia_kz":
        return {"passed": False, "phase": "A.0",
                "reason": "CONSTRAINTS §1 - sesion Asia excluida (FQ_ASIA_VETO=0 para override)"}
    # CONSTRAINTS §2 - CHoCH mandatorio
    if REQUIRE_CHOCH and not field.choch:
        return {"passed": False, "phase": "A.0c",
                "reason": "CONSTRAINTS §2 - CHoCH no confirmado (FQ_REQUIRE_CHOCH=0 para override)"}
    if field.bias_4h == "rango":
        return {"passed": False, "phase": "A.1",
                "reason": "Bias 4H en rango — sin direccion estructural"}
    if not field.bias_aligned:
        return {"passed": False, "phase": "A.2",
                "reason": "4H={} vs 1H={} desalineados".format(
                    field.bias_4h, field.bias_1h)}
    aligned, reason = field.aligned_with_direction(direction)
    if not aligned:
        return {"passed": False, "phase": "A.3", "reason": reason}
    if direction == "long" and field.pd_pct > 0.40:
        return {"passed": False, "phase": "A.4",
                "reason": "LONG con pd_pct={:.0%} — fuera de discount profundo".format(
                    field.pd_pct)}
    if direction == "short" and field.pd_pct < 0.60:
        return {"passed": False, "phase": "A.4",
                "reason": "SHORT con pd_pct={:.0%} — fuera de premium profundo".format(
                    field.pd_pct)}
    return {"passed": True, "phase": "A"}

# ============================================================
# FASE B - LIQUIDEZ
# ============================================================
def _execute_phase_b(field, direction):
    if not field.has_fuel:
        return {"passed": False, "phase": "B.1",
                "reason": "Sin pools de liquidez identificables"}
    has_recent_sweep = (field.recent_sweep is not None and
                        field.recent_sweep.get("reaction", False))
    has_target_pool = False
    if direction == "long" and field.pool_low and not field.pool_low.swept:
        has_target_pool = True
    if direction == "short" and field.pool_high and not field.pool_high.swept:
        has_target_pool = True
    if not (has_recent_sweep or has_target_pool):
        return {"passed": False, "phase": "B.2",
                "reason": "Sin sweep con reaccion ni pool objetivo claro"}
    if has_recent_sweep:
        sweep_dir = field.recent_sweep.get("direction")
        if direction == "long" and sweep_dir == "high":
            return {"passed": False, "phase": "B.3",
                    "reason": "Sweep reciente del pool SUPERIOR — contra LONG"}
        if direction == "short" and sweep_dir == "low":
            return {"passed": False, "phase": "B.3",
                    "reason": "Sweep reciente del pool INFERIOR — contra SHORT"}
    return {"passed": True, "phase": "B"}

# ============================================================
# FASE C - CONFLUENCIA ICT
# ============================================================
def _execute_phase_c(field, direction):
    if field.confluence_count < CONFLUENCE_MIN:
        return {"passed": False, "phase": "C.1",
                "reason": "Confluencia {}/{} — superposicion".format(
                    field.confluence_count, CONFLUENCE_MIN)}
    if field.node_type != "colapso":
        return {"passed": False, "phase": "C.2",
                "reason": "Nodo en superposicion — no operable"}
    required_directional = False
    if direction == "long":
        if (field.order_blocks.get("bullish") and
            field.order_blocks["bullish"].still_valid):
            required_directional = True
        if any(f.direction == "bullish" and f.filled_pct < 0.5
               for f in field.fvgs):
            required_directional = True
    else:
        if (field.order_blocks.get("bearish") and
            field.order_blocks["bearish"].still_valid):
            required_directional = True
        if any(f.direction == "bearish" and f.filled_pct < 0.5
               for f in field.fvgs):
            required_directional = True
    if not required_directional:
        return {"passed": False, "phase": "C.3",
                "reason": "Sin OB/FVG valido para {}".format(direction.upper())}
    if field.pd_hierarchy == "nula":
        return {"passed": False, "phase": "C.4",
                "reason": "Jerarquia PD = NULA"}
    # C.5: OTE estricto si el bot esta en modo "solo OTE" (env flag)
    if REQUIRE_OTE_STRICT:
        if not (field.ote_zone and field.ote_zone.valid and field.ote_zone.in_zone):
            return {"passed": False, "phase": "C.5",
                    "reason": "Fuera de zona OTE estricta (62-79% retracement)"}
    # C.6: CONSTRAINTS §3 - Fib minimum touches
    # n_touches = cuantos fib levels estan en confluencia (proxy del Fib touch count)
    if FIB_MIN_TOUCHES > 0:
        fib_in_confluence = sum(1 for c in field.confluence_list
                                 if isinstance(c, str) and c.startswith("fib_"))
        if fib_in_confluence < FIB_MIN_TOUCHES:
            return {"passed": False, "phase": "C.6",
                    "reason": "CONSTRAINTS §3 - Fib touches {}/{} (FQ_FIB_MIN_TOUCHES=0 para override)".format(
                        fib_in_confluence, FIB_MIN_TOUCHES)}
    return {"passed": True, "phase": "C"}

# ============================================================
# FASE D - TIMING + CRT + MEMORIA OUTCOME
# ============================================================
def _execute_phase_d(field, direction, p_master_provisional, tf_id=None):
    # Sub-check 1: killzone operable
    if field.killzone_priority == "baja":
        if field.confluence_count < 5:
            return {"passed": False, "phase": "D.1",
                    "reason": "Fuera de killzone con confluencia justa ({}) — req >=5".format(
                        field.confluence_count)}
    # Sub-check 2: CRT
    if field.crt is None or not field.crt.confirmed:
        return {"passed": False, "phase": "D.2",
                "reason": "Sin CRT confirmado en TF bajo"}
    if direction == "long" and field.crt.crt_type != "bullish_crt":
        return {"passed": False, "phase": "D.2",
                "reason": "CRT es {} — incoherente con LONG".format(field.crt.crt_type)}
    if direction == "short" and field.crt.crt_type != "bearish_crt":
        return {"passed": False, "phase": "D.2",
                "reason": "CRT es {} — incoherente con SHORT".format(field.crt.crt_type)}

    # Sub-check 3: memoria de outcome (cierre del loop)
    tier_provisional = ev.tier_from_pmaster(p_master_provisional)
    bucket_key = field.bucket_key_v2(tier_provisional, direction, tf_id=tf_id)
    field.bucket_memory = _load_bucket_memory(bucket_key)
    bm = field.bucket_memory
    if bm.confidence == "active":
        if bm.win_rate < 0.30 and bm.n_closed >= 16:
            return {"passed": False, "phase": "D.3",
                    "reason": "Bucket toxico: WR={:.0%} en {} cerradas (kappa_evo={:.2f})".format(
                        bm.win_rate, bm.n_closed, bm.kappa_evo)}
        if bm.streak <= -4:
            return {"passed": False, "phase": "D.3",
                    "reason": "Racha de {} perdidas consecutivas en bucket".format(
                        abs(bm.streak))}
    return {"passed": True, "phase": "D"}

# ============================================================
# P_MASTER REFINADO
# ============================================================
def _compute_p_master_refined(field, direction, masses, lap, config, phase_e_data=None):
    """
    Calculo final con hibrido w_clock <-> w_killzone + f_confluence + ICT concepts.
    Usa Thompson sampling sobre bucket_key_v3 si FQ_USE_THOMPSON=1.
    Si phase_e_data presente: aplica sync_modulator sobre kappa_evo y P_master con caps.
    """
    tf_id = config.get("TF_ID")  # opcional: separa memorias 5m/15m/1h
    n_closed_v2 = ev.count_closed_v2_buckets() if hasattr(ev, "count_closed_v2_buckets") else 0
    alpha = kzpd.refine_field_timing(field, n_closed_v2, HYBRID_DECAY_N)

    h_factor = 1.0 if lap["active"] else 0.7
    f_confluence = field.confluence_factor()

    p_master_raw = PHI * field.w_effective * h_factor
    p_master_raw *= 1 + (masses["count"] - 2) * 0.15
    p_master_raw *= f_confluence

    # === BONUS POR CONCEPTOS ICT v3 ===
    # Cada concepto detectado y confirmado aporta hasta +ICT_CONCEPT_BONUS (capped)
    concepts = ict.compile_concept_flags(field)
    n_concepts = min(ICT_BONUS_MAX_CONCEPTS, sum(1 for v in concepts.values() if v))
    f_ict = 1.0 + (n_concepts * ICT_CONCEPT_BONUS)
    p_master_raw *= f_ict

    # === KAPPA EVO ===
    tier = ev.tier_from_pmaster(p_master_raw)
    bucket_key_v2 = field.bucket_key_v2(tier, direction, tf_id=tf_id)
    bucket_key_v3 = ev.make_bucket_key_v3(
        field.killzone, tier, direction,
        field.pd_zone, field.pd_hierarchy, concepts, tf_id=tf_id
    )
    bucket_key_coarse = ev.make_bucket_key_v3_coarse(field.killzone, tier, direction, tf_id=tf_id)

    if USE_THOMPSON_KAPPA and hasattr(ev, "compute_kappa_thompson"):
        kappa_evo, kappa_stats = ev.compute_kappa_thompson(
            bucket_key_v3, bucket_key_coarse
        )
        kappa_method = "thompson"
        bm = _load_bucket_memory(bucket_key_v2)  # mantiene info legacy para reports
    else:
        bm = _load_bucket_memory(bucket_key_v2)
        kappa_evo = bm.kappa_evo
        kappa_stats = {"n": bm.n_closed, "method": "legacy_v2"}
        kappa_method = "legacy_v2"

    p_master = p_master_raw * kappa_evo

    # === FASE E - SYNC MODULATOR (FQ v5.1) ===
    # Si phase_e_data presente: aplica sigma_tau sobre P_master + kappa_evo_mult con caps.
    # Si no: comportamiento identico a v5.0 exacto (back-compat).
    sigma_tau = 1.0
    sync_score = None
    sync_tier = None
    kappa_evo_modulated = kappa_evo
    caps_applied = []
    if phase_e_data is not None and _QTE_AVAILABLE:
        mods = emergent_time.sync_modulators(phase_e_data["sync_score"])
        sigma_tau = mods["sigma_tau"]
        sync_score = phase_e_data["sync_score"]
        sync_tier = mods["tier"]
        kappa_evo_modulated = emergent_time.apply_kappa_cap(kappa_evo * mods["kappa_evo_mult"])
        p_master_pre = p_master_raw * kappa_evo_modulated
        p_master_post_raw = p_master_pre * sigma_tau
        p_master, caps_applied = emergent_time.apply_inflation_cap(p_master_pre, p_master_post_raw)
        kappa_evo = kappa_evo_modulated  # para reporting downstream

    return {
        "p_master_raw":   p_master_raw,
        "p_master":       p_master,
        "kappa_evo":      kappa_evo,
        "kappa_method":   kappa_method,
        "kappa_stats":    kappa_stats,
        "alpha_hybrid":   alpha,
        "w_effective":    field.w_effective,
        "w_clock_legacy": field.w_clock_legacy,
        "w_killzone":     field.w_killzone,
        "h_factor":       h_factor,
        "f_confluence":   f_confluence,
        "f_ict":          f_ict,
        "n_concepts":     n_concepts,
        "concepts":       concepts,
        "n_masses":       masses["count"],
        "tier":           tier,
        "bucket_key_v2":  bucket_key_v2,
        "bucket_key_v3":  bucket_key_v3,
        "bucket_key_coarse": bucket_key_coarse,
        "bucket_memory":  bm,
        "n_closed_v2":    n_closed_v2,
        # Phase E (FQ v5.1) - None cuando flag OFF
        "sync_score":           sync_score,
        "sync_tier":            sync_tier,
        "sigma_tau":            sigma_tau,
        "kappa_evo_modulated":  kappa_evo_modulated,
        "phase_e_components":   phase_e_data["components"] if phase_e_data else None,
        "phase_e_tau":          phase_e_data["tau_components"] if phase_e_data else None,
        "caps_applied":         caps_applied,
    }

# ============================================================
# ORQUESTADOR PRINCIPAL
# ============================================================
def evaluate_signal(
    df_15m, df_1h, df_4h, df_1m,
    detect_pspace_fn, laplacian_check_fn, calculate_levels_fn,
    config, intra=False,
):
    """
    PUNTO DE ENTRADA UNICO. Sustituye evaluate_setup.

    Args:
        df_15m, df_1h, df_4h, df_1m: DataFrames con indicadores
        detect_pspace_fn, laplacian_check_fn, calculate_levels_fn: del bot
        config: dict con PHI, PMASTER_MIN, RR_MIN_TP_DIVINO

    Returns:
        (fire: bool, field: FieldState, decision_report: dict)
    """
    try:
        # 0. WEEKEND VETO (PRE-CHECK ABSOLUTO)
        if WEEKEND_VETO and kzpd.is_weekend_closed():
            wk = kzpd.weekend_status()
            empty_field = ict.FieldState()
            return False, empty_field, _build_report(
                decision="weekend_veto", failed_at="weekend",
                reason="Mercado cerrado ({} {:.1f}UTC) - veto fin de semana".format(
                    wk["weekday_label"], wk["hour_utc"]),
                weekend_status=wk,
            )

        # 1. CONSTRUIR FIELDSTATE
        masses = detect_pspace_fn(df_15m)
        lap = laplacian_check_fn(df_15m)
        field = ict.read_field(df_15m, df_1h, df_4h, df_1m, masses, lap)

        # 1.b Llenar fase D (killzone + hibrido)
        n_closed_v2 = ev.count_closed_v2_buckets() if hasattr(ev, "count_closed_v2_buckets") else 0
        kzpd.refine_field_timing(field, n_closed_v2, HYBRID_DECAY_N)

        # 2. SANITY CHECK
        actionable, reason = field.is_actionable()
        if not actionable:
            return False, field, _build_report(
                decision="silence", failed_at="pre_check", reason=reason,
                masses=masses, lap=lap
            )

        # 3. DIRECCION PROPUESTA POR EL CAMPO
        direction = field.propose_direction()
        if direction is None:
            return False, field, _build_report(
                decision="silence", failed_at="direction",
                reason="Campo sin direccion clara",
                masses=masses, lap=lap
            )

        # 3.b QTE pre-fusion (FQ v5.1 Phase E) - solo si flag ON
        # Corre con direction ya resuelta para evitar 2x calls o sesgo.
        # n_paths se toma del TF profile cuando esta presente (5m/15m/1h tunean
        # latencia vs precision) o cae al global FQ_PHASE_E_N_PATHS.
        qte_payload = None
        if EMERGENT_TIME_ENABLED and _QTE_AVAILABLE:
            try:
                n_paths_tf = config.get("PHASE_E_N_PATHS") or PHASE_E_QTE_N_PATHS
                qa = qt.quantum_analysis(
                    df_15m, direction=direction,
                    ict_module=ict,
                    n_paths=n_paths_tf, run_optimizer=False,
                )
                qte_payload = emergent_time.build_qte_payload_from_quantum_analysis(qa)
            except Exception as e:
                log.warning("QTE pre-fusion error: {}".format(e))
                qte_payload = None

        # 4. FASE A
        a = _execute_phase_a(field, direction)
        if not a["passed"]:
            return False, field, _build_report(
                decision="field_only", failed_at="A", failed_phase=a["phase"],
                reason=a["reason"], direction_inferred=direction,
                masses=masses, lap=lap
            )

        # 5. FASE B
        b = _execute_phase_b(field, direction)
        if not b["passed"]:
            return False, field, _build_report(
                decision="field_only", failed_at="B", failed_phase=b["phase"],
                reason=b["reason"], direction_inferred=direction,
                masses=masses, lap=lap
            )

        # 6. FASE C
        c = _execute_phase_c(field, direction)
        if not c["passed"]:
            return False, field, _build_report(
                decision="field_only", failed_at="C", failed_phase=c["phase"],
                reason=c["reason"], direction_inferred=direction,
                masses=masses, lap=lap
            )

        # 7. P_master provisional (necesario para tier en Fase D.3)
        p_provisional = PHI * field.w_effective * (1.0 if lap["active"] else 0.7)
        p_provisional *= 1 + (masses["count"] - 2) * 0.15
        p_provisional *= field.confluence_factor()

        # 8. FASE D (carga bucket memory)
        d = _execute_phase_d(field, direction, p_provisional, tf_id=config.get("TF_ID"))
        if not d["passed"]:
            return False, field, _build_report(
                decision="field_only", failed_at="D", failed_phase=d["phase"],
                reason=d["reason"], direction_inferred=direction,
                masses=masses, lap=lap
            )

        # 8.b FASE E - Sync gate emergente (FQ v5.1)
        # tau(t) = phi_clock * phi_memory * phi_horizon * phi_refractory
        # sync_score < 0.30 -> veto absoluto. Modulador continuo encima.
        # cooldown_minutes se toma del TF profile (5m=20, 15m=60, 1h=180) o
        # cae al default global COOLDOWN_REF_MINUTES.
        phase_e_data = None
        if EMERGENT_TIME_ENABLED and _QTE_AVAILABLE and qte_payload is not None:
            last_ts = config.get("LAST_SIGNAL_TS")
            delta_min = _compute_delta_minutes(last_ts)
            cooldown_tf = config.get("PHASE_E_COOLDOWN_MIN") or emergent_time.COOLDOWN_REF_MINUTES
            phase_e_data = emergent_time.compute_sync_score(
                field, field.bucket_memory, qte_payload, delta_min, direction,
                cooldown_minutes=cooldown_tf,
            )
            mods = emergent_time.sync_modulators(phase_e_data["sync_score"])
            log.info("PHASE_E tf=%s sync=%.3f tau=%.3f phi_c=%.2f phi_m=%.2f phi_h=%.2f phi_r=%.2f tier=%s",
                config.get("TF_ID", "?"),
                phase_e_data["sync_score"],
                phase_e_data["tau_components"]["tau"],
                phase_e_data["tau_components"]["phi_clock"],
                phase_e_data["tau_components"]["phi_memory"],
                phase_e_data["tau_components"]["phi_horizon"],
                phase_e_data["tau_components"]["phi_refractory"],
                mods["tier"]
            )
            if phase_e_data["sync_score"] < PHASE_E_VETO_LO:
                return False, field, _build_report(
                    decision="sync_veto", failed_at="E", failed_phase="E.veto",
                    reason="Phase E veto: sync={:.2f}<{:.2f}".format(
                        phase_e_data["sync_score"], PHASE_E_VETO_LO),
                    direction_inferred=direction,
                    phase_e=phase_e_data,
                    masses=masses, lap=lap
                )

        # 9. P_MASTER FINAL REFINADO
        pm_data = _compute_p_master_refined(field, direction, masses, lap, config, phase_e_data=phase_e_data)

        if pm_data["p_master"] < config["PMASTER_MIN"]:
            return False, field, _build_report(
                decision="math_below_threshold", failed_at="p_master",
                reason="P_master {:.2f}<{:.2f}".format(pm_data["p_master"],
                                                        config["PMASTER_MIN"]),
                direction_inferred=direction, p_master_data=pm_data,
                masses=masses, lap=lap
            )

        # 10. NIVELES + R:R
        levels = calculate_levels_fn(df_15m, direction)
        if levels["rr_tp3"] < config["RR_MIN_TP_DIVINO"]:
            return False, field, _build_report(
                decision="rr_insufficient", failed_at="rr",
                reason="R:R TP3={:.2f}<{:.2f}".format(levels["rr_tp3"],
                                                       config["RR_MIN_TP_DIVINO"]),
                direction_inferred=direction, p_master_data=pm_data,
                levels=levels, masses=masses, lap=lap
            )

        # 10.5 CONSTRAINTS §6 - P_master >= 7/10 (~2.965) para fire/broadcast
        # Default OFF en beta para no romper deploys actuales; enable con env.
        if ENFORCE_HIGH_GATE and pm_data["p_master"] < PMASTER_HIGH_GATE:
            return False, field, _build_report(
                decision="below_high_gate", failed_at="p_master_7_10",
                reason="CONSTRAINTS §6 - P_master {:.2f} < {:.2f} (7/10 minimo)".format(
                    pm_data["p_master"], PMASTER_HIGH_GATE),
                direction_inferred=direction, p_master_data=pm_data,
                levels=levels, masses=masses, lap=lap
            )

        # 11. CAPA ML v4.3 - scorer ensemble + regime (additivos, no afectan P_master)
        score_result = None
        regime_state = None
        if USE_SCORER and _ML_AVAILABLE:
            try:
                concepts_flags = pm_data.get("concepts", {})
                bm = pm_data.get("bucket_memory")
                kappa_stats = pm_data.get("kappa_stats")
                score_result = signal_scorer.evaluate(
                    df_15m, field, direction,
                    concepts_flags=concepts_flags,
                    kappa_stats=kappa_stats,
                    bucket_memory=bm,
                )
            except Exception as e:
                log.warning("scorer error: {}".format(e))
        if USE_REGIME and _ML_AVAILABLE:
            try:
                regime_state = regime_detector.detect_regime(df_15m)
            except Exception as e:
                log.warning("regime error: {}".format(e))

        # Si regime esta en deriva Y scorer < threshold high -> downgrade a no-fire
        if score_result and regime_state:
            if (regime_state["state"] == "deriva" and
                score_result["total_score"] < signal_scorer.ENSEMBLE_MIN_FOR_HIGHTIER):
                return False, field, _build_report(
                    decision="regime_deriva_block",
                    failed_at="regime",
                    reason="Regime DERIVA + scorer {:.2f}<{:.2f}".format(
                        score_result["total_score"],
                        signal_scorer.ENSEMBLE_MIN_FOR_HIGHTIER),
                    direction_inferred=direction, p_master_data=pm_data,
                    levels=levels, masses=masses, lap=lap,
                    score=score_result, regime=regime_state
                )

        # 12. SENAL ALINEADA - DISPARAR (con metadata ML adjunta para reports)
        return True, field, _build_report(
            decision="fire", direction=direction,
            p_master_data=pm_data, levels=levels,
            masses=masses, lap=lap,
            score=score_result, regime=regime_state
        )
    except Exception as e:
        log.error("evaluate_signal: {}\n{}".format(e, traceback.format_exc()))
        empty_field = ict.FieldState()
        return False, empty_field, _build_report(
            decision="error", reason="EXCEPTION: " + str(e)[:120]
        )

def _build_report(decision, **kwargs):
    return {
        "decision": decision,
        "ts": datetime.now(timezone.utc).isoformat(),
        **kwargs,
    }
