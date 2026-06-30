# -*- coding: utf-8 -*-
"""Pipeline Numerai Crypto (ruta A): fetcher-schema -> panel -> submission CSV.
Verifica el recorrido end-to-end con data sintética (sin red) y el formato de submission."""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "tools")
import numerai_crypto_pipeline as ncp


def test_pipeline_self_test():
    assert ncp._self_test() == 0          # end-to-end sintético, sin red


def test_submission_columns_and_range(tmp_path):
    rng = np.random.default_rng(1)
    n = 300
    ts = 1_700_000_000_000 + np.arange(n) * 86_400_000   # ms, barras diarias
    uni = {}
    for i in range(6):
        c = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
        pd.DataFrame({"ts": ts, "open": c, "high": c * 1.01, "low": c * 0.99,
                      "close": c, "volume": rng.uniform(1e3, 1e4, n)}).to_parquet(
            tmp_path / ("kl_hist_S%dUSDT.parquet" % i), index=False)
        uni["S%d" % i] = "S%dUSDT" % i
    sub = ncp.build_panel_csv(uni, str(tmp_path), str(tmp_path / "s.csv"))
    assert list(sub.columns) == ["symbol", "signal"]
    assert sub.signal.between(0, 1).all() and len(sub) >= 1
    assert (tmp_path / "s.csv").exists()
