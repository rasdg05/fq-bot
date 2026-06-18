# -*- coding: utf-8 -*-
"""
FORWARD [retrieval-rolling] (online / memoria expansiva) — prueba de la PUERTA
DE LEAKAGE (embargo == max_bars).

El gate rolling camina la ventana AFTER en K tramos y, para cada tramo i,
reconstruye indice + umbral con la MEMORIA = todo evento cuya ETIQUETA ya se
resolvio antes de que el tramo i empiece. La regla de admision es:

    e.entry_index + max_bars  <  chunk_i_start

Estos tests fijan esa regla sobre las funciones PURAS que la implementan
(_rolling_memory_mask + _rolling_chunk_bounds), con datos sinteticos y sin deps
pesadas (sin red, sin lightgbm, sin StateIndex). Lo que se demuestra:

  1) TODO evento en la memoria del tramo i cumple entry_index + max_bars <
     chunk_i_start (resuelto antes de la frontera).
  2) NINGUN evento del tramo i o posterior entra en la memoria del tramo i.
  3) Un evento ABIERTO en la frontera (entry_index + max_bars == chunk_start, o
     >) queda EXCLUIDO: su desenlace aun no se conocia.
"""
import sys

import numpy as np

sys.argv = sys.argv[:1]  # el runner parsea sys.argv al importar utilidades de CLI
import tools.run_research_real as rr  # noqa: E402


# ---------------------------------------------------------------------------
# _rolling_memory_mask — la regla de embargo, aislada
# ---------------------------------------------------------------------------
def test_memory_mask_admits_only_resolved_before_boundary():
    """Todo evento admitido cumple entry_index + max_bars < chunk_start; ninguno
    a/despues de la frontera entra."""
    ei = np.array([0, 10, 20, 30, 40, 50], dtype="float64")
    max_bars = 5
    chunk_start = 30.0
    mask = rr._rolling_memory_mask(ei, max_bars, chunk_start)
    # admitidos: 0,10,20 (+5 => 5,15,25 < 30); excluidos: 30,40,50 (>= 30 al sumar)
    assert mask.tolist() == [True, True, True, False, False, False]
    # invariante duro: cada admitido resuelve ESTRICTAMENTE antes de la frontera
    assert np.all(ei[mask] + max_bars < chunk_start)
    # y ninguno NO-admitido lo cumple (la mascara es exacta, no conservadora de mas)
    assert np.all(ei[~mask] + max_bars >= chunk_start)


def test_event_open_at_boundary_is_excluded():
    """Un evento cuyo horizonte cierra JUSTO en la frontera (==) o despues NO entra:
    su pnl_r aun no se conocia al arrancar el tramo."""
    max_bars = 8
    chunk_start = 100.0
    # entry_index = 92 -> 92+8 = 100 == frontera (abierto en el limite): EXCLUIDO
    # entry_index = 91 -> 91+8 = 99  < 100 (cerrado un bar antes): ADMITIDO
    # entry_index = 95 -> 95+8 = 103 > 100 (claramente abierto): EXCLUIDO
    ei = np.array([91, 92, 95], dtype="float64")
    mask = rr._rolling_memory_mask(ei, max_bars, chunk_start)
    assert mask.tolist() == [True, False, False]


def test_memory_mask_empty_when_nothing_resolved():
    """Si ningun evento resolvio antes de la frontera, la memoria es vacia."""
    ei = np.array([100, 110, 120], dtype="float64")
    mask = rr._rolling_memory_mask(ei, max_bars=50, chunk_start=100.0)
    assert mask.tolist() == [False, False, False]


# ---------------------------------------------------------------------------
# _rolling_chunk_bounds — particion cronologica de AFTER
# ---------------------------------------------------------------------------
def test_chunk_bounds_partition_is_complete_and_disjoint():
    """Los tramos cubren TODO AFTER exactamente una vez (disjuntos + completos), y
    su frontera es el primer entry_index del tramo."""
    ei = np.arange(0, 60, dtype="float64")          # 60 eventos contiguos
    bounds = rr._rolling_chunk_bounds(ei, n_chunks=6)
    assert len(bounds) == 6
    union = np.zeros(len(ei), dtype=bool)
    prev_start = -np.inf
    for chunk_start, mask in bounds:
        assert not (union & mask).any()             # disjuntos
        union |= mask
        # la frontera es el MINIMO entry_index del tramo
        assert chunk_start == float(ei[mask].min())
        # tramos en orden cronologico estricto de frontera
        assert chunk_start > prev_start
        prev_start = chunk_start
    assert union.all()                              # completos


def test_chunk_bounds_unsorted_input_is_ordered_chronologically():
    """Aunque el AFTER llegue desordenado, los tramos se forman por orden de
    entry_index (cronologico), no por orden de fila."""
    ei = np.array([50, 10, 30, 20, 40, 0], dtype="float64")
    bounds = rr._rolling_chunk_bounds(ei, n_chunks=3)
    starts = [cs for cs, _ in bounds]
    assert starts == sorted(starts)                 # fronteras crecientes
    # el primer tramo contiene los entry_index mas pequenos (0 y 10)
    _, first_mask = bounds[0]
    assert set(ei[first_mask].tolist()) == {0.0, 10.0}


# ---------------------------------------------------------------------------
# INTEGRACION de las dos piezas: la invariante que el revisor audita
# ---------------------------------------------------------------------------
def test_no_event_from_chunk_i_or_later_enters_chunk_i_memory():
    """Sobre la particion REAL en tramos: para CADA tramo i, la memoria construida
    con _rolling_memory_mask (1) solo contiene eventos resueltos antes de la
    frontera de i, y (2) NO contiene ningun evento del tramo i ni de tramos
    posteriores (>= i). Esta es la garantia anti-fuga end-to-end."""
    n = 48
    ei = np.arange(0, n, dtype="float64")           # AFTER: entry_index 0..47
    max_bars = 6
    K = 6
    bounds = rr._rolling_chunk_bounds(ei, n_chunks=K)

    for i, (chunk_start, _chunk_mask) in enumerate(bounds):
        mem_mask = rr._rolling_memory_mask(ei, max_bars, chunk_start)
        # (1) todo lo de la memoria resolvio antes de la frontera del tramo i
        assert np.all(ei[mem_mask] + max_bars < chunk_start)
        # (2) NINGUN evento del tramo i o posterior esta en la memoria:
        #     construimos la mascara de "tramo >= i" y la cruzamos con la memoria.
        later = np.zeros(n, dtype=bool)
        for j in range(i, len(bounds)):
            later |= bounds[j][1]
        assert not (mem_mask & later).any(), (
            f"fuga: evento de tramo>={i} entro en la memoria del tramo {i}")
        # equivalente directo: el mayor entry_index de la memoria es < frontera
        if mem_mask.any():
            assert ei[mem_mask].max() < chunk_start


def test_memory_grows_monotonically_across_chunks():
    """La memoria EXPANSIVA no encoge: conforme avanzamos de tramo, el conjunto
    admitido es un superconjunto del anterior (re-ingiere lo que va resolviendo)."""
    n = 48
    ei = np.arange(0, n, dtype="float64")
    max_bars = 6
    bounds = rr._rolling_chunk_bounds(ei, n_chunks=6)
    prev = np.zeros(n, dtype=bool)
    for chunk_start, _m in bounds:
        cur = rr._rolling_memory_mask(ei, max_bars, chunk_start)
        # cada admitido previo sigue admitido (frontera mas tardia => mas resuelto)
        assert np.all(cur[prev]), "la memoria expansiva no debe perder eventos"
        prev = cur
