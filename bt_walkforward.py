# -*- coding: utf-8 -*-
"""
================================================================================
  BT WALKFORWARD - particion walk-forward con purga y embargo
  by RasDG_Sol + Claude

  Etapa 3 del harness de research. Genera folds (train, test) para validar
  out-of-sample SIN fuga de informacion (leakage), siguiendo a Lopez de Prado
  (Advances in Financial ML, cap. 7).

  El problema: cada etiqueta (triple-barrier) se resuelve usando velas FUTURAS,
  desde t0 (entrada, cuando la feature se conoce) hasta t1 (salida). Si un
  ejemplo de entrenamiento tiene su ventana [t0, t1] solapada con el periodo de
  test, ese ejemplo "vio el futuro" del test -> el backtest se infla y miente.

  La solucion (dos capas):
    1. PURGA: quitar del train todo ejemplo cuya etiqueta [t0, t1] se solape con
       el span temporal del test.
    2. EMBARGO: ademas, dejar un colchon temporal antes del test (correlacion
       serial), descartando ejemplos demasiado pegados al borde.

  Walk-forward (no combinatorio): el train es SIEMPRE pasado respecto al test.
  Pieza pura: opera sobre arrays t0/t1 (indices de vela o timestamps). No I/O.
================================================================================
"""
import logging

import numpy as np

log = logging.getLogger("bt_walkforward")


def purged_walk_forward_splits(t0, t1, n_splits=5, embargo=0, min_train=1):
    """Folds walk-forward purgados con embargo.

    t0, t1: array-like (len N). t0 = momento en que la feature se conoce
            (entrada); t1 = momento en que la etiqueta se resuelve (salida).
            Mismas unidades comparables (indices de vela enteros o timestamps
            numericos). Debe cumplirse t1 >= t0.
    n_splits: el eje temporal se parte en n_splits bloques contiguos por t0; se
              generan hasta n_splits-1 folds (cada bloque k>=1 es test, con su
              pasado como train).
    embargo: colchon en las MISMAS unidades que t. Un ejemplo de train solo se
             admite si su t1 <= (inicio_del_test - embargo).
    min_train: minimo de ejemplos de train para emitir el fold (si no, se salta).

    Devuelve lista de (train_idx, test_idx), arrays de indices posicionales en
    el orden original de t0/t1.
    """
    t0 = np.asarray(t0, dtype="float64")
    t1 = np.asarray(t1, dtype="float64")
    if len(t0) != len(t1):
        raise ValueError("t0 y t1 deben tener la misma longitud")
    if np.any(t1 < t0):
        raise ValueError("t1 debe ser >= t0 en todos los eventos")
    n = len(t0)
    if n == 0 or n_splits < 2:
        return []

    order = np.argsort(t0, kind="mergesort")     # estable; respeta empates
    blocks = np.array_split(order, n_splits)

    folds = []
    for k in range(1, len(blocks)):
        test_idx = blocks[k]
        if len(test_idx) == 0:
            continue
        test_start = float(t0[test_idx].min())
        cutoff = test_start - embargo

        # Train = pasado purgado + embargado: su etiqueta debe CERRAR ESTRICTAMENTE
        # antes del colchon. El '<' (no '<=') evita admitir un evento cuya etiqueta
        # cierra en la misma vela donde abre el test (comparten esa barra).
        train_mask = t1 < cutoff
        train_idx = np.where(train_mask)[0]

        # Garantia walk-forward: el train no comparte indices con el test.
        if len(train_idx):
            train_idx = np.setdiff1d(train_idx, test_idx, assume_unique=False)

        if len(train_idx) < min_train:
            continue
        folds.append((train_idx, np.sort(test_idx)))

    return folds


def folds_from_labeled(labeled, n_splits=5, embargo=0, min_train=1,
                       entry_col="entry_index", held_col="bars_held"):
    """Conveniencia: construye t0/t1 desde un DataFrame etiquetado y delega.

    t0 = entry_index; t1 = entry_index + bars_held (la vela donde cerro la
    etiqueta). Filas sin etiqueta resuelta (outcome nulo / bars_held nulo) se
    excluyen ANTES de partir. Devuelve (folds, valid_index) donde valid_index
    mapea las posiciones de los folds a las filas originales del DataFrame.
    """
    valid = labeled
    if "outcome" in labeled.columns:
        valid = labeled[labeled["outcome"].notna()]
    valid = valid[valid[held_col].notna()]
    valid_index = valid.index.to_numpy()

    t0 = valid[entry_col].to_numpy(dtype="float64")
    t1 = t0 + valid[held_col].to_numpy(dtype="float64")
    folds = purged_walk_forward_splits(
        t0, t1, n_splits=n_splits, embargo=embargo, min_train=min_train,
    )
    return folds, valid_index


def assert_no_leakage(t0, t1, train_idx, test_idx, embargo=0):
    """Verifica que ningun ejemplo de train solape (con embargo) el span del
    test. Lanza AssertionError si encuentra fuga. util en tests y CI.
    """
    t0 = np.asarray(t0, dtype="float64")
    t1 = np.asarray(t1, dtype="float64")
    if len(test_idx) == 0 or len(train_idx) == 0:
        return True
    test_start = float(t0[test_idx].min())
    test_end = float(t1[test_idx].max())
    cutoff = test_start - embargo
    for i in train_idx:
        # La etiqueta del train debe cerrar ESTRICTAMENTE antes del colchon.
        assert t1[i] < cutoff, (
            f"leakage: train idx {i} con t1={t1[i]} >= cutoff={cutoff} "
            f"(test_start={test_start}, embargo={embargo})"
        )
        # Y no debe caer dentro del span del test.
        assert not (t0[i] <= test_end and t1[i] >= test_start), (
            f"leakage: train idx {i} [{t0[i]},{t1[i]}] solapa test "
            f"[{test_start},{test_end}]"
        )
    return True
