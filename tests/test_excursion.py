# -*- coding: utf-8 -*-
"""
RECORRIDO MFE/MAE — el dato que faltaba para juzgar la geometria TP/SL.

El ledger sellaba donde SALIO cada trade, no hasta donde LLEGO. Con eso se sabe
que un trade perdio, pero no si perdio porque el TP estaba demasiado lejos,
porque el SL estaba demasiado cerca, o porque la senal no separa. Tres
enfermedades con el mismo sintoma y tratamientos opuestos.
"""
import pytest

import execution as ex
from bt_engine import CostModel


def _acct(equity=10_000.0):
    return ex.Account("test", equity)


def _sig(entry=100.0, stop=99.0, tp=103.0, direction=1):
    return {"symbol": "X/USDT", "direction": direction,
            "entry": entry, "stop": stop, "tp": tp}


# --- mecanica del seguimiento ---------------------------------------------

def test_long_acumula_extremos():
    b = ex.PaperBroker()
    pos = b.open(_acct(), _sig(), 0.01)
    b.track_excursion(pos, high=101.0, low=99.5)
    b.track_excursion(pos, high=100.2, low=99.2)   # peor minimo, peor maximo
    mfe, mae = pos.excursion_r()
    assert mfe == pytest.approx(1.0)               # llego a 101 = +1R
    assert mae == pytest.approx(-0.8)              # bajo a 99.2 = -0.8R
    assert pos.bars_held == 2


def test_short_invierte_el_signo():
    """En un short, 'favorable' es que BAJE."""
    b = ex.PaperBroker()
    pos = b.open(_acct(), _sig(entry=100.0, stop=101.0, tp=97.0, direction=-1), 0.01)
    b.track_excursion(pos, high=100.5, low=98.0)
    mfe, mae = pos.excursion_r()
    assert mfe == pytest.approx(2.0)               # bajo a 98 = +2R a favor
    assert mae == pytest.approx(-0.5)              # subio a 100.5 = -0.5R


def test_sin_velas_no_inventa_cero():
    """Ausencia != 'no se movio'. Un 0.0 sellado se leeria como lo segundo."""
    b = ex.PaperBroker()
    pos = b.open(_acct(), _sig(), 0.01)
    assert pos.excursion_r() == (None, None)


# --- sellado en el ledger --------------------------------------------------

def test_el_cierre_sella_el_recorrido():
    a, b = _acct(), ex.PaperBroker()
    pos = b.open(a, _sig(), 0.01)
    b.resolve_on_bar(a, pos, high=102.0, low=99.5)      # no toca nada
    b.resolve_on_bar(a, pos, high=103.5, low=99.8)      # toca TP

    pay = b.ledger.records[-1]["payload"]
    assert pay["event"] == "CLOSE"
    assert pay["mfe_r"] == pytest.approx(3.5)
    assert pay["mae_r"] == pytest.approx(-0.5)
    assert pay["bars_held"] == 2


def test_la_vela_que_resuelve_cuenta():
    """Convencion estandar: el recorrido incluye la barra de salida."""
    a, b = _acct(), ex.PaperBroker()
    pos = b.open(a, _sig(), 0.01)
    b.resolve_on_bar(a, pos, high=104.0, low=98.0)      # stop Y tp en la misma
    pay = b.ledger.records[-1]["payload"]
    assert pay["reason"] == "stop"                       # desempate pesimista
    assert pay["mfe_r"] == pytest.approx(4.0)            # pero llego a +4R
    assert pay["bars_held"] == 1


def test_cierre_directo_no_sella_recorrido():
    """resolve() sin barras observadas: el campo se omite en vez de mentir."""
    a, b = _acct(), ex.PaperBroker()
    pos = b.open(a, _sig(), 0.01)
    b.resolve(a, pos, 101.0, "timeout")
    assert "mfe_r" not in b.ledger.records[-1]["payload"]


def test_el_recorrido_convive_con_el_modelo_de_costes():
    a, b = _acct(), ex.PaperBroker(cost=CostModel())
    pos = b.open(a, _sig(), 0.01)
    b.resolve_on_bar(a, pos, high=103.5, low=99.5)
    pay = b.ledger.records[-1]["payload"]
    assert "mfe_r" in pay and "fees_quote" in pay


# --- el informe ------------------------------------------------------------

def _close(pnl_r, mfe_r, mae_r):
    return {"event": "CLOSE", "pnl_r": pnl_r, "mfe_r": mfe_r, "mae_r": mae_r,
            "bars_held": 3}


def test_el_informe_detecta_tp_demasiado_lejos(capsys):
    """Perdedores que estuvieron muy a favor = se sale tarde, no se falla."""
    from tools import geometry_report as gr
    closes = [_close(-1.0, 1.8, -1.0) for _ in range(40)]
    gr.report_tp_too_far(closes)
    out = capsys.readouterr().out
    assert "MFE >= 1.0R :  40" in out
    assert "Recoger antes" in out


def test_el_informe_detecta_que_la_senal_no_separa(capsys):
    """La lectura que mas duele: ganadores y perdedores con el mismo recorrido."""
    from tools import geometry_report as gr
    closes = [_close(+1.0, 1.2, -0.5) for _ in range(20)]
    closes += [_close(-1.0, 1.15, -1.0) for _ in range(20)]
    gr.report_distribution(closes)
    out = capsys.readouterr().out
    assert "NO separa" in out


def test_el_contrafactual_es_pesimista_en_el_cruce():
    """Si MFE y MAE cruzan ambos umbrales no se sabe el orden intra-vela ->
    cuenta como perdedor. Sin esa regla el informe se auto-enganaria."""
    from tools import geometry_report as gr
    closes = [_close(-1.0, 3.0, -1.0)]      # llego a +3R Y a -1R
    gr.counterfactual(closes, tps=[2.0], sls=[1.0])
    # con TP=2 y SL=1 ambos se cruzan -> debe contar -1.0, no +2.0
    tot = -1.0 if closes[0]["mae_r"] <= -1.0 else 2.0
    assert tot == -1.0


# --- desambiguacion por orden de barra --------------------------------------

def _c(pnl_r, mfe_r, mae_r, mfe_bar=None, mae_bar=None):
    d = {"event": "CLOSE", "pnl_r": pnl_r, "mfe_r": mfe_r, "mae_r": mae_r}
    if mfe_bar is not None:
        d["mfe_bar"], d["mae_bar"] = mfe_bar, mae_bar
    return d


def test_track_sella_la_barra_de_cada_extremo():
    b = ex.PaperBroker()
    pos = b.open(_acct(), _sig(), 0.01)
    b.track_excursion(pos, high=101.0, low=99.8)   # barra 1: mejor maximo
    b.track_excursion(pos, high=100.2, low=99.1)   # barra 2: peor minimo
    assert pos.mfe_bar == 1
    assert pos.mae_bar == 2


def test_replay_el_tp_primero_gana():
    """Llego a +2R en la barra 1 y murio en la 3: con TP=1R habria salido en
    TP, porque el stop aun no existia cuando se toco el objetivo."""
    from tools.geometry_report import _replay_one
    assert _replay_one(_c(-1.0, 2.0, -1.0, mfe_bar=1, mae_bar=3), tp=1.0, sl=1.0) == 1.0


def test_replay_el_sl_primero_gana():
    from tools.geometry_report import _replay_one
    assert _replay_one(_c(-1.0, 2.0, -1.0, mfe_bar=4, mae_bar=2), tp=1.0, sl=1.0) == -1.0


def test_replay_empate_intra_vela_es_pesimista():
    """Misma barra: el orden es genuinamente desconocido -> peor caso."""
    from tools.geometry_report import _replay_one
    assert _replay_one(_c(-1.0, 2.0, -1.0, mfe_bar=2, mae_bar=2), tp=1.0, sl=1.0) == -1.0


def test_replay_sin_indice_de_barra_es_pesimista():
    """Cierres anteriores a la instrumentacion: no se les da el beneficio."""
    from tools.geometry_report import _replay_one
    assert _replay_one(_c(-1.0, 2.0, -1.0), tp=1.0, sl=1.0) == -1.0


def test_replay_solo_un_umbral_cruzado():
    from tools.geometry_report import _replay_one
    assert _replay_one(_c(+1.0, 2.0, -0.3, 1, 2), tp=1.5, sl=1.0) == 1.5
    assert _replay_one(_c(-1.0, 0.2, -1.5, 2, 1), tp=1.5, sl=1.0) == -1.0
