# -*- coding: utf-8 -*-
"""
SIZING — vol-targeting + Hierarchical Risk Parity (pure-numpy, sin scipy).

Audita: el peso de vol-targeting escala inverso a la vol (causal, capeado); HRP da
pesos válidos (suman 1, positivos) y asigna MÁS al activo independiente que a cada
uno de un par correlacionado (diversificación correcta sin invertir covarianza).
Determinista, sin red.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import sizing  # noqa: E402


def test_vol_target_weight_escala_inverso_a_la_vol():
    baja_vol = np.full(50, 0.001) + 0.0001 * np.sin(np.arange(50))
    alta_vol = 0.05 * np.sin(np.arange(50))
    w_baja = sizing.vol_target_weight(baja_vol, target_vol=0.01, lookback=20)
    w_alta = sizing.vol_target_weight(alta_vol, target_vol=0.01, lookback=20)
    assert w_baja > w_alta                       # baja vol -> más peso
    assert w_alta <= 3.0 and w_baja <= 3.0       # cap


def test_vol_target_weight_capea_y_no_crashea_corto():
    assert sizing.vol_target_weight([0.001], target_vol=0.01) == 1.0   # serie corta
    assert sizing.vol_target_weight(np.zeros(50), target_vol=0.01) == 3.0  # vol 0 -> cap


def test_vol_target_series_devuelve_in_out():
    t = np.arange(1000)
    r = 0.0003 + (0.004 + 0.003 * np.sin(t * 0.01)) * np.sin(t * 0.5)
    vt = sizing.vol_target_series(r, lookback=30)
    assert vt is not None
    assert "sharpe" in vt["in"] and "sharpe" in vt["out"]
    assert "vol_of_vol" in vt["out"]


def test_hrp_pesos_validos():
    R = np.column_stack([np.sin(np.arange(500) * 0.1 + k) for k in range(4)])
    w = sizing.hrp_weights(R)
    assert abs(w.sum() - 1.0) < 1e-9
    assert (w >= 0).all() and len(w) == 4


def test_hrp_diversifica_el_independiente():
    # A≈B (correlacionados) + C independiente -> C pesa más que A o B individual
    base = np.sin(np.arange(1200) * 0.1)
    A = base + 0.04 * np.cos(np.arange(1200) * 0.3)
    B = base + 0.04 * np.cos(np.arange(1200) * 0.31)
    C = np.cos(np.arange(1200) * 0.073)
    w = sizing.hrp_weights(np.column_stack([A, B, C]))
    assert w[2] > w[0] and w[2] > w[1]           # el indep pesa más que cada correlacionado
    assert abs(w.sum() - 1.0) < 1e-9


def test_hrp_un_solo_activo():
    w = sizing.hrp_weights(np.sin(np.arange(100) * 0.1).reshape(-1, 1))
    assert w.shape == (1,) and abs(w[0] - 1.0) < 1e-12
