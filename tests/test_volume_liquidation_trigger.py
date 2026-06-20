# -*- coding: utf-8 -*-
"""volume_liquidation_trigger: confirma el disparo por VOLUMEN (+ LIQUIDACIONES),
reemplazando el veto del scorer over-fit. Funciones puras -> tests directos."""
import pandas as pd
import pytest

import volume_liquidation_trigger as vlt


def _df(vols):
    n = len(vols)
    return pd.DataFrame({"open": [1.0] * n, "high": [1.0] * n, "low": [1.0] * n,
                         "close": [1.0] * n, "volume": list(vols)})


# --------------------------------------------------------------------------
# volume_surge_score
# --------------------------------------------------------------------------
def test_volume_surge_alto_cuando_hay_surge():
    # baseline 100, ultimas 3 a 200 -> ratio 2x >= surge_mult(1.4) -> 1.0
    s, _ = vlt.volume_surge_score(_df([100.0] * 20 + [200.0] * 3), surge_mult=1.4)
    assert s == pytest.approx(1.0)


def test_volume_surge_cero_sin_exceso():
    s, _ = vlt.volume_surge_score(_df([100.0] * 23), surge_mult=1.4)
    assert s == 0.0


def test_volume_surge_lineal_entremedio():
    # recent 1.2x baseline, surge_mult 1.4 -> (1.2-1)/(1.4-1)=0.5
    s, _ = vlt.volume_surge_score(_df([100.0] * 20 + [120.0] * 3), surge_mult=1.4)
    assert s == pytest.approx(0.5, abs=1e-6)


def test_volume_surge_sin_data_es_cero():
    s, r = vlt.volume_surge_score(None)
    assert s == 0.0 and "sin volume" in r
    assert vlt.volume_surge_score(_df([100.0] * 5))[0] == 0.0   # pocas velas


# --------------------------------------------------------------------------
# liquidation_fuel_score (tesis momentum por default)
# --------------------------------------------------------------------------
def test_liq_fuel_momentum_long_favorecido_por_shorts_liquidados():
    snap = {"fresh": True, "intensity": 0.8, "skew": 1.0}   # todo SHORT liquidado
    assert vlt.liquidation_fuel_score(snap, "long")[0] == pytest.approx(0.8)
    assert vlt.liquidation_fuel_score(snap, "short")[0] == 0.0


def test_liq_fuel_sin_feed_o_stale_es_cero():
    assert vlt.liquidation_fuel_score(None, "long")[0] == 0.0
    stale = {"fresh": False, "intensity": 1.0, "skew": 1.0}
    assert vlt.liquidation_fuel_score(stale, "long")[0] == 0.0


# --------------------------------------------------------------------------
# confirm (gate que reemplaza al scorer)
# --------------------------------------------------------------------------
def test_confirm_vol_only_pasa_con_surge():
    ok, reason, score = vlt.confirm(_df([100.0] * 20 + [200.0] * 3), None, "long",
                                    min_confirm=0.30)
    assert ok and score == pytest.approx(1.0) and "vol-only" in reason


def test_confirm_bloquea_sin_surge():
    ok, _, score = vlt.confirm(_df([100.0] * 23), None, "long", min_confirm=0.30)
    assert not ok and score == 0.0


def test_confirm_blend_vol_y_liq():
    snap = {"fresh": True, "intensity": 1.0, "skew": 1.0}   # short liq -> fuel LONG
    ok, reason, score = vlt.confirm(_df([100.0] * 20 + [200.0] * 3), snap, "long",
                                    min_confirm=0.30)
    assert ok and score == pytest.approx(1.0) and "vol+liq" in reason
