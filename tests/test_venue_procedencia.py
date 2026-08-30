# -*- coding: utf-8 -*-
"""GUARDA DE PROCEDENCIA: de que venue salio cada fichero (ago-2026).

El repo tenia un directorio `data/okx/` en el que escribian TRES fetchers de
Binance. Un nombre de carpeta es una convencion que nadie hace cumplir: cuando
hubo que re-etiquetar el cube se bajaron 200 MB del venue equivocado, y lo
delato un `bars_held` que no cuadraba (0.766 con Binance, 1.0000 con OKX spot),
no el nombre del directorio. Nada DENTRO del fichero decia de donde venia.

Por que importa: si las velas no son las del venue con el que se cosecho, cambia
el bar en que salta la barrera, y con el la vida del trade -- que es justo lo que
la excursion en vida recorta.

Lo que se fija aqui:
  1. El sello viaja en el DATO (una columna), no en el nombre del fichero.
  2. Un fichero SIN sello no se inventa: la guarda calla. Mentir por omision
     seria peor que no comprobar.
  3. Los fetchers de velas sellan. Los puntos donde se CRUZAN dos datasets
     comprueban.
  4. El cruce spot/perp del CostModel se NOMBRA siempre que ocurre.
"""
import ast
import os

import pandas as pd
import pytest

import bt_data as btd
from tools.cube_net_expectancy import aviso_venue

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _df(venue=None, n=3):
    d = pd.DataFrame({"ts": range(n), "close": [1.0] * n})
    return btd.stamp_venue(d, venue) if venue else d


# --- 1 y 2: el sello, y el silencio honesto cuando no lo hay ----------------

def test_el_sello_viaja_en_el_dato():
    d = _df(btd.VENUE_OKX_SPOT)
    assert btd.VENUE_COL in d.columns
    assert btd.venue_of(d) == "okx_spot"


def test_un_fichero_sin_sello_no_se_inventa():
    assert btd.venue_of(_df()) is None
    assert btd.venue_of(_df(), default="?") == "?"
    # ...y cruzarlo con uno sellado NO falla: la guarda solo afirma sobre lo
    # que esta sellado.
    assert btd.require_same_venue(_df(), _df(btd.VENUE_OKX_SPOT)) == "okx_spot"


def test_un_fichero_con_venues_mezclados_es_un_error():
    d = _df(btd.VENUE_OKX_SPOT)
    d.loc[1, btd.VENUE_COL] = btd.VENUE_BINANCE_UM
    with pytest.raises(ValueError, match="mezclados"):
        btd.venue_of(d)


def test_cruzar_venues_distintos_falla_y_dice_cuales():
    with pytest.raises(ValueError) as e:
        btd.require_same_venue(_df(btd.VENUE_OKX_SPOT), _df(btd.VENUE_BINANCE_UM),
                               who="el regrade", nombres=("el cubo", "las velas"))
    msg = str(e.value)
    assert "okx_spot" in msg and "binance_um" in msg and "el regrade" in msg


def test_spot_y_swap_del_mismo_exchange_no_son_el_mismo_tape():
    """Verificado con datos reales: el entry_price del cube coincide 5/5 con OKX
    spot y 0/5 con OKX swap. El sufijo del venue no es decorativo."""
    assert btd.VENUE_OKX_SPOT != btd.VENUE_OKX_SWAP
    with pytest.raises(ValueError):
        btd.require_same_venue(_df(btd.VENUE_OKX_SPOT), _df(btd.VENUE_OKX_SWAP))


# --- 3: quien sella y quien comprueba ---------------------------------------

def _fuente(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def test_los_fetchers_de_velas_sellan_su_venue():
    faltan = []
    tools = os.path.join(ROOT, "tools")
    for name in sorted(os.listdir(tools)):
        if not (name.startswith("fetch_") and name.endswith(".py")):
            continue
        if "klines" not in name and "life_windows" not in name:
            continue
        if "stamp_venue" not in _fuente("tools/" + name):
            faltan.append("tools/" + name)
    assert not faltan, (
        "estos fetchers de velas no sellan su venue, asi que quien las lea no "
        "puede saber de que tape salieron: %s" % ", ".join(faltan))


def test_los_cruces_comprueban_el_venue():
    """sl_noise_screen compara el stop de un CUBO contra la vela de unas KLINES.
    Si no son el mismo tape, el cociente no significa nada."""
    assert "require_same_venue" in _fuente("tools/sl_noise_screen.py")


def test_el_cubo_reetiquetado_hereda_el_venue_de_sus_velas():
    src = _fuente("tools/cube_regrade_excursion.py")
    assert "venue_of" in src and "VENUE_COL" in src


# --- 4: el cruce spot/perp se nombra ----------------------------------------

class _Cost:
    def __init__(self, apply_funding=True):
        self.apply_funding = apply_funding


def test_el_cruce_spot_perp_se_avisa():
    av = aviso_venue(btd.VENUE_OKX_SPOT, _Cost(apply_funding=True))
    assert av and "okx_spot" in av and "funding" in av
    assert "re-cosechar" in av, "el aviso debe decir cual es el arreglo de verdad"


def test_sin_cruce_no_hay_ruido():
    assert aviso_venue(btd.VENUE_OKX_SPOT, _Cost(apply_funding=False)) is None
    assert aviso_venue(btd.VENUE_BINANCE_UM, _Cost(apply_funding=True)) is None
    assert aviso_venue(None, _Cost(apply_funding=True)) is None


def test_el_directorio_heredado_ya_no_es_el_defecto():
    """`data/okx/` guardaba velas de Binance. Se mantiene como FALLBACK para no
    romper datos locales, pero el defecto de una instalacion nueva es neutral."""
    for rel in ("tools/fetch_binance_vision_klines.py",
                "tools/fetch_binance_vision_cvd.py",
                "motor_paper.py"):
        src = _fuente(rel)
        assert "data/mercado" in src, rel
        # y si menciona el viejo, es solo como fallback condicionado
        if '"data/okx"' in src:
            assert 'os.path.isdir("data/okx")' in src, (
                "%s usa data/okx sin comprobar que exista: eso lo convierte en "
                "el defecto otra vez" % rel)
