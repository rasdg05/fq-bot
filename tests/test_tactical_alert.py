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


def test_volume_quality_labels():
    import volume_quality as vq
    assert vq.volume_quality_label(0.5) == "Muy bajo"
    assert vq.volume_quality_label(0.7) == "Bajo"
    assert vq.volume_quality_label(1.0) == "Normal"
    assert vq.volume_quality_label(1.4) == "Alto"
    assert vq.volume_quality_label(None) == "—"


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
def test_compute_tactical_tps_short():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import fq_bot_v3_2 as b
    tps = b._compute_tactical_tps("short", 100.0, 102.0)
    # risk = 2.0; short -> price = entry - risk*rr
    assert len(tps) == 3
    assert tps[0]["rr"] == 1.0 and tps[0]["weight_pct"] == 40
    assert tps[1]["rr"] == 1.5 and tps[1]["weight_pct"] == 35
    assert tps[2]["rr"] == 2.2 and tps[2]["weight_pct"] == 25
    assert abs(tps[0]["price"] - (100.0 - 2.0 * 1.0)) < 1e-6
    assert abs(tps[1]["price"] - (100.0 - 2.0 * 1.5)) < 1e-6
    assert abs(tps[2]["price"] - (100.0 - 2.0 * 2.2)) < 1e-6


def test_compute_tactical_tps_long():
    import fq_bot_v3_2 as b
    tps = b._compute_tactical_tps("long", 100.0, 98.0)
    assert abs(tps[0]["price"] - (100.0 + 2.0 * 1.0)) < 1e-6
    assert abs(tps[2]["price"] - (100.0 + 2.0 * 2.2)) < 1e-6


def test_compute_tactical_tps_zero_risk():
    import fq_bot_v3_2 as b
    assert b._compute_tactical_tps("long", 100.0, 100.0) == []


# ===========================================
# 5. PROMOCION A VIP - LOGICA DE GATING
# ===========================================
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
    # Tambien debe evitar dead window. Aqui no podemos mockear is_dead_window
    # facilmente sin freeze_time; el test depende de la hora actual.
    # Para evitar flakiness, solo afirmamos que el gating no se bloquea por
    # las condiciones que podemos controlar (vol+edge). is_dead_window depende
    # de la hora; si runea en 15-16 CDMX o viernes tarde no promueve y el test
    # se salta con xfail-like skip.
    import volume_quality as vq
    if vq.is_dead_window():
        import pytest
        pytest.skip("Test corriendo en franja muerta; no se puede afirmar promote=True")
    ok, _ = b._should_promote_tactical_to_vip(plan, {"score": 1.2}, "asia_open")
    assert ok is True


def test_promote_accumulate_checks_zone_edge():
    b = _reload_with_flag("1")
    import volume_quality as vq
    if vq.is_dead_window():
        import pytest
        pytest.skip("franja muerta")
    plan = {"verdict": "ACUMULAR_EN_ZONA", "direction": "long",
            "market": {"entry": 80.91, "p_sl": 0.5, "ev": 0.3},
            "primary_zone": {"ev_cond": 1.2, "reach_prob": 0.4}}
    ok, _ = b._should_promote_tactical_to_vip(plan, {"score": 1.0}, "asia_open")
    assert ok is True

    # Zona con poca reach -> no promove
    plan2 = dict(plan)
    plan2["primary_zone"] = {"ev_cond": 1.2, "reach_prob": 0.20}
    ok2, _ = b._should_promote_tactical_to_vip(plan2, {"score": 1.0}, "asia_open")
    assert ok2 is False


# ===========================================
# 6. 3M TIMEFRAME PROFILE
# ===========================================
def test_3m_profile_exists():
    import fq_bot_v3_2 as b
    assert "3m" in b.TF_PROFILES
    p3 = b.TF_PROFILES["3m"]
    assert p3["label"] == "SCALP_INTRA"
    assert p3["RR_MIN_TP3"] == 1.50    # TP3 corto para intradia
    assert p3["PMASTER_MIN"] == 2.05   # mas exigente que 5m
    assert p3["SIGNAL_COOLDOWN_MINUTES"] == 10


def test_3m_opt_in_via_env():
    import importlib
    os.environ["FQ_INCLUDE_3M"] = "1"
    import fq_bot_v3_2 as b
    importlib.reload(b)
    assert "3m" in b.TIMEFRAMES
    # Sin flag, no se incluye
    os.environ["FQ_INCLUDE_3M"] = "0"
    importlib.reload(b)
    assert "3m" not in b.TIMEFRAMES
