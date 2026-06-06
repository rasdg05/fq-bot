# -*- coding: utf-8 -*-
"""
================================================================================
  BT ABLATION - poda de modulos por supervivencia out-of-sample
  by RasDG_Sol + Claude

  La herramienta de "matar lo que no sobrevive". Cada modulo del motor
  (session_bias, regime, QTE, volume_quality, ...) actua como un FILTRO sobre
  las senales: deja pasar unas y veta otras. Aqui medimos, SOLO sobre el test
  walk-forward (out-of-sample) y con costes reales, si ese filtro aporta
  expectancy o es peso muerto.

  Metodo:
    - baseline: aplica TODOS los filtros (AND de las mascaras de modulo).
    - sin_M:    aplica todos MENOS el del modulo M.
    - veredicto: el modulo M SOBREVIVE si baseline expectancy_r > sin_M (quitarlo
      empeora) por un margen. Si quitarlo no cambia o mejora, es peso muerto ->
      se mata.

  Cada modulo se expresa como una mascara: callable(df) -> bool array, True =
  "este modulo DEJA PASAR la senal". Pieza pura: combina bt_engine + bt_metrics
  sobre el subconjunto OOS. Sin I/O.
================================================================================
"""
import logging

import numpy as np
import pandas as pd

import bt_engine as eng
import bt_metrics as met

log = logging.getLogger("bt_ablation")


def pooled_oos_trades(labeled, folds, valid_index=None, sort_col="entry_index"):
    """Reune todas las filas de TEST de los folds en una sola cartera OOS,
    ordenada cronologicamente para que el compounding del engine tenga sentido.
    """
    base = labeled
    if valid_index is not None:
        base = labeled.loc[valid_index]
    base = base.reset_index(drop=True)

    test_positions = np.unique(np.concatenate([te for _tr, te in folds])) \
        if folds else np.array([], dtype=int)
    pooled = base.iloc[test_positions]
    if sort_col in pooled.columns:
        pooled = pooled.sort_values(sort_col)
    return pooled.reset_index(drop=True)


def _apply_masks(df, masks):
    """AND de una lista de mascaras (cada una callable(df)->bool array)."""
    keep = np.ones(len(df), dtype=bool)
    for fn in masks:
        keep &= np.asarray(fn(df), dtype=bool)
    return keep


def _variant_metrics(df, keep_mask, sim_kwargs, periods_per_year):
    sel = df[keep_mask]
    if len(sel) == 0:
        return {"n_trades": 0, "expectancy_r": None, "sharpe": None,
                "total_r": 0.0, "max_drawdown": 0.0, "final_equity": None}
    res = eng.simulate(sel, **(sim_kwargs or {}))
    m = met.metrics_from_result(res, periods_per_year=periods_per_year)
    return {
        "n_trades": m.get("n_trades", 0),
        "expectancy_r": m.get("expectancy_r"),
        "sharpe": m.get("sharpe"),
        "total_r": m.get("total_r", 0.0),
        "max_drawdown": m.get("max_drawdown", 0.0),
        "final_equity": m.get("final_equity"),
    }


def run_ablation(labeled, folds, modules, valid_index=None, sim_kwargs=None,
                 periods_per_year=None, margin=0.0, metric="expectancy_r"):
    """Corre la ablacion de modulos sobre la cartera OOS.

    labeled : DataFrame etiquetado (salida de bt_labeler), con pnl_r/outcome y
              las columnas que las mascaras de modulo necesiten.
    folds   : folds walk-forward (bt_walkforward).
    modules : dict {nombre: mask_fn(df)->bool}. True = el modulo deja pasar.
    valid_index: el de folds_from_labeled (mapea posiciones a filas).
    sim_kwargs : kwargs para bt_engine.simulate (equity0, risk_frac, cost, ...).
    margin  : delta minimo de `metric` para declarar que el modulo sobrevive.
    metric  : metrica de decision ("expectancy_r" por defecto; tambien "sharpe").

    Devuelve un DataFrame-reporte, una fila por variante:
      variant, is_module, n_trades, expectancy_r, sharpe, total_r,
      max_drawdown, delta_vs_baseline, survives
    'survives' solo aplica a filas de modulo (None en baseline/none).
    """
    pooled = pooled_oos_trades(labeled, folds, valid_index=valid_index)
    names = list(modules.keys())
    all_masks = [modules[n] for n in names]

    rows = []

    # Variante NONE: ningun filtro (universo completo).
    none_keep = np.ones(len(pooled), dtype=bool)
    none_m = _variant_metrics(pooled, none_keep, sim_kwargs, periods_per_year)
    rows.append({"variant": "none", "is_module": False, **none_m,
                 "delta_vs_baseline": None, "survives": None})

    # Variante BASELINE: todos los filtros.
    base_keep = _apply_masks(pooled, all_masks)
    base_m = _variant_metrics(pooled, base_keep, sim_kwargs, periods_per_year)
    base_metric = base_m.get(metric)
    rows.append({"variant": "baseline", "is_module": False, **base_m,
                 "delta_vs_baseline": 0.0, "survives": None})

    # Una variante por modulo: todos MENOS ese.
    for n in names:
        others = [modules[k] for k in names if k != n]
        keep = _apply_masks(pooled, others) if others else \
            np.ones(len(pooled), dtype=bool)
        vm = _variant_metrics(pooled, keep, sim_kwargs, periods_per_year)
        without_metric = vm.get(metric)
        if base_metric is None or without_metric is None:
            delta = None
            survives = None
        else:
            # delta > 0 => quitar el modulo EMPEORA => el modulo aporta => vive.
            delta = base_metric - without_metric
            survives = bool(delta > margin)
        rows.append({"variant": f"sin_{n}", "is_module": True, **vm,
                     "delta_vs_baseline": delta, "survives": survives})

    return pd.DataFrame(rows)


def attribution_story(report, metric="expectancy_r"):
    """Narrativa legible: que modulos sobreviven y cuales se matan, ordenados por
    cuanto aportan (delta). Devuelve texto para el reporte/pitch.
    """
    mod_rows = report[report["is_module"]].copy()
    if len(mod_rows) == 0:
        return "sin modulos evaluados"
    mod_rows = mod_rows.sort_values("delta_vs_baseline",
                                    ascending=False, na_position="last")
    base = report[report["variant"] == "baseline"].iloc[0]
    lines = [
        f"Baseline OOS: {metric}={_fmt(base.get(metric))} "
        f"sharpe={_fmt(base.get('sharpe'))} n={int(base['n_trades'])}",
        "",
        "Atribucion por modulo (delta = cuanto cae el baseline al quitarlo):",
    ]
    for _, r in mod_rows.iterrows():
        name = r["variant"].replace("sin_", "")
        verdict = "VIVE " if r["survives"] else "MATAR"
        lines.append(
            f"  [{verdict}] {name:<16} delta={_fmt(r['delta_vs_baseline'])}  "
            f"(sin el: {metric}={_fmt(r.get(metric))})"
        )
    return "\n".join(lines)


def _fmt(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)
