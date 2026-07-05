"""GATE-C: sizing por convicción en LONGS (barbell 4:2:1, validado CPCV/PBO 2026-07-05).
Prueba la función pura `conviction_weight` + la extracción `_report_p_master`. El
default del motor es OFF (FQ_CONVICTION_LONGS no seteado) -> byte-idéntico; aquí se
prueba la MECÁNICA del peso (independiente del flag)."""
import numpy as np
import pytest

import motor_paper as M


# hist con distribución clara: 1..100 -> pctl33≈33.7, pctl67≈67.3
HIST = [float(x) for x in range(1, 101)]


def test_short_siempre_neutral():
    # p_master no separa en shorts (GATE-B) -> peso 1.0 sin importar la convicción
    assert M.conviction_weight(99.0, HIST, -1) == 1.0
    assert M.conviction_weight(1.0, HIST, -1) == 1.0
    assert M.conviction_weight(50.0, HIST, 0) == 1.0   # dir 0 -> neutral


def test_long_tercil_alto_recibe_hi():
    # p_master por encima del pctl67 -> peso HI (1.0 por default = riesgo pleno)
    assert M.conviction_weight(90.0, HIST, 1) == pytest.approx(M._CONV_HI)


def test_long_tercil_medio_recibe_mid():
    assert M.conviction_weight(50.0, HIST, 1) == pytest.approx(M._CONV_MID)


def test_long_tercil_bajo_recibe_lo():
    # p_master por debajo del pctl33 -> peso LO (0.25 = riesgo reducido)
    assert M.conviction_weight(5.0, HIST, 1) == pytest.approx(M._CONV_LO)


def test_ratios_barbell_validados_4_2_1():
    # los defaults deben mantener los ratios que pasaron el gate: hi:mid:lo = 4:2:1
    hi, mid, lo = M._CONV_HI, M._CONV_MID, M._CONV_LO
    assert hi / mid == pytest.approx(2.0)
    assert mid / lo == pytest.approx(2.0)
    # y nunca por encima de 1.0 (barbell hacia abajo -> respeta el cap del gobernador)
    assert max(hi, mid, lo) <= 1.0


def test_historia_insuficiente_es_neutral():
    # sin terciles confiables aún -> 1.0 (no arriesga de más al arrancar en vivo)
    corta = [2.0, 3.0, 2.5]
    assert M.conviction_weight(99.0, corta, 1) == 1.0


def test_pmaster_invalido_es_neutral():
    assert M.conviction_weight(None, HIST, 1) == 1.0
    assert M.conviction_weight(float("nan"), HIST, 1) == 1.0
    assert M.conviction_weight("basura", HIST, 1) == 1.0


def test_hist_con_nans_se_limpia():
    sucio = HIST + [None, float("nan")]
    # sigue funcionando (limpia los inválidos antes del percentil)
    assert M.conviction_weight(90.0, sucio, 1) == pytest.approx(M._CONV_HI)


def test_pesos_overridables():
    # hi/mid/lo se pueden pasar explícitos (para experimentar esquemas)
    assert M.conviction_weight(90.0, HIST, 1, hi=2.0) == pytest.approx(2.0)
    assert M.conviction_weight(50.0, HIST, 1, mid=0.7) == pytest.approx(0.7)


def test_report_p_master_extrae():
    rep = {"p_master_data": {"p_master": 3.14}}
    assert M._report_p_master(rep) == pytest.approx(3.14)


def test_report_p_master_defensivo():
    assert M._report_p_master(None) is None
    assert M._report_p_master({}) is None
    assert M._report_p_master({"p_master_data": {}}) is None
    assert M._report_p_master({"p_master_data": {"p_master": None}}) is None
    assert M._report_p_master({"p_master_data": {"p_master": "x"}}) is None


def test_min_hist_configurable():
    # con min_hist bajo, una historia corta ya activa el peso
    corta = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert M.conviction_weight(5.0, corta, 1, min_hist=3) == pytest.approx(M._CONV_HI)
    assert M.conviction_weight(1.0, corta, 1, min_hist=3) == pytest.approx(M._CONV_LO)
