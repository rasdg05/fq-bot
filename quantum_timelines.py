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

import qte_verdict  # veredicto canonico compartido con la superficie VIP

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

# Ventana de tiempo emergente (horizonte adaptativo) ---------------------------
# El horizonte deja de ser un 24h fijo: se sustenta en estructura real (cuanto
# tarda el precio en recorrer la distancia hasta el TP mas lejano a la velocidad
# tipica del ATR) y se modula por el tiempo universal del momento (killzone /
# sesion activa). Asi la ventana mostrada al VIP refleja el contexto real y no
# una promesa hardcodeada que se evapora cuando cambia el momentum.
HORIZON_MIN_CANDLES     = 24      # 6h  piso: no proyectar ventanas absurdamente cortas
HORIZON_MAX_CANDLES     = 160     # 40h techo: no prometer ventanas multi-dia
HORIZON_PATH_EFFICIENCY = 0.40    # avance neto direccional como fraccion del ATR/vela
HORIZON_MEANDER_MARGIN  = 1.30    # colchon: el precio rara vez avanza en linea recta
HORIZON_SESSION_REF_W   = 1.00    # peso killzone de referencia (neutro)
HORIZON_SESSION_FMIN    = 0.70    # killzone fuerte (Silver Bullet) -> ventana mas corta
HORIZON_SESSION_FMAX    = 1.50    # asia / fuera de KZ -> ventana mas larga

# HORIZON_MIN/MAX_CANDLES y DEFAULT_HORIZON estan calibrados asumiendo velas de
# 15m (6h-40h reales). `candle_minutes` (parametro de adaptive_horizon/
# quantum_analysis, default 15 = comportamiento historico) reescala esos pisos/
# techos a velas reales cuando el caller opera en otro TF (p.ej. 5m), para que
# el horizonte siga representando las mismas horas reales sin importar la vela.
DEFAULT_CANDLE_MINUTES  = 15

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
# PROBABILIDADES P(TP_i) vs P(SL)  -  vectorizado (numpy)
# ============================================================
def compute_tp_sl_probabilities(paths, entry, sl, tp_list, direction):
    """
    Version vectorizada del calculo de primer-paso TP/SL sobre los N paths.

    Para cada path, en orden temporal:
      - SL primero  -> R = -1.0
      - TP1 primero -> R = (tp1-entry)/risk  (el TP mas cercano; ver nota)
      - sin toque en el horizonte -> timeout, R = (final-entry)/risk

    Paridad EXACTA con _compute_tp_sl_probabilities_loop (oraculo del self-test):
    SL y TP1 son mutuamente excluyentes en un mismo precio (long: sl<entry<tp1),
    asi que el orden "SL antes que TP" del loop nunca cambia un resultado. Como el
    loop hace break en el primer TP tocado (el mas cercano), p_tp2/p_tp3 son 0.0 y
    se preservan asi por compatibilidad. Para una medida util de los targets
    lejanos se AÑADEN p_reach_tp1/2/3 = P(tocar TPk antes que SL).

    paths: shape (n_paths, horizon+1)
    Returns: mismas keys que la version loop + p_reach_tp1/2/3.
    """
    n_paths, _ = paths.shape
    risk = abs(entry - sl)
    if risk <= 0:
        return {"p_sl": 0, "p_tp1": 0, "p_tp2": 0, "p_tp3": 0, "p_tp4": 0,
                "expected_R": 0, "win_rate": 0, "p_timeout": 1,
                "p_reach_tp1": 0.0, "p_reach_tp2": 0.0, "p_reach_tp3": 0.0}

    is_long = direction == "long"
    tps_sorted = sorted(tp_list) if is_long else sorted(tp_list, reverse=True)

    fut = paths[:, 1:]          # (N, H); col 0 == barra t=1 (== loop range(1,len))
    H = fut.shape[1]

    def _first_idx(hit):
        """Indice del primer True por fila; H (centinela "nunca") si all-False."""
        any_hit = hit.any(axis=1)
        idx = np.where(any_hit, hit.argmax(axis=1), H)
        return idx, any_hit

    if is_long:
        sl_hit  = fut <= sl
        tp1_hit = fut >= tps_sorted[0]
        tp2_hit = (fut >= tps_sorted[1]) if len(tps_sorted) > 1 else np.zeros_like(sl_hit)
        tp3_hit = (fut >= tps_sorted[2]) if len(tps_sorted) > 2 else np.zeros_like(sl_hit)
    else:
        sl_hit  = fut >= sl
        tp1_hit = fut <= tps_sorted[0]
        tp2_hit = (fut <= tps_sorted[1]) if len(tps_sorted) > 1 else np.zeros_like(sl_hit)
        tp3_hit = (fut <= tps_sorted[2]) if len(tps_sorted) > 2 else np.zeros_like(sl_hit)

    sl_idx,  sl_any  = _first_idx(sl_hit)
    tp1_idx, tp1_any = _first_idx(tp1_hit)
    tp2_idx, tp2_any = _first_idx(tp2_hit)
    tp3_idx, tp3_any = _first_idx(tp3_hit)

    # Loop chequea SL antes que TP -> SL gana el empate (imposible en la practica)
    sl_first  = sl_any  & (sl_idx <= tp1_idx)
    tp1_first = tp1_any & (tp1_idx < sl_idx)
    timeout   = ~sl_first & ~tp1_first

    final = paths[:, -1]
    r = np.empty(n_paths, dtype=np.float64)
    r[sl_first]  = -1.0
    r[tp1_first] = abs(tps_sorted[0] - entry) / risk
    if is_long:
        r[timeout] = (final[timeout] - entry) / risk
    else:
        r[timeout] = (entry - final[timeout]) / risk

    n = float(n_paths)
    p_sl       = float(sl_first.sum())  / n
    p_tp1      = float(tp1_first.sum()) / n
    p_timeout  = float(timeout.sum())   / n
    expected_R = float(r.mean())
    win_rate   = p_tp1   # == sum(p_tps); p_tp2/p_tp3 son 0 igual que en el loop

    # P(tocar TPk antes que SL) - medida util de targets lejanos (aditiva).
    # Monotona por construccion (umbral mas lejano -> tpk_idx no-decreciente).
    p_reach_tp1 = float((tp1_any & (tp1_idx < sl_idx)).sum()) / n
    p_reach_tp2 = float((tp2_any & (tp2_idx < sl_idx)).sum()) / n
    p_reach_tp3 = float((tp3_any & (tp3_idx < sl_idx)).sum()) / n

    return {
        "p_sl":        p_sl,
        "p_timeout":   p_timeout,
        "expected_R":  expected_R,
        "win_rate":    win_rate,
        "p_tp1":       p_tp1,
        "p_tp2":       0.0,
        "p_tp3":       0.0,
        "p_tp4":       0.0,
        "p_reach_tp1": p_reach_tp1,
        "p_reach_tp2": p_reach_tp2,
        "p_reach_tp3": p_reach_tp3,
    }


def _first_true_idx(hit, sentinel):
    """Indice del primer True por fila (axis=1); `sentinel` si all-False."""
    any_hit = hit.any(axis=1)
    idx = np.where(any_hit, hit.argmax(axis=1), sentinel)
    return idx, any_hit


def evaluate_entry_zone(paths, zone_entry, zone_sl, tp_prices, direction):
    """
    Evalua la calidad de ENTRAR EN UNA ZONA (pullback / acumulacion) reutilizando
    los MISMOS paths Monte Carlo - sin re-simular. Responde la pregunta del
    trader: "es mas probable ganar si entro mas abajo en esta zona?".

    Para LONG, zone_entry suele estar < precio actual (paths[:,0]); mide:
      - reach_prob: fraccion de paths que TOCAN la zona dentro del horizonte
      - condicional (solo paths que tocan, desde el primer toque en adelante):
          p_sl_cond, ev_cond (R), p_reach_tp1_cond
      - median_bars_to_reach: mediana de velas hasta tocar la zona

    Devuelve dict. Si ningun path toca la zona, reach_prob=0 y condicionales None.
    """
    n_paths, _ = paths.shape
    is_long = direction == "long"
    fut = paths[:, 1:]                  # (N, H); col 0 == barra t=1
    H = fut.shape[1]
    cols = np.arange(H)[None, :]        # (1, H)

    # 1) Primer toque de la zona
    reach_hit = (fut <= zone_entry) if is_long else (fut >= zone_entry)
    reach_idx, reached = _first_true_idx(reach_hit, H)
    n_reached = int(reached.sum())
    reach_prob = n_reached / float(n_paths)
    if n_reached == 0:
        return {"reach_prob": 0.0, "n_reached": 0, "p_sl_cond": None,
                "ev_cond": None, "p_reach_tp1_cond": None,
                "median_bars_to_reach": None}

    # 2) Edge condicional desde el toque: solo barras en/after el primer toque
    risk = abs(zone_entry - zone_sl)
    after = cols >= reach_idx[:, None]          # (N, H)
    tps_sorted = sorted(tp_prices) if is_long else sorted(tp_prices, reverse=True)
    if is_long:
        sl_hit  = (fut <= zone_sl) & after
        tp1_hit = (fut >= tps_sorted[0]) & after
    else:
        sl_hit  = (fut >= zone_sl) & after
        tp1_hit = (fut <= tps_sorted[0]) & after
    sl_idx,  sl_any  = _first_true_idx(sl_hit, H)
    tp1_idx, tp1_any = _first_true_idx(tp1_hit, H)

    sl_first  = sl_any  & (sl_idx <= tp1_idx)
    tp1_first = tp1_any & (tp1_idx < sl_idx)
    timeout   = reached & ~sl_first & ~tp1_first

    final = paths[:, -1]
    r = np.zeros(n_paths, dtype=np.float64)
    if risk > 0:
        r[sl_first]  = -1.0
        r[tp1_first] = abs(tps_sorted[0] - zone_entry) / risk
        if is_long:
            r[timeout] = (final[timeout] - zone_entry) / risk
        else:
            r[timeout] = (zone_entry - final[timeout]) / risk

    nr = float(n_reached)
    return {
        "reach_prob":           reach_prob,
        "n_reached":            n_reached,
        "p_sl_cond":            float(sl_first.sum()) / nr,
        "ev_cond":              float(r[reached].mean()) if risk > 0 else 0.0,
        "p_reach_tp1_cond":     float(tp1_first.sum()) / nr,
        "median_bars_to_reach": float(np.median(reach_idx[reached] + 1)),
    }


def _compute_tp_sl_probabilities_loop(paths, entry, sl, tp_list, direction):
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
# CLASIFICACION DE REGIMENES  -  vectorizado (numpy)
# ============================================================
def classify_regimes(paths, entry, atr, meta=None):
    """
    Version vectorizada. Paridad EXACTA con _classify_regimes_loop (oraculo del
    self-test). Clasifica cada path en uno de REGIME_LIST y devuelve
    {regime: fraction} ordenado descendente (mismo desempate estable que el loop).
    """
    n_paths, _ = paths.shape
    anchors = (meta or {}).get("anchors", {})
    pool_h = anchors.get("pool_high_price")
    pool_l = anchors.get("pool_low_price")

    final = paths[:, -1]
    max_p = paths.max(axis=1)
    min_p = paths.min(axis=1)
    delta = final - entry
    crosses = (np.diff(np.sign(paths - entry), axis=1) != 0).sum(axis=1)

    is_bull = delta >= 1.0 * atr
    is_bear = delta <= -1.0 * atr
    mid = ~is_bull & ~is_bear

    false_n = np.zeros(n_paths, dtype=bool)
    # Nota: pool_h/pool_l pueden ser None -> usar mascara all-False (None no
    # hace broadcast). Se replican las sub-condiciones delta>0 / delta<0 del
    # loop para paridad exacta incluso con atr degenerado (<=0).
    touch_low  = (min_p <= pool_l) if pool_l is not None else false_n
    touch_high = (max_p >= pool_h) if pool_h is not None else false_n

    sweep_bull = is_bull & touch_low  & (delta > 0)
    sweep_bear = is_bear & touch_high & (delta < 0)

    if pool_h is not None and pool_l is not None:
        inside_range = (max_p < pool_h * 1.005) & (min_p > pool_l * 0.995)
        range_mask = mid & inside_range & (crosses >= 4)
    else:
        range_mask = false_n

    regime = np.select(
        [sweep_bull, is_bull, sweep_bear, is_bear, range_mask],
        ["sweep_and_reverse", "bull_continuation",
         "sweep_and_reverse", "bear_reversal", "range"],
        default="chop",
    )

    counts = {r: int(np.count_nonzero(regime == r)) for r in REGIME_LIST}
    n = float(n_paths)
    fractions = {r: counts[r] / n for r in REGIME_LIST}
    return dict(sorted(fractions.items(), key=lambda x: -x[1]))


def _classify_regimes_loop(paths, entry, atr, meta=None):
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
# VENTANA DE TIEMPO EMERGENTE - HORIZONTE ADAPTATIVO
# ============================================================
def _current_session_weight():
    """Peso de la killzone activa AHORA (tiempo universal). Import perezoso para
    no acoplar quantum_timelines a killzones_pd (self-tests siguen aislados)."""
    try:
        import killzones_pd
        kz = killzones_pd.current_killzone()
        w = _safe_float(kz.get("w_kz"), HORIZON_SESSION_REF_W)
        return w if w > 0 else HORIZON_SESSION_REF_W
    except Exception:
        return HORIZON_SESSION_REF_W


def adaptive_horizon(entry, atr, tp_far, session_w=None, default=DEFAULT_HORIZON,
                      candle_minutes=DEFAULT_CANDLE_MINUTES):
    """
    Horizonte (velas del TF fed) sustentado en estructura real + tiempo universal.

    1) Estructura: cuantas velas toma recorrer la distancia entry -> TP mas
       lejano a la velocidad neta tipica (ATR * eficiencia), con un colchon
       por el zigzag natural del precio.
    2) Tiempo universal: la killzone/sesion activa AHORA modula la urgencia.
       Killzone fuerte (Silver Bullet/London/NY open) -> momentum rapido ->
       ventana mas corta; Asia/fuera de KZ -> ventana mas larga.

    Devuelve int de velas acotado a [HORIZON_MIN_CANDLES, HORIZON_MAX_CANDLES]
    escalados por `candle_minutes` (default 15 = los bounds tal cual, 6h-40h).
    Si el caller opera en otro TF (p.ej. 5m), se reescala para seguir
    representando las MISMAS horas reales (72-480 velas de 5m, no 24-160).
    Si faltan datos, cae al default (96 velas de 15m-equivalente = 24h) sin
    romper.
    """
    atr_v = _safe_float(atr, 0.0)
    entry_v = _safe_float(entry, 0.0)
    tp_v = _safe_float(tp_far, 0.0)
    if atr_v <= 0 or entry_v <= 0 or tp_v <= 0:
        return default

    distance = abs(tp_v - entry_v)
    net_vel = atr_v * HORIZON_PATH_EFFICIENCY
    if distance <= 0 or net_vel <= 0:
        return default

    candles = (distance / net_vel) * HORIZON_MEANDER_MARGIN

    if session_w is None:
        session_w = _current_session_weight()
    sw = _safe_float(session_w, HORIZON_SESSION_REF_W)
    if sw > 0:
        factor = HORIZON_SESSION_REF_W / sw
        factor = max(HORIZON_SESSION_FMIN, min(HORIZON_SESSION_FMAX, factor))
        candles *= factor

    scale = DEFAULT_CANDLE_MINUTES / candle_minutes if candle_minutes else 1.0
    min_c = HORIZON_MIN_CANDLES * scale
    max_c = HORIZON_MAX_CANDLES * scale
    candles = max(min_c, min(max_c, candles))
    return int(round(candles))


def _farthest_tp(levels, entry, direction):
    """Distancia/precio del TP mas lejano declarado en levels (tp1..tp4)."""
    if not levels:
        return None
    far = None
    for k in ("tp1", "tp2", "tp3", "tp4"):
        v = levels.get(k)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if direction == "short":
            if v < entry and (far is None or v < far):
                far = v
        else:
            if v > entry and (far is None or v > far):
                far = v
    return far


# ============================================================
# ORQUESTADOR PRINCIPAL
# ============================================================
def quantum_analysis(df_15m, df_1h=None, df_4h=None, direction=None,
                     pspace=None, levels=None, ict_module=None,
                     n_paths=DEFAULT_N_PATHS_VIP, horizon=None,
                     seed=42, run_optimizer=True, return_paths=False,
                     adaptive=False, candle_minutes=DEFAULT_CANDLE_MINUTES):
    """
    Funcion publica principal del QTE.

    levels: dict con keys entry, sl, tp1, tp2, tp3 (de calculate_levels_v2).
            Si es None, usa proxies basicos del df.

    candle_minutes: minutos reales por vela de `df_15m` (default 15 =
    comportamiento historico). Solo afecta la conversion a horas
    (`horizon_hours`) y el reescalado de los pisos/techos del horizonte
    adaptativo -- si el caller opera en otro TF (p.ej. 5m), pasa
    candle_minutes=5 para que "Horizonte ~Nh" siga representando horas
    reales en vez de asumir velas de 15m.

    Returns: dict con probabilidades, regimenes, niveles optimizados (si aplica),
             coherencia y metadata.
    """
    t0 = time.perf_counter()

    if direction is None:
        direction = "long"
    if horizon is None:
        horizon = int(round(DEFAULT_HORIZON * DEFAULT_CANDLE_MINUTES / candle_minutes))

    # Ventana de tiempo emergente: si se pide, el horizonte se sustenta en
    # estructura real (distancia al TP mas lejano / velocidad ATR) y en el
    # tiempo universal del momento (killzone activa), en vez del 24h fijo.
    if adaptive and levels:
        try:
            feat = _extract_market_features(df_15m)
            tp_far = _farthest_tp(levels, feat["price"], direction)
            horizon = adaptive_horizon(feat["price"], feat["atr"], tp_far,
                                       candle_minutes=candle_minutes)
        except Exception as e:
            log.warning("adaptive_horizon fallo, uso default {}: {}".format(
                horizon, e))

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
    result = {
        "n_paths": n_paths,
        "horizon_candles": horizon,
        "horizon_hours": horizon * candle_minutes / 60,
        "elapsed_ms": elapsed_ms,
        "probabilities": probs,
        "regimes": regimes,
        "dominant_regime": dominant_regime,
        "dominant_regime_pct": dominant_pct,
        "coherence": coherence,
        # Veredicto canonico horneado aqui (direction conocida) para que admin,
        # VIP y la lectura de Claude lean la MISMA interpretacion del setup.
        "verdict": qte_verdict.compute(
            {"probabilities": probs, "regimes": regimes, "coherence": coherence},
            direction),
        "optimized_levels": optimized,
        "vs_baseline": vs_baseline,
        "anchors": meta["anchors"],
        # Precios finales de cada path (paths[:,-1]) para que /timelines no
        # tenga que re-simular 2000 paths solo para su histograma. Aditivo.
        "final_prices": paths[:, -1],
    }
    if return_paths:
        # Matriz completa (N, horizon+1) para que battle_planner evalue zonas de
        # entrada sobre los MISMOS paths. Solo bajo demanda (no infla otros calls).
        result["paths"] = paths
    return result


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
        # p_reach_tp* = P(tocar TPk antes que SL). p_tp2/p_tp3 quedaron en 0 por
        # el break del primer-paso; fallback a ellos por compat defensiva.
        p1=probs.get("p_reach_tp1", probs["p_tp1"]),
        p2=probs.get("p_reach_tp2", probs["p_tp2"]),
        ps=probs["p_sl"],
        ev=probs["expected_R"], coh=qa["coherence"],
    )


def build_qte_block_admin(qa, direction=None):
    """Bloque detallado admin con probabilidades, regimenes y veredicto.

    El veredicto sale de qte_verdict.compute() (misma fuente que la superficie
    VIP), preferentemente el horneado en qa["verdict"]; cae a recomputar si el
    qa no lo trae (p.ej. dicts sinteticos de test).

    NOTA: no usar el caracter '<' en este bloque. El mensaje se envia con
    parse_mode=HTML en Telegram y un '<' suelto (p.ej. 'P(TP2<SL)') se
    interpreta como apertura de tag y se traga todo el texto hasta el
    siguiente '>', corrompiendo el analisis completo.
    """
    probs = qa["probabilities"]
    regs_str = regimes_short_label(qa["regimes"])
    verdict = qa.get("verdict") or qte_verdict.compute(qa, direction)
    lines = [
        "QUANTUM TIMELINES ENGINE (QTE)",
        "  paths        {}".format(qa["n_paths"]),
        "  horizon      {} velas ({:.0f}h)".format(
            qa["horizon_candles"], qa["horizon_hours"]),
        "  elapsed      {:.0f} ms".format(qa["elapsed_ms"]),
        "  coherencia   {:.0%}  ({})".format(
            qa["coherence"], qte_verdict.coherence_label(qa["coherence"])),
        "",
        "PROBABILIDADES (sobre niveles propuestos):",
        "  {:<22s}{:>6.1%}".format("Toca SL primero", probs["p_sl"]),
        "  {:<22s}{:>6.1%}".format("Toca TP1 antes que SL", probs.get("p_reach_tp1", probs["p_tp1"])),
        "  {:<22s}{:>6.1%}".format("Toca TP2 antes que SL", probs.get("p_reach_tp2", probs["p_tp2"])),
        "  {:<22s}{:>6.1%}".format("Toca TP3 antes que SL", probs.get("p_reach_tp3", probs["p_tp3"])),
        "  {:<22s}{:>6.1%}  (timeout)".format("Cierra sin tocar", probs["p_timeout"]),
        "  {:<22s}{:>+6.2f} R".format("Valor esperado", probs["expected_R"]),
        "  {:<22s}{:>6.1%}".format("Win rate (TP1)", probs["win_rate"]),
        "",
        "REGIMENES (24h simuladas):",
        "  {}".format(regs_str),
        "  dominante: {} ({:.0%})".format(qa["dominant_regime"], qa["dominant_regime_pct"]),
    ]
    if qa.get("vs_baseline"):
        vb = qa["vs_baseline"]
        lines.extend([
            "",
            "OPTIMIZER (QAOA-inspired):",
            "  P(SL)  {:.1%} -> {:.1%}".format(vb["baseline_p_sl"], vb["optimized_p_sl"]),
            "  EV     {:+.2f}R -> {:+.2f}R  (delta {:+.2f}R)".format(
                vb["baseline_ev_R"], vb["optimized_ev_R"], vb["delta_R"]),
            "  {}".format(_optimizer_note(vb)),
        ])
    if verdict:
        lines.extend([
            "",
            "VEREDICTO QTE: {}".format(verdict["label"]),
            "  {}".format(verdict["admin_body"]),
        ])
    return "\n".join(lines)


def _optimizer_note(vb):
    """Interpreta el delta del optimizer en una frase (conecta el ajuste de
    niveles con el veredicto en vez de dejar dos lineas de numeros sueltas)."""
    delta = vb.get("delta_R", 0.0) or 0.0
    if delta >= 0.5:
        return "el motor mejora el EV ajustando SL/TP (vale la pena)"
    if delta >= 0.1:
        return "ajuste marginal de SL/TP"
    return "los niveles propuestos ya son cercanos al optimo"


# ============================================================
# SELF-TESTS  -  ejecutar con:  python quantum_timelines.py
# ============================================================
def _synth_paths(seed, n=400, horizon=DEFAULT_HORIZON, p0=100.0, vol=0.01):
    """Random walks sinteticos (sin clip). Solo para tests de paridad."""
    rng = np.random.default_rng(seed)
    shocks = rng.normal(0.0, vol, size=(n, horizon))
    walk = np.cumprod(1.0 + shocks, axis=1)
    paths = np.empty((n, horizon + 1), dtype=np.float64)
    paths[:, 0] = p0
    paths[:, 1:] = p0 * walk
    return paths


def _synth_df(n=200):
    """DataFrame minimo con las columnas que generate_paths necesita."""
    rng = np.random.default_rng(123)
    close = 100.0 + np.cumsum(rng.normal(0.0, 0.3, size=n))
    high = close + np.abs(rng.normal(0.0, 0.2, size=n))
    low = close - np.abs(rng.normal(0.0, 0.2, size=n))
    return pd.DataFrame({
        "close": close, "high": high, "low": low,
        "atr14": np.full(n, 0.5),
        "ema50": close, "ema200": close,
    })


def _run_self_tests():
    print("Running quantum_timelines self-tests...\n")

    # ---- Test 1: paridad compute_tp_sl_probabilities + p_reach -------------
    n_checks = 0
    for seed in [1, 7, 42, 99]:
        for direction in ["long", "short"]:
            paths = _synth_paths(seed)
            entry = 100.0
            if direction == "long":
                sl_configs = [entry - 1.5, entry - 0.6, entry - 5.0]
                tp_configs = [
                    [entry + 1, entry + 2, entry + 3],
                    [entry + 0.5, entry + 1.0, entry + 1.5],
                    [entry + 8, entry + 12, entry + 20],   # wide -> mucho timeout
                ]
            else:
                sl_configs = [entry + 1.5, entry + 0.6, entry + 5.0]
                tp_configs = [
                    [entry - 1, entry - 2, entry - 3],
                    [entry - 0.5, entry - 1.0, entry - 1.5],
                    [entry - 8, entry - 12, entry - 20],
                ]
            for sl in sl_configs:
                for tps in tp_configs:
                    vec = compute_tp_sl_probabilities(paths, entry, sl, tps, direction)
                    ref = _compute_tp_sl_probabilities_loop(paths, entry, sl, tps, direction)
                    for k in ("p_sl", "p_tp1", "p_tp2", "p_tp3", "p_tp4",
                              "p_timeout", "win_rate"):
                        assert abs(vec[k] - ref[k]) < 1e-12, \
                            "probs[{}] mismatch: {} vs {}".format(k, vec[k], ref[k])
                    assert np.isclose(vec["expected_R"], ref["expected_R"],
                                      atol=1e-9, rtol=0), \
                        "expected_R mismatch: {} vs {}".format(
                            vec["expected_R"], ref["expected_R"])
                    # p_reach: consistencia + monotonia
                    assert abs(vec["p_reach_tp1"] - vec["p_tp1"]) < 1e-12
                    assert vec["p_reach_tp1"] >= vec["p_reach_tp2"] - 1e-12
                    assert vec["p_reach_tp2"] >= vec["p_reach_tp3"] - 1e-12
                    n_checks += 1
    print("  [OK] compute_tp_sl_probabilities paridad + p_reach ({} configs)".format(n_checks))

    # ---- Test 2: guard risk<=0 --------------------------------------------
    g = compute_tp_sl_probabilities(_synth_paths(1), 100.0, 100.0,
                                    [101, 102, 103], "long")
    assert g["p_timeout"] == 1 and g["p_sl"] == 0
    assert g["p_reach_tp1"] == 0.0 and g["p_reach_tp2"] == 0.0 and g["p_reach_tp3"] == 0.0
    print("  [OK] guard risk<=0 (dict uniforme con p_reach)")

    # ---- Test 3: paridad classify_regimes (con/sin pools, atr variado) -----
    n_reg = 0
    for seed in [1, 7, 42, 99]:
        paths = _synth_paths(seed)
        entry = 100.0
        for atr in [0.5, 1.0, 2.0]:
            for meta in [
                None,
                {"anchors": {"pool_high_price": 103.0, "pool_low_price": 97.0}},
                {"anchors": {"pool_high_price": None, "pool_low_price": 98.5}},
                {"anchors": {"pool_high_price": 101.5, "pool_low_price": None}},
            ]:
                v = classify_regimes(paths, entry, atr, meta)
                r = _classify_regimes_loop(paths, entry, atr, meta)
                assert list(v.keys()) == list(r.keys()), \
                    "regime order mismatch: {} vs {}".format(list(v.keys()), list(r.keys()))
                for k in REGIME_LIST:
                    assert abs(v[k] - r[k]) < 1e-12, \
                        "regime[{}] mismatch: {} vs {}".format(k, v[k], r[k])
                n_reg += 1
    print("  [OK] classify_regimes paridad ({} configs)".format(n_reg))

    # ---- Test 4: all-False (nada se toca -> todo timeout) ------------------
    flat = np.full((100, DEFAULT_HORIZON + 1), 100.0)
    af = compute_tp_sl_probabilities(flat, 100.0, 90.0, [110, 120, 130], "long")
    assert abs(af["p_timeout"] - 1.0) < 1e-12 and af["p_sl"] == 0.0 and af["p_tp1"] == 0.0
    print("  [OK] all-False -> p_timeout=1")

    # ---- Test 5: integracion quantum_analysis (final_prices + keys) --------
    df = _synth_df(200)
    qa = quantum_analysis(df, direction="long", n_paths=300, run_optimizer=True)
    assert "final_prices" in qa and len(qa["final_prices"]) == 300
    for k in ("p_sl", "p_tp1", "p_tp2", "p_tp3", "expected_R", "win_rate",
              "p_reach_tp1", "p_reach_tp2", "p_reach_tp3"):
        assert k in qa["probabilities"], "quantum_analysis falta key {}".format(k)
    print("  [OK] quantum_analysis devuelve final_prices + p_reach")

    # ---- Test 6: evaluate_entry_zone (reach + edge condicional) ------------
    def _zone_loop(paths, zone, sl, tps, direction):
        """Oraculo lento para evaluate_entry_zone."""
        is_long = direction == "long"
        tps_s = sorted(tps) if is_long else sorted(tps, reverse=True)
        risk = abs(zone - sl)
        reached = 0; rs = []
        for path in paths:
            t_touch = None
            for t in range(1, len(path)):
                if (is_long and path[t] <= zone) or (not is_long and path[t] >= zone):
                    t_touch = t; break
            if t_touch is None:
                continue
            reached += 1
            outcome = None
            for t in range(t_touch, len(path)):
                p = path[t]
                if (is_long and p <= sl) or (not is_long and p >= sl):
                    outcome = -1.0; break
                if (is_long and p >= tps_s[0]) or (not is_long and p <= tps_s[0]):
                    outcome = abs(tps_s[0]-zone)/risk; break
            if outcome is None:
                outcome = (path[-1]-zone)/risk if is_long else (zone-path[-1])/risk
            rs.append(outcome)
        n = len(paths)
        if reached == 0:
            return 0.0, None, None
        return reached/float(n), sum(1 for x in rs if x==-1.0)/float(reached), sum(rs)/float(reached)

    nz = 0
    for seed in [1, 42, 99]:
        for direction in ["long", "short"]:
            paths = _synth_paths(seed, vol=0.012)
            entry = 100.0
            if direction == "long":
                zones = [(99.0, 98.0, [101, 102, 103]), (97.0, 96.0, [100.5, 102, 104])]
            else:
                zones = [(101.0, 102.0, [99, 98, 97]), (103.0, 104.0, [99.5, 98, 96])]
            for zone, sl, tps in zones:
                ez = evaluate_entry_zone(paths, zone, sl, tps, direction)
                rp_ref, psl_ref, ev_ref = _zone_loop(paths, zone, sl, tps, direction)
                assert abs(ez["reach_prob"] - rp_ref) < 1e-12, "reach_prob mismatch"
                assert 0.0 <= ez["reach_prob"] <= 1.0
                if ez["n_reached"] > 0:
                    assert abs(ez["p_sl_cond"] - psl_ref) < 1e-12, "p_sl_cond mismatch"
                    assert np.isclose(ez["ev_cond"], ev_ref, atol=1e-9, rtol=0), "ev_cond mismatch"
                nz += 1
    # zona mas profunda -> reach_prob menor o igual (mas dificil de alcanzar)
    p = _synth_paths(7, vol=0.012)
    near = evaluate_entry_zone(p, 99.0, 98.0, [101, 102], "long")["reach_prob"]
    far  = evaluate_entry_zone(p, 96.0, 95.0, [101, 102], "long")["reach_prob"]
    assert near >= far - 1e-12, "zona profunda deberia ser menos alcanzable"
    print("  [OK] evaluate_entry_zone paridad + reach monotono ({} configs)".format(nz))

    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    _run_self_tests()
