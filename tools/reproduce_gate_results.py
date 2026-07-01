#!/usr/bin/env python3
"""reproduce_gate_results — regenera los resultados del gate POC-distance del review.

Corre el MISMO gate_poc_distance que valida en producción sobre los 5 cubos cripto,
imprime la tabla por símbolo (far vs near) + el veredicto pooled (DSR / ortogonalidad-KL
/ CPCV / PBO) y guarda una figura. Reproducible -> respalda la sección de Resultados del
review científico (MEMORY/investigacion/review-fq).

  python tools/reproduce_gate_results.py --out-dir MEMORY/investigacion
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import gate_poc_distance as G  # noqa: E402

PAIRS = [
    ("BTC", "cosecha_cubes/tp_cube_BTC_USDT.parquet", "data/kl_hist_BTCUSDT.parquet"),
    ("ETH", "cosecha_cubes/tp_cube_ETH_USDT.parquet", "data/kl_hist_ETHUSDT.parquet"),
    ("SOL", "cosecha_cubes/tp_cube_SOL_USDT.parquet", "data/kl_hist_SOLUSDT.parquet"),
    ("BCH", "cosecha_cubes/tp_cube_BCH_USDT.parquet", "data/okx/kl_hist_BCHUSDT.parquet"),
    ("BNB", "cosecha_cubes/tp_cube_BNB_USDT.parquet", "data/okx/kl_hist_BNBUSDT.parquet"),
]

# La figura es BILINGÜE: el review (ES) y el preprint SSRN (EN) embeben la MISMA gráfica con
# etiquetas en su idioma (bug 2026-07-01: el preprint EN llevaba la figura en español).
FIG_LABELS = {
    "es": dict(far="lejos del POC", near="cerca del POC", exc="excepción",
               title="POC-distance: lejos vs cerca del POC del día previo (5 cripto, tp4/h576)",
               fname="fig-poc-distance.png"),
    "en": dict(far="far from prior-day POC", near="near the POC", exc="exception",
               title="POC-distance: far vs near the prior-day POC (5 crypto, tp4/h576)",
               fname="fig-poc-distance-en.png"),
}


def make_figure(tab, out_dir, lang="es"):
    """Dibuja la figura far-vs-near por símbolo en el idioma pedido. `tab` = DataFrame
    [sym, n, far, near] (del gate). Devuelve la ruta del PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    L = FIG_LABELS[lang]
    syms = tab.sym.tolist()
    x = np.arange(len(syms))
    w = 0.38
    fig, ax = plt.subplots(figsize=(7.4, 3.7), dpi=150)
    ax.bar(x - w / 2, tab.far, w, label=L["far"], color="#0f6f4d")
    ax.bar(x + w / 2, tab.near, w, label=L["near"], color="#b08338")
    ax.axhline(0, color="#1c2420", lw=0.8)
    bnb_i = syms.index("BNB") if "BNB" in syms else None
    if bnb_i is not None:
        ax.annotate(L["exc"], xy=(bnb_i, tab.near.iloc[bnb_i]),
                    xytext=(bnb_i - 0.1, max(tab.far.max(), tab.near.max()) * 0.92),
                    fontsize=8, color="#a23b2e", ha="center",
                    arrowprops=dict(arrowstyle="->", color="#a23b2e", lw=0.9))
    ax.set_xticks(x)
    ax.set_xticklabels(syms)
    ax.set_ylabel("meanR (gross)")
    ax.set_title(L["title"], fontsize=10)
    # upper LEFT: la anotación de la excepción (BNB, último símbolo) vive arriba a la
    # derecha — con la leyenda ahí se encimaban (bug visual detectado en el preprint EN).
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    figpath = os.path.join(out_dir, L["fname"])
    fig.savefig(figpath)
    return figpath


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="MEMORY/investigacion")
    p.add_argument("--lang", default="es", choices=sorted(FIG_LABELS),
                   help="idioma de la figura (es=review, en=preprint SSRN)")
    a = p.parse_args(argv)
    os.makedirs(a.out_dir, exist_ok=True)

    rows, frames = [], []
    for label, cube, kl in PAIRS:
        t = G.tag(label, cube, kl)
        frames.append(t)
        thr = float(t.poc_dist.quantile(0.70))
        far = t[t.poc_dist >= thr].pnl_r
        near = t[t.poc_dist < thr].pnl_r
        rows.append(dict(sym=label, n=int(len(t)),
                         far=float(far.mean()), near=float(near.mean())))
    tab = pd.DataFrame(rows)
    pool = pd.concat(frames, ignore_index=True)
    g = G.gate(pool)
    passed = (g["dsr_far"]["significant"] and g["upl_within_kl"] > 0.02
              and g["oos_med"] > 0 and g["pbo"] < 0.5)

    print("== POC-distance — resultados reproducibles (tp4/h576, GROSS) ==")
    print(tab.assign(uplift=(tab.far - tab.near)).to_string(index=False))
    print("\nPOOLED n=%d  uplift(far-base)=+%.3f  DSR=%.3f  within-KL=+%.3f  "
          "CPCV-OOS=+%.3f (%.0f%% paths>0)  PBO=%.2f  -> %s"
          % (g["base_n"], g["upl_far"], g["dsr_far"]["dsr"], g["upl_within_kl"],
             g["oos_med"], g["oos_pos"] * 100, g["pbo"], "PASA" if passed else "NO PASA"))

    # ---- figura (bilingüe) ----
    figpath = make_figure(tab, a.out_dir, lang=a.lang)
    print("\nfigura -> %s" % figpath)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
