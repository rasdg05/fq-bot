#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cube_fixed_window — ¿la señal se distingue ANTES de resolverse?

LA PREGUNTA QUE geometry_report NO PUEDE HACER. Comparar el recorrido de
ganadores contra el de perdedores sobre la excursión sellada es circular: ganar
ES tocar el TP, luego MFE >= rr por construcción (medido: 96,5 % contra 0,0 %).
Los grupos no pueden solaparse y el veredicto "separan" sale siempre.

LA VERSIÓN NO CIRCULAR, y sus tres condiciones:

  1. **Ventana fija.** k velas iguales para toda señal, no la vida de cada una.
  2. **Solo las vivas en k** (`bars_held > k`). Si una ya resolvió, su desenlace
     está DENTRO de la ventana y la circularidad vuelve. "Sigue viva en k" se
     sabe en la vela k: no es lookahead, es lo que un operador tiene delante.
  3. **Placebo obligatorio.** Sin él la lectura miente. Medido: el recorrido
     temprano da AUC 0,69 sobre las señales del motor — y una entrada ARBITRARIA
     sobre la misma cinta da lo mismo (diferencia +0,000 / −0,012). Lo que mide
     no es la señal: es que el precio que ya se movió hacia el TP lo tiene más
     cerca. Una propiedad del camino que cumple cualquier entrada.

Por eso este tool **no sabe imprimir el número solo**. Siempre sale contra su
placebo, y lo que se lee es la DIFERENCIA con su IC95 % por bootstrap.

EL PLACEBO. Misma cinta, mismo día, misma dirección, misma geometría relativa
(stop en % del precio, mismo rr), entrada arbitraria W velas después. Está
emparejado a propósito: comparte régimen y volatilidad, así que si algo queda
es de la señal. Sesga en CONTRA de encontrar diferencia (el placebo hereda algo
del régimen que disparó la señal), o sea que es conservador.

Uso:
  python tools/cube_fixed_window.py
  python tools/cube_fixed_window.py --ks 3 6 12 24 --symbols BTC_USDT
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cube_regrade_excursion as CR      # noqa: E402

BAR_MS = 300_000
MIN_N = 30
KS = [3, 6, 12, 24]
W = 48                                   # velas de vida para motor y placebo
N_BOOT = 2000
BASE_TP, BASE_H = "tp4", 288


def auc(score, y):
    """P(score de un positivo > score de un negativo), empates a 0.5."""
    score = np.asarray(score, dtype=float)
    y = np.asarray(y).astype(bool)
    n_p, n_n = int(y.sum()), int((~y).sum())
    if n_p == 0 or n_n == 0:
        return float("nan")
    r = pd.Series(score).rank().to_numpy()
    return (r[y].sum() - n_p * (n_p + 1) / 2.0) / (n_p * n_n)


def auc_ci(score, y, n_boot=1000, seed=0):
    rng = np.random.default_rng(seed)
    score = np.asarray(score, dtype=float)
    y = np.asarray(y).astype(bool)
    outs = [a for a in (auc(score[i], y[i]) for i in
                        (rng.integers(0, len(y), len(y)) for _ in range(n_boot)))
            if a == a]
    if not outs:
        return (float("nan"), float("nan"))
    return (float(np.percentile(outs, 2.5)), float(np.percentile(outs, 97.5)))


def sim_entry(entry, stop_pct, direction, hi, lo, cl, rr):
    """Recorrido y desenlace de UNA entrada. Empate intra-vela -> perdedor."""
    risk = entry * stop_pct
    d = direction
    fav = (hi - entry) / risk if d == 1 else (entry - lo) / risk
    adv = (lo - entry) / risk if d == 1 else (entry - hi) / risk
    t = np.flatnonzero(fav >= rr)
    s = np.flatnonzero(adv <= -1.0)
    t = int(t[0]) if t.size else None
    s = int(s[0]) if s.size else None
    if t is None and s is None:
        gana, vida = bool(d * (cl[-1] - entry) / risk > 0), len(cl)
    elif s is None:
        gana, vida = True, t + 1
    elif t is None:
        gana, vida = False, s + 1
    else:
        gana, vida = (t < s), min(t, s) + 1
    return {"gana": gana, "vida": vida,
            "mfe": np.maximum.accumulate(fav),
            "mae": np.minimum.accumulate(adv),
            "net": d * (cl - entry) / risk}


def recoger(sym, kl, cube, w=W):
    """(motor, placebo) emparejados, una entrada de cada por señal."""
    base = (cube[(cube["tp"] == BASE_TP) & (cube["horizon"] == BASE_H)]
            .drop_duplicates(["entry_ts", "direction"]))
    pos = pd.Series(np.arange(len(kl)), index=kl.index.to_numpy())
    motor, placebo = [], []
    for row in base.to_dict("records"):
        ms = int(pd.Timestamp(row["entry_ts"]).value // 10**6)
        p = pos.reindex(np.arange(ms + BAR_MS, ms + (2 * w + 1) * BAR_MS, BAR_MS))
        if p.isna().any():
            continue
        b = kl.iloc[p.astype(int).to_numpy()]
        hi, lo, cl = (b["high"].to_numpy(), b["low"].to_numpy(), b["close"].to_numpy())
        e, d = float(row["entry_price"]), int(row["direction"])
        risk = abs(e - float(row["stop_price"]))
        sp = risk / e
        rr = abs(float(row["px_tp4"]) - e) / risk
        motor.append(sim_entry(e, sp, d, hi[:w], lo[:w], cl[:w], rr))
        placebo.append(sim_entry(cl[w - 1], sp, d, hi[w:], lo[w:], cl[w:], rr))
    return motor, placebo


def _wr_diff(motor, placebo, rng):
    a = np.array([x["gana"] for x in motor])
    b = np.array([x["gana"] for x in placebo])
    n = len(a)
    d = np.array([a[i].mean() - b[i].mean()
                  for i in (rng.integers(0, n, n) for _ in range(N_BOOT))])
    return a.mean(), b.mean(), d


def informe(motor, placebo, ks=KS, seed=0):
    rng = np.random.default_rng(seed)
    n = len(motor)
    print("\n=== SEPARACION NO CIRCULAR — %d senales, vida %d velas, %s ==="
          % (n, W, BASE_TP))
    if n < MIN_N:
        print("  n<%d: NO se concluye." % MIN_N)
        return

    wm, wp, d = _wr_diff(motor, placebo, rng)
    print("\nWIN RATE contra el placebo (lo que mide la ENTRADA)")
    print("  motor %.1f%%   placebo %.1f%%   diff %+.1f pp  IC95%% [%+.1f, %+.1f]"
          % (100 * wm, 100 * wp, 100 * (wm - wp),
             100 * np.percentile(d, 2.5), 100 * np.percentile(d, 97.5)))
    print("  P(diff<=0) = %.3f" % float(np.mean(d <= 0)))

    print("\nAUC del RECORRIDO TEMPRANO — diferencia contra el placebo")
    print("  (lo que mide si la trayectoria anticipa el desenlace)")
    print("  %-4s %8s %-28s %-28s" % ("k", "n_vivas", "mfe_k", "net_k"))
    for k in ks:
        mr = [x for x in motor if x["vida"] > k]
        mp = [x for x in placebo if x["vida"] > k]
        if len(mr) < MIN_N or len(mp) < MIN_N:
            continue
        cols = []
        for campo in ("mfe", "net"):
            sr = np.array([x[campo][k - 1] for x in mr])
            yr = np.array([x["gana"] for x in mr])
            sp = np.array([x[campo][k - 1] for x in mp])
            yp = np.array([x["gana"] for x in mp])
            dd = []
            for _ in range(N_BOOT):
                ir = rng.integers(0, len(mr), len(mr))
                ip = rng.integers(0, len(mp), len(mp))
                a1, a2 = auc(sr[ir], yr[ir]), auc(sp[ip], yp[ip])
                if a1 == a1 and a2 == a2:
                    dd.append(a1 - a2)
            dd = np.array(dd)
            lo, hi = np.percentile(dd, 2.5), np.percentile(dd, 97.5)
            cols.append("%+.3f [%+.3f,%+.3f]%s"
                        % (dd.mean(), lo, hi, "" if (lo > 0 or hi < 0) else " ~"))
        print("  %-4d %8d %-28s %-28s" % (k, len(mr), cols[0], cols[1]))
    print("\n  '~' = el IC95% de la DIFERENCIA cruza cero -> indistinguible del")
    print("  placebo. Con 8 celdas a 95%, esperar ~0.4 falsos positivos: una sola")
    print("  celda significativa NO es un hallazgo.")


def main(argv=None):
    p = argparse.ArgumentParser(description="Separacion no circular, contra placebo")
    p.add_argument("--kl-dir", default=CR.KL_DIR)
    p.add_argument("--symbols", nargs="*", default=None)
    p.add_argument("--ks", nargs="*", type=int, default=KS)
    a = p.parse_args(argv)

    motor, placebo = [], []
    for f in sorted(glob.glob(os.path.join(a.kl_dir, "kl_life_*.parquet"))):
        sym = os.path.basename(f).replace("kl_life_", "").replace(".parquet", "")
        if a.symbols and sym not in a.symbols:
            continue
        kl = CR.load_life_candles(sym, a.kl_dir)
        cube, _ = CR.regrade(
            pd.read_parquet("cosecha_cubes/tp_cube_%s.parquet" % sym), kl)
        if cube is None:
            continue
        m, q = recoger(sym, kl, cube)
        print("  %-10s %d senales con ventana de %d velas" % (sym, len(m), 2 * W))
        motor += m
        placebo += q
    if not motor:
        print("sin senales con ventana completa; corre fetch_okx_life_windows")
        return 1
    informe(motor, placebo, a.ks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
