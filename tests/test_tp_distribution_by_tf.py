# -*- coding: utf-8 -*-
"""Nuevo comando admin /tphits (2026-07-21). Nace de una observacion de RasDG
mirando una lectura de ETH en 5m: "TP2 es el mas verga -- simetrico y
repetible, independiente de la direccion". Antes de tocar producto (battle
planner, /lectura) con esa hipotesis, se mide contra el ledger real:
get_tp_distribution_by_tf desglosa que outcome (tp1..tp4/sl/timeout) es mas
frecuente, por timeframe."""
import sqlite3

import pytest

import entropy_cognition as ev


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    db = tmp_path / "ledger.db"
    monkeypatch.setenv("FQ_LEDGER_PATH", str(db))
    import importlib
    importlib.reload(ev)
    ev.init_db()
    ev.migrate_schema_v2()
    ev.migrate_schema_v3()
    ev.migrate_schema_v4()
    ev.migrate_schema_v5()
    return ev


def _insert(ev_mod, tf_id, outcome, pnl_r, symbol="SOL"):
    conn = sqlite3.connect(ev_mod.DB_PATH)
    conn.execute("""
        INSERT INTO signals (ts_emitted, direction, entry_price, sl, tp1, tp2,
            tp3, tp4, p_master_raw, p_master_final, kappa_evo, session,
            w_clock, tier, pspace_count, bucket_key, snapshot_json,
            symbol, tf_id, ts_closed, outcome, pnl_r)
        VALUES ('2026-01-01T00:00:00+00:00','long',100,95,105,110,115,120,
                2.5,2.5,1.0,'ny_am_kz',0.8,'scalp',3,'x','{}',
                ?, ?, '2026-01-01T01:00:00+00:00', ?, ?)
    """, (symbol, tf_id, outcome, pnl_r))
    conn.commit()
    conn.close()


def test_sin_cierres_devuelve_vacio(ledger):
    assert ev.get_tp_distribution_by_tf() == {}
    assert ev.format_tp_distribution_telegram() is None


def test_agrupa_por_tf_id(ledger):
    _insert(ev, "5m", "tp2", 2.39)
    _insert(ev, "5m", "tp2", 2.39)
    _insert(ev, "5m", "sl", -1.0)
    _insert(ev, "15m", "tp1", 1.5)

    dist = ev.get_tp_distribution_by_tf()
    assert set(dist.keys()) == {"5m", "15m"}
    assert dist["5m"]["n"] == 3
    assert dist["5m"]["dist"] == {"tp2": 2, "sl": 1}
    assert dist["15m"]["n"] == 1


def test_top_tp_es_el_mas_frecuente_entre_wins(ledger):
    """La hipotesis de RasDG: en 5m, TP2 domina los wins."""
    _insert(ev, "5m", "tp2", 2.39)
    _insert(ev, "5m", "tp2", 2.39)
    _insert(ev, "5m", "tp2", 2.39)
    _insert(ev, "5m", "tp1", 1.5)
    _insert(ev, "5m", "sl", -1.0)

    dist = ev.get_tp_distribution_by_tf()
    assert dist["5m"]["top_tp"] == "tp2"
    assert dist["5m"]["top_tp_pct"] == pytest.approx(3 / 4)  # 3 de 4 wins


def test_tf_sin_ningun_win_top_tp_es_none(ledger):
    _insert(ev, "5m", "sl", -1.0)
    _insert(ev, "5m", "timeout", 0.0)

    dist = ev.get_tp_distribution_by_tf()
    assert dist["5m"]["top_tp"] is None
    assert dist["5m"]["top_tp_pct"] == 0
    assert dist["5m"]["win_rate"] == 0


def test_tf_id_null_cae_al_anchor_15m(ledger):
    """Señales pre-schema-v4 (tf_id NULL, columna no existia): mismo criterio
    que reconcile_outcomes -- caen al anchor historico 15m, no se pierden."""
    conn = sqlite3.connect(ev.DB_PATH)
    conn.execute("""
        INSERT INTO signals (ts_emitted, direction, entry_price, sl, tp1, tp2,
            tp3, tp4, p_master_raw, p_master_final, kappa_evo, session,
            w_clock, tier, pspace_count, bucket_key, snapshot_json,
            ts_closed, outcome, pnl_r)
        VALUES ('2026-01-01T00:00:00+00:00','long',100,95,105,110,115,120,
                2.5,2.5,1.0,'ny_am_kz',0.8,'scalp',3,'x','{}',
                '2026-01-01T01:00:00+00:00','tp1',1.5)
    """)
    conn.commit()
    conn.close()

    dist = ev.get_tp_distribution_by_tf()
    assert "15m" in dist
    assert dist["15m"]["n"] == 1


def test_stale_se_excluye(ledger):
    _insert(ev, "5m", "stale", 0.0)
    _insert(ev, "5m", "tp1", 1.5)

    dist = ev.get_tp_distribution_by_tf()
    assert dist["5m"]["n"] == 1
    assert "stale" not in dist["5m"]["dist"]


def test_symbol_none_mezcla_todos(ledger):
    _insert(ev, "5m", "tp2", 2.39, symbol="SOL")
    _insert(ev, "5m", "tp2", 2.39, symbol="ETH")

    dist = ev.get_tp_distribution_by_tf()
    assert dist["5m"]["n"] == 2


def test_symbol_filtra_uno_solo(ledger):
    _insert(ev, "5m", "tp2", 2.39, symbol="SOL")
    _insert(ev, "5m", "tp1", 1.5, symbol="ETH")

    dist_eth = ev.get_tp_distribution_by_tf(symbol="ETH")
    assert dist_eth["5m"]["n"] == 1
    assert dist_eth["5m"]["dist"] == {"tp1": 1}


def test_format_telegram_incluye_top_tp_y_simbolo(ledger):
    _insert(ev, "5m", "tp2", 2.39, symbol="ETH")
    _insert(ev, "5m", "tp2", 2.39, symbol="ETH")

    out = ev.format_tp_distribution_telegram()
    assert "[5m]" in out
    assert "TP2" in out
    assert "SOL+BTC+ETH" in out   # symbol=None -> mezcla, se rotula asi
    assert "<" in out or "&" not in out  # sanity: no rompe HTML basico


def test_format_telegram_con_symbol_lo_rotula(ledger):
    _insert(ev, "5m", "tp1", 1.5, symbol="BTC")
    out = ev.format_tp_distribution_telegram(symbol="BTC")
    assert "(BTC)" in out
