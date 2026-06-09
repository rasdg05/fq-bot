# -*- coding: utf-8 -*-
"""
================================================================================
  BT OPTIMIZE - optimizacion de SL/TP/entrada SIN re-replay (post-replay)
  by RasDG_Sol + Claude

  El replay del motor (recorrer la historia disparando fusion_engine) es el ~99%
  del coste. Tanto el ANCHO DEL STOP como el NIVEL DEL TP son post-replay: solo
  cambian el ETIQUETADO triple-barrier, que es barato. Aqui re-etiquetamos el
  MISMO conjunto de senales fired variando:

    - ancho de SL en multiplos de ATR (en la vela de entrada),
    - nivel de TP (tp1..tp4 del motor; tp3 se omite porque == tp2),

  y reportamos una tabla (SL x TP) con expectancy_r / WR / total_R / Calmar y
  drawdown, OOS cuando la muestra alcanza para walk-forward (cae a in-sample con
  pocas senales). Cero replays extra: identico patron al barrido de horizonte.

  NOTA tp3 (corregido jun-2026): calculate_levels en fq_bot_v3_2.py ya separa
  tp3 al punto medio aureo entry + rng*(1+PHI_INV)/2 (~0.809*rng), entre tp2
  (0.618) y tp4 (1.0). Antes tp3 == tp2 (mismo precio) y la escalera tenia 3
  peldanos; ahora son cuatro distintos y monotonos, asi que el grid puede barrer
  tp1..tp4 sin filas duplicadas.

  Frontera (TP x horizonte): tp_horizon_grid usa el cubo de una pasada
  bt_labeler.label_events_grid (re-etiquetar al variar target/horizonte es
  gratis post-replay) para la tabla que el selector F3 del retrieval consume.

  Pieza (casi) pura: usa bt_features._atr_series + bt_labeler/bt_engine/
  bt_walkforward/bt_metrics. Sin red, sin tocar el monolito.
================================================================================
"""
import logging

import numpy as np
import pandas as pd

import bt_features as bf
import bt_labeler as lb
import bt_engine as eng
import bt_metrics as met
import bt_walkforward as wf
import bt_ablation as ab

log = logging.getLogger("bt_optimize")


def _periods_per_year(labeled, bar_minutes):
    """trades/ano desde el span de las entradas (espejo del runner)."""
    if "entry_ts" not in labeled.columns or len(labeled) < 2:
        return None
    ts = pd.to_datetime(labeled["entry_ts"])
    span_days = (ts.max() - ts.min()).total_seconds() / 86400.0
    if span_days <= 0:
        return None
    return len(labeled) * 365.0 / span_days


def _cell_metrics(labeled, sim_kwargs, bar_minutes, n_splits, embargo):
    """Metricas de una celda (SL,TP) ya etiquetada. OOS si hay folds; si no,
    in-sample (lo flageamos en 'oos'). Net de costes via bt_engine.simulate.
    """
    sim_kwargs = sim_kwargs or {}
    ppy = _periods_per_year(labeled, bar_minutes)
    folds, valid_index = wf.folds_from_labeled(
        labeled, n_splits=n_splits, embargo=embargo)
    if folds:
        trades = ab.pooled_oos_trades(labeled, folds, valid_index=valid_index)
        oos = True
    else:
        # muestra insuficiente para walk-forward: in-sample (fijo, sin ajuste)
        trades = labeled[labeled["outcome"].notna()] if "outcome" in labeled.columns \
            else labeled
        oos = False
    if len(trades) == 0:
        return {"n": 0, "oos": oos, "exp_R": None, "WR": None, "total_R": None,
                "calmar": None, "max_dd": None}
    res = eng.simulate(trades, **sim_kwargs)
    m = met.metrics_from_result(res, periods_per_year=ppy)
    return {
        "n": m.get("n_trades", 0),
        "oos": oos,
        "exp_R": m.get("expectancy_r"),
        "WR": m.get("win_rate"),
        "total_R": m.get("total_r"),
        "calmar": m.get("calmar"),
        "max_dd": m.get("max_drawdown"),
    }


def tp_sl_grid(df_primary, events, sl_mults, tp_levels, horizon, *,
               sim_kwargs=None, n_splits=7, embargo=8, bar_minutes=5.0,
               atr_col=None):
    """Grid post-replay SL(xATR) x TP(tp1..tp4) sobre el MISMO conjunto fired.

    df_primary : OHLCV del TF primario (para ATR en la vela de entrada y como
                 serie de futuro del triple-barrier).
    events     : DataFrame de senales fired (con entry_index, entry_price,
                 direction y px_tp1..px_tp4). Acepta tambien lista de dicts.
    sl_mults   : iterable de multiplos de ATR para el ancho del stop.
    tp_levels  : iterable de niveles ('tp1'..'tp4').
    horizon    : barrera vertical (velas) para el etiquetado.

    Para cada celda re-deriva stop = entry -/+ sl_mult*ATR[entry] (signo segun
    direccion) y target = px_<lvl>, re-etiqueta y mide. Devuelve un DataFrame con
    columnas: SL_xATR, TP, n, oos, exp_R, WR, total_R, calmar, max_dd.
    """
    if hasattr(events, "to_dict"):
        recs = events.to_dict("records")
    else:
        recs = list(events)
    atr = bf._atr_series(df_primary, atr_col)
    n_atr = len(atr)

    rows = []
    for sl in sl_mults:
        for lvl in tp_levels:
            col = f"px_{lvl}"
            cell = []
            for r in recs:
                ei = int(r["entry_index"])
                d = int(r["direction"])
                entry = float(r["entry_price"])
                px = r.get(col)
                if px is None or (isinstance(px, float) and np.isnan(px)):
                    continue
                if ei < 0 or ei >= n_atr:
                    continue
                a = atr[ei]
                if not np.isfinite(a) or a <= 0:
                    continue
                stop = entry - d * float(sl) * a   # stop a sl*ATR del entry
                if abs(entry - stop) <= 0:
                    continue
                cell.append({**r, "entry_index": ei, "direction": d,
                             "entry_price": entry, "stop_price": float(stop),
                             "target_price": float(px)})
            if not cell:
                continue
            labeled = lb.label_events(df_primary, cell, max_bars=horizon)
            mm = _cell_metrics(labeled, sim_kwargs, bar_minutes, n_splits, embargo)
            rows.append({"SL_xATR": float(sl), "TP": lvl, **mm})
    return pd.DataFrame(rows)


def tp_horizon_grid(df_primary, events, tp_levels, horizons, *,
                    sim_kwargs=None, n_splits=7, embargo=8, bar_minutes=5.0):
    """Frontera (TP x horizonte) sobre el MISMO conjunto fired, con costes y OOS.

    A diferencia de tp_sl_grid (SL x TP a un horizonte), aqui el STOP es el del
    motor (events['stop_price']) y barremos NIVEL de TP x HORIZONTE vertical. Se
    apoya en el cubo de UNA pasada (bt_labeler.label_events_grid): re-etiquetar
    todas las celdas no re-replica el motor (gratis). Por celda mide net de
    costes con bt_engine.simulate, OOS cuando hay folds.

    df_primary : OHLCV del TF primario (futuro del triple-barrier).
    events     : DataFrame/lista de senales fired con entry_index, entry_price,
                 stop_price, direction y px_<lvl>.
    tp_levels  : iterable de niveles ('tp1'..'tp4').
    horizons   : iterable de barreras verticales (velas).

    Devuelve DataFrame: TP, horizon, n, oos, exp_R, WR, total_R, calmar, max_dd.
    """
    if hasattr(events, "to_dict"):
        recs = events.to_dict("records")
    else:
        recs = list(events)
    target_keys = [f"px_{lvl}" for lvl in tp_levels]
    long_df = lb.label_events_grid(df_primary, recs, target_keys, list(horizons))
    if len(long_df) == 0:
        return pd.DataFrame(
            columns=["TP", "horizon", "n", "oos", "exp_R", "WR", "total_R",
                     "calmar", "max_dd"])
    rows = []
    for (tp, h), cell in long_df.groupby(["tp", "horizon"], sort=False):
        mm = _cell_metrics(cell, sim_kwargs, bar_minutes, n_splits, embargo)
        rows.append({"TP": tp, "horizon": int(h), **mm})
    return pd.DataFrame(rows)


def choose_optimum(grid, by="calmar"):
    """Elige la mejor celda del grid por `by` (calmar/exp_R/total_R), con
    fallback a exp_R si la metrica principal es toda None. None si grid vacio.
    """
    if grid is None or len(grid) == 0:
        return None
    for metric in (by, "exp_R", "total_R"):
        sub = grid[grid[metric].notna()]
        if len(sub):
            return sub.loc[sub[metric].astype(float).idxmax()].to_dict()
    return None
