# -*- coding: utf-8 -*-
"""
V4 — LA MEDIA ARITMETICA NO ES LO QUE LE PASA A LA CUENTA.

Tres regresiones que este archivo fija:

1. **`f` es invisible para todo lo demas.** E[R], IC95% y DSR son invariantes a
   la fraccion arriesgada por construccion (`cube_report.apply_costs` lo dice en
   su docstring: "la R neta por trade sale invariante al capital"). O sea que el
   sistema de medicion entero es incapaz de detectar una sobre-apuesta. `growth`
   es el unico sitio donde `f` cambia el veredicto, y aqui se comprueba que lo
   cambia en la direccion correcta.

2. **Apostar de mas NO es simetrico a apostar de menos.** Pasado ~2xf* el
   crecimiento se vuelve NEGATIVO aunque la media siga positiva. Es el modo de
   fallo del texto de Tsitsiklis (y de XIV): la media sube mientras la mediana
   baja, porque el promedio lo levanta una cola que no vas a vivir.

3. **La invariante de publicacion.** `format_expectancy` levanta sin el bloque de
   crecimiento, igual que ya levantaba sin el desglose por periodo (E9). Mismo
   choke point, misma familia de error: un numero exacto que describe algo
   distinto de lo que el lector cree.
"""
import math

import pytest

import growth
import ledger_stats as ls


def _loteria(n=300, p=0.3, ganancia=3.0):
    """Perfil real del motor: WR bajo, cola derecha gorda, media positiva."""
    fila = []
    for i in range(n):
        fila.append(ganancia if (i % round(1 / p)) == 0 else -1.0)
    return fila


def _perdedora(n=300):
    return [1.0 if i % 3 == 0 else -1.0 for i in range(n)]      # media -0.33R


# ------------------------------------------------- 1. `f` cambia el veredicto

def test_la_media_es_invariante_a_f_pero_el_crecimiento_no():
    """El nucleo de V4. La misma serie, dos fracciones: E[R] identico, `g`
    distinto. Si esto dejara de ser cierto, `growth` no estaria midiendo nada
    que las demas metricas no midan ya."""
    rs = _loteria()
    a = growth.growth_stats(rs, 0.01)
    b = growth.growth_stats(rs, 0.30)
    assert a["mean_r"] == pytest.approx(b["mean_r"])         # E[R] no ve la f
    assert a["g"] != pytest.approx(b["g"])                   # el crecimiento si


def test_el_crecimiento_tiene_un_maximo_interior():
    """Kelly: `g(f)` sube, tiene un pico y baja. Si fuese monotono, "arriesgar
    mas" seria siempre mejor y no habria nada que gobernar."""
    rs = _loteria()
    k = growth.kelly_fraction(rs)
    assert 0 < k["f_star"] < 0.5
    for delta in (0.5, 2.0):
        g = growth.growth_rate(rs, k["f_star"] * delta)
        assert g is not None and g < k["g_star"]


def test_sobre_apostar_no_es_simetrico_a_sub_apostar():
    """La asimetria que hace peligrosa la sobre-apuesta: a 2xf* el crecimiento
    es PEOR que a la mitad de f*, aunque los dos esten 'igual de lejos' del
    optimo en apariencia."""
    rs = _loteria()
    fs = growth.kelly_fraction(rs)["f_star"]
    assert growth.growth_rate(rs, 2.0 * fs) < growth.growth_rate(rs, 0.5 * fs)


def test_pasado_el_doble_de_kelly_la_media_sube_y_la_cuenta_encoge():
    """El fenomeno del texto, en una assert: media positiva, crecimiento
    negativo. Es exactamente XIV — el dia promedio ganaba."""
    rs = _loteria()
    fs = growth.kelly_fraction(rs)["f_star"]
    st = growth.growth_stats(rs, min(2.2 * fs, 0.45))
    assert st["mean_r"] > 0                     # la media dice que ganas
    assert st["g"] < 0                          # la cuenta dice que no
    assert st["mean_x"] > 1.0 and st["median_x"] < 1.0


def test_media_y_mediana_divergen_con_cola_derecha():
    st = growth.growth_stats(_loteria(), 0.01)
    assert st["skew_r"] > 0
    assert st["median_r"] < st["mean_r"]


# ------------------------------------------------- 2. los casos que no crecen

def test_sin_edge_la_fraccion_optima_es_cero():
    """Si mu <= 0 ninguna `f` positiva crece: `f*` = 0 y hay que decirlo asi, no
    devolver 'un poco'. Es la traduccion al idioma del crecimiento de lo que V1
    midio sobre tp1: no es sizing, falta edge."""
    st = growth.growth_stats(_perdedora(), 0.01)
    assert st["f_star"] == 0.0
    assert st["g"] < 0
    assert "NO apostar" in growth.format_growth(st)


def test_la_ruina_no_se_promedia_se_declara():
    """Con una R de -1 y f=1 la cuenta se borra. Eso no es 'g muy negativo': es
    que esa fraccion no es apostable, y un promedio finito lo esconderia."""
    assert growth.growth_rate([-1.0, 2.0, 3.0], 1.0) is None
    st = growth.growth_stats([-1.0, 2.0, 3.0] * 20, 1.0)
    assert st["g"] is None
    assert "RUINA" in growth.format_growth(st)


def test_muestra_corta_se_marca_en_vez_de_recomendar():
    st = growth.growth_stats([1.0, -1.0, 2.0, -1.0], 0.01)
    assert st["thin"] is True
    assert "orientativo" in growth.format_growth(st)


# ------------------------------- 3. una sola fuente de verdad para la fraccion

def test_la_f_que_juzga_es_la_f_que_opera():
    """Que el gobernador arriesgue una fraccion y el informe evalue otra es la
    forma exacta de no enterarse. Misma familia que `vip_report.vip_universe` vs
    `fq_bot_v3_2.VIP_PAIRS`: medir el producto que NO se opera."""
    import execution
    assert (execution.GovernorConfig().max_risk_frac
            == growth.configured_risk_frac())


def test_el_env_mueve_las_dos_a_la_vez(monkeypatch):
    import execution
    monkeypatch.setenv(growth.RISK_FRAC_ENV, "0.004")
    assert growth.configured_risk_frac() == pytest.approx(0.004)
    assert execution.GovernorConfig().max_risk_frac == pytest.approx(0.004)


def test_default_byte_identico_al_de_antes(monkeypatch):
    """El cableado es aditivo: sin env, la cuenta viva arriesga lo mismo que
    antes de V4 (0.25%)."""
    monkeypatch.delenv(growth.RISK_FRAC_ENV, raising=False)
    assert growth.configured_risk_frac() == pytest.approx(0.0025)


# --------------------------------------------- 4. la invariante de publicacion

def _rows(n=60, ganadora=0.3):
    return [{"outcome": "tp4" if (i % round(1 / ganadora)) == 0 else "sl",
             "pnl_r": 3.0 if (i % round(1 / ganadora)) == 0 else -1.0,
             "minutes_open": 60,
             "closed_at": "2026-0%d-15T00:00:00Z" % (1 + i % 6)}
            for i in range(n)]


def test_window_stats_adjunta_siempre_el_crecimiento():
    st = ls.window_stats(_rows())
    assert st["growth"] is not None
    assert st["growth"]["risk_frac"] == growth.configured_risk_frac()


def test_no_se_puede_publicar_una_expectancy_sin_crecimiento():
    """La invariante. Un stats con desglose pero sin `growth` NO sale."""
    st = ls.window_stats(_rows())
    salida = ls.format_expectancy(st)                  # sano: sale
    assert "Crecimiento" in salida
    del st["growth"]
    with pytest.raises(growth.ArithmeticWithoutGrowthError):
        ls.format_expectancy(st)


def test_el_render_publica_la_probabilidad_de_acabar_arriba():
    """No basta con calcularla: el numero que un suscriptor entiende tiene que
    salir pegado al que no."""
    salida = ls.format_expectancy(ls.window_stats(_rows()))
    assert "P(acabar por encima del capital inicial)" in salida
    assert "f*" in salida


def test_p_up_es_coherente_con_el_signo_del_crecimiento():
    arriba = growth.growth_stats(_loteria(), 0.01)
    abajo = growth.growth_stats(_perdedora(), 0.01)
    assert arriba["p_up"] > 0.5
    assert abajo["p_up"] < 0.5


def test_horizonte_mas_largo_separa_mas():
    """Con g>0, mas trades = mas seguro acabar arriba; con g<0, menos. Es la
    ergodicidad haciendo su trabajo: el tiempo no promedia, acumula."""
    rs = _loteria()
    corto = growth.growth_stats(rs, 0.01, horizon=50)
    largo = growth.growth_stats(rs, 0.01, horizon=800)
    assert largo["p_up"] > corto["p_up"]
    malo_corto = growth.growth_stats(_perdedora(), 0.01, horizon=50)
    malo_largo = growth.growth_stats(_perdedora(), 0.01, horizon=800)
    assert malo_largo["p_up"] < malo_corto["p_up"]


# ------------------------------------------------------- 5. el panel de /salud

def test_salud_avisa_solo_cuando_la_cuenta_encoge():
    """Calibracion del panel: pasarse de Kelly es AVISO (creces de mas con mas
    varianza); que la cuenta encoja es ROTO. Confundirlos gasta la alarma."""
    import salud
    rs = _loteria()
    fs = growth.kelly_fraction(rs)["f_star"]
    assert salud.check_sobreapuesta(
        growth.growth_stats(rs, fs * 0.4))["estado"] == salud.OK
    assert salud.check_sobreapuesta(
        growth.growth_stats(rs, fs * 1.3))["estado"] == salud.WARN
    assert salud.check_sobreapuesta(
        growth.growth_stats(rs, min(fs * 2.5, 0.49)))["estado"] == salud.BROKEN


def test_salud_distingue_falta_de_edge_de_mal_sizing():
    """Dos diagnosticos que se parecen y piden cosas distintas: si f*=0 el
    problema no es la fraccion, es que no hay nada que dimensionar."""
    import salud
    c = salud.check_sobreapuesta(growth.growth_stats(_perdedora(), 0.01))
    assert c["estado"] == salud.BROKEN
    assert "falta edge" in c["accion"]
