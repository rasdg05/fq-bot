# -*- coding: utf-8 -*-
"""GUARDA ANTI-CIRCULARIDAD DE geometry_report (hallazgo ago-2026).

`report_distribution` comparaba el MFE medio de los ganadores contra el de los
perdedores y dictaba "Se solapan / Separan". Esa comparacion es CIRCULAR: un
ganador ES el que toco el TP, luego su MFE >= rr por construccion; un perdedor no
lo toco, luego su MFE < rr. Los dos grupos no pueden solaparse, asi que el
veredicto "Separan. Hay margen para que la geometria capture mas" salia SIEMPRE.

Medido sobre el cube re-etiquetado (7 simbolos, ago-2026): 96.5% de los
ganadores cumplen MFE >= rr y 0.0% de los perdedores.

Importa porque el BRIEF pone a `geometry_report` como condicion de desbloqueo de
E6 ("Tocar TP/SL: >=30 cierres con recorrido sellado + veredicto de
geometry_report"). Con la lectura circular, ese candado se abria solo.

Y el contrafactual tiene un sesgo distinto, tambien medido contra el camino real:
exacto en SL=1.00 (que ES el stop original, porque R = |entry - stop|), pero
sobreestima hasta +0.083R al estrechar el stop y subestima hasta -0.052R al
ensancharlo. Sobre una expectancy de ~0.2R es un 40%, y apunta justo a "aprieta
el stop".
"""
import os

import pytest

import tools.geometry_report as G

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cierres sinteticos con la MISMA mecanica que el motor: R=1 por definicion,
# el TP en +2R. Un ganador sale en +2R (y su MFE no puede ser menor); un
# perdedor sale en -1R (y su MFE no llego a +2R, o habria ganado).
RR = 2.0
CLOSES = (
    [{"pnl_r": RR, "mfe_r": RR + 0.05 * i, "mae_r": -0.2 - 0.05 * i,
      "bars_held": 8, "mfe_bar": 5, "mae_bar": 2} for i in range(20)]
    + [{"pnl_r": -1.0, "mfe_r": 0.1 + 0.05 * i, "mae_r": -1.0 - 0.02 * i,
        "bars_held": 6, "mfe_bar": 1, "mae_bar": 4} for i in range(20)]
)


def _salida(fn, *a):
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a)
    return buf.getvalue()


def test_la_circularidad_es_real_no_una_opinion():
    """Con TP fijo, las dos clases NO pueden solaparse. Esto lo demuestra."""
    wins = [c for c in CLOSES if c["pnl_r"] > 0]
    loss = [c for c in CLOSES if c["pnl_r"] <= 0]
    assert min(c["mfe_r"] for c in wins) >= RR
    assert max(c["mfe_r"] for c in loss) < RR
    # ...luego el "hueco" entre las medias esta acotado por abajo, y el umbral
    # de 0.25R del veredicto viejo no podia no superarse.
    mw = sum(c["mfe_r"] for c in wins) / len(wins)
    ml = sum(c["mfe_r"] for c in loss) / len(loss)
    assert mw - ml > 0.25


def test_ya_no_se_dicta_veredicto_de_separacion():
    out = _salida(G.report_distribution, CLOSES)
    for prohibido in ("Separan", "Se solapan", "NO separa"):
        assert prohibido not in out, (
            "volvio el veredicto circular de separacion: %r" % prohibido)
    assert "circular" in out
    assert "ventana FIJA" in out


def test_la_nota_explica_por_que_no_se_calcula():
    out = _salida(G.separacion_nota)
    assert "circular" in out and "MFE >= rr" in out


def test_las_lecturas_no_circulares_siguen_vivas():
    """tp_demasiado_lejos y sl_demasiado_cerca NO son circulares y se quedan.

    Un perdedor se define por tocar el STOP, asi que preguntar cuanto llego a
    ganar antes de morir es legitimo. Un ganador se define por tocar el TP, asi
    que su MAE es libre en (-1R, 0]. La circularidad estaba solo en comparar el
    MFE de una clase contra el de la otra.
    """
    assert "MFE >= 1.0R" in _salida(G.report_tp_too_far, CLOSES).replace(
        "MFE >= 1.0R", "MFE >= 1.0R")
    out = _salida(G.report_sl_too_tight, CLOSES)
    assert "ganadores que llegaron a -0.7R o peor" in out


def test_el_contrafactual_declara_el_sesgo_del_eje_sl():
    out = _salida(G.counterfactual, CLOSES, [1.0, 2.0], [0.5, 1.0, 1.5])
    assert "SL = 1.00" in out and "exacto" in out
    assert "SOBREESTIMA" in out and "SUBESTIMA" in out


def test_ningun_tool_dicta_separacion_desde_excursion_sellada():
    """Barrido: que nadie reintroduzca el veredicto en otro modulo."""
    malos = []
    tools = os.path.join(ROOT, "tools")
    for name in sorted(os.listdir(tools)):
        if not name.endswith(".py"):
            continue
        src = open(os.path.join(tools, name), encoding="utf-8").read()
        if "mfe_r" not in src:
            continue
        for frase in ("Separan.", "Se solapan.", "senal NO separa",
                      "señal NO separa"):
            if frase in src and "circular" not in src:
                malos.append("tools/%s (%r)" % (name, frase))
    assert not malos, (
        "dictan separacion desde la excursion sellada sin declarar la "
        "circularidad: %s" % ", ".join(malos))
