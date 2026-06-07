# -*- coding: utf-8 -*-
"""
================================================================================
  BT FEATURES - capa de integracion: replay del motor REAL sobre histgrico
  by RasDG_Sol + Claude

  El puente entre el harness de research y el motor en vivo. Recorre las velas
  historicas y, en cada una, reconstruye las ventanas multi-TF y llama al MISMO
  fusion_engine.evaluate_signal que el bot usa en produccion. Cuando el motor
  DISPARA, registra un evento (entry/sl/target/direction) + las features que el
  motor calculo (p_master, scorer, regime, atributos del field). Asi el dataset
  de research ve EXACTAMENTE lo que ve el bot, no datos sinteticos.

  Salida -> bt_labeler.label_events (etiqueta) -> bt_walkforward -> bt_engine /
  bt_train / bt_ablation.

  Diseno testeable: el loop de replay recibe `evaluate_fn` por parametro
  (default: fusion_engine.evaluate_signal) y las funciones del monolito
  (detect_pspace/laplacian_check/calculate_levels) tambien. En tests se inyecta
  un evaluate_fn falso -> se prueba el cableado sin importar el monolito ni red.
  El runner real (tools/run_research_real.py) inyecta las funciones de verdad.
================================================================================
"""
import logging

import numpy as np
import pandas as pd

log = logging.getLogger("bt_features")

LONG = 1
SHORT = -1

_DIR_MAP = {"long": LONG, "short": SHORT, LONG: LONG, SHORT: SHORT}


# ============================================================
# ALINEACION MULTI-TF (causal: solo pasado <= ts)
# ============================================================
def htf_window(df_htf, ts, tail=None):
    """Devuelve las filas de un TF superior con timestamp <= ts (causal: nunca
    mira velas futuras). `tail` recorta a las ultimas N para acotar coste.

    df_htf: DataFrame con columna 'timestamp' (datetime). Puede ser None.
    """
    if df_htf is None or len(df_htf) == 0:
        return df_htf
    mask = df_htf["timestamp"].to_numpy() <= np.datetime64(ts)
    win = df_htf[mask]
    if tail is not None and len(win) > tail:
        win = win.iloc[-tail:]
    return win


# ============================================================
# EXTRACCION DE FEATURES (pura: lee field + report)
# ============================================================
def extract_features(field, report):
    """Aplana en un dict las features que el motor ya computo para esta senal.

    Defensivo: usa getattr/.get con fallbacks, porque distintos paths del motor
    pueblan distintos sub-dicts. Devuelve solo numeros/categorias planas, listas
    para alimentar el GBM (bt_train) y las mascaras de ablacion.
    """
    f = {}

    pm = report.get("p_master_data") or {}
    f["p_master"] = pm.get("p_master")
    f["p_master_raw"] = pm.get("p_master_raw")
    f["p_master_pre_vol"] = pm.get("p_master_pre_vol")

    score = report.get("score") or {}
    f["scorer_total"] = score.get("total_score")
    # breakdown de signal_scorer.evaluate es una LISTA de dicts
    # {"name","score","weight","contribution","detail"}. Tambien aceptamos un
    # dict {name: score} por robustez.
    breakdown = score.get("breakdown") or []
    by_name = {}
    if isinstance(breakdown, dict):
        by_name = breakdown
    else:
        for item in breakdown:
            if isinstance(item, dict) and "name" in item:
                by_name[item["name"]] = item.get("score")
    for k in ("volume", "structure", "liquidity", "concept_stack", "history"):
        v = by_name.get(k)
        f["scorer_" + k] = v.get("score") if isinstance(v, dict) else v

    regime = report.get("regime") or {}
    f["regime_state"] = regime.get("state")
    f["regime_score"] = regime.get("score")

    # Atributos del FieldState (lo que ve el motor estructuralmente).
    for attr in ("confluence_count", "pd_pct", "w_effective", "node_type",
                 "killzone", "killzone_priority", "bias_4h", "bias_1h",
                 "choch", "has_fuel"):
        f["field_" + attr] = getattr(field, attr, None)

    return f


def _numeric_feature_columns(events):
    """Columnas de features estrictamente numericas (para el modelo)."""
    cols = []
    for c in events.columns:
        if not c.startswith(("p_master", "scorer_", "regime_score",
                             "field_confluence", "field_pd_pct",
                             "field_w_effective")):
            continue
        if pd.api.types.is_numeric_dtype(events[c]):
            cols.append(c)
    return cols


# ============================================================
# REPLAY DEL MOTOR SOBRE HISTORICO
# ============================================================
def replay_events(
    df_15m, df_1h, df_4h, df_1m,
    evaluate_fn,
    detect_pspace_fn, laplacian_check_fn, calculate_levels_fn,
    config,
    min_lookback=200,
    step=1,
    htf_tail=300,
    sub_tail=120,
    target_level="tp1",
    enrich_fn=None,
    progress_every=0,
):
    """Recorre df_15m y dispara el motor en cada vela; registra los FIRE.

    df_15m: DataFrame OHLCV+indicadores del TF primario (con 'timestamp').
    df_1h/df_4h/df_1m: contexto/sub-TF (con 'timestamp'); pueden ser None.
    evaluate_fn: callable con la firma de fusion_engine.evaluate_signal:
        (df_15m, df_1h, df_4h, df_1m, detect_pspace_fn, laplacian_check_fn,
         calculate_levels_fn, config) -> (fire, field, report)
    config: dict de config del motor (PHI, PMASTER_MIN, RR_MIN_TP_DIVINO, ...).
    min_lookback: no evalua hasta tener al menos estas velas de 15m.
    step: evaluar 1 de cada `step` velas (1 = todas).
    htf_tail/sub_tail: recorte de ventanas HTF/sub para acotar coste.
    target_level: nivel de levels usado como barrera de TP ("tp1" por defecto;
        toca TP1 = win, igual que el ledger).
    enrich_fn: opcional callable(field, report, win15, direction) -> dict extra
        (p.ej. volumen/session_bias/sync calculados aparte) para mas features.

    Devuelve un DataFrame de eventos: una fila por senal disparada, con
    entry_index (posicion en df_15m), entry_price, stop_price, target_price,
    direction (+1/-1) + features. Listo para bt_labeler.label_events(df_15m, ...).
    """
    n = len(df_15m)
    ts_col = df_15m["timestamp"].to_numpy()
    events = []

    for i in range(min_lookback, n, step):
        if progress_every and i % progress_every == 0:
            log.info("replay %d/%d eventos=%d", i, n, len(events))

        ts = ts_col[i]
        win15 = df_15m.iloc[: i + 1]
        win1h = htf_window(df_1h, ts, tail=htf_tail)
        win4h = htf_window(df_4h, ts, tail=htf_tail)
        win1m = htf_window(df_1m, ts, tail=sub_tail)

        try:
            fire, field, report = evaluate_fn(
                win15, win1h, win4h, win1m,
                detect_pspace_fn, laplacian_check_fn, calculate_levels_fn,
                config,
            )
        except Exception as e:
            log.warning("evaluate_fn fallo en i=%d: %s", i, e)
            continue

        if not fire or report.get("decision") != "fire":
            continue

        direction = _DIR_MAP.get(report.get("direction"))
        levels = report.get("levels") or {}
        entry = levels.get("entry")
        stop = levels.get("sl")
        target = levels.get(target_level)
        if direction is None or entry is None or stop is None or target is None:
            log.warning("fire sin niveles completos en i=%d (skip)", i)
            continue

        row = {
            "entry_index": i,
            "entry_ts": pd.Timestamp(ts),
            "entry_price": float(entry),
            "stop_price": float(stop),
            "target_price": float(target),
            "direction": direction,
            "tp3": levels.get("tp3"),
            "rr_tp3": levels.get("rr_tp3"),
            # Precios de los targets: permiten reetiquetar tp1..tp4 desde un solo
            # replay (el replay es lo caro; el TP solo cambia el label). OJO: en el
            # motor (calculate_levels) tp3 = entry + rng*PHI_INV, IDENTICO a tp2 ->
            # px_tp3 == px_tp2 (la frontera lo refleja: filas tp2 y tp3 iguales).
            # px_tp4 = entry + rng (rng/risk en R) es el unico target lejano REAL
            # disponible para el test de alcance hasta que se corrija tp3 en el motor.
            "px_tp1": levels.get("tp1"),
            "px_tp2": levels.get("tp2"),
            "px_tp3": levels.get("tp3"),
            "px_tp4": levels.get("tp4"),
        }
        row.update(extract_features(field, report))
        if enrich_fn is not None:
            try:
                row.update(enrich_fn(field, report, win15, direction) or {})
            except Exception as e:
                log.warning("enrich_fn fallo en i=%d: %s", i, e)
        events.append(row)

    return pd.DataFrame(events)
