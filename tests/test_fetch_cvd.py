# -*- coding: utf-8 -*-
"""
fetch_cvd (CVD REAL / order-flow firmado) — pruebas SIN RED.

cvd.py es el PROXY (CVD estimado de OHLCV); fetch_cvd es el dato REAL (taker
buy/sell por barra, OKX rubik / Binance) — "el paso siguiente" que cvd.py anticipa.
El research: el order-flow FIRMADO mueve el precio (no el volumen sin firmar). Se
audita el feature puro (cvd_features), confirms_direction (el reemplazo del trigger
de volumen) y append_dedupe. Los fetchers son red -> se prueban en vivo.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import fetch_cvd as cvd  # noqa: E402


def _bars(buys, sells, t0=1_700_000_000_000, step=300_000):
    return pd.DataFrame({"ts": [t0 + i * step for i in range(len(buys))],
                         "buy_vol": list(map(float, buys)),
                         "sell_vol": list(map(float, sells))})


def test_cvd_sube_con_presion_compradora():
    f = cvd.cvd_features(_bars([100] * 30, [60] * 30), win=24)
    assert f["cvd"] > 0 and f["cvd_slope"] > 0 and f["imbalance"] > 0.5


def test_cvd_baja_con_presion_vendedora():
    f = cvd.cvd_features(_bars([40] * 30, [90] * 30), win=24)
    assert f["cvd_slope"] < 0 and f["imbalance"] < 0.5


def test_neutral_imbalance_medio():
    f = cvd.cvd_features(_bars([70] * 30, [70] * 30), win=24)
    assert abs(f["imbalance"] - 0.5) < 1e-6 and abs(f["cvd_slope"]) < 1e-6


def test_confirms_direction_long_y_short():
    buy_flow = cvd.cvd_features(_bars([100] * 30, [55] * 30), win=24)
    sell_flow = cvd.cvd_features(_bars([55] * 30, [100] * 30), win=24)
    assert cvd.confirms_direction(buy_flow, "long") is True
    assert cvd.confirms_direction(buy_flow, "short") is False
    assert cvd.confirms_direction(sell_flow, "short") is True
    assert cvd.confirms_direction(sell_flow, "long") is False
    assert cvd.confirms_direction(buy_flow, 1) is True
    assert cvd.confirms_direction(sell_flow, -1) is True


def test_append_dedupe_idempotente(tmp_path):
    path = str(tmp_path / "cvd.parquet")
    df = _bars([1, 2, 3], [1, 1, 1]).assign(ccy="BTC", exchange="okx")
    df = df[["ts", "ccy", "exchange", "buy_vol", "sell_vol"]]
    assert len(cvd.append_dedupe(path, df)) == 3
    assert len(cvd.append_dedupe(path, df)) == 3       # idempotente


def test_ventana_corta_no_crashea():
    f = cvd.cvd_features(_bars([10], [5]), win=24)
    assert f["imbalance"] == 0.5 and f["cvd_slope"] == 0.0
