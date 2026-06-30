# -*- coding: utf-8 -*-
"""Scaffold de Numerai Signals: reframe de los features validados de FQ a un ranking
[0,1] por ticker. Verifica el formato de submission + que los features se computan."""
import sys

import numpy as np

sys.path.insert(0, "tools")
import numerai_signals_features as nsf


def test_build_submission_format():
    sub = nsf.build_submission(nsf._synthetic_panel(n_tickers=20))
    assert list(sub.columns) == ["ticker", "signal"]
    assert len(sub) > 0
    assert sub.signal.between(0, 1).all()          # formato Numerai Signals


def test_feature_row_keys_and_finite():
    df = nsf._synthetic_panel(n_tickers=1)["T000"]
    f = nsf.feature_row(df)
    assert set(f) == {"kl_irrev", "poc_dist", "mom"}
    assert all(np.isfinite(v) for v in f.values())  # 400 barras -> todos computables


def test_raw_score_none_on_missing():
    assert np.isnan(nsf.raw_score({"kl_irrev": np.nan, "poc_dist": 1.0, "mom": 0.0}))
