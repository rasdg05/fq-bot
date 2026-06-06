# -*- coding: utf-8 -*-
"""
bt_labeler (etapa 2): etiquetado triple-barrier. Pieza pura -> tests directos
sobre DataFrames OHLCV construidos a mano, sin red ni mocks.
"""
import pandas as pd
import pytest

import bt_labeler as lb


def _bars(rows):
    """rows: lista de (high, low, close)."""
    return pd.DataFrame(rows, columns=["high", "low", "close"])


# --------------------------------------------------------------------------
# label_event - casos directos
# --------------------------------------------------------------------------
def test_long_hits_target():
    # entry 100, stop 95 (R=5), target 110. La 3a vela toca 110.
    bars = _bars([(102, 99, 101), (104, 100, 103), (111, 105, 110)])
    r = lb.label_event(bars, 100, 95, 110, lb.LONG)
    assert r["outcome"] == lb.WIN
    assert r["bars_held"] == 3
    assert r["exit_price"] == 110
    assert r["pnl_r"] == pytest.approx((110 - 100) / 5)   # +2R
    assert r["hit_index"] == 2


def test_long_hits_stop():
    bars = _bars([(102, 99, 101), (101, 94, 96)])   # 2a vela perfora 95
    r = lb.label_event(bars, 100, 95, 110, lb.LONG)
    assert r["outcome"] == lb.LOSS
    assert r["bars_held"] == 2
    assert r["pnl_r"] == pytest.approx(-1.0)          # -1R
    assert r["hit_index"] == 1


def test_long_timeout_marks_to_close():
    bars = _bars([(101, 99, 100.5), (102, 99, 101.5)])  # ni TP ni SL
    r = lb.label_event(bars, 100, 95, 110, lb.LONG)
    assert r["outcome"] == lb.TIMEOUT
    assert r["bars_held"] == 2
    assert r["exit_price"] == 101.5
    assert r["pnl_r"] == pytest.approx((101.5 - 100) / 5)  # +0.3R


def test_short_hits_target():
    # SHORT entry 100, stop 105 (R=5), target 90. La vela toca 90 por abajo.
    bars = _bars([(101, 98, 99), (100, 89, 91)])
    r = lb.label_event(bars, 100, 105, 90, lb.SHORT)
    assert r["outcome"] == lb.WIN
    assert r["pnl_r"] == pytest.approx((100 - 90) / 5)     # +2R short
    assert r["hit_index"] == 1


def test_short_hits_stop():
    bars = _bars([(106, 101, 105)])   # high 106 >= stop 105
    r = lb.label_event(bars, 100, 105, 90, lb.SHORT)
    assert r["outcome"] == lb.LOSS
    assert r["pnl_r"] == pytest.approx(-1.0)


def test_same_bar_pessimistic_defaults_to_loss():
    # Una sola vela que toca TP (111) Y SL (94): ambiguo.
    bars = _bars([(111, 94, 100)])
    r_pess = lb.label_event(bars, 100, 95, 110, lb.LONG, pessimistic=True)
    assert r_pess["outcome"] == lb.LOSS
    r_opt = lb.label_event(bars, 100, 95, 110, lb.LONG, pessimistic=False)
    assert r_opt["outcome"] == lb.WIN


def test_max_bars_caps_horizon():
    # El target llega en la vela 3, pero max_bars=2 fuerza timeout antes.
    bars = _bars([(101, 99, 100), (102, 99, 101), (111, 105, 110)])
    r = lb.label_event(bars, 100, 95, 110, lb.LONG, max_bars=2)
    assert r["outcome"] == lb.TIMEOUT
    assert r["bars_held"] == 2


def test_mfe_mae_tracked():
    # Sube a 108 (MFE +1.6R), baja a 97 (MAE -0.6R), cierra timeout.
    bars = _bars([(108, 99, 100), (101, 97, 99)])
    r = lb.label_event(bars, 100, 95, 110, lb.LONG)
    assert r["mfe_r"] == pytest.approx((108 - 100) / 5)
    assert r["mae_r"] == pytest.approx((97 - 100) / 5)


def test_zero_risk_raises():
    bars = _bars([(101, 99, 100)])
    with pytest.raises(ValueError):
        lb.label_event(bars, 100, 100, 110, lb.LONG)


def test_bad_direction_raises():
    bars = _bars([(101, 99, 100)])
    with pytest.raises(ValueError):
        lb.label_event(bars, 100, 95, 110, 0)


# --------------------------------------------------------------------------
# barriers_from_r
# --------------------------------------------------------------------------
def test_barriers_from_stop_price():
    stop, target = lb.barriers_from_r(100, lb.LONG, stop_price=95, target_rr=2.0)
    assert stop == 95
    assert target == pytest.approx(110)   # 100 + 5*2


def test_barriers_from_r_pct_short():
    stop, target = lb.barriers_from_r(100, lb.SHORT, stop_r_pct=0.02,
                                      target_rr=3.0)
    assert stop == pytest.approx(102)              # short: stop arriba
    assert target == pytest.approx(100 - 2 * 3)    # 94


# --------------------------------------------------------------------------
# label_events (lote) + summary
# --------------------------------------------------------------------------
def test_label_events_batch_and_summary():
    # Serie continua; dos eventos con desenlaces distintos.
    df = _bars([
        (100, 100, 100),  # 0 entry A
        (102, 99, 101),   # 1
        (111, 105, 110),  # 2 A gana
        (100, 100, 100),  # 3 entry B
        (101, 94, 96),    # 4 B pierde
        (97, 95, 96),     # 5
    ])
    events = [
        {"entry_index": 0, "entry_price": 100, "stop_price": 95,
         "target_price": 110, "direction": lb.LONG, "bucket": "A"},
        {"entry_index": 3, "entry_price": 100, "stop_price": 95,
         "target_price": 110, "direction": lb.LONG, "bucket": "B"},
    ]
    out = lb.label_events(df, events)
    assert list(out["outcome"]) == [lb.WIN, lb.LOSS]
    # preserva claves originales del evento
    assert list(out["bucket"]) == ["A", "B"]

    s = lb.label_summary(out)
    assert s["n"] == 2
    assert s["wins"] == 1 and s["losses"] == 1
    assert s["win_rate"] == pytest.approx(0.5)
    assert s["total_r"] == pytest.approx(2.0 + (-1.0))  # +2R y -1R


def test_label_events_no_future_marks_none():
    df = _bars([(100, 100, 100), (101, 99, 100)])
    events = [{"entry_index": 1, "entry_price": 100, "stop_price": 95,
               "target_price": 110, "direction": lb.LONG}]
    out = lb.label_events(df, events)
    assert out.iloc[0]["outcome"] is None
    assert lb.label_summary(out) is None
