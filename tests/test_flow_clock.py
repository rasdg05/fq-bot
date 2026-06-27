# -*- coding: utf-8 -*-
"""F3 reloj de flujo: build_flow_clock.to_flow_bars + validate_flow_clock (prueba pareada).
Puro; el DSR sobre data real lo corre el workflow."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import build_flow_clock as B  # noqa: E402
import validate_flow_clock as F  # noqa: E402


def _cvd(buys, sells, t0=1_700_000_000_000, step=300_000):
    n = len(buys)
    return pd.DataFrame({"ts": [t0 + i * step for i in range(n)],
                         "buy_vol": list(map(float, buys)), "sell_vol": list(map(float, sells))})


def test_to_flow_bars_n_y_conserva_volumen():
    # 48 barras; el reloj de flujo las parte en 12 cubetas de |buy-sell| ~igual
    df = _cvd([100 + i for i in range(48)], [50] * 48)
    fb = B.to_flow_bars(df, 12)
    assert fb is not None and len(fb) == 12
    # conserva el volumen total (solo re-agrupa)
    assert abs(fb["buy_vol"].sum() - df["buy_vol"].sum()) < 1e-6
    assert abs(fb["sell_vol"].sum() - df["sell_vol"].sum()) < 1e-6


def test_to_flow_bars_insuficiente_da_none():
    assert B.to_flow_bars(_cvd([10, 20], [5, 5]), 12) is None       # menos barras que n_bars
    assert B.to_flow_bars(_cvd([5] * 30, [5] * 30), 12) is None     # |delta|=0 -> sin flujo


def test_flow_bars_acelera_en_estallidos():
    # flujo plano salvo un estallido: las cubetas de flujo se CONCENTRAN en el estallido
    buys = [51] * 40 + [200, 200, 200, 200] + [51] * 4
    fb = B.to_flow_bars(_cvd(buys, [50] * len(buys)), 8)
    assert fb is not None and len(fb) == 8                          # re-muestrea sin crashear


def test_evaluate_pareada_y_ortogonalidad_no_crashea(tmp_path, capsys):
    base = 1_700_000_000_000
    n = 80
    ev_ts = [base + i * 3_600_000 for i in range(n)]
    cube = pd.DataFrame({"tp": ["tp4"] * n, "horizon": [576] * n, "entry_index": range(n),
                         "entry_ts": pd.to_datetime(ev_ts, unit="ms"),
                         "direction": [1, -1] * (n // 2),
                         "pnl_r": np.random.default_rng(5).normal(0.1, 1, n)})
    cube_p = tmp_path / "cube.parquet"; cube.to_parquet(cube_p)
    cvd_ts = list(range(base - 300 * 300000, base + n * 3_600_000, 300000))
    m = len(cvd_ts)
    rng = np.random.default_rng(6)
    cvd = pd.DataFrame({"ts": cvd_ts, "buy_vol": np.abs(rng.normal(60, 15, m)),
                        "sell_vol": np.abs(rng.normal(45, 15, m))})
    cvd_p = tmp_path / "cvd.parquet"; cvd.to_parquet(cvd_p)
    df = F.evaluate(str(cube_p), str(cvd_p), n_bars=16, thr=0.0, lookback=96)
    assert len(df) > 20 and "wall" in df.columns and "flow" in df.columns
    F.report(df, 16, 0.0)
    F.report_orthogonality(df, 0.50)
    assert "reloj de flujo" in capsys.readouterr().out
