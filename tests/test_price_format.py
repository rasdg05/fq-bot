# -*- coding: utf-8 -*-
"""Decimales dinámicos en las señales (fix bug DOGE: $0.07 = $0.07 = $0.07). Los pares
baratos (DOGE/TRX/ADA) deben mostrar entry/stop/TP DISTINTOS, no colapsados por %.2f."""
import types

import vip_format as vf


def test_px_decimales_por_magnitud():
    assert vf._px(62069.8) == "62,069.80"      # BTC: 2 dec
    assert vf._px(80.44) == "80.440"           # SOL: 3 dec
    assert vf._px(7.625) == "7.6250"           # LINK: 4 dec
    assert vf._px(0.0725) == "0.07250"         # DOGE: 5 dec
    assert vf._px(0.00031) == "0.0003100"      # micro: 7 dec


def test_px_defensivo():
    assert vf._px(None) == "None"              # jamás lanza


def _field():
    return types.SimpleNamespace(
        bias_aligned=True, pd_zone="discount", has_fuel=True, recent_sweep="low",
        pool_low=True, pool_high=False, confluence_count=4, node_type="colapso",
        pd_hierarchy="OTE", killzone="ny_am_kz")


def test_doge_free_precios_distintos():
    rep = {"direction": "short",
           "levels": {"entry": 0.0725, "sl": 0.0727, "risk": 0.0002,
                      "tp1": 0.0708, "rr_tp1": 2.9}}
    msg = vf.build_free_signal(rep, pair="DOGE/USDT")
    assert "$0.07250" in msg and "$0.07270" in msg and "$0.07080" in msg
    # los tres NO colapsan al mismo string
    assert msg.count("$0.07\n") == 0


def test_doge_vip_precios_distintos():
    rep = {"direction": "short", "p_master_data": {"p_master": 2.5},
           "levels": {"entry": 0.0725, "sl": 0.0727, "risk": 0.0002,
                      "tp1": 0.0708, "rr_tp1": 2.9, "tp2": 0.0695, "rr_tp2": 4.5,
                      "tp3": 0.0685, "rr_tp3": 6.0, "tp4": 0.0675, "rr_tp4": 8.0}}
    msg = vf.build_vip_signal(_field(), rep, pair="DOGE/USDT")
    for px in ("$0.07250", "$0.07270", "$0.07080", "$0.06950", "$0.06750"):
        assert px in msg
