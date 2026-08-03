"""FQ_FORWARD_MEASURE (launcher): prende el set candidato (BCH/BNB/LINK) en modo
measure-first — motores paper ON, broadcast OFF, regime tags ON — respetando
overrides del usuario (setdefault) y SIN tocar FQ_KL_FILTER (taggea, no gatea)."""
import importlib
import os

import pytest

_KEYS = ["FQ_FORWARD_MEASURE", "FQ_REGIME_TAGS",
         "FQ_MOTOR_PAPER_BCH", "FQ_BCH_VIP_BROADCAST",
         "FQ_MOTOR_PAPER_BNB", "FQ_BNB_VIP_BROADCAST",
         "FQ_MOTOR_PAPER_LINK", "FQ_LINK_VIP_BROADCAST",
         "FQ_KL_FILTER"]


@pytest.fixture
def launcher():
    """Aisla os.environ a mano, sin monkeypatch.

    monkeypatch solo deshace lo que MONKEYPATCH escribio, y aqui la que escribe
    es la funcion bajo prueba: `_apply_forward_measure()` hace
    `os.environ["FQ_MOTOR_PAPER_LINK"] = "1"` directo. Con `delenv(raising=False)`
    sobre una clave ausente no se registra nada que restaurar, asi que esas
    variables quedaban PEGADAS para el resto de la sesion de pytest y
    contaminaban a cualquier test posterior que releyera el entorno.
    """
    previo = {k: os.environ.get(k) for k in _KEYS}
    for k in _KEYS:
        os.environ.pop(k, None)
    import launcher as L
    yield importlib.reload(L)
    for k, v in previo.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_sin_flag_no_hace_nada(launcher, monkeypatch):
    launcher._apply_forward_measure()
    import os
    assert "FQ_MOTOR_PAPER_BCH" not in os.environ


def test_con_flag_prende_el_set_candidato(launcher, monkeypatch):
    import os
    monkeypatch.setenv("FQ_FORWARD_MEASURE", "1")
    launcher._apply_forward_measure()
    assert os.environ["FQ_MOTOR_PAPER_BCH"] == "1"
    assert os.environ["FQ_MOTOR_PAPER_BNB"] == "1"
    assert os.environ["FQ_MOTOR_PAPER_LINK"] == "1"
    assert os.environ["FQ_BCH_VIP_BROADCAST"] == "0"
    assert os.environ["FQ_BNB_VIP_BROADCAST"] == "0"
    assert os.environ["FQ_LINK_VIP_BROADCAST"] == "0"
    assert os.environ["FQ_REGIME_TAGS"] == "1"


def test_override_del_usuario_gana(launcher, monkeypatch):
    import os
    monkeypatch.setenv("FQ_FORWARD_MEASURE", "1")
    monkeypatch.setenv("FQ_BNB_VIP_BROADCAST", "1")   # el usuario SÍ quiere difundir BNB
    launcher._apply_forward_measure()
    assert os.environ["FQ_BNB_VIP_BROADCAST"] == "1"  # setdefault: su valor gana


def test_no_toca_el_gate_kl(launcher, monkeypatch):
    import os
    monkeypatch.setenv("FQ_FORWARD_MEASURE", "1")
    launcher._apply_forward_measure()
    # measure-first = taggear, no gatear. El edge de BCH vive en irrev-ALTO.
    assert "FQ_KL_FILTER" not in os.environ
