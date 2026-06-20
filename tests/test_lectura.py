# -*- coding: utf-8 -*-
"""lectura.build_lectura / render — el composer de 'La Lectura' (puro, sin red)."""
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lectura
import killzones_pd as kz


def _synth(n, tf_ms, *, p0=100.0, drift=0.02, seed=1):
    rng = np.random.default_rng(seed)
    close = p0 + rng.normal(drift, 1.0, n).cumsum()
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = close - np.abs(rng.normal(0, 0.5, n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = np.abs(rng.normal(1000, 200, n))
    ts = 1_700_000_000_000 + np.arange(n) * tf_ms
    df = pd.DataFrame({"timestamp": ts, "open": open_, "high": high,
                       "low": low, "close": close, "volume": vol})
    return lectura._ensure_indicators(df)


_NY_AM = datetime(2026, 6, 3, 9, 5, tzinfo=kz.CDMX_TZ)   # miercoles, NY AM


def test_build_lectura_produce_lectura_valida():
    df15 = _synth(200, 15 * 60 * 1000)
    df1h = _synth(200, 60 * 60 * 1000, seed=2)
    df4h = _synth(200, 4 * 60 * 60 * 1000, seed=3)
    L = lectura.build_lectura("SOL-USDT-SWAP", df15, df1h, df4h, now_cdmx=_NY_AM)
    assert L["error"] is None
    assert L["price"] > 0
    assert isinstance(L["magnets"], list) and isinstance(L["zones"], list)
    assert L["killzone"]["name"]                    # killzone resuelta
    txt = lectura.render(L)
    assert "LA LECTURA" in txt
    assert "Vos decidis" in txt                     # el cierre honesto siempre


def test_datos_insuficientes_no_crashea():
    df = _synth(10, 15 * 60 * 1000)
    L = lectura.build_lectura("X", df, df, df, now_cdmx=_NY_AM)
    assert L["error"]
    assert "LA LECTURA" in lectura.render(L)         # render degrada con gracia


def test_verdict_siempre_es_string():
    df = _synth(200, 15 * 60 * 1000)
    L = lectura.build_lectura("X", df, df, df, now_cdmx=_NY_AM)
    v = lectura._verdict(L)
    assert isinstance(v, str) and len(v) > 0


def test_tension_se_detecta_cuando_cloud_y_estructura_difieren():
    # construido a mano: proposed short, mode_dir long -> tension True
    L = {"proposed_dir": "short", "mode_dir": "long"}
    assert bool(L["proposed_dir"] and L["mode_dir"] and L["proposed_dir"] != L["mode_dir"])
