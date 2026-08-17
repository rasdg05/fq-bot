# -*- coding: utf-8 -*-
"""Brier advantage: los tests fijan el BUG que se encontro midiendo, no una teoria.

El bug real (2026-08-17): ponderar por TRADE mostraba un sesgo de -4/-5pp en el
tramo 0.35-0.80, monotono, sobre millones de trades. Era un artefacto -- un
mercado que cae de 0.60 a 0 genera enorme volumen en la caida, asi que ponderar
por trade sobre-muestrea "estaba caro y resolvio NO". Por MERCADO el sesgo a 1h
es +0.22pp.

Estos tests hacen imposible que ese artefacto vuelva sin que algo falle en rojo.
"""
import numpy as np
import pandas as pd
import pytest

from tools.polymarket_brier import (
    N_MIN_CONCLUYENTE,
    brier_of,
    calibration_table,
    clean_resolutions,
    fit_recalibration,
    market_snapshots,
    parse_final_price,
    realized_edge_pp,
    walk_forward_advantage,
)

T0 = pd.Timestamp("2026-03-01", tz="UTC")


def _markets(rows):
    """rows: (id, closed, outcome_prices, volume)."""
    frame = pd.DataFrame(rows, columns=["id", "closed", "outcome_prices", "volume"])
    frame["end_date"] = T0 + pd.Timedelta(days=10)
    return frame


# --- Trampa 1: el 0.50 no es un desenlace ---------------------------------


def test_parse_final_price_desenvuelve_la_doble_codificacion():
    assert parse_final_price("[\"0.0005\", \"0.9995\"]") == pytest.approx(0.0005)
    assert parse_final_price("\"['0.0005', '0.9995']\"") == pytest.approx(0.0005)
    assert np.isnan(parse_final_price("basura"))


def test_los_mercados_en_050_se_descartan_y_se_cuentan():
    frame = _markets([
        ("a", 1, "['0.0005', '0.9995']", 1e6),   # resolvio NO
        ("b", 1, "['0.9995', '0.0005']", 1e6),   # resolvio SI
        ("c", 1, "['0.5', '0.5']", 1e6),         # NO resolvio: default
        ("d", 1, "['0.48', '0.52']", 1e6),       # ambiguo: tampoco resolvio
    ])
    resolved, descartes = clean_resolutions(frame)

    assert len(resolved) == 2
    assert set(resolved["id"]) == {"a", "b"}
    assert resolved.set_index("id")["y"].to_dict() == {"a": 0, "b": 1}
    assert descartes["sin_desenlace"] == 2           # se cuenta
    assert descartes["en_050_exacto"] == 1           # y el 0.50 se nombra aparte


# --- Trampa 2: LA GRANDE. Una observacion por mercado ---------------------


def _trades_con_colapso(n_caida=500):
    """Un mercado que se desploma de 0.60 a 0 y genera MUCHISIMO volumen en la
    caida, mas mercados tranquilos que resolvieron SI con pocos trades.

    Ponderado por trade, el desplome domina y finge un sesgo. Por mercado, no.
    """
    filas = []
    # el que se desploma: 500 trades, precio bajando, resolvio NO
    for i in range(n_caida):
        filas.append({
            "market_id": "cae",
            "p": 0.60 * (1 - i / n_caida),
            "timestamp": int((T0 + pd.Timedelta(hours=i)).timestamp()),
        })
    # 20 mercados tranquilos a 0.60 que SI ocurrieron: 2 trades cada uno
    for m in range(20):
        for j in range(2):
            filas.append({
                "market_id": f"tranquilo{m}",
                "p": 0.60,
                "timestamp": int((T0 + pd.Timedelta(hours=j)).timestamp()),
            })
    return pd.DataFrame(filas)


def test_ponderar_por_trade_fabrica_un_sesgo_que_por_mercado_NO_existe():
    """EL test de este archivo. Si se rompe, volvio el artefacto de -4pp."""
    trades = _trades_con_colapso()
    resueltos = _markets(
        [("cae", 1, "['0.0005', '0.9995']", 1e6)]
        + [(f"tranquilo{m}", 1, "['0.9995', '0.0005']", 1e6) for m in range(20)]
    )
    resueltos["end_date"] = T0 + pd.Timedelta(days=30)
    resolved, _ = clean_resolutions(resueltos)

    unido = trades.join(
        resolved.set_index(resolved["id"].astype(str))[["y"]], on="market_id", how="inner"
    )
    sesgo_por_trade = (unido["y"].mean() - unido["p"].mean()) * 100

    snaps = market_snapshots(
        trades, resolved, lead_hours=24 * 25, tolerance_hours=24 * 30
    )
    sesgo_por_mercado = (snaps["y"].mean() - snaps["p"].mean()) * 100

    assert len(snaps) == 21                       # UNA fila por mercado, no 540
    assert sesgo_por_trade < -20                  # el artefacto: enorme y negativo
    assert sesgo_por_mercado > 20                 # la verdad: del signo CONTRARIO
    assert abs(sesgo_por_trade - sesgo_por_mercado) > 40


def test_market_snapshots_no_repite_ningun_mercado():
    trades = _trades_con_colapso(n_caida=50)
    resueltos = _markets(
        [("cae", 1, "['0.0005', '0.9995']", 1e6)]
        + [(f"tranquilo{m}", 1, "['0.9995', '0.0005']", 1e6) for m in range(20)]
    )
    resueltos["end_date"] = T0 + pd.Timedelta(days=30)
    resolved, _ = clean_resolutions(resueltos)
    snaps = market_snapshots(trades, resolved, lead_hours=1, tolerance_hours=24 * 40)
    assert snaps["market_id"].is_unique


def test_solo_entran_trades_ANTERIORES_al_cierre():
    """Un trade posterior al cierre no es informacion: es el desenlace filtrado."""
    resueltos = _markets([("m", 1, "['0.9995', '0.0005']", 1e6)])
    resueltos["end_date"] = T0
    resolved, _ = clean_resolutions(resueltos)
    trades = pd.DataFrame({
        "market_id": ["m", "m"],
        "p": [0.4, 0.99],
        "timestamp": [
            int((T0 - pd.Timedelta(hours=5)).timestamp()),
            int((T0 + pd.Timedelta(hours=5)).timestamp()),   # DESPUES: prohibido
        ],
    })
    snaps = market_snapshots(trades, resolved, lead_hours=5, tolerance_hours=48)
    assert len(snaps) == 1
    assert snaps["p"].iloc[0] == pytest.approx(0.4)


# --- La n que se reporta y el marcado de muestra chica --------------------


def test_calibracion_marca_los_buckets_con_menos_de_30_mercados():
    snaps = pd.DataFrame({
        "p": [0.7] * 10 + [0.3] * 50,
        "y": [1] * 10 + [0] * 50,
    })
    tabla = calibration_table(snaps)
    chico = tabla[tabla["bucket"].str.startswith("(0.65")]
    grande = tabla[tabla["bucket"].str.startswith("(0.2")]
    assert bool(chico["thin"].iloc[0]) is True
    assert bool(grande["thin"].iloc[0]) is False


def test_brier_marca_muestra_chica_y_calcula_skill():
    res = brier_of([0.5] * 10, [1] * 5 + [0] * 5)
    assert res.n_markets == 10
    assert res.thin is True
    assert res.brier == pytest.approx(0.25)
    assert res.skill == pytest.approx(0.0)          # 0.5 == tasa base: sin skill

    bueno = brier_of([0.9] * 50 + [0.1] * 50, [1] * 50 + [0] * 50)
    assert bueno.brier < bueno.brier_base
    assert bueno.skill > 0.5


# --- Sin fuga: la recalibracion se ajusta SOLO con el pasado --------------


def test_sobre_ruido_puro_la_recalibracion_NO_gana_fuera_de_muestra():
    """El test que impide fabricar edge inexistente.

    Precio aleatorio, desenlace aleatorio e INDEPENDIENTE: no hay nada que
    aprender. Un mapa ajustado en muestra ganaria; fuera de muestra no puede.
    Si esto empieza a dar ventaja positiva y grande, hay fuga.
    """
    rng = np.random.default_rng(0)
    n = 4000
    p = rng.uniform(0.05, 0.95, n)
    y = rng.binomial(1, p)               # el precio ES la probabilidad: calibrado
    snaps = pd.DataFrame({
        "p": p, "y": y,
        "end_date": pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
    })
    mkt, mod, edge, n_oos = walk_forward_advantage(snaps, n_folds=4)

    assert n_oos > 0
    ventaja = mkt.brier - mod.brier
    assert ventaja < 0.005                                   # ninguna ventaja real
    assert edge["edge_pp"] - 1.96 * edge["se_pp"] < 0        # IC95% incluye el cero


def test_la_recalibracion_SI_encuentra_un_sesgo_real_y_lo_corrige():
    """Contraparte del anterior: si el sesgo existe, tiene que verse."""
    rng = np.random.default_rng(1)
    n = 6000
    p_mkt = rng.uniform(0.10, 0.90, n)
    p_true = np.clip(p_mkt - 0.10, 0.01, 0.99)     # el mercado sobrevalora 10pp
    y = rng.binomial(1, p_true)
    snaps = pd.DataFrame({
        "p": p_mkt, "y": y,
        "end_date": pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
    })
    mkt, mod, edge, _ = walk_forward_advantage(snaps, n_folds=4)

    assert mod.brier < mkt.brier                             # el modelo gana
    assert edge["edge_pp"] > 5                               # y se cobra en puntos
    assert edge["edge_pp"] - 1.96 * edge["se_pp"] > 0


def test_un_bin_con_muestra_chica_no_se_ajusta_deja_pasar_el_mercado():
    """Ajustar un bin con n<30 es como el +1.47R de n=17: ruido con decimales.

    Los bins son por cuantil, asi que cada uno lleva ~n/n_bins. Con muestra
    total chica TODOS los bins caen bajo el piso y el mapa debe volverse la
    identidad -- devolver el precio del mercado en vez de inventar un ajuste.
    """
    rng = np.random.default_rng(3)
    # 80 obs / 8 bins = 10 por bin: por debajo del piso de 30
    p_chico = rng.uniform(0.2, 0.8, 80)
    y_chico = np.zeros(80)                     # sesgo brutal, pero sin muestra
    mapper_chico = fit_recalibration(p_chico, y_chico, n_bins=8)
    assert mapper_chico([0.5])[0] == pytest.approx(0.5)     # no toca nada

    # 800 obs / 8 bins = 100 por bin: ahora si hay con que ajustar
    p_grande = rng.uniform(0.2, 0.8, 800)
    y_grande = np.zeros(800)
    mapper_grande = fit_recalibration(p_grande, y_grande, n_bins=8)
    assert mapper_grande([0.5])[0] < 0.1                    # y corrige a la baja


# --- El edge realizado, que es lo que se compara con el breakeven ---------


def test_edge_realizado_en_puntos_y_su_error_estandar():
    # el modelo dice 0.6 donde el mercado dice 0.5, y ocurre el 60% de las veces
    n = 1000
    p_mkt = np.full(n, 0.5)
    p_mod = np.full(n, 0.6)
    y = np.zeros(n)
    y[: int(n * 0.6)] = 1.0
    out = realized_edge_pp(p_mkt, p_mod, y)

    assert out["edge_pp"] == pytest.approx(10.0, abs=0.01)   # (0.6-0.5)*100
    assert out["n_trades"] == n
    assert out["se_pp"] > 0                                  # SIEMPRE con su EE


def test_edge_realizado_es_negativo_cuando_el_modelo_se_equivoca():
    n = 1000
    p_mkt = np.full(n, 0.5)
    p_mod = np.full(n, 0.7)          # dice que esta barato...
    y = np.zeros(n)
    y[: int(n * 0.3)] = 1.0          # ...y ocurre solo el 30%
    assert realized_edge_pp(p_mkt, p_mod, y)["edge_pp"] < 0


def test_sin_discrepancia_no_hay_trade():
    p = np.full(100, 0.5)
    out = realized_edge_pp(p, p, np.zeros(100), threshold=0.0)
    assert out["n_trades"] == 0
    assert np.isnan(out["edge_pp"])


def test_walk_forward_se_niega_con_muestra_insuficiente():
    snaps = pd.DataFrame({
        "p": [0.5] * (N_MIN_CONCLUYENTE - 1),
        "y": [1] * (N_MIN_CONCLUYENTE - 1),
        "end_date": pd.date_range("2026-01-01", periods=N_MIN_CONCLUYENTE - 1, freq="h", tz="UTC"),
    })
    assert walk_forward_advantage(snaps) is None
