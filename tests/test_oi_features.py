# -*- coding: utf-8 -*-
"""oi_features / oi_confirms — el medidor de posicionamiento (OI), a validar con DSR
igual que el CVD. Puro, sin red."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import fetch_agg_oi as oi  # noqa: E402


def _df(vals):
    return pd.DataFrame({"ts": list(range(0, len(vals) * 300000, 300000)), "oi_usd": vals})


def test_oi_features_sube():
    f = oi.oi_features(_df([100, 110, 120, 130, 140]), win=5)
    assert f["oi_slope"] > 0 and f["oi_change_pct"] > 0 and f["n"] == 5


def test_oi_features_baja():
    f = oi.oi_features(_df([140, 130, 120, 110, 100]), win=5)
    assert f["oi_slope"] < 0 and f["oi_change_pct"] < 0


def test_oi_features_pocas_barras_no_crashea():
    f = oi.oi_features(_df([100]), win=5)
    assert f["oi_slope"] == 0.0 and f["n"] == 1


def test_oi_confirms_solo_si_sube_sobre_umbral():
    rising = oi.oi_features(_df([100, 105, 110, 116, 122]), win=5)   # +22%
    flat = oi.oi_features(_df([100, 100, 100, 100, 100]), win=5)     # 0%
    assert oi.oi_confirms(rising, 1, min_change=0.0) is True
    assert oi.oi_confirms(rising, 1, min_change=0.30) is False       # exige +30%, no llega
    assert oi.oi_confirms(flat, 1, min_change=0.0) is False
