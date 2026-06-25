# -*- coding: utf-8 -*-
"""
DEFLATED SHARPE RATIO (DSR) + PROBABILITY OF BACKTEST OVERFITTING (PBO) -- el
veredicto ANTI-SUERTE. Estos tests fijan las DOS propiedades que hacen util a la
matematica de Bailey & Lopez de Prado, sobre datos sinteticos puros:

  DSR -- DESCUENTA los multiples intentos:
    * Un Sharpe claramente real con N=1 -> DSR ~ 1 (nada que deshinchar).
    * EL MISMO Sharpe con N grande -> DSR ~ 0 (la barra del maximo-de-N lo come):
      con suficientes intentos, ese edge pudo ser el mas afortunado de N.
    * DSR decreciente en n_trials y en trials_sr_var (mas intentos / mas
      dispersos => mas facil que el mejor sea suerte => menos credito).

  PBO -- detecta el OVERFIT del ranking IS->OOS (CSCV):
    * Configs cuyo edge IN-SAMPLE se REVIERTE OUT-OF-SAMPLE (suerte, sin edge
      real) -> PBO alto (>= 0.5): el ganador IS no predice el OOS.
    * Una config genuinamente mejor en TODA la muestra -> PBO bajo (< 0.2): el
      ganador IS sigue ganando OOS (robusto).

Puro numpy. La precision de Phi/Phi^-1 con grado scipy se prueba aparte tras
importorskip('scipy'); el resto corre sobre el fallback erf/Acklam del modulo.
"""
import math

import numpy as np
import pytest

import deflated as d


# ===========================================================================
# DSR -- descuento por multiples intentos
# ===========================================================================
def _strong_sr_returns(seed=0, n=600, sr_per_period=0.13):
    """Serie con un Sharpe per-period CLARAMENTE real (mean/sd = sr) y casi
    normal: el caso donde el edge es genuino si NO hubiera multiples intentos."""
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, 1.0, n)
    r = (r - r.mean()) / r.std(ddof=1)          # estandariza exacto
    return r * 1.0 + sr_per_period               # mean=sr_per_period, sd=1


def test_dsr_high_when_single_trial_real_edge():
    """Sharpe fuerte + N=1 (un solo intento) -> DSR ~ 1: no hay seleccion que
    corregir, el edge se toma al pie de la letra."""
    r = _strong_sr_returns()
    out = d.deflated_sharpe_ratio(r, n_trials=1)
    assert out["sr0"] == 0.0                      # 1 intento: barra deshinchada = 0
    assert out["dsr"] > 0.95                       # claramente real
    assert out["T"] == len(r)
    # casi normal: skew ~ 0, kurtosis NO-excess ~ 3
    assert abs(out["skew"]) < 0.25
    assert abs(out["kurt"] - 3.0) < 0.6


def test_dsr_low_when_many_trials_same_edge():
    """EL MISMO Sharpe, pero declarando MUCHOS intentos -> DSR ~ 0: con N grande
    y dispersion realista, ese edge cabe dentro del maximo esperado por azar.
    Esta es LA prueba de que descuenta la suerte de probar N veces."""
    r = _strong_sr_returns()
    single = d.deflated_sharpe_ratio(r, n_trials=1)["dsr"]
    many = d.deflated_sharpe_ratio(r, n_trials=200, trials_sr_var=0.25)
    assert single > 0.95
    assert many["dsr"] < 0.05                      # la deflacion lo hunde
    assert many["sr0"] > 0.0                        # SR0 deshinchado es positivo
    assert many["sr0"] > single * 0                 # (sanity, SR0 no degenera a <0)


def test_dsr_monotonic_decreasing_in_n_trials():
    """A mas intentos, mayor la barra del maximo-de-N => DSR NO crece (decrece
    estrictamente mientras la barra siga mordiendo)."""
    r = _strong_sr_returns()
    prev = None
    for n in (1, 2, 5, 10, 30, 100, 300):
        dsr = d.deflated_sharpe_ratio(r, n_trials=n, trials_sr_var=0.20)["dsr"]
        if prev is not None:
            assert dsr <= prev + 1e-12             # monotono no-creciente
        prev = dsr
    # extremos: con N=1 alto, con N enorme hundido (decrecimiento real, no plano)
    hi = d.deflated_sharpe_ratio(r, n_trials=1, trials_sr_var=0.20)["dsr"]
    lo = d.deflated_sharpe_ratio(r, n_trials=300, trials_sr_var=0.20)["dsr"]
    assert hi > lo


def test_dsr_monotonic_decreasing_in_trials_sr_var():
    """A mayor DISPERSION de los Sharpes de los intentos, mas alto el maximo
    esperado por azar => DSR decrece. (N fijo.)"""
    r = _strong_sr_returns()
    prev = None
    for v in (0.001, 0.01, 0.05, 0.10, 0.25, 0.5):
        dsr = d.deflated_sharpe_ratio(r, n_trials=10, trials_sr_var=v)["dsr"]
        if prev is not None:
            assert dsr <= prev + 1e-12
        prev = dsr
    hi = d.deflated_sharpe_ratio(r, n_trials=10, trials_sr_var=0.001)["dsr"]
    lo = d.deflated_sharpe_ratio(r, n_trials=10, trials_sr_var=0.5)["dsr"]
    assert hi > lo


def test_dsr_default_var_flag_when_unspecified():
    """Si N>1 y no se pasa trials_sr_var, se usa el default conservador y se
    MARCA el flag para que el caller avise (no se deshincha 'en silencio')."""
    r = _strong_sr_returns()
    out = d.deflated_sharpe_ratio(r, n_trials=10)
    assert out.get("sr0_var_default") is True
    assert out["sr0"] > 0.0
    # con N=1 no hay nada que deshinchar y NO se marca el flag
    out1 = d.deflated_sharpe_ratio(r, n_trials=1)
    assert "sr0_var_default" not in out1
    assert out1["sr0"] == 0.0


def test_dsr_benchmark_raises_bar():
    """Un sr_benchmark por encima de SR0 sube la barra efectiva y baja el DSR."""
    r = _strong_sr_returns()
    base = d.deflated_sharpe_ratio(r, n_trials=1)["dsr"]
    raised = d.deflated_sharpe_ratio(r, n_trials=1, sr_benchmark=0.10)["dsr"]
    assert raised < base


def test_dsr_insufficient_sample_returns_none():
    out = d.deflated_sharpe_ratio([0.1], n_trials=1)
    assert out["dsr"] is None and out["sr"] is None


def test_expected_max_sharpe_monotone_both_args():
    """SR0 (max esperado de N normales) crece en N y en V; 0 si N<=1 o V<=0."""
    assert d.expected_max_sharpe(1, 0.25) == 0.0
    assert d.expected_max_sharpe(50, 0.0) == 0.0
    prev = -1.0
    for n in (2, 3, 5, 10, 50, 200, 1000):
        v = d.expected_max_sharpe(n, 0.25)
        assert v > prev                            # estrictamente creciente en N
        prev = v
    prev = -1.0
    for var in (0.01, 0.05, 0.25, 1.0, 4.0):
        v = d.expected_max_sharpe(10, var)
        assert v > prev                            # estrictamente creciente en V
        prev = v


# ===========================================================================
# PBO -- overfit del ranking IS->OOS (CSCV, Bailey et al. 2017)
# ===========================================================================
def _overfit_matrix(seed, T=240, C=16, edge_sd=0.6):
    """Mundo SIN edge real: cada config tiene una 'ventaja' aleatoria en la
    PRIMERA mitad que se REVIERTE en la segunda (suerte in-sample que no
    persiste). Media de toda la muestra ~ 0 por construccion. Es la firma
    canonica del overfit: el ganador IS es el perdedor OOS."""
    rng = np.random.default_rng(seed)
    half = T // 2
    M = rng.normal(0.0, 1.0, (T, C))
    mu = rng.normal(0.0, edge_sd, C)               # 'fit' a la primera mitad
    M[:half, :] += mu
    M[half:, :] -= mu                               # se revierte (sin edge real)
    return M


def _real_best_matrix(seed, T=240, C=16, real_edge=0.35):
    """Una config (col 0) genuinamente mejor en TODA la muestra; el resto ruido.
    El ganador IS deberia seguir ganando OOS -> PBO bajo."""
    rng = np.random.default_rng(seed)
    M = rng.normal(0.0, 1.0, (T, C))
    M[:, 0] += real_edge                            # edge real y persistente
    return M


def test_pbo_high_when_edge_is_pure_overfit():
    """Edge IS que se revierte OOS (sin edge real) -> PBO >= 0.5 en cada seed:
    el ranking in-sample no predice el out-of-sample."""
    for seed in range(6):
        out = d.probability_backtest_overfitting(_overfit_matrix(seed), n_splits=8)
        assert out["pbo"] is not None
        assert out["pbo"] >= 0.5, f"seed={seed} PBO={out['pbo']}"
        assert out["n_combos"] > 0


def test_pbo_low_when_one_config_is_genuinely_better():
    """Una config realmente mejor en toda la muestra -> PBO < 0.2 en cada seed:
    el ganador IS sigue ganando OOS (robusto, no overfit)."""
    for seed in range(6):
        out = d.probability_backtest_overfitting(_real_best_matrix(seed), n_splits=8)
        assert out["pbo"] is not None
        assert out["pbo"] < 0.2, f"seed={seed} PBO={out['pbo']}"


def test_pbo_overfit_strictly_higher_than_real_best():
    """Comparacion directa, mismo seed: el mundo overfit da PBO MUCHO mayor que
    el mundo con un ganador real."""
    for seed in range(4):
        hi = d.probability_backtest_overfitting(_overfit_matrix(seed), n_splits=8)["pbo"]
        lo = d.probability_backtest_overfitting(_real_best_matrix(seed), n_splits=8)["pbo"]
        assert hi > lo + 0.3


def test_pbo_samples_when_combinatorics_explode():
    """Con muchos grupos, C(S, S/2) explota; el modulo MUESTREA un subconjunto
    reproducible y lo documenta (sampled + n_combos_total)."""
    M = _real_best_matrix(0, T=400, C=20)
    out = d.probability_backtest_overfitting(M, n_splits=16, max_combos=400, seed=0)
    assert out.get("sampled") is True
    assert out["n_combos"] <= 400
    assert out["n_combos_total"] == math.comb(16, 8)
    # reproducible por seed
    out2 = d.probability_backtest_overfitting(M, n_splits=16, max_combos=400, seed=0)
    assert out2["pbo"] == out["pbo"]


def test_pbo_insufficient_inputs():
    """< 2 configs o filas < n_splits -> sin veredicto (pbo None), sin crash."""
    one_col = np.random.default_rng(0).normal(0, 1, (100, 1))
    assert d.probability_backtest_overfitting(one_col, n_splits=8)["pbo"] is None
    tiny = np.random.default_rng(0).normal(0, 1, (4, 5))
    assert d.probability_backtest_overfitting(tiny, n_splits=8)["pbo"] is None


# ===========================================================================
# Phi / Phi^-1 -- el fallback puro debe igualar a scipy con grado de embarque
# ===========================================================================
def test_phi_inv_matches_known_quantiles():
    """El Phi^-1 del modulo (scipy o fallback Acklam) acierta cuantiles tabulados
    a 1e-6 -- precision de sobra para el termino del maximo-de-N."""
    assert abs(d._Phi_inv(0.5) - 0.0) < 1e-9
    assert abs(d._Phi_inv(0.975) - 1.959963985) < 1e-6
    assert abs(d._Phi_inv(0.99) - 2.326347874) < 1e-6
    assert abs(d._Phi_inv(0.001) + 3.090232306) < 1e-6
    # Phi y Phi^-1 son inversas
    for x in (-2.5, -1.0, 0.0, 0.7, 2.3):
        assert abs(d._Phi_inv(d._Phi(x)) - x) < 1e-6


def test_fallback_matches_scipy_when_available():
    """Si scipy esta instalado, el fallback erf/Acklam coincide con scipy.norm en
    Phi y Phi^-1 (a 1e-6). Si no, se omite (el fallback es el unico camino)."""
    scipy_stats = pytest.importorskip("scipy.stats")
    snorm = scipy_stats.norm
    for x in np.linspace(-3.5, 3.5, 25):
        assert abs(d._Phi(x) - float(snorm.cdf(x))) < 1e-7
    for p in np.linspace(0.001, 0.999, 25):
        assert abs(d._Phi_inv(p) - float(snorm.ppf(p))) < 1e-6
