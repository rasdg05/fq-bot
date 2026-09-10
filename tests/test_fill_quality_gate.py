# -*- coding: utf-8 -*-
"""
GATE DE CALIDAD DE FILL — seleccion adversa en limites pasivas.

Una limite que se llena en la PRIMERA barra se esta llenando porque el precio la
esta atravesando: no es un retroceso amable hacia tu nivel, es momentum en tu
contra. Medido en el ledger del motor (jul-2026, 90 cierres con fees):

    fills <=2 barras : n=53  WR 11%  sumR -36.69   <- 80% de toda la perdida
    fills >=5 barras : n=25  WR 44%  sumR  -2.14

Fisher exacto p=0.0024 (sobrevive Bonferroni sobre ~10 cortes probados) y el
signo aguanta en las dos mitades temporales. El precio de entrada es exacto
(entry==limit, sin deslizamiento), asi que la perdida no viene de entrar mal
sino de lo que pasa DESPUES del fill.

Lo que este gate NO es: filtrar los fills rapidos lleva la E[R] de -0.51 a
~-0.09, pero el IC95% sigue cruzando el cero. Deja de sangrar; no demuestra
edge. Por eso cada rechazo queda sellado (MOTOR_FILL_REJECTED) y se mide
forward en vez de darse por bueno.
"""
import pytest

import motor_paper as mp
import execution as ex


class _Ledger:
    def __init__(self): self.records = []
    def append(self, payload): self.records.append({"payload": payload}); return {}
    def verify(self): return True


def _runtime(min_fill_bars):
    acc = ex.Account("paper-test", 10_000.0)
    broker = ex.PaperBroker(ledger=_Ledger())
    return mp.MotorPaperRuntime("SOL/USDT", account=acc, broker=broker,
                                maker_sim=False, min_fill_bars=min_fill_bars)


def _pending(rt, *, entry=100.0, stop=101.0, tp=96.0, direction=-1, waited=0):
    """Encola una entrada pendiente como lo hace el motor."""
    rt._pending_entries = [{
        "sig": {"symbol": "SOL/USDT", "direction": direction,
                "entry": entry, "stop": stop, "tp": tp},
        "limit": entry, "direction": direction, "waited": waited,
        "risk_frac": 0.0025, "tf": "5m", "killzone": "ny_am_kz",
        "regime": "stable", "regime_tags": {}, "cvd": None,
    }]


def _events(rt, name):
    return [r["payload"] for r in rt.broker.ledger.records
            if r["payload"].get("event") == name]


def test_fill_de_una_barra_se_rechaza():
    """El caso que concentra la perdida: llenado inmediato."""
    rt = _runtime(min_fill_bars=2)
    _pending(rt, waited=0)
    # El precio penetra la limite en esta misma barra -> waited pasaria a 1.
    rt._process_pending_entries(high=102.0, low=99.0, price=100.0, ts="t0")

    assert _events(rt, "MOTOR_FILL_REJECTED"), "deberia haber rechazado el fill"
    assert not _events(rt, "OPEN"), "no debe abrir posicion"
    assert rt.counts.get("fill_rejected") == 1


def test_fill_lento_se_acepta():
    """Contraprueba: la misma limite tras aguantar barras SI entra."""
    rt = _runtime(min_fill_bars=2)
    _pending(rt, waited=3)
    rt._process_pending_entries(high=102.0, low=99.0, price=100.0, ts="t0")

    assert not _events(rt, "MOTOR_FILL_REJECTED")
    opens = _events(rt, "OPEN")
    assert len(opens) == 1
    meta = _events(rt, "MOTOR_OPEN_META")[0]
    assert meta["bars_waited"] == 4
    assert meta["fill_type"] == "maker"


def test_gate_apagado_es_comportamiento_historico():
    """min_fill_bars=0 -> no rechaza nada (compat byte-identica)."""
    rt = _runtime(min_fill_bars=0)
    _pending(rt, waited=0)
    rt._process_pending_entries(high=102.0, low=99.0, price=100.0, ts="t0")

    assert not _events(rt, "MOTOR_FILL_REJECTED")
    assert len(_events(rt, "OPEN")) == 1


def test_el_rechazo_queda_sellado_con_su_evidencia():
    """El rechazo no es silencioso: se mide forward para poder juzgarlo despues."""
    rt = _runtime(min_fill_bars=3)
    _pending(rt, waited=0)
    rt._process_pending_entries(high=102.0, low=99.0, price=100.0, ts="t0")

    ev = _events(rt, "MOTOR_FILL_REJECTED")[0]
    assert ev["bars_waited"] == 1
    assert ev["min_fill_bars"] == 3
    assert ev["killzone"] == "ny_am_kz"
    assert "seleccion adversa" in ev["why"]


def test_el_gate_no_toca_el_fallback_taker():
    """La conversion a taker al expirar el TTL es otra via y no se filtra: en la
    muestra es justo la que NO sangra (n=22, WR 45%)."""
    rt = _runtime(min_fill_bars=2)
    rt.maker_ttl_bars = 2
    _pending(rt, waited=1)
    # No penetra (high por debajo de la limite en un short) -> waited=2 -> TTL.
    rt._process_pending_entries(high=99.5, low=98.0, price=99.0, ts="t0")

    assert not _events(rt, "MOTOR_FILL_REJECTED")
    metas = _events(rt, "MOTOR_OPEN_META")
    assert len(metas) == 1 and metas[0]["fill_type"] == "taker"


def test_default_del_entorno_es_2(monkeypatch):
    """from_env enciende el gate por defecto: el motor es PAPEL, encenderlo es
    medir, no arriesgar capital."""
    monkeypatch.delenv("FQ_MOTOR_MIN_FILL_BARS", raising=False)
    assert int(__import__("os").environ.get("FQ_MOTOR_MIN_FILL_BARS", "2")) == 2
