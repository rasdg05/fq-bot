# -*- coding: utf-8 -*-
"""Cableado del comando admin /tphits (2026-07-21): cmd_tphits + su registro
en COMMANDS/ADMIN_ONLY dentro de command_listener. command_listener es un
loop de polling sin arnes de test directo (ver test_lectura_tier_aware.py),
asi que el registro se sella por inspeccion de fuente."""
import inspect

import pytest

import fq_bot_v3_2 as b


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    db = tmp_path / "ledger.db"
    monkeypatch.setenv("FQ_LEDGER_PATH", str(db))
    import importlib
    importlib.reload(b.ev)
    b.ev.init_db()
    b.ev.migrate_schema_v2()
    b.ev.migrate_schema_v3()
    b.ev.migrate_schema_v4()
    b.ev.migrate_schema_v5()
    return b.ev


def test_cmd_tphits_sin_datos(ledger):
    assert "Sin cierres registrados" in b.cmd_tphits()


def test_cmd_tphits_devuelve_el_formato_del_ledger(monkeypatch):
    monkeypatch.setattr(b.ev, "format_tp_distribution_telegram",
                        lambda **k: "DISTRIBUCION FAKE")
    assert b.cmd_tphits() == "DISTRIBUCION FAKE"


def test_cmd_tphits_no_explota_si_ev_falla(monkeypatch):
    def _boom(**k):
        raise RuntimeError("db lock")
    monkeypatch.setattr(b.ev, "format_tp_distribution_telegram", _boom)
    out = b.cmd_tphits()
    assert "Error" in out


def _command_listener_source():
    return inspect.getsource(b.command_listener)


def test_tphits_esta_en_admin_only():
    src = _command_listener_source()
    idx = src.index("ADMIN_ONLY = {")
    block = src[idx: src.index("}", idx)]
    assert '"/tphits"' in block


def test_tphits_esta_registrado_en_commands():
    """COMMANDS se construye dentro de main() (global COMMANDS), no al
    importar el modulo -- se sella por inspeccion de fuente, igual que
    ADMIN_ONLY arriba."""
    src = inspect.getsource(b.main)
    idx = src.index('COMMANDS = {')
    block = src[idx: src.index("\n    }", idx)]
    assert '"/tphits"' in block
