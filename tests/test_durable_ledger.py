# -*- coding: utf-8 -*-
"""
DurableHashLedger: respaldo append-only del proof-of-work en disco. Sobrevive a
restarts (rehidrata + verifica). Determinista, stdlib, sin red.
"""
import json

import pytest

import execution as ex
import reconciler as rc


def test_append_persists_and_reload_verifies(tmp_path):
    p = str(tmp_path / "gold_ledger.jsonl")
    led = ex.DurableHashLedger(p)
    led.append({"event": "OPEN", "pid": 1})
    led.append({"event": "CLOSE", "pid": 1, "pnl_r": 1.5})
    # rehidratar como en un restart del contenedor
    led2 = ex.DurableHashLedger.load(p)
    assert led2.verify() is True
    assert [r["payload"]["event"] for r in led2.records] == ["OPEN", "CLOSE"]
    assert led2.records[-1]["payload"]["pnl_r"] == 1.5
    # la cadena sigue creciendo coherente tras recargar
    led2.append({"event": "OPEN", "pid": 2})
    assert ex.DurableHashLedger.load(p).verify() is True


def test_corrupt_chain_on_disk_raises(tmp_path):
    p = str(tmp_path / "led.jsonl")
    led = ex.DurableHashLedger(p)
    led.append({"event": "CLOSE", "pid": 1, "pnl_r": 1.0})
    led.append({"event": "CLOSE", "pid": 2, "pnl_r": -1.0})
    lines = open(p).read().splitlines()
    rec = json.loads(lines[0])
    rec["payload"]["pnl_r"] = 99.0                 # manipula el pasado en disco
    lines[0] = json.dumps(rec, sort_keys=True, default=str)
    open(p, "w").write("\n".join(lines) + "\n")
    with pytest.raises(ValueError):
        ex.DurableHashLedger.load(p)


def test_load_missing_file_is_empty(tmp_path):
    led = ex.DurableHashLedger.load(str(tmp_path / "nope.jsonl"))
    assert led.records == [] and led.verify() is True


def test_torn_tail_write_heals_not_bricks(tmp_path):
    # A0 crash-safety: un crash a media escritura deja una última línea JSON parcial.
    # Antes load() LANZABA -> ledger brickeado. Ahora SANA la cola y conserva lo válido.
    p = str(tmp_path / "led.jsonl")
    led = ex.DurableHashLedger(p)
    led.append({"event": "OPEN", "pid": 1})
    led.append({"event": "CLOSE", "pid": 1, "pnl_r": 1.0})
    with open(p, "a") as fh:
        fh.write('{"seq": 2, "prev": "x", "hash')     # torn write (JSON sin cerrar)
    led2 = ex.DurableHashLedger.load(p)               # NO lanza
    assert led2.verify() is True and len(led2.records) == 2
    assert len(open(p).read().splitlines()) == 2       # archivo saneado (cola removida)
    led2.append({"event": "OPEN", "pid": 2})           # la cadena sigue creciendo
    assert ex.DurableHashLedger.load(p).verify() is True


def test_paperbroker_with_durable_ledger_survives_reload(tmp_path):
    p = str(tmp_path / "led.jsonl")
    broker = ex.PaperBroker(ledger=ex.DurableHashLedger(p))
    acc = ex.Account("paper", 10_000.0)
    sig = {"symbol": "BTC/USDT:USDT", "direction": ex.LONG,
           "entry": 100.0, "stop": 99.0, "tp": 101.0}
    pos = broker.open(acc, sig, 0.0025)
    broker.resolve(acc, pos, 101.0, "tp")
    # tras "restart": el reconciler reconstruye la expectancy del ledger en disco
    reloaded = ex.DurableHashLedger.load(p)
    assert reloaded.verify()
    assert rc.extract_closed_r(reloaded) == pytest.approx([1.0])
