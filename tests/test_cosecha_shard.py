# -*- coding: utf-8 -*-
"""Tests de la lógica pura del sharding (merge + chunks). El replay end-to-end
(sharded == sin-shardear) se valida con `cosecha_shard.py --verify` en el VPS,
donde hay datos OHLCV; aquí cubrimos lo determinista."""
import importlib.util
import os

import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "cosecha_shard",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "tools", "cosecha_shard.py"))
cs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cs)


def _cube_df(ts_list, pnl):
    rows = []
    for ts, pr in zip(ts_list, pnl):
        for tp in ("tp1", "tp2"):
            for h in (96, 288):
                rows.append({"entry_ts": pd.Timestamp(ts), "tp": tp,
                             "horizon": h, "pnl_r": pr, "outcome": "win"})
    return pd.DataFrame(rows)


def test_merge_cubes_dedup_y_sort(tmp_path):
    a = _cube_df(["2024-01-03", "2024-01-01"], [0.1, 0.2])
    b = _cube_df(["2024-01-02", "2024-01-01"], [0.3, 0.2])  # 01-01 dup con a
    pa, pb = str(tmp_path / "a.parquet"), str(tmp_path / "b.parquet")
    a.to_parquet(pa); b.to_parquet(pb)
    m = cs.merge_cubes([pa, pb])
    # 3 eventos únicos (01,02,03) x 2tp x 2h = 12 filas (el dup 01-01 se quita)
    assert m["entry_ts"].nunique() == 3 and len(m) == 12
    assert list(m["entry_ts"].drop_duplicates()) == [
        pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-01-03")]


def test_chunks_tilea_contiguo():
    cks = cs.chunks(pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-09"), 4)
    assert len(cks) == 4
    assert cks[0][0] == pd.Timestamp("2024-01-01")
    assert cks[-1][1] == pd.Timestamp("2024-01-09")
    for i in range(3):
        assert cks[i][1] == cks[i + 1][0]   # sin huecos ni solapes


def test_merge_vacio_es_none(tmp_path):
    assert cs.merge_cubes([str(tmp_path / "noexiste.parquet")]) is None
