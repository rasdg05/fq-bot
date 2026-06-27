# -*- coding: utf-8 -*-
"""validate_persistence_flow (F2): memoria larga del flujo firmado (persist/revert/hurst).
Puro; el DSR sobre data real lo corre el workflow."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import validate_persistence_flow as P  # noqa: E402


def _cvd(deltas, base_sell=10.0):
    """CVD sintético: cada delta -> buy=sell+delta (signo del flujo = signo del delta)."""
    n = len(deltas)
    sell = [base_sell] * n
    buy = [base_sell + d for d in deltas]
    return pd.DataFrame({"ts": list(range(0, n * 300000, 300000)),
                         "buy_vol": buy, "sell_vol": sell})


def test_autocorr_sum_positivo_en_corridas():
    # corridas de mismo signo (order-splitting) -> autocorrelación lag-1 positiva (la canónica)
    s = np.array([1, 1, 1, 1, -1, -1, -1, -1] * 3, float)
    tot, ac1 = P._autocorr_sum(s, 1)
    assert ac1 > 0 and abs(tot - ac1) < 1e-9       # k=1 -> la suma corta ES ac1


def test_hurst_persistente_mayor_que_ruido():
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 1, 256)
    walk = np.cumsum(rng.normal(0, 1, 256))             # integrado -> memoria larga
    assert P._hurst(walk) > P._hurst(noise)


def test_persist_confirma_continuacion_alineada():
    # corridas persistentes con presión NETA positiva -> netdir=+1, ac1>0 -> LONG
    deltas = ([3, 3, 3, 3, -1, -1] * 4)
    f = P.persistence_features(_cvd(deltas), win=24)
    assert f["ac1"] > 0 and f["netdir"] == 1
    assert P.persistence_confirms(f, 1, rule="persist", thr=0.0) is True
    assert P.persistence_confirms(f, -1, rule="persist", thr=0.0) is False


def test_hurst_rule_direccion_alineada():
    deltas = list(np.cumsum(np.ones(24)))               # flujo monotónicamente comprador
    f = P.persistence_features(_cvd(deltas), win=24)
    assert f["netdir"] == 1
    assert P.persistence_confirms(f, 1, rule="hurst", thr=-0.4) is True


def test_evaluate_y_ortogonalidad_no_crashea(tmp_path, capsys):
    base = 1_700_000_000_000
    n = 80
    ev_ts = [base + i * 3_600_000 for i in range(n)]
    cube = pd.DataFrame({"tp": ["tp4"] * n, "horizon": [576] * n, "entry_index": range(n),
                         "entry_ts": pd.to_datetime(ev_ts, unit="ms"),
                         "direction": [1, -1] * (n // 2),
                         "pnl_r": np.random.default_rng(4).normal(0.1, 1, n)})
    cube_p = tmp_path / "cube.parquet"; cube.to_parquet(cube_p)
    cvd_ts = list(range(base - 200 * 300000, base + n * 3_600_000, 300000))
    m = len(cvd_ts)
    cvd = pd.DataFrame({"ts": cvd_ts, "buy_vol": [60.0] * m, "sell_vol": [40.0] * m})
    cvd_p = tmp_path / "cvd.parquet"; cvd.to_parquet(cvd_p)
    df = P.evaluate(str(cube_p), str(cvd_p), rule="persist", thr=0.0)
    assert len(df) > 20 and df["cvd_conf"].notna().any()
    P.report_orthogonality(df, 0.50)
    assert "Ortogonalidad" in capsys.readouterr().out
