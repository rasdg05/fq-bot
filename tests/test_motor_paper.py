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
from bt_engine import CostModel


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


# --------------------------------------------------------------------------
# EJECUCION maker (FQ_EXEC_MODE=maker -> cost.maker_entry): entrada diferida
# --------------------------------------------------------------------------
def _maker_rt(ttl=6):
    return _runtime(cost=CostModel(maker_entry=True), maker_eps_bps=1.0,
                    maker_ttl_bars=ttl)


def test_maker_exec_encola_la_entrada_y_no_abre_en_la_senal():
    # En modo ejecucion, el fire ENCOLA una limite; NO abre en su propia vela
    # aunque esa vela ya penetre el nivel (sin look-ahead).
    rt = _maker_rt()
    assert rt.maker_exec is True
    rep = rt.on_bar(True, _field(), _report("long", entry=100.0), None, 100.0,
                    high=100.2, low=99.5)             # low penetra 99.99
    assert rep["opened"] is None and rep["maker_opened"] == []
    assert len(rt.account.open) == 0 and len(rt._pending_entries) == 1
    assert rt.counts == {"fire": 1, "opened": 0, "vetoed": 0}
    assert len(_events(rt, "MAKER_ENTRY_PENDING")) == 1


def test_maker_exec_fill_por_penetracion_abre_maker_en_el_nivel():
    rt = _maker_rt()
    rt.on_bar(True, _field(), _report("long", entry=100.0), None, 100.0)   # encola
    rep = rt.on_bar(False, _field(), _report("long"), None, 100.0,
                    high=100.2, low=99.9)             # penetra 99.99 -> FILL maker
    assert len(rep["maker_opened"]) == 1
    assert rep["maker_opened"][0]["fill_type"] == "maker"
    pos = rt.account.open[0]
    assert pos.entry == 100.0 and pos.entry_fill_type == "maker"
    assert rt._pending_entries == [] and rt.counts["opened"] == 1
    meta = _events(rt, "MOTOR_OPEN_META")[-1]
    assert meta["fill_type"] == "maker" and meta["bars_waited"] == 1


def test_maker_exec_fill_cobra_menos_que_taker_al_resolver():
    # La posicion abierta maker, al tocar TP, cobra fee maker (2bps) sin slippage
    # de entrada -> neto MAYOR que el equivalente taker. (LONG 100/99/101.)
    rt = _maker_rt()
    rt.on_bar(True, _field(), _report("long", entry=100.0), None, 100.0)
    rt.on_bar(False, _field(), _report("long"), None, 100.0, high=100.2, low=99.9)  # FILL
    rep = rt.on_bar(False, _field(), _report("long"), None, 101.5,
                    high=101.5, low=100.2)            # toca TP=101
    assert rep["resolved"][0]["reason"] == "tp"
    close = [r["payload"] for r in rt.broker.ledger.records
             if r["payload"].get("event") == "CLOSE"][-1]
    assert close["fill_type"] == "maker"
    # neto > +1R bruto-de-fees? no: hay fee. Pero la entrada no paga slippage:
    # entry efectivo = 100 exacto. pnl_r neto debe ser > el de un taker (que
    # pagaria slippage de entrada + 5bps). Aqui solo verificamos que es maker y
    # que el neto quedo por debajo del bruto +1R por el fee.
    assert close["pnl_r"] < 1.0 and close["fill_type"] == "maker"


def test_maker_exec_ttl_fallback_a_taker_en_mercado():
    rt = _maker_rt(ttl=3)
    rt.on_bar(True, _field(), _report("long", entry=100.0), None, 100.0)  # 100/99/101
    # 3 velas evaluables que NO penetran 99.99 y NO pasan TP(101): al expirar TTL
    # -> fallback taker a mercado (price de la 3a vela = 100.5)
    for px in (100.3, 100.4, 100.5):
        rep = rt.on_bar(False, _field(), _report("long"), None, px,
                        high=px + 0.05, low=100.2)
    assert len(rep["maker_opened"]) == 1
    pos = rt.account.open[0]
    assert pos.entry_fill_type == "taker" and pos.entry == pytest.approx(100.5)
    assert rt._pending_entries == []
    meta = _events(rt, "MOTOR_OPEN_META")[-1]
    assert meta["fill_type"] == "taker" and meta["bars_waited"] == 3


def test_maker_exec_short_fill_por_penetracion_abre_maker():
    # Simetria SHORT: la limite (venta) en 100 se llena si el precio SUBE y
    # penetra 100*(1+1bp)=100.01. Abre maker en el nivel.
    rt = _maker_rt()
    rt.on_bar(True, _field(), _report("short", entry=100.0), None, 100.0)  # 100/101/99
    rep = rt.on_bar(False, _field(), _report("short"), None, 100.0,
                    high=100.1, low=99.8)            # high penetra 100.01 -> FILL
    assert len(rep["maker_opened"]) == 1
    pos = rt.account.open[0]
    assert pos.direction == ex.SHORT and pos.entry == 100.0
    assert pos.entry_fill_type == "maker" and rt._pending_entries == []


def test_maker_exec_runaway_pasado_el_tp_no_persigue():
    # El precio se escapa por encima del TP sin volver al nivel: el maker se
    # perdio el runner entero -> NO se persigue (MISS). Esa es la adverse sel.
    rt = _maker_rt(ttl=2)
    rt.on_bar(True, _field(), _report("long", entry=100.0), None, 100.0)  # tp=101
    rt.on_bar(False, _field(), _report("long"), None, 101.5, high=101.6, low=100.5)
    rep = rt.on_bar(False, _field(), _report("long"), None, 102.0,
                    high=102.1, low=101.2)            # TTL y price 102 > tp 101
    assert rep["maker_opened"] == [] and len(rt.account.open) == 0
    assert rt._pending_entries == []
    assert len(_events(rt, "MAKER_RUNAWAY")) == 1
    assert rt.counts["opened"] == 0


def test_resuelve_abierta_contra_la_vela():
    rt = _runtime()
    rt.on_bar(True, _field(), _report("long"), None, 100.0)   # abre long 100/99/101
    rep = rt.on_bar(False, _field(), _report("long"), None, 100.0,
                    high=101.5, low=100.2)                     # toca TP
    assert len(rep["resolved"]) == 1 and rep["resolved"][0]["reason"] == "tp"


def test_ledger_report_y_formato(tmp_path):
    """ledger_report agrega cartera/fill-rate/adverse selection desde un ledger
    durable real; el formato Telegram no crashea en vacío ni con data."""
    path = str(tmp_path / "m.jsonl")
    broker = ex.PaperBroker(ledger=ex.DurableHashLedger.load(path))
    rt = mp.MotorPaperRuntime("SOL/USDT", account=ex.Account("a", 10_000.0),
                              broker=broker, veto=sv.parse(killzones="london_open_kz"),
                              maker_sim=True, maker_eps_bps=1.0, maker_ttl_bars=6)
    rt.on_bar(True, _field(), _report("long"), None, 100.0)                     # abre
    rt.on_bar(False, _field(), _report("long"), None, 100.0, high=100.2, low=99.9)   # FILL
    rt.on_bar(False, _field(), _report("long"), None, 101.5, high=101.5, low=100.2)  # TP
    rt.on_bar(True, _field("london_open_kz"), _report("long"), None, 100.0)     # vetada
    # ledger inexistente -> None -> formato no crashea
    assert mp.ledger_report(str(tmp_path / "noexiste.jsonl")) is None
    assert "sin ledger" in mp.format_report_telegram(None)
    rep = mp.ledger_report(path)
    assert rep["n_closed"] == 1 and rep["n_vetoed"] == 1
    assert rep["n_fill"] == 1 and rep["fill_rate"] == 1.0
    assert rep["portfolio"]["mean"] == 1.0  # TP a +1R gross
    msg = mp.format_report_telegram(rep)
    assert "Motor paper" in msg and "fill-rate maker" in msg


def test_ledger_report_modo_ejecucion_maker(tmp_path):
    """En modo EJECUCION maker el /paper distingue fills maker reales, fallback
    taker y runaways, marca el portfolio NETO, y mide adverse selection exec."""
    path = str(tmp_path / "mx.jsonl")
    broker = ex.PaperBroker(ledger=ex.DurableHashLedger.load(path),
                            cost=CostModel(maker_entry=True))
    rt = mp.MotorPaperRuntime("SOL/USDT", account=ex.Account("a", 10_000.0),
                              broker=broker, veto=sv.SegmentVeto(),
                              maker_eps_bps=1.0, maker_ttl_bars=2)
    assert rt.maker_exec is True
    # trade A: encola -> FILL maker -> TP (cierra NETO)
    rt.on_bar(True, _field(), _report("long", entry=100.0), None, 100.0)
    rt.on_bar(False, _field(), _report("long"), None, 100.0, high=100.2, low=99.9)   # FILL
    rt.on_bar(False, _field(), _report("long"), None, 101.5, high=101.5, low=100.2)  # TP
    # trade B: encola -> runaway (el precio rebasa el TP sin volver al nivel)
    rt.on_bar(True, _field(), _report("long", entry=200.0), None, 200.0)             # tp=201
    rt.on_bar(False, _field(), _report("long", entry=200.0), None, 201.5,
              high=201.6, low=200.5)
    rt.on_bar(False, _field(), _report("long", entry=200.0), None, 202.0,
              high=202.1, low=201.2)
    rep = mp.ledger_report(path)
    assert rep["exec"] is True and rep["net"] is True
    assert rep["n_maker"] == 1 and rep["n_taker"] == 0 and rep["n_runaway"] == 1
    assert rep["exec_fill_rate"] == pytest.approx(0.5)   # 1 maker / (1 + 0 + 1)
    assert rep["maker"]["n"] == 1
    assert rep["portfolio"]["mean"] < 1.0                # NETO < +1R bruto (fee)
    msg = mp.format_report_telegram(rep)
    assert "ejecución maker" in msg and "NETO" in msg


def test_from_env_default_london(monkeypatch, tmp_path):
    monkeypatch.setenv("FQ_MOTOR_PAPER_LEDGER_PATH", str(tmp_path / "m.jsonl"))
    for k in ("FQ_MOTOR_PAPER_VETO_KILLZONES", "FQ_MOTOR_PAPER_VETO_UTC_BLOCKS",
              "FQ_MOTOR_PAPER_VETO_WEEKDAYS", "FQ_MOTOR_PAPER_EQUITY"):
        monkeypatch.delenv(k, raising=False)
    rt = mp.MotorPaperRuntime.from_env("SOL/USDT")
    assert rt.veto.active and "london_open_kz" in rt.veto.killzones
    assert rt.maker_sim is True  # shadow ON por default (es el punto del track)


def test_from_env_ledger_path_override_separates_symbols(monkeypatch, tmp_path):
    """Correr SOL+BTC en paralelo exige ledgers SEPARADOS. ledger_path explicito
    debe GANARLE a FQ_MOTOR_PAPER_LEDGER_PATH; si no, ambos simbolos mezclarian
    sus trades en un solo archivo y corromperian los dos edges (el pipeline BTC
    paralelo depende de esto)."""
    sol_path = tmp_path / "sol.jsonl"
    btc_path = tmp_path / "btc.jsonl"
    monkeypatch.setenv("FQ_MOTOR_PAPER_LEDGER_PATH", str(sol_path))  # seteado p/ SOL
    sol = mp.MotorPaperRuntime.from_env("SOL/USDT")
    btc = mp.MotorPaperRuntime.from_env("BTC/USDT", ledger_path=str(btc_path))
    assert sol.broker.ledger.path == str(sol_path)
    assert btc.broker.ledger.path == str(btc_path)   # el override le gana al env
    assert sol.broker.ledger.path != btc.broker.ledger.path
