# -*- coding: utf-8 -*-
"""Regresion: check_outcome_against_candles compara fechas tz-safe.

Las velas OHLCV llegan en UTC pero tz-naive (datetime64[ms]); ts_emitted es
tz-aware. Antes esto reventaba con 'Invalid comparison between dtype=
datetime64[ms] and Timestamp' y spameaba ERROR [fq_entropy] reconcile signal.
Cubrimos ambas convenciones de la columna (naive y aware)."""
from datetime import datetime, timezone

import pandas as pd
import pytest

import entropy_cognition as ec


def _signal():
    ts = datetime(2026, 6, 10, 16, 0, 0, tzinfo=timezone.utc)
    return {"ts_emitted": ts.isoformat(), "direction": "long",
            "entry_price": 100.0, "sl": 95.0,
            "tp1": 105, "tp2": 110, "tp3": 115, "tp4": 120}


def _candles(tz_aware):
    idx = pd.to_datetime(["2026-06-10T16:05", "2026-06-10T16:20",
                          "2026-06-10T16:35"], utc=tz_aware)
    ts = idx if tz_aware else idx.astype("datetime64[ms]")
    return pd.DataFrame({"timestamp": ts, "high": [106, 103, 104],
                         "low": [99, 98, 97], "close": [105, 102, 103]})


@pytest.mark.parametrize("tz_aware", [False, True])
def test_outcome_tz_mismatch_no_raise(tz_aware):
    # No debe lanzar y debe resolver TP1 (high 106 >= tp1 105 en la 1a vela post).
    res = ec.check_outcome_against_candles(_signal(), _candles(tz_aware))
    assert res is not None
    assert res["outcome"] == "tp1"
