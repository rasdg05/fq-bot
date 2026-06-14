# -*- coding: utf-8 -*-
"""
F3 — SELECTOR de TP/horizonte por vecindario (RETRIEVAL_PLAN §3.2 / roadmap F3).

Para cada señal, usa el cubo persistido (entry × tp × horizonte -> pnl_r + las
features del motor) para ELEGIR el (tp, horizonte) que pagó en estados similares
(k-NN causal, walk-forward), en vez de un TP1/horizonte FIJO. Compara la cartera
del selector contra la baseline fija, out-of-sample. Symbol-agnóstico; reusa el
vectorizador causal de bt_retrieval y los folds purgados de bt_walkforward.

Causalidad: por fold se ajusta el vectorizador SOLO con el train; el train se
purga+embarga (un evento del train entra solo si su desenlace —tras el horizonte
MÁS LARGO— cerró antes del inicio del test). El selector ABSTIENE (cae a la
baseline) si el vecindario no permite estimar una celda -> la comparación es
sobre la MISMA población.

GATE (§6.6): necesita ≥~1000 eventos para que el vecindario k=50 sea estimable.
Con menos, es DIAGNÓSTICO de bajo poder (radar), NO veredicto.
"""
import numpy as np
import pandas as pd

import bt_retrieval as btr
import bt_walkforward as wf


def events_and_cells(cube, baseline=("tp1", 288)):
    """Pivotea el cubo largo a: events (1 row/evento con features, ordenado por
    entry_index), cell_pnl (n_events × n_cells), cells [(tp,horizon)...], y
    base_pnl (pnl_r de la celda baseline por evento)."""
    cube = cube.copy()
    cube["horizon"] = cube["horizon"].astype(int)
    cube["_cell"] = list(zip(cube["tp"].astype(str), cube["horizon"]))
    cells = sorted(set(cube["_cell"]), key=lambda c: (c[0], c[1]))
    col_of = {c: j for j, c in enumerate(cells)}
    ev = (cube.sort_values("entry_index")
          .drop_duplicates("entry_index").reset_index(drop=True))
    idx_of = {int(e): i for i, e in enumerate(ev["entry_index"].to_numpy())}
    cell_pnl = np.full((len(ev), len(cells)), np.nan, dtype="float64")
    for ei, c, r in zip(cube["entry_index"], cube["_cell"], cube["pnl_r"]):
        i = idx_of.get(int(ei))
        if i is not None and pd.notna(r):
            cell_pnl[i, col_of[c]] = float(r)
    bcol = col_of.get((str(baseline[0]), int(baseline[1])))
    base_pnl = (cell_pnl[:, bcol].copy() if bcol is not None
                else cell_pnl[:, 0].copy())
    return ev, cell_pnl, cells, base_pnl


def _folds(ev, cells, n_splits, embargo):
    """Folds purgados sobre los eventos; t1 = entry + horizonte MÁS LARGO
    (cota causal conservadora: el evento resolvió todas sus celdas)."""
    hmax = max(h for _t, h in cells) if cells else 0
    t0 = ev["entry_index"].to_numpy("float64")
    return wf.purged_walk_forward_splits(t0, t0 + float(hmax), n_splits, embargo)


def select_oos(ev, cell_pnl, base_pnl, cells, folds, *, base_col=0,
               vectorizer=None, k=50, min_neighbors=10, margin=0.1,
               min_support=20):
    """Walk-forward causal con GATE DE CONFIANZA. Por cada evento de test
    recupera los k vecinos del train y, por celda, estima expectancy + soporte.
    Solo SE DESVÍA de la baseline si el mejor cell supera al baseline DEL
    VECINDARIO por >= `margin` Y tiene >= `min_support` vecinos que lo
    resolvieron; si no, ABSTIENE a baseline (misma población). Devuelve un
    DataFrame OOS (entry_index, sel_pnl, base_pnl, sel_cell, abstain)."""
    vz0 = vectorizer or btr.StateVectorizer(
        numeric=btr.DEFAULT_NUMERIC, categorical=btr.DEFAULT_CATEGORICAL)
    rows = []
    for tr_idx, te_idx in folds:
        if len(tr_idx) < min_neighbors:
            continue
        vz = btr.StateVectorizer(numeric=vz0.numeric, categorical=vz0.categorical,
                                 cat_scale=vz0.cat_scale)
        vz.fit(ev.iloc[tr_idx])
        Vtr = vz.transform(ev.iloc[tr_idx])
        Vte = vz.transform(ev.iloc[te_idx])
        tr_cells = cell_pnl[tr_idx]
        kk = int(min(k, len(tr_idx)))
        for r, te in enumerate(te_idx):
            base = base_pnl[te]
            if not np.isfinite(base):
                continue  # sin baseline -> fuera de la comparación
            sims = Vtr @ Vte[r]
            nn = (np.argpartition(-sims, kk - 1)[:kk] if kk < len(sims)
                  else np.arange(len(sims)))
            nb = tr_cells[nn]                      # (kk, ncells)
            with np.errstate(invalid="ignore", all="ignore"):
                cell_exp = np.nanmean(nb, axis=0)
                support = np.isfinite(nb).sum(axis=0)
            sel_cell, sel = None, float(base)     # default: ABSTIENE a baseline
            base_nb = cell_exp[base_col]
            if np.any(np.isfinite(cell_exp)) and np.isfinite(base_nb):
                bc = int(np.nanargmax(np.where(np.isfinite(cell_exp),
                                               cell_exp, -np.inf)))
                # GATE: deviar solo si confiadamente mejor que la baseline.
                if (bc != base_col and (cell_exp[bc] - base_nb) >= margin
                        and support[bc] >= min_support):
                    v = cell_pnl[te, bc]
                    if np.isfinite(v):
                        sel_cell, sel = cells[bc], float(v)
            rows.append({"entry_index": int(ev["entry_index"].iloc[te]),
                         "sel_pnl": sel, "base_pnl": float(base),
                         "sel_cell": sel_cell, "abstain": sel_cell is None})
    return pd.DataFrame(rows)


def evaluate(sel_df):
    """Compara cartera del selector vs baseline fija (OOS pooled)."""
    if len(sel_df) == 0:
        return {"n": 0}
    s = sel_df["sel_pnl"].to_numpy()
    b = sel_df["base_pnl"].to_numpy()

    def _e(x):
        return {"n": int(len(x)), "expectancy_r": float(np.mean(x)),
                "wr": float(np.mean(x > 0)), "total_r": float(np.sum(x))}
    dist = (sel_df[~sel_df["abstain"]]["sel_cell"].astype(str)
            .value_counts().to_dict())
    return {"selector": _e(s), "baseline": _e(b),
            "lift_r": float(np.mean(s) - np.mean(b)),
            "abstain_rate": float(np.mean(sel_df["abstain"].to_numpy())),
            "cell_dist": {str(kk): int(v) for kk, v in dist.items()}}


def _base_col(cells, baseline):
    key = (str(baseline[0]), int(baseline[1]))
    return cells.index(key) if key in cells else 0


def run(cube, *, n_splits=7, embargo=8, k=50, baseline=("tp1", 288),
        vectorizer=None, min_neighbors=10, margin=0.1, min_support=20):
    """Tubería completa sobre un cubo: pivota, foldea causal, selecciona (con
    gate de confianza), evalúa. Devuelve (sel_df, report)."""
    ev, cell_pnl, cells, base_pnl = events_and_cells(cube, baseline)
    folds = _folds(ev, cells, n_splits, embargo)
    sel = select_oos(ev, cell_pnl, base_pnl, cells, folds,
                     base_col=_base_col(cells, baseline), vectorizer=vectorizer,
                     k=k, min_neighbors=min_neighbors, margin=margin,
                     min_support=min_support)
    return sel, evaluate(sel)


def sweep(cube, *, ks=(25, 50, 75), margins=(0.0, 0.05, 0.1, 0.2),
          n_splits=7, embargo=8, baseline=("tp1", 288), min_support=20):
    """Barrido de calibración (k × margin) -> tabla de lift OOS. Para elegir la
    config de F3 sin re-correr CI (segundos locales sobre el cubo)."""
    ev, cell_pnl, cells, base_pnl = events_and_cells(cube, baseline)
    base_col = _base_col(cells, baseline)
    folds = _folds(ev, cells, n_splits, embargo)
    out = []
    for k in ks:
        for m in margins:
            rep = evaluate(select_oos(
                ev, cell_pnl, base_pnl, cells, folds, base_col=base_col,
                k=k, margin=m, min_support=min_support))
            if "selector" not in rep:
                out.append({"k": k, "margin": m, "n": 0}); continue
            out.append({"k": k, "margin": m, "n": rep["selector"]["n"],
                        "base_exp": round(rep["baseline"]["expectancy_r"], 4),
                        "sel_exp": round(rep["selector"]["expectancy_r"], 4),
                        "lift_r": round(rep["lift_r"], 4),
                        "abstain": round(rep["abstain_rate"], 3)})
    return pd.DataFrame(out)


def main(argv):
    import argparse
    p = argparse.ArgumentParser(description="F3 selector TP/horizonte (diagnóstico).")
    p.add_argument("cube", help="tp_cube_<sym>.parquet de un run")
    p.add_argument("--k", type=int, default=50)
    p.add_argument("--n-splits", type=int, default=7)
    p.add_argument("--embargo", type=int, default=8)
    p.add_argument("--baseline-tp", default="tp1")
    p.add_argument("--baseline-h", type=int, default=288)
    p.add_argument("--margin", type=float, default=0.1,
                   help="gate de confianza: deviar solo si el mejor cell supera "
                        "al baseline del vecindario por >= margin (R)")
    p.add_argument("--min-support", type=int, default=20,
                   help="vecinos minimos que resolvieron la celda para elegirla")
    p.add_argument("--sweep", action="store_true",
                   help="barrido de calibracion (k x margin) en vez del run unico")
    a = p.parse_args(argv)
    cube = pd.read_parquet(a.cube)
    n_ev = cube["entry_index"].nunique()
    if a.sweep:
        tbl = sweep(cube, n_splits=a.n_splits, embargo=a.embargo,
                    baseline=(a.baseline_tp, a.baseline_h),
                    min_support=a.min_support)
        print(f"eventos en el cubo: {n_ev} | barrido de calibracion F3:")
        print(tbl.to_string(index=False))
        if n_ev < 1000:
            print(f"  ⚠ GATE §6.6: {n_ev} < 1000 -> bajo poder (radar).")
        return 0
    sel, rep = run(cube, n_splits=a.n_splits, embargo=a.embargo, k=a.k,
                   baseline=(a.baseline_tp, a.baseline_h),
                   margin=a.margin, min_support=a.min_support)
    print(f"eventos en el cubo: {n_ev} | OOS evaluados: {rep.get('n', len(sel))}")
    if rep.get("n", len(sel)) == 0:
        print("  (sin folds/eventos suficientes)"); return 0
    s, b = rep["selector"], rep["baseline"]
    print(f"  baseline ({a.baseline_tp}/h{a.baseline_h}): "
          f"exp_r={b['expectancy_r']:+.4f} WR={b['wr']*100:.1f}% n={b['n']}")
    print(f"  SELECTOR F3 (k={a.k})        : "
          f"exp_r={s['expectancy_r']:+.4f} WR={s['wr']*100:.1f}% n={s['n']}")
    print(f"  LIFT del selector: {rep['lift_r']:+.4f}R | abstención "
          f"{rep['abstain_rate']*100:.1f}%")
    print(f"  celdas elegidas: {rep['cell_dist']}")
    if n_ev < 1000:
        print(f"  ⚠ GATE §6.6: {n_ev} eventos < 1000 -> diagnóstico de BAJO PODER "
              "(el vecindario es ralo). Radar, no veredicto: cosechar más.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
