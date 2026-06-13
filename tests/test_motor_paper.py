# -*- coding: utf-8 -*-
"""motor_paper: paper del MOTOR BASE + veto + shadow maker (§6.10.1).

Verifica: abre sobre el `fire` crudo, el veto propio (london) filtra, el shadow
maker mide fill por penetracion / miss por TTL, el gobernador puede vetar, y la
resolucion contra la vela. Sin red ni monolito (broker/governor/veto inyectados).
"""
from types import SimpleNamespace

import pytest

import execution as ex
import segment_veto as sv
import motor_paper as mp


def _field(killzone="ny_am_kz"):
    return SimpleNamespace(killzone=killzone)


def _report(direction="long", *, decision="fire", entry=100.0):
    """Report 'fire' de fusion_engine: decision + direction + levels."""
    if direction == "long":
        levels = {"entry": entry, "sl": entry - 1.0, "tp1": entry + 1.0}
    else:
        levels = {"entry": entry, "sl": entry + 1.0, "tp1": entry - 1.0}
    return {"decision": decision, "direction": direction, "levels": levels}


def _runtime(veto=None, governor=None, **kw):
    return mp.MotorPaperRuntime(
        "BTC/USDT:USDT", account=ex.Account("paper-motor", 10_000.0),
        veto=veto if veto is not None else sv.SegmentVeto(),
        governor=governor, **kw)


def _events(rt, name):
    return [r["payload"] for r in rt.broker.ledger.records
            if r["payload"].get("event") == name]


def _maker_events(rt):
    return [r["payload"] for r in rt.broker.ledger.records
            if str(r["payload"].get("event", "")).startswith("MAKER_")]


class _RejectGov:
    def decide(self, account, requested_risk=None):
        return {"approved": False, "risk_frac": 0.0, "reason": "test-reject"}


def test_abre_en_fire_sin_veto():
    rt = _runtime()  # veto vacio
    rep = rt.on_bar(True, _field(), _report("long"), None, 100.0)
    assert rep["opened"] is not None
    assert rt.counts == {"fire": 1, "opened": 1, "vetoed": 0}
    meta = _events(rt, "MOTOR_OPEN_META")
    assert len(meta) == 1 and meta[0]["killzone"] == "ny_am_kz"


def test_no_fire_no_abre():
    rt = _runtime()
    rep = rt.on_bar(False, _field(), _report("long"), None, 100.0)
    assert rep["opened"] is None
    assert rt.counts == {"fire": 0, "opened": 0, "vetoed": 0}
    assert len(rt.account.open) == 0


def test_veto_london_no_abre_y_loguea():
    rt = _runtime(veto=sv.parse(killzones="london_open_kz"))
    rep = rt.on_bar(True, _field("london_open_kz"), _report("long"), None, 100.0)
    assert rep["opened"] is None
    assert rt.counts["vetoed"] == 1 and rt.counts["opened"] == 0
    ev = _events(rt, "MOTOR_VETOED")
    assert len(ev) == 1 and ev[0]["killzone"] == "london_open_kz"
    assert "killzone=london_open_kz" in ev[0]["why"]


def test_veto_no_afecta_otra_killzone():
    rt = _runtime(veto=sv.parse(killzones="london_open_kz"))
    rep = rt.on_bar(True, _field("ny_am_kz"), _report("long"), None, 100.0)
    assert rep["opened"] is not None and rt.counts["opened"] == 1


def test_report_sin_niveles_no_abre_ni_crashea():
    rt = _runtime()
    bad = {"decision": "fire", "direction": "long", "levels": {}}
    rep = rt.on_bar(True, _field(), bad, None, 100.0)
    assert rep["opened"] is None and rt.counts["fire"] == 1


def test_gobernador_puede_vetar():
    rt = _runtime(governor=_RejectGov())
    rep = rt.on_bar(True, _field(), _report("long"), None, 100.0)
    assert rep["opened"] is None and rt.counts["opened"] == 0


def test_maker_shadow_fill_por_penetracion():
    rt = _runtime(maker_sim=True, maker_eps_bps=1.0, maker_ttl_bars=6)
    rep = rt.on_bar(True, _field(), _report("long"), None, 100.0)  # abre + pending
    pid = rep["opened"]["pid"]
    # touch exacto del nivel NO llena (low == limite)
    rt.on_bar(False, _field(), _report("long"), None, 100.0, high=100.5, low=100.0)
    assert _maker_events(rt) == []
    # penetracion: low < 100*(1-1bp)=99.99 -> FILL; no toca SL(99) ni TP(101)
    rt.on_bar(False, _field(), _report("long"), None, 100.0, high=100.2, low=99.9)
    evs = _maker_events(rt)
    assert len(evs) == 1 and evs[0]["event"] == "MAKER_FILL"
    assert evs[0]["pid"] == pid and evs[0]["bars_waited"] == 2


def test_maker_shadow_miss_al_expirar_ttl():
    rt = _runtime(maker_sim=True, maker_eps_bps=1.0, maker_ttl_bars=3)
    rt.on_bar(True, _field(), _report("short"), None, 100.0)  # SHORT limite en 100
    for _ in range(3):  # nunca penetra por encima de 100*(1+eps)=100.01
        rt.on_bar(False, _field(), _report("short"), None, 99.0, high=99.95, low=98.5)
    evs = _maker_events(rt)
    assert len(evs) == 1 and evs[0]["event"] == "MAKER_MISS"
    assert evs[0]["bars_waited"] == 3 and rt._maker_pending == []


def test_maker_off_por_default_no_instrumenta():
    rt = _runtime(maker_sim=False)
    rt.on_bar(True, _field(), _report("long"), None, 100.0)
    rt.on_bar(False, _field(), _report("long"), None, 100.0, high=100.2, low=99.9)
    assert _maker_events(rt) == []


def test_resuelve_abierta_contra_la_vela():
    rt = _runtime()
    rt.on_bar(True, _field(), _report("long"), None, 100.0)   # abre long 100/99/101
    rep = rt.on_bar(False, _field(), _report("long"), None, 100.0,
                    high=101.5, low=100.2)                     # toca TP
    assert len(rep["resolved"]) == 1 and rep["resolved"][0]["reason"] == "tp"


def test_from_env_default_london(monkeypatch, tmp_path):
    monkeypatch.setenv("FQ_MOTOR_PAPER_LEDGER_PATH", str(tmp_path / "m.jsonl"))
    for k in ("FQ_MOTOR_PAPER_VETO_KILLZONES", "FQ_MOTOR_PAPER_VETO_UTC_BLOCKS",
              "FQ_MOTOR_PAPER_VETO_WEEKDAYS", "FQ_MOTOR_PAPER_EQUITY"):
        monkeypatch.delenv(k, raising=False)
    rt = mp.MotorPaperRuntime.from_env("SOL/USDT")
    assert rt.veto.active and "london_open_kz" in rt.veto.killzones
    assert rt.maker_sim is True  # shadow ON por default (es el punto del track)
