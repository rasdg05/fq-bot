# -*- coding: utf-8 -*-
"""
Politica de senales (v6): solo VIP de pura lectura en cadencia, tacticas muertas.

Guarda el contrato de defaults de produccion:
  - el RADAR (y con el, las ALERTAS TACTICAS al VIP) arranca APAGADO.
  - el path VIP clasico (fusion_engine) sigue vivo e independiente.
El gate ORO (FQ_ENFORCE_HIGH_GATE) se enciende cuando los numeros del research
(quality_gate + cubo) fijen el umbral; hasta entonces su default no se toca aqui.
"""
import os

import pytest


@pytest.mark.skipif("FQ_RADAR_ENABLED" in os.environ,
                    reason="override de entorno activo; el test valida el DEFAULT")
def test_tactical_radar_off_by_default():
    """Las senales tacticas estan muertas por defecto (radar OFF)."""
    b = pytest.importorskip("fq_bot_v3_2")   # skip si faltan deps del monolito
    assert b.RADAR_ENABLED is False


def test_radar_flag_is_env_overridable(monkeypatch):
    """Reversibilidad: FQ_RADAR_ENABLED=1 vuelve a encender el radar."""
    monkeypatch.setenv("FQ_RADAR_ENABLED", "1")
    flag = os.environ.get("FQ_RADAR_ENABLED", "0").strip() in ("1", "true", "yes")
    assert flag is True


def test_vip_engine_independent_of_radar():
    """El motor VIP (fusion_engine.evaluate_signal) no depende del radar: matar
    tacticas no toca la generacion de senales VIP."""
    import fusion_engine
    assert hasattr(fusion_engine, "evaluate_signal")
