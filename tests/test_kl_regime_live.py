# -*- coding: utf-8 -*-
"""motor_paper.kl_regime_live: filtro de régimen KL-bajo en vivo (sobre la ventana de precio
que el bot ya tiene). Defensivo, sin red. El cableado al broadcast es env-gated (FQ_KL_FILTER)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import motor_paper as mp  # noqa: E402


def test_low_irrev_es_low_true():
    f = mp.kl_regime_live(np.ones(80), thr=0.34)        # serie plana -> irrev 0 -> reversible
    assert f is not None and f["low"] is True and f["irrev"] == 0.0


def test_asimetrica_tiene_irrev_positiva():
    saw = np.array(([0, 1, 2, 3, 4, 5, 6, 7] * 8), float)   # diente de sierra -> irreversible
    f = mp.kl_regime_live(saw, thr=0.0)
    assert f is not None and f["irrev"] > 0.0 and f["low"] is False    # irrev > thr=0 -> NO low


def test_thr_decide_el_corte():
    saw = np.array(([0, 1, 2, 3, 4, 5, 6, 7] * 8), float)
    assert mp.kl_regime_live(saw, thr=100.0)["low"] is True     # umbral altísimo -> todo es low
    assert mp.kl_regime_live(saw, thr=-1.0)["low"] is False     # umbral negativo -> nada es low


def test_ventana_corta_y_basura_dan_none():
    assert mp.kl_regime_live(np.ones(8)) is None                # < 16
    assert mp.kl_regime_live([float("nan")] * 40) is None       # sin datos finitos


def test_thr_default_desde_env(monkeypatch):
    monkeypatch.setenv("FQ_KL_THR", "0.01")
    saw = np.array(([0, 1, 2, 3, 4, 5, 6, 7] * 8), float)
    assert mp.kl_regime_live(saw)["low"] is False               # irrev > 0.01
