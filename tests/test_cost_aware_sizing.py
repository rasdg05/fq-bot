# -*- coding: utf-8 -*-
"""
SIZING CONSCIENTE DE COSTES — que risk_frac signifique lo que dice.

`size = equity * risk_frac / rdist` dimensiona para que la perdida BRUTA al stop
sea risk_frac del equity. Pero _settle resta despues fees y slippage, asi que la
perdida REALIZADA es mayor: en el ledger del motor (jul-2026, 90 cierres) el
stop medio costo -1.191R en vez de -1.0R. Un 19% de sobrecoste sistematico que
ademas desfasa TODOS los topes del gobernador, que quedan mas laxos de lo
configurado.

OJO con lo que esto NO es: corrige el presupuesto de riesgo, no la expectancy.
R es una unidad; reescalarla no crea edge. El WR de equilibrio es invariante.
"""
import pytest

import execution as ex
from bt_engine import CostModel


def _acct(equity=10_000.0):
    return ex.Account("test", equity)


def _sig(entry=100.0, stop=99.0, tp=103.0, direction=1):
    return {"symbol": "X/USDT", "direction": direction,
            "entry": entry, "stop": stop, "tp": tp}


def test_stop_cuesta_exactamente_el_riesgo_configurado(monkeypatch):
    """La prueba que importa: arriesgar 1% debe perder 1% cuando salta el stop."""
    monkeypatch.setenv("FQ_COST_AWARE_SIZING", "1")
    a, b = _acct(10_000), ex.PaperBroker(cost=CostModel())
    pos = b.open(a, _sig(), 0.01)
    b.resolve(a, pos, 99.0, "stop")

    perdida = 10_000 - a.equity
    assert perdida == pytest.approx(100.0, rel=0.01), (
        "risk_frac=1%% sobre 10.000 debe costar ~100, costo %.2f" % perdida)


def test_el_dimensionado_bruto_se_pasa_de_riesgo(monkeypatch):
    """Contraprueba del defecto: con el sizing viejo el stop cuesta MAS."""
    monkeypatch.setenv("FQ_COST_AWARE_SIZING", "0")
    a, b = _acct(10_000), ex.PaperBroker(cost=CostModel())
    pos = b.open(a, _sig(), 0.01)
    b.resolve(a, pos, 99.0, "stop")

    perdida = 10_000 - a.equity
    assert perdida > 105.0, "el defecto historico deberia sobrepasar el 1%%"


def test_sin_cost_model_es_identico(monkeypatch):
    """Compat: sin modelo de costes el dimensionado no cambia (size = eq*rf/rdist)."""
    monkeypatch.setenv("FQ_COST_AWARE_SIZING", "1")
    a, b = _acct(10_000), ex.PaperBroker()          # cost=None
    pos = b.open(a, _sig(), 0.01)
    assert pos.size == pytest.approx(100.0)


def test_maker_arriesga_menos_por_unidad_que_taker():
    """Una entrada maker no paga slippage ni fee taker -> pierde menos por unidad
    al stop -> admite mas size para el MISMO riesgo. Es la direccion correcta."""
    b = ex.PaperBroker(cost=CostModel())
    l_maker = b.net_unit_loss(100.0, 99.0, 1, entry_maker=True)
    l_taker = b.net_unit_loss(100.0, 99.0, 1, entry_maker=False)
    assert l_maker < l_taker
    assert l_maker > 1.0, "aun con maker, el stop cruza el book y paga"


def test_net_unit_loss_sin_costes_es_la_distancia():
    b = ex.PaperBroker()
    assert b.net_unit_loss(100.0, 99.0, 1) == pytest.approx(1.0)


def test_topes_del_gobernador_dejan_de_estar_desfasados(monkeypatch):
    """El efecto colateral que mas importa: con el sizing bruto, 4 stops a 1% de
    riesgo superaban el tope de perdida diaria del 4%. Ahora no."""
    monkeypatch.setenv("FQ_COST_AWARE_SIZING", "1")
    a, b = _acct(10_000), ex.PaperBroker(cost=CostModel())
    for _ in range(4):
        pos = b.open(a, _sig(), 0.01)
        b.resolve(a, pos, 99.0, "stop")
    assert a.day_pnl_frac() >= -0.041, (
        "4 stops al 1%% no deben cruzar el tope diario del 4%%, y cruzaban")
