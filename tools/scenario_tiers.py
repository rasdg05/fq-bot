#!/usr/bin/env python3
"""scenario_tiers — Monte-Carlo de escenario por TIER (calidad vs premium),
multi-símbolo, con apalancamiento real y coste honesto.

Lee los JSON de measure_tiers (BTC/SOL/ETH), agrupa la serie-R del tier elegido,
y simula 2 semanas de operación:

  - cadencia 3-símbolos = suma de cadencias por símbolo
  - n_trades = cadencia × semanas
  - cada trade: equity *= (1 + risk_eff * (R - coste_R)),  bootstrap i.i.d.
  - apalancamiento REAL = risk_frac / stop%. Si excede el tope del exchange
    (25x), el tope LIMITA el tamaño -> risk_eff = min(risk_frac, 25*stop%).
  - coste_R: haircut round-trip (fees+slippage) en unidades de R (1R = el stop).

Reporta bandas de equity, P(verde), drawdown y cola de pérdida.

  python tools/scenario_tiers.py --tiers scratchpad/tiers_BTC.json scratchpad/tiers_SOL.json \
      scratchpad/tiers_ETH.json --tier premium --bankroll 1000 --weeks 2 \
      --risk 0.036 0.069 --max-lev 25 --cost-r 0.15
"""
import argparse
import json
import sys

import numpy as np


def load_tier(paths, tier):
    R, stops, cad, per = [], [], 0.0, {}
    for p in paths:
        d = json.load(open(p))
        t = d["tiers"].get(tier)
        if not t or t["n"] == 0:
            per[d["symbol"]] = {"n": 0, "cad": 0.0, "meanR": None}
            continue
        R += list(t["R"])
        stops += list(t.get("stops", [None] * t["n"]))
        cad += t["cadence_wk"] or 0.0
        per[d["symbol"]] = {"n": t["n"], "cad": t["cadence_wk"], "meanR": t["meanR"],
                            "WR": t["WR"], "stop_med": t.get("stop_pct_median")}
    return np.array(R, float), stops, cad, per


def simulate(R, stops, *, risk_frac, n_trades, bankroll=1000.0, max_lev=25.0,
             cost_r=0.15, n_paths=40000, seed=11):
    rng = np.random.default_rng(seed)
    R = np.asarray(R, float)
    # risk efectivo por trade segun stop% y tope de apalancamiento
    st = np.array([s if (s is not None) else np.nan for s in stops], float)
    med_stop = float(np.nanmedian(st)) if np.isfinite(st).any() else 0.005
    st = np.where(np.isfinite(st), st, med_stop)
    risk_cap = np.minimum(risk_frac, max_lev * st)          # por-trade
    capped_frac = float((max_lev * st < risk_frac).mean())
    netR = R - cost_r
    idx = rng.integers(0, R.size, size=(n_paths, n_trades))
    step = 1.0 + risk_cap[idx] * netR[idx]
    step = np.maximum(step, 1e-9)
    eq = np.cumprod(step, axis=1)
    eq = np.concatenate([np.ones((n_paths, 1)), eq], axis=1)
    final = eq[:, -1] * bankroll
    run_max = np.maximum.accumulate(eq, axis=1)
    max_dd = (1.0 - eq / run_max).max(axis=1)

    def q(a, p):
        return float(np.quantile(a, p))
    return {
        "n_trades": n_trades, "risk_frac": risk_frac,
        "real_lev_median": round(risk_frac / med_stop, 1),
        "stop_median_pct": round(100 * med_stop, 3),
        "capped_by_25x_frac": round(capped_frac, 3),
        "gross_meanR": round(float(R.mean()), 3), "net_meanR": round(float(netR.mean()), 3),
        "WR": round(float((R > 0).mean()), 3),
        "final_p10": round(q(final, .10)), "final_p25": round(q(final, .25)),
        "final_median": round(q(final, .50)), "final_mean": round(float(final.mean())),
        "final_p75": round(q(final, .75)), "final_p90": round(q(final, .90)),
        "P_green": round(float((final > bankroll).mean()), 3),
        "dd_median": round(float(np.median(max_dd)), 3), "dd_p95": round(q(max_dd, .95), 3),
        "P_lose_25": round(float((final < 0.75 * bankroll).mean()), 3),
        "P_lose_50": round(float((final < 0.50 * bankroll).mean()), 3),
    }


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--tiers", nargs="+", required=True)
    p.add_argument("--tier", required=True, choices=["base", "calidad", "cvd", "premium"])
    p.add_argument("--bankroll", type=float, default=1000.0)
    p.add_argument("--weeks", type=float, default=2.0)
    p.add_argument("--risk", nargs="+", type=float, default=[0.036, 0.069])
    p.add_argument("--max-lev", type=float, default=25.0)
    p.add_argument("--cost-r", type=float, default=0.15)
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)

    R, stops, cad3, per = load_tier(a.tiers, a.tier)
    n_trades = max(1, int(round(cad3 * a.weeks)))
    print("\n############  TIER = %s  ############" % a.tier.upper())
    print("cadencia 3-simbolos = %.2f/sem  ->  %d trades en %g sem   (pool n=%d, R global)" % (
        cad3, n_trades, a.weeks, R.size))
    for sym, m in per.items():
        if m["n"]:
            print("   %-4s n=%-4d  %.2f/sem  meanR=%+.3f  WR=%.0f%%  stop_med=%.2f%%" % (
                sym, m["n"], m["cad"], m["meanR"], 100 * m["WR"],
                100 * m["stop_med"] if m["stop_med"] else float("nan")))
        else:
            print("   %-4s n=0  (sin señales del tier en la ventana)" % sym)

    out = {"tier": a.tier, "cadence_3sym_wk": round(cad3, 2), "n_trades": n_trades,
           "weeks": a.weeks, "bankroll": a.bankroll, "pool_n": int(R.size), "runs": []}
    for rf in a.risk:
        rep = simulate(R, stops, risk_frac=rf, n_trades=n_trades, bankroll=a.bankroll,
                       max_lev=a.max_lev, cost_r=a.cost_r)
        out["runs"].append(rep)
        print("\n  --- riesgo %.1f%%/trade  (lev real ~%.1fx, tope %gx; %.0f%% trades topados) ---" % (
            100 * rf, rep["real_lev_median"], a.max_lev, 100 * rep["capped_by_25x_frac"]))
        print("    $%-5g -> mediana $%-6d  media $%-6d   (neto meanR=%+.3f, WR=%.0f%%)" % (
            a.bankroll, rep["final_median"], rep["final_mean"], rep["net_meanR"], 100 * rep["WR"]))
        print("    bandas:  p10 $%-5d  p25 $%-5d  p75 $%-5d  p90 $%-5d" % (
            rep["final_p10"], rep["final_p25"], rep["final_p75"], rep["final_p90"]))
        print("    P(verde)=%.0f%%   DD mediana=%.0f%% / p95=%.0f%%   P(pierde>25%%)=%.0f%%  P(pierde>50%%)=%.0f%%" % (
            100 * rep["P_green"], 100 * rep["dd_median"], 100 * rep["dd_p95"],
            100 * rep["P_lose_25"], 100 * rep["P_lose_50"]))
    if a.out:
        json.dump(out, open(a.out, "w"), indent=2)
        print("\n  -> %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
