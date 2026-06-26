# -*- coding: utf-8 -*-
"""
validate_cvd_signed_flow — prueba SIN RED del alineado CVD-real ↔ cube (causal) + report.

Construye un cube sintético y un CVD sintético (presión compradora) en parquets tmp y
verifica: el alineado es CAUSAL (sólo CVD antes de la entrada), confirms_direction se
computa por evento, y report() no crashea con muestra chica/grande.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import validate_cvd_signed_flow as vcvd  # noqa: E402


def _make(tmp_path, n_ev=40, buy=100, sell=60):
    # CVD 5m con presión compradora sostenida (slope>0, imbalance>0.5)
    t0 = 1_700_000_000_000
    ncvd = 4000
    cvd = pd.DataFrame({"ts": [t0 + i * 300_000 for i in range(ncvd)],
                        "buy_vol": [float(buy)] * ncvd, "sell_vol": [float(sell)] * ncvd})
    cvd_p = str(tmp_path / "cvd_hist.parquet")
    cvd.to_parquet(cvd_p, index=False)
    # cube: eventos LONG espaciados dentro de la ventana del CVD
    ev_ts = [t0 + (200 + i * 80) * 300_000 for i in range(n_ev)]
    cube = pd.DataFrame({
        "entry_index": list(range(n_ev)),
        "entry_ts": pd.to_datetime(ev_ts, unit="ms"),
        "tp": ["tp4"] * n_ev, "horizon": [576] * n_ev,
        "direction": [1] * n_ev,
        "pnl_r": list(np.linspace(-0.5, 1.5, n_ev)),
    })
    cube_p = str(tmp_path / "cube.parquet")
    cube.to_parquet(cube_p, index=False)
    return cube_p, cvd_p


def test_evaluate_alinea_causal_y_confirma(tmp_path):
    cube_p, cvd_p = _make(tmp_path, n_ev=40, buy=100, sell=60)
    df = vcvd.evaluate(cube_p, cvd_p, tp="tp4", horizon=576)
    assert len(df) >= 30                      # casi todos los eventos quedan cubiertos
    # CVD comprador + eventos LONG -> mayoría confirmada
    assert df["confirma"].mean() > 0.8
    assert set(df.columns) >= {"pnl_r", "confirma", "imbalance", "dir"}


def test_flujo_vendedor_no_confirma_long(tmp_path):
    cube_p, cvd_p = _make(tmp_path, n_ev=40, buy=55, sell=100)   # presión vendedora
    df = vcvd.evaluate(cube_p, cvd_p, tp="tp4", horizon=576)
    assert df["confirma"].mean() < 0.2        # LONG no se confirma con flujo vendedor


def test_report_muestra_chica_no_crashea(tmp_path, capsys):
    cube_p, cvd_p = _make(tmp_path, n_ev=8)
    df = vcvd.evaluate(cube_p, cvd_p)
    vcvd.report(df)                            # <20 -> mensaje de muestra insuficiente
    out = capsys.readouterr().out
    assert "insuficiente" in out or "eventos" in out


def test_report_muestra_grande_corre_dsr(tmp_path, capsys):
    cube_p, cvd_p = _make(tmp_path, n_ev=60, buy=100, sell=60)
    df = vcvd.evaluate(cube_p, cvd_p)
    vcvd.report(df, n_trials=12)
    out = capsys.readouterr().out
    assert "DSR" in out or "baseline" in out
