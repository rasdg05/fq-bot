# -*- coding: utf-8 -*-
"""
FQ v5.5 - Longitud de onda de TPs por timeframe + cap anti-sobre-extension +
ventana de tiempo emergente (horizonte adaptativo).

Cubre:
  - _tf_wavelength_factor: escala correcta por TF.
  - _compute_tps_v2: TP3<=5R y TP4<=6.5R (baseline 15m), escala por TF,
    monotonia estricta garantizada.
  - _compute_tactical_tps: cap del contexto favorable bajado 8.0R -> 6.5R,
    onda mas larga en 5m/1m que en 15m.
  - quantum_timelines.adaptive_horizon: sustento en estructura (distancia/ATR)
    + tiempo universal (killzone), clamps y fallback.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ----------------------------------------------------------------------
# Factor de longitud de onda
# ----------------------------------------------------------------------
def test_tf_wavelength_factor_known_tfs():
    import fq_bot_v3_2 as b
    assert b._tf_wavelength_factor("15m") == 1.0
    assert b._tf_wavelength_factor("5m") > 1.0
    assert b._tf_wavelength_factor("1m") > b._tf_wavelength_factor("5m")


def test_tf_wavelength_factor_unknown_defaults_1():
    import fq_bot_v3_2 as b
    assert b._tf_wavelength_factor(None) == 1.0
    assert b._tf_wavelength_factor("13m") == 1.0


# ----------------------------------------------------------------------
# _compute_tps_v2 - cap anti-sobre-extension + monotonia
# ----------------------------------------------------------------------
def _empty_fd():
    # Sin estructura cercana -> fuerza el camino synthetic acotado por banda.
    return {"swing_high_recent": 1e9, "swing_low_recent": -1e9,
            "ema50": 99.0, "low_20": 95.0, "high_20": 108.0}


def test_tps_v2_caps_tp3_tp4_15m():
    import fq_bot_v3_2 as b
    ps = {"count": 2, "support_weight": 0, "resistance_weight": 0}
    tps = b._compute_tps_v2(100.0, 98.0, "long", _empty_fd(), ps, tf="15m")
    assert len(tps) == 4
    # TP3 no rebasa 5R, TP4 no rebasa 6.5R (baseline 15m, wf=1.0)
    assert tps[2]["rr"] <= 5.0 + 1e-6
    assert tps[3]["rr"] <= 6.5 + 1e-6


def test_tps_v2_monotonic_strict():
    import fq_bot_v3_2 as b
    ps = {"count": 2, "support_weight": 0, "resistance_weight": 0}
    for tf in ("1m", "5m", "15m"):
        tps = b._compute_tps_v2(100.0, 99.6, "long", _empty_fd(), ps, tf=tf)
        rrs = [t["rr"] for t in tps]
        assert rrs == sorted(rrs)
        assert len(set(rrs)) == len(rrs), "TPs deben ser estrictamente crecientes"


def test_tps_v2_5m_longer_wave_than_15m():
    import fq_bot_v3_2 as b
    ps = {"count": 2, "support_weight": 0, "resistance_weight": 0}
    fd = _empty_fd()
    t5 = b._compute_tps_v2(100.0, 98.0, "long", fd, ps, tf="5m")
    t15 = b._compute_tps_v2(100.0, 98.0, "long", fd, ps, tf="15m")
    # cada TP del 5m esta mas lejos en R que su equivalente 15m (onda mas larga)
    for a, c in zip(t5, t15):
        assert a["rr"] >= c["rr"]
    assert t5[-1]["rr"] > t15[-1]["rr"]


def test_tps_v2_short_direction_below_entry():
    import fq_bot_v3_2 as b
    ps = {"count": 2, "support_weight": 0, "resistance_weight": 0}
    tps = b._compute_tps_v2(100.0, 102.0, "short", _empty_fd(), ps, tf="15m")
    assert all(t["price"] < 100.0 for t in tps)


# ----------------------------------------------------------------------
# _compute_tactical_tps - cap 6.5R + onda por TF
# ----------------------------------------------------------------------
def test_tactical_cap_rejects_over_extended_structural():
    import fq_bot_v3_2 as b
    # structural a ~12.8R: fuera del cap 6.5R -> NO se persigue (synth 3.0R)
    structural = [{"price": 90.0, "kind": "pspace_R"}]
    tps = b._compute_tactical_tps(
        "long", 80.91, 80.20, structural_tps=structural,
        plan={"market": {"ev": 1.6}, "regime_pct": 0.60},
        qa={"coherence": 0.70}, tf="15m")
    assert tps[-1]["rr"] <= 6.5 + 1e-6
    assert tps[-1]["kind"] == "synthetic"


def test_tactical_cap_accepts_structural_within_band():
    import fq_bot_v3_2 as b
    # structural a ~6.46R: dentro del cap 6.5R -> se usa (anclaje real)
    structural = [{"price": 85.50, "kind": "pspace_R"}]
    tps = b._compute_tactical_tps(
        "long", 80.91, 80.20, structural_tps=structural,
        plan={"market": {"ev": 1.6}, "regime_pct": 0.60},
        qa={"coherence": 0.70}, tf="15m")
    assert tps[-1]["kind"] == "pspace_R"
    assert 6.0 <= tps[-1]["rr"] <= 6.5 + 1e-6


def test_tactical_5m_longer_wave_than_15m():
    import fq_bot_v3_2 as b
    t5 = b._compute_tactical_tps("long", 100.0, 98.0, tf="5m")
    t15 = b._compute_tactical_tps("long", 100.0, 98.0, tf="15m")
    assert t5[-1]["rr"] > t15[-1]["rr"]


# ----------------------------------------------------------------------
# Ventana de tiempo emergente - horizonte adaptativo
# ----------------------------------------------------------------------
def test_adaptive_horizon_session_shortens_in_strong_killzone():
    import quantum_timelines as qt
    # Misma estructura: killzone fuerte (w=1.4) -> ventana <= killzone debil (w=0.6)
    h_strong = qt.adaptive_horizon(100.0, 1.0, 112.0, session_w=1.4)
    h_weak = qt.adaptive_horizon(100.0, 1.0, 112.0, session_w=0.6)
    assert h_strong <= h_weak


def test_adaptive_horizon_clamped():
    import quantum_timelines as qt
    h = qt.adaptive_horizon(100.0, 1.0, 112.0, session_w=1.0)
    assert qt.HORIZON_MIN_CANDLES <= h <= qt.HORIZON_MAX_CANDLES


def test_adaptive_horizon_farther_tp_longer_window():
    import quantum_timelines as qt
    near = qt.adaptive_horizon(100.0, 1.0, 104.0, session_w=1.0)
    far = qt.adaptive_horizon(100.0, 1.0, 120.0, session_w=1.0)
    assert far >= near


def test_adaptive_horizon_fallback_on_bad_input():
    import quantum_timelines as qt
    assert qt.adaptive_horizon(100.0, 0.0, 112.0, session_w=1.0) == qt.DEFAULT_HORIZON
    assert qt.adaptive_horizon(100.0, 1.0, None, session_w=1.0) == qt.DEFAULT_HORIZON
