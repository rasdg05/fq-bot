# -*- coding: utf-8 -*-
"""Walk-forward report (N8.2): métricas por fold + resumen de estabilidad, y un
edge positivo da media OOS>0 con folds mayormente positivos. Sin red ni cubo.
"""
import numpy as np
import pandas as pd
import pytest

import bt_engine as eng
import tools.walkforward_report as wr


def _labeled(n=420, win_rate=0.60, seed=1):
    rng = np.random.default_rng(seed)
    win = rng.random(n) < win_rate
    return pd.DataFrame({
        "entry_index": np.arange(n), "entry_price": 100.0, "stop_price": 95.0,
        "exit_price": np.where(win, 110.0, 95.0), "direction": eng.LONG,
        "bars_held": 1, "outcome": np.where(win, "win", "loss"),
        "pnl_r": np.where(win, 2.0, -1.0),
    })


def _no_cost():
    return {"cost": eng.CostModel(taker_fee=0.0, slippage_bps=0.0,
                                  apply_funding=False)}


def test_per_fold_and_summary():
    df = _labeled(420, win_rate=0.60)
    rep, summary = wr.run(df, n_splits=5, embargo=0, sim_kwargs=_no_cost())
    assert summary["n_folds"] >= 3      # walk-forward purgado da ~n_splits-1
    assert summary["folds_evaluated"] >= 1
    assert {"fold", "n_trades", "expectancy_r", "win_rate"}.issubset(rep.columns)
    # win 60% con 2R/-1R -> expectancy ~0.8R -> media OOS>0, casi todos los folds +
    assert summary["expectancy_mean"] > 0
    assert summary["folds_positive"] >= summary["folds_evaluated"] - 1


def test_lamina_png(tmp_path):
    pytest.importorskip("matplotlib")  # lámina opcional: sin el renderer, skip
    df = _labeled(300)
    rep, summary = wr.run(df, n_splits=5, embargo=0, sim_kwargs=_no_cost())
    p = tmp_path / "wf.png"
    wr.lamina(rep, summary, str(p))
    assert p.exists() and p.stat().st_size > 0
