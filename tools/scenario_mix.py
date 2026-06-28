#!/usr/bin/env python3
"""scenario_mix — Monte-Carlo de un PORTAFOLIO mixto (tier distinto por símbolo).

A diferencia de scenario_tiers (un solo tier para todos), aquí cada símbolo entra
con SU tier: p.ej. BTC/SOL/ETH en 'calidad' (KL-bajo) + BCH en 'base' (sin KL).
Agrupa la R de cada símbolo·tier, suma cadencias, y simula como siempre
(equity *= 1+risk_eff*(R−coste); tope 25x real por stop; bootstrap i.i.d.).

  python tools/scenario_mix.py \
    --leg BTC:calidad:scratch/tiersFULL_BTC.json --leg SOL:calidad:... \
    --leg ETH:calidad:... --leg BCH:base:scratch/tiersFULL_BCH.json \
    --risk 0.036 --weeks 2 --bankroll 1000
"""
import argparse
import json
import sys

import numpy as np

sys.path.insert(0, "tools")
import scenario_tiers as st  # noqa: E402


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--leg", action="append", required=True,
                   help="SYM:tier:path.json (repetir por símbolo)")
    p.add_argument("--bankroll", type=float, default=1000.0)
    p.add_argument("--weeks", type=float, default=2.0)
    p.add_argument("--risk", nargs="+", type=float, default=[0.036])
    p.add_argument("--cost-r", type=float, default=0.15)
    p.add_argument("--max-lev", type=float, default=25.0)
    p.add_argument("--label", default="MIX")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)

    R, stops, cad3, legs = [], [], 0.0, []
    for leg in a.leg:
        sym, tier, path = leg.split(":", 2)
        t = json.load(open(path))["tiers"][tier]
        R += list(t["R"])
        stops += list(t.get("stops", [None] * t["n"]))
        cad3 += t["cadence_wk"] or 0.0
        legs.append({"sym": sym, "tier": tier, "n": t["n"],
                     "cad": t["cadence_wk"], "meanR": t["meanR"]})
    R = np.array(R, float)
    n_trades = max(1, int(round(cad3 * a.weeks)))

    print("\n############  %s  ############" % a.label)
    for L in legs:
        print("   %-4s %-8s n=%-4d %.2f/sem  meanR=%+.3f" % (
            L["sym"], L["tier"], L["n"], L["cad"], L["meanR"]))
    print("   cadencia total = %.2f/sem -> %d trades en %g sem  (pool n=%d)" % (
        cad3, n_trades, a.weeks, R.size))

    out = {"label": a.label, "legs": legs, "cadence_wk": round(cad3, 2),
           "n_trades": n_trades, "weeks": a.weeks, "runs": []}
    for rf in a.risk:
        rep = st.simulate(R, stops, risk_frac=rf, n_trades=n_trades,
                          bankroll=a.bankroll, max_lev=a.max_lev, cost_r=a.cost_r)
        out["runs"].append(rep)
        print("\n  --- riesgo %.1f%%/trade (lev real ~%.1fx, tope %gx) ---" % (
            100 * rf, rep["real_lev_median"], a.max_lev))
        print("    $%-5g -> mediana $%-6d media $%-6d  (neto meanR=%+.3f, WR=%.0f%%)" % (
            a.bankroll, rep["final_median"], rep["final_mean"], rep["net_meanR"], 100 * rep["WR"]))
        print("    bandas: p10 $%-5d p25 $%-5d p75 $%-5d p90 $%-5d" % (
            rep["final_p10"], rep["final_p25"], rep["final_p75"], rep["final_p90"]))
        print("    P(verde)=%.0f%%  DD mediana=%.0f%%/p95=%.0f%%  P(pierde>25%%)=%.0f%% P(>50%%)=%.0f%%" % (
            100 * rep["P_green"], 100 * rep["dd_median"], 100 * rep["dd_p95"],
            100 * rep["P_lose_25"], 100 * rep["P_lose_50"]))
    if a.out:
        json.dump(out, open(a.out, "w"), indent=2)
        print("\n  -> %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
