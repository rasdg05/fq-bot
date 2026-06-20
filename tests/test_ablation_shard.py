# -*- coding: utf-8 -*-
"""Tests de la lógica pura de la poda sharded (merge de eventos + veredicto §6.6).
El end-to-end (sharded == sin-shardear) se valida con `ablation_shard.py --verify`
en el VPS, donde hay datos OHLCV; aquí cubrimos lo determinista y sin red."""
import importlib.util
import os

import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "ablation_shard",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "tools", "ablation_shard.py"))
ab = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ab)


def _ev_df(ts_list):
    return pd.DataFrame([{"entry_ts": pd.Timestamp(t), "entry_index": i,
                          "entry_price": 100.0 + i, "direction": "long"}
                         for i, t in enumerate(ts_list)])


def test_merge_events_dedup_y_sort(tmp_path):
    # dos shards con rangos que se tocan en 01-01 (dup por construcción del buffer)
    a = _ev_df(["2024-01-03", "2024-01-01"])
    b = _ev_df(["2024-01-02", "2024-01-01"])
    pa, pb = str(tmp_path / "a.parquet"), str(tmp_path / "b.parquet")
    a.to_parquet(pa)
    b.to_parquet(pb)
    m = ab._merge_events([pa, pb])
    # 3 eventos únicos, ordenados por entry_ts, el dup 01-01 colapsado
    assert len(m) == 3
    assert list(m["entry_ts"]) == [pd.Timestamp("2024-01-01"),
                                   pd.Timestamp("2024-01-02"),
                                   pd.Timestamp("2024-01-03")]


def test_merge_events_disjuntos_no_pierden(tmp_path):
    # shards SIN solape (caso normal): la unión = todos los eventos, sin pérdida
    a = _ev_df(["2024-01-01", "2024-01-02"])
    b = _ev_df(["2024-01-03", "2024-01-04"])
    pa, pb = str(tmp_path / "a.parquet"), str(tmp_path / "b.parquet")
    a.to_parquet(pa)
    b.to_parquet(pb)
    m = ab._merge_events([pa, pb])
    assert len(m) == 4
    assert m["entry_ts"].is_monotonic_increasing


def test_merge_events_vacio_es_none(tmp_path):
    assert ab._merge_events([str(tmp_path / "noexiste.parquet")]) is None


def test_verdict_regla_6_6():
    assert ab._verdict(0.05, 0.0).strip() == "VIVE"      # delta>0 -> aporta
    assert ab._verdict(-0.01, 0.30).strip() == "MATAR"   # no daña Y +cadencia
    assert ab._verdict(-0.01, 0.05).strip() == "QUEDA"   # inerte (poca cadencia)
    assert ab._verdict(0.0, 0.30).strip() == "MATAR"     # delta==0 Y +cadencia
    assert ab._verdict(0.0, 0.0).strip() == "QUEDA"      # delta==0 sin cadencia
    assert ab._verdict(None, 0.5).strip() == "?"         # sin métrica
