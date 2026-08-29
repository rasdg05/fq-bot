# -*- coding: utf-8 -*-
"""La lectura NO circular de separacion, y las dos trampas que la sostienen.

geometry_report no puede contestar "la senal separa?" porque comparar el
recorrido de ganadores contra el de perdedores es circular (ganar ES tocar el
TP). La version honesta mira una ventana FIJA de k velas y pregunta si predice
el desenlace POSTERIOR. Dos condiciones la mantienen honesta, y las dos se fijan
aqui:

  1. Solo entran las senales VIVAS en la vela k. Si una resolvio dentro de la
     ventana, su desenlace esta contenido en ella y la circularidad vuelve.
  2. El resultado no vale sin PLACEBO. Un AUC de 0.69 sobre el recorrido
     temprano parece separacion y no lo es: una entrada arbitraria sobre la
     misma cinta da lo mismo (medido ago-2026: diferencia +0.000 a -0.012 en
     net_k). Lo que mide es que el precio que ya se movio hacia el TP lo tiene
     mas cerca -- una propiedad del camino, no de la senal.
"""
import numpy as np
import pytest

from tools.cube_fixed_window import auc, auc_ci


def test_auc_de_una_moneda_es_media():
    rng = np.random.default_rng(0)
    y = rng.random(4000) < 0.4
    s = rng.normal(size=4000)                 # score sin relacion con y
    a = auc(s, y)
    lo, hi = auc_ci(s, y, n_boot=300)
    assert lo < 0.5 < hi, "un score aleatorio debe ser indistinguible de 0.5"
    assert abs(a - 0.5) < 0.05


def test_auc_de_un_separador_perfecto_es_uno():
    y = np.array([True] * 50 + [False] * 50)
    s = np.concatenate([np.ones(50), np.zeros(50)])
    assert auc(s, y) == pytest.approx(1.0)
    assert auc(-s, y) == pytest.approx(0.0)


def test_los_empates_valen_medio():
    y = np.array([True, True, False, False])
    assert auc(np.ones(4), y) == pytest.approx(0.5)


def test_auc_indefinido_sin_una_de_las_clases():
    y = np.array([True, True, True])
    assert np.isnan(auc(np.array([1.0, 2.0, 3.0]), y))


def test_la_condicion_de_seguir_viva_no_es_lookahead():
    """`bars_held > k` se sabe EN la vela k: es lo que un operador tiene delante.

    Y es imprescindible: sin ella entran senales ya resueltas, cuyo recorrido
    en [0,k] CONTIENE el desenlace, y el AUC se dispara por construccion.
    """
    k = 10
    # dos senales resueltas dentro de la ventana: la ganadora llego a +3R, la
    # perdedora a -1R. Incluirlas hace el AUC perfecto sin que nadie prediga nada.
    vivas = [{"bars_held": 4, "gana": True, "mfe": 3.0},
             {"bars_held": 3, "gana": False, "mfe": 0.0}]
    y = np.array([s["gana"] for s in vivas])
    assert auc(np.array([s["mfe"] for s in vivas]), y) == pytest.approx(1.0)
    # ...y todas quedan fuera del filtro, que es justo el punto.
    assert [s for s in vivas if s["bars_held"] > k] == []
