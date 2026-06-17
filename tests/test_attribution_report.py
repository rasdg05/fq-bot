# -*- coding: utf-8 -*-
"""Atribución de módulos (N8.6): el wrapper de bt_ablation produce el veredicto
correcto (módulo útil VIVE, peso muerto MATAR) y la lámina del deck.

Cubo sintético al estilo de test_bt_ablation: un gate útil (correlaciona con
ganar) y uno inútil. Todo local, sin red ni cubo real.
"""
import numpy as np
import pandas as pd
import pytest

import bt_engine as eng
import tools.attribution_report as ar


def _labeled(n=240, seed=1):
    rng = np.random.default_rng(seed)
    good = rng.integers(0, 2, n).astype(bool)   # gate útil
    bad = rng.integers(0, 2, n).astype(bool)    # gate peso muerto
    win = rng.random(n) < np.where(good, 0.75, 0.30)
    return pd.DataFrame({
        "entry_index": np.arange(n), "entry_price": 100.0, "stop_price": 95.0,
        "exit_price": np.where(win, 110.0, 95.0), "direction": eng.LONG,
        "bars_held": 1, "outcome": np.where(win, "win", "loss"),
        "pnl_r": np.where(win, 2.0, -1.0),
        "good_gate": good, "bad_gate": bad,
    })


def _no_cost():
    return {"cost": eng.CostModel(taker_fee=0.0, slippage_bps=0.0,
                                  apply_funding=False)}


def test_detect_modules_picks_gate_columns():
    mods = ar.detect_modules(_labeled(20))
    assert set(mods) == {"good_gate", "bad_gate"}


def test_useful_module_survives_useless_dies():
    df = _labeled(240)
    report, mods = ar.run(df, n_splits=6, embargo=0, sim_kwargs=_no_cost())
    g = report[report["variant"] == "sin_good_gate"].iloc[0]
    b = report[report["variant"] == "sin_bad_gate"].iloc[0]
    assert g["survives"] is True and g["delta_vs_baseline"] > 0   # aporta
    assert b["survives"] is False                                  # peso muerto


def test_lamina_writes_png(tmp_path):
    pytest.importorskip("matplotlib")  # lámina opcional: sin el renderer, skip
    df = _labeled(160)
    report, _ = ar.run(df, n_splits=5, embargo=0, sim_kwargs=_no_cost())
    p = tmp_path / "attr.png"
    ar.lamina(report, str(p))
    assert p.exists() and p.stat().st_size > 0


def test_missing_gate_columns_errors():
    df = _labeled(40).drop(columns=["good_gate", "bad_gate"])
    with pytest.raises(SystemExit):
        ar.run(df, n_splits=4, embargo=0, sim_kwargs=_no_cost())
