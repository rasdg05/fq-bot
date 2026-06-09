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

    # BLOQUE QUANTUM / TIEMPO EMERGENTE (Eje A) — magnitudes que el motor YA computa
    # en p_master_data y que codifican convicción adaptativa, excitación de campo y
    # tiempo complejo. Prefijo qt_ para agruparlas como bloque ablacionable.
    #   · convicción/entropía (siempre vivas): kappa_evo, alpha_hybrid, h_factor,
    #     f_confluence, f_ict, n_concepts
    #   · excitación de campo: vol_score, session_bias_mult
    #   · tiempo emergente (vivas SOLO con FQ_EMERGENT_TIME_ENABLED=1; si no, son
    #     constantes/None): sync_score, sigma_tau
    f["qt_kappa_evo"]         = pm.get("kappa_evo")
    f["qt_alpha_hybrid"]      = pm.get("alpha_hybrid")
    f["qt_h_factor"]          = pm.get("h_factor")
    f["qt_f_confluence"]      = pm.get("f_confluence")
    f["qt_f_ict"]             = pm.get("f_ict")
    f["qt_n_concepts"]        = pm.get("n_concepts")
    f["qt_vol_score"]         = pm.get("vol_score")
    f["qt_session_bias_mult"] = pm.get("session_bias_mult")
    f["qt_sync_score"]        = pm.get("sync_score")
    f["qt_sigma_tau"]         = pm.get("sigma_tau")

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
    on_bar=None,
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
        if on_bar is not None:
            on_bar(ts)   # inyecta la hora del bar en gates por reloj de pared
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


# ============================================================
# REPLAY DENSO: estado de CADA vela (no solo las que disparan)
# ============================================================
WIN = "win"
LOSS = "loss"


def _atr_series(df, atr_col=None):
    """Serie de ATR para normalizar el retorno forward. Usa la columna dada o una
    comun (atr14/atr/ATRr_14); si no hay, calcula ATR(14) Wilder desde H/L/C.
    """
    import numpy as _np
    if atr_col and atr_col in df.columns:
        return df[atr_col].to_numpy(dtype="float64")
    for c in ("atr14", "atr", "ATRr_14", "ATR_14", "atr_14"):
        if c in df.columns:
            return df[c].to_numpy(dtype="float64")
    high = df["high"].to_numpy(dtype="float64")
    low = df["low"].to_numpy(dtype="float64")
    close = df["close"].to_numpy(dtype="float64")
    prev = _np.concatenate([[close[0]], close[:-1]])
    tr = _np.maximum(high - low, _np.maximum(_np.abs(high - prev), _np.abs(low - prev)))
    atr = pd.Series(tr).ewm(alpha=1.0 / 14, adjust=False).mean().to_numpy()
    return atr


def _fire_levels(report, target_level="tp1"):
    """Direccion (+1/-1) y niveles del motor para un FIRE valido, o (None, None)
    si el report no trae niveles completos. Compartido para que la fila de senal
    del replay denso sea IDENTICA a la de replay_events (fires-only)."""
    direction = _DIR_MAP.get(report.get("direction"))
    levels = report.get("levels") or {}
    entry = levels.get("entry"); stop = levels.get("sl")
    target = levels.get(target_level)
    if direction is None or entry is None or stop is None or target is None:
        return None, None
    return direction, {
        "entry_price": float(entry), "stop_price": float(stop),
        "target_price": float(target), "direction": direction,
        "tp3": levels.get("tp3"), "rr_tp3": levels.get("rr_tp3"),
        "px_tp1": levels.get("tp1"), "px_tp2": levels.get("tp2"),
        "px_tp3": levels.get("tp3"), "px_tp4": levels.get("tp4"),
    }


def replay_states(
    df_primary, df_mid, df_high, df_sub,
    evaluate_fn, detect_pspace_fn, laplacian_check_fn, calculate_levels_fn, config,
    min_lookback=300, step=1, horizon_bars=288, htf_tail=300, sub_tail=120,
    atr_col=None, target_level="tp1", progress_every=0, on_bar=None,
):
    """Replay DENSO para el indice de retrieval (pivot): registra el ESTADO
    (field/features que el motor computa) de CADA vela evaluada -- dispare o no --
    etiquetado con el retorno forward normalizado por ATR a `horizon_bars`.

    Asi el estimador k-NN prueba la tesis pura ('estados de mercado similares
    preceden movimientos similares') con densidad real (decenas de miles de
    estados), desacoplado del gate francotirador (que solo dispara ~decenas).

    pnl_r = (close[i+H] - close[i]) / ATR[i]  (movimiento forward en multiplos de
    ATR; direccion LONG por construccion -> el signo mide si el estado precede
    subida o bajada). outcome = win si pnl_r>0.

    UNIFICADO: las filas con fired=True llevan ADEMAS la direccion/entry/sl/targets
    reales del motor -> ese subset ES el track record de senales (lo consumen
    label_events + la frontera TP, identico a replay_events). Asi UN solo replay
    alimenta las dos salidas (retrieval denso + research de senales) sin repetir el
    coste del motor.

    Causal: usa df_primary.iloc[:i+1] y htf_window (solo pasado <= ts). El label
    mira al futuro [i, i+H] pero eso es el DESENLACE (se conoce solo despues); el
    walk-forward + embargo de retrieval_oos garantiza que ningun vecino del indice
    tenga su [i, i+H] solapado con el query.
    """
    n = len(df_primary)
    ts_col = df_primary["timestamp"].to_numpy()
    close = df_primary["close"].to_numpy(dtype="float64")
    atr = _atr_series(df_primary, atr_col)
    last_i = n - horizon_bars - 1   # necesitamos H velas de futuro para el label
    rows = []
    for i in range(min_lookback, max(min_lookback, last_i), step):
        if progress_every and i % progress_every == 0:
            log.info("replay_states %d/%d estados=%d", i, n, len(rows))
        ts = ts_col[i]
        if on_bar is not None:
            on_bar(ts)   # hora del bar para los gates por reloj de pared
        winp = df_primary.iloc[: i + 1]
        win_mid = htf_window(df_mid, ts, tail=htf_tail)
        win_high = htf_window(df_high, ts, tail=htf_tail)
        win_sub = htf_window(df_sub, ts, tail=sub_tail)
        try:
            fire, field, report = evaluate_fn(
                winp, win_mid, win_high, win_sub,
                detect_pspace_fn, laplacian_check_fn, calculate_levels_fn, config,
            )
        except Exception as e:
            log.warning("evaluate_fn (denso) fallo en i=%d: %s", i, e)
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        fwd_r = float((close[i + horizon_bars] - close[i]) / a)
        is_fire = bool(fire and report.get("decision") == "fire")
        direction, lvl = _fire_levels(report, target_level) if is_fire else (None, None)
        row = {
            "entry_index": i, "entry_ts": pd.Timestamp(ts),
            "entry_price": float(close[i]), "direction": LONG,
            "bars_held": int(horizon_bars), "pnl_r": fwd_r,
            "outcome": WIN if fwd_r > 0 else LOSS,
            # fired = FIRE valido (con niveles): este subset ES el track record de
            # senales (frontera+modelo via label_events). El label denso (pnl_r
            # forward-ATR) queda intacto para el retrieval; label_events re-etiqueta
            # el subset con triple-barrier en su propia tabla.
            "fired": lvl is not None,
        }
        row.update(extract_features(field, report))
        if lvl is not None:
            row.update(lvl)   # dir/entry/sl/targets reales del motor (sobreescribe LONG)
        rows.append(row)
    return pd.DataFrame(rows)
