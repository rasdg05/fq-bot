# -*- coding: utf-8 -*-
"""
VALIDATION GATE — Deflated Sharpe / PSR / expected_max_sharpe / CPCV / PBO.

El lever #1 del research: deflactar el Sharpe por multiple-testing. Se audita
contra valores conocidos (normal CDF/PPF) y las propiedades clave: la vara sube
con N trials, el DSR baja con N, CPCV purga sin fugas, PBO alto sin skill.
Pure-python (sin scipy); cero red.
"""
import math

import numpy as np
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import validation_gate as v  # noqa: E402


# ----------------------------- normal CDF / PPF -----------------------------
def test_norm_cdf_valores_conocidos():
    assert abs(v.norm_cdf(0.0) - 0.5) < 1e-9
    assert abs(v.norm_cdf(1.96) - 0.9750) < 1e-3
    assert abs(v.norm_cdf(-1.96) - 0.0250) < 1e-3


def test_norm_ppf_inverso_del_cdf():
    for p in (0.05, 0.5, 0.95, 0.975, 0.999):
        assert abs(v.norm_cdf(v.norm_ppf(p)) - p) < 1e-6
    assert abs(v.norm_ppf(0.975) - 1.959964) < 1e-4


# ----------------------------- expected_max_sharpe -----------------------------
def test_vara_sube_con_n_trials():
    # más cosas probás -> más alto el Sharpe que el azar regala
    s = [v.expected_max_sharpe(n, 0.02) for n in (2, 10, 100, 1000)]
    assert all(s[i] < s[i + 1] for i in range(len(s) - 1))
    assert s[0] > 0


def test_vara_cero_si_no_hay_dispersion():
    assert v.expected_max_sharpe(100, 0.0) == 0.0


# ----------------------------- PSR / DSR -----------------------------
def test_dsr_baja_con_n_trials():
    r = 0.0006 + 0.01 * np.sin(np.arange(1500) * 0.07)   # serie determinista, media>0
    dsrs = [v.deflated_sharpe_ratio(r, n_trials=n, sr_trials_std=0.03)["dsr"]
            for n in (1, 10, 100, 1000)]
    assert all(dsrs[i] >= dsrs[i + 1] for i in range(len(dsrs) - 1))   # monótono no creciente
    assert dsrs[0] > dsrs[-1]


def test_dsr_fuerte_significativo_debil_no():
    fuerte = 0.002 + 0.005 * np.sin(np.arange(2000) * 0.05)   # media alta vs vol
    debil = 0.00002 + 0.02 * np.sin(np.arange(2000) * 0.05)   # media casi nula
    df = v.deflated_sharpe_ratio(fuerte, n_trials=20, sr_trials_std=0.02)
    dd = v.deflated_sharpe_ratio(debil, n_trials=20, sr_trials_std=0.02)
    assert df["dsr"] > dd["dsr"]
    assert df["significant"] is True
    assert dd["significant"] is False


def test_psr_sube_con_el_sharpe():
    a = v.probabilistic_sharpe_ratio(0.05, 0.0, 1000)
    b = v.probabilistic_sharpe_ratio(0.15, 0.0, 1000)
    assert b > a > 0.5


# ----------------------------- CPCV -----------------------------
def test_cpcv_numero_de_caminos_y_disjuntos():
    paths = v.cpcv_paths(600, n_groups=6, n_test_groups=2, embargo_frac=0.01)
    assert len(paths) == 15                       # C(6,2)
    for train, test in paths:
        assert set(train.tolist()).isdisjoint(set(test.tolist()))   # sin solape


def test_cpcv_purga_el_embargo():
    # ningún índice de train debe caer dentro del embargo de un test
    paths = v.cpcv_paths(600, n_groups=6, n_test_groups=2, embargo_frac=0.02)
    emb = max(1, int(0.02 * 600))
    train, test = paths[0]
    tset = set(test.tolist())
    for i in train.tolist():
        assert not any((i - emb) <= t <= (i + emb) for t in tset)


# ----------------------------- PBO -----------------------------
def test_pbo_en_rango_y_alto_sin_skill():
    # columnas periódicas sin edge real -> selección IS no predice OOS -> PBO alto
    T, N = 400, 8
    M = np.column_stack([np.sin(np.arange(T) * (0.05 + 0.01 * j)) for j in range(N)])
    p = v.pbo(M, n_splits=8)
    assert 0.0 <= p <= 1.0
    assert p > 0.5
