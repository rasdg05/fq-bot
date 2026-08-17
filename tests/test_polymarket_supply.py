# -*- coding: utf-8 -*-
"""Sondeo de oferta de Polymarket: las cuatro lecciones del repo, como tests.

Cada test de aquí fija una regresión que YA costó dinero o credibilidad una vez:

  1. El agregado no sale sin desglose por régimen  -> el fantasma de mayo (E9)
  2. n<30 se marca, no se diluye en el promedio    -> CLAUDE.md, regla de la casa
  3. Nada se excluye en silencio                   -> las 23 filas de julio
  4. Una columna constante se delata               -> `vp_basis` (BRIEF E1)

Sin red y sin parquet: frames sintéticos.
"""
import pandas as pd
import pytest

from tools.polymarket_supply import (
    N_MIN_CONCLUYENTE,
    capacity,
    capacity_by_year,
    capturable_universe,
    constant_columns,
    format_report,
    hygiene_report,
)

PARAMS = dict(edge_pp=2.0, avg_price=0.5, participation=0.02)


def _frame(rows):
    """rows: (question, volume, created_at, end_date, closed)."""
    frame = pd.DataFrame(
        rows, columns=["question", "volume", "created_at", "end_date", "closed"]
    )
    for col in ("created_at", "end_date"):
        frame[col] = pd.to_datetime(frame[col], utc=True)
    return frame


def _market(i, *, year=2026, vol=1e6, horizon_days=7.0, closed=1):
    start = pd.Timestamp(f"{year}-01-01", tz="UTC") + pd.Timedelta(days=i)
    return (
        f"pregunta {year}-{i}",
        vol,
        start,
        start + pd.Timedelta(days=horizon_days),
        closed,
    )


# --- 1. El agregado no sale sin desglose (BRIEF E9) -------------------------


def test_reporte_exige_desglose_por_anio():
    """Imprimir un agregado sin su desglose debe ser IMPOSIBLE, no desaconsejado."""
    hygiene = hygiene_report(_frame([_market(0)]))
    with pytest.raises(ValueError, match="desglose"):
        format_report(
            hygiene, {}, vol_min=1e5, horizon_max_days=7, **PARAMS
        )


def test_desglose_separa_regimenes_que_el_agregado_esconderia():
    """2024 (elección, horizonte largo) y 2026 (por horas) no son el mismo mercado."""
    rows = [_market(i, year=2024, horizon_days=180.0) for i in range(40)]
    rows += [_market(i, year=2026, horizon_days=2.0) for i in range(40)]
    by_year = capacity_by_year(
        _frame(rows), vol_min=1e5, horizon_max_days=365, **PARAMS
    )
    assert set(by_year) == {2024, 2026}
    # el horizonte ponderado los separa por un orden de magnitud: promediarlos
    # inventaria un mercado que nunca existio
    assert by_year[2024].wavg_horizon_days > 100
    assert by_year[2026].wavg_horizon_days < 5
    assert by_year[2026].annual_return > by_year[2024].annual_return * 10


# --- 2. n<30 se marca, no se diluye ----------------------------------------


def test_muestra_chica_se_marca():
    chica = capacity_by_year(
        _frame([_market(i) for i in range(N_MIN_CONCLUYENTE - 1)]),
        vol_min=1e5,
        horizon_max_days=7,
        **PARAMS,
    )
    assert chica[2026].thin is True

    gorda = capacity_by_year(
        _frame([_market(i) for i in range(N_MIN_CONCLUYENTE + 1)]),
        vol_min=1e5,
        horizon_max_days=7,
        **PARAMS,
    )
    assert gorda[2026].thin is False


def test_la_marca_llega_al_reporte_impreso():
    """Marcar en el dataclass y no imprimirlo seria un hallazgo sin invariante."""
    frame = _frame([_market(i) for i in range(3)])
    texto = format_report(
        hygiene_report(frame),
        capacity_by_year(frame, vol_min=1e5, horizon_max_days=7, **PARAMS),
        vol_min=1e5,
        horizon_max_days=7,
        **PARAMS,
    )
    assert "NO CONCLUYE" in texto


# --- 3. Nada se excluye en silencio ----------------------------------------


def test_horizonte_roto_se_excluye_pero_se_cuenta():
    """Las 23 filas del fantasma se excluyen por invariante, NO se borran."""
    sano = [_market(i) for i in range(5)]
    roto = [
        (
            "pregunta rota",
            1e6,
            pd.Timestamp("2026-03-01", tz="UTC"),
            pd.Timestamp("2026-02-01", tz="UTC"),  # end_date ANTES de created_at
            1,
        )
    ]
    frame = _frame(sano + roto)

    hygiene = hygiene_report(frame)
    universo = capturable_universe(frame, vol_min=0, horizon_max_days=1e9)

    assert hygiene.n_horizon_nonpositive == 1        # se cuenta
    assert len(universo) == len(sano)                # se excluye
    assert hygiene.n_usable == len(universo)         # y las dos cuentas cuadran


def test_el_reporte_imprime_lo_excluido_encima_de_los_numeros():
    frame = _frame(
        [_market(i) for i in range(3)]
        + [
            (
                "rota",
                1e6,
                pd.Timestamp("2026-03-01", tz="UTC"),
                pd.Timestamp("2026-02-01", tz="UTC"),
                1,
            )
        ]
    )
    texto = format_report(
        hygiene_report(frame),
        capacity_by_year(frame, vol_min=1e5, horizon_max_days=7, **PARAMS),
        vol_min=1e5,
        horizon_max_days=7,
        **PARAMS,
    )
    assert "EXCLUIDAS" in texto
    assert texto.index("HIGIENE") < texto.index("CAPACIDAD")  # antes de los numeros


# --- 4. Una columna constante se delata (leccion `vp_basis`) ---------------


def test_columna_constante_se_delata():
    frame = _frame([_market(i, vol=1e6 * (i + 1), closed=1) for i in range(5)])
    assert "closed" in constant_columns(frame)       # todas cerradas: no es feature
    assert "volume" not in constant_columns(frame)   # varia: si es feature


def test_columna_constante_aparece_en_el_reporte():
    frame = _frame([_market(i) for i in range(40)])
    texto = format_report(
        hygiene_report(frame),
        capacity_by_year(frame, vol_min=1e5, horizon_max_days=7, **PARAMS),
        vol_min=1e5,
        horizon_max_days=7,
        **PARAMS,
    )
    assert "CONSTANTES" in texto
    assert "closed" in texto


# --- La aritmetica que sostiene el veredicto -------------------------------


def test_retorno_anual_no_depende_del_tamano_de_la_apuesta():
    """La participacion fija la ESCALA, no el rendimiento. Si esto se rompe,
    el veredicto de capacidad estaria midiendo otra cosa."""
    universo = capturable_universe(
        _frame([_market(i) for i in range(40)]), vol_min=1e5, horizon_max_days=7
    )
    chico = capacity(universo, participation=0.001, span_days=365, edge_pp=2.0, avg_price=0.5)
    grande = capacity(universo, participation=0.100, span_days=365, edge_pp=2.0, avg_price=0.5)

    assert chico.annual_return == pytest.approx(grande.annual_return)
    assert grande.peak_capital_usd == pytest.approx(chico.peak_capital_usd * 100)


def test_horizonte_ponderado_manda_sobre_el_mediano():
    """Un mercado gordo y lento pesa mas que cien chicos y rapidos: si usaramos
    la mediana, el retorno anual saldria inflado ~20x."""
    rows = [_market(i, vol=1e3, horizon_days=1.0) for i in range(100)]
    rows += [_market(200, vol=1e9, horizon_days=200.0)]
    universo = capturable_universe(_frame(rows), vol_min=0, horizon_max_days=365)
    cap = capacity(universo, span_days=365, **PARAMS)

    assert universo["horizon_days"].median() == pytest.approx(1.0)
    assert cap.wavg_horizon_days > 190          # el gordo manda


def test_la_horquilla_se_descuenta_y_puede_matar_el_retorno():
    """El pecado de agosto fue publicar bruto. Aqui el neto es obligatorio.

    Aguantando a resolucion se cruza una sola vez: coste = spread/2. Con edge
    2pp, un spread de 4pp deja el retorno EXACTAMENTE en cero, y por encima
    en negativo. Si esto se rompe, el tool vuelve a prometer +450% de humo.
    """
    universo = capturable_universe(
        _frame([_market(i) for i in range(40)]), vol_min=1e5, horizon_max_days=7
    )
    base = dict(participation=0.02, span_days=365, edge_pp=2.0, avg_price=0.5)

    bruto = capacity(universo, spread_pp=0.0, **base)
    justo = capacity(universo, spread_pp=bruto.breakeven_spread_pp, **base)
    caro = capacity(universo, spread_pp=bruto.breakeven_spread_pp + 1.0, **base)

    assert bruto.breakeven_spread_pp == pytest.approx(4.0)   # 2 * edge
    assert justo.annual_return == pytest.approx(0.0)          # justo lo mata
    assert caro.annual_return < 0                             # y por encima, sangra
    assert bruto.annual_return > 0


def test_el_reporte_avisa_cuando_el_numero_es_bruto():
    """Un retorno de tres cifras sin la palabra BRUTO al lado es una promesa."""
    frame = _frame([_market(i) for i in range(40)])
    texto = format_report(
        hygiene_report(frame),
        capacity_by_year(frame, vol_min=1e5, horizon_max_days=7, spread_pp=0.0, **PARAMS),
        vol_min=1e5,
        horizon_max_days=7,
        spread_pp=0.0,
        **PARAMS,
    )
    assert "BRUTO" in texto
    assert "No es un resultado" in texto


def test_universo_vacio_no_revienta():
    universo = capturable_universe(
        _frame([_market(0, vol=1.0)]), vol_min=1e9, horizon_max_days=7
    )
    cap = capacity(universo, span_days=365, **PARAMS)
    assert cap.n == 0 and cap.volume_usd == 0.0
