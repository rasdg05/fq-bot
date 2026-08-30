# -*- coding: utf-8 -*-
"""
Tests para FQ v5.2 — ALERTA TACTICA + volume gate.

Cubre:
  - volume_quality: modulador suave, veto en horas muertas, label.
  - killzones_pd: nuevas KZ (asia_open, eu_pre_open) y penalty (ny_close_hour).
  - vip_format.build_tactical_alert: render con TPs cortos.
  - fq_bot_v3_2._compute_tactical_tps: RR 1.0/1.5/2.2 para long y short.
  - fq_bot_v3_2._should_promote_tactical_to_vip: gating combinado.
"""
import os
import sys
from datetime import datetime

import pytest

# Shim para entornos sin pandas-ta instalado (pandas-ta-classic provee la API)
try:
    import pandas_ta  # noqa: F401
except ImportError:
    try:
        import pandas_ta_classic as _ta
        sys.modules["pandas_ta"] = _ta
    except ImportError:
        pass


# ===========================================
# 1. VOLUME QUALITY
# ===========================================
def test_volume_modulator_anchors():
    import volume_quality as vq
    assert abs(vq.volume_modulator(1.0) - 1.0) < 1e-6
    assert abs(vq.volume_modulator(vq.VOL_SCORE_LOW) - vq.VOL_MOD_MIN) < 1e-6
    assert abs(vq.volume_modulator(vq.VOL_SCORE_HIGH) - vq.VOL_MOD_MAX) < 1e-6


def test_volume_modulator_monotonic():
    import volume_quality as vq
    samples = [vq.volume_modulator(s) for s in (0.0, 0.5, 0.8, 1.0, 1.1, 1.3, 2.0)]
    assert samples == sorted(samples)


def test_volume_veto_only_with_AND():
    import volume_quality as vq
    from datetime import datetime, timezone, timedelta
    CDMX = timezone(timedelta(hours=-6))

    late_ny = datetime(2026, 6, 1, 15, 30, tzinfo=CDMX)
    morning = datetime(2026, 6, 1, 9, 0, tzinfo=CDMX)
    fri_late = datetime(2026, 6, 5, 14, 30, tzinfo=CDMX)

    # vol bajo + dead -> veto
    v, _ = vq.volume_veto(0.4, now_cdmx=late_ny)
    assert v is True
    # vol bajo + active -> no veto
    v, _ = vq.volume_veto(0.4, now_cdmx=morning)
    assert v is False
    # vol alto + dead -> no veto
    v, _ = vq.volume_veto(1.2, now_cdmx=late_ny)
    assert v is False
    # viernes tarde
    v, _ = vq.volume_veto(0.4, now_cdmx=fri_late)
    assert v is True


def test_dead_window_2pm_manipulation():
    """La hora 2PM CDMX (14:00-15:00) es franja muerta diaria por manipulacion.

    Reproduce el caso real: ALERTA TACTICA SHORT @14:50 CDMX (lunes) que termino
    en SL. Antes 14:50 caia justo antes de la franja muerta (15:00-16:00) y no se
    filtraba; ahora is_dead_window la marca y dead_window_label la etiqueta.
    """
    import volume_quality as vq
    from datetime import datetime, timezone, timedelta
    CDMX = timezone(timedelta(hours=-6))

    manip_2pm = datetime(2026, 6, 1, 14, 50, tzinfo=CDMX)  # lunes 14:50 (caso real)
    just_after = datetime(2026, 6, 1, 13, 30, tzinfo=CDMX)  # 1:30 PM aun activo
    boundary = datetime(2026, 6, 1, 15, 0, tzinfo=CDMX)     # 15:00 -> ya NY close

    assert vq.is_dead_window(manip_2pm) is True
    assert vq.dead_window_label(manip_2pm) == "manipulacion 2PM"
    assert vq.is_dead_window(just_after) is False, "13:30 CDMX sigue activo"
    assert vq.is_dead_window(boundary) is True, "15:00 cae en ultima hora NY"
    # vol bajo en 2PM -> veto (gate AND se cumple)
    v, _ = vq.volume_veto(0.4, now_cdmx=manip_2pm)
    assert v is True


def test_volume_quality_labels():
    import volume_quality as vq
    assert vq.volume_quality_label(0.5) == "Muy bajo"
    assert vq.volume_quality_label(0.7) == "Bajo"
    assert vq.volume_quality_label(1.0) == "Normal"
    assert vq.volume_quality_label(1.4) == "Alto"
    assert vq.volume_quality_label(None) == "—"


def test_volume_score_forming_candle_is_misleading():
    """Reproduce el bug del RADAR: si se mide el volumen incluyendo la vela
    RECIEN ABIERTA (en formacion), vol_last es parcial y el score sale
    artificialmente bajo (el caso real vol_score=0.11 en pleno horario de Asia).
    Medir sobre la ultima vela CERRADA (df.iloc[:-1]) recupera el score real.
    """
    import pandas as pd
    import volume_quality as vq

    # 21 velas CERRADAS con volumen normal (=100) + 1 vela en formacion (=11,
    # ~11% del promedio porque acaba de abrir). Misma forma OHLC en todas.
    n_closed = 21
    rows = []
    for _ in range(n_closed):
        rows.append({"open": 10.0, "high": 11.0, "low": 10.0, "close": 10.5,
                     "volume": 100.0})
    rows.append({"open": 10.0, "high": 11.0, "low": 10.0, "close": 10.5,
                 "volume": 11.0})  # vela recien abierta
    df = pd.DataFrame(rows)

    # Incluyendo la vela en formacion -> score enganoso ~0.11 (< gate 0.85)
    vs_forming = vq.volume_score(df)
    assert abs(vs_forming["score"] - 0.11) < 1e-6

    # Sobre la ultima vela CERRADA (lo que hace el fix) -> score real ~1.0
    vs_closed = vq.volume_score(df.iloc[:-1])
    assert abs(vs_closed["score"] - 1.0) < 1e-6


def test_radar_check_uses_closed_candle_for_volume():
    """Guardia de regresion: radar_check debe medir el volumen sobre la vela
    cerrada (df.iloc[:-1]), no sobre la vela en formacion. radar_check corre al
    detectar vela nueva, asi que df.iloc[-1] esta recien abierta."""
    import inspect
    import fq_bot_v3_2 as b
    src = inspect.getsource(b.radar_check)
    assert "df.iloc[:-1]" in src, \
        "radar_check debe calcular vol_score sobre la vela cerrada, no la en formacion"


# ===========================================
# 2. KILLZONES (mapa v5.2)
# ===========================================
def test_killzones_new_asia_open():
    import killzones_pd as k
    from datetime import datetime
    CDMX = k.CDMX_TZ
    kz = k.current_killzone(datetime(2026, 6, 1, 17, 30, tzinfo=CDMX))
    assert kz["name"] == "asia_open"
    assert kz["w_kz"] == 1.05
    assert kz["priority"] == "alta-volumen"


def test_killzones_ny_close_penalty():
    import killzones_pd as k
    from datetime import datetime
    CDMX = k.CDMX_TZ
    kz = k.current_killzone(datetime(2026, 6, 1, 15, 30, tzinfo=CDMX))
    assert kz["name"] == "ny_close_hour"
    assert kz["w_kz"] == 0.45
    assert kz["priority"] == "penalty"


def test_killzones_ny_pm_acortada_no_solapa_penalty():
    import killzones_pd as k
    from datetime import datetime
    CDMX = k.CDMX_TZ
    # 14:30 todavia es ny_pm_kz (1.10)
    kz = k.current_killzone(datetime(2026, 6, 1, 14, 30, tzinfo=CDMX))
    assert kz["name"] == "ny_pm_kz"
    # 15:00 ya es penalty
    kz2 = k.current_killzone(datetime(2026, 6, 1, 15, 0, tzinfo=CDMX))
    assert kz2["name"] == "ny_close_hour"


def test_weekend_status_near_close_field():
    import killzones_pd as k
    ws = k.weekend_status()
    assert "near_close" in ws
    assert isinstance(ws["near_close"], bool)


# ===========================================
# 3. TACTICAL ALERT FORMAT
# ===========================================
def test_build_tactical_alert_execute_short():
    import vip_format as vf
    plan = {
        "verdict": "EJECUTAR_AHORA",
        "direction": "short",
        "headline": "EJECUTA SHORT a mercado ~$80.91",
        "market": {"entry": 80.91, "p_sl": 0.28, "ev": 1.30},
        "primary_zone": None,
        "invalidation": 81.36,
    }
    tps = [
        {"price": 80.46, "rr": 1.00, "weight_pct": 40},
        {"price": 80.23, "rr": 1.50, "weight_pct": 35},
        {"price": 79.92, "rr": 2.20, "weight_pct": 25},
    ]
    msg = vf.build_tactical_alert(plan, tps, vol_label="Alto",
                                  killzone_name="asia_open")
    assert "ALERTA TACTICA" in msg
    assert "EJECUTA SHORT" in msg
    assert "$80.91" in msg
    assert "$81.36" in msg                # invalidacion
    assert "TP1 (40%)" in msg
    assert "R:R 1.00" in msg
    assert "R:R 2.20" in msg
    assert "#Tactica" in msg
    assert "#SHORT" in msg
    # No expone numeros crudos del motor (P_master, kappa, etc.)
    assert "P_master" not in msg
    assert "kappa" not in msg
    # Importante: no sustituye la senal automatica
    assert "no sustituye" in msg.lower()


def test_build_tactical_alert_accumulate_long():
    import vip_format as vf
    plan = {
        "verdict": "ACUMULAR_EN_ZONA",
        "direction": "long",
        "headline": "",
        "market": {"entry": 80.91, "p_sl": 0.45, "ev": 0.30},
        "primary_zone": {
            "label": "Order Block alcista",
            "low": 80.45, "high": 80.78, "ref": 80.78,
            "ev_cond": 1.40, "p_sl_cond": 0.25, "reach_prob": 0.55,
            "accumulate": [{"price": 80.78, "weight_pct": 40},
                           {"price": 80.61, "weight_pct": 35},
                           {"price": 80.45, "weight_pct": 25}],
        },
        "invalidation": 80.20,
        "trigger": "retroceso a Order Block alcista $80.45-$80.78",
    }
    tps = [
        {"price": 81.05, "rr": 1.00, "weight_pct": 40},
        {"price": 81.30, "rr": 1.50, "weight_pct": 35},
        {"price": 81.60, "rr": 2.20, "weight_pct": 25},
    ]
    msg = vf.build_tactical_alert(plan, tps, vol_label="Normal",
                                  killzone_name="asia_open")
    assert "ACUMULA LONG" in msg
    assert "Order Block alcista" in msg
    assert "40%" in msg and "$80.78" in msg
    assert "Gatillo" in msg
    assert "#LONG" in msg


def test_build_tactical_alert_handles_empty():
    import vip_format as vf
    assert vf.build_tactical_alert(None, [{"price": 1, "rr": 1, "weight_pct": 40}]) == ""
    assert vf.build_tactical_alert({"verdict": "X"}, []) == ""


# ===========================================
# 4. TPS CORTOS
# ===========================================
def test_compute_tactical_tps_short_fallback():
    """Sin structural, sin plan/qa: synthetic 1.0/1.8/2.5 con 40/35/25."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import fq_bot_v3_2 as b
    tps = b._compute_tactical_tps("short", 100.0, 102.0)
    # risk = 2.0; short -> price = entry - risk*rr
    assert len(tps) == 3
    assert tps[0]["rr"] == 1.0 and tps[0]["weight_pct"] == 40
    assert tps[1]["rr"] == 1.8 and tps[1]["weight_pct"] == 35   # synth midband
    assert tps[2]["rr"] == 2.5 and tps[2]["weight_pct"] == 25   # cap conservador
    assert abs(tps[0]["price"] - (100.0 - 2.0 * 1.0)) < 1e-6
    assert abs(tps[1]["price"] - (100.0 - 2.0 * 1.8)) < 1e-6
    assert abs(tps[2]["price"] - (100.0 - 2.0 * 2.5)) < 1e-6


def test_compute_tactical_tps_long_fallback():
    import fq_bot_v3_2 as b
    tps = b._compute_tactical_tps("long", 100.0, 98.0)
    assert abs(tps[0]["price"] - (100.0 + 2.0 * 1.0)) < 1e-6
    assert abs(tps[2]["price"] - (100.0 + 2.0 * 2.5)) < 1e-6


def test_compute_tactical_tps_zero_risk():
    import fq_bot_v3_2 as b
    assert b._compute_tactical_tps("long", 100.0, 100.0) == []


# ===========================================
# 5. PROMOCION A VIP - LOGICA DE GATING
# ===========================================
@pytest.fixture(autouse=True)
def reloj_fijo(monkeypatch):
    """Fija el reloj de `is_dead_window` en un instante conocido y VIVO.

    Estos tests se saltaban solos una hora al dia. `is_dead_window()` lee
    `datetime.now(CDMX_TZ)`, asi que entre las 14:00 y las 16:00 CDMX -- y los
    viernes por la tarde -- seis tests desaparecian sin que nadie lo viera: el
    resumen decia "passed" con seis menos. Un test que se salta segun la hora no
    es un test flaky, es una guarda que deja de guardar en silencio.

    No se mockea el veredicto: se fija el INSTANTE y la logica real corre entera.
    Martes 10:00 CDMX esta fuera de las tres franjas (2PM, ultima hora NY,
    viernes tarde), asi que is_dead_window devuelve False por sus propias reglas.
    Para probar la logica de franja muerta en si esta
    test_dead_window_2pm_manipulation, que pasa las horas explicitamente.
    """
    import volume_quality as vq
    real = vq.is_dead_window
    fijo = datetime(2026, 8, 4, 10, 0, tzinfo=vq.CDMX_TZ)      # martes, activo
    monkeypatch.setattr(vq, "is_dead_window",
                        lambda now_cdmx=None: real(now_cdmx or fijo))
    return fijo


def test_el_reloj_fijo_cae_fuera_de_toda_franja_muerta():
    """Si esto falla, el instante elegido dejo de ser 'vivo' y los tests que
    dependen de el volverian a mentir -- callados, como antes."""
    import volume_quality as vq
    assert vq.is_dead_window() is False
    assert vq.dead_window_label() in (None, "")


def _reload_with_flag(flag_value):
    """Recarga fq_bot_v3_2 con FQ_TACTICAL_VIP_ENABLED= flag_value."""
    import importlib
    os.environ["FQ_TACTICAL_VIP_ENABLED"] = flag_value
    import fq_bot_v3_2 as b
    importlib.reload(b)
    return b


def test_promote_blocked_by_flag_off():
    b = _reload_with_flag("0")
    plan = {"verdict": "EJECUTAR_AHORA", "direction": "short",
            "market": {"entry": 80.91, "p_sl": 0.28, "ev": 1.30}}
    ok, reason = b._should_promote_tactical_to_vip(plan, {"score": 1.2}, "asia_open")
    assert ok is False
    assert "flag" in reason.lower()


def test_promote_blocked_by_low_volume():
    b = _reload_with_flag("1")
    plan = {"verdict": "EJECUTAR_AHORA", "direction": "short",
            "market": {"entry": 80.91, "p_sl": 0.28, "ev": 1.30}}
    ok, reason = b._should_promote_tactical_to_vip(plan, {"score": 0.5}, "asia_open")
    assert ok is False
    assert "vol_score" in reason


def test_promote_blocked_by_weak_edge():
    b = _reload_with_flag("1")
    plan = {"verdict": "EJECUTAR_AHORA", "direction": "short",
            "market": {"entry": 80.91, "p_sl": 0.55, "ev": 0.50}}
    ok, reason = b._should_promote_tactical_to_vip(plan, {"score": 1.2}, "asia_open")
    assert ok is False


def test_promote_ok_when_all_align():
    b = _reload_with_flag("1")
    plan = {"verdict": "EJECUTAR_AHORA", "direction": "short",
            "market": {"entry": 80.91, "p_sl": 0.28, "ev": 1.30}}
    # El reloj lo fija la fixture `reloj_fijo` (martes 10:00 CDMX): fuera de
    # franja muerta, siempre, corra la suite a la hora que corra.
    ok, _ = b._should_promote_tactical_to_vip(plan, {"score": 1.2}, "asia_open")
    assert ok is True


def test_promote_allows_medium_probability():
    """v5.3: una señal 'Edge fuerte · probabilidad media' (p_sl=0.50) SI se
    promueve al VIP (el corte de probabilidad subio a 0.55)."""
    b = _reload_with_flag("1")
    plan = {"verdict": "EJECUTAR_AHORA", "direction": "short",
            "market": {"entry": 80.91, "p_sl": 0.50, "ev": 1.30}}
    ok, reason = b._should_promote_tactical_to_vip(plan, {"score": 1.2}, "asia_open")
    assert ok is True, reason

    # Pero p_sl por encima de 0.55 (probabilidad baja) si bloquea.
    plan_low = {"verdict": "EJECUTAR_AHORA", "direction": "short",
                "market": {"entry": 80.91, "p_sl": 0.60, "ev": 1.30}}
    ok2, _ = b._should_promote_tactical_to_vip(plan_low, {"score": 1.2}, "asia_open")
    assert ok2 is False


def test_promote_accumulate_checks_zone_edge():
    b = _reload_with_flag("1")
    plan = {"verdict": "ACUMULAR_EN_ZONA", "direction": "long",
            "market": {"entry": 80.91, "p_sl": 0.5, "ev": 0.3},
            "primary_zone": {"ev_cond": 1.2, "reach_prob": 0.4, "p_sl_cond": 0.40}}
    ok, _ = b._should_promote_tactical_to_vip(plan, {"score": 1.0}, "asia_open")
    assert ok is True

    # Zona con poca reach -> no promove
    plan2 = dict(plan)
    plan2["primary_zone"] = {"ev_cond": 1.2, "reach_prob": 0.20, "p_sl_cond": 0.40}
    ok2, _ = b._should_promote_tactical_to_vip(plan2, {"score": 1.0}, "asia_open")
    assert ok2 is False


def test_promote_accumulate_rejects_low_zone_probability():
    """v5.3: el ACUMULA 'Desde zona · prob. baja' (p_sl_cond alto) NO se
    promueve aunque el R:R (ev_cond) sea bueno. Es el caso del SHORT $76.90
    que toco SL: reach alta pero probabilidad condicional baja."""
    b = _reload_with_flag("1")
    base = {"verdict": "ACUMULAR_EN_ZONA", "direction": "short",
            "primary_zone": {"ev_cond": 1.6, "reach_prob": 0.7}}

    # prob. baja desde zona (p_sl_cond=0.60) -> bloquea
    low = dict(base)
    low["primary_zone"] = dict(base["primary_zone"], p_sl_cond=0.60)
    ok_low, reason = b._should_promote_tactical_to_vip(low, {"score": 0.9}, "ny")
    assert ok_low is False
    assert "p_sl_cond" in reason

    # prob. media desde zona (p_sl_cond=0.45) -> SI promueve
    med = dict(base)
    med["primary_zone"] = dict(base["primary_zone"], p_sl_cond=0.45)
    ok_med, _ = b._should_promote_tactical_to_vip(med, {"score": 0.9}, "ny")
    assert ok_med is True


def test_asia_open_fakeout_veto_unit():
    """Guard puro: solo veta el patron asia_open + LONG + bajo volumen."""
    import volume_quality as vq
    # long de bajo volumen en asia_open -> veta (el bull fakeout)
    v, reason = vq.asia_open_fakeout_veto("long", 0.70, "asia_open")
    assert v is True
    assert "fakeout" in reason
    # long con volumen genuino (>= 0.85) -> pasa (displacement real)
    assert vq.asia_open_fakeout_veto("long", 1.00, "asia_open")[0] is False
    # short en asia_open -> no se toca (el fakeout es alcista)
    assert vq.asia_open_fakeout_veto("short", 0.40, "asia_open")[0] is False
    # mismo long bajo volumen pero en otra killzone -> no aplica
    assert vq.asia_open_fakeout_veto("long", 0.40, "ny_am_kz")[0] is False


def test_promote_blocked_asia_open_long_low_volume():
    """Caso real del screenshot: ACUMULA LONG en FVG alcista, asia_open,
    'Volumen bajo' (~0.78). Antes pasaba el piso relajado de ACUMULAR (0.60) y
    salia al VIP; ahora el bull-fakeout guard lo bloquea."""
    b = _reload_with_flag("1")
    plan = {"verdict": "ACUMULAR_EN_ZONA", "direction": "long",
            "market": {"entry": 68.75, "p_sl": 0.45, "ev": 0.30},
            "primary_zone": {"ev_cond": 1.4, "reach_prob": 0.5, "p_sl_cond": 0.40}}
    ok, reason = b._should_promote_tactical_to_vip(plan, {"score": 0.78}, "asia_open")
    assert ok is False
    assert "asia_open" in reason and "fakeout" in reason

    # El mismo setup con volumen genuino (Normal+) si se promueve.
    ok_vol, _ = b._should_promote_tactical_to_vip(plan, {"score": 1.00}, "asia_open")
    assert ok_vol is True

    # Y un SHORT de bajo volumen en asia_open no lo bloquea este guard (el
    # fakeout es alcista); lo filtran los otros gates si aplica.
    plan_short = {"verdict": "ACUMULAR_EN_ZONA", "direction": "short",
                  "market": {"entry": 68.75, "p_sl": 0.45, "ev": 0.30},
                  "primary_zone": {"ev_cond": 1.4, "reach_prob": 0.5, "p_sl_cond": 0.40}}
    ok_short, reason_short = b._should_promote_tactical_to_vip(
        plan_short, {"score": 0.78}, "asia_open")
    assert "fakeout" not in reason_short


def test_promote_volume_gate_by_type():
    """v5.3: ACUMULA usa un piso de volumen bajo (~0.60); EJECUTAR mantiene
    la confirmacion (0.85). Rescata señales tipo el ACUMULA SHORT $76.90 que
    marco vol~0.78 y se quedaba fuera del VIP."""
    b = _reload_with_flag("1")

    # ACUMULA con vol 0.78 (antes <0.85 lo bloqueaba) -> ahora SI promueve
    acum = {"verdict": "ACUMULAR_EN_ZONA", "direction": "short",
            "primary_zone": {"ev_cond": 1.2, "reach_prob": 0.5, "p_sl_cond": 0.45}}
    ok, reason = b._should_promote_tactical_to_vip(acum, {"score": 0.78}, "ny")
    assert ok is True, reason

    # Pero tape muerto de verdad (<0.60) SI bloquea hasta el ACUMULA
    ok_dead, _ = b._should_promote_tactical_to_vip(acum, {"score": 0.45}, "ny")
    assert ok_dead is False

    # EJECUTAR a mercado con el mismo 0.78 sigue exigiendo momentum -> bloquea
    exe = {"verdict": "EJECUTAR_AHORA", "direction": "short",
           "market": {"entry": 79.0, "p_sl": 0.40, "ev": 1.6}}
    ok_exe, reason_exe = b._should_promote_tactical_to_vip(exe, {"score": 0.78}, "ny")
    assert ok_exe is False
    assert "vol_score" in reason_exe


# ===========================================
# 6. FIELD TIMEFRAMES (RADAR/ALERTA TACTICA corre aqui)
# ===========================================
def test_classical_tf_profiles_unchanged():
    """v5.2: el motor clasico vuelve a 5m/15m/1h (sin 3m).
    Las senales intradia 1m/3m se canalizan via FIELD_TIMEFRAMES."""
    import fq_bot_v3_2 as b
    assert "3m" not in b.TF_PROFILES, "3m no debe estar en motor clasico"
    assert "1m" not in b.TF_PROFILES, "1m no debe estar en motor clasico"
    assert set(b.TF_PROFILES.keys()) == {"5m", "15m", "1h"}


def test_field_timeframes_default():
    """v5.3: default = 5m afinado + 15m original. 3m ya NO entra por defecto
    (sangraba la cuenta con falsos positivos / senales encimadas)."""
    import importlib
    os.environ.pop("FQ_FIELD_TIMEFRAMES", None)
    os.environ.pop("FQ_FIELD_INCLUDE_1M", None)
    import fq_bot_v3_2 as b
    importlib.reload(b)
    assert b.FIELD_TIMEFRAMES == ("5m", "15m")
    assert "3m" not in b.FIELD_TIMEFRAMES, "3m no debe estar por defecto"


def test_field_timeframes_with_1m_opt_in():
    import importlib
    os.environ["FQ_FIELD_INCLUDE_1M"] = "1"
    import fq_bot_v3_2 as b
    importlib.reload(b)
    assert "1m" in b.FIELD_TIMEFRAMES
    os.environ["FQ_FIELD_INCLUDE_1M"] = "0"
    importlib.reload(b)
    assert "1m" not in b.FIELD_TIMEFRAMES


def test_field_timeframes_csv_override():
    import importlib
    os.environ["FQ_FIELD_TIMEFRAMES"] = "1m,3m"
    import fq_bot_v3_2 as b
    importlib.reload(b)
    assert b.FIELD_TIMEFRAMES == ("1m", "3m")
    os.environ.pop("FQ_FIELD_TIMEFRAMES", None)


# ===========================================
# 6.b GATE DE CONVICCION DEL RADAR (FQ v5.3)
#     "no me des lectura de campo sin conviccion, de ser asi mejor nada"
# ===========================================
def test_conviction_field_strong_edge_passes():
    """5m con Edge fuerte (ev>=1.5) y P(SL) bajo -> emite."""
    import fq_bot_v3_2 as b
    plan = {"verdict": "EJECUTAR_AHORA",
            "market": {"entry": 79.0, "p_sl": 0.30, "ev": 1.60}}
    ok, _ = b._radar_has_conviction(plan, "5m")
    assert ok is True


def test_conviction_field_medium_edge_blocked():
    """5m con 'Edge - probabilidad media' (ev 1.0-1.5) -> NO emite (ruido)."""
    import fq_bot_v3_2 as b
    plan = {"verdict": "EJECUTAR_AHORA",
            "market": {"entry": 79.0, "p_sl": 0.35, "ev": 1.20}}
    ok, reason = b._radar_has_conviction(plan, "5m")
    assert ok is False
    assert "ev=" in reason


def test_conviction_field_allows_medium_probability():
    """v5.3: Edge fuerte + 'probabilidad media' (P(SL)<=0.55) SI emite.
    Mantiene señales utiles tipo 'Edge fuerte · probabilidad media'."""
    import fq_bot_v3_2 as b
    plan = {"verdict": "EJECUTAR_AHORA",
            "market": {"entry": 79.0, "p_sl": 0.50, "ev": 1.80}}
    ok, _ = b._radar_has_conviction(plan, "5m")
    assert ok is True


def test_conviction_field_high_psl_blocked():
    """P(SL) por encima del label 'Media' (>0.55) -> NO emite (probabilidad baja)."""
    import fq_bot_v3_2 as b
    plan = {"verdict": "EJECUTAR_AHORA",
            "market": {"entry": 79.0, "p_sl": 0.60, "ev": 1.80}}
    ok, reason = b._radar_has_conviction(plan, "5m")
    assert ok is False
    assert "p_sl=" in reason


def test_conviction_3m_uses_field_floor():
    """Si alguien fuerza 3m por override, sigue exigiendo Edge fuerte."""
    import fq_bot_v3_2 as b
    plan = {"verdict": "EJECUTAR_AHORA",
            "market": {"entry": 79.0, "p_sl": 0.30, "ev": 1.20}}
    ok, _ = b._radar_has_conviction(plan, "3m")
    assert ok is False


def test_conviction_15m_softer_floor():
    """El 15m original mantiene un piso mas suave (ev>=1.2): un setup que el
    canal de campo descarta, el 15m si lo emite."""
    import fq_bot_v3_2 as b
    plan = {"verdict": "EJECUTAR_AHORA",
            "market": {"entry": 79.0, "p_sl": 0.30, "ev": 1.25}}
    assert b._radar_has_conviction(plan, "5m")[0] is False
    assert b._radar_has_conviction(plan, "15m")[0] is True


def test_conviction_accumulate_checks_zone():
    import fq_bot_v3_2 as b
    strong = {"verdict": "ACUMULAR_EN_ZONA",
              "primary_zone": {"ev_cond": 1.6, "reach_prob": 0.40}}
    assert b._radar_has_conviction(strong, "5m")[0] is True
    weak_reach = {"verdict": "ACUMULAR_EN_ZONA",
                  "primary_zone": {"ev_cond": 1.6, "reach_prob": 0.20}}
    assert b._radar_has_conviction(weak_reach, "5m")[0] is False
    weak_ev = {"verdict": "ACUMULAR_EN_ZONA",
               "primary_zone": {"ev_cond": 1.1, "reach_prob": 0.50}}
    assert b._radar_has_conviction(weak_ev, "5m")[0] is False


def test_conviction_non_operable_verdict_blocked():
    import fq_bot_v3_2 as b
    for v in ("ESPERAR_GATILLO", "STAND_DOWN"):
        ok, _ = b._radar_has_conviction({"verdict": v}, "5m")
        assert ok is False


def test_radar_cooldown_per_tf():
    """5m tiene su propia ventana (30 min default), distinta de 1m/3m (15 min)
    y del 15m (90 min)."""
    import fq_bot_v3_2 as b
    assert b._radar_cooldown_for("5m") == b.RADAR_COOLDOWN_5M_SEC
    assert b._radar_cooldown_for("3m") == b.RADAR_COOLDOWN_FIELD_SEC
    assert b._radar_cooldown_for("1m") == b.RADAR_COOLDOWN_FIELD_SEC
    assert b._radar_cooldown_for("15m") == b.RADAR_COOLDOWN_SEC


def test_radar_module_is_source_of_truth():
    """v5.3: la logica pura del radar vive en fq_radar; el monolito reexporta.
    Garantiza que ambos apuntan al mismo objeto (no copias divergentes)."""
    import fq_radar
    import fq_bot_v3_2 as b
    assert b._radar_has_conviction is fq_radar._radar_has_conviction
    assert b._radar_emit_decision is fq_radar._radar_emit_decision
    assert b._radar_cooldown_for is fq_radar._radar_cooldown_for
    # fq_radar es importable sin arrastrar el runtime del bot (ccxt, etc.)
    assert fq_radar._radar_has_conviction(
        {"verdict": "EJECUTAR_AHORA", "market": {"ev": 1.6, "p_sl": 0.30}}, "5m"
    )[0] is True


# ===========================================
# 7. SMART TP PICKER (contextual)
# ===========================================
def test_extension_score_high():
    import fq_bot_v3_2 as b
    plan = {"market": {"ev": 1.6}, "regime_pct": 0.60}
    qa = {"coherence": 0.70}
    assert b._extension_score(plan, qa) >= 0.95


def test_extension_score_low():
    import fq_bot_v3_2 as b
    plan = {"market": {"ev": 0.2}, "regime_pct": 0.30}
    qa = {"coherence": 0.20}
    assert b._extension_score(plan, qa) <= 0.10


def test_tp_picker_uses_structural_when_in_band():
    import fq_bot_v3_2 as b
    structural = [{"price": 82.00, "kind": "fib_1272"}]  # 1.54R aprox
    tps = b._compute_tactical_tps("long", 80.91, 80.20,
                                  structural_tps=structural,
                                  plan={"market": {"ev": 1.0}, "regime_pct": 0.5},
                                  qa={"coherence": 0.55})
    # TP2 deberia ser el structural (no synthetic)
    assert any(t["kind"] == "fib_1272" for t in tps)


def test_tp_picker_stretches_with_high_extension():
    """Con extension alta y un structural en 1:6+, TP3 lo usa (no se cap a 2.5R)."""
    import fq_bot_v3_2 as b
    structural = [
        {"price": 82.00, "kind": "fib_1272"},
        {"price": 85.50, "kind": "pspace_R"},  # ~6.5R desde 80.91/80.20
    ]
    tps_high = b._compute_tactical_tps("long", 80.91, 80.20,
                                       structural_tps=structural,
                                       plan={"market": {"ev": 1.6}, "regime_pct": 0.60},
                                       qa={"coherence": 0.70})
    assert tps_high[-1]["rr"] > 4.0, "ext alto deberia estirar TP3"


def test_tp_picker_caps_low_extension_at_2_5R():
    """Con extension baja, TP3 se cap en 2.5R aunque haya estructural lejano."""
    import fq_bot_v3_2 as b
    structural = [{"price": 85.50, "kind": "pspace_R"}]  # ~6.5R
    tps_low = b._compute_tactical_tps("long", 80.91, 80.20,
                                      structural_tps=structural,
                                      plan={"market": {"ev": 0.2}, "regime_pct": 0.30},
                                      qa={"coherence": 0.30})
    assert tps_low[-1]["rr"] <= 2.5 + 1e-6
    assert tps_low[-1]["kind"] == "synthetic"


def test_tp_picker_no_structural_fallback():
    """Sin structural_tps: synth 1.0/1.8/2.5 con cierres 40/35/25."""
    import fq_bot_v3_2 as b
    tps = b._compute_tactical_tps("short", 100.0, 102.0)
    assert len(tps) == 3
    assert tps[0]["rr"] == 1.0 and tps[0]["weight_pct"] == 40
    assert tps[2]["weight_pct"] == 25


def test_tp_picker_monotonic():
    """TPs ordenados por R creciente."""
    import fq_bot_v3_2 as b
    structural = [
        {"price": 82.00, "kind": "fib_1272"},
        {"price": 83.50, "kind": "fib_1618"},
        {"price": 85.50, "kind": "pspace_R"},
    ]
    tps = b._compute_tactical_tps("long", 80.91, 80.20,
                                  structural_tps=structural,
                                  plan={"market": {"ev": 1.6}, "regime_pct": 0.60},
                                  qa={"coherence": 0.70})
    rrs = [t["rr"] for t in tps]
    assert rrs == sorted(rrs), "TPs deben estar ordenados por R"


# ===========================================
# 8. TIERS: VIP + TRIAL + ADMIN (no solo VIP)
# ===========================================
def test_tactical_alert_broadcasts_to_trial_too():
    """v5.2: la alerta tactica va a vip+trial+admin (no excluye trial)."""
    # Verificamos por inspeccion del codigo fuente que radar_check usa los 3 tiers
    import inspect
    import fq_bot_v3_2 as b
    src = inspect.getsource(b.radar_check)
    assert 'tiers=["vip", "trial", "admin"]' in src, \
        "radar_check debe difundir a vip+trial+admin"


# ===========================================
# 9. TF LABEL EN HEADER (3m/15m visible)
# ===========================================
def test_tactical_alert_header_includes_tf():
    import vip_format as vf
    plan = {"verdict": "EJECUTAR_AHORA", "direction": "short",
            "market": {"entry": 80.91, "p_sl": 0.28, "ev": 1.30},
            "primary_zone": None, "invalidation": 81.36}
    tps = [{"price": 80.46, "rr": 1.0, "weight_pct": 40, "kind": "synthetic"},
           {"price": 80.23, "rr": 1.5, "weight_pct": 35, "kind": "synthetic"},
           {"price": 79.92, "rr": 2.2, "weight_pct": 25, "kind": "synthetic"}]
    msg = vf.build_tactical_alert(plan, tps, vol_label="Alto",
                                   killzone_name="asia_open", tf_label="3m")
    # Formato premium (v5.5): el TF viaja en la linea de contexto del header
    # (Killzone · Volumen · <TF> · hora), no ya como sufijo "— 3m".
    assert "3m" in msg, "header debe llevar TF"


# ===========================================
# 10. ANTI-FLIP RADAR (LONG -> SHORT en cooldown)
# ===========================================
# Reproducen el caso del 02/06 02:09 AM: el bias del 3m flipea de long->short
# 13 min despues del primer radar. Antes del fix, el cooldown solo bloqueaba
# misma direccion; el flip pasaba sin freno. Ahora exige fuerza relativa.

def test_radar_no_previous_emits_normal():
    import fq_bot_v3_2 as b
    action, flip = b._radar_emit_decision(
        last_radar={}, now_s=1000.0, direction="long",
        new_ev=1.2, new_psl=0.30, cooldown_sec=900)
    assert action == "emit"
    assert flip is False


def test_radar_same_direction_in_cooldown_skips():
    import fq_bot_v3_2 as b
    last = {"ts": 1000.0, "direction": "long", "ev": 1.2, "p_sl": 0.30}
    action, flip = b._radar_emit_decision(
        last_radar=last, now_s=1000.0 + 300, direction="long",
        new_ev=1.3, new_psl=0.28, cooldown_sec=900)
    assert action == "skip"
    assert flip is False


def test_radar_weak_flip_in_cooldown_skips():
    """LONG@ev=1.40 seguido por SHORT@ev=1.45 dentro de 13min: el SHORT no
    supera el ratio 1.3 (necesitaria >=1.82), debe descartarse."""
    import fq_bot_v3_2 as b
    last = {"ts": 1000.0, "direction": "long", "ev": 1.40, "p_sl": 0.30}
    action, flip = b._radar_emit_decision(
        last_radar=last, now_s=1000.0 + 13 * 60, direction="short",
        new_ev=1.45, new_psl=0.30, cooldown_sec=15 * 60)
    assert action == "skip"
    assert flip is False


def test_radar_strong_flip_in_cooldown_replaces():
    """LONG@ev=1.00 seguido por SHORT@ev=1.60 (1.6x > 1.3x ratio, EV>=1.0,
    P(SL)<=0.45): debe pasar y marcarse como reemplazo."""
    import fq_bot_v3_2 as b
    last = {"ts": 1000.0, "direction": "long", "ev": 1.00, "p_sl": 0.35}
    action, flip = b._radar_emit_decision(
        last_radar=last, now_s=1000.0 + 13 * 60, direction="short",
        new_ev=1.60, new_psl=0.30, cooldown_sec=15 * 60)
    assert action == "emit"
    assert flip is True


def test_radar_flip_fails_min_ev_floor():
    """Aunque el ratio se cumpla (0.5 -> 0.80 = 1.6x), si el EV nuevo no
    alcanza el minimo absoluto 1.0 la senal sigue siendo debil, descartar."""
    import fq_bot_v3_2 as b
    last = {"ts": 1000.0, "direction": "long", "ev": 0.50, "p_sl": 0.40}
    action, flip = b._radar_emit_decision(
        last_radar=last, now_s=1000.0 + 60, direction="short",
        new_ev=0.80, new_psl=0.30, cooldown_sec=15 * 60)
    assert action == "skip"


def test_radar_flip_fails_high_psl():
    """EV nuevo fuerte pero P(SL) > 0.45: no es lo suficientemente seguro
    para reemplazar al previo."""
    import fq_bot_v3_2 as b
    last = {"ts": 1000.0, "direction": "long", "ev": 1.00, "p_sl": 0.30}
    action, flip = b._radar_emit_decision(
        last_radar=last, now_s=1000.0 + 60, direction="short",
        new_ev=1.80, new_psl=0.55, cooldown_sec=15 * 60)
    assert action == "skip"


def test_radar_flip_after_cooldown_emits_normal():
    """Pasado el cooldown, el flip se emite normal (sin marca de reemplazo)."""
    import fq_bot_v3_2 as b
    last = {"ts": 1000.0, "direction": "long", "ev": 1.40, "p_sl": 0.30}
    action, flip = b._radar_emit_decision(
        last_radar=last, now_s=1000.0 + 20 * 60, direction="short",
        new_ev=1.45, new_psl=0.30, cooldown_sec=15 * 60)
    assert action == "emit"
    assert flip is False, "fuera de cooldown no se marca como reemplazo"


def test_radar_real_case_long_158_to_short_165_suppressed():
    """Caso real 02/06: LONG entry 79.78 invalida 79.24 -> SHORT entry 79.57
    invalida 80.01, 13 min despues. Supuesto: EV_long ~ 1.10 (Edge), EV_short
    ~ 1.55 (Edge fuerte). 1.55 / 1.10 = 1.41 > 1.3 -> el SHORT SI debe pasar
    como reemplazo (acierta con la senal mas fuerte segun la propia etiqueta
    del bot)."""
    import fq_bot_v3_2 as b
    last = {"ts": 1000.0, "direction": "long", "ev": 1.10, "p_sl": 0.32}
    action, flip = b._radar_emit_decision(
        last_radar=last, now_s=1000.0 + 13 * 60, direction="short",
        new_ev=1.55, new_psl=0.28, cooldown_sec=15 * 60)
    assert action == "emit"
    assert flip is True
