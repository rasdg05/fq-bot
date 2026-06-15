# -*- coding: utf-8 -*-
"""
Monte Carlo de la curva de equity — paso N8.3 del ENGINEERING_PLAN.

Una sola realización histórica esconde la DISTRIBUCIÓN de desenlaces. Este tool
toma la serie de R por-trade (de un cubo cosecha parquet, un ledger motor/ORO, o
un texto) y por bootstrap (remuestreo con reemplazo) estima:
  - drawdown máximo (p50 / p95 / p99)
  - risk-of-ruin a un umbral de drawdown
  - bandas de equity final (p5 / p50 / p95) a horizonte N trades
  - probabilidad de cerrar en ganancia

Modelo de equity: riesgo fraccional fijo por trade (Kelly-fraccional simple),
equity *= (1 + risk_frac * R_i), componiendo. Bootstrap i.i.d. sobre los trades
(NO captura clustering de rachas; un block-bootstrap es la mejora futura — se
declara por honestidad). Sin red, determinista por --seed.

Uso:
  python tools/montecarlo_curve.py --cube data/cosecha_SOL.parquet --col pnl_r
  python tools/montecarlo_curve.py --ledger /data/motor_paper_BTC_USDT.jsonl
  python tools/montecarlo_curve.py --rfile rs.txt --paths 20000 --horizon 500 \
         --risk-frac 0.01 --ruin-dd 0.5 --seed 42 --out mc_SOL.json
"""
import argparse
import json
import sys

import numpy as np


def simulate(r_series, *, n_paths=10000, horizon=None, risk_frac=0.01,
             ruin_dd=0.5, seed=42):
    """Monte Carlo sobre una serie de R por-trade (lista de R-múltiplos).

    r_series   : iterable de R por trade (los None/NaN se descartan).
    n_paths    : caminos simulados.
    horizon    : trades por camino (default = tamaño de la serie histórica).
    risk_frac  : fracción del equity arriesgada por trade (0.01 = 1%).
    ruin_dd    : umbral de drawdown que cuenta como "ruina" (0.5 = -50%).
    seed       : semilla (reproducible).

    Devuelve un dict de estadísticos (drawdowns, risk-of-ruin, bandas).
    """
    rs = np.asarray([x for x in r_series if x is not None and np.isfinite(x)],
                    dtype=float)
    if rs.size < 2:
        raise ValueError("serie de R insuficiente (n<2)")
    rng = np.random.default_rng(seed)
    H = int(horizon or rs.size)
    # bootstrap: (n_paths, H) índices con reemplazo sobre la serie histórica
    draws = rng.integers(0, rs.size, size=(n_paths, H))
    sampled = rs[draws]                                  # R por trade
    step = np.maximum(1.0 + risk_frac * sampled, 1e-9)   # factor por trade (piso)
    eq = np.exp(np.cumsum(np.log(step), axis=1))         # log-equity (estable)
    eq = np.concatenate([np.ones((n_paths, 1)), eq], axis=1)  # base 1.0
    run_max = np.maximum.accumulate(eq, axis=1)
    max_dd = (1.0 - eq / run_max).max(axis=1)            # peor DD por camino
    final = eq[:, -1]                                    # equity final por camino

    def q(a, p):
        return float(np.quantile(a, p))

    return {
        "n_trades_hist": int(rs.size),
        "mean_R": float(rs.mean()),
        "wr": float((rs > 0).mean()),
        "paths": int(n_paths),
        "horizon": H,
        "risk_frac": float(risk_frac),
        "ruin_dd": float(ruin_dd),
        "seed": int(seed),
        "max_dd_p50": q(max_dd, 0.50),
        "max_dd_p95": q(max_dd, 0.95),
        "max_dd_p99": q(max_dd, 0.99),
        "risk_of_ruin": float((max_dd >= ruin_dd).mean()),
        "equity_p05": q(final, 0.05),
        "equity_p50": q(final, 0.50),
        "equity_p95": q(final, 0.95),
        "prob_profit": float((final > 1.0).mean()),
    }


def _load_r(args):
    """Carga la serie de R desde --cube (parquet), --ledger (jsonl) o --rfile."""
    if args.rfile:
        return list(np.loadtxt(args.rfile, dtype=float).ravel())
    if args.ledger:
        from execution import DurableHashLedger     # lazy: evita deps en test
        import reconciler as rc
        return rc.extract_closed_r(DurableHashLedger.load(args.ledger))
    if args.cube:
        import pandas as pd                          # lazy: parquet sólo en runner
        df = pd.read_parquet(args.cube)
        if args.col not in df.columns:
            raise SystemExit("col %r no está en el cubo (cols: %s)"
                             % (args.col, list(df.columns)[:20]))
        return list(df[args.col].dropna().astype(float))
    raise SystemExit("dá una fuente: --cube / --ledger / --rfile")


def _fmt(rep):
    return "\n".join([
        "Monte Carlo de la curva — n_hist=%d  mean_R=%+.4f  WR=%.1f%%"
        % (rep["n_trades_hist"], rep["mean_R"], rep["wr"] * 100.0),
        "  caminos=%d  horizonte=%d  riesgo/trade=%.2f%%"
        % (rep["paths"], rep["horizon"], rep["risk_frac"] * 100.0),
        "  drawdown máx: p50=%.1f%%  p95=%.1f%%  p99=%.1f%%"
        % (rep["max_dd_p50"] * 100, rep["max_dd_p95"] * 100, rep["max_dd_p99"] * 100),
        "  risk-of-ruin(@-%.0f%%)=%.2f%%   prob. ganancia=%.1f%%"
        % (rep["ruin_dd"] * 100, rep["risk_of_ruin"] * 100, rep["prob_profit"] * 100),
        "  equity final: p05=%.2fx  p50=%.2fx  p95=%.2fx"
        % (rep["equity_p05"], rep["equity_p50"], rep["equity_p95"]),
    ])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Monte Carlo de la curva de equity")
    src = ap.add_argument_group("fuente de R (una)")
    src.add_argument("--cube", help="parquet del cubo cosecha")
    src.add_argument("--col", default="pnl_r", help="columna de R en el cubo")
    src.add_argument("--ledger", help="ledger jsonl (motor/ORO paper)")
    src.add_argument("--rfile", help="texto con una R por línea")
    ap.add_argument("--paths", type=int, default=10000)
    ap.add_argument("--horizon", type=int, default=None)
    ap.add_argument("--risk-frac", type=float, default=0.01)
    ap.add_argument("--ruin-dd", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", help="vuelca el dict a JSON")
    args = ap.parse_args(argv)
    rs = _load_r(args)
    rep = simulate(rs, n_paths=args.paths, horizon=args.horizon,
                   risk_frac=args.risk_frac, ruin_dd=args.ruin_dd, seed=args.seed)
    print(_fmt(rep))
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(rep, fh, indent=2)
        print("→ %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
