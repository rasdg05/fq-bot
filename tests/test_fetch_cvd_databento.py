# -*- coding: utf-8 -*-
"""fetch_cvd_databento — adaptador trades CME (Databento) -> schema [ts,buy_vol,sell_vol]
del gate de order-flow. Blinda: agregación 5m correcta, ns->ms, 'N' sin agresor no suma,
side flexible + inversión configurable, y DROP-IN con fetch_cvd.cvd_features (el gate corre
sin cambios). El veredicto real (DSR) necesita datos de Databento + el cubo TradFi."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import fetch_cvd_databento as fx
import fetch_cvd

BAR = fx.BAR_MS
BASE_NS = 1_699_999_800_000 * 1_000_000   # bar-aligned (múltiplo de BAR_MS) en ns
MIN = 60 * 1_000_000_000                   # 1 min en ns


def _trades():
    return pd.DataFrame([
        {"ts_event": BASE_NS + 0 * MIN, "size": 10, "side": "B"},
        {"ts_event": BASE_NS + 1 * MIN, "size": 4,  "side": "A"},
        {"ts_event": BASE_NS + 2 * MIN, "size": 3,  "side": "N"},   # sin agresor -> nada
        {"ts_event": BASE_NS + 6 * MIN, "size": 7,  "side": "B"},
        {"ts_event": BASE_NS + 7 * MIN, "size": 2,  "side": "A"},
    ])


def test_agrega_por_barra_5m_y_dropea_N():
    g = fx.signed_bars(_trades())
    assert len(g) == 2
    assert g.iloc[0]["buy_vol"] == 10 and g.iloc[0]["sell_vol"] == 4   # 'N' no sumó
    assert g.iloc[1]["buy_vol"] == 7 and g.iloc[1]["sell_vol"] == 2


def test_ts_en_ms_floored_a_la_barra():
    g = fx.signed_bars(_trades())
    assert (g["ts"] % BAR == 0).all()
    assert g.iloc[1]["ts"] - g.iloc[0]["ts"] == BAR


def test_dropin_con_fetch_cvd_features():
    # El output alimenta el gate SIN cambios: CVD = cumsum(buy-sell) = (10-4)+(7-2) = 11
    g = fx.signed_bars(_trades())
    f = fetch_cvd.cvd_features(g, win=24)
    assert abs(f["cvd"] - 11.0) < 1e-9
    assert f["imbalance"] > 0.5 and 0.0 <= f["imbalance"] <= 1.0


def test_side_flexible_e_inversion():
    rows = pd.DataFrame([{"ts_event": BASE_NS, "size": 5, "side": "Bid"},
                         {"ts_event": BASE_NS, "size": 8, "side": "Ask"}])
    g = fx.signed_bars(rows)
    assert g.iloc[0]["buy_vol"] == 5 and g.iloc[0]["sell_vol"] == 8
    gi = fx.signed_bars(rows, buy_code="A", sell_code="B")   # correctness: --buy A --sell B
    assert gi.iloc[0]["buy_vol"] == 8 and gi.iloc[0]["sell_vol"] == 5


def test_ts_unit_ms_y_ns():
    g_ns = fx.signed_bars(pd.DataFrame([{"ts_event": BASE_NS, "size": 1, "side": "B"}]), ts_unit="ns")
    g_ms = fx.signed_bars(pd.DataFrame([{"ts_event": BASE_NS // 1_000_000, "size": 1, "side": "B"}]),
                          ts_unit="ms")
    assert g_ns.iloc[0]["ts"] == g_ms.iloc[0]["ts"]   # mismo bar por ambas rutas


def test_ts_event_como_datetime_columna_o_indice():
    # Databento .to_df(pretty_ts=True) devuelve ts_event como datetime (col o índice).
    idx = pd.to_datetime([BASE_NS, BASE_NS + MIN], utc=True)
    # como ÍNDICE (DatetimeIndex named ts_event)
    di = pd.DataFrame({"size": [10, 4], "side": ["B", "A"]}, index=idx)
    di.index.name = "ts_event"
    gi = fx.signed_bars(di)
    assert gi.iloc[0]["buy_vol"] == 10 and gi.iloc[0]["sell_vol"] == 4
    # como COLUMNA datetime
    dc = pd.DataFrame({"ts_event": idx, "size": [5, 8], "side": ["B", "A"]})
    gc = fx.signed_bars(dc)
    assert gc.iloc[0]["buy_vol"] == 5 and gc.iloc[0]["sell_vol"] == 8


def test_falta_ts_col_da_error_claro():
    import pytest
    with pytest.raises(KeyError):
        fx.signed_bars(pd.DataFrame({"size": [1], "side": ["B"]}))   # sin ts en col ni índice
