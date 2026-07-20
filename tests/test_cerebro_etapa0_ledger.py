# -*- coding: utf-8 -*-
"""Cerebro Etapa 0 (2026-07-20, pedido de RasDG): "cerrar el gap del ledger
BTC/ETH". Antes, BTC y ETH se broadcasteaban a clientes pero su UNICO
registro era el motor paper de 1 TP -- una senal podia salir a VIP y no
quedar en ningun registro con outcome verificable (MEMORY/ESTADO.md).

Fix: columna `symbol` (migrate_schema_v5, additiva, filas viejas='SOL') +
`log_signal(signal_data, symbol=...)` + `_record_vip_signal` (fq_bot_v3_2)
graban BTC/ETH en el MISMO ledger rico (4 TP) que SOL.

Riesgo real identificado y cerrado: TODA la maquinaria de self-audit /
kappa-evolucion / entropia de SOL vive en las MISMAS tablas -- sin aislar
por symbol, un fire de BTC con el mismo bucket_key que uno de SOL habria
contaminado el modulador kappa_evo EN VIVO de SOL, el track record de
/resultados (client-facing), y el prompt de self-audit de Opus. Estos tests
sellan que CADA una de esas superficies sigue leyendo SOLO SOL por default
(byte-identico a antes de esta migracion), mientras BTC/ETH acumulan su
propio track record en paralelo, sin contaminar ni ser ignorados."""
import sqlite3

import pytest

import entropy_cognition as ev


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    """Ledger temporal, esquema completo via init_db + todas las migraciones
    (igual que arranca el bot real)."""
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


def _sig(**overrides):
    base = {
        "direction": "long", "entry": 100.0, "sl": 95.0,
        "tp1": 105.0, "tp2": 110.0, "tp3": 115.0, "tp4": 120.0,
        "p_master_raw": 2.5, "p_master_final": 2.5, "kappa_evo": 1.0,
        "session": "ny_am_kz", "w_clock": 0.8, "pspace_count": 3,
        "snapshot": {},
    }
    base.update(overrides)
    return base


# ============================================================
# Migracion: additiva, idempotente, default SOL
# ============================================================
def test_migrate_v5_agrega_columna_symbol_default_sol(ledger):
    conn = sqlite3.connect(ev.DB_PATH)
    cols = {r[1]: r for r in conn.execute("PRAGMA table_info(signals)")}
    conn.close()
    assert "symbol" in cols
    # DEFAULT 'SOL' visible en el PRAGMA (columna dflt_value, indice 4)
    assert cols["symbol"][4] == "'SOL'"


def test_migrate_v5_es_idempotente(ledger):
    ev.migrate_schema_v5()
    ev.migrate_schema_v5()  # no debe explotar ni duplicar la columna


def test_filas_viejas_sin_symbol_explicito_caen_a_sol(ledger):
    """Una fila insertada por log_signal_v2 (que NO conoce 'symbol') debe
    quedar symbol='SOL' via el DEFAULT de la columna, sin tocar su INSERT."""
    conn = sqlite3.connect(ev.DB_PATH)
    conn.execute("""
        INSERT INTO signals (ts_emitted, direction, entry_price, sl, tp1, tp2,
            tp3, tp4, p_master_raw, p_master_final, kappa_evo, session,
            w_clock, tier, pspace_count, bucket_key, snapshot_json)
        VALUES ('2026-01-01T00:00:00+00:00','long',100,95,105,110,115,120,
                2.5,2.5,1.0,'ny_am_kz',0.8,'scalp',3,'x','{}')
    """)
    conn.commit()
    conn.close()
    rows = ev.get_recent_signals(10, symbol="SOL")
    assert len(rows) == 1


# ============================================================
# log_signal(symbol=...) / get_open_signals / reconcile aislados
# ============================================================
def test_log_signal_default_symbol_es_sol(ledger):
    sid = ev.log_signal(_sig())
    row = ev.get_recent_signals(1, symbol="SOL")[0]
    assert row["id"] == sid


def test_log_signal_btc_queda_aislado_de_sol(ledger):
    sid_sol = ev.log_signal(_sig())
    sid_btc = ev.log_signal(_sig(), symbol="BTC")

    open_sol = ev.get_open_signals(symbol="SOL")
    open_btc = ev.get_open_signals(symbol="BTC")
    assert [r["id"] for r in open_sol] == [sid_sol]
    assert [r["id"] for r in open_btc] == [sid_btc]


def test_get_open_signals_default_es_sol(ledger):
    """Preserva el comportamiento historico: get_open_signals() sin args
    devuelve SOLO SOL (evolution_periodic_hook sigue viendo lo mismo)."""
    ev.log_signal(_sig())
    ev.log_signal(_sig(), symbol="BTC")
    assert len(ev.get_open_signals()) == 1


def test_reconcile_btc_no_toca_senales_sol(monkeypatch, ledger):
    """reconcile_outcomes(ccy='BTC') NUNCA debe cerrar una senal SOL, aunque
    comparta niveles de precio -- son ledgers logicamente separados por
    symbol, no solo por valor de precio."""
    import pandas as pd
    from datetime import datetime, timezone, timedelta

    sid_sol = ev.log_signal(_sig())
    sid_btc = ev.log_signal(_sig(), symbol="BTC")

    now = datetime.now(timezone.utc)
    ts = [now - timedelta(minutes=10), now - timedelta(minutes=5), now]
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(ts).tz_localize(None),
        "high": [121.0, 121.0, 121.0],   # dispara TP4 (120) de cualquiera
        "low": [99.0, 99.0, 99.0],
        "close": [120.5, 120.5, 120.5],
    })

    closed = ev.reconcile_outcomes(lambda *a, **k: df, None, "BTC-USDT-SWAP",
                                   "5m", ccy="BTC")

    assert [c["id"] for c in closed] == [sid_btc]
    # La senal SOL sigue abierta -- el reconcile de BTC no la toco
    assert [r["id"] for r in ev.get_open_signals(symbol="SOL")] == [sid_sol]


def test_reconcile_default_ccy_es_sol_comportamiento_historico(monkeypatch, ledger):
    """Llamadas existentes (2 en fq_bot_v3_2.py) no pasan ccy -> deben seguir
    reconciliando SOLO SOL, sin cambios."""
    import pandas as pd
    from datetime import datetime, timezone, timedelta

    sid_sol = ev.log_signal(_sig())
    ev.log_signal(_sig(), symbol="BTC")

    now = datetime.now(timezone.utc)
    ts = [now - timedelta(minutes=10), now]
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(ts).tz_localize(None),
        "high": [121.0, 121.0], "low": [99.0, 99.0], "close": [120.5, 120.5],
    })
    closed = ev.reconcile_outcomes(lambda *a, **k: df, None, "SOL-USDT-SWAP", "5m")
    assert [c["id"] for c in closed] == [sid_sol]


# ============================================================
# EL RIESGO CRITICO: kappa_evo en vivo no se contamina
# ============================================================
def test_compute_kappa_evo_no_se_contamina_con_btc(ledger):
    """Un bucket_key IDENTICO (session|tier|direction|curvatura no incluye
    symbol) para SOL y BTC no debe mezclar sus outcomes en el modulador
    kappa_evo -- eso afilaria P_master EN VIVO con datos del simbolo
    equivocado."""
    session, direction = "ny_am_kz", "long"
    tier = ev.tier_from_pmaster(2.5)
    csign = ev.curvature_sign(0, 0)

    # 8 SOL wins (tp4) -> kappa_evo debe afilarse hacia arriba (>1.0)
    for _ in range(8):
        sid = ev.log_signal(_sig(session=session))
        ev.close_signal(sid, "tp4", 120.0, 4.0, 60)

    # 8 BTC losses (sl) con el MISMO bucket -- si esto contaminara, el
    # kappa combinado bajaria o quedaria neutro
    for _ in range(8):
        sid = ev.log_signal(_sig(session=session), symbol="BTC")
        ev.close_signal(sid, "sl", 95.0, -1.0, 30)

    kappa, stats = ev.compute_kappa_evo(session, tier, direction, csign)
    assert stats["n"] == 8          # SOLO las 8 de SOL, no 16
    assert stats["win_rate"] == 1.0
    assert kappa > 1.0              # sigue afilando hacia arriba, sin diluir


def test_get_bucket_stats_symbol_default_sol(ledger):
    bucket = ev.make_bucket_key("ny_am_kz", "scalp", "long", "flat")
    for _ in range(8):
        sid = ev.log_signal(_sig())
        ev.close_signal(sid, "tp4", 120.0, 4.0, 60)
    for _ in range(8):
        sid = ev.log_signal(_sig(), symbol="ETH")
        ev.close_signal(sid, "sl", 95.0, -1.0, 30)
    assert ev.get_bucket_stats(bucket)["n"] == 8
    assert ev.get_bucket_stats(bucket, symbol="ETH")["n"] == 8


# ============================================================
# Superficies agregadas: /metrics, /resultados, self-audit -- SOL-only default
# ============================================================
def test_get_global_metrics_no_mezcla_btc(ledger):
    sid_sol = ev.log_signal(_sig())
    ev.close_signal(sid_sol, "tp4", 120.0, 4.0, 60)
    sid_btc = ev.log_signal(_sig(), symbol="BTC")
    ev.close_signal(sid_btc, "sl", 95.0, -1.0, 30)

    m = ev.get_global_metrics()
    assert m["n"] == 1
    assert m["win_rate"] == 1.0


def test_get_results_summary_no_mezcla_btc(ledger):
    """/resultados es el numero que ve el CLIENTE -- no se diluye con BTC/ETH
    sin decision explicita de producto."""
    sid_sol = ev.log_signal(_sig())
    ev.close_signal(sid_sol, "tp4", 120.0, 4.0, 60)
    sid_btc = ev.log_signal(_sig(), symbol="BTC")
    ev.close_signal(sid_btc, "sl", 95.0, -1.0, 30)

    summary = ev.get_results_summary()
    assert summary["total"]["n"] == 1


def test_bucket_performance_table_no_mezcla_btc(ledger):
    for _ in range(4):
        sid = ev.log_signal(_sig())
        ev.close_signal(sid, "tp4", 120.0, 4.0, 60)
    for _ in range(4):
        sid = ev.log_signal(_sig(), symbol="BTC")
        ev.close_signal(sid, "sl", 95.0, -1.0, 30)
    table = ev._bucket_performance_table()
    assert len(table) == 1
    assert table[0]["n"] == 4
    assert table[0]["win_rate"] == 1.0


def test_count_signals_no_mezcla_btc(ledger):
    ev.log_signal(_sig())
    ev.log_signal(_sig(), symbol="BTC")
    ev.log_signal(_sig(), symbol="ETH")
    assert ev.count_signals() == 1
    assert ev.count_signals(symbol="BTC") == 1


def test_count_closed_v2_buckets_ignora_btc_por_null(ledger):
    """BTC/ETH se graban via log_signal simple (bucket_key_v2 queda NULL a
    proposito) -- el filtro symbol='SOL' es cinturon Y tirantes, pero la
    proteccion real ya viene del NULL."""
    sid_sol = ev.log_signal(_sig())
    ev.close_signal(sid_sol, "tp4", 120.0, 4.0, 60)
    sid_btc = ev.log_signal(_sig(), symbol="BTC")
    ev.close_signal(sid_btc, "sl", 95.0, -1.0, 30)
    # BTC nunca escribe bucket_key_v2 -> 0 sin importar el symbol pasado
    assert ev.count_closed_v2_buckets() == 0


# ============================================================
# /ledger admin: mezclado a proposito (feed de eventos, no track-record)
# ============================================================
def test_get_recent_signals_default_mezcla_todo(ledger):
    sid_sol = ev.log_signal(_sig())
    sid_btc = ev.log_signal(_sig(), symbol="BTC")
    rows = ev.get_recent_signals(10)
    ids = {r["id"] for r in rows}
    assert ids == {sid_sol, sid_btc}


def test_format_ledger_telegram_muestra_symbol_por_fila(ledger):
    sid = ev.log_signal(_sig(), symbol="BTC")
    ev.close_signal(sid, "tp1", 105.0, 1.0, 15)
    out = ev.format_ledger_telegram(10)
    assert "BTC" in out


def test_export_ledger_csv_incluye_symbol_de_todos(ledger):
    ev.log_signal(_sig())
    ev.log_signal(_sig(), symbol="BTC")
    csv = ev.export_ledger_csv()
    assert "symbol" in csv
    assert "BTC" in csv
