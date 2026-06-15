# -*- coding: utf-8 -*-
"""
Atribución de módulos (lámina) — paso N8.6 del ENGINEERING_PLAN.

Envuelve `bt_ablation.run_ablation` —que ya mide, módulo por módulo y SOLO en el
test OOS walk-forward con costes reales, si cada componente del motor aporta
expectancy o es peso muerto— en un REPORTE + lámina para el deck. Vuelve la
'caja' del motor TRANSPARENTE: qué genera el alpha, ranqueado, con veredicto
VIVE/MATAR.

Requiere que el cubo traiga, además de las columnas del engine
(entry_price/stop_price/exit_price/direction/bars_held/pnl_r), las COLUMNAS-GATE
por módulo (booleanas; True = el módulo deja pasar el evento). Convención de
nombres de gate: sufijo _gate/_ok/_pass/_flag, o se listan con --modules /
--modules-json. Si el cubo no las trae, re-cosecha guardándolas (alternativa:
ablación por replay con toggles de env en run_research_real).

Uso:
  python tools/attribution_report.py --cube data/cosecha_SOL.parquet \
      --tp tp4 --label-horizon 288 --out-json attr_SOL.json --out-png attr_SOL.png
  python tools/attribution_report.py --cube c.parquet --modules sb_gate,regime_gate
"""
import argparse
import json
import re
import sys

import numpy as np
import pandas as pd

import bt_walkforward as wf
import bt_ablation as ab

_GATE_RE = re.compile(r"(_gate|_ok|_pass|_flag)$", re.I)
_EXCLUDE = {"outcome", "win", "is_win", "loss", "timeout", "direction"}


def detect_modules(df, names=None):
    """Dict {modulo: mask_fn(df)->bool[]} desde columnas-gate del cubo.

    names: lista explícita de columnas-gate. Default: autodetecta por sufijo.
    """
    if names:
        miss = [c for c in names if c not in df.columns]
        if miss:
            raise SystemExit("columnas-gate ausentes en el cubo: %s" % miss)
        cols = list(names)
    else:
        cols = [c for c in df.columns
                if _GATE_RE.search(str(c)) and str(c).lower() not in _EXCLUDE]
    if not cols:
        raise SystemExit(
            "no hay columnas-gate (sufijo _gate/_ok/_pass/_flag) en el cubo. "
            "Da --modules col1,col2 o --modules-json, o re-cosecha guardándolas.")
    # col=c por-default evita el late-binding del closure en el loop
    return {str(c): (lambda d, col=c: np.asarray(d[col]).astype(bool)) for c in cols}


def load_cube(path, *, tp=None, label_horizon=None):
    """Carga el cubo y lo filtra a UN (tp,horizonte). El cubo es long (1 fila por
    evento×tp×horizonte) y la ablación pool-ea eventos → sin filtrar, duplica."""
    df = pd.read_parquet(path)
    if tp is not None and "tp" in df.columns:
        df = df[df["tp"].astype(str) == str(tp)]
    if label_horizon is not None and "horizon" in df.columns:
        df = df[df["horizon"].astype(int) == int(label_horizon)]
    df = df.reset_index(drop=True)
    if df.empty:
        raise SystemExit("0 filas tras filtrar (revisa --tp / --label-horizon)")
    return df


def run(df, *, n_splits=7, embargo=8, names=None, modules=None, sim_kwargs=None,
        metric="expectancy_r", margin=0.0, min_train=1):
    """Folds walk-forward + ablación → DataFrame-reporte (y el dict de módulos)."""
    folds, valid_index = wf.folds_from_labeled(
        df, n_splits=n_splits, embargo=embargo, min_train=min_train)
    mods = modules or detect_modules(df, names=names)
    report = ab.run_ablation(df, folds, mods, valid_index=valid_index,
                             sim_kwargs=sim_kwargs, metric=metric, margin=margin)
    return report, mods


def lamina(report, path, *, metric="expectancy_r",
           title="Atribución de módulos (OOS walk-forward, costes reales)"):
    """Lámina deck: barra horizontal del Δmetric por módulo, verde=VIVE/rojo=MATAR."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    mod = report[report["is_module"]].copy()
    mod = mod.sort_values("delta_vs_baseline", na_position="first")
    names = [str(v).replace("sin_", "") for v in mod["variant"]]
    deltas = mod["delta_vs_baseline"].fillna(0.0).to_numpy(dtype=float)
    surv = mod["survives"].fillna(False).to_numpy()
    colors = ["#2e9e6b" if s else "#d2453f" for s in surv]
    fig, ax = plt.subplots(figsize=(10, 0.6 * max(len(names), 1) + 1.6), dpi=150)
    ax.barh(range(len(names)), deltas, color=colors)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.axvline(0.0, color="#666", lw=1)
    ax.set_xlabel("Δ %s al quitar el módulo  (>0 = el módulo APORTA)" % metric)
    base = report[report["variant"] == "baseline"]
    bm = base.iloc[0][metric] if len(base) else None
    ax.set_title("%s\nbaseline %s = %s   ·   verde = VIVE   rojo = MATAR"
                 % (title, metric, ("%.4f" % bm) if bm is not None else "n/a"))
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Atribución de módulos (lámina deck)")
    ap.add_argument("--cube", required=True, help="parquet del cubo cosecha")
    ap.add_argument("--tp", default=None, help="filtra a un nivel TP (p.ej. tp4)")
    ap.add_argument("--label-horizon", type=int, default=None,
                    help="filtra a un horizonte de label (p.ej. 288)")
    ap.add_argument("--modules", default=None,
                    help="columnas-gate (coma). Default: autodetecta por sufijo")
    ap.add_argument("--modules-json", default=None,
                    help="JSON {modulo: columna-gate} explícito")
    ap.add_argument("--n-splits", type=int, default=7)
    ap.add_argument("--embargo", type=int, default=8)
    ap.add_argument("--metric", default="expectancy_r",
                    choices=["expectancy_r", "sharpe"])
    ap.add_argument("--margin", type=float, default=0.0)
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--out-png", default=None)
    args = ap.parse_args(argv)

    df = load_cube(args.cube, tp=args.tp, label_horizon=args.label_horizon)
    names, modules = None, None
    if args.modules_json:
        spec = json.load(open(args.modules_json))
        modules = {k: (lambda d, col=v: np.asarray(d[col]).astype(bool))
                   for k, v in spec.items()}
    elif args.modules:
        names = [c.strip() for c in args.modules.split(",") if c.strip()]

    report, mods = run(df, n_splits=args.n_splits, embargo=args.embargo,
                       names=names, modules=modules, metric=args.metric,
                       margin=args.margin)
    print(ab.attribution_story(report, metric=args.metric))
    print("\nmódulos evaluados: %s" % ", ".join(mods.keys()))
    if args.out_json:
        report.to_json(args.out_json, orient="records", indent=2)
        print("→ %s" % args.out_json)
    if args.out_png:
        lamina(report, args.out_png, metric=args.metric)
        print("→ %s" % args.out_png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
