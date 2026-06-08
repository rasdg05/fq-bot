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

  BUG CONOCIDO DEL MONOLITO (calculate_levels en fq_bot_v3_2.py): tp3 se computa
  como entry + rng*PHI_INV, IDENTICO a tp2 -> px_tp3 == px_tp2 (la frontera y el
  grid lo reflejan: filas tp2/tp3 iguales). El UNICO target genuinamente lejano
  es tp4 = entry + rng. TODO (en el entorno del bot, no en este sandbox donde el
  monolito no importa): en calculate_levels, separar tp3 a un multiplo intermedio
  real (p.ej. entry + rng*(1+PHI_INV)/2 o un RR fijo entre tp2 y tp4) para que la
  escalera "TP tras TP" tenga cuatro peldanos distintos. Hasta entonces, el grid
  usa por defecto tp1,tp2,tp4.

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
