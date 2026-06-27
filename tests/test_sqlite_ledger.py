# -*- coding: utf-8 -*-
"""
SqliteHashLedger + migración: consolidación del ledger del motor a SQLite multi-símbolo.
Preserva la cadena SHA-256, misma interfaz que DurableHashLedger. Reversible (FQ_LEDGER_SQLITE).
Determinista, stdlib (sqlite3), sin red.
"""
import json
import os
import sqlite3
import sys

import pytest

import execution as ex
import reconciler as rc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import migrate_ledgers_to_sqlite as M  # noqa: E402


def test_append_load_verify(tmp_path):
    db = str(tmp_path / "fq_motor.db")
    led = ex.SqliteHashLedger(db, "BTC/USDT")
    led.append({"event": "OPEN", "pid": 1})
    led.append({"event": "CLOSE", "pid": 1, "pnl_r": 1.5})
    led2 = ex.SqliteHashLedger.load(db, "BTC/USDT")        # rehidrata como en un restart
    assert led2.verify() is True
    assert [r["payload"]["event"] for r in led2.records] == ["OPEN", "CLOSE"]
    led2.append({"event": "OPEN", "pid": 2})               # la cadena sigue creciendo
    assert ex.SqliteHashLedger.load(db, "BTC/USDT").verify() is True


def test_multisimbolo_aislado_en_un_archivo(tmp_path):
    db = str(tmp_path / "fq_motor.db")
    b = ex.SqliteHashLedger(db, "BTC/USDT"); b.append({"event": "CLOSE", "pnl_r": 1.0})
    e = ex.SqliteHashLedger(db, "ETH/USDT"); e.append({"event": "CLOSE", "pnl_r": -0.5})
    e.append({"event": "CLOSE", "pnl_r": 0.3})
    lb = ex.SqliteHashLedger.load(db, "BTC/USDT")
    le = ex.SqliteHashLedger.load(db, "ETH/USDT")
    assert len(lb.records) == 1 and len(le.records) == 2   # cada símbolo su propia cadena
    assert lb.verify() and le.verify()
    assert rc.extract_closed_r(le) == pytest.approx([-0.5, 0.3])


def test_cadena_identica_a_durable(tmp_path):
    # MISMOS payloads -> MISMOS hashes en ambos backends (la consolidación no cambia la cadena)
    payloads = [{"event": "OPEN", "pid": 1}, {"event": "CLOSE", "pid": 1, "pnl_r": 0.7}]
    dur = ex.DurableHashLedger(str(tmp_path / "x.jsonl"))
    sq = ex.SqliteHashLedger(str(tmp_path / "x.db"), "SOL/USDT")
    for p in payloads:
        dur.append(p); sq.append(p)
    assert [r["hash"] for r in dur.records] == [r["hash"] for r in sq.records]
    assert rc.extract_closed_r(dur) == rc.extract_closed_r(sq)


def test_tamper_lanza(tmp_path):
    db = str(tmp_path / "fq_motor.db")
    led = ex.SqliteHashLedger(db, "BTC/USDT")
    led.append({"event": "CLOSE", "pid": 1, "pnl_r": 1.0})
    led.append({"event": "CLOSE", "pid": 2, "pnl_r": -1.0})
    con = sqlite3.connect(db)                              # manipula el pasado en la tabla
    con.execute("UPDATE motor_ledger SET payload=? WHERE symbol=? AND seq=0",
                (json.dumps({"event": "CLOSE", "pid": 1, "pnl_r": 99.0}), "BTC/USDT"))
    con.commit(); con.close()
    with pytest.raises(ValueError):
        ex.SqliteHashLedger.load(db, "BTC/USDT")


def test_factory_env_gated(tmp_path, monkeypatch):
    jp = str(tmp_path / "motor_paper_BTC_USDT.jsonl")
    ex.DurableHashLedger(jp).append({"event": "OPEN", "pid": 1})
    monkeypatch.delenv("FQ_LEDGER_SQLITE", raising=False)
    monkeypatch.setenv("FQ_MOTOR_DB", str(tmp_path / "fq_motor.db"))
    assert isinstance(ex.open_motor_ledger(jp, "BTC/USDT"), ex.DurableHashLedger)   # default OFF
    monkeypatch.setenv("FQ_LEDGER_SQLITE", "1")
    assert isinstance(ex.open_motor_ledger(jp, "BTC/USDT"), ex.SqliteHashLedger)    # gated ON
    assert ex._symbol_from_jsonl(jp) == "BTC/USDT"


def test_auto_migra_al_prender_flag(tmp_path, monkeypatch):
    # FQ_LEDGER_SQLITE=1 + SQLite vacío + JSONL existente -> auto-importa al abrir (corte 1-flag)
    jp = str(tmp_path / "motor_paper_SOL_USDT.jsonl")
    src = ex.DurableHashLedger(jp)
    for i in range(3):
        src.append({"event": "CLOSE", "pid": i, "pnl_r": float(i)})
    monkeypatch.setenv("FQ_MOTOR_DB", str(tmp_path / "fq_motor.db"))
    monkeypatch.setenv("FQ_LEDGER_SQLITE", "1")
    led = ex.open_motor_ledger(jp, "SOL/USDT")
    assert isinstance(led, ex.SqliteHashLedger) and len(led.records) == 3 and led.verify()
    assert led.records[-1]["hash"] == src.records[-1]["hash"]       # cadena idéntica
    assert len(ex.open_motor_ledger(jp, "SOL/USDT").records) == 3   # idempotente (no re-importa)


def test_migracion_idempotente_y_paridad(tmp_path, capsys):
    # crea un JSONL real, migra, y verifica head-hash idéntico + idempotencia
    jp = str(tmp_path / "motor_paper_ETH_USDT.jsonl")
    src = ex.DurableHashLedger(jp)
    for i in range(5):
        src.append({"event": "CLOSE", "pid": i, "pnl_r": float(i) - 2})
    db = str(tmp_path / "fq_motor.db")
    assert M.migrate(str(tmp_path), db) == 0
    sq = ex.SqliteHashLedger.load(db, "ETH/USDT")
    assert len(sq.records) == 5 and sq.verify()
    assert sq.records[-1]["hash"] == src.records[-1]["hash"]    # cadena idéntica
    assert M.migrate(str(tmp_path), db) == 0                    # 2a corrida = idempotente
    assert len(ex.SqliteHashLedger.load(db, "ETH/USDT").records) == 5
