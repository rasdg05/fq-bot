# -*- coding: utf-8 -*-
"""
bt_ablation (poda OOS): valida que un modulo util sobrevive y uno inutil se mata.
Pieza pura -> dataset sintetico con dos modulos de calidad conocida.
"""
import numpy as np
import pandas as pd
import pytest

import bt_ablation as ab
import bt_engine as eng
import bt_walkforward as wf


def _no_cost():
    return {"cost": eng.CostModel(taker_fee=0.0, slippage_bps=0.0,
                                  apply_funding=False)}


def _build_labeled(n=200, seed=1):
    """Construye senales etiquetadas con dos flags de modulo:
      good_flag: cuando True, la senal tiende a GANAR (modulo util).
      bad_flag : independiente del resultado (modulo inutil/peso muerto).
    Todas LONG, entry 100, stop 95 (R=5). exit = 110 si gana, 95 si pierde.
    """
    rng = np.random.default_rng(seed)
    good_flag = rng.integers(0, 2, size=n).astype(bool)
    bad_flag = rng.integers(0, 2, size=n).astype(bool)
    # win con prob alta si good_flag, baja si no. bad_flag no influye.
    p_win = np.where(good_flag, 0.75, 0.30)
    win = rng.random(n) < p_win
    exit_price = np.where(win, 110.0, 95.0)
    pnl_r = np.where(win, 2.0, -1.0)
    outcome = np.where(win, "win", "loss")
    df = pd.DataFrame({
        "entry_index": np.arange(n),
        "entry_price": 100.0,
        "stop_price": 95.0,
        "exit_price": exit_price,
        "direction": eng.LONG,
        "bars_held": 1,
        "outcome": outcome,
        "pnl_r": pnl_r,
        "good_flag": good_flag,
        "bad_flag": bad_flag,
    })
    return df


def test_useful_module_survives_useless_module_dies():
    df = _build_labeled(n=240)
    folds, valid_index = wf.folds_from_labeled(df, n_splits=6)
    modules = {
        # el modulo "good" deja pasar solo cuando good_flag (filtro util)
        "good": lambda d: d["good_flag"].to_numpy(),
        # el modulo "bad" deja pasar segun bad_flag (no correlaciona con ganar)
        "bad": lambda d: d["bad_flag"].to_numpy(),
    }
    report = ab.run_ablation(df, folds, modules, valid_index=valid_index,
                             sim_kwargs=_no_cost(), margin=0.0)
    good_row = report[report["variant"] == "sin_good"].iloc[0]
    bad_row = report[report["variant"] == "sin_bad"].iloc[0]
    # quitar 'good' empeora mucho -> delta positivo grande -> sobrevive
    assert good_row["survives"] is True
    assert good_row["delta_vs_baseline"] > 0
    # quitar 'bad' no mejora la expectancy -> se mata
    assert bad_row["survives"] is False


def test_report_has_baseline_and_none_variants():
    df = _build_labeled(n=120)
    folds, valid_index = wf.folds_from_labeled(df, n_splits=5)
    modules = {"good": lambda d: d["good_flag"].to_numpy()}
    report = ab.run_ablation(df, folds, modules, valid_index=valid_index,
                             sim_kwargs=_no_cost())
    variants = set(report["variant"])
    assert {"none", "baseline", "sin_good"} <= variants
    # el universo completo (none) debe tener >= trades que el baseline filtrado
    n_none = report[report["variant"] == "none"].iloc[0]["n_trades"]
    n_base = report[report["variant"] == "baseline"].iloc[0]["n_trades"]
    assert n_none >= n_base


def test_attribution_story_renders_verdicts():
    df = _build_labeled(n=200)
    folds, valid_index = wf.folds_from_labeled(df, n_splits=6)
    modules = {
        "good": lambda d: d["good_flag"].to_numpy(),
        "bad": lambda d: d["bad_flag"].to_numpy(),
    }
    report = ab.run_ablation(df, folds, modules, valid_index=valid_index,
                             sim_kwargs=_no_cost())
    story = ab.attribution_story(report)
    assert "VIVE" in story or "MATAR" in story
    assert "good" in story and "bad" in story


def test_pooled_oos_trades_are_chronological():
    df = _build_labeled(n=100)
    folds, valid_index = wf.folds_from_labeled(df, n_splits=5)
    pooled = ab.pooled_oos_trades(df, folds, valid_index=valid_index)
    assert pooled["entry_index"].is_monotonic_increasing
    assert len(pooled) > 0
