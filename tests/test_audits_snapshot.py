"""Revive la tabla `audits`: el snapshot CUANTITATIVo (n_closed, winR, expectancy,
entropy, kl_drift) debe escribirse SIEMPRE, incluso con opus_response vacío (sin
Claude). Antes el write iba gated por Claude -> tabla vacía. Este test fija el
contrato del que depende el fix del loop en fq_bot_v3_2.py."""
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
    ev.migrate_schema_v2(); ev.migrate_schema_v3()
    ev.migrate_schema_v4(); ev.migrate_schema_v5()
    return ev


def _sig(**ov):
    base = {"direction": "long", "entry": 100.0, "sl": 95.0,
            "tp1": 105.0, "tp2": 110.0, "tp3": 115.0, "tp4": 120.0,
            "p_master_raw": 2.5, "p_master_final": 2.5, "kappa_evo": 1.0,
            "session": "ny_am_kz", "w_clock": 0.8, "pspace_count": 3, "snapshot": {}}
    base.update(ov)
    return base


def _seed_closed(ev, wins, losses):
    for _ in range(wins):
        sid = ev.log_signal(_sig()); ev.close_signal(sid, "tp4", 120.0, 4.0, 60)
    for _ in range(losses):
        sid = ev.log_signal(_sig()); ev.close_signal(sid, "sl", 95.0, -1.0, 30)


def _audits(ev):
    conn = sqlite3.connect(ev.DB_PATH)
    try:
        return conn.execute(
            "SELECT n_closed, win_rate, expectancy_r, opus_response FROM audits ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def test_snapshot_cuantitativo_se_escribe_sin_claude(ledger):
    ev = ledger
    _seed_closed(ev, wins=3, losses=1)          # 4 cerradas, winR 0.75
    n = ev.count_signals(closed_only=True)
    assert n == 4
    ev.save_audit(n, ev.get_global_metrics(), "")   # opus vacío == sin Claude
    rows = _audits(ev)
    assert len(rows) == 1
    n_closed, win_rate, exp_r, opus = rows[0]
    assert n_closed == 4
    assert abs(win_rate - 0.75) < 1e-6
    assert opus == ""                              # fila cuantitativa pura, sin narrativa
    assert exp_r is not None


def test_narrativa_opus_opcional_no_bloquea(ledger):
    ev = ledger
    _seed_closed(ev, wins=2, losses=2)
    n = ev.count_signals(closed_only=True)
    ev.save_audit(n, ev.get_global_metrics(), "narrativa de Opus aquí")
    rows = _audits(ev)
    assert len(rows) == 1 and rows[0][3] == "narrativa de Opus aquí"


def test_should_trigger_cada_n_y_anti_doble(ledger):
    ev = ledger
    # sin cierres -> no dispara
    assert ev.should_trigger_audit() is False
    _seed_closed(ev, wins=ev.AUDIT_EVERY_N_CLOSED, losses=0)   # justo el umbral
    assert ev.should_trigger_audit() is True
    # tras escribir el snapshot, el anti-doble-trigger lo apaga en ese umbral
    ev.save_audit(ev.count_signals(closed_only=True), ev.get_global_metrics(), "")
    assert ev.should_trigger_audit() is False
