#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COMPARA el diagnostico de retrieval entre simbolos (SOL vs BTC) y aplica el
criterio explicito de migracion del plan (RETRIEVAL_PLAN.md, §6.3).

Lee los JSON que produce run_research_real.py --retrieval-json y emite:
  - tabla comparativa con las MISMAS metricas OOS por simbolo,
  - veredicto de leakage por simbolo (placebo debe colapsar),
  - decision de migracion SOL->BTC segun umbrales.

Uso:
  python tools/compare_retrieval.py retrieval_SOL.json retrieval_BTC.json
"""
import argparse
import json
import sys

# Umbrales de migracion (RETRIEVAL_PLAN.md §6.3). Re-anclar tras F1.
MIN_EXPECTANCY_R = 0.05     # expectancy neta minima del gate_pass en BTC
MIN_PF = 1.3                # profit factor minimo en BTC
MIN_N_DENSITY = 25          # mediana de vecinos (proxy: n gate_pass suficiente)
MAX_ABSTAIN_FRAC = 0.30     # fraccion de abstencion maxima


def _load(path):
    with open(path) as fh:
        return json.load(fh)


def _g(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


def _fmt(v):
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.4f}"
    except (TypeError, ValueError):
        return str(v)


def summarize(payload):
    abl = payload.get("ablation", {})
    gp = abl.get("gate_pass", {})
    base = abl.get("base", {})
    abst = abl.get("abstained", {})
    n_total = base.get("n", 0) or 0
    n_abst = abst.get("n", 0) or 0
    return {
        "symbol": payload.get("symbol"),
        "edge_causal_r": payload.get("edge_causal_r"),
        "edge_placebo_r": payload.get("edge_placebo_r"),
        "edge_oracle_r": payload.get("edge_oracle_r"),
        "leakage_verdict": payload.get("leakage_verdict"),
        "gate_expectancy_r": gp.get("expectancy_r"),
        "gate_pf": gp.get("pf"),
        "gate_n": gp.get("n"),
        "gate_wr": gp.get("wr"),
        "base_expectancy_r": base.get("expectancy_r"),
        "abstain_frac": (n_abst / n_total) if n_total else None,
    }


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def migration_decision(sol, btc):
    """Aplica el criterio §6.3. Devuelve (decision:str, checks:list)."""
    checks = []

    def chk(name, ok, detail):
        checks.append((name, bool(ok), detail))
        return bool(ok)

    btc_exp = _num(btc["gate_expectancy_r"])
    sol_exp = _num(sol["gate_expectancy_r"])
    btc_pf = _num(btc["gate_pf"])
    btc_edge = _num(btc["edge_causal_r"])
    btc_pl = _num(btc["edge_placebo_r"])

    c1 = chk("edge_neto",
             btc_exp is not None and sol_exp is not None
             and btc_exp >= max(sol_exp, MIN_EXPECTANCY_R)
             and btc_pf is not None and btc_pf >= MIN_PF,
             f"BTC exp_r={_fmt(btc_exp)} >= max(SOL {_fmt(sol_exp)}, {MIN_EXPECTANCY_R}) y PF={_fmt(btc_pf)}>={MIN_PF}")
    c2 = chk("lift_atribuible",
             btc_edge is not None and btc_edge > 0,
             f"edge causal BTC={_fmt(btc_edge)} > 0")
    c3 = chk("densidad_fiable",
             (btc["gate_n"] or 0) >= MIN_N_DENSITY
             and (btc["abstain_frac"] is None or btc["abstain_frac"] < MAX_ABSTAIN_FRAC),
             f"gate_n={btc['gate_n']}>={MIN_N_DENSITY}, abstain={_fmt(btc['abstain_frac'])}<{MAX_ABSTAIN_FRAC}")
    c4 = chk("sin_leakage",
             btc.get("leakage_verdict") == "OK"
             and (btc_pl is None or btc_edge is None or abs(btc_pl) < abs(btc_edge)),
             f"veredicto={btc.get('leakage_verdict')}, placebo={_fmt(btc_pl)} colapsa vs causal {_fmt(btc_edge)}")

    if all([c1, c2, c3, c4]):
        decision = "MIGRAR a BTC (cumple los 4 criterios §6.3)"
    elif c2 and c1 and not c3:
        decision = "NO migrar todavia: edge existe pero densidad insuficiente -> seguir ingiriendo"
    else:
        decision = "NO migrar: no se cumplen los criterios de §6.3"
    return decision, checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sol_json", help="JSON de retrieval de SOL")
    ap.add_argument("btc_json", help="JSON de retrieval de BTC")
    args = ap.parse_args()

    sol = summarize(_load(args.sol_json))
    btc = summarize(_load(args.btc_json))

    print("=" * 72)
    print("  COMPARATIVA RETRIEVAL — SOL vs BTC (F1, read-only)")
    print("=" * 72)
    rows = [
        ("symbol", "symbol"),
        ("base exp_r", "base_expectancy_r"),
        ("gate_pass exp_r", "gate_expectancy_r"),
        ("gate_pass WR", "gate_wr"),
        ("gate_pass PF", "gate_pf"),
        ("gate_pass n", "gate_n"),
        ("edge causal R", "edge_causal_r"),
        ("edge placebo R", "edge_placebo_r"),
        ("edge oracle R", "edge_oracle_r"),
        ("abstain frac", "abstain_frac"),
        ("leakage", "leakage_verdict"),
    ]
    print(f"  {'metric':<18} {'SOL':>14} {'BTC':>14}")
    print("  " + "-" * 48)
    for label, key in rows:
        print(f"  {label:<18} {_fmt(sol[key]) if key!='symbol' else str(sol[key]):>14} "
              f"{_fmt(btc[key]) if key!='symbol' else str(btc[key]):>14}")

    print("\n  Criterio de migracion SOL->BTC (§6.3):")
    decision, checks = migration_decision(sol, btc)
    for name, ok, detail in checks:
        print(f"   [{'PASS' if ok else 'FAIL'}] {name:<18} {detail}")
    print(f"\n  >> DECISION: {decision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
