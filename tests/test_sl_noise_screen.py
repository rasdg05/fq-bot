# -*- coding: utf-8 -*-
"""Screen SL-vs-ruido: la distancia del stop vs el rango de una vela 5m, cross-símbolo."""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "tools")
import sl_noise_screen as sns


def test_self_test():
    assert sns._self_test() == 0


def test_bar_noise_and_stop_stats():
    # vela de rango ~1% del close -> noise ~1.0
    c = np.full(100, 100.0)
    kl = pd.DataFrame({"high": c * 1.005, "low": c * 0.995, "close": c})
    assert abs(sns.bar_noise_pct(kl) - 1.0) < 1e-6
    # stops a 0.5% -> mediana 0.5
    cube = pd.DataFrame({"entry_index": range(50), "fired": True,
                         "entry_price": np.full(50, 200.0), "stop_price": np.full(50, 201.0)})
    st = sns.stop_stats(cube)
    assert abs(st["stop_med"] - 0.5) < 1e-6 and st["n"] == 50
