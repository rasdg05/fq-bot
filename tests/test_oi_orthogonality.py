# -*- coding: utf-8 -*-
"""Cruce OI×CVD del validador: evaluate() puede traer cvd_conf y report_orthogonality
no crashea. La separación estadística la mide el workflow sobre data real; aquí sólo
verificamos el plumbing (que apile bien las dos confirmaciones por evento)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import validate_oi_flow as V  # noqa: E402


def _setup(tmp_path, n=80):
    base = 1_700_000_000_000
    ev_ts = [base + i * 3_600_000 for i in range(n)]
    cube = pd.DataFrame({
        "tp": ["tp4"] * n, "horizon": [576] * n, "entry_index": range(n),
        "entry_ts": pd.to_datetime(ev_ts, unit="ms"),
        "direction": [1, -1] * (n // 2),
        "pnl_r": np.random.default_rng(1).normal(0.1, 1, n)})
    cube_p = tmp_path / "cube.parquet"
    cube.to_parquet(cube_p)
    oi_ts = list(range(base - 200 * 300000, base + n * 3_600_000, 300000))
    oi = pd.DataFrame({"ts": oi_ts, "oi_usd": [1e9 * (1 + 0.0002 * i) for i in range(len(oi_ts))]})
    oi_p = tmp_path / "oi.parquet"
    oi.to_parquet(oi_p)
    cvd = pd.DataFrame({"ts": oi_ts, "buy_vol": [60.0] * len(oi_ts), "sell_vol": [40.0] * len(oi_ts)})
    cvd_p = tmp_path / "cvd.parquet"
    cvd.to_parquet(cvd_p)
    return str(cube_p), str(oi_p), str(cvd_p)


def test_evaluate_sin_cvd_no_trae_cvd_conf(tmp_path):
    cube, oi, _ = _setup(tmp_path)
    df = V.evaluate(cube, oi)
    assert len(df) > 20 and df["cvd_conf"].isna().all()


def test_evaluate_con_cvd_apila_ambas_confirmaciones(tmp_path):
    cube, oi, cvd = _setup(tmp_path)
    df = V.evaluate(cube, oi, cvd_path=cvd)
    assert len(df) > 20
    assert df["cvd_conf"].notna().any()          # el cruce trajo la confirmación CVD
    assert df["confirma"].any()                  # y la del OI


def test_report_orthogonality_no_crashea(tmp_path, capsys):
    cube, oi, cvd = _setup(tmp_path)
    df = V.evaluate(cube, oi, cvd_path=cvd)
    V.report_orthogonality(df, 0.50, 0.0)
    assert "Ortogonalidad" in capsys.readouterr().out
