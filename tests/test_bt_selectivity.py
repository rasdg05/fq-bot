# -*- coding: utf-8 -*-
"""Tests del GATE DE SELECTIVIDAD P2 ("operar solo el subset de alta expectancy").

Cubrimos la lógica PURA y determinista del selector (sin red, sin lightgbm, sin
replay): (a) `_select_mask` excluye las killzones estructurales correctas Y aplica
el umbral de score; (b) un caso sintético donde el subset SELECCIONADO tiene
expectancy claramente mayor que el universo completo (la tesis P2). La derivación
leakage-clean del umbral (OOF en OOS / ventana BEFORE en forward) y el end-to-end
del harness se ejercitan en el run real; aquí va lo unitario.

`_select_mask` / `SELECT_KILLZONE_EXCLUDE` viven en tools/run_research_real.py; se
cargan por importlib (como tests/test_ablation_shard.py). El import del módulo
arrastra dependencias opcionales del bot -> si faltan en este entorno, se SKIPea
el archivo entero en vez de fallar (mismo criterio que importorskip)."""
import importlib.util
import os

import numpy as np
import pandas as pd
import pytest

import bt_engine as eng

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "run_research_real", os.path.join(_ROOT, "tools", "run_research_real.py"))
rrr = importlib.util.module_from_spec(_SPEC)
try:
    _SPEC.loader.exec_module(rrr)
except Exception as e:  # pragma: no cover - depende del entorno
    pytest.skip(f"run_research_real no importable (deps opcionales del bot): {e}",
                allow_module_level=True)


# --------------------------------------------------------------------------
# (a) _select_mask: killzones estructurales + umbral de score
# --------------------------------------------------------------------------
def _df(kzs):
    return pd.DataFrame({"field_killzone": kzs})


def test_excludes_structural_killzones():
    # mismo score alto para todas; SOLO la pierna de killzone decide
    df = _df(["ny_am_kz", "london_open_kz", "fuera", "asia_open", "asia_kz"])
    scores = np.full(len(df), 0.9)
    m = rrr._select_mask(df, scores, score_thr=0.5)
    # fuera y asia_open caen; el resto pasa
    assert list(m) == [True, True, False, False, True]


def test_constant_is_the_declared_structural_prior():
    # el prior estructural está FIJO (no data-minado): exactamente estas dos
    assert rrr.SELECT_KILLZONE_EXCLUDE == {"fuera", "asia_open"}


def test_applies_score_threshold():
    # todas en killzone líquida; SOLO el umbral de score decide
    df = _df(["ny_am_kz"] * 5)
    scores = np.array([0.2, 0.49, 0.5, 0.7, 0.95])
    m = rrr._select_mask(df, scores, score_thr=0.5)
    assert list(m) == [False, False, True, True, True]   # >= es inclusivo


def test_combines_score_and_killzone_with_and():
    # alto score PERO killzone excluida -> NO entra; baja score en killzone OK -> NO entra
    df = _df(["fuera", "ny_am_kz", "ny_pm_kz", "asia_open"])
    scores = np.array([0.99, 0.10, 0.80, 0.99])
    m = rrr._select_mask(df, scores, score_thr=0.5)
    assert list(m) == [False, False, True, False]


def test_missing_killzone_column_degrades_to_score_only():
    df = pd.DataFrame({"other": [1, 2, 3]})         # sin field_killzone
    scores = np.array([0.4, 0.6, 0.9])
    m = rrr._select_mask(df, scores, score_thr=0.5)
    assert list(m) == [False, True, True]           # solo-score, sin crashear


def test_silver_bullet_and_open_killzones_pass():
    # los silver_bullet_* y *_open de killzones definidas NO están excluidos
    df = _df(["silver_bullet_ny_am", "silver_bullet_lo", "london_open_kz",
              "ny_pm_kz", "asia_kz"])
    scores = np.full(len(df), 1.0)
    m = rrr._select_mask(df, scores, score_thr=0.5)
    assert all(m)


# --------------------------------------------------------------------------
# (b) la tesis P2: el subset seleccionado tiene MAYOR expectancy que el total
# --------------------------------------------------------------------------
def test_selected_subset_has_higher_expectancy_than_full_set():
    """Caso sintético alineado con la tesis P2: el edge se concentra en el TOP
    del score y dentro de killzones líquidas; la media de TODAS es negativa.

    Construimos pnl_r de forma que (score alto AND killzone líquida) ganen y el
    resto pierda, y comprobamos que _select_mask aísla justo el subset rentable.
    """
    rng = np.random.default_rng(0)
    n = 200
    scores = rng.random(n)
    # killzone líquida ~mitad; el resto 'fuera'/'asia_open' (excluidas)
    kz = np.where(rng.random(n) < 0.5, "ny_am_kz",
                  np.where(rng.random(n) < 0.5, "fuera", "asia_open"))
    liquid = ~np.isin(kz, list(rrr.SELECT_KILLZONE_EXCLUDE))
    good = (scores >= 0.5) & liquid                 # el subset con edge real
    pnl_r = np.where(good, 1.0, -0.4)               # ganan los buenos, pierde el resto
    df = pd.DataFrame({"field_killzone": kz, "pnl_r": pnl_r})

    m = rrr._select_mask(df, scores, score_thr=0.5)
    exp_all = float(np.mean(pnl_r))
    exp_sel = float(np.mean(pnl_r[m]))

    assert exp_all < 0.0                            # la media de TODAS es negativa
    assert m.sum() > 0
    assert exp_sel > exp_all + 0.5                  # el subset es claramente mejor
    # _select_mask aisló EXACTAMENTE el subset bueno (score>=thr AND líquida)
    assert np.array_equal(m, good)


def test_selected_subset_higher_expectancy_via_engine_simulate():
    """Mismo veredicto medido con el motor REAL (eng.simulate, net de costes):
    la expectancy_r del subset seleccionado supera a la del universo completo."""
    met = pytest.importorskip("bt_metrics")
    n = 120
    rng = np.random.default_rng(7)
    scores = rng.random(n)
    kz = np.where(rng.random(n) < 0.6, "london_open_kz", "fuera")
    liquid = ~np.isin(kz, list(rrr.SELECT_KILLZONE_EXCLUDE))
    good = (scores >= 0.5) & liquid
    # trades resueltos: ganadores salen en TP (>entry), perdedores en stop.
    entry = np.full(n, 100.0)
    stop = np.full(n, 99.0)
    exit_px = np.where(good, 102.0, 99.0)           # +2R buenos, -1R resto
    outcome = np.where(good, "win", "loss")
    trades = pd.DataFrame({
        "entry_index": np.arange(n), "entry_price": entry, "stop_price": stop,
        "exit_price": exit_px, "direction": eng.LONG, "bars_held": 5.0,
        "outcome": outcome, "field_killzone": kz,
    })
    cost = eng.CostModel(taker_fee=0.0, slippage_bps=0.0, apply_funding=False)

    def _exp(sub):
        res = eng.simulate(sub, cost=cost)
        return met.metrics_from_result(res).get("expectancy_r")

    m = rrr._select_mask(trades, scores, score_thr=0.5)
    exp_all = _exp(trades)
    exp_sel = _exp(trades[m])
    assert exp_all < 0.0 < exp_sel                  # all negativa, selected positiva
