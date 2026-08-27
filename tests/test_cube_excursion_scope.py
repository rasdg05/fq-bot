# -*- coding: utf-8 -*-
"""GUARDA DE ALCANCE DE LA EXCURSION (hallazgo ago-2026, codificado como test).

El cubo de research etiquetaba cada fila con `mfe_r`/`mae_r` medidos sobre TODA
la ventana del horizonte, no sobre la vida del trade. Con senales que viven 10
velas medianas y horizontes de 96/288/576, eso acreditaba recorrido POSTERIOR a
la muerte de la senal: el 83.4% de las perdidas "habia estado a +1R a favor" a
h576 — y esa fraccion CRECIA con el horizonte, que es la firma de la
contaminacion, no un hallazgo.

`label_event` (una senal) siempre lo hizo bien: corta al tocar la barrera.
`label_event_grid` (el cubo) no. Mismo nombre de columna, dos definiciones. De
ahi salio GHOST_MAP H5 ("MFE medio +6.66R, MAE medio -5.65R"), que es
exactamente la ventana de 288 velas.

Lo que fija este test:
  1. Las dos rutas de etiquetado coinciden en `mfe_r`/`mae_r`. UN nombre, UNA
     definicion.
  2. La excursion de celda esta acotada por la de ventana, y es ESTRICTAMENTE
     menor cuando el trade muere antes del horizonte (si vuelven a ser iguales,
     alguien re-cableo la de ventana al nombre corto).
  3. `require_life_scoped` rechaza un cubo de esquema 1 (los .parquet viejos en
     disco, donde `mfe_r` sigue siendo de ventana).
  4. Ningun consumidor lee mfe_r/mae_r de un cubo sin pasar por la guarda.
"""
import ast
import os

import numpy as np
import pandas as pd
import pytest

import bt_labeler as lb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bars(seq):
    """seq: lista de (high, low, close) -> DataFrame OHLC posterior al entry."""
    return pd.DataFrame(seq, columns=["high", "low", "close"])


# Un SHORT que muere en el stop en la vela 2 y DESPUES el precio se desploma:
# el tape recorre +8R, pero la senal ya estaba cerrada.
ENTRY, STOP, TARGET = 100.0, 105.0, 90.0        # R = 5
MUERE_PRONTO = _bars([
    (102.0, 99.0, 101.0),      # 0: nada
    (106.0, 101.0, 105.0),     # 1: toca el stop (high >= 105) -> LOSS, bars_held=2
    (101.0,  95.0,  96.0),     # 2: +1.0R a favor... con la senal ya muerta
    (96.0,   60.0,  62.0),     # 3: +8.0R a favor... idem
])


def test_las_dos_rutas_de_etiquetado_coinciden():
    """label_event y label_event_grid deben dar el MISMO mfe_r/mae_r."""
    uno = lb.label_event(MUERE_PRONTO, ENTRY, STOP, TARGET, lb.SHORT, max_bars=4)
    grid = lb.label_event_grid(MUERE_PRONTO, ENTRY, STOP, lb.SHORT,
                               {"t": TARGET}, [4])
    celda = grid["cells"][("t", 4)]

    assert celda["outcome"] == uno["outcome"] == lb.LOSS
    assert celda["bars_held"] == uno["bars_held"] == 2
    assert celda["mfe_r"] == pytest.approx(uno["mfe_r"])
    assert celda["mae_r"] == pytest.approx(uno["mae_r"])
    # Estando viva, la senal solo llego a +0.2R ((100-99)/5).
    assert celda["mfe_r"] == pytest.approx(0.2)


def test_la_de_ventana_ve_lo_que_la_senal_no_vivio():
    """La excursion de ventana SI recorre el post-mortem: por eso va aparte."""
    grid = lb.label_event_grid(MUERE_PRONTO, ENTRY, STOP, lb.SHORT,
                               {"t": TARGET}, [4])
    assert grid["mfe_horizon_r"][4] == pytest.approx(8.0)      # (100-60)/5
    celda = grid["cells"][("t", 4)]
    assert celda["mfe_r"] < grid["mfe_horizon_r"][4], (
        "la excursion de celda volvio a ser la de ventana: el bug de ago-2026 "
        "esta de vuelta")
    # Y el nombre corto NO debe reaparecer en el nivel de ventana.
    assert "mfe_r" not in grid and "mae_r" not in grid


def test_acotada_por_la_de_ventana_en_todos_los_horizontes():
    grid = lb.label_event_grid(MUERE_PRONTO, ENTRY, STOP, lb.SHORT,
                               {"t": TARGET}, [1, 2, 4])
    for (_, h), celda in grid["cells"].items():
        assert celda["mfe_r"] <= grid["mfe_horizon_r"][h] + 1e-12
        assert celda["mae_r"] >= grid["mae_horizon_r"][h] - 1e-12


def test_orden_de_barras_sellado():
    """mfe_bar/mae_bar son el indice de la vela del extremo, DENTRO de la vida.

    Sin ellos el contrafactual de geometry_report juzga todo empate en el peor
    caso; el cubo nunca los traia.
    """
    grid = lb.label_event_grid(MUERE_PRONTO, ENTRY, STOP, lb.SHORT,
                               {"t": TARGET}, [4])
    celda = grid["cells"][("t", 4)]
    assert celda["mfe_bar"] == 0        # el minimo low de la vida esta en la 0
    assert celda["mae_bar"] == 1        # el high del stop, en la 1
    assert celda["mae_bar"] < celda["bars_held"]
    assert celda["mfe_bar"] < celda["bars_held"]


def test_el_cubo_largo_lleva_las_dos_familias():
    df = pd.concat([_bars([(100.0, 100.0, 100.0)]), MUERE_PRONTO],
                   ignore_index=True)
    ev = [{"entry_index": 0, "entry_price": ENTRY, "stop_price": STOP,
           "direction": lb.SHORT, "px_tp1": TARGET}]
    largo = lb.label_events_grid(df, ev, ["px_tp1"], [4])
    for col in ("mfe_r", "mae_r", "mfe_bar", "mae_bar",
                "mfe_horizon_r", "mae_horizon_r"):
        assert col in largo.columns, col
    assert lb.cube_schema(largo) == 2
    assert float(largo["mfe_r"].iloc[0]) < float(largo["mfe_horizon_r"].iloc[0])


def test_la_guarda_rechaza_el_esquema_viejo():
    viejo = pd.DataFrame({"mfe_r": [6.66], "mae_r": [-5.65], "pnl_r": [-1.0]})
    assert lb.cube_schema(viejo) == 1
    with pytest.raises(ValueError, match="esquema 1"):
        lb.require_life_scoped(viejo, who="el informe de geometria")
    nuevo = viejo.assign(mfe_horizon_r=6.66, mae_horizon_r=-5.65)
    assert lb.require_life_scoped(nuevo) is nuevo


# --- 4. ningun consumidor lee la excursion del cubo sin la guarda -------------

# Modulos que (a) cargan un cubo y (b) nombran mfe_r/mae_r. Cada uno debe
# invocar require_life_scoped, o justificar aqui por que no lo necesita.
CONSUMIDORES_EXENTOS = {
    # camina las velas REALES por trade; no lee la excursion del cubo, solo
    # explica en su docstring por que no puede.
    "tools/trailing_backtest.py":
        "path-based: recorre velas, no lee mfe_r del cubo",
    # es el PRODUCTOR del cubo, no un consumidor.
    "tools/run_research_real.py":
        "productor: llama a label_events_grid",
    # concatena shards del mismo run; no interpreta la columna.
    "tools/cosecha_shard.py":
        "solo concatena/compara columnas entre shards, no las lee como recorrido",
}


def _lee_cubo(src):
    return any(k in src for k in ("tp_cube", "cosecha_cubes", '"--cube"', "'--cube'"))


def test_consumidores_de_excursion_pasan_por_la_guarda():
    faltan = []
    tools = os.path.join(ROOT, "tools")
    for name in sorted(os.listdir(tools)):
        if not name.endswith(".py"):
            continue
        rel = "tools/" + name
        src = open(os.path.join(tools, name), encoding="utf-8").read()
        if not (_lee_cubo(src) and ("mfe_r" in src or "mae_r" in src)):
            continue
        if rel in CONSUMIDORES_EXENTOS:
            continue
        if "require_life_scoped" not in src:
            faltan.append(rel)
    assert not faltan, (
        "leen la excursion de un cubo sin la guarda de alcance: %s. Llama a "
        "bt_labeler.require_life_scoped(cubo) antes de tratar mfe_r/mae_r como "
        "recorrido del trade, o anade el modulo a CONSUMIDORES_EXENTOS con el "
        "motivo." % ", ".join(faltan))
