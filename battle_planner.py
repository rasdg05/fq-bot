# -*- coding: utf-8 -*-
"""
================================================================================
  BATTLE PLANNER - FQ v5.x  (compañero de batalla intradia)
  by RasDG_Sol + Claude

  Convierte el campo ICT + las 2000 trayectorias del QTE en un VEREDICTO
  CERTERO y un plan de ejecucion accionable, no una entrada "raw".

  La pregunta que responde, en lenguaje de trader:
    "¿Opero ya, o es mas probable ganar acumulando mas abajo en tal Order Block /
     zona de liquidez? ¿Donde acumulo y donde se invalida?"

  Para cada zona candidata (OB, liquidez no barrida, FVG, EMA) en el lado
  favorable (descuento para long / premium para short) mide sobre los MISMOS
  paths simulados:
    - reach_prob: probabilidad de que el precio REGRESE a la zona
    - edge condicional desde la zona: P(SL), EV en R, P(tocar TP1)
  y la compara con entrar a mercado AHORA. Emite uno de:
    EJECUTAR_AHORA / ACUMULAR_EN_ZONA / ESPERAR_GATILLO / STAND_DOWN

  Modulo dependency-light: numpy + quantum_timelines. Duck-typea los objetos
  ICT (OB/FVG/pool) por atributos, sin importar ict_smc.
================================================================================
"""
import logging
import os
import numpy as np

import quantum_timelines as qt

log = logging.getLogger("battle_planner")

# ============================================================
# UMBRALES (tuneables)
# ============================================================
MIN_REACH_PROB_ZONE = 0.22   # no recomendar una zona que el precio casi no visita
EDGE_MARGIN_R       = 0.30   # la zona debe superar el EV de mercado por >= 0.30R
PSL_MARGIN          = 0.07   # ...o bajar P(SL) en >= 7 puntos
STRONG_EV_R         = 1.00   # EV de mercado para "ejecutar ya"
MAX_PSL_MARKET      = 0.35   # P(SL) maximo para "ejecutar ya"
DECENT_ZONE_EV_R    = 0.60   # EV minimo de zona para "esperar gatillo"
CHOP_DOMINANT_PCT   = 0.45   # chop dominante >= esto -> stand down
SL_BUFFER_ATR       = 0.30   # colchon anti stop-hunt bajo/sobre la zona
SWEEP_BUFFER_ATR    = 0.50   # colchon extra para entradas post-barrida

# Seleccion de zona (peticion RasDG, jun-2026): "el FVG me lo dio muy abajo".
# Causa: el score multiplicaba por reach_prob, y entre dos FVG en la direccion el
# MAS CERCANO al precio siempre tiene mayor reach_prob -> ganaba el mas bajo (un
# FVG viejo) en vez del FRESCO del ultimo displacement. El precio atravesaba la
# zona baja y pegaba el SL.
#   - reach_prob queda como GATE (MIN_REACH_PROB_ZONE), no como sesgo dominante.
#   - ZONE_REACH_BIAS atenua cuanto pesa reach_prob en el score (0 = ignora la
#     cercania y rankea puro por edge; 0.5 = comportamiento legacy). Default 0.35
#     = punto medio: corrige el sesgo a la zona baja sin premiar zonas lejanas
#     poco alcanzables.
#   - con empate de edge, gana el FVG mas FRESCO (ts mas reciente), no el mas
#     cercano.
ZONE_REACH_BIAS     = float(os.environ.get("FQ_ZONE_REACH_BIAS", "0.35"))
ZONE_FRESH_TIEBREAK = os.environ.get("FQ_ZONE_FRESH_TIEBREAK", "1").strip() in ("1", "true", "yes")


def _attr(obj, name, default=None):
    """getattr defensivo + float, tolerante a None."""
    if obj is None:
        return default
    v = getattr(obj, name, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def _zone_ts(ts):
    """Normaliza el ts de una zona a float comparable (recencia). 0.0 si no hay.

    Tolera epoch (int/float), pandas Timestamp/datetime, o None. Solo se usa como
    desempate de RECENCIA entre zonas del mismo tipo (FVGs), nunca como filtro.
    """
    if ts is None:
        return 0.0
    try:
        return float(ts)
    except (TypeError, ValueError):
        pass
    try:
        return float(ts.timestamp())
    except Exception:
        return 0.0


# ============================================================
# EXTRACCION DE ZONAS CANDIDATAS
# ============================================================
def extract_candidate_zones(direction, current_price, field_data, atr):
    """
    Devuelve lista de zonas candidatas en el lado favorable, cada una:
      {label, kind, low, high, ref, sl, needs_sweep}
    - long: zonas de DESCUENTO por debajo del precio (donde acumular comprando)
    - short: zonas PREMIUM por encima del precio
    `ref` = borde de la zona que el precio toca primero (top para long, low p/short).
    `sl`  = invalidacion estructural (bajo la zona para long).
    """
    is_long = direction == "long"
    zones = []
    fd = field_data or {}

    def add(label, kind, low, high, needs_sweep=False, ts=None):
        if low is None or high is None or low <= 0 or high <= 0:
            return
        low, high = float(min(low, high)), float(max(low, high))
        if is_long:
            # zona util solo si esta (mayormente) por debajo del precio actual
            if high >= current_price:
                return
            ref = high                      # borde superior: se toca primero
            sl = low - SL_BUFFER_ATR * atr
            if needs_sweep:
                sl = low - SWEEP_BUFFER_ATR * atr
        else:
            if low <= current_price:
                return
            ref = low                       # borde inferior: se toca primero
            sl = high + SL_BUFFER_ATR * atr
            if needs_sweep:
                sl = high + SWEEP_BUFFER_ATR * atr
        zones.append({"label": label, "kind": kind, "low": low, "high": high,
                      "ref": float(ref), "sl": float(sl), "needs_sweep": needs_sweep,
                      "ts": _zone_ts(ts)})

    # Order Block en la direccion (acumulacion prime, doctrina ICT)
    if is_long:
        ob = fd.get("ob_bullish")
        if ob is not None and getattr(ob, "still_valid", False):
            add("Order Block alcista", "OB", _attr(ob, "low"), _attr(ob, "high"))
    else:
        ob = fd.get("ob_bearish")
        if ob is not None and getattr(ob, "still_valid", False):
            add("Order Block bajista", "OB", _attr(ob, "low"), _attr(ob, "high"))

    # Liquidez no barrida (SSL para long / BSL para short) -> entrada post-barrida
    pool = fd.get("pool_low") if is_long else fd.get("pool_high")
    if pool is not None and not getattr(pool, "swept", True):
        pp = _attr(pool, "price")
        if pp is not None:
            half = 0.15 * atr
            add("Liquidez SSL (barrida+reclamo)" if is_long else "Liquidez BSL (barrida+reclamo)",
                "POOL", pp - half, pp + half, needs_sweep=True)

    # FVG en la direccion
    for f in (fd.get("fvgs") or []):
        fdir = getattr(f, "direction", None)
        if is_long and fdir == "bullish":
            add("FVG alcista", "FVG", _attr(f, "bottom"), _attr(f, "top"),
                ts=getattr(f, "ts", None))
        elif (not is_long) and fdir == "bearish":
            add("FVG bajista", "FVG", _attr(f, "bottom"), _attr(f, "top"),
                ts=getattr(f, "ts", None))

    # EMA50 dinamica (si esta en el lado favorable)
    ema50 = fd.get("ema50")
    if ema50 is not None:
        half = 0.10 * atr
        add("EMA50 dinamica", "EMA", ema50 - half, ema50 + half)

    return zones


# ============================================================
# ACUMULACION: sub-niveles dentro de la zona
# ============================================================
def _accumulation_levels(zone, direction):
    """Reparte la posicion dentro de la zona (mas size mas profundo/mejor precio)."""
    low, high = zone["low"], zone["high"]
    width = high - low
    if width <= 0 or zone["kind"] in ("POOL", "EMA"):
        # zona puntual: una sola entrada en ref
        return [{"price": zone["ref"], "weight_pct": 100}]
    if direction == "long":
        # top (toque) -> low (mejor precio)
        return [{"price": round(high, 4),            "weight_pct": 40},
                {"price": round((high + low) / 2, 4), "weight_pct": 35},
                {"price": round(low, 4),              "weight_pct": 25}]
    else:
        return [{"price": round(low, 4),             "weight_pct": 40},
                {"price": round((high + low) / 2, 4), "weight_pct": 35},
                {"price": round(high, 4),             "weight_pct": 25}]


# ============================================================
# SCORING + RANKING DE ZONAS  (puro y testeable)
# ============================================================
def _zone_score(ez):
    """Calidad compuesta de una zona: EV condicional penalizado por P(SL).

    reach_prob entra ATENUADO por ZONE_REACH_BIAS para NO sesgar a la zona mas
    cercana: antes (bias=0.5 implicito), entre dos FVG en la direccion el mas
    bajo (mayor reach_prob) le ganaba al FVG fresco del ultimo displacement. La
    alcanzabilidad real se filtra aparte con MIN_REACH_PROB_ZONE (gate).
    """
    edge = ez["ev_cond"] - ez["p_sl_cond"]
    return edge * ((1.0 - ZONE_REACH_BIAS) + ZONE_REACH_BIAS * ez["reach_prob"])


def _rank_zones(scored):
    """Ordena zonas por score y devuelve solo las alcanzables (gate de reach).

    Empate de score -> gana la mas FRESCA (ts reciente = ultimo displacement),
    NO la mas cercana. reach_prob queda como ultimo desempate.
    """
    if ZONE_FRESH_TIEBREAK:
        scored.sort(key=lambda z: (-z["score"], -z.get("ts", 0.0), -z["reach_prob"]))
    else:
        scored.sort(key=lambda z: (-z["score"], -z["reach_prob"]))
    return [z for z in scored if z["reach_prob"] >= MIN_REACH_PROB_ZONE]


# ============================================================
# ORQUESTADOR
# ============================================================
def build_battle_plan(direction, current_price, field_data, levels, paths, qa,
                      atr=None):
    """
    Construye el plan de batalla. Devuelve dict estructurado que consumen el
    formateador VIP y el prompt de Claude.

    paths: matriz (N, horizon+1) de quantum_analysis(..., return_paths=True)
    qa:    dict de quantum_analysis (regimen, coherencia, probs baseline)
    levels: dict de calculate_levels_v2 (entry, sl, tp_meta, atr, sl_anchor)
    """
    is_long = direction == "long"
    atr = float(atr if atr is not None else levels.get("atr") or (current_price * 0.005))

    # TPs = liquidez real ya calculada (precios fijos; mejor entrada => mejor R)
    tp_meta = levels.get("tp_meta") or []
    tp_prices = [t["price"] for t in tp_meta[:3]] if tp_meta else [
        levels.get("tp1"), levels.get("tp2"), levels.get("tp3")]
    tp_prices = [float(p) for p in tp_prices if p is not None]
    if len(tp_prices) < 3 and tp_prices:
        tp_prices = (tp_prices + [tp_prices[-1]] * 3)[:3]

    # --- Edge de entrar A MERCADO ahora (entrada del bot) ---
    mkt_entry = float(levels.get("entry", current_price))
    mkt_sl = float(levels.get("sl", mkt_entry - 1.5 * atr if is_long else mkt_entry + 1.5 * atr))
    mkt = qt.compute_tp_sl_probabilities(paths, mkt_entry, mkt_sl, tp_prices, direction) \
        if tp_prices else {"p_sl": 1.0, "expected_R": 0.0, "p_reach_tp1": 0.0}
    market = {"entry": mkt_entry, "sl": mkt_sl,
              "p_sl": mkt["p_sl"], "ev": mkt["expected_R"],
              "p_reach_tp1": mkt.get("p_reach_tp1", mkt.get("p_tp1", 0.0))}

    # --- Evaluar cada zona candidata sobre los MISMOS paths ---
    zones = extract_candidate_zones(direction, current_price, field_data, atr)
    scored = []
    for z in zones:
        if not tp_prices:
            continue
        ez = qt.evaluate_entry_zone(paths, z["ref"], z["sl"], tp_prices, direction)
        if ez["n_reached"] == 0 or ez["ev_cond"] is None:
            continue
        z2 = dict(z)
        z2.update(ez)
        z2["score"] = _zone_score(ez)
        z2["accumulate"] = _accumulation_levels(z, direction)
        scored.append(z2)
    reachable = _rank_zones(scored)
    best = reachable[0] if reachable else None

    # --- Contexto de regimen ---
    dom = qa.get("dominant_regime") if qa else None
    dom_pct = float(qa.get("dominant_regime_pct", 0.0)) if qa else 0.0
    chop_dominant = dom == "chop" and dom_pct >= CHOP_DOMINANT_PCT
    regime_contra = ((is_long and dom == "bear_reversal" and dom_pct >= CHOP_DOMINANT_PCT) or
                     ((not is_long) and dom == "bull_continuation" and dom_pct >= CHOP_DOMINANT_PCT))

    zone_beats_market = best is not None and (
        (best["ev_cond"] - market["ev"] >= EDGE_MARGIN_R) or
        (best["p_sl_cond"] <= market["p_sl"] - PSL_MARGIN))

    # --- VEREDICTO ---
    trigger = None
    if chop_dominant or regime_contra or (
            market["ev"] < 0 and (best is None or best["ev_cond"] < 0.5)):
        verdict = "STAND_DOWN"
    elif zone_beats_market:
        verdict = "ACUMULAR_EN_ZONA"
        if best["needs_sweep"]:
            side = "SSL" if is_long else "BSL"
            trigger = "barrida de {} ${:.2f} + reclamo".format(side, best["ref"])
    elif market["ev"] >= STRONG_EV_R and market["p_sl"] <= MAX_PSL_MARKET:
        verdict = "EJECUTAR_AHORA"
    elif best is not None and best["ev_cond"] >= DECENT_ZONE_EV_R:
        verdict = "ESPERAR_GATILLO"
        if best["needs_sweep"]:
            side = "SSL" if is_long else "BSL"
            trigger = "barrida de {} ${:.2f} + reclamo".format(side, best["ref"])
        else:
            trigger = "retroceso a {} ${:.2f}-${:.2f}".format(best["label"], best["low"], best["high"])
    else:
        verdict = "STAND_DOWN"

    emoji = {"EJECUTAR_AHORA": "🟢", "ACUMULAR_EN_ZONA": "🟡",
             "ESPERAR_GATILLO": "🟠", "STAND_DOWN": "🔴"}[verdict]

    # --- Invalidacion + headline + racional ---
    side_word = "LONG" if is_long else "SHORT"
    if verdict == "EJECUTAR_AHORA":
        invalidation = market["sl"]
        headline = "EJECUTA {} a mercado ~${:.2f}".format(side_word, market["entry"])
        rationale = "Mercado ya da edge: EV {:+.2f}R, P(SL) {:.0%}. Ningun retroceso mejora claramente.".format(
            market["ev"], market["p_sl"])
    elif verdict == "ACUMULAR_EN_ZONA":
        invalidation = best["sl"]
        headline = "ACUMULA {} en {} ${:.2f}-${:.2f}".format(
            side_word, best["label"], best["low"], best["high"])
        rationale = ("No persigas a mercado. P(regreso a zona) {:.0%}; desde ahi "
                     "EV {:+.2f}R vs {:+.2f}R a mercado y P(SL) {:.0%} vs {:.0%}.").format(
            best["reach_prob"], best["ev_cond"], market["ev"],
            best["p_sl_cond"], market["p_sl"])
    elif verdict == "ESPERAR_GATILLO":
        invalidation = best["sl"] if best else market["sl"]
        headline = "ARMADO {} - espera gatillo".format(side_word)
        rationale = "Ni mercado ni zona dan edge claro aun. Gatillo: {}.".format(
            trigger or "confirmacion (displacement/CHoCH)")
    else:  # STAND_DOWN
        invalidation = market["sl"]
        if chop_dominant:
            reason = "regimen chop dominante ({:.0%})".format(dom_pct)
        elif regime_contra:
            reason = "regimen {} contradice {}".format(dom, side_word)
        else:
            reason = "EV de mercado {:+.2f}R sin zona mejor".format(market["ev"])
        headline = "STAND DOWN - sin edge operable"
        rationale = "{}. Reengancha si hay barrida + displacement a favor.".format(reason)

    return {
        "verdict": verdict,
        "emoji": emoji,
        "direction": direction,
        "headline": headline,
        "rationale": rationale,
        "trigger": trigger,
        "market": market,
        "primary_zone": best,                 # None si EJECUTAR/STAND_DOWN sin zona
        "alt_zones": reachable[1:3],          # hasta 2 alternativas
        "tps": tp_prices,
        "invalidation": float(invalidation),
        "regime": dom,
        "regime_pct": dom_pct,
        "coherence": float(qa.get("coherence", 0.0)) if qa else 0.0,
    }


# ============================================================
# SELF-TESTS  -  python battle_planner.py
# ============================================================
class _FakeOB:
    def __init__(self, low, high, valid=True):
        self.low, self.high, self.still_valid = low, high, valid

class _FakePool:
    def __init__(self, price, swept=False):
        self.price, self.swept = price, swept

class _FakeFVG:
    def __init__(self, direction, bottom, top, ts=0):
        self.direction, self.bottom, self.top = direction, bottom, top
        self.ts = ts


def _trending_paths(seed, drift, n=2000, H=qt.DEFAULT_HORIZON, p0=100.0, vol=0.004):
    rng = np.random.default_rng(seed)
    steps = rng.normal(drift, vol, size=(n, H))
    paths = np.empty((n, H + 1)); paths[:, 0] = p0
    paths[:, 1:] = p0 * np.cumprod(1 + steps, axis=1)
    return paths


def _run_self_tests():
    print("Running battle_planner self-tests...\n")

    # Caso 1: precio 100, OB de descuento 96-97 con drift que primero baja.
    # Esperado: el plan reconoce una zona alcanzable y produce un veredicto valido.
    paths = _trending_paths(1, drift=-0.0005)   # leve bajada -> toca zonas debajo
    field = {"ob_bullish": _FakeOB(96.0, 97.0), "ema50": 95.0,
             "pool_low": _FakePool(95.5, swept=False), "fvgs": []}
    levels = {"entry": 100.0, "sl": 98.5, "atr": 1.0,
              "tp_meta": [{"price": 103.0, "kind": "BSL_target"},
                          {"price": 105.0, "kind": "fib_1272"},
                          {"price": 107.0, "kind": "fib_1618"}]}
    plan = build_battle_plan("long", 100.0, field, levels, paths,
                             qa={"dominant_regime": "bull_continuation",
                                 "dominant_regime_pct": 0.4, "coherence": 0.7}, atr=1.0)
    assert plan["verdict"] in ("EJECUTAR_AHORA", "ACUMULAR_EN_ZONA",
                               "ESPERAR_GATILLO", "STAND_DOWN")
    assert plan["emoji"] and plan["headline"] and plan["rationale"]
    assert isinstance(plan["invalidation"], float)
    # hay zonas de descuento -> deberia haber al menos una candidata evaluada
    zs = extract_candidate_zones("long", 100.0, field, 1.0)
    assert any(z["kind"] == "OB" for z in zs), "deberia extraer el OB de descuento"
    assert all(z["high"] < 100.0 for z in zs), "todas las zonas long < precio"
    print("  [OK] caso long descuento: veredicto={} zonas={}".format(plan["verdict"], len(zs)))

    # Caso 2: chop dominante -> STAND_DOWN
    plan2 = build_battle_plan("long", 100.0, field, levels, paths,
                              qa={"dominant_regime": "chop",
                                  "dominant_regime_pct": 0.6, "coherence": 0.4}, atr=1.0)
    assert plan2["verdict"] == "STAND_DOWN", plan2["verdict"]
    print("  [OK] chop dominante -> STAND_DOWN")

    # Caso 3: short premium (zonas arriba)
    field_s = {"ob_bearish": _FakeOB(103.0, 104.0), "ema50": 105.0,
               "pool_high": _FakePool(104.5, swept=False), "fvgs": []}
    levels_s = {"entry": 100.0, "sl": 101.5, "atr": 1.0,
                "tp_meta": [{"price": 97.0, "kind": "SSL_target"},
                            {"price": 95.0, "kind": "fib_1272"},
                            {"price": 93.0, "kind": "fib_1618"}]}
    zs_s = extract_candidate_zones("short", 100.0, field_s, 1.0)
    assert all(z["low"] > 100.0 for z in zs_s), "todas las zonas short > precio"
    plan3 = build_battle_plan("short", 100.0, field_s, levels_s, _trending_paths(2, 0.0005),
                              qa={"dominant_regime": "bear_reversal",
                                  "dominant_regime_pct": 0.4, "coherence": 0.7}, atr=1.0)
    assert plan3["direction"] == "short" and plan3["verdict"] in (
        "EJECUTAR_AHORA", "ACUMULAR_EN_ZONA", "ESPERAR_GATILLO", "STAND_DOWN")
    print("  [OK] caso short premium: veredicto={} zonas={}".format(plan3["verdict"], len(zs_s)))

    # Caso 4: acumulacion reparte 100%
    z = {"low": 96.0, "high": 97.0, "ref": 97.0, "kind": "OB"}
    acc = _accumulation_levels(z, "long")
    assert sum(a["weight_pct"] for a in acc) == 100
    print("  [OK] acumulacion suma 100%")

    # Caso 5: REGRESION FVG "muy abajo" (peticion RasDG). Dos FVG bajistas arriba:
    # uno FRESCO mas alto (ult. displacement) y uno VIEJO mas bajo/cercano. El
    # scoring legacy (bias 0.5) premiaba al bajo por mayor reach_prob; el fix lo
    # corrige. Numeros elegidos para que el legacy elija MAL y el nuevo bien.
    fresh_high = {"label": "FVG bajista", "kind": "FVG", "low": 102.0, "high": 103.0,
                  "ref": 102.0, "ts": 2000.0, "ev_cond": 2.00, "p_sl_cond": 0.40,
                  "reach_prob": 0.35}
    old_low    = {"label": "FVG bajista", "kind": "FVG", "low": 100.5, "high": 101.0,
                  "ref": 100.5, "ts": 1000.0, "ev_cond": 1.70, "p_sl_cond": 0.45,
                  "reach_prob": 0.75}
    # Comprobar que el legacy SI elegiria el bajo (demuestra que el caso es valido)
    def _legacy_score(ez):
        return (ez["ev_cond"] - ez["p_sl_cond"]) * (0.5 + 0.5 * ez["reach_prob"])
    assert _legacy_score(old_low) > _legacy_score(fresh_high), \
        "el caso debe reproducir el bug: legacy premia el FVG bajo"
    # Con el fix, el FVG fresco/alto gana
    scored = []
    for zc in (fresh_high, old_low):
        z2 = dict(zc); z2["score"] = _zone_score(zc); scored.append(z2)
    best = _rank_zones(scored)[0]
    assert best["ref"] == 102.0, \
        "fix debe elegir el FVG fresco/alto (ref=102), no el bajo. got ref={}".format(best["ref"])
    print("  [OK] FVG: fix elige el fresco/alto, no el mas cercano/bajo")

    # Caso 6: empate de score -> gana el mas FRESCO, no el de mayor reach
    a = {"label": "FVG bajista", "kind": "FVG", "ref": 105.0, "ts": 100.0,
         "score": 1.0, "reach_prob": 0.90}
    b = {"label": "FVG bajista", "kind": "FVG", "ref": 110.0, "ts": 500.0,
         "score": 1.0, "reach_prob": 0.40}
    best_tie = _rank_zones([a, b])[0]
    assert best_tie["ref"] == 110.0, "empate de score -> gana el ts mas reciente"
    print("  [OK] desempate por frescura (ts), no por cercania")

    # Caso 7: extract_candidate_zones propaga el ts del FVG
    field_ts = {"fvgs": [_FakeFVG("bearish", 102.0, 103.0, ts=12345.0)]}
    zs_ts = extract_candidate_zones("short", 100.0, field_ts, 1.0)
    fvg_zone = next(z for z in zs_ts if z["kind"] == "FVG")
    assert fvg_zone["ts"] == 12345.0, "la zona FVG debe llevar su ts. got {}".format(fvg_zone["ts"])
    print("  [OK] extract_candidate_zones propaga ts del FVG")

    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    _run_self_tests()
