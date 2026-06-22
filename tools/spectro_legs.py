# -*- coding: utf-8 -*-
"""
spectro_legs.py - Espectroscopia de saltos (la "primera solucion numerica").

Pregunta fisica: el activo tiene "energias favoritas" (saltos discretos = orbitas
de Bohr), o un continuo liso? Si el modelo cuantico-de-liquidez es real, la
distribucion de tamanos de pierna (normalizada por ATR) es MULTIMODAL; si es
poesia, es una log-normal lisa unimodal.

Metodo:
  1. Pivots (swings) replicando ict_smc.find_pivots (fractal de fuerza s).
  2. Colapso a zigzag alternante (H,L,H,L...).
  3. Pierna = |dP| entre swings consecutivos / ATR(14) Wilder al inicio de la
     pierna (quita el escalado trivial de volatilidad).
  4. Espectro = distribucion de leg/ATR. Multimodalidad EN LOG-ESPACIO (una
     log-normal -> 1 bulto; energias favoritas -> varios bultos).
  5. Barrido de bandwidth (Silverman) + varias fuerzas de pivot -> robustez
     (los modos no deben depender de un solo seteo).

Pure numpy/pandas. Sin scipy/sklearn (CONSTRAINTS 7).
"""
import numpy as np
import pandas as pd

PARQUET = "data/okx/SOL-USDT-SWAP_5m.parquet"
STRENGTHS = (2, 3, 5)        # robustez vs definicion de swing
DETAIL_STRENGTH = 3          # para el detalle + el plot


def atr_wilder(df, n=14):
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    prev = np.concatenate([[close[0]], close[:-1]])
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    return pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def find_pivots(df, strength):
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)
    ph, pl = [], []
    for i in range(strength, n - strength):
        if all(highs[i] > highs[i - j] for j in range(1, strength + 1)) and \
           all(highs[i] > highs[i + j] for j in range(1, strength + 1)):
            ph.append((i, float(highs[i]), "H"))
        if all(lows[i] < lows[i - j] for j in range(1, strength + 1)) and \
           all(lows[i] < lows[i + j] for j in range(1, strength + 1)):
            pl.append((i, float(lows[i]), "L"))
    return ph, pl


def zigzag(ph, pl):
    piv = sorted(ph + pl)  # por idx
    seq = []
    for idx, price, kind in piv:
        if seq and seq[-1][2] == kind:  # mismo tipo seguido -> quedarse con el extremo
            if (kind == "H" and price > seq[-1][1]) or (kind == "L" and price < seq[-1][1]):
                seq[-1] = (idx, price, kind)
        else:
            seq.append((idx, price, kind))
    return seq


def legs_for(df, atr, strength):
    ph, pl = find_pivots(df, strength)
    seq = zigzag(ph, pl)
    out = []
    for (i0, p0, _), (i1, p1, _) in zip(seq[:-1], seq[1:]):
        a0 = atr[i0]
        if a0 > 0 and np.isfinite(a0):
            out.append(abs(p1 - p0) / a0)
    return np.array(out), len(ph) + len(pl), len(seq)


def kde(y, grid, bw):
    u = (grid[:, None] - y[None, :]) / bw
    return np.exp(-0.5 * u * u).sum(1) / (len(y) * bw * np.sqrt(2 * np.pi))


def silverman_bw(y):
    n = len(y)
    sd = y.std(ddof=1)
    q75, q25 = np.percentile(y, [75, 25])
    iqr = (q75 - q25) / 1.349
    a = min(sd, iqr) if iqr > 0 else sd
    return 0.9 * a * n ** (-1 / 5)


def peaks_of(grid, dens, min_prom=0.05):
    gmax = dens.max()
    pk = [i for i in range(1, len(dens) - 1)
          if dens[i] > dens[i - 1] and dens[i] >= dens[i + 1] and dens[i] > min_prom * gmax]
    return pk


def clean(legs):
    lo, hi = np.percentile(legs, [1, 99])
    return legs[(legs >= max(lo, 0.1)) & (legs <= hi)]


def main():
    df = pd.read_parquet(PARQUET)
    atr = atr_wilder(df)
    print(f"candles={len(df)}  symbol=SOL-USDT-SWAP 5m\n")

    # ---- headline: cuantos modos por fuerza de pivot (robustez) ----
    print("=" * 64)
    print("ESPECTRO POR FUERZA DE PIVOT  (modos del KDE en log-espacio)")
    print("=" * 64)
    detail = None
    for s in STRENGTHS:
        legs, npiv, nsw = legs_for(df, atr, s)
        x = clean(legs)
        y = np.log(x)
        grid = np.linspace(y.min(), y.max(), 600)
        bw0 = silverman_bw(y)
        nmodes = {}
        for mult in (0.75, 1.0, 1.5):
            pk = peaks_of(grid, kde(y, grid, bw0 * mult))
            nmodes[mult] = (len(pk), np.round(np.exp(grid[pk]), 2))
        print(f"\nstrength={s}: pivots={npiv} swings={nsw} legs={len(legs)} "
              f"| median leg/ATR={np.median(legs):.2f}")
        for mult, (nm, modes) in nmodes.items():
            print(f"   bw x{mult:>4}: {nm} modos -> ATR-mult {list(modes)}")
        if s == DETAIL_STRENGTH:
            detail = (legs, x, y, grid, bw0)

    # ---- detalle @ DETAIL_STRENGTH ----
    legs, x, y, grid, bw0 = detail
    d = kde(y, grid, bw0)
    pk = peaks_of(grid, d)
    modes = np.exp(grid[pk])
    heights = d[pk]
    print("\n" + "=" * 64)
    print(f"DETALLE @ strength={DETAIL_STRENGTH}  (Silverman bw={bw0:.3f})")
    print("=" * 64)
    print(f"leg/ATR: n={len(legs)} median={np.median(legs):.2f} mean={legs.mean():.2f} "
          f"p10={np.percentile(legs,10):.2f} p90={np.percentile(legs,90):.2f} max={legs.max():.2f}")
    print(f"\nMODOS detectados: {len(pk)}")
    for m, h in zip(modes, heights):
        print(f"   leg/ATR ~ {m:.2f}   (densidad {h:.3f})")
    if len(pk) >= 2:
        order = np.argsort(heights)[-2:]
        i, j = sorted([pk[order[0]], pk[order[1]]])
        dip = d[i:j + 1].min() / min(d[i], d[j])
        print(f"   valle/pico entre 2 modos top = {dip:.2f}  "
              f"(<0.85 => bimodalidad real; ~1.0 => unimodal)")

    # Fibonacci check
    if len(modes):
        base = modes.min()
        fibs = {"0.618": 0.618, "1.0": 1.0, "1.272": 1.272, "1.618": 1.618,
                "2.0": 2.0, "2.618": 2.618}
        print("\n¿Modos en proporcion Fibonacci respecto al modo base?")
        for m in modes:
            r = m / base
            name, val = min(fibs.items(), key=lambda kv: abs(kv[1] - r))
            tag = "<== match" if abs(val - r) < 0.08 else ""
            print(f"   modo {m:.2f}  ratio={r:.2f}  Fib+cercano={name} {tag}")

    # espectro de texto (lineal)
    print("\nESPECTRO (histograma leg/ATR lineal):")
    counts, edges = np.histogram(x, bins=36)
    cmax = counts.max()
    for c, e in zip(counts, edges[:-1]):
        print(f"  {e:4.2f} |{'#' * int(46 * c / cmax)} {c}")

    # plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(13, 5))
        ax[0].hist(x, bins=60, density=True, alpha=.45, color="steelblue")
        xs = np.linspace(x.min(), x.max(), 400)
        ax[0].plot(xs, kde(x, xs, silverman_bw(x)), "k-", lw=1.6)
        for m in modes:
            ax[0].axvline(m, color="crimson", ls="--", lw=1)
        ax[0].set_title("Espectro de saltos SOL 5m (leg/ATR, lineal)")
        ax[0].set_xlabel("leg / ATR")
        ax[0].set_ylabel("densidad")
        ax[1].hist(x, bins=60, density=True, alpha=.4, color="seagreen")
        ax[1].plot(np.exp(grid), d, "k-", lw=1.6)
        for m in modes:
            ax[1].axvline(m, color="crimson", ls="--", lw=1)
        ax[1].set_xscale("log")
        ax[1].set_title(f"Mismo, log-x ({len(pk)} modos @Silverman)")
        ax[1].set_xlabel("leg / ATR (log)")
        fig.tight_layout()
        fig.savefig("spectro_sol_legs.png", dpi=110)
        print("\nPLOT -> spectro_sol_legs.png")
    except Exception as e:
        print(f"\n(sin plot: {e})")


if __name__ == "__main__":
    main()
