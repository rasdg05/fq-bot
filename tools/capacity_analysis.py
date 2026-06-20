# -*- coding: utf-8 -*-
"""
Análisis de capacidad — paso N8.4 del ENGINEERING_PLAN.

¿Cuánto capital absorbe el edge antes de que el slippage se lo coma? El edge se
mide en R por-trade (sin coste de impacto). Al crecer el capital, cada orden es
más grande respecto a la liquidez disponible → más slippage → cada R rinde menos.
Este tool barre el capital y dibuja la curva de expectancy degradada, marcando:
  - C½  : capital donde el edge cae a la MITAD del bruto.
  - C0  : capital donde el edge se anula (techo absoluto).

Modelo (paramétrico, raíz cuadrada — el estándar de market impact):
  notional   = capital * risk_frac / stop_frac          (tamaño de posición)
  liquidez   = avg_bar_notional * fill_bars              (se reparte la orden)
  q          = notional / liquidez                       (participación)
  slip_bps   = impact_coef * q**impact_exp               (impact_exp=0.5)
  slip_R     = 2 * (slip_bps/1e4) / stop_frac            (entrada+salida)
  edge(C)    = mean_R - slip_R

CAVEAT honesto: `avg_bar_notional` e `impact_coef` son los inputs que mandan;
hay que CALIBRARLOS con volumen real y fills reales (el forward maker los dará).
El valor del tool es el marco + la SENSIBILIDAD, no un número mágico.

Uso:
  python tools/capacity_analysis.py --cube data/cosecha_SOL.parquet --tp tp4 \
      --label-horizon 288 --avg-bar-notional 3e6 --out-png cap_SOL.png
  python tools/capacity_analysis.py --ledger /data/motor_paper_BTC_USDT.jsonl \
      --avg-bar-notional 2e7
"""
import argparse
import json
import sys

import numpy as np


def capacity_curve(r_series, *, capitals=None, risk_frac=0.01, stop_frac=0.012,
                   avg_bar_notional=3e6, fill_bars=24, impact_coef=45.0,
                   impact_exp=0.5):
    """Curva de expectancy degradada vs capital + los puntos C½ y C0.

    r_series        : R por-trade (R-múltiplos, sin coste de impacto).
    capitals        : grilla de capital (USD). Default: log 1e3..1e8.
    risk_frac       : fracción de capital arriesgada por trade.
    stop_frac       : distancia del stop como fracción del precio.
    avg_bar_notional: notional (USD) negociado por barra (liquidez base).
    fill_bars       : barras en que se reparte la orden (ventana de fill).
    impact_coef     : slippage en bps a participación q=1 (a calibrar).
    impact_exp      : exponente del impacto (0.5 = raíz, el estándar).
    """
    rs = np.asarray([x for x in r_series if x is not None and np.isfinite(x)],
                    dtype=float)
    if rs.size < 2:
        raise ValueError("serie de R insuficiente (n<2)")
    mean_R = float(rs.mean())
    if capitals is None:
        capitals = np.logspace(3, 8, 60)          # 1k .. 100M
    capitals = np.asarray(capitals, dtype=float)
    liq = avg_bar_notional * fill_bars
    notional = capitals * risk_frac / stop_frac
    q = notional / liq
    slip_bps = impact_coef * np.power(q, impact_exp)
    slip_R = 2.0 * (slip_bps / 1e4) / stop_frac
    edge = mean_R - slip_R

    def _cross(target):
        """Menor capital donde edge(C) <= target (interp lineal). None si nunca."""
        below = np.where(edge <= target)[0]
        if below.size == 0:
            return None
        i = below[0]
        if i == 0:
            return float(capitals[0])
        x0, x1 = capitals[i - 1], capitals[i]
        y0, y1 = edge[i - 1], edge[i]
        if y1 == y0:
            return float(x1)
        return float(x0 + (target - y0) * (x1 - x0) / (y1 - y0))

    return {
        "n_trades": int(rs.size),
        "mean_R_gross": mean_R,
        "params": {"risk_frac": risk_frac, "stop_frac": stop_frac,
                   "avg_bar_notional": avg_bar_notional, "fill_bars": fill_bars,
                   "impact_coef": impact_coef, "impact_exp": impact_exp},
        "capital_half": _cross(mean_R * 0.5),     # C½
        "capital_zero": _cross(0.0),              # C0
        "curve": {"capital": capitals.tolist(),
                  "participation": q.tolist(),
                  "slip_bps": slip_bps.tolist(),
                  "edge_r": edge.tolist()},
    }


def _load_r(args):
    if args.rfile:
        return list(np.loadtxt(args.rfile, dtype=float).ravel())
    if args.ledger:
        from execution import DurableHashLedger
        import reconciler as rc
        return rc.extract_closed_r(DurableHashLedger.load(args.ledger))
    if args.cube:
        import pandas as pd
        df = pd.read_parquet(args.cube)
        if args.tp and "tp" in df.columns:
            df = df[df["tp"].astype(str) == str(args.tp)]
        if args.label_horizon is not None and "horizon" in df.columns:
            df = df[df["horizon"].astype(int) == int(args.label_horizon)]
        if args.col not in df.columns:
            raise SystemExit("col %r no está en el cubo" % args.col)
        rs = df[args.col].dropna().astype(float)
        if rs.empty:
            raise SystemExit("0 filas tras filtrar (--tp / --label-horizon)")
        return list(rs)
    raise SystemExit("dá una fuente: --cube / --ledger / --rfile")


def lamina(rep, path, *, title="Capacidad: expectancy vs capital"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cap = np.asarray(rep["curve"]["capital"])
    edge = np.asarray(rep["curve"]["edge_r"])
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(cap, edge, color="#2b6cb0", lw=2)
    ax.axhline(rep["mean_R_gross"], color="#999", ls=":", lw=1,
               label="edge bruto %.3fR" % rep["mean_R_gross"])
    ax.axhline(0.0, color="#d2453f", lw=1)
    for key, col, lab in (("capital_half", "#e0a93f", "C½"),
                          ("capital_zero", "#d2453f", "C0")):
        c = rep.get(key)
        if c:
            ax.axvline(c, color=col, ls="--", lw=1.4,
                       label="%s ≈ $%.0fk" % (lab, c / 1e3))
    ax.set_xscale("log")
    ax.set_xlabel("Capital desplegado (USD, log)")
    ax.set_ylabel("Expectancy por trade (R, neto de impacto)")
    ax.set_title(title)
    ax.legend(loc="lower left", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def _fmt(rep):
    ch = rep["capital_half"]
    cz = rep["capital_zero"]
    return "\n".join([
        "Capacidad — n=%d  edge bruto=%+.4fR" % (rep["n_trades"], rep["mean_R_gross"]),
        "  liquidez=%.1eUSD/bar × %d bars · impact=%.0fbps@q=1 (raíz)"
        % (rep["params"]["avg_bar_notional"], rep["params"]["fill_bars"],
           rep["params"]["impact_coef"]),
        "  C½ (edge a la mitad) ≈ %s" % ("$%.0fk" % (ch / 1e3) if ch else "n/a (no degrada en el rango)"),
        "  C0 (edge anulado)    ≈ %s" % ("$%.0fk" % (cz / 1e3) if cz else "n/a"),
    ])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Análisis de capacidad del edge")
    ap.add_argument("--cube"); ap.add_argument("--col", default="pnl_r")
    ap.add_argument("--tp", default=None)
    ap.add_argument("--label-horizon", type=int, default=None)
    ap.add_argument("--ledger"); ap.add_argument("--rfile")
    ap.add_argument("--risk-frac", type=float, default=0.01)
    ap.add_argument("--stop-frac", type=float, default=0.012)
    ap.add_argument("--avg-bar-notional", type=float, default=3e6,
                    help="USD negociados por barra (CALIBRAR con volumen real)")
    ap.add_argument("--fill-bars", type=int, default=24)
    ap.add_argument("--impact-coef", type=float, default=45.0,
                    help="slippage bps a participación=1 (CALIBRAR)")
    ap.add_argument("--out-json"); ap.add_argument("--out-png")
    args = ap.parse_args(argv)
    rs = _load_r(args)
    rep = capacity_curve(rs, risk_frac=args.risk_frac, stop_frac=args.stop_frac,
                         avg_bar_notional=args.avg_bar_notional,
                         fill_bars=args.fill_bars, impact_coef=args.impact_coef)
    print(_fmt(rep))
    if args.out_json:
        with open(args.out_json, "w") as fh:
            json.dump(rep, fh, indent=2)
        print("→ %s" % args.out_json)
    if args.out_png:
        lamina(rep, args.out_png)
        print("→ %s" % args.out_png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
