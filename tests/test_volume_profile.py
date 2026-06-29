# -*- coding: utf-8 -*-
"""Tests de volume_profile: POC/Value Area, posicion premium/value/discount,
y CAUSALIDAD del perfil por dia (prior_day vs developing)."""
import numpy as np
import pandas as pd

import volume_profile as vp


def _bars(prices, vols, start="2024-01-01", freq="5min"):
    prices = np.asarray(prices, float)
    ts = pd.date_range(start, periods=len(prices), freq=freq, tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "open": prices,
        "high": prices + 0.5,
        "low": prices - 0.5,
        "close": prices,
        "volume": np.asarray(vols, float),
    })


def test_poc_at_volume_concentration():
    # 80 velas en ~100 con vol alto, 20 dispersas con vol bajo -> POC ~100
    prices = [100.0] * 80 + list(np.linspace(95, 105, 20))
    vols = [100.0] * 80 + [1.0] * 20
    prof = vp.volume_profile(_bars(prices, vols), n_bins=50)
    assert prof is not None
    assert abs(prof.poc - 100.0) < 1.0, prof.poc
    assert prof.val <= prof.poc <= prof.vah


def test_value_area_brackets_poc_and_covers_target():
    rng = np.random.default_rng(0)
    # campana de precios alrededor de 200 -> VA estrecha alrededor del POC
    prices = 200 + rng.normal(0, 2, 600)
    vols = rng.uniform(50, 150, 600)
    df = _bars(prices, vols)
    prof = vp.volume_profile(df, n_bins=60, va_pct=0.70)
    assert prof is not None
    assert prof.val < prof.poc < prof.vah          # VA encierra al POC
    # la Value Area debe ser MAS angosta que el rango total (concentra el 70%)
    full = float(df["high"].max() - df["low"].min())
    assert (prof.vah - prof.val) < full


def test_vp_position_premium_value_discount():
    prof = vp.volume_profile(_bars([100.0] * 50, [10.0] * 50), n_bins=20)
    assert prof is not None
    assert vp.vp_position(prof.vah + 100, prof) == "premium"
    assert vp.vp_position(prof.val - 100, prof) == "discount"
    assert vp.vp_position(prof.poc, prof) == "value"
    assert prof.position(prof.poc) == "value"      # via dataclass


def test_prior_day_is_causal_and_separated():
    # Dia 1 (288 velas 5m) concentrado en 100; Dia 2 concentrado en 200.
    d1 = _bars([100.0] * 288, [100.0] * 288, start="2024-01-01")
    d2 = _bars([200.0] * 288, [100.0] * 288, start="2024-01-02")
    df = pd.concat([d1, d2], ignore_index=True)
    prof_prev = vp.prior_day_profile(df, n_bins=50)   # debe ver SOLO el dia 1
    prof_today = vp.daily_volume_profile(df, n_bins=50)  # debe ver SOLO el dia 2
    assert prof_prev is not None and prof_today is not None
    assert abs(prof_prev.poc - 100.0) < 1.5, prof_prev.poc
    assert abs(prof_today.poc - 200.0) < 1.5, prof_today.poc


def test_prior_day_none_without_two_days():
    df = _bars([100.0] * 50, [10.0] * 50)
    assert vp.prior_day_profile(df) is None            # un solo dia -> sin previo


def test_degenerate_inputs_return_none():
    assert vp.volume_profile(None) is None
    assert vp.volume_profile(pd.DataFrame()) is None
    # sin columna volume
    df_novol = _bars([100.0] * 10, [1.0] * 10).drop(columns=["volume"])
    assert vp.volume_profile(df_novol) is None
    # precio totalmente plano (pmax==pmin) -> sin rango -> None
    flat = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=10, freq="5min", tz="UTC"),
                         "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 5.0})
    assert vp.volume_profile(flat) is None
    assert vp.vp_position(123.0, None) == "unknown"


def test_flat_bars_counted_at_close():
    # velas planas (high==low) deben contar su volumen en el bin del close,
    # no perderse. Mezclamos planas en 110 con rango-velas en 90.
    flat_p = [110.0] * 40
    rng_p = list(np.linspace(89.5, 90.5, 40))
    df = _bars(flat_p + rng_p, [50.0] * 40 + [10.0] * 40)
    # forzamos las primeras 40 a ser planas
    df.loc[:39, "high"] = 110.0
    df.loc[:39, "low"] = 110.0
    prof = vp.volume_profile(df, n_bins=50)
    assert prof is not None
    # el volumen pesado plano en 110 domina -> POC cerca de 110
    assert abs(prof.poc - 110.0) < 1.5, prof.poc
