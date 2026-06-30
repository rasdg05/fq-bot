# -*- coding: utf-8 -*-
"""Simulación PAPER de rendimiento: net_R = gross_R − costo, equity compuesta, costos por stop%."""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "tools")
import sim_paper_return as sp


def test_self_test():
    assert sp._self_test() == 0


def test_cost_reduces_net_and_compounding():
    rng = np.random.default_rng(1)
    n = 120
    ts = [pd.Timestamp("2026-06-01") + pd.Timedelta(hours=i) for i in range(n)]
    t = pd.DataFrame({"entry_ts": ts, "pnl_r": rng.choice([-1.0, 2.0], n),
                      "outcome": rng.choice(["loss", "win"], n),
                      "stop_pct": np.full(n, 0.5)})           # stop 0.5% -> costo 0.10/0.5 = 0.2R
    gross = sp.simulate(t, risk=0.004, cost_pct=0.0)
    net = sp.simulate(t, risk=0.004, cost_pct=0.10)
    # costo total = 0.2R * n ; neto = bruto - costo
    assert abs(net["cost_R_total"] - 0.2 * n) < 1e-6
    assert net["net_R_total"] < gross["net_R_total"]          # los costos restan
    assert net["final"] < gross["final"]                      # y bajan el saldo
