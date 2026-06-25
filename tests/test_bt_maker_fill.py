# -*- coding: utf-8 -*-
"""Fill-model de la entrada maker en backtest (bt_engine.maker_entry_fill_mask):
una limite pasiva en `entry_price` se llena SOLO si una vela SIGUIENTE penetra el
nivel mas alla de eps (touch NO llena). Verifica geometria long/short, ventana
TTL (excluye la vela de firing), y que coincide con la regla VIVA por-vela de
gold_paper.process_maker_pending. Sin red ni datos: arrays sinteticos."""
import numpy as np
import pandas as pd
import pytest

import bt_engine as eng

EPS = 1e-4   # 1 bps
TTL = 6


def _trades(rows):
    return pd.DataFrame([{"entry_index": ei, "entry_price": e, "direction": d}
                         for ei, e, d in rows])


def test_long_fills_on_penetration():
    low = np.array([100, 99.98, 100, 100, 100, 100, 100, 100.0])  # bar1 < 99.99
    high = np.full(8, 101.0)
    m = eng.maker_entry_fill_mask(_trades([(0, 100.0, eng.LONG)]), high, low,
                                  eps=EPS, ttl_bars=TTL)
    assert bool(m[0]) is True


def test_long_misses_on_no_touch():
    low = np.full(8, 100.0)        # nunca penetra por debajo de 99.99
    high = np.full(8, 101.0)
    m = eng.maker_entry_fill_mask(_trades([(0, 100.0, eng.LONG)]), high, low,
                                  eps=EPS, ttl_bars=TTL)
    assert bool(m[0]) is False


def test_short_fills_on_penetration():
    high = np.array([100, 100.02, 100, 100, 100, 100, 100, 100.0])  # bar1 > 100.01
    low = np.full(8, 99.0)
    m = eng.maker_entry_fill_mask(_trades([(0, 100.0, eng.SHORT)]), high, low,
                                  eps=EPS, ttl_bars=TTL)
    assert bool(m[0]) is True


def test_firing_bar_is_excluded():
    # la penetracion ocurre SOLO en la vela de entrada (idx0); la ventana arranca
    # en idx1 -> NO debe contar como fill (modela una limite recien puesta).
    low = np.array([90, 100, 100, 100, 100, 100, 100, 100.0])
    high = np.full(8, 101.0)
    m = eng.maker_entry_fill_mask(_trades([(0, 100.0, eng.LONG)]), high, low,
                                  eps=EPS, ttl_bars=TTL)
    assert bool(m[0]) is False


def test_ttl_window_respected():
    low = np.array([100, 100, 100, 100, 100, 100, 100, 90.0])   # penetra en idx7
    high = np.full(8, 101.0)
    t = _trades([(0, 100.0, eng.LONG)])
    assert bool(eng.maker_entry_fill_mask(t, high, low, eps=EPS, ttl_bars=6)[0]) is False  # ventana [1..6]
    assert bool(eng.maker_entry_fill_mask(t, high, low, eps=EPS, ttl_bars=7)[0]) is True   # ventana [1..7]


def test_no_evaluable_bars_is_miss():
    # entrada en la ULTIMA vela: no hay velas siguientes -> MISS (conservador)
    low = np.array([100, 99.0])
    high = np.array([101, 101.0])
    m = eng.maker_entry_fill_mask(_trades([(1, 100.0, eng.LONG)]), high, low,
                                  eps=EPS, ttl_bars=TTL)
    assert bool(m[0]) is False


@pytest.mark.parametrize("low_seq,expected", [
    ([100, 100, 100, 99.0, 100, 100, 100, 100], True),    # fill en idx3
    ([100, 100, 100, 100, 100, 100, 100, 100], False),    # nunca penetra
])
def test_agrees_with_gold_paper_live_rule(low_seq, expected):
    """La mascara vectorizada (backtest) debe dar el MISMO veredicto que la regla
    viva por-vela gold_paper.process_maker_pending alimentada vela a vela."""
    gp = pytest.importorskip("gold_paper")
    low = np.array(low_seq, dtype=float)
    high = np.full(len(low), 101.0)
    E, d = 100.0, eng.LONG
    # regla viva: arma la pendiente y la alimenta desde la vela SIGUIENTE
    pend = [{"pid": 1, "direction": d, "limit": E, "waited": 0}]
    led = []
    for j in range(1, len(low)):
        pend = gp.process_maker_pending(pend, led, float(high[j]), float(low[j]),
                                        j, eps=EPS, ttl_bars=TTL)
        if not pend:
            break
    live_filled = any(e["event"] == "MAKER_FILL" for e in led)
    mask = eng.maker_entry_fill_mask(_trades([(0, E, d)]), high, low,
                                     eps=EPS, ttl_bars=TTL)
    assert bool(mask[0]) == live_filled == expected
