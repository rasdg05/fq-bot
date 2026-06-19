# -*- coding: utf-8 -*-
"""liquidity_magnet (capa 1): VWAP daily, racimo de MAs + tell de divergencia,
enumeracion de imanes. Funciones puras -> tests directos."""
import pandas as pd
import pytest

import liquidity_magnet as lm


def _df(closes, vols=None):
    closes = [float(c) for c in closes]
    vols = [10.0] * len(closes) if vols is None else [float(v) for v in vols]
    return pd.DataFrame({"open": closes, "high": closes, "low": closes,
                         "close": closes, "volume": vols})


# --------------------------------------------------------------------------
# VWAP daily
# --------------------------------------------------------------------------
def test_daily_vwap_constante():
    assert lm.daily_vwap(_df([100.0] * 50)) == pytest.approx(100.0)


def test_daily_vwap_ponderado_por_volumen():
    # ultimas 2 velas: tp=100(vol1), tp=200(vol3) -> (100*1+200*3)/4 = 175
    df = _df([100.0, 200.0], vols=[1.0, 3.0])
    assert lm.daily_vwap(df, fallback_bars=2) == pytest.approx(175.0)


# --------------------------------------------------------------------------
# racimo de MAs + divergencia
# --------------------------------------------------------------------------
def test_ma_cloud_uptrend_precio_sobre_cloud_sin_divergencia():
    closes = list(range(50, 120))                 # subiendo
    c = lm.ma_cloud(_df(closes), periods=(5, 10))
    assert c is not None
    assert c["below"] is False                    # precio arriba del cloud
    assert c["low"] <= c["center"] <= c["high"]
    assert c["divergence"] is False


def test_ma_cloud_tell_de_divergencia():
    # precio cae con volumen ENORME en el fondo y rebota leve: queda DEBAJO del
    # cloud de MAs (que lagea arriba) pero ARRIBA del VWMA (volumen compro abajo).
    closes = [100.0] * 17 + [90.0, 90.0, 91.0]
    vols = [1.0] * 17 + [1000.0, 1000.0, 1.0]
    c = lm.ma_cloud(_df(closes, vols), periods=(5,))
    assert c["below"] is True                      # debajo del cloud (stack alto)
    assert c["vwma_above"] is True                 # arriba del VWMA (volumen compra)
    assert c["divergence"] is True                 # el tell exacto


# --------------------------------------------------------------------------
# enumeracion de imanes
# --------------------------------------------------------------------------
def test_enumerate_magnets_tipos_y_lados():
    closes = list(range(50, 120))
    mags = lm.enumerate_magnets(_df(closes), None, price=119.0)
    kinds = {m.kind for m in mags}
    assert {"vwap", "ma_cloud", "prior_high", "prior_low"} <= kinds
    assert all(m.side in ("above", "below") for m in mags)
    plow = next(m for m in mags if m.kind == "prior_low")
    assert plow.side == "below"                    # min previo (~50) bajo el precio


def test_enumerate_magnets_usa_pools_del_field():
    closes = list(range(50, 120))

    class _Pool:
        def __init__(self, p):
            self.price = p

    class _Field:
        pool_high = _Pool(130.0)
        pool_low = _Pool(60.0)

    by_kind = {m.kind: m for m in lm.enumerate_magnets(_df(closes), _Field(), 119.0)}
    assert by_kind["pool_high"].price == 130.0 and by_kind["pool_high"].side == "above"
    assert by_kind["pool_low"].price == 60.0 and by_kind["pool_low"].side == "below"
