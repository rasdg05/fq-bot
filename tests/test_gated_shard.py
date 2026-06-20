# -*- coding: utf-8 -*-
"""Tests de la logica pura del gateado sharded (merge de ESTADOS DENSOS). El
end-to-end (sharded == sin-shardear) se valida con `gated_shard.py --verify` en el
VPS, donde hay datos OHLCV; aqui cubrimos lo determinista y sin red."""
import importlib.util
import os

import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "gated_shard",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "tools", "gated_shard.py"))
gs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gs)


def _states_df(ts_list, fired=False):
    """Estados densos: una fila por VELA (no solo fired). Lleva 'fired' (subset de
    senales) + el label forward, como produce bf.replay_states."""
    return pd.DataFrame([{"entry_ts": pd.Timestamp(t), "entry_index": i,
                          "fired": bool(fired), "pnl_r": 0.1 * i,
                          "close": 100.0 + i, "direction": "long"}
                         for i, t in enumerate(ts_list)])


def test_merge_states_dedup_y_sort(tmp_path):
    # dos shards con rangos que se tocan en 01-01 (dup por construccion del buffer)
    a = _states_df(["2024-01-03", "2024-01-01"])
    b = _states_df(["2024-01-02", "2024-01-01"])
    pa, pb = str(tmp_path / "a.parquet"), str(tmp_path / "b.parquet")
    a.to_parquet(pa)
    b.to_parquet(pb)
    m = gs._merge_states([pa, pb])
    # 3 estados unicos, ordenados por entry_ts, el dup 01-01 colapsado
    assert len(m) == 3
    assert list(m["entry_ts"]) == [pd.Timestamp("2024-01-01"),
                                   pd.Timestamp("2024-01-02"),
                                   pd.Timestamp("2024-01-03")]


def test_merge_states_disjuntos_no_pierden(tmp_path):
    # shards SIN solape (caso normal): la union = todos los estados, sin perdida
    a = _states_df(["2024-01-01", "2024-01-02"])
    b = _states_df(["2024-01-03", "2024-01-04"])
    pa, pb = str(tmp_path / "a.parquet"), str(tmp_path / "b.parquet")
    a.to_parquet(pa)
    b.to_parquet(pb)
    m = gs._merge_states([pa, pb])
    assert len(m) == 4
    assert m["entry_ts"].is_monotonic_increasing


def test_merge_states_solapados_no_duplican(tmp_path):
    # solape amplio entre shards adyacentes (buffer lookback/horizonte): cada
    # entry_ts repetido colapsa a 1 -> ni duplica ni pierde, queda ordenado.
    a = _states_df(["2024-01-01", "2024-01-02", "2024-01-03"])
    b = _states_df(["2024-01-02", "2024-01-03", "2024-01-04"])
    pa, pb = str(tmp_path / "a.parquet"), str(tmp_path / "b.parquet")
    a.to_parquet(pa)
    b.to_parquet(pb)
    m = gs._merge_states([pa, pb])
    assert list(m["entry_ts"]) == [pd.Timestamp("2024-01-0%d" % d)
                                   for d in (1, 2, 3, 4)]
    assert m["entry_ts"].is_monotonic_increasing
    # el merge denso preserva el subset fired (todas las velas estan presentes)
    assert "fired" in m.columns and len(m) == m["entry_ts"].nunique()


def test_merge_states_vacio_es_none(tmp_path):
    assert gs._merge_states([str(tmp_path / "noexiste.parquet")]) is None
