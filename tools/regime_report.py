# -*- coding: utf-8 -*-
"""
Reporte de edge por régimen — paso N8.5 del ENGINEERING_PLAN.

Segmenta el cubo por una columna (régimen de mercado / volatilidad / sesión) y
mide la expectancy OOS POR SEGMENTO → dónde VIVE el alpha y dónde conviene
abstenerse. Numérica con muchos valores → bins por cuantiles; categórica → grupos.
Symbol-agnóstico (corre igual sobre el cubo SOL o BTC).

Uso:
  python tools/regime_report.py --cube data/cosecha_BTC.parquet --tp tp4 \
      --label-horizon 288 --by regime --out-png reg_BTC.png
  python tools/regime_report.py --cube c.parquet --by regime_score --qbins 5
"""
import argparse
import json
import sys

import numpy as np
import pandas as pd

import bt_engine as eng
import bt_metrics as met

_REGIME_CANDIDATES = ["regime", "regime_label", "regimen", "regime_state",
                      "regime_score"]


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


def detect_by(df, by=None):
    if by:
        if by not in df.columns:
            raise SystemExit("columna --by %r ausente. cols: %s"
                             % (by, list(df.columns)[:25]))
        return by
    for c in _REGIME_CANDIDATES:
        if c in df.columns:
            return c
    raise SystemExit("no encuentro columna de régimen (probé %s). Pasá --by COL. "
                     "cols: %s" % (_REGIME_CANDIDATES, list(df.columns)[:25]))


def _segments(series, qbins):
    """Numérica con muchos valores → bins por cuantiles; si no → categórica."""
    if pd.api.types.is_numeric_dtype(series) and series.nunique() > qbins:
        return pd.qcut(series, qbins, duplicates="drop").astype(str)
    return series.astype(str)


def run(df, by=None, *, sim_kwargs=None, periods_per_year=None, qbins=4):
    col = detect_by(df, by)
    df = df[df[col].notna()].reset_index(drop=True)
    seg = _segments(df[col], qbins)
    rows = []
    for g, idx in df.groupby(seg).groups.items():
        sel = df.loc[idx]
        if "entry_index" in sel.columns:
            sel = sel.sort_values("entry_index")
        if len(sel) == 0:
            continue
        res = eng.simulate(sel, **(sim_kwargs or {}))
        m = met.metrics_from_result(res, periods_per_year=periods_per_year)
        rows.append({"regime": str(g), "n_trades": int(m.get("n_trades", 0)),
                     "expectancy_r": m.get("expectancy_r"),
                     "win_rate": m.get("win_rate"),
                     "total_r": m.get("total_r", 0.0)})
    rep = pd.DataFrame(rows).sort_values(
        "expectancy_r", ascending=False, na_position="last").reset_index(drop=True)
    return rep, col


def lamina(rep, path, *, by="régimen", title=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    r = rep.iloc[::-1]                                  # mejor arriba en barh
    names = r["regime"].astype(str).tolist()
    exp = r["expectancy_r"].fillna(0.0).to_numpy(dtype=float)
    colors = ["#2e9e6b" if e > 0 else "#d2453f" for e in exp]
    fig, ax = plt.subplots(figsize=(10, 0.6 * max(len(names), 1) + 1.6), dpi=150)
    ax.barh(range(len(names)), exp, color=colors)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(["%s (n=%d)" % (n, int(v)) for n, v in
                        zip(names, r["n_trades"])])
    ax.axvline(0.0, color="#666", lw=1)
    ax.set_xlabel("expectancy_r OOS por segmento")
    ax.set_title(title or ("Edge por %s — dónde vive el alpha" % by))
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def _story(rep, col):
    lines = ["Edge por régimen (col=%s) — segmentos ordenados por expectancy:" % col]
    for _, r in rep.iterrows():
        e = r["expectancy_r"]
        lines.append("  %-22s n=%-4d expectancy_r=%s WR=%s" % (
            r["regime"][:22], int(r["n_trades"]),
            ("%+.4f" % e) if e is not None else "n/a",
            ("%.0f%%" % (r["win_rate"] * 100)) if r["win_rate"] is not None else "n/a"))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Reporte de edge por régimen")
    ap.add_argument("--cube", required=True)
    ap.add_argument("--tp", default=None)
    ap.add_argument("--label-horizon", type=int, default=None)
    ap.add_argument("--by", default=None, help="columna de segmentación (auto si se omite)")
    ap.add_argument("--qbins", type=int, default=4)
    ap.add_argument("--out-json"); ap.add_argument("--out-png")
    args = ap.parse_args(argv)
    df = load_cube(args.cube, tp=args.tp, label_horizon=args.label_horizon)
    rep, col = run(df, by=args.by, qbins=args.qbins)
    print(_story(rep, col))
    if args.out_json:
        json.dump(rep.to_dict(orient="records"), open(args.out_json, "w"), indent=2)
        print("→ %s" % args.out_json)
    if args.out_png:
        lamina(rep, args.out_png, by=col)
        print("→ %s" % args.out_png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
