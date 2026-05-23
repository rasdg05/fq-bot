# -*- coding: utf-8 -*-
"""
================================================================================
  QUANTUM TIMELINES ENGINE (QTE) - FQ v5.1 Mistral Emergent Time Edition
  by RasDG_Sol + Claude

  Motor probabilistico cuantico-inspirado. Simula N futuros posibles
  (Monte Carlo paths) bajo restricciones estructurales del mercado.
  Mide P(TP_i), P(SL), Valor Esperado en R, regimen dominante.

  CERO dependencias cuanticas reales (no qiskit, no dimod). Solo numpy
  + pandas. Performance objetivo: <1.5s con 500 paths en Railway.

  Mapeo cuantico clasico:
    superposicion        -> N paths Monte Carlo coexistiendo
    funcion de onda      -> distribucion empirica de paths
    Hamiltoniano         -> bias function: drift + vol + magnetic_pull
    annealing            -> sampling con temperatura decreciente (no usado v1)
    QAOA                 -> grid search sobre (SL, TP1, TP2, TP3) -> max EV
    colapso / medicion   -> seleccion del regimen modal del ensemble
    decoherencia         -> path divergence: uncertainty == std normalizada

  Modulo INERTE - no envia, no toca DB. Solo computa.
================================================================================
"""
import numpy as np
import pandas as pd
import logging
import time

log = logging.getLogger("quantum_timelines")

# ============================================================
# CONSTANTES - tuneables por env (futuro)
# ============================================================
DEFAULT_N_PATHS_VIP   = 500
DEFAULT_N_PATHS_ADMIN = 500    # 2000 cuando se invoque desde /timelines
DEFAULT_HORIZON       = 96      # 96 velas de 15m = 24h
SWEEP_BIAS_RADIUS     = 0.4     # multiplos de ATR para activar sweep_bias
SWEEP_REACTION_BARS   = 8       # ventana para considerar "reaccion" post-sweep
LIQUIDITY_PULL_GAIN   = 0.15    # fuerza maxima del jalon magnetico (% ATR)
DRIFT_EMA50_GAIN      = 0.03    # mean-reversion a EMA50 por paso
DRIFT_EMA200_GAIN     = 0.01    # drift secundario a EMA200
MIN_PATHS_FOR_OPTIM   = 200     # bajo eso, no optimizar

# Constraints del optimizer (heredados del plan)
OPT_MAX_P_SL          = 0.35    # rechazar setups con >35% prob de SL primero
OPT_MIN_EV_R          = 1.0     # rechazar setups con EV<1R
OPT_MIN_SL_ATR_MULT   = 0.5     # SL minimo 0.5 ATR del entry

# Regimenes posibles (orden importa para reporte)
REGIME_LIST = ["bull_continuation", "bear_reversal", "chop",
               "sweep_and_reverse", "range"]


# ============================================================
# GENERACION DE PATHS - el corazon del motor
# ============================================================
def _safe_float(x, default):
    """Devuelve float(x) si valido, sino default."""
    try:
        v = float(x)
        if np.isnan(v) or np.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _extract_market_features(df_15m):
    """
    Extrae features del estado actual para parametrizar la simulacion.
    Devuelve dict con todo lo que generate_paths necesita.
    """
    last = df_15m.iloc[-1]
    price = float(last["close"])
    atr = _safe_float(last.get("atr14"), price * 0.005)
    ema50 = _safe_float(last.get("ema50"), price)
    ema200 = _safe_float(last.get("ema200"), price)

    # Volatilidad normalizada: ATR/precio acotado
    vol_norm = max(0.002, min(0.05, atr / price))

    # Drift macro: si EMA50 > precio -> bias bearish (regression to mean)
    ema_pull = (ema50 - price) / price  # signed

    return {
        "price": price,
        "atr": atr,
        "vol_norm": vol_norm,
        "ema50": ema50,
        "ema200": ema200,
        "ema_pull": ema_pull,
    }


def _extract_structural_anchors(df_15m, ict_module=None):
    """
    Extrae niveles estructurales para el campo magnetico.
    Si ict_module esta disponible, usa sus detectores; sino fallback basico.
    """
    anchors = {
        "pool_high_price": None,
        "pool_high_swept": True,
        "pool_low_price": None,
        "pool_low_swept": True,
        "ob_bull_low": None,
        "ob_bull_valid": False,
        "ob_bear_high": None,
        "ob_bear_valid": False,
        "swing_high": None,
        "swing_low": None,
    }

    # Fallback basico siempre disponible
    anchors["swing_high"] = float(df_15m["high"].iloc[-50:].max())
    anchors["swing_low"] = float(df_15m["low"].iloc[-50:].min())

    if ict_module is not None:
        try:
            ph, pl = ict_module.find_pivots(df_15m)
            obs = ict_module.detect_order_blocks(df_15m)
            pool_h, pool_l, _ = ict_module.detect_liquidity_pools(df_15m, ph, pl)
            if pool_h is not None:
                anchors["pool_high_price"] = float(pool_h.price)
                anchors["pool_high_swept"] = bool(pool_h.swept)
            if pool_l is not None:
                anchors["pool_low_price"] = float(pool_l.price)
                anchors["pool_low_swept"] = bool(pool_l.swept)
            ob_b = obs.get("bullish")
            if ob_b is not None:
                anchors["ob_bull_low"] = float(ob_b.low)
                anchors["ob_bull_valid"] = bool(ob_b.still_valid)
            ob_e = obs.get("bearish")
            if ob_e is not None:
                anchors["ob_bear_high"] = float(ob_e.high)
                anchors["ob_bear_valid"] = bool(ob_e.still_valid)
        except Exception as e:
            log.warning("QTE structural anchors fallback: {}".format(e))

    return anchors


def _magnetic_pull(prices, anchors, atr):
    """
    Calcula el jalon magnetico de cada path hacia los pools/anchors no barridos.
    Vectorizado sobre prices (shape: n_paths,).
    Devuelve delta normalizado (fraccion del precio).
    """
    pull = np.zeros_like(prices)
    # Pool high no barrido tira hacia arriba con fuerza ~ 1/dist^2
    if anchors["pool_high_price"] and not anchors["pool_high_swept"]:
        target = anchors["pool_high_price"]
        dist = (target - prices) / atr  # en multiplos de ATR
        # solo jala si esta arriba (dist > 0)
        mask = dist > 0
        force = np.where(mask, LIQUIDITY_PULL_GAIN / (1 + dist ** 2), 0)
        pull += force
    if anchors["pool_low_price"] and not anchors["pool_low_swept"]:
        target = anchors["pool_low_price"]
        dist = (prices - target) / atr
        mask = dist > 0
        force = np.where(mask, -LIQUIDITY_PULL_GAIN / (1 + dist ** 2), 0)
        pull += force
    return pull


def _sweep_bias(prices, anchors, atr, rng):
    """
    Devuelve un kick estocastico extra cuando precio esta cerca de un pool
    no barrido (simula el stop hunt = barrida + reaccion).
    """
    kick = np.zeros_like(prices)
    radius = SWEEP_BIAS_RADIUS * atr
    if anchors["pool_high_price"] and not anchors["pool_high_swept"]:
        target = anchors["pool_high_price"]
        close_mask = np.abs(prices - target) < radius
        # 25% paths cercanos cazan el pool con prob 1
        roll = rng.random(prices.shape)
        cross = close_mask & (roll < 0.25)
        kick = np.where(cross, (target - prices + atr * 0.2) / prices, kick)
    if anchors["pool_low_price"] and not anchors["pool_low_swept"]:
        target = anchors["pool_low_price"]
        close_mask = np.abs(prices - target) < radius
        roll = rng.random(prices.shape)
        cross = close_mask & (roll < 0.25)
        kick = np.where(cross, (target - prices - atr * 0.2) / prices, kick)
    return kick


def generate_paths(df_15m, n_paths=DEFAULT_N_PATHS_VIP, horizon=DEFAULT_HORIZON,
                   ict_module=None, seed=None):
    """
    Genera matriz (n_paths, horizon+1) de precios futuros simulados.
    Cada path es un universo paralelo bajo restricciones estructurales.

    Returns:
        paths: np.ndarray shape (n_paths, horizon+1) - precios incluyendo entry
        meta: dict con features extraidas + anchors
    """
    rng = np.random.default_rng(seed)
    feat = _extract_market_features(df_15m)
    anchors = _extract_structural_anchors(df_15m, ict_module)

    p0 = feat["price"]
    atr = feat["atr"]
    vol_norm = feat["vol_norm"]
    ema_pull = feat["ema_pull"]

    paths = np.zeros((n_paths, horizon + 1), dtype=np.float64)
    paths[:, 0] = p0
    current = np.full(n_paths, p0, dtype=np.float64)

    # Hamiltonian = composicion de:
    #  - drift ema (mean reversion suave)
    #  - vol shock estocastico N(0, sigma)
    #  - magnetic pull a pools no barridos
    #  - sweep bias cerca de pools
    for t in range(horizon):
        # Vol shock por path: shock gaussiano calibrado al ATR
        shock = rng.normal(0.0, vol_norm, size=n_paths)

        # Drift suave a EMA50 (cada path tiene un poco de mean reversion)
        # current_pull es signed: si current > ema50, pull negativo
        ema_drift = -DRIFT_EMA50_GAIN * (current - feat["ema50"]) / current

        # Magnetic pull
        mag_pull = _magnetic_pull(current, anchors, atr)

        # Sweep bias
        sweep = _sweep_bias(current, anchors, atr, rng)

        # Composicion
        ret = shock + ema_drift + mag_pull + sweep
        current = current * (1.0 + ret)
        # Sanity: precio positivo, no explotar
        current = np.clip(current, p0 * 0.5, p0 * 1.5)
        paths[:, t + 1] = current

    meta = {
        "p0": p0,
        "atr": atr,
        "vol_norm": vol_norm,
        "anchors": anchors,
        "n_paths": n_paths,
        "horizon": horizon,
    }
    return paths, meta


# ============================================================
# PROBABILIDADES P(TP_i) vs P(SL)
# ============================================================
def compute_tp_sl_probabilities(paths, entry, sl, tp_list, direction):
    """
    Para cada path, en orden temporal:
      - Si toca SL primero -> SL hit
      - Si toca TP_i primero -> TP_i hit (con i el primero alcanzado)
      - Si no toca nada en el horizonte -> timeout

    paths: shape (n_paths, horizon+1)
    entry: float
    sl: float
    tp_list: list[float] (ordenados TP1 < TP2 < TP3 < ... para LONG)
    direction: "long" o "short"

    Returns: dict con probabilidades, EV en R y win_rate.
    """
    n_paths, _ = paths.shape
    risk = abs(entry - sl)
    if risk <= 0:
        return {"p_sl": 0, "p_tp1": 0, "p_tp2": 0, "p_tp3": 0,
                "expected_R": 0, "win_rate": 0, "p_timeout": 1}

    is_long = direction == "long"
    tps_sorted = sorted(tp_list) if is_long else sorted(tp_list, reverse=True)

    # Para cada path, encontrar primer evento
    sl_hits = 0
    tp_hits = [0] * len(tps_sorted)
    timeouts = 0
    r_outcomes = []

    for i in range(n_paths):
        path = paths[i]
        hit = None  # ("sl") o ("tp", idx)

        for t in range(1, len(path)):
            p = path[t]
            if is_long:
                if p <= sl:
                    hit = ("sl",)
                    break
                # Check TPs en orden (TP1 mas cercano primero)
                for j, tp in enumerate(tps_sorted):
                    if p >= tp:
                        hit = ("tp", j)
                        break
                if hit is not None and hit[0] == "tp":
                    break
            else:
                if p >= sl:
                    hit = ("sl",)
                    break
                for j, tp in enumerate(tps_sorted):
                    if p <= tp:
                        hit = ("tp", j)
                        break
                if hit is not None and hit[0] == "tp":
                    break

        if hit is None:
            timeouts += 1
            # outcome final: precio final vs entry, calculado en R
            final = path[-1]
            r = (final - entry) / risk if is_long else (entry - final) / risk
            r_outcomes.append(r)
        elif hit[0] == "sl":
            sl_hits += 1
            r_outcomes.append(-1.0)
        else:
            j = hit[1]
            tp_hits[j] += 1
            r = abs(tps_sorted[j] - entry) / risk
            r_outcomes.append(r)

    n = float(n_paths)
    p_sl = sl_hits / n
    p_timeout = timeouts / n
    p_tps = [tp_hits[i] / n for i in range(len(tps_sorted))]
    expected_R = float(np.mean(r_outcomes))
    win_rate = sum(p_tps)  # fraccion que tocaron al menos TP1

    result = {
        "p_sl": p_sl,
        "p_timeout": p_timeout,
        "expected_R": expected_R,
        "win_rate": win_rate,
    }
    for i in range(min(4, len(p_tps))):
        result["p_tp{}".format(i + 1)] = p_tps[i]
    # Asegurar 4 keys
    for i in range(len(p_tps), 4):
        result["p_tp{}".format(i + 1)] = 0.0

    return result


# ============================================================
# CLASIFICACION DE REGIMENES
# ============================================================
def classify_regimes(paths, entry, atr, meta=None):
    """
    Sobre los N paths, clasifica el resultado de cada uno:
      - bull_continuation: termina >= +1 ATR arriba del entry sin SL
      - bear_reversal:     termina >= +1 ATR abajo del entry
      - chop:              termina dentro de +-0.5 ATR con muchos cruces
      - sweep_and_reverse: barre pool y revierte
      - range:             oscila entre pool_low y pool_high

    Returns: dict {regime: fraction} ordenado descendente.
    """
    n_paths, horizon_plus = paths.shape
    counts = {r: 0 for r in REGIME_LIST}

    anchors = (meta or {}).get("anchors", {})
    pool_h = anchors.get("pool_high_price")
    pool_l = anchors.get("pool_low_price")

    for i in range(n_paths):
        path = paths[i]
        final = path[-1]
        max_p = path.max()
        min_p = path.min()
        delta_final = final - entry

        # Cruces sobre entry: cuantas veces el path cruza
        crosses = int(np.sum(np.diff(np.sign(path - entry)) != 0))

        regime = "chop"  # default

        if delta_final >= 1.0 * atr:
            # Verificar si toco pool_low primero (sweep_and_reverse bullish)
            if pool_l is not None and min_p <= pool_l and delta_final > 0:
                regime = "sweep_and_reverse"
            else:
                regime = "bull_continuation"
        elif delta_final <= -1.0 * atr:
            if pool_h is not None and max_p >= pool_h and delta_final < 0:
                regime = "sweep_and_reverse"
            else:
                regime = "bear_reversal"
        else:
            # Cerca del entry: distinguir chop de range
            if pool_h is not None and pool_l is not None:
                inside_range = (max_p < pool_h * 1.005 and min_p > pool_l * 0.995)
                if inside_range and crosses >= 4:
                    regime = "range"
                elif crosses >= 6:
                    regime = "chop"
                else:
                    regime = "chop"
            else:
                regime = "chop"

        counts[regime] += 1

    n = float(n_paths)
    fractions = {r: counts[r] / n for r in REGIME_LIST}
    sorted_fractions = dict(sorted(fractions.items(), key=lambda x: -x[1]))
    return sorted_fractions


# ============================================================
# QAOA-INSPIRED OPTIMIZER
# ============================================================
def optimize_sl_tp_qaoa(entry, atr, direction, sl_candidates, tp_grids,
                        paths, max_combos=125):
    """
    Grid search clasico (analogo simple a QAOA) sobre (sl, tp1, tp2, tp3).
    Reutiliza los paths ya simulados - NO re-simula.

    sl_candidates: list[float] (5-8 SLs candidatos del paso F1)
    tp_grids: list[list[float]] - [tp1_candidates, tp2_candidates, tp3_candidates]
              cada uno con 3-5 niveles

    Returns: dict con la mejor combinacion (sl, tp1, tp2, tp3, expected_R, p_sl)
             que cumpla constraints, o None si ninguna pasa.
    """
    best = None
    best_ev = -np.inf
    combos_tried = 0
    n_paths, _ = paths.shape

    is_long = direction == "long"

    for sl in sl_candidates:
        # SL minimo 0.5 ATR del entry
        if abs(entry - sl) < OPT_MIN_SL_ATR_MULT * atr:
            continue
        # SL en la direccion correcta
        if is_long and sl >= entry: continue
        if not is_long and sl <= entry: continue

        for tp1 in tp_grids[0]:
            if is_long and tp1 <= entry: continue
            if not is_long and tp1 >= entry: continue
            for tp2 in tp_grids[1]:
                if is_long and tp2 <= tp1: continue
                if not is_long and tp2 >= tp1: continue
                for tp3 in tp_grids[2]:
                    if is_long and tp3 <= tp2: continue
                    if not is_long and tp3 >= tp2: continue
                    combos_tried += 1
                    if combos_tried > max_combos:
                        break

                    probs = compute_tp_sl_probabilities(
                        paths, entry, sl, [tp1, tp2, tp3], direction)
                    if probs["p_sl"] > OPT_MAX_P_SL:
                        continue
                    if probs["expected_R"] < OPT_MIN_EV_R:
                        continue

                    if probs["expected_R"] > best_ev:
                        best_ev = probs["expected_R"]
                        best = {
                            "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3,
                            "expected_R": probs["expected_R"],
                            "p_sl": probs["p_sl"],
                            "p_tp1": probs["p_tp1"],
                            "p_tp2": probs["p_tp2"],
                            "p_tp3": probs["p_tp3"],
                            "win_rate": probs["win_rate"],
                        }

    return best


# ============================================================
# COHERENCIA (decoherence proxy)
# ============================================================
def compute_coherence(paths):
    """
    Coherencia = 1 - uncertainty.
    Uncertainty = std normalizada del cierre final / std esperado.
    """
    final_prices = paths[:, -1]
    initial = paths[0, 0]
    actual_std = float(np.std(final_prices))
    expected_std = float(np.std(paths[:, paths.shape[1] // 2]))
    if expected_std <= 0:
        return 0.5
    uncertainty = min(1.0, actual_std / (expected_std * 2.0))
    return max(0.0, 1.0 - uncertainty)


# ============================================================
# ORQUESTADOR PRINCIPAL
# ============================================================
def quantum_analysis(df_15m, df_1h=None, df_4h=None, direction=None,
                     pspace=None, levels=None, ict_module=None,
                     n_paths=DEFAULT_N_PATHS_VIP, horizon=DEFAULT_HORIZON,
                     seed=42, run_optimizer=True):
    """
    Funcion publica principal del QTE.

    levels: dict con keys entry, sl, tp1, tp2, tp3 (de calculate_levels_v2).
            Si es None, usa proxies basicos del df.

    Returns: dict con probabilidades, regimenes, niveles optimizados (si aplica),
             coherencia y metadata.
    """
    t0 = time.perf_counter()

    if direction is None:
        direction = "long"

    paths, meta = generate_paths(df_15m, n_paths=n_paths, horizon=horizon,
                                 ict_module=ict_module, seed=seed)

    if levels is None:
        # Fallback: usa entry=close, SL=close-1.5ATR, TPs= +1R +2R +3R
        entry = meta["p0"]
        atr = meta["atr"]
        if direction == "long":
            sl = entry - max(1.5 * atr, 0.015 * entry)
            tp1, tp2, tp3 = entry + atr, entry + 2 * atr, entry + 3 * atr
        else:
            sl = entry + max(1.5 * atr, 0.015 * entry)
            tp1, tp2, tp3 = entry - atr, entry - 2 * atr, entry - 3 * atr
        levels = {"entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3}

    entry = levels["entry"]
    sl = levels["sl"]
    tp1 = levels["tp1"]
    tp2 = levels["tp2"]
    tp3 = levels["tp3"]
    atr = meta["atr"]

    # Probabilidades baseline (niveles propuestos por F1)
    probs = compute_tp_sl_probabilities(paths, entry, sl, [tp1, tp2, tp3], direction)

    # Regimenes
    regimes = classify_regimes(paths, entry, atr, meta)
    dominant_regime = next(iter(regimes))  # primero del sorted dict
    dominant_pct = regimes[dominant_regime]

    # Coherencia
    coherence = compute_coherence(paths)

    # Optimizer (opcional)
    optimized = None
    vs_baseline = None
    if run_optimizer and n_paths >= MIN_PATHS_FOR_OPTIM:
        try:
            sl_cands = _build_sl_candidate_grid(entry, atr, direction, levels)
            tp_grids = _build_tp_candidate_grids(entry, atr, direction, levels)
            optimized = optimize_sl_tp_qaoa(
                entry, atr, direction, sl_cands, tp_grids, paths)
            if optimized:
                vs_baseline = {
                    "baseline_p_sl": probs["p_sl"],
                    "optimized_p_sl": optimized["p_sl"],
                    "baseline_ev_R": probs["expected_R"],
                    "optimized_ev_R": optimized["expected_R"],
                    "delta_R": optimized["expected_R"] - probs["expected_R"],
                }
        except Exception as e:
            log.warning("QTE optimizer error: {}".format(e))

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        "n_paths": n_paths,
        "horizon_candles": horizon,
        "horizon_hours": horizon * 15 / 60,
        "elapsed_ms": elapsed_ms,
        "probabilities": probs,
        "regimes": regimes,
        "dominant_regime": dominant_regime,
        "dominant_regime_pct": dominant_pct,
        "coherence": coherence,
        "optimized_levels": optimized,
        "vs_baseline": vs_baseline,
        "anchors": meta["anchors"],
    }


def _build_sl_candidate_grid(entry, atr, direction, levels):
    """5-8 SLs candidatos alrededor del SL propuesto por F1."""
    sl0 = levels["sl"]
    is_long = direction == "long"
    deltas_atr = [-0.5, -0.25, 0, 0.25, 0.5, 0.75]  # multiplos de ATR alrededor
    cands = []
    for d in deltas_atr:
        if is_long:
            # mover el SL hacia abajo (mas lejos del entry) = restar
            cand = sl0 - d * atr
            if cand < entry:
                cands.append(cand)
        else:
            cand = sl0 + d * atr
            if cand > entry:
                cands.append(cand)
    # quitar duplicados y devolver maximo 8
    return list(dict.fromkeys(round(c, 4) for c in cands))[:8]


def _build_tp_candidate_grids(entry, atr, direction, levels):
    """Para cada TP slot, 3-5 candidatos cerca del nivel F1 propuesto."""
    is_long = direction == "long"
    tp_grids = []
    for key in ("tp1", "tp2", "tp3"):
        tp0 = levels.get(key, entry)
        cands = []
        for d in [-0.5, -0.25, 0, 0.5, 1.0]:
            if is_long:
                c = tp0 + d * atr
                if c > entry:
                    cands.append(c)
            else:
                c = tp0 - d * atr
                if c < entry:
                    cands.append(c)
        tp_grids.append(list(dict.fromkeys(round(c, 4) for c in cands))[:5])
    return tp_grids


# ============================================================
# HELPERS DE FORMATEO (para consumo desde fq_bot)
# ============================================================
def regimes_short_label(regimes_dict):
    """
    Convierte el dict de regimenes a un string corto:
      'bull 42% / sweep 21% / chop 18%'
    """
    labels = {
        "bull_continuation": "bull",
        "bear_reversal":     "bear",
        "chop":              "chop",
        "sweep_and_reverse": "sweep",
        "range":             "range",
    }
    parts = []
    for k, v in regimes_dict.items():
        if v > 0.01:
            parts.append("{} {:.0%}".format(labels.get(k, k), v))
    return " / ".join(parts[:4])


def build_qte_block_vip(qa):
    """Bloque corto VIP con probabilidades QTE - estilo Mistral."""
    probs = qa["probabilities"]
    regs = qa["regimes"]
    return (
        "  ◆ Timelines simuladas: {n}\n"
        "  ▴ Bullish {bp}%  ▾ Bearish {brp}%  ◇ Sweep {sp}%\n"
        "  ◆ P(TP1) {p1:.0%}  P(TP2) {p2:.0%}  P(SL) {ps:.0%}\n"
        "  ◆ EV: {ev:+.2f}R    Coherencia: {coh:.0%}"
    ).format(
        n=qa["n_paths"],
        bp=int(regs.get("bull_continuation", 0) * 100),
        brp=int(regs.get("bear_reversal", 0) * 100),
        sp=int(regs.get("sweep_and_reverse", 0) * 100),
        p1=probs["p_tp1"], p2=probs["p_tp2"], ps=probs["p_sl"],
        ev=probs["expected_R"], coh=qa["coherence"],
    )


def build_qte_block_admin(qa):
    """Bloque detallado admin con regimenes + comparativa baseline vs optimized."""
    probs = qa["probabilities"]
    regs_str = "\n".join(
        "  {:18s} {:.1%}".format(k, v) for k, v in qa["regimes"].items()
    )
    lines = [
        "QUANTUM TIMELINES ENGINE (QTE)",
        "  paths        {}".format(qa["n_paths"]),
        "  horizon      {} velas ({:.0f}h)".format(
            qa["horizon_candles"], qa["horizon_hours"]),
        "  elapsed      {:.0f} ms".format(qa["elapsed_ms"]),
        "  coherence    {:.0%}".format(qa["coherence"]),
        "",
        "PROBABILIDADES (niveles F1):",
        "  P(SL)        {:.1%}".format(probs["p_sl"]),
        "  P(TP1)       {:.1%}".format(probs["p_tp1"]),
        "  P(TP2)       {:.1%}".format(probs["p_tp2"]),
        "  P(TP3)       {:.1%}".format(probs["p_tp3"]),
        "  P(timeout)   {:.1%}".format(probs["p_timeout"]),
        "  EV en R      {:+.2f}".format(probs["expected_R"]),
        "  Win rate     {:.1%}".format(probs["win_rate"]),
        "",
        "REGIMENES:",
        regs_str,
        "",
        "DOMINANTE: {} ({:.0%})".format(qa["dominant_regime"], qa["dominant_regime_pct"]),
    ]
    if qa.get("vs_baseline"):
        vb = qa["vs_baseline"]
        lines.extend([
            "",
            "OPTIMIZER (QAOA-inspired):",
            "  baseline P(SL)  {:.1%}".format(vb["baseline_p_sl"]),
            "  optim P(SL)     {:.1%}".format(vb["optimized_p_sl"]),
            "  baseline EV     {:+.2f}R".format(vb["baseline_ev_R"]),
            "  optim EV        {:+.2f}R".format(vb["optimized_ev_R"]),
            "  delta EV        {:+.2f}R".format(vb["delta_R"]),
        ])
    return "\n".join(lines)
