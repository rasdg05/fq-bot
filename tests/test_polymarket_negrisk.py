# -*- coding: utf-8 -*-
"""neg_risk: las dos trampas que fabrican un arbitraje que no existe.

Ambas se encontraron midiendo, no teorizando:

  (a) Patas faltantes  -> desviacion mediana FINGIDA de -26.00 pp
  (b) Asincronia       -> |dev| pasa de 1.00pp (cap 15min) a 1.90pp (cap 24h)

Y la aritmetica que mata la idea: el coste escala con N patas, la incoherencia
no. Si algun dia alguien "optimiza" quitando el requisito de patas completas o
el de simultaneidad, estos tests fallan en rojo.
"""
import numpy as np
import pandas as pd
import pytest

from tools.polymarket_negrisk import (
    HALF_SPREAD_PP,
    N_MIN_CONCLUYENTE,
    event_snapshot,
    fake_arb_of_incomplete,
    keep_complete,
    legs_alive_at,
    score,
    verdict,
)

T0 = pd.Timestamp("2026-03-01", tz="UTC")
TS0 = int(T0.timestamp())


def _legs(event="e1", n=3, created=None, ends=None):
    created = created or T0 - pd.Timedelta(days=10)
    ends = ends or T0 + pd.Timedelta(days=10)
    return pd.DataFrame({
        "id": [f"{event}-m{i}" for i in range(n)],
        "event_id": event,
        "neg_risk": 1,
        "created_at": created,
        "end_date": ends,
    })


def _trades(rows):
    """rows: (market_id, event_id, p, offset_min antes del instante objetivo)."""
    frame = pd.DataFrame(rows, columns=["market_id", "event_id", "p", "off_min"])
    frame["timestamp"] = TS0 - (frame["off_min"] * 60).astype(int)
    frame["log_index"] = range(len(frame))
    return frame.sort_values(["timestamp", "log_index"])


# --- Trampa (a): patas faltantes fabrican el arb ---------------------------


def test_una_pata_faltante_finge_un_arbitraje_enorme():
    """EL test. Ver 2 de 7 patas dio -26pp de desviacion fingida en el dato real."""
    legs = _legs(n=7)
    # solo 2 de las 7 patas tienen precio
    trades = _trades([("e1-m0", "e1", 0.30, 1), ("e1-m1", "e1", 0.20, 1)])
    snaps = event_snapshot(trades, legs, moment_ts=TS0, staleness_cap_min=15)

    assert snaps["n_obs"].iloc[0] == 2
    assert snaps["n_expected"].iloc[0] == 7
    # sin exigir completitud pareceria un arb del 50%
    assert (snaps["sum_p"].iloc[0] - 1.0) * 100 == pytest.approx(-50.0)
    # ...y con el filtro no queda nada
    assert len(keep_complete(snaps)) == 0


def test_el_arb_fingido_se_cuantifica_y_no_se_esconde():
    legs = _legs(n=5)
    trades = _trades([("e1-m0", "e1", 0.20, 1), ("e1-m1", "e1", 0.15, 1)])
    snaps = event_snapshot(trades, legs, moment_ts=TS0, staleness_cap_min=15)
    fake = fake_arb_of_incomplete(snaps)

    assert fake is not None
    assert fake["n"] == 1
    assert fake["dev_pp_median"] < -50          # arbitraje fabricado, y reportado
    assert fake["legs_seen"] == 2 and fake["legs_expected"] == 5


def test_evento_completo_si_pasa_el_filtro():
    legs = _legs(n=3)
    trades = _trades([
        ("e1-m0", "e1", 0.50, 1), ("e1-m1", "e1", 0.30, 1), ("e1-m2", "e1", 0.22, 1),
    ])
    complete = keep_complete(event_snapshot(trades, legs, moment_ts=TS0, staleness_cap_min=15))
    assert len(complete) == 1
    assert complete["sum_p"].iloc[0] == pytest.approx(1.02)


# --- El denominador: patas VIVAS, no las de hoy ---------------------------


def test_una_pata_que_aun_no_existia_no_cuenta_como_faltante():
    """Usar el conteo de patas de HOY sobre un instante pasado inventa faltantes."""
    viejas = _legs(event="e1", n=2)
    nueva = _legs(event="e1", n=1, created=T0 + pd.Timedelta(days=5))
    nueva["id"] = ["e1-tardia"]
    legs = pd.concat([viejas, nueva], ignore_index=True)

    vivas = legs_alive_at(legs, T0)
    assert vivas["e1"] == 2                      # la tardia no cuenta todavia

    trades = _trades([("e1-m0", "e1", 0.60, 1), ("e1-m1", "e1", 0.45, 1)])
    complete = keep_complete(event_snapshot(trades, legs, moment_ts=TS0, staleness_cap_min=15))
    assert len(complete) == 1                    # el evento SI esta completo


def test_una_pata_ya_cerrada_tampoco_cuenta():
    vivas = _legs(event="e1", n=2)
    cerrada = _legs(event="e1", n=1, ends=T0 - pd.Timedelta(days=1))
    cerrada["id"] = ["e1-cerrada"]
    legs = pd.concat([vivas, cerrada], ignore_index=True)
    assert legs_alive_at(legs, T0)["e1"] == 2


# --- Trampa (b): la simultaneidad -----------------------------------------


def test_el_cap_de_frescura_descarta_precios_viejos():
    legs = _legs(n=2)
    # una pata fresca, la otra de hace 3 horas
    trades = _trades([("e1-m0", "e1", 0.60, 1), ("e1-m1", "e1", 0.30, 180)])

    apretado = keep_complete(event_snapshot(trades, legs, moment_ts=TS0, staleness_cap_min=15))
    flojo = keep_complete(event_snapshot(trades, legs, moment_ts=TS0, staleness_cap_min=1440))

    assert len(apretado) == 0        # con 15 min la pata vieja no vale: se descarta
    assert len(flojo) == 1           # con 24h entra... y con ella el desfase
    assert flojo["stale_max"].iloc[0] == pytest.approx(180.0)


def test_solo_entran_trades_ANTERIORES_al_instante():
    legs = _legs(n=2)
    trades = _trades([
        ("e1-m0", "e1", 0.60, 1),
        ("e1-m1", "e1", 0.30, -60),      # 60 min DESPUES: seria mirar al futuro
    ])
    snaps = event_snapshot(trades, legs, moment_ts=TS0, staleness_cap_min=1440)
    assert snaps["n_obs"].iloc[0] == 1               # solo la anterior
    assert len(keep_complete(snaps)) == 0


# --- La aritmetica que mata la idea ---------------------------------------


def test_el_coste_escala_con_las_patas_y_la_incoherencia_no():
    """El argumento estructural del veredicto, fijado como test."""
    misma_dev = pd.DataFrame({
        "event_id": ["a", "b", "c"],
        "n_obs": [2, 6, 12],
        "n_expected": [2, 6, 12],
        "sum_p": [1.02, 1.02, 1.02],          # MISMA incoherencia: 2pp
        "stale_max": [1.0, 1.0, 1.0],
    })
    out = score(misma_dev)

    assert out["dev_pp"].tolist() == pytest.approx([2.0, 2.0, 2.0])
    assert out["cost_pp"].tolist() == pytest.approx(
        [2 * HALF_SPREAD_PP, 6 * HALF_SPREAD_PP, 12 * HALF_SPREAD_PP]
    )
    # con 2 patas casi empata; con 6 y 12 sangra, y cada vez mas
    assert out["net_pp"].iloc[0] > out["net_pp"].iloc[1] > out["net_pp"].iloc[2]
    assert out["net_pp"].iloc[1] < 0 and out["net_pp"].iloc[2] < 0


def test_veredicto_niega_cuando_el_neto_no_cubre_el_coste():
    n = 100
    flojo = pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "n_obs": 3, "n_expected": 3,
        "sum_p": 1.01,                         # 1pp de incoherencia
        "stale_max": 1.0,
    })
    out = verdict(score(flojo))
    assert out["decidible"] is True
    assert out["cost_pp_median"] == pytest.approx(3 * HALF_SPREAD_PP)
    assert out["net_pp_median"] < 0
    assert out["sobrevive"] is False


def test_veredicto_reconoce_un_arb_de_verdad_si_lo_hubiera():
    """Contraparte: si la incoherencia superara el coste, tiene que decirlo."""
    n = 100
    gordo = pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "n_obs": 2, "n_expected": 2,
        "sum_p": 1.15,                         # 15pp contra un coste de 1.9pp
        "stale_max": 1.0,
    })
    out = verdict(score(gordo))
    assert out["sobrevive"] is True
    assert out["frac_rentable"] == pytest.approx(1.0)


def test_muestra_chica_no_emite_veredicto():
    poco = pd.DataFrame({
        "event_id": [f"e{i}" for i in range(N_MIN_CONCLUYENTE - 1)],
        "n_obs": 3, "n_expected": 3, "sum_p": 1.30, "stale_max": 1.0,
    })
    out = verdict(score(poco))
    assert out["decidible"] is False           # ni a favor ni en contra
    assert str(N_MIN_CONCLUYENTE) in out["razon"]


def test_el_overround_se_reporta_con_signo():
    """Sum>1 sistematico es margen de casa. Importa su signo, no solo |dev|."""
    n = 100
    frame = pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "n_obs": 3, "n_expected": 3,
        "sum_p": np.concatenate([np.full(80, 1.008), np.full(20, 0.995)]),
        "stale_max": 1.0,
    })
    out = verdict(score(frame))
    assert out["frac_sum_mayor_1"] == pytest.approx(0.80)
    assert out["overround_pp"] > 0
