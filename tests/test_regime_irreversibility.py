# -*- coding: utf-8 -*-
"""KL: irreversibilidad temporal (grafo de visibilidad) como condicionador de régimen.
Puro; el DSR sobre data real lo corre el workflow."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import validate_regime_irreversibility as R  # noqa: E402


def test_hvg_invariante_in_eq_out():
    # cada arista aporta un grado in y uno out -> sum(in) == sum(out)
    y = np.array([1.0, 3.0, 2.0, 4.0, 1.5, 5.0, 0.5, 2.5], float)
    indeg, outdeg = R._hvg_degrees(y)
    assert indeg.sum() == outdeg.sum() and (indeg >= 0).all() and (outdeg >= 0).all()


def test_irreversibilidad_constante_y_corta_es_cero():
    assert R.irreversibility(np.ones(40)) == 0.0          # serie plana -> reversible
    assert R.irreversibility(np.array([1.0, 2.0, 3.0])) == 0.0   # <8 -> 0


def test_serie_asimetrica_es_irreversible():
    # diente de sierra: sube lento, cae de golpe -> asimétrica temporalmente -> KL>0
    saw = np.array(([0, 1, 2, 3, 4, 5, 6, 7] * 6), float)
    assert R.irreversibility(saw) > 0.0


def test_evaluate_condicionador_no_crashea(tmp_path, capsys):
    base = 1_700_000_000_000
    n = 120
    ev_ts = [base + i * 3_600_000 for i in range(n)]
    cube = pd.DataFrame({"tp": ["tp4"] * n, "horizon": [576] * n, "entry_index": range(n),
                         "entry_ts": pd.to_datetime(ev_ts, unit="ms"),
                         "direction": [1, -1] * (n // 2),
                         "pnl_r": np.random.default_rng(7).normal(0.1, 1, n)})
    cube_p = tmp_path / "cube.parquet"; cube.to_parquet(cube_p)
    kl_ts = list(range(base - 200 * 300000, base + n * 3_600_000, 300000))
    m = len(kl_ts)
    rng = np.random.default_rng(8)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.004, m))
    kl = pd.DataFrame({"ts": kl_ts, "open": close, "high": close * 1.001,
                       "low": close * 0.999, "close": close,
                       "volume": [100.0] * m, "taker_buy_base": [55.0] * m})
    kl_p = tmp_path / "kl.parquet"; kl.to_parquet(kl_p)
    df = R.evaluate(str(cube_p), str(kl_p), lookback=64)
    assert len(df) > 40 and "irrev" in df.columns
    R.report(df)
    assert "irreversibilidad" in capsys.readouterr().out
