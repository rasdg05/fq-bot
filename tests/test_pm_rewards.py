# -*- coding: utf-8 -*-
"""
Matematica de los Liquidity Rewards de Polymarket. El ancla del test es el
EJEMPLO RESUELTO de la documentacion oficial: si nuestros numeros no dan lo
mismo que los de ellos, la estimacion de la Fase 0 no vale nada.
"""
import pytest

from pm import rewards


# ============================================================
# EJEMPLO RESUELTO DE LA DOC (max_spread = 3c, midpoint = 0.50)
# ============================================================
def test_score_order_reproduce_doc():
    # S(3, 1) = ((3-1)/3)^2 = 4/9
    assert rewards.score_order(3, 1) == pytest.approx(4 / 9)
    assert rewards.score_order(3, 2) == pytest.approx(1 / 9)
    assert rewards.score_order(3, 1.5) == pytest.approx(0.25)
    assert rewards.score_order(3, 0.5) == pytest.approx((2.5 / 3) ** 2)


def test_score_order_cae_a_cero_fuera_del_max_spread():
    assert rewards.score_order(3, 3) == 0.0
    assert rewards.score_order(3, 4) == 0.0
    assert rewards.score_order(0, 1) == 0.0          # mercado sin config


def test_score_order_es_cuadratico():
    """Al doble de distancia, un cuarto de puntos. Es LA razon por la que
    cotizar pegado al midpoint importa tanto."""
    cerca = rewards.score_order(4.0, 1.0)
    lejos = rewards.score_order(4.0, 2.0)
    assert cerca / lejos == pytest.approx((3 / 4) ** 2 / (2 / 4) ** 2)


def test_lados_del_libro_reproducen_el_ejemplo_de_la_doc():
    """Doc, pasos 2 y 3: Q_ne = 111.11, Q_no = 175.0."""
    mid = 0.50
    yes_bids = [(0.49, 100), (0.48, 200), (0.485, 100)]
    yes_asks = []
    no_bids = [(0.48, 100)]
    no_asks = [(0.51, 100), (0.505, 200)]

    q_one, q_two = rewards.side_scores(yes_bids, yes_asks, no_bids, no_asks,
                                       mid, max_spread_cents=3, min_size=0)
    # Q_one = bids YES + asks NO. El ejemplo pone el bid de 0.485 en el segundo
    # lado, asi que aca aparece la suma de los tres bids YES mas los asks NO.
    esperado_one = ((4 / 9) * 100 + (1 / 9) * 200 + 0.25 * 100
                    + (4 / 9) * 100 + (2.5 / 3) ** 2 * 200)
    esperado_two = (1 / 9) * 100
    assert q_one == pytest.approx(esperado_one)
    assert q_two == pytest.approx(esperado_two)


# ============================================================
# Q_MIN: el premio a estar en los dos lados
# ============================================================
def test_q_min_en_el_centro_tolera_un_solo_lado_dividido_por_c():
    assert rewards.q_min(300, 0, midpoint=0.50) == pytest.approx(100.0)   # 300/3


def test_q_min_en_las_colas_exige_los_dos_lados():
    assert rewards.q_min(300, 0, midpoint=0.05) == 0.0
    assert rewards.q_min(300, 0, midpoint=0.95) == 0.0


def test_q_min_dos_lados_gana_al_ajuste_de_un_lado():
    # 200 y 180 en cada lado: min = 180 > max/c = 66.7
    assert rewards.q_min(200, 180, midpoint=0.5) == pytest.approx(180.0)


def test_q_min_sin_midpoint_es_cero():
    assert rewards.q_min(500, 500, midpoint=None) == 0.0


# ============================================================
# MIDPOINT AJUSTADO POR EL CORTE DE TAMANO
# ============================================================
def test_midpoint_ignora_ordenes_debajo_del_corte():
    bids = [(0.60, 5), (0.50, 100)]       # la de 0.60 no llega al corte
    asks = [(0.62, 3), (0.70, 100)]       # la de 0.62 tampoco
    assert rewards.adjusted_midpoint(bids, asks, min_size=30) == pytest.approx(0.60)
    # Sin corte, el midpoint es otro: por eso la doc habla de "adjusted".
    assert rewards.adjusted_midpoint(bids, asks, min_size=0) == pytest.approx(0.61)


def test_midpoint_none_si_falta_un_lado():
    assert rewards.adjusted_midpoint([(0.5, 100)], [], min_size=0) is None
    assert rewards.adjusted_midpoint([], [], min_size=0) is None


def test_niveles_tolera_basura():
    """Un libro mal formado no puede tumbar una corrida de siete dias."""
    crudo = [(0.5, 100), None, {"price": "x", "size": 1}, {"price": 0.4, "size": 50},
             (0.3, 0), "basura"]
    assert rewards._levels(crudo) == [(0.5, 100.0), (0.4, 50.0)]


# ============================================================
# NUESTRA COTIZACION Y EL CAPITAL QUE CUESTA
# ============================================================
def test_capital_de_dos_lados_es_casi_un_dolar_por_share():
    """La regla de bolsillo del bot: $1 de capital ~ 1 share a dos lados,
    casi sin importar el precio del mercado."""
    for mid in (0.15, 0.35, 0.50, 0.72, 0.88):
        cap = rewards.capital_for_two_sided(100, mid, spread_cents=1.0)
        assert cap == pytest.approx(98.0, abs=0.01)


def test_nuestra_cotizacion_no_califica_debajo_del_min_size():
    assert rewards.our_q_min(29, 1.0, 0.5, max_spread_cents=4.5, min_size=30) == 0.0
    assert rewards.our_q_min(30, 1.0, 0.5, max_spread_cents=4.5, min_size=30) > 0.0


def test_nuestra_cotizacion_de_dos_lados_puntua_simetrico():
    """Bid en YES puntua en Q_one, bid en NO en Q_two -> min() no castiga."""
    q = rewards.our_q_min(100, 1.0, 0.5, max_spread_cents=4.5, min_size=30)
    assert q == pytest.approx(rewards.score_order(4.5, 1.0) * 100)


def test_reward_estimado_es_la_parte_del_pool():
    # Mismo puntaje que el libro -> nos toca la mitad.
    assert rewards.estimate_daily_reward(100.0, 500.0, 500.0) == pytest.approx(50.0)
    # Enanos frente al libro -> migajas.
    assert rewards.estimate_daily_reward(100.0, 200_000.0, 150.0) < 0.1
    assert rewards.estimate_daily_reward(100.0, 0.0, 0.0) == 0.0


def test_barrido_de_spreads_ordena_por_cercania_al_midpoint():
    filas = rewards.sweep_spreads(daily_pool=100.0, book_q_min=1000.0,
                                  capital_usd=500.0, midpoint=0.5,
                                  max_spread_cents=4.5, min_size=30,
                                  spreads_cents=(0.5, 1.0, 3.0))
    assert [f["spread_cents"] for f in filas] == [0.5, 1.0, 3.0]
    # Mas pegado al midpoint => mas puntaje con el MISMO capital.
    assert filas[0]["est_daily_usd"] > filas[1]["est_daily_usd"] > filas[2]["est_daily_usd"]
    assert all(f["qualifies"] for f in filas)


def test_barrido_descarta_spreads_fuera_del_maximo():
    filas = rewards.sweep_spreads(100.0, 1000.0, 500.0, 0.5, max_spread_cents=2.0,
                                  min_size=30, spreads_cents=(1.0, 2.0, 3.0))
    assert [f["spread_cents"] for f in filas] == [1.0]
