# -*- coding: utf-8 -*-
"""
bt_features (integracion): replay del motor sobre histgrico. Se testea con un
evaluate_fn FALSO -> valida el cableado sin importar el monolito ni red.
"""
import numpy as np
import pandas as pd

import bt_features as bf


# --- dobles de prueba: field y report estilo fusion_engine ---
class _FakeField:
    confluence_count = 4
    pd_pct = 0.25
    w_effective = 1.3
    node_type = "colapso"
    killzone = "ny_kz"
    killzone_priority = "alta"
    bias_4h = "alcista"
    bias_1h = "alcista"
    choch = True
    has_fuel = True


def _fire_report(direction="long", entry=100.0, sl=95.0, tp1=105.0, tp3=115.0):
    return {
        "decision": "fire",
        "direction": direction,
        "levels": {"entry": entry, "sl": sl, "tp1": tp1, "tp2": 110.0,
                   "tp3": tp3, "rr_tp3": 3.0},
        "p_master_data": {"p_master": 3.1, "p_master_raw": 3.0,
                          "p_master_pre_vol": 3.05},
        "score": {"total_score": 0.72,
                  # forma REAL de signal_scorer.evaluate: lista de dicts
                  "breakdown": [
                      {"name": "volume", "score": 0.8, "weight": 0.2},
                      {"name": "structure", "score": 0.7, "weight": 0.2},
                      {"name": "liquidity", "score": 0.6, "weight": 0.2},
                      {"name": "concept_stack", "score": 0.75, "weight": 0.2},
                      {"name": "history", "score": 0.65, "weight": 0.2},
                  ]},
        "regime": {"state": "tendencia", "score": 0.9},
    }


def _silence_report():
    return {"decision": "silence", "reason": "sin edge"}


def _make_tf(n, start="2024-01-01", freq="15min", base=100.0):
    ts = pd.date_range(start, periods=n, freq=freq)
    px = base + np.sin(np.arange(n) / 10.0)
    return pd.DataFrame({"timestamp": ts, "open": px, "high": px + 1,
                         "low": px - 1, "close": px, "volume": 100.0})


# --------------------------------------------------------------------------
# htf_window (alineacion causal)
# --------------------------------------------------------------------------
def test_htf_window_is_causal():
    df = _make_tf(50, freq="1h")
    ts = df["timestamp"].iloc[20]
    win = bf.htf_window(df, np.datetime64(ts))
    assert win["timestamp"].max() <= ts
    assert len(win) == 21                      # 0..20 inclusive


def test_htf_window_tail_caps_rows():
    df = _make_tf(100, freq="1h")
    ts = df["timestamp"].iloc[80]
    win = bf.htf_window(df, np.datetime64(ts), tail=10)
    assert len(win) == 10
    assert win["timestamp"].max() <= ts


def test_htf_window_none_passthrough():
    assert bf.htf_window(None, np.datetime64("2024-01-01")) is None


# --------------------------------------------------------------------------
# extract_features
# --------------------------------------------------------------------------
def test_extract_features_flattens_field_and_report():
    f = bf.extract_features(_FakeField(), _fire_report())
    assert f["p_master"] == 3.1
    assert f["scorer_total"] == 0.72
    assert f["scorer_volume"] == 0.8
    assert f["regime_state"] == "tendencia"
    assert f["field_confluence_count"] == 4
    assert f["field_pd_pct"] == 0.25
    assert f["field_bias_4h"] == "alcista"


def test_extract_features_defensive_on_empty_report():
    f = bf.extract_features(_FakeField(), {"decision": "silence"})
    assert f["p_master"] is None
    assert f["scorer_total"] is None
    assert f["regime_state"] is None
    # los atributos de field siguen presentes
    assert f["field_confluence_count"] == 4


# --------------------------------------------------------------------------
# replay_events (cableado con evaluate_fn falso)
# --------------------------------------------------------------------------
def test_replay_fires_only_on_marked_bars():
    df15 = _make_tf(260)
    fire_bars = {210, 230, 250}

    def fake_eval(w15, w1h, w4h, w1m, dp, lap, cl, cfg):
        i = len(w15) - 1            # indice de la ultima vela de la ventana
        if i in fire_bars:
            return True, _FakeField(), _fire_report(entry=float(w15["close"].iloc[-1]))
        return False, _FakeField(), _silence_report()

    ev = bf.replay_events(
        df15, None, None, None,
        evaluate_fn=fake_eval,
        detect_pspace_fn=None, laplacian_check_fn=None, calculate_levels_fn=None,
        config={"PMASTER_MIN": 2.6},
        min_lookback=200,
    )
    assert list(ev["entry_index"]) == sorted(fire_bars)
    assert set(ev["direction"]) == {bf.LONG}
    assert "p_master" in ev.columns and "scorer_total" in ev.columns
    # entry tomado del close real de esa vela
    assert ev.iloc[0]["entry_price"] == float(df15["close"].iloc[210])


def test_replay_skips_fire_without_levels():
    df15 = _make_tf(230)

    def fake_eval(w15, *a):
        i = len(w15) - 1
        if i == 220:
            r = _fire_report()
            r["levels"] = {"entry": 100.0}      # falta sl/tp -> debe saltarse
            return True, _FakeField(), r
        return False, _FakeField(), _silence_report()

    ev = bf.replay_events(
        df15, None, None, None, evaluate_fn=lambda w15, w1h, w4h, w1m, *a: fake_eval(w15),
        detect_pspace_fn=None, laplacian_check_fn=None, calculate_levels_fn=None,
        config={}, min_lookback=200,
    )
    assert len(ev) == 0


def test_replay_short_direction_and_enrich():
    df15 = _make_tf(230)

    def fake_eval(w15, w1h, w4h, w1m, dp, lap, cl, cfg):
        if len(w15) - 1 == 215:
            return True, _FakeField(), _fire_report(direction="short")
        return False, _FakeField(), _silence_report()

    def enrich(field, report, win15, direction):
        return {"vol_score": 0.66, "sb_weight": 1.1}

    ev = bf.replay_events(
        df15, None, None, None, evaluate_fn=fake_eval,
        detect_pspace_fn=None, laplacian_check_fn=None, calculate_levels_fn=None,
        config={}, min_lookback=200, enrich_fn=enrich,
    )
    assert len(ev) == 1
    assert ev.iloc[0]["direction"] == bf.SHORT
    assert ev.iloc[0]["vol_score"] == 0.66
    assert ev.iloc[0]["sb_weight"] == 1.1


def test_replay_step_subsamples():
    df15 = _make_tf(260)

    def fake_eval(w15, *a, **k):
        return True, _FakeField(), _fire_report()

    ev = bf.replay_events(
        df15, None, None, None,
        evaluate_fn=lambda *a, **k: fake_eval(a[0]),
        detect_pspace_fn=None, laplacian_check_fn=None, calculate_levels_fn=None,
        config={}, min_lookback=200, step=10,
    )
    # de 200..259 en pasos de 10 -> 200,210,...,250 = 6 evaluaciones
    assert list(ev["entry_index"]) == [200, 210, 220, 230, 240, 250]


# --------------------------------------------------------------------------
# Eje A — bloque quantum / tiempo emergente en extract_features
# --------------------------------------------------------------------------
def _qt_report():
    r = _fire_report()
    r["p_master_data"].update({
        "kappa_evo": 1.08, "alpha_hybrid": 0.6, "h_factor": 1.0,
        "f_confluence": 0.7, "f_ict": 0.5, "n_concepts": 3,
        "vol_score": 1.25, "session_bias_mult": 1.1,
        "sync_score": 0.82, "sigma_tau": 1.05,
    })
    return r


def test_extract_features_emits_quantum_block():
    f = bf.extract_features(_FakeField(), _qt_report())
    # las 10 coordenadas del bloque quantum quedan aplanadas con prefijo qt_
    assert f["qt_kappa_evo"] == 1.08
    assert f["qt_sigma_tau"] == 1.05
    assert f["qt_sync_score"] == 0.82
    assert f["qt_vol_score"] == 1.25
    assert f["qt_n_concepts"] == 3
    for k in ("qt_alpha_hybrid", "qt_h_factor", "qt_f_confluence", "qt_f_ict",
              "qt_session_bias_mult"):
        assert k in f


def test_extract_features_quantum_block_defensive_none():
    # si el motor no pobló esas claves (p.ej. Phase E OFF), no rompe: van None.
    f = bf.extract_features(_FakeField(), _fire_report())
    assert f["qt_sync_score"] is None and f["qt_sigma_tau"] is None
    assert f["qt_kappa_evo"] is None
