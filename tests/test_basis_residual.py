# -*- coding: utf-8 -*-
"""basis_residual — el gemelo TradFi del funding-percentil (XAU/NQ). Feature PURA para el
gate: residual de carry (basis observada - basis implícita por tasa) + mapeo direccional
con la MISMA semántica de percentil que el funding del bot (long<=0.5, short>=0.7). El
veredicto real (DSR/CPCV/PBO) necesita datos de Databento; esto sólo blinda la matemática."""
import math

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import basis_residual as br


def test_residual_cero_en_carry_fair_value():
    # front = spot * exp((r-q)*tau) -> basis observada == carry teórico -> residual 0
    r, q, tau = 0.05, 0.01, 0.25
    front = 100.0 * math.exp((r - q) * tau)
    assert abs(br.basis_residual(front, 100.0, r, q, tau)) < 1e-9


def test_signo_del_residual():
    r, q, tau = 0.05, 0.01, 0.25
    fair = 100.0 * math.exp((r - q) * tau)
    assert br.basis_residual(fair * 1.01, 100.0, r, q, tau) > 0   # rico  -> +
    assert br.basis_residual(fair * 0.99, 100.0, r, q, tau) < 0   # barato -> -


def test_percentil_igual_que_funding_pctl_live():
    # fracción de la historia <= actual (constructo idéntico a motor_paper.funding_pctl_live)
    assert br.residual_pctl(list(range(100)) + [1000]) == 1.0
    assert br.residual_pctl(list(range(100)) + [-1000]) <= 0.02
    assert br.residual_pctl([1, 2, 3]) is None          # < MIN_HIST -> None honesto


def test_mapeo_direccional_identico_a_funding_favorable():
    assert br.directional_signal(0.30) == 1             # residual bajo  -> LONG
    assert br.directional_signal(0.85) == -1            # residual alto  -> SHORT
    assert br.directional_signal(0.60) == 0             # zona neutra
    assert br.directional_signal(None) == 0             # sin dato -> neutro
    # umbrales configurables (el gate los barre)
    assert br.directional_signal(0.55, long_pctl=0.6) == 1


def test_rolling_es_causal_y_defensivo():
    res = [0.0] * 40 + [5.0]
    assert br.rolling_signal(res, len(res) - 1, n_hist=300) == -1   # extremo alto -> SHORT
    assert br.rolling_signal(res, 5) == 0                           # historia < MIN_HIST -> 0
    assert br.rolling_signal(res, 999) == 0                         # índice fuera de rango


def test_defensivo_inputs_basura_dan_nan():
    for bad in [(None, 1, 0, 0, 1), (1, 0, 0, 0, 1), (1, 1, 0, 0, 0), ("x", 1, 0, 0, 1)]:
        assert math.isnan(br.basis_residual(*bad))


def test_series_preserva_longitud_con_nan():
    fronts = [110.0, 0.0, 121.0]      # el del medio es inválido -> nan, no rompe
    out = br.residual_series(fronts, [100.0]*3, [0.05]*3, [0.0]*3, [1.0]*3)
    assert len(out) == 3 and math.isnan(out[1]) and not math.isnan(out[0])
