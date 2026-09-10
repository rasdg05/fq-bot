# -*- coding: utf-8 -*-
"""
HORIZONTE DE OUTCOME — regresion del "fantasma" del 10-jun-2026.

Que paso: check_outcome_against_candles recorria TODAS las velas posteriores a
la emision sin tope, y el timeout solo se evaluaba DESPUES del bucle. Una senal
que debia morir por timeout a las 8h seguia viva indefinidamente hasta tocar un
TP. Al volver el tracker de un downtime, replayo un mes de velas y cerro 23
senales de mayo en 763 ms: los 16 shorts a TP4 y los 7 longs a SL, sin un solo
tp1/tp2/tp3/timeout. El resultado era una funcion de la DIRECCION y de una
caida del -21% en SOL, no del sistema, y publicaba E[R]=+1.84R mientras el
motor con fees marcaba -0.51R.

Estos tests fijan las dos mitades del arreglo:
  1. el barrido se corta en el horizonte (nada se resuelve despues),
  2. minutes_open se mide contra la VELA de salida, no contra datetime.now().
"""
import importlib
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import entropy_cognition as ev


def _candles(start, n, *, low, high, tf_min=15):
    """n velas de tf_min minutos desde `start`, con el rango [low, high]."""
    return pd.DataFrame({
        "timestamp": [start + timedelta(minutes=tf_min * i) for i in range(n)],
        "open":  [(low + high) / 2] * n,
        "high":  [high] * n,
        "low":   [low] * n,
        "close": [(low + high) / 2] * n,
    })


def _signal(ts_emitted, direction="short", entry=100.0):
    """Short con SL a 101 y TP4 a 96 (riesgo 1.0, TP4 a 4R)."""
    if direction == "short":
        return {"ts_emitted": ts_emitted.isoformat(), "direction": "short",
                "entry_price": entry, "sl": entry + 1.0,
                "tp1": entry - 1.0, "tp2": entry - 2.0,
                "tp3": entry - 3.0, "tp4": entry - 4.0}
    return {"ts_emitted": ts_emitted.isoformat(), "direction": "long",
            "entry_price": entry, "sl": entry - 1.0,
            "tp1": entry + 1.0, "tp2": entry + 2.0,
            "tp3": entry + 3.0, "tp4": entry + 4.0}


def test_tp_fuera_del_horizonte_no_cuenta():
    """EL test del fantasma. Precio plano durante las 8h de vida y recien
    despues se desploma hasta TP4. El desenlace debe ser 'timeout', NUNCA tp4:
    a las 8h la senal ya estaba cerrada, ese movimiento no es del trade."""
    emitted = datetime.now(timezone.utc) - timedelta(days=20)
    # 32 velas de 15m = 8h exactas, plano (sin tocar nada).
    vivo = _candles(emitted + timedelta(minutes=15), 32, low=99.5, high=100.5)
    # Despues del horizonte: caida a 95 (por debajo del TP4 en 96).
    tarde = _candles(emitted + timedelta(hours=9), 40, low=95.0, high=96.0)
    df = pd.concat([vivo, tarde], ignore_index=True)

    out = ev.check_outcome_against_candles(_signal(emitted), df)

    assert out is not None
    assert out["outcome"] == "timeout", (
        "un TP tocado despues del horizonte se acredito como desenlace: "
        "es exactamente el bug del 10-jun-2026")
    assert out["pnl_r"] < 1.0


def test_tp_dentro_del_horizonte_si_cuenta():
    """Contraprueba: el mismo movimiento DENTRO de la ventana de vida si
    resuelve. El arreglo acota, no rompe el tracking."""
    emitted = datetime.now(timezone.utc) - timedelta(days=20)
    df = _candles(emitted + timedelta(minutes=15), 40, low=95.0, high=100.5)

    out = ev.check_outcome_against_candles(_signal(emitted), df)

    assert out is not None
    assert out["outcome"] == "tp4"
    assert out["pnl_r"] == pytest.approx(4.0)


def test_minutes_open_acotado_al_horizonte():
    """minutes_open sale de la vela de salida, no de datetime.now(). El bloque
    fantasma registraba vidas de hasta 43.611 minutos (30 dias) porque medía
    contra 'ahora' en el momento del reconcile."""
    emitted = datetime.now(timezone.utc) - timedelta(days=30)
    vivo = _candles(emitted + timedelta(minutes=15), 32, low=99.5, high=100.5)
    tarde = _candles(emitted + timedelta(days=10), 40, low=95.0, high=96.0)
    df = pd.concat([vivo, tarde], ignore_index=True)

    out = ev.check_outcome_against_candles(_signal(emitted), df)

    assert out["minutes_open"] <= ev.OUTCOME_TIMEOUT_HOURS * 60, (
        "vida registrada mayor que el horizonte: imposible bajo un tracker "
        "correcto")


def test_sl_dentro_del_horizonte_manda():
    """El SL sigue teniendo prioridad conservadora dentro de la ventana."""
    emitted = datetime.now(timezone.utc) - timedelta(days=2)
    df = _candles(emitted + timedelta(minutes=15), 10, low=99.0, high=101.5)

    out = ev.check_outcome_against_candles(_signal(emitted), df)

    assert out["outcome"] == "sl"
    assert out["pnl_r"] == pytest.approx(-1.0)


def test_senal_viva_no_se_decide():
    """Antes del horizonte y sin tocar nada: sigue abierta (None)."""
    emitted = datetime.now(timezone.utc) - timedelta(minutes=30)
    df = _candles(emitted + timedelta(minutes=15), 2, low=99.5, high=100.5)

    assert ev.check_outcome_against_candles(_signal(emitted), df) is None
