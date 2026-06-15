# -*- coding: utf-8 -*-
"""
Reporte walk-forward — paso N8.2 del ENGINEERING_PLAN.

El cubo ya trae folds walk-forward purgados (cosecha_shard --n-splits 7 --embargo
8). Este tool mide la expectancy OOS FOLD A FOLD y su dispersión: la evidencia de
que el edge es ESTABLE en el tiempo y NO un overfit a una ventana. Symbol-agnóstico
(corre igual sobre el cubo SOL o BTC).

Salida: tabla por fold (n, expectancy_r, WR) + resumen (media, desvío, % folds
positivos) + lámina deck.

Uso:
  python tools/walkforward_report.py --cube data/cosecha_BTC.parquet \
      --tp tp4 --label-horizon 288 --out-png wf_BTC.png
"""
import argparse
import json
import sys

import numpy as np
import pandas as pd

import bt_walkforward as wf
import bt_engine as eng
import bt_metrics as met


def load_cube(path, *, tp=None, label_horizon=None):
    df = pd.read_parquet(path)
    if tp is not None and "tp" in df.columns:
        df = df[df["tp"].astype(str) == str(tp)]
    if label_horizon is not None and "horizon" in df.columns:
        df = df[df["horizon"].astype(int) == int(label_horizon)]
    df = df.reset_index(drop=True)
    if df.empty:
        raise SystemExit("0 filas tras filtrar (--tp / --label-horizon)")
    return df


def run(df, *, n_splits=7, embargo=8, sim_kwargs=None, periods_per_year=None,
        min_train=1):
    """Métricas OOS por fold + resumen de estabilidad."""
    folds, valid_index = wf.folds_from_labeled(
        df, n_splits=n_splits, embargo=embargo, min_train=min_train)
    base = df.loc[valid_index].reset_index(drop=True)
    rows = []
    for k, (_tr, te) in enumerate(folds):
        sel = base.iloc[te]
        if "entry_index" in sel.columns:
            sel = sel.sort_values("entry_index")           # compounding cronológico
        if len(sel) == 0:
            rows.append({"fold": k, "n_trades": 0, "expectancy_r": None,
                         "win_rate": None, "total_r": 0.0})
            continue
        res = eng.simulate(sel, **(sim_kwargs or {}))
        m = met.metrics_from_result(res, periods_per_year=periods_per_year)
        rows.append({"fold": k, "n_trades": int(m.get("n_trades", 0)),
                     "expectancy_r": m.get("expectancy_r"),
                     "win_rate": m.get("win_rate"),
                     "total_r": m.get("total_r", 0.0)})
    rep = pd.DataFrame(rows)
    exps = rep["expectancy_r"].dropna().to_numpy(dtype=float)
    summary = {
        "n_folds": len(folds),
        "expectancy_mean": float(exps.mean()) if exps.size else None,
        "expectancy_std": float(exps.std(ddof=0)) if exps.size else None,
        "expectancy_min": float(exps.min()) if exps.size else None,
        "expectancy_max": float(exps.max()) if exps.size else None,
        "folds_positive": int((exps > 0).sum()),
        "folds_evaluated": int(exps.size),
    }
    return rep, summary


def lamina(rep, summary, path, *, title="Walk-forward OOS por fold"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    exp = rep["expectancy_r"].fillna(0.0).to_numpy(dtype=float)
    folds = rep["fold"].to_numpy()
    colors = ["#2e9e6b" if e > 0 else "#d2453f" for e in exp]
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.bar(folds, exp, color=colors)
    mu = summary.get("expectancy_mean")
    if mu is not None:
        ax.axhline(mu, color="#2b6cb0", ls="--", lw=1.5,
                   label="media OOS %.3fR" % mu)
    ax.axhline(0.0, color="#666", lw=1)
    ax.set_xlabel("fold walk-forward (cronológico)")
    ax.set_ylabel("expectancy_r OOS")
    pos = summary.get("folds_positive", 0)
    nf = summary.get("folds_evaluated", 0)
    ax.set_title("%s\n%d/%d folds positivos · desvío %s" % (
        title, pos, nf,
        ("%.3f" % summary["expectancy_std"]) if summary.get("expectancy_std") is not None else "n/a"))
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def _story(rep, summary):
    lines = ["Walk-forward OOS — %d/%d folds positivos, media=%s desvío=%s" % (
        summary.get("folds_positive", 0), summary.get("folds_evaluated", 0),
        ("%+.4f" % summary["expectancy_mean"]) if summary.get("expectancy_mean") is not None else "n/a",
        ("%.4f" % summary["expectancy_std"]) if summary.get("expectancy_std") is not None else "n/a")]
    for _, r in rep.iterrows():
        e = r["expectancy_r"]
        lines.append("  fold %d: n=%-4d expectancy_r=%s WR=%s" % (
            int(r["fold"]), int(r["n_trades"]),
            ("%+.4f" % e) if e is not None else "n/a",
            ("%.0f%%" % (r["win_rate"] * 100)) if r["win_rate"] is not None else "n/a"))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Reporte walk-forward OOS por fold")
    ap.add_argument("--cube", required=True)
    ap.add_argument("--tp", default=None)
    ap.add_argument("--label-horizon", type=int, default=None)
    ap.add_argument("--n-splits", type=int, default=7)
    ap.add_argument("--embargo", type=int, default=8)
    ap.add_argument("--out-json"); ap.add_argument("--out-png")
    args = ap.parse_args(argv)
    df = load_cube(args.cube, tp=args.tp, label_horizon=args.label_horizon)
    rep, summary = run(df, n_splits=args.n_splits, embargo=args.embargo)
    print(_story(rep, summary))
    if args.out_json:
        json.dump({"folds": rep.to_dict(orient="records"), "summary": summary},
                  open(args.out_json, "w"), indent=2)
        print("→ %s" % args.out_json)
    if args.out_png:
        lamina(rep, summary, args.out_png)
        print("→ %s" % args.out_png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
