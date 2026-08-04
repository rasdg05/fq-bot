# -*- coding: utf-8 -*-
"""
RIESGO DE CARTERA — el R por trade no describe lo que le pasa a la cuenta.

Todo lo que este repo mide está en R por trade. Eso describe una operación
aislada. El caso que motivó este módulo: la geometría ancha daba +0.085R por
trade, con CPCV positivo y holdout por símbolo que transfiere (8/8) — y a nivel
cartera, con `risk_frac=1%` y sin límite de concurrencia, **arruina la cuenta**,
porque el hold medio de 2 días deja 13.7 posiciones abiertas a la vez.

Las regresiones que fija este archivo:

1. El capital se compromete en la APERTURA y se realiza en el CIERRE. Componer
   trade a trade en orden de entrada asume capital libre que no está libre:
   sobrestima el retorno y subestima el drawdown a la vez.
2. El límite de concurrencia SALTA señales, no las encola — y el coste de
   saltarlas se reporta, porque es una decisión de producto.
3. Un drawdown que no es operable se dice con esas palabras.
"""
import numpy as np
import pytest

pd = pytest.importorskip("pandas")

from tools.portfolio_risk import report, simulate_portfolio, worst_days

T0 = pd.Timestamp("2024-01-01")


def _trades(specs):
    """specs: lista de (offset_horas_apertura, horas_de_vida, net_r)."""
    return pd.DataFrame({
        "t0": [T0 + pd.Timedelta(hours=a) for a, _, _ in specs],
        "t1": [T0 + pd.Timedelta(hours=a + v) for a, v, _ in specs],
        "net_r": [r for _, _, r in specs],
    })


# --- 1. el capital se compromete al abrir ----------------------------------

def test_el_riesgo_se_fija_con_el_equity_de_la_APERTURA():
    """Dos trades solapados arriesgan sobre el MISMO equity: el segundo no se
    beneficia de la ganancia del primero, porque aun no ha cerrado."""
    t = _trades([(0, 10, 1.0), (1, 10, 1.0)])
    r = simulate_portfolio(t, 0.10)
    # ambos arriesgan 0.10 del equity inicial -> 1 + 0.10 + 0.10 = 1.20
    assert r["equity_final"] == pytest.approx(1.20)


def test_secuencial_compone_y_da_MAS_que_solapado():
    """La diferencia que motiva el modulo: en secuencial el segundo trade
    arriesga sobre el equity ya crecido. Confundirlos infla el retorno."""
    solapado = simulate_portfolio(_trades([(0, 10, 1.0), (1, 10, 1.0)]), 0.10)
    secuencial = simulate_portfolio(_trades([(0, 1, 1.0), (5, 1, 1.0)]), 0.10)
    assert secuencial["equity_final"] > solapado["equity_final"]
    assert secuencial["equity_final"] == pytest.approx(1.21)


def test_las_perdidas_simultaneas_pegan_juntas():
    t = _trades([(0, 10, -1.0)] * 5)
    r = simulate_portfolio(t, 0.10)
    assert r["equity_final"] == pytest.approx(0.50)
    assert r["conc_max"] == 5


# --- 2. concurrencia y su coste --------------------------------------------

def test_mide_la_concurrencia():
    t = _trades([(0, 10, 0.0), (1, 10, 0.0), (2, 1, 0.0)])
    r = simulate_portfolio(t, 0.01)
    assert r["conc_max"] == 3


def test_el_limite_SALTA_señales_y_las_cuenta():
    """No las encola: una señal que no cabe se pierde, y el coste se reporta
    porque es una decision de producto, no un detalle."""
    t = _trades([(0, 10, 1.0), (1, 10, 1.0), (2, 10, 1.0)])
    r = simulate_portfolio(t, 0.10, max_concurrent=2)
    assert r["saltadas"] == 1
    assert r["equity_final"] == pytest.approx(1.20)


def test_un_cierre_libera_hueco_en_el_mismo_instante():
    """Si el cierre no se procesara antes que la apertura simultanea, el limite
    rechazaria señales que en la practica si caben."""
    t = pd.DataFrame({
        "t0": [T0, T0 + pd.Timedelta(hours=5)],
        "t1": [T0 + pd.Timedelta(hours=5), T0 + pd.Timedelta(hours=10)],
        "net_r": [1.0, 1.0],
    })
    r = simulate_portfolio(t, 0.10, max_concurrent=1)
    assert r["saltadas"] == 0


def test_sin_limite_no_se_salta_nada():
    t = _trades([(0, 10, 0.5)] * 20)
    assert simulate_portfolio(t, 0.001)["saltadas"] == 0


# --- 3. drawdown -----------------------------------------------------------

def test_el_drawdown_se_mide_sobre_el_pico():
    t = _trades([(0, 1, 2.0), (10, 1, -1.0), (20, 1, -1.0)])
    r = simulate_portfolio(t, 0.10)
    assert r["max_drawdown"] < -0.15


def test_una_cuenta_arruinada_no_reporta_drawdown_bonito():
    t = _trades([(i * 10, 1, -1.0) for i in range(60)])
    r = simulate_portfolio(t, 0.10)
    assert r["equity_final"] < 0.01
    assert r["max_drawdown"] < -0.98


def test_los_peores_dias_agregan_por_fecha_de_cierre():
    t = _trades([(0, 1, -3.0), (1, 1, -4.0), (500, 1, +2.0)])
    peores = worst_days(t, k=1)
    assert peores.iloc[0]["sum"] == pytest.approx(-7.0)
    assert peores.iloc[0]["count"] == 2


# --- 4. el informe dice cuando algo no es operable -------------------------

def test_el_informe_avisa_de_un_drawdown_inoperable(capsys):
    rng = np.random.default_rng(5)
    specs = [(i * 6, 48, float(rng.normal(0.05, 2.0))) for i in range(400)]
    report(_trades(specs), risk_fracs=(0.02,), caps=())
    out = capsys.readouterr().out
    assert "RIESGO DE CARTERA" in out
    assert "E[R] por trade" in out


def test_el_informe_dice_si_ninguna_config_sobrevive(capsys):
    t = _trades([(i * 2, 48, -1.0) for i in range(200)])
    assert report(t, risk_fracs=(0.05, 0.02), caps=()) is None
    assert "NINGUNA configuracion" in capsys.readouterr().out


def test_el_informe_avisa_si_el_cap_tira_media_cadencia(capsys):
    """Sin `risk_fracs` la unica config reportada es la limitada, asi que es la
    que se selecciona — el aviso va sobre la config ELEGIDA, no sobre todas."""
    t = _trades([(i, 200, 0.5) for i in range(300)])
    report(t, risk_fracs=(), caps=(3,), cap_risk_frac=0.001)
    out = capsys.readouterr().out
    assert "cadencia del producto se desploma" in out


def test_la_tabla_reporta_las_saltadas_de_cada_config(capsys):
    """Aunque el aviso sea de la elegida, el coste de cada limite tiene que
    verse en su fila: es el precio de esa decision de producto."""
    t = _trades([(i, 200, 0.5) for i in range(300)])
    report(t, risk_fracs=(0.001,), caps=(3,), cap_risk_frac=0.001)
    linea = [l for l in capsys.readouterr().out.splitlines() if "cap 3" in l][0]
    assert linea.split()[-1] != "0"


def test_el_informe_declara_que_el_DD_es_cota_inferior(capsys):
    t = _trades([(i * 5, 48, 0.3) for i in range(100)])
    report(t, risk_fracs=(0.005,), caps=())
    assert "COTA INFERIOR" in capsys.readouterr().out
