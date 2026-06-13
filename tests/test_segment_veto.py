# -*- coding: utf-8 -*-
"""Tests del VETO DE SESION (segment_veto, F2.6 §6.8).

Todos los timestamps son HISTORICOS y explicitos (la leccion §6.7: jamas el
reloj de pared). Cubren: default OFF, los tres predicados (killzone / bloque
UTC / dia), la derivacion de killzone desde el ts de la vela, y — clave — la
PARIDAD entre el path escalar (vivo) y el vectorizado (research/offline): el
mismo predicado, cero divergencia backtest/live.
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

import segment_veto as sv

UTC = timezone.utc

# --- timestamps historicos de referencia (UTC; CDMX = UTC-6) ---
# 2024-01-15 es LUNES. 07:30 UTC = 01:30 CDMX -> london_open_kz (1.0-5.0) gana
# (eu_pre_open 0.5-2.0 mismo 'order', pierde por orden de lista; silver_bullet_lo
# arranca a las 2.0).
T_LONDON = datetime(2024, 1, 15, 7, 30, tzinfo=UTC)   # lunes, london_open_kz
# 2024-01-16 MARTES. 15:30 UTC = 09:30 CDMX -> silver_bullet_ny_am (9.0-10.0).
T_NY = datetime(2024, 1, 16, 15, 30, tzinfo=UTC)      # martes, silver_bullet_ny_am
T_SAT = datetime(2024, 1, 20, 12, 0, tzinfo=UTC)      # sabado


def test_default_off_es_noop():
    veto = sv.parse()  # todo vacio == lo que da from_env sin envs
    assert not veto.active
    assert veto.describe() == "(sin veto)"
    assert veto.reason(killzone="london_open_kz", ts_utc=T_LONDON) is None
    assert veto.vetoes(killzone="london_open_kz", ts_utc=T_LONDON) is False


def test_from_env_default_off(monkeypatch):
    for k in (sv.ENV_KILLZONES, sv.ENV_UTC_BLOCKS, sv.ENV_WEEKDAYS):
        monkeypatch.delenv(k, raising=False)
    assert not sv.from_env().active
    # env vacio explicito tambien es OFF
    assert not sv.from_env({sv.ENV_KILLZONES: "", sv.ENV_UTC_BLOCKS: ""}).active


def test_from_env_killzones(monkeypatch):
    monkeypatch.setenv(sv.ENV_KILLZONES, "london_open_kz")
    monkeypatch.delenv(sv.ENV_UTC_BLOCKS, raising=False)
    monkeypatch.delenv(sv.ENV_WEEKDAYS, raising=False)
    veto = sv.from_env()
    assert veto.active and veto.killzones == frozenset({"london_open_kz"})


def test_killzone_explicito_preferido():
    veto = sv.parse(killzones="london_open_kz")
    assert veto.active
    # se pasa field.killzone ya computado -> usa ESE (paridad con el motor)
    assert veto.reason(killzone="london_open_kz", ts_utc=T_NY) == "killzone=london_open_kz"
    assert veto.reason(killzone="silver_bullet_ny_am", ts_utc=T_LONDON) is None
    # killzone None/NaN no veta
    assert veto.reason(killzone=None, ts_utc=None) is None


def test_killzone_derivada_del_ts():
    """Sin field.killzone, se deriva del TS de la vela (fallback explicito)."""
    veto = sv.parse(killzones="london_open_kz")
    assert veto.reason(killzone=None, ts_utc=T_LONDON) == "killzone=london_open_kz"
    assert veto.reason(killzone=None, ts_utc=T_NY) is None


def test_killzone_of_historico():
    assert sv.killzone_of(T_LONDON) == "london_open_kz"
    assert sv.killzone_of(T_NY) == "silver_bullet_ny_am"
    assert sv.killzone_of(None) is None


def test_utc_blocks():
    veto = sv.parse(utc_blocks="00-04,04-08")
    assert veto.utc_blocks == frozenset({0, 4})
    t2 = datetime(2024, 1, 15, 2, 0, tzinfo=UTC)    # bloque 00-04
    t6 = datetime(2024, 1, 15, 6, 0, tzinfo=UTC)    # bloque 04-08
    t10 = datetime(2024, 1, 15, 10, 0, tzinfo=UTC)  # bloque 08-12 (no vetado)
    assert veto.reason(ts_utc=t2) == "utc_block=00-04"
    assert veto.reason(ts_utc=t6) == "utc_block=04-08"
    assert veto.reason(ts_utc=t10) is None
    # sin ts no puede juzgar bloque -> no veta (fallback graccioso del vivo)
    assert veto.reason(ts_utc=None) is None


def test_weekdays():
    veto = sv.parse(weekdays="lun,sab")
    assert veto.weekdays == frozenset({0, 5})
    assert veto.reason(ts_utc=T_LONDON) == "dia=lun"   # lunes
    assert veto.reason(ts_utc=T_SAT) == "dia=sab"      # sabado
    assert veto.reason(ts_utc=T_NY) is None            # martes


def test_weekday_invalido_explota():
    with pytest.raises(ValueError):
        sv.parse(weekdays="lunes")


def test_naive_se_asume_utc():
    veto = sv.parse(utc_blocks="00-04")
    aware = datetime(2024, 1, 15, 2, 0, tzinfo=UTC)
    naive = datetime(2024, 1, 15, 2, 0)  # sin tz -> debe tratarse igual (UTC)
    assert veto.reason(ts_utc=aware) == veto.reason(ts_utc=naive) == "utc_block=00-04"


def test_acepta_pandas_timestamp_y_str():
    veto = sv.parse(weekdays="sab")
    assert veto.reason(ts_utc=pd.Timestamp("2024-01-20 12:00:00")) == "dia=sab"
    assert veto.reason(ts_utc="2024-01-20T12:00:00") == "dia=sab"


def test_or_combina_predicados():
    veto = sv.parse(killzones="london_open_kz", weekdays="sab")
    # cae por killzone aunque el dia no este vetado (martes)
    assert veto.vetoes(killzone="london_open_kz", ts_utc=T_NY)
    # cae por dia (sabado) aunque la killzone no este vetada
    assert veto.vetoes(killzone="ny_am_kz", ts_utc=T_SAT)
    # no cae: martes + killzone no vetada
    assert not veto.vetoes(killzone="ny_am_kz", ts_utc=T_NY)


# ---------------------------------------------------------------------------
# PARIDAD vectorizado (mask, research/offline) <-> escalar (reason, vivo)
# ---------------------------------------------------------------------------
def _cube_sample():
    """Mini-cubo con las MISMAS columnas que tp_cube_<sym>.parquet usa el
    regrade/segmentos: field_killzone + entry_ts (UTC)."""
    rows = [
        ("london_open_kz",       T_LONDON),
        ("silver_bullet_ny_am",  T_NY),
        ("ny_am_kz",             T_SAT),
        ("asia_kz",              datetime(2024, 1, 17, 2, 0, tzinfo=UTC)),  # mie, bloque 00-04
        ("london_open_kz",       datetime(2024, 1, 18, 16, 0, tzinfo=UTC)),  # jue
    ]
    return pd.DataFrame({
        "field_killzone": [r[0] for r in rows],
        "entry_ts": [pd.Timestamp(r[1]) for r in rows],
        "pnl_r": [0.1, -0.2, 0.3, -0.1, 0.4],
    })


@pytest.mark.parametrize("cfg", [
    dict(killzones="london_open_kz"),
    dict(utc_blocks="00-04,04-08"),
    dict(weekdays="lun,sab"),
    dict(killzones="london_open_kz", weekdays="sab"),
    dict(killzones="london_open_kz", utc_blocks="00-04", weekdays="jue"),
])
def test_mask_igual_a_reason_fila_a_fila(cfg):
    """La mascara vectorizada (research/offline) debe coincidir EXACTAMENTE con
    el predicado escalar (vivo) fila a fila. Esta es la garantia de cero
    divergencia entre offline, replay integrado y vivo."""
    veto = sv.parse(**cfg)
    df = _cube_sample()
    vec = veto.mask(df)
    esc = np.array([
        veto.vetoes(killzone=row.field_killzone, ts_utc=row.entry_ts)
        for row in df.itertuples()
    ])
    assert list(vec) == list(esc)


def test_mask_off_no_filtra():
    df = _cube_sample()
    assert sv.parse().mask(df).sum() == 0  # OFF -> nada vetado
    assert sv.parse().mask(df.iloc[0:0]).shape == (0,)  # df vacio -> ok


def test_mask_no_muta_el_df():
    df = _cube_sample()
    before = df.copy()
    sv.parse(killzones="london_open_kz").mask(df)
    pd.testing.assert_frame_equal(df, before)


def test_mask_killzone_veta_filas_correctas():
    df = _cube_sample()
    m = sv.parse(killzones="london_open_kz").mask(df)
    # filas 0 y 4 son london_open_kz
    assert list(np.where(m)[0]) == [0, 4]
