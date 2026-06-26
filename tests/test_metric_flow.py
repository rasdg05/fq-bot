# -*- coding: utf-8 -*-
"""validate_metric_flow: las 3 hipótesis (rising/directional/contrarian) sobre cualquier
medidor del dataset metrics. Puro; el DSR sobre data real lo corre el workflow."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import validate_metric_flow as M  # noqa: E402


def _df(vals, col="taker_ls"):
    return pd.DataFrame({"ts": list(range(0, len(vals) * 300000, 300000)), col: vals})


def test_features_mean_y_slope():
    f = M.metric_features(_df([1.0, 1.1, 1.2, 1.3, 1.4]), "taker_ls", win=5)
    assert f["slope"] > 0 and abs(f["mean"] - 1.2) < 1e-9 and f["n"] == 5


def test_directional_confirma_con_la_direccion():
    bull = M.metric_features(_df([1.2, 1.25, 1.3]), "taker_ls", win=3)   # mean 1.25 > 1
    bear = M.metric_features(_df([0.8, 0.75, 0.7]), "taker_ls", win=3)   # mean 0.75 < 1
    assert M.metric_confirms(bull, 1, rule="directional", thr=0.05) is True    # LONG con ratio alcista
    assert M.metric_confirms(bull, -1, rule="directional", thr=0.05) is False  # SHORT NO
    assert M.metric_confirms(bear, -1, rule="directional", thr=0.05) is True   # SHORT con ratio bajista


def test_contrarian_fadea_la_multitud():
    crowd_long = M.metric_features(_df([1.3, 1.35, 1.4], "global_ls"), "global_ls", win=3)  # retail muy largo
    # contrarian: multitud larga -> confirma SHORT, NO confirma LONG
    assert M.metric_confirms(crowd_long, -1, rule="contrarian", thr=0.05) is True
    assert M.metric_confirms(crowd_long, 1, rule="contrarian", thr=0.05) is False


def test_rising_es_direction_agnostico():
    up = M.metric_features(_df([100, 110, 120], "oi_usd"), "oi_usd", win=3)
    assert M.metric_confirms(up, 1, rule="rising", thr=0.0) is True
    assert M.metric_confirms(up, -1, rule="rising", thr=0.0) is True


def test_evaluate_con_cvd_apila_y_ortogonalidad_no_crashea(tmp_path, capsys):
    import numpy as np
    base = 1_700_000_000_000
    n = 80
    ev_ts = [base + i * 3_600_000 for i in range(n)]
    cube = pd.DataFrame({"tp": ["tp4"] * n, "horizon": [576] * n, "entry_index": range(n),
                         "entry_ts": pd.to_datetime(ev_ts, unit="ms"),
                         "direction": [1, -1] * (n // 2),
                         "pnl_r": np.random.default_rng(2).normal(0.1, 1, n)})
    cube_p = tmp_path / "cube.parquet"; cube.to_parquet(cube_p)
    mt_ts = list(range(base - 200 * 300000, base + n * 3_600_000, 300000))
    met = pd.DataFrame({"ts": mt_ts, "global_ls": [1.3] * len(mt_ts)})   # retail largo
    met_p = tmp_path / "met.parquet"; met.to_parquet(met_p)
    cvd = pd.DataFrame({"ts": mt_ts, "buy_vol": [60.0] * len(mt_ts), "sell_vol": [40.0] * len(mt_ts)})
    cvd_p = tmp_path / "cvd.parquet"; cvd.to_parquet(cvd_p)
    df = M.evaluate(str(cube_p), str(met_p), "global_ls", rule="contrarian", thr=0.0, cvd_path=str(cvd_p))
    assert len(df) > 20 and df["cvd_conf"].notna().any()
    M.report_orthogonality(df, "global_ls", 0.50)
    assert "Ortogonalidad" in capsys.readouterr().out
