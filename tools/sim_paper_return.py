#!/usr/bin/env python3
"""sim_paper_return — ejercicio "¿qué hubiera rendido 10k en el bot los últimos 2 meses?".

HONESTO por diseño: corre sobre el cube (la simulación PAPER del motor, NO el ledger forward
real), aplica COSTOS estimados por trade, y separa bruto vs neto y la racha-de-la-ventana vs la
expectativa de por vida. El costo en R = costo%_ida_vuelta / distancia_del_stop% (un stop más
apretado paga MÁS fee por R) — por eso los costos importan tanto en este motor.

  python tools/sim_paper_return.py --self-test
  python tools/sim_paper_return.py --risk 0.004 --cost 0.10 --tp tp1 --horizon 96
"""
import argparse
import glob
import os
import re

import numpy as np
import pandas as pd

# Set REAL de broadcast VIP confirmado por RasDG (2026-06-30): SOL (pilar) + BTC/ETH/BCH/BNB.
# OJO: el CÓDIGO tiene FQ_LINK_VIP_BROADCAST default ON, pero en producción LINK NO se transmite
# (RasDG: "no conviene"; además no validado) -> NO incluir LINK. La config viva manda, no el default.
LIVE = os.environ.get("FQ_SIM_SYMBOLS",
                      "SOL_USDT BTC_USDT ETH_USDT BCH_USDT BNB_USDT").split()


def _window_trades(cube_dir, tp, horizon, days):
    cubes = {}
    for s in LIVE:
        p = os.path.join(cube_dir, "tp_cube_%s.parquet" % s)
        if os.path.exists(p):
            cubes[s] = pd.read_parquet(p)
    if not cubes:
        raise SystemExit("sin cubos live en %s" % cube_dir)
    mx = max(pd.to_datetime(c["entry_ts"]).max() for c in cubes.values())
    win0 = mx - pd.Timedelta(days=days)
    parts, life_n, life_win = [], 0, 0
    for s, c in cubes.items():
        d = c[(c["fired"] == True) & (c["tp"] == tp) & (c["horizon"] == horizon)].drop_duplicates("entry_index").copy()  # noqa: E712
        life_n += len(d); life_win += int((d["outcome"] == "win").sum())
        d["entry_ts"] = pd.to_datetime(d["entry_ts"])
        d = d[d["entry_ts"] >= win0]
        d["stop_pct"] = np.abs(d["entry_price"] - d["stop_price"]) / d["entry_price"] * 100
        parts.append(d[["entry_ts", "pnl_r", "outcome", "stop_pct"]])
    t = pd.concat(parts).sort_values("entry_ts").reset_index(drop=True)
    return t, mx, win0, (life_win / life_n * 100 if life_n else float("nan"))


def simulate(trades, *, risk=0.004, cost_pct=0.10, start=10000.0):
    """Compone `start` aplicando risk·R_neto por trade. R_neto = pnl_r − cost%/stop%."""
    cost_r = cost_pct / trades["stop_pct"].clip(lower=1e-6)
    net_r = trades["pnl_r"].to_numpy() - cost_r.to_numpy()
    bal = start; eq = [bal]; peak = bal; mdd = 0.0
    for r in net_r:
        bal *= (1 + risk * r); eq.append(bal); peak = max(peak, bal); mdd = min(mdd, (bal - peak) / peak)
    return {"final": bal, "ret_pct": (bal / start - 1) * 100, "mdd_pct": mdd * 100,
            "net_R_total": float(net_r.sum()), "gross_R_total": float(trades["pnl_r"].sum()),
            "cost_R_total": float(cost_r.sum()), "n": len(trades),
            "wr_win": (trades["outcome"] == "win").mean() * 100 if len(trades) else float("nan"),
            "equity": np.array(eq)}


def run(cube_dir, *, tp="tp1", horizon=96, days=60, risk=0.004, cost_pct=0.10):
    t, mx, win0, life_wr = _window_trades(cube_dir, tp, horizon, days)
    r = simulate(t, risk=risk, cost_pct=cost_pct)
    r.update({"tp": tp, "horizon": horizon, "win_to": str(mx.date()), "win_from": str(win0.date()),
              "life_wr": life_wr, "risk": risk, "cost_pct": cost_pct})
    return r, t


def _fmt(r):
    return (f"{r['tp']}/h{r['horizon']} · {r['win_from']}→{r['win_to']} · riesgo {r['risk']*100:.1f}%"
            f" · costo {r['cost_pct']:.2f}%/rt\n"
            f"  trades={r['n']}  WR_ventana={r['wr_win']:.0f}% (vida {r['life_wr']:.0f}%)\n"
            f"  R bruto {r['gross_R_total']:+.1f} − costo {r['cost_R_total']:.1f} = neto {r['net_R_total']:+.1f}\n"
            f"  saldo 10,000 → {r['final']:,.0f} MXN ({r['ret_pct']:+.0f}%)  maxDD {r['mdd_pct']:.0f}%")


def _self_test():
    import tempfile
    d = tempfile.mkdtemp()
    rng = np.random.default_rng(0)
    base = pd.Timestamp("2026-06-01")
    for s in LIVE:
        n = 200
        ts = [base + pd.Timedelta(hours=i) for i in range(n)]
        ep = 100 + rng.normal(0, 5, n)
        pd.DataFrame({"entry_index": range(n), "fired": True, "tp": "tp1", "horizon": 96,
                      "entry_ts": ts, "entry_price": ep, "stop_price": ep * 1.005,
                      "pnl_r": rng.choice([-1.0, 2.0], n), "outcome": rng.choice(["loss", "win"], n)}
                     ).to_parquet(os.path.join(d, "tp_cube_%s.parquet" % s), index=False)
    r, t = run(d, tp="tp1", horizon=96, days=60, risk=0.004, cost_pct=0.10)
    assert r["n"] > 0 and np.isfinite(r["final"]) and r["cost_R_total"] > 0
    assert abs(r["net_R_total"] - (r["gross_R_total"] - r["cost_R_total"])) < 1e-6
    print("self-test OK:\n" + _fmt(r))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--cube-dir", default="cosecha_cubes")
    p.add_argument("--tp", default="tp1"); p.add_argument("--horizon", type=int, default=96)
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--risk", type=float, default=0.004)
    p.add_argument("--cost", type=float, default=0.10, help="costo %% ida-vuelta del notional")
    a = p.parse_args(argv)
    if a.self_test:
        return _self_test()
    r, _ = run(a.cube_dir, tp=a.tp, horizon=a.horizon, days=a.days, risk=a.risk, cost_pct=a.cost)
    print(_fmt(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
