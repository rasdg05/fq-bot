"""Halt de supervivencia pico-a-valle en el RiskGovernor (respuesta measure-first a
'¿cómo sobrevive el bot los 7 años?'). Con 28% WR las rachas malas son brutales; el
cap de drawdown deja de abrir antes de la ruina. Default OFF (0.0) -> byte-idéntico."""
import pytest
from execution import Account, RiskGovernor, GovernorConfig


def _acc(equity, peak):
    a = Account("t", equity)
    a.peak_equity = peak
    a.day_start_equity = 1e-6   # aísla el DD: day_pnl_frac siempre >0 -> el corte diario
                                # nunca entra, así probamos SOLO el halt pico-a-valle
    return a


def test_default_off_no_bloquea_por_dd():
    # max_drawdown_frac=0.0 (default) -> el DD nunca frena (comportamiento histórico)
    gov = RiskGovernor(GovernorConfig())
    a = _acc(50.0, 100.0)          # 50% de drawdown
    assert gov.decide(a)["approved"] is True


def test_halt_cuando_dd_supera_el_tope():
    gov = RiskGovernor(GovernorConfig(max_drawdown_frac=0.25))
    a = _acc(74.0, 100.0)          # 26% DD > 25% tope
    d = gov.decide(a)
    assert d["approved"] is False
    assert d["risk_frac"] == 0.0
    assert "drawdown" in d["reason"]


def test_aprueba_bajo_el_tope():
    gov = RiskGovernor(GovernorConfig(max_drawdown_frac=0.25))
    a = _acc(80.0, 100.0)          # 20% DD < 25%
    assert gov.decide(a)["approved"] is True


def test_frontera_exacta_halt():
    gov = RiskGovernor(GovernorConfig(max_drawdown_frac=0.25))
    a = _acc(75.0, 100.0)          # exactamente 25% -> >= tope -> halt
    assert gov.decide(a)["approved"] is False


def test_pico_a_valle_no_desde_inicio():
    # el DD es contra el PICO, no el equity inicial: subió a 200, cayó a 150 = 25% DD
    gov = RiskGovernor(GovernorConfig(max_drawdown_frac=0.20))
    a = _acc(150.0, 200.0)         # 25% desde el pico 200 -> halt (aunque > inicio)
    assert gov.decide(a)["approved"] is False


def test_dd_halt_reversible_al_recuperar():
    # si el equity se recupera por encima del umbral, vuelve a operar
    gov = RiskGovernor(GovernorConfig(max_drawdown_frac=0.25))
    a = _acc(90.0, 100.0)          # 10% DD -> opera
    assert gov.decide(a)["approved"] is True
    a.equity = 70.0               # cae a 30% DD -> halt
    assert gov.decide(a)["approved"] is False
    a.equity = 95.0               # recupera a 5% DD -> opera de nuevo
    assert gov.decide(a)["approved"] is True
