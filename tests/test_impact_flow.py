# -*- coding: utf-8 -*-
"""validate_impact_flow (F1): residual de impacto raíz-cuadrada (coiled/extended/fragile).
Puro; el DSR sobre data real lo corre el workflow."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import validate_impact_flow as I  # noqa: E402


def _kl(close, tbb_frac, vol=100.0):
    """klines sintéticos: close list, taker_buy_base = tbb_frac*vol (constante)."""
    n = len(close)
    return pd.DataFrame({"ts": list(range(0, n * 300000, 300000)),
                         "close": close, "volume": [vol] * n,
                         "taker_buy_base": [tbb_frac * vol] * n})


def _absorb_close():
    # precio que OSCILA (σ real no-cero) con drift neto chico pese a la compra -> absorción
    return [100.0 + 2.0 * np.sin(0.9 * i) for i in range(24)]


def test_features_signo_netflow_y_residual():
    # compra agresiva (70% taker-buy) absorbida -> netflow>0, resid<0 (precio no sigue al flujo)
    f = I.impact_features(_kl(_absorb_close(), 0.70), win=24)
    assert f["netflow"] > 0 and f["pred"] > 0 and f["resid"] < 0 and f["n"] == 24


def test_coiled_confirma_long_con_absorcion():
    f = I.impact_features(_kl(_absorb_close(), 0.70), win=24)            # buy absorbido
    assert I.impact_confirms(f, 1, rule="coiled", thr=0.05) is True     # resorte comprimido -> LONG
    assert I.impact_confirms(f, -1, rule="coiled", thr=0.05) is False


def test_fragile_confirma_momentum_alineado():
    # compra agresiva con precio subiendo fuerte (con ruido) -> eff alto, flujo alcista -> LONG
    up = [100.0 * (1.01 ** i) + np.sin(i) for i in range(24)]
    f = I.impact_features(_kl(up, 0.70), win=24)
    assert f["eff"] > 0.05 and f["netflow"] > 0
    assert I.impact_confirms(f, 1, rule="fragile", thr=0.05) is True
    assert I.impact_confirms(f, -1, rule="fragile", thr=0.05) is False


def test_evaluate_con_cvd_y_ortogonalidad_no_crashea(tmp_path, capsys):
    base = 1_700_000_000_000
    n = 80
    ev_ts = [base + i * 3_600_000 for i in range(n)]
    cube = pd.DataFrame({"tp": ["tp4"] * n, "horizon": [576] * n, "entry_index": range(n),
                         "entry_ts": pd.to_datetime(ev_ts, unit="ms"),
                         "direction": [1, -1] * (n // 2),
                         "pnl_r": np.random.default_rng(3).normal(0.1, 1, n)})
    cube_p = tmp_path / "cube.parquet"; cube.to_parquet(cube_p)
    kl_ts = list(range(base - 200 * 300000, base + n * 3_600_000, 300000))
    m = len(kl_ts)
    kl = pd.DataFrame({"ts": kl_ts, "open": [100.0] * m, "high": [101.0] * m,
                       "low": [99.0] * m, "close": [100.0 + 0.01 * i for i in range(m)],
                       "volume": [100.0] * m, "taker_buy_base": [65.0] * m})
    kl_p = tmp_path / "kl.parquet"; kl.to_parquet(kl_p)
    cvd = pd.DataFrame({"ts": kl_ts, "buy_vol": [60.0] * m, "sell_vol": [40.0] * m})
    cvd_p = tmp_path / "cvd.parquet"; cvd.to_parquet(cvd_p)
    df = I.evaluate(str(cube_p), str(kl_p), rule="coiled", thr=0.0, cvd_path=str(cvd_p))
    assert len(df) > 20 and df["cvd_conf"].notna().any()
    I.report_orthogonality(df, 0.50)
    assert "Ortogonalidad" in capsys.readouterr().out
