# -*- coding: utf-8 -*-
"""Horquilla efectiva: los estimadores recuperan un spread CONOCIDO.

Un estimador que nadie verificó contra una verdad sintetica es una opinion con
decimales. Aqui se construyen series con horquilla impuesta y se comprueba que
cada estimador la recupera — y que las dos trampas del venue (perspectiva YES y
fraccionamiento de ordenes) rompen el numero si no se tratan.

Sin red y sin parquet.
"""
import numpy as np
import pandas as pd
import pytest

from tools.polymarket_spread import (
    bounce_spread,
    collapse_taker_orders,
    correct_roll,
    direction_autocorr,
    normalize_yes,
    roll_correction_factor,
    roll_spread,
    summarize_bounce,
    summarize_roll,
    verdict,
)


def _serie_con_horquilla(
    spread=0.02, n=400, mid=0.50, drift_sigma=0.0, seed=0, market="m1", sides="alterna"
):
    """Precio eficiente + rebote: el comprador paga mid+s/2, el vendedor cobra
    mid-s/2. `drift_sigma` mete deriva real encima.

    `sides` importa mucho y por eso es explicito:
      "alterna" -> BUY/SELL perfectamente alternados (rho1 = -1)
      "iid"     -> signo aleatorio 50/50 (rho1 = 0), que es LO QUE ROLL SUPONE
    Con "alterna", Roll devuelve 2x la horquilla real: no es un bug del codigo,
    es el supuesto iid del estimador. Ver test_roll_sesgado_por_autocorrelacion.
    """
    rng = np.random.default_rng(seed)
    mids = mid + np.cumsum(rng.normal(0, drift_sigma, n)) if drift_sigma else np.full(n, mid)
    if sides == "alterna":
        lados = np.where(np.arange(n) % 2 == 0, "BUY", "SELL")
    else:
        lados = np.where(rng.random(n) < 0.5, "BUY", "SELL")
    signo = np.where(lados == "BUY", 1.0, -1.0)
    precios = mids + signo * spread / 2.0
    return pd.DataFrame({
        "market_id": market,
        "transaction_hash": [f"0x{i:064x}" for i in range(n)],
        "side": lados,
        "p": precios,
        "usd": 1000.0,
        "ts": np.arange(n),
        "li": 0,
    })


# --- Los estimadores recuperan una horquilla conocida ----------------------


@pytest.mark.parametrize("spread", [0.005, 0.02, 0.05])
def test_rebote_recupera_la_horquilla_impuesta(spread):
    est = bounce_spread(_serie_con_horquilla(spread=spread), min_pairs=10)
    assert len(est) == 1
    assert est["spread"].iloc[0] == pytest.approx(spread, abs=1e-9)
    assert est["frac_neg"].iloc[0] == 0.0          # sin deriva, ningun par negativo


@pytest.mark.parametrize("spread", [0.01, 0.04])
def test_roll_recupera_la_horquilla_con_flujo_iid(spread):
    """Roll SOLO es insesgado con signo iid, que es su supuesto declarado."""
    serie = _serie_con_horquilla(spread=spread, n=8000, sides="iid", seed=7)
    est = roll_spread(serie, min_orders=10)
    assert len(est) == 1
    assert est["cov"].iloc[0] < 0                  # el rebote da covarianza negativa
    assert est["roll"].iloc[0] == pytest.approx(spread, rel=0.06)


def test_roll_sesgado_por_autocorrelacion_y_la_correccion_lo_arregla():
    """El hallazgo del dato real: en Polymarket rho1 = +0.234, no 0.

    Roll supone iid. Con signo alternado (rho1 = -1) Roll devuelve 2x la
    horquilla real. La correccion sqrt(1 + rho2 - 2*rho1) la recupera. Si esto
    se rompe, el veredicto viajaria con un sesgo desconocido.
    """
    spread = 0.02
    serie = _serie_con_horquilla(spread=spread, n=2000, sides="alterna")
    crudo = roll_spread(serie, min_orders=10)["roll"].iloc[0]
    assert crudo == pytest.approx(2 * spread, rel=0.05)      # 2x: el sesgo

    ac = direction_autocorr(serie, min_orders=10)
    rho1, rho2 = ac["rho1"].iloc[0], ac["rho2"].iloc[0]
    assert rho1 == pytest.approx(-1.0, abs=0.01)             # alternancia perfecta
    assert crudo / roll_correction_factor(rho1, rho2) == pytest.approx(spread, rel=0.05)


def test_la_correccion_se_niega_cuando_el_modelo_no_aplica():
    """Radicando <= 0: el modelo de Roll no describe la serie. NaN, no un numero."""
    assert np.isnan(roll_correction_factor(rho1=0.9, rho2=0.0))   # 1+0-1.8 < 0
    assert np.isnan(roll_correction_factor(rho1=float("nan"), rho2=0.0))
    assert roll_correction_factor(rho1=0.0, rho2=0.0) == pytest.approx(1.0)  # iid: sin correccion


def test_el_rebote_aguanta_deriva_y_lo_declara():
    """La deriva es media-cero: la MEDIA sobrevive, pero frac_neg debe subir
    para que se vea que el estimador esta trabajando con ruido encima."""
    limpio = bounce_spread(_serie_con_horquilla(spread=0.02, drift_sigma=0.0), min_pairs=10)
    sucio = bounce_spread(
        _serie_con_horquilla(spread=0.02, drift_sigma=0.02, n=4000), min_pairs=10
    )
    assert sucio["spread"].iloc[0] == pytest.approx(0.02, abs=0.005)
    assert sucio["frac_neg"].iloc[0] > limpio["frac_neg"].iloc[0]
    assert limpio["frac_neg"].iloc[0] == 0.0


def test_roll_indefinido_queda_NaN_y_se_reporta():
    """Con momentum (cov>0) Roll no existe. Poner cero seria mentir."""
    rng = np.random.default_rng(0)
    n = 300
    precios = 0.5 + np.cumsum(np.abs(rng.normal(0.001, 0.0002, n)))  # tendencia pura
    frame = pd.DataFrame({
        "market_id": "m1", "side": "BUY", "p": precios,
        "usd": 1000.0, "ts": np.arange(n), "li": 0,
    })
    est = roll_spread(frame, min_orders=10)
    assert np.isnan(est["roll"].iloc[0])
    resumen = summarize_roll(est)
    assert resumen.diagnostic == pytest.approx(1.0)   # 100% indefinido, dicho


# --- Trampa (a): la perspectiva del venue ---------------------------------


def test_normalizacion_yes_voltea_precio_y_lado():
    frame = pd.DataFrame({
        "price": [0.30, 0.30],
        "taker_direction": ["BUY", "BUY"],
        "nonusdc_side": ["token1", "token2"],
    })
    out = normalize_yes(frame)
    assert out["p"].tolist() == [0.30, 0.70]          # comprar NO a 0.30 = YES a 0.70
    assert out["side"].tolist() == ["BUY", "SELL"]    # ...y es VENDER YES


def test_sin_normalizar_los_lados_salen_desbalanceados():
    """En crudo el venue reporta ~89% SELL. Si alguien mide sobre eso, mide la
    codificacion del venue y no la horquilla."""
    frame = pd.DataFrame({
        "price": [0.4] * 100,
        "taker_direction": ["SELL"] * 90 + ["BUY"] * 10,
        "nonusdc_side": ["token2"] * 80 + ["token1"] * 20,
    })
    crudo = frame["taker_direction"].value_counts(normalize=True)["SELL"]
    normalizado = normalize_yes(frame)["side"].value_counts(normalize=True)["SELL"]
    assert crudo == pytest.approx(0.90)
    assert normalizado < crudo                        # la normalizacion reequilibra


# --- Trampa (b): el fraccionamiento de ordenes ----------------------------


def test_colapso_por_transaccion_junta_los_fills_al_vwap():
    frame = pd.DataFrame({
        "market_id": ["m1"] * 3,
        "transaction_hash": ["0xaa", "0xaa", "0xbb"],
        "side": ["BUY", "BUY", "SELL"],
        "p": [0.50, 0.60, 0.40],
        "usd_amount": [100.0, 300.0, 50.0],
        "timestamp": [1, 1, 2],
        "log_index": [0, 1, 2],
    })
    ordenes = collapse_taker_orders(frame)
    assert len(ordenes) == 2                                   # 3 fills -> 2 ordenes
    compra = ordenes[ordenes["side"] == "BUY"].iloc[0]
    assert compra["p"] == pytest.approx(0.575)                 # (0.5*100+0.6*300)/400
    assert compra["usd"] == pytest.approx(400.0)


def test_el_colapso_NO_cambia_el_rebote_y_asi_debe_ser():
    """CORRECCION medida (2026-08-17). La primera version de este test afirmaba
    que sin colapsar el rebote se sesgaba hacia cero. Es FALSO: sobre datos
    reales el efecto es -0.0%.

    La razon: los fills consecutivos de una misma orden comparten lado, y el
    estimador solo usa pares donde el lado CAMBIA -- ya quedaban fuera solos.
    El colapso se mantiene porque el precio del taker es el VWAP de su orden,
    no porque mueva el numero. Este test fija esa verdad, no la comoda.
    """
    base = _serie_con_horquilla(spread=0.02, n=200)
    partido = base.loc[base.index.repeat(3)].reset_index(drop=True)
    partido = partido.rename(columns={"usd": "usd_amount", "ts": "timestamp", "li": "log_index"})
    partido["log_index"] = np.arange(len(partido))

    sin_colapsar = bounce_spread(
        partido.rename(columns={"usd_amount": "usd"}), min_pairs=10
    )["spread"].iloc[0]
    colapsado = bounce_spread(collapse_taker_orders(partido), min_pairs=10)["spread"].iloc[0]

    assert colapsado == pytest.approx(0.02, abs=1e-9)
    assert sin_colapsar == pytest.approx(colapsado, abs=1e-9)   # identicos, medido


# --- El veredicto no elige el estimador por su resultado ------------------


def test_el_veredicto_usa_el_estimador_mas_ADVERSO():
    barato = summarize_bounce(bounce_spread(_serie_con_horquilla(spread=0.01), min_pairs=10))
    caro = summarize_roll(roll_spread(_serie_con_horquilla(spread=0.05), min_orders=10))
    out = verdict(barato, caro, edge_pp=2.0)
    # 5pp (el peor) manda sobre 1pp (el mejor): elegir el favorable seria
    # seleccionar por resultado, que es justo lo que el repo tiene prohibido
    assert out["spread_adverso_pp"] == pytest.approx(caro.vw_pp, rel=0.05)
    assert out["spread_adverso_pp"] > barato.vw_pp


def test_el_veredicto_mata_cuando_la_horquilla_supera_el_breakeven():
    caro = summarize_bounce(bounce_spread(_serie_con_horquilla(spread=0.06), min_pairs=10))
    out = verdict(caro, caro, edge_pp=2.0)
    assert out["breakeven_pp"] == pytest.approx(4.0)
    assert out["sobrevive"] is False
    assert out["edge_neto_pp"] < 0

    barato = summarize_bounce(bounce_spread(_serie_con_horquilla(spread=0.01), min_pairs=10))
    vivo = verdict(barato, barato, edge_pp=2.0)
    assert vivo["sobrevive"] is True
    assert vivo["edge_neto_pp"] == pytest.approx(1.5, abs=0.01)


def test_sin_estimadores_no_hay_veredicto():
    """Preferimos 'no decidible' a un numero inventado."""
    vacio = summarize_bounce(bounce_spread(pd.DataFrame(
        columns=["market_id", "side", "p", "usd", "ts", "li"]
    ), min_pairs=10))
    assert vacio.n_markets == 0
    assert verdict(vacio, vacio, edge_pp=2.0)["decidible"] is False


def test_correct_roll_devuelve_el_estimado_corregido_y_las_rho():
    serie = _serie_con_horquilla(spread=0.02, n=2000, sides="alterna")
    crudo = summarize_roll(roll_spread(serie, min_orders=10))
    corregido, rho1, rho2 = correct_roll(crudo, direction_autocorr(serie, min_orders=10))

    assert rho1 == pytest.approx(-1.0, abs=0.01)
    assert crudo.vw_pp == pytest.approx(4.0, rel=0.05)        # 2x de 2pp: sesgado
    assert corregido.vw_pp == pytest.approx(2.0, rel=0.05)    # corregido al real
    assert corregido.n_markets == crudo.n_markets             # no inventa muestra


def test_correct_roll_no_toca_nada_si_no_hay_autocorrelacion_medible():
    import pandas as pd

    crudo = summarize_roll(roll_spread(
        _serie_con_horquilla(spread=0.02, n=2000, sides="iid", seed=3), min_orders=10
    ))
    vacio = pd.DataFrame(columns=["market_id", "rho1", "rho2", "usd"])
    corregido, rho1, _ = correct_roll(crudo, vacio)
    assert corregido.vw_pp == crudo.vw_pp                      # sin rho, sin correccion
    assert np.isnan(rho1)


def test_muestra_chica_se_marca():
    pocos = _serie_con_horquilla(spread=0.02, n=60, market="m1")
    est = summarize_bounce(bounce_spread(pocos, min_pairs=10))
    assert est.n_markets == 1
    assert est.thin is True          # un solo mercado no concluye nada
