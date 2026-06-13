# -*- coding: utf-8 -*-
"""F3 — selector TP/horizonte (bt_tp_selector).

Verifica la maquinaria: pivoteo del cubo, folds causales, y que con ESTRUCTURA
real (un feature determina qué celda paga) el selector SUPERA a la baseline fija.
Cubo sintético con entry_index espaciado (la cota causal t1=entry+horizonte exige
que los gaps entre eventos superen el horizonte, como en el cubo real esparso).
"""
import numpy as np
import pandas as pd

import bt_tp_selector as bts


def _cube(n=300, seed=0):
    """Dos regímenes por p_master: en uno paga tp3/576, en otro tp1/288."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        ei = i * 1000  # espaciado >> horizonte (576) -> folds causales válidos
        regime = i % 2
        pm = 5.0 if regime == 1 else 0.0
        if regime == 1:
            pnl = {("tp1", 288): 0.2 + rng.normal(0, 0.02),
                   ("tp3", 576): 1.0 + rng.normal(0, 0.02)}
        else:
            pnl = {("tp1", 288): 0.3 + rng.normal(0, 0.02),
                   ("tp3", 576): -0.5 + rng.normal(0, 0.02)}
        for (tp, h), r in pnl.items():
            rows.append({"entry_index": ei,
                         "entry_ts": pd.Timestamp("2024-01-01") + pd.Timedelta(minutes=5 * i),
                         "tp": tp, "horizon": h, "pnl_r": r,
                         "p_master": pm, "direction": 1,
                         "bars_held": h, "outcome": "win"})
    return pd.DataFrame(rows)


def test_events_and_cells_pivota():
    ev, cell_pnl, cells, base = bts.events_and_cells(_cube(n=10), baseline=("tp1", 288))
    assert len(ev) == 10 and cell_pnl.shape == (10, 2)
    assert ("tp1", 288) in cells and ("tp3", 576) in cells
    assert np.isfinite(base).all()


def test_selector_supera_baseline_con_estructura():
    cube = _cube()
    sel, rep = bts.run(cube, n_splits=5, embargo=8, k=20, min_neighbors=10)
    assert rep["selector"]["n"] > 0
    # el selector aprende qué celda paga por régimen -> supera la baseline fija
    assert rep["selector"]["expectancy_r"] > rep["baseline"]["expectancy_r"]
    assert rep["lift_r"] > 0.1
    # eligió la celda tp3/576 (la que paga en su régimen)
    assert any("tp3" in c for c in rep["cell_dist"])


def test_baseline_es_la_celda_fija():
    cube = _cube(n=60)
    _sel, rep = bts.run(cube, n_splits=4, embargo=8, k=15, min_neighbors=10)
    # baseline = tp1/288: su expectancy es la media de esa celda en el OOS
    assert rep["baseline"]["n"] == rep["selector"]["n"]  # MISMA población


def test_cubo_chico_no_crashea():
    _sel, rep = bts.run(_cube(n=8), n_splits=5, embargo=8, k=20)
    assert isinstance(rep, dict)  # folds vacíos -> n=0, sin crash


def test_abstencion_cae_a_baseline():
    """Si una celda no es estimable, el selector usa la baseline (misma población)."""
    sel, rep = bts.run(_cube(n=200), n_splits=4, embargo=8, k=15, min_neighbors=10)
    assert 0.0 <= rep["abstain_rate"] <= 1.0
    # sel_pnl nunca es NaN (siempre hay un valor: celda elegida o baseline)
    assert np.isfinite(sel["sel_pnl"].to_numpy()).all()
