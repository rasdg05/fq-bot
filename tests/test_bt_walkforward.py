# -*- coding: utf-8 -*-
"""
bt_walkforward (etapa 3): folds walk-forward purgados con embargo. Pieza pura
-> tests directos sobre arrays t0/t1.
"""
import numpy as np
import pandas as pd
import pytest

import bt_walkforward as wf


def test_basic_walkforward_shape():
    # 50 eventos, cada etiqueta dura 2 unidades.
    t0 = np.arange(50, dtype=float)
    t1 = t0 + 2
    folds = wf.purged_walk_forward_splits(t0, t1, n_splits=5)
    assert len(folds) == 4                      # n_splits - 1
    for train_idx, test_idx in folds:
        assert len(train_idx) > 0 and len(test_idx) > 0
        # train siempre por debajo (pasado) del test
        assert t0[train_idx].max() < t0[test_idx].min()


def test_train_grows_expanding():
    t0 = np.arange(50, dtype=float)
    t1 = t0 + 1
    folds = wf.purged_walk_forward_splits(t0, t1, n_splits=5)
    sizes = [len(tr) for tr, _ in folds]
    assert sizes == sorted(sizes)               # ventana expansiva
    assert sizes[0] < sizes[-1]


def test_purge_removes_overlapping_label():
    # Etiquetas largas: t1 = t0 + 5. El borde del test debe purgar los eventos
    # cuyo t1 invade el periodo de test.
    t0 = np.arange(40, dtype=float)
    t1 = t0 + 5
    folds = wf.purged_walk_forward_splits(t0, t1, n_splits=4)
    for train_idx, test_idx in folds:
        wf.assert_no_leakage(t0, t1, train_idx, test_idx)


def test_embargo_widens_the_gap():
    t0 = np.arange(40, dtype=float)
    t1 = t0 + 1
    no_emb = wf.purged_walk_forward_splits(t0, t1, n_splits=4, embargo=0)
    with_emb = wf.purged_walk_forward_splits(t0, t1, n_splits=4, embargo=5)
    # Con embargo el train es <= que sin embargo (se descartan ejemplos al borde).
    for (tr_n, te_n), (tr_e, te_e) in zip(no_emb, with_emb):
        assert len(tr_e) <= len(tr_n)
        wf.assert_no_leakage(t0, t1, tr_e, te_e, embargo=5)


def test_no_leakage_holds_for_all_folds():
    rng = np.random.default_rng(0)
    t0 = np.sort(rng.uniform(0, 1000, size=200))
    t1 = t0 + rng.uniform(1, 10, size=200)
    folds = wf.purged_walk_forward_splits(t0, t1, n_splits=6, embargo=3)
    assert len(folds) >= 1
    for train_idx, test_idx in folds:
        wf.assert_no_leakage(t0, t1, train_idx, test_idx, embargo=3)
        # sin solape de indices
        assert len(np.intersect1d(train_idx, test_idx)) == 0


def test_min_train_skips_thin_folds():
    t0 = np.arange(20, dtype=float)
    t1 = t0 + 1
    folds = wf.purged_walk_forward_splits(t0, t1, n_splits=5, min_train=100)
    assert folds == []                          # ninguno alcanza 100 de train


def test_t1_before_t0_raises():
    with pytest.raises(ValueError):
        wf.purged_walk_forward_splits([0, 1, 2], [0, 0, 0], n_splits=2)


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        wf.purged_walk_forward_splits([0, 1], [0, 1, 2], n_splits=2)


def test_folds_from_labeled_dataframe():
    # DataFrame estilo salida de bt_labeler.
    n = 60
    df = pd.DataFrame({
        "entry_index": np.arange(n),
        "bars_held": np.full(n, 3),
        "outcome": ["win"] * n,
        "pnl_r": np.ones(n),
    })
    # mete dos filas sin resolver: deben excluirse
    df.loc[60] = {"entry_index": 60, "bars_held": np.nan,
                  "outcome": None, "pnl_r": np.nan}
    folds, valid_index = wf.folds_from_labeled(df, n_splits=5)
    assert len(folds) == 4
    assert len(valid_index) == 60               # la fila sin resolver fuera
    # los indices de los folds son posicionales sobre el subset valido
    for train_idx, test_idx in folds:
        assert train_idx.max() < len(valid_index)
        assert test_idx.max() < len(valid_index)


def test_assert_no_leakage_detects_injected_leak():
    t0 = np.array([0.0, 1, 2, 3, 4])
    t1 = t0 + 2
    # forzamos un train que invade el test
    train_idx = np.array([3])     # t1=5
    test_idx = np.array([2])      # test_start = 2
    with pytest.raises(AssertionError):
        wf.assert_no_leakage(t0, t1, train_idx, test_idx)
