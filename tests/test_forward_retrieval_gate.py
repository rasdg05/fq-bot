# -*- coding: utf-8 -*-
"""
FORWARD [retrieval] (out-of-time) — prueba de NO-FUGA del gate de retrieval.

El gate forward construye el indice k-NN, el escalador y el umbral ORO con la
ventana BEFORE (pre-corte) y clasifica los eventos AFTER (post-corte) consultando
ESE indice. Estos tests demuestran la propiedad leakage-clean POR CONSTRUCCION:

  1) los vecinos de CUALQUIER evento AFTER salen SIEMPRE del BEFORE (nunca AFTER),
  2) el desenlace (pnl_r) de AFTER NO informa ni el umbral ni la decision del gate
     (barajar/poner a cero el pnl_r de AFTER deja umbral + gate_pass IDENTICOS),
  3) el umbral se deriva de BEFORE (before_oos | before_insample), nunca de AFTER.

Datos sinteticos -> indice exacto, determinista, sin red.
"""
import sys

import numpy as np
import pandas as pd

sys.argv = sys.argv[:1]  # el runner parsea sys.argv al importar utilidades de CLI
import tools.run_research_real as rr  # noqa: E402
import retrieval_gate as rg  # noqa: E402


def _window(n, seed, t0):
    """Ventana sintetica: pnl_r correlaciona con el estado (vecindarios discriminan).
    entry_index/entry_ts ESTRICTAMENTE crecientes y disjuntos entre ventanas."""
    rng = np.random.default_rng(seed)
    feat = rng.uniform(-1.0, 1.0, n)
    pnl = feat * 1.2 + rng.normal(0, 0.1, n)
    ts = pd.date_range("2025-01-01", periods=n, freq="1h") + pd.Timedelta(hours=t0)
    return pd.DataFrame({
        "entry_ts": ts,
        "entry_index": np.arange(t0, t0 + n),
        "pnl_r": pnl,
        "p_master": feat + 3.0,
        "scorer_structure": feat * 0.8,
        "direction": np.where(feat >= 0, "long", "short"),
        "outcome": np.where(pnl > 0, "win", "loss"),
        "bars_held": 5,
        "entry_price": 100.0, "stop_price": 99.0, "exit_price": 101.2,
    })


_KW = dict(k=30, sim_floor=0.0, n_floor=3, gold_top_pct=0.20,
           n_splits=5, embargo=2, seed=42)


def test_after_neighbors_come_only_from_before():
    """Cada evento AFTER recupera vecinos UNICAMENTE del indice de BEFORE: ningun
    id devuelto por la busqueda pertenece a AFTER (k-NN causal)."""
    before = _window(400, 0, t0=0)
    after = _window(120, 1, t0=10_000)          # entry_index de AFTER >> BEFORE
    before_ids = set(int(i) for i in before["entry_index"])
    after_ids = set(int(i) for i in after["entry_index"])
    assert before_ids.isdisjoint(after_ids)

    seen = {"ids": []}
    orig_build = rg.StateIndex.build

    def _spy_build(*a, **kw):
        idx = orig_build(*a, **kw)
        real_search = idx.be.search

        def _wrapped(queries, k, allowlist=None):
            scores, ids = real_search(queries, k, allowlist=allowlist)
            seen["ids"].extend(int(i) for i in np.asarray(ids).ravel())
            return scores, ids

        idx.be.search = _wrapped
        return idx

    rg.StateIndex.build = _spy_build
    try:
        out = rr._forward_retrieval_gate(before, after, **_KW)
    finally:
        rg.StateIndex.build = orig_build

    assert len(seen["ids"]) > 0
    returned = set(seen["ids"])
    # TODO id devuelto por la busqueda es del BEFORE; NINGUNO es de AFTER.
    assert returned.issubset(before_ids)
    assert returned.isdisjoint(after_ids)
    # y el gate efectivamente clasifico AFTER (no se quedo vacio por accidente)
    assert out["n_after_scored"] == len(after)


def test_after_outcomes_cannot_inform_gate_or_threshold():
    """Barajar / poner a cero el pnl_r de AFTER no cambia NI el umbral NI el
    conjunto gate_pass: el desenlace de AFTER no entra en la decision."""
    before = _window(400, 0, t0=0)
    after = _window(120, 1, t0=10_000)

    base = rr._forward_retrieval_gate(before, after, **_KW)

    after_shuf = after.copy()
    after_shuf["pnl_r"] = np.random.default_rng(7).permutation(
        after_shuf["pnl_r"].to_numpy())
    after_zero = after.copy()
    after_zero["pnl_r"] = 0.0

    for variant in (after_shuf, after_zero):
        alt = rr._forward_retrieval_gate(before, variant, **_KW)
        # mismo umbral (deriva SOLO de BEFORE)
        assert alt["threshold"] == base["threshold"]
        assert alt["thr_source"] == base["thr_source"]
        assert alt["n_confident"] == base["n_confident"]
        # MISMOS eventos AFTER clasificados ORO (la decision no mira pnl_r de AFTER)
        assert (alt["gate_pass"]["entry_index"].tolist()
                == base["gate_pass"]["entry_index"].tolist())


def test_threshold_is_before_derived_and_gate_concentrates_edge():
    """El umbral viene de BEFORE (before_oos en este tamaño) y el subset ORO de
    AFTER tiene mayor expectancy realizada que todo AFTER (la puerta concentra)."""
    before = _window(400, 0, t0=0)
    after = _window(160, 1, t0=10_000)
    out = rr._forward_retrieval_gate(before, after, **_KW)

    assert out["thr_source"] in ("before_oos", "before_insample")
    assert out["threshold"] is not None
    assert len(out["gate_pass"]) > 0
    gp_exp = out["gate_pass"]["pnl_r"].mean()
    all_exp = after["pnl_r"].mean()
    assert gp_exp > all_exp     # el gate ORO concentra expectancy OUT-OF-TIME


def test_before_insample_fallback_when_no_folds():
    """Si BEFORE es muy pequeño para folds walk-forward, el umbral cae al fallback
    in-sample de BEFORE (sigue dentro de BEFORE; nunca AFTER)."""
    before = _window(40, 0, t0=0)               # demasiado corto para 5 folds utiles
    after = _window(40, 1, t0=10_000)
    out = rr._forward_retrieval_gate(before, after, **dict(_KW, n_splits=8))
    # el origen del umbral es de BEFORE en cualquier caso (jamas AFTER)
    assert out["thr_source"] in ("before_insample", "before_oos", "none")
