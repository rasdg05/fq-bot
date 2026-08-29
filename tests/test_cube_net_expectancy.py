# -*- coding: utf-8 -*-
"""E8: el cube con costes, y donde se llena el stop.

El cube etiqueta con triple barrera y SIN modelo de fill: asume que el stop se
llena exacto en `stop_price`. Medido sobre 49.808 perdidas, la vela que lo
dispara se pasa +0.388R de media. Una orden stop es MARKET: se llena en algun
punto entre el nivel y el extremo de la vela, y ese punto no esta en el dato.

Por eso `aplicar_sobrepaso` es un BARRIDO, no una estimacion. Lo que este test
fija son las propiedades que lo hacen honesto:
  - frac=0 devuelve el pool intacto (la hipotesis optimista del cube);
  - frac=1 lleva el fill al extremo de la vela (el peor caso posible);
  - el fill siempre cae ENTRE el nivel y el extremo, en ambas direcciones;
  - solo toca las salidas por STOP. El TP es orden LIMITE: se llena a tu precio,
    y su sobrepaso (+0.485R medido) ni se cobra ni se paga. La asimetria es de un
    solo lado y va en contra: fijarla evita que alguien "compense" una con otra.
"""
import numpy as np
import pandas as pd
import pytest

import bt_labeler as lb
from tools.cube_net_expectancy import aplicar_sobrepaso, neto


def _pool():
    """Dos perdedoras (LONG y SHORT) y una ganadora, con esquema 2."""
    return pd.DataFrame({
        "entry_price": [100.0, 100.0, 100.0],
        "stop_price":  [99.0, 101.0, 99.0],       # risk = 1.0 en las tres
        "direction":   [1, -1, 1],
        "outcome":     [lb.LOSS, lb.LOSS, lb.WIN],
        "exit_price":  [99.0, 101.0, 103.0],
        "bars_held":   [5, 5, 9],
        "pnl_r":       [-1.0, -1.0, 3.0],
        "mae_r":       [-1.5, -1.8, -0.4],        # la vela se paso 0.5R y 0.8R
        "mfe_r":       [0.3, 0.2, 3.0],
        "mfe_horizon_r": [2.0, 2.0, 4.0],         # marca el esquema 2
        "mae_horizon_r": [-3.0, -3.0, -1.0],
    })


def test_frac_cero_no_toca_nada():
    p = _pool()
    assert aplicar_sobrepaso(p, 0.0)["exit_price"].tolist() == p["exit_price"].tolist()


def test_frac_uno_lleva_el_fill_al_extremo_de_la_vela():
    q = aplicar_sobrepaso(_pool(), 1.0)
    # LONG: extremo = entry + mae_r*risk = 100 + (-1.5)(1) = 98.5
    assert q["exit_price"].iloc[0] == pytest.approx(98.5)
    # SHORT: extremo = entry - mae_r*risk = 100 + 1.8 = 101.8 (por encima)
    assert q["exit_price"].iloc[1] == pytest.approx(101.8)


def test_el_fill_siempre_cae_entre_el_nivel_y_el_extremo():
    p = _pool()
    for frac in (0.25, 0.5, 0.75):
        q = aplicar_sobrepaso(p, frac)
        for i in (0, 1):
            st = p["stop_price"].iloc[i]
            ext = 98.5 if i == 0 else 101.8
            px = q["exit_price"].iloc[i]
            assert min(st, ext) <= px <= max(st, ext), (frac, i, px)


def test_la_ganadora_no_se_toca_nunca():
    """El TP es LIMITE: se llena a tu precio. Su sobrepaso no entra."""
    for frac in (0.25, 1.0):
        q = aplicar_sobrepaso(_pool(), frac)
        assert q["exit_price"].iloc[2] == pytest.approx(103.0)


def test_mas_sobrepaso_nunca_mejora_el_neto():
    """Monotonia: el barrido solo puede ir a peor. Si sube, hay un signo mal."""
    previo = None
    for frac in (0.0, 0.25, 0.5, 1.0):
        r = neto(_pool(), "TEST", fill_frac=frac)
        m = r["neto_r"].mean()
        if previo is not None:
            assert m <= previo + 1e-9, "el sobrepaso mejoro el neto en frac=%s" % frac
        previo = m


def test_rechaza_un_cubo_de_esquema_1():
    """Sin la guarda, mae_r seria la excursion de VENTANA y el fill se iria muy
    por debajo del stop real (a -9R en el peor caso medido)."""
    viejo = _pool().drop(columns=["mfe_horizon_r", "mae_horizon_r"])
    with pytest.raises(ValueError, match="esquema 1"):
        neto(viejo, "TEST")
