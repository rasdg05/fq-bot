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
# CROSS-ASSET LEAD-LAG (BTC -> alt), CAUSAL por construccion
# ============================================================
# Prefijo de TODAS las features cross-asset. El loader las inyecta en los eventos
# /estados y, gracias a que estan en la lista de _numeric_feature_columns (modelo)
# y en bt_retrieval.DEFAULT_NUMERIC (vector de retrieval), las consume TANTO el GBM
# del [3/4] COMO el vector k-NN del retrieval + el gate ORO. Ver feasibility.
XBTC_PREFIX = "xbtc_"

# Columnas xbtc_ que el modelo y el vector deben reconocer. Se declaran aqui (no en
# DEFAULT_NUMERIC para evitar import circular) y bt_retrieval las anexa. Si anades
# una xbtc_, agregala aqui: queda numerica -> entra al modelo y al vector.
XBTC_FEATURE_COLUMNS = (
    "xbtc_ret_3", "xbtc_ret_12", "xbtc_ret_48",
    "xbtc_atrpct", "xbtc_trend", "xbtc_relstr",
)


def cross_asset_features(
    df_primary, df_cross, *,
    ret_bars=(3, 12, 48), atr_bars=14, trend_ma_bars=48, relstr_bars=12,
    shift_cross=1,
):
    """Features lead-lag de un activo CRUZADO (p.ej. BTC) alineadas CAUSALMENTE a
    cada vela del activo primario (p.ej. SOL/ETH). Pieza PURA: DataFrames in ->
    DataFrame in (sin red, sin estado, testeable).

    df_primary / df_cross: OHLCV con columna 'timestamp' (datetime), MISMO TF y
    exchange. El cruzado se usa SOLO con timestamp <= el de la vela primaria.

    DEVUELVE un DataFrame con UNA fila por vela primaria (mismo orden/longitud que
    df_primary) y columnas:
      xbtc_ret_3 / xbtc_ret_12 / xbtc_ret_48 : pct-change del close cruzado sobre
          N velas del TF primario (momentum del lider a 3 horizontes).
      xbtc_atrpct : volatilidad reciente del cruzado = ATR(atr_bars) Wilder / close
          (en fraccion del precio; trailing, min_periods).
      xbtc_trend  : sign(close_cruzado - MA(trend_ma_bars) del cruzado) en {-1,0,1}.
      xbtc_relstr : FUERZA RELATIVA = ret_primario(relstr_bars) - ret_cruzado(
          relstr_bars) sobre la MISMA ventana (si el alt sube mas/menos que BTC).

    ---------------------------------------------------------------------------
    LEAKAGE (el punto que se revisa). Una feature en la vela primaria t SOLO puede
    leer datos del cruzado con timestamp <= t (jamas el futuro):

    1) ALINEACION via pd.merge_asof(..., direction="backward"): a cada vela
       primaria t le empareja la fila del cruzado con timestamp MAS RECIENTE que
       NO sea posterior a t (cross_ts <= t). Nunca rellena desde el futuro
       (forward-fill), nunca una ventana centrada/adelantada.

    2) CONSERVADOR (shift_cross=1, default): la vela del cruzado fechada EXACTAMENTE
       en t cierra al final del periodo t (misma convencion open-stamped que la
       primaria), asi que en el INSTANTE de la decision del alt en t esa vela del
       cruzado AUN se esta formando -> no es conocible. Por eso desplazamos las
       features del cruzado UNA vela (se usan valores de cierre del cruzado en
       t-1cross, ya cerrados) ANTES del merge. Eleccion conservadora y documentada
       (la alternativa <= t exacta asumiria conocer una vela en formacion).

    3) Las ventanas rolling del cruzado (ret/atr/ma) son TRAILING con min_periods:
       cada valor en la fila k usa solo filas <= k del cruzado. Sin ventana futura.

    El resultado: el valor xbtc_* en t NO puede reflejar ningun dato del cruzado
    posterior a t (de hecho, ni siquiera el de t: solo <= t-1cross). La maquinaria
    temporal OOS/embargo/OOT existente se mantiene honesta porque estas columnas
    son, por construccion, funcion solo del pasado.
    """
    n = len(df_primary)
    empty = pd.DataFrame(index=range(n))
    for c in XBTC_FEATURE_COLUMNS:
        empty[c] = np.nan
    if df_cross is None or len(df_cross) == 0 or n == 0:
        return empty

    # --- features del CRUZADO, calculadas SOLO sobre su propia serie (trailing) ---
    cx = df_cross[["timestamp"]].copy()
    cx["timestamp"] = pd.to_datetime(df_cross["timestamp"])
    cx = cx.sort_values("timestamp").reset_index(drop=True)
    c_close = pd.to_numeric(df_cross["close"], errors="coerce").reset_index(drop=True)
    c_high = pd.to_numeric(df_cross["high"], errors="coerce").reset_index(drop=True)
    c_low = pd.to_numeric(df_cross["low"], errors="coerce").reset_index(drop=True)
    # reordena las series OHLC al mismo orden temporal que cx
    order = df_cross["timestamp"].reset_index(drop=True).sort_values().index
    c_close = c_close.iloc[order].reset_index(drop=True)
    c_high = c_high.iloc[order].reset_index(drop=True)
    c_low = c_low.iloc[order].reset_index(drop=True)

    feat = pd.DataFrame({"timestamp": cx["timestamp"]})
    rb = sorted({int(b) for b in ret_bars})
    # los 3 horizontes pedidos van a xbtc_ret_3/12/48 por convencion de nombre
    name_for = {3: "xbtc_ret_3", 12: "xbtc_ret_12", 48: "xbtc_ret_48"}
    for b in rb:
        col = name_for.get(b, f"xbtc_ret_{b}")
        feat[col] = c_close.pct_change(b)
    # ATR(atr_bars) Wilder, trailing -> en fraccion del precio
    prev = c_close.shift(1)
    tr = pd.concat([(c_high - c_low),
                    (c_high - prev).abs(),
                    (c_low - prev).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / float(atr_bars), adjust=False,
                 min_periods=atr_bars).mean()
    feat["xbtc_atrpct"] = (atr / c_close).replace([np.inf, -np.inf], np.nan)
    # trend: signo de close - MA(trend_ma_bars), trailing
    ma = c_close.rolling(trend_ma_bars, min_periods=trend_ma_bars).mean()
    feat["xbtc_trend"] = np.sign(c_close - ma)
    feat["xbtc_trend"] = feat["xbtc_trend"].where(ma.notna(), np.nan)
    # guarda el retorno del cruzado para la fuerza relativa (mismo window)
    feat["_xbtc_ret_rs"] = c_close.pct_change(relstr_bars)

    cols_all = [c for c in feat.columns if c != "timestamp"]
    # (2) CONSERVADOR: desplaza las features del cruzado shift_cross velas ANTES de
    # alinear -> la vela del cruzado en formacion en t (cross_ts == t) NO se usa;
    # se toma la ultima YA CERRADA (cross_ts <= t-shift_cross). NaN inicial limpio.
    if shift_cross:
        feat[cols_all] = feat[cols_all].shift(int(shift_cross))

    # --- ALINEACION CAUSAL: merge_asof backward (cross_ts <= primary_ts) ---
    prim = pd.DataFrame({"timestamp": pd.to_datetime(df_primary["timestamp"]).to_numpy()})
    prim["_pos"] = np.arange(n)
    prim = prim.sort_values("timestamp")
    feat = feat.sort_values("timestamp")
    merged = pd.merge_asof(prim, feat, on="timestamp", direction="backward")
    merged = merged.sort_values("_pos").reset_index(drop=True)

    # fuerza relativa = ret_primario(window) - ret_cruzado(window), ambos hasta t
    p_close = pd.to_numeric(df_primary["close"], errors="coerce").reset_index(drop=True)
    p_ret = p_close.pct_change(relstr_bars)
    merged["xbtc_relstr"] = p_ret.to_numpy() - merged["_xbtc_ret_rs"].to_numpy()

    out = pd.DataFrame(index=range(n))
    for c in XBTC_FEATURE_COLUMNS:
        out[c] = merged[c].to_numpy() if c in merged.columns else np.nan
    return out


def attach_cross_asset_features(events, df_primary, df_cross, **kwargs):
    """Inyecta las columnas xbtc_* (cross_asset_features) en un DataFrame de
    eventos/estados, casando por entry_index (posicion en df_primary).

    events: DataFrame con columna 'entry_index' (posicion de la vela primaria),
            tal cual lo emiten replay_events / replay_states.
    Devuelve `events` con las columnas xbtc_* anexadas (no muta el original).
    Causal: cada fila recibe el valor xbtc_ de SU entry_index, que a su vez solo
    leyo cruzado <= esa vela (ver cross_asset_features). No reordena los eventos.
    """
    if events is None or len(events) == 0:
        out = events.copy() if events is not None else events
        if out is not None:
            for c in XBTC_FEATURE_COLUMNS:
                if c not in out.columns:
                    out[c] = np.nan
        return out
    xf = cross_asset_features(df_primary, df_cross, **kwargs)
    ei = pd.to_numeric(events["entry_index"], errors="coerce").to_numpy()
    out = events.copy()
    n = len(xf)
    for c in XBTC_FEATURE_COLUMNS:
        vals = np.full(len(out), np.nan)
        ok = np.isfinite(ei) & (ei >= 0) & (ei < n)
        idx = ei[ok].astype(int)
        vals[ok] = xf[c].to_numpy()[idx]
        out[c] = vals
    return out


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
    # regime_detector.detect_regime NO emite 'score': su magnitud numerica es
    # n_flags (0..3 votos de deriva, lo que define el state). Sin este fallback
    # la columna regime_score llegaba 100% NaN en TODOS los simbolos (dimension
    # muerta del vector de retrieval + warnings 'All-NaN slice' en el fit).
    # 'score' se respeta por si un detector futuro lo emite.
    rs = regime.get("score")
    f["regime_score"] = rs if rs is not None else regime.get("n_flags")

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
    """Columnas de features estrictamente numericas (para el modelo).

    Incluye el prefijo cross-asset XBTC_PREFIX ('xbtc_') para que las features
    lead-lag del activo lider (BTC) entren al GBM del [3/4] cuando esten presentes
    (--cross-asset). Sin esto, una columna numerica xbtc_ NO se recogeria (la
    seleccion es por allowlist de prefijos, no por dtype solo)."""
    cols = []
    for c in events.columns:
        if not c.startswith(("p_master", "scorer_", "regime_score",
                             "field_confluence", "field_pd_pct",
                             "field_w_effective", XBTC_PREFIX)):
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
            # Diagnostico de CADENCIA: en que gate murio la vela candidata.
            # Gratis en el mismo replay; decision_funnel() lo agrupa post-replay
            # para decidir que modulo relajar (con respaldo OOS de la poda).
            "decision": report.get("decision"),
            "failed_at": report.get("failed_at"),
        }
        row.update(extract_features(field, report))
        if lvl is not None:
            row.update(lvl)   # dir/entry/sl/targets reales del motor (sobreescribe LONG)
        rows.append(row)
    return pd.DataFrame(rows)


def decision_funnel(states):
    """FUNNEL de cadencia: cuenta estados del replay denso por (decision,
    failed_at) del motor -- 'donde mueren las velas candidatas'.

    states: DataFrame de replay_states (necesita la columna 'decision'; los
    replays anteriores a jun-2026 no la traen -> devuelve vacio).
    Devuelve DataFrame [decision, failed_at, n, pct] ordenado desc por n.
    """
    cols = ["decision", "failed_at", "n", "pct"]
    if states is None or len(states) == 0 or "decision" not in states.columns:
        return pd.DataFrame(columns=cols)
    df = states[["decision"]].copy()
    fa = states["failed_at"] if "failed_at" in states.columns else None
    df["failed_at"] = (fa.fillna("") if fa is not None else "")
    df["decision"] = df["decision"].fillna("?")
    g = df.groupby(["decision", "failed_at"]).size().reset_index(name="n")
    g["pct"] = (100.0 * g["n"] / len(states)).round(2)
    return g.sort_values(["n", "decision"], ascending=[False, True]).reset_index(drop=True)
