# -*- coding: utf-8 -*-
"""
transition_matrix.py - Heisenberg matricial aplicado al precio.

El observable NO es el camino entre saltos (irrelevante), sino el par
(nivel de salida, nivel de llegada). Construimos la matriz de transiciones
M[i->j] entre niveles de liquidez y miramos su ESTRUCTURA (reglas de seleccion,
orbitales, modos ciclicos) = la espectroscopia hecha como Heisenberg manda.

Estado / "nivel": distancia del precio al VWAP rodante (24h), en ATR, binned.
  -> estacionario (saca la tendencia = saca el Doppler). Estados -K..+K.
Salto: pivote-a-pivote (zigzag sobre find_pivots). Cada salto = (estado_salida,
  estado_llegada) -> suma 1 a M.

Tests:
  - Entropia de M vs un null (barajar llegadas): hay estructura real o es azar?
  - Eigen-espectro: |l2| (memoria/mezcla) y autovalores complejos (ciclos).
  - Mapa de contraccion E[|llegada| | |salida|]: de lejos del valor, vuelve
    (reversion/orbital) o sigue (momentum)? = la regla de seleccion clave.
  - BTC vs SOL: BTC (mas energia/decoherencia) deberia ser MAS estructurado.

Pure numpy/pandas (+ matplotlib). CONSTRAINTS 7.
"""
import numpy as np
import pandas as pd

SYMBOLS = {"BTC": "data/okx/BTC-USDT-SWAP_5m.parquet",
           "SOL": "data/okx/SOL-USDT-SWAP_5m.parquet"}
STRENGTH = 3
VWAP_WIN = 288    # 24h en velas de 5m
BINW = 0.75       # ancho de bin en ATR
K = 5             # estados -K..+K (2K+1 = 11)
NULLS = 200


def atr_wilder(df, n=14):
    h = df["high"].to_numpy(float); l = df["low"].to_numpy(float); c = df["close"].to_numpy(float)
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    return pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def find_pivots(df, strength):
    hi = df["high"].values; lo = df["low"].values; n = len(df)
    ph, pl = [], []
    for i in range(strength, n - strength):
        if all(hi[i] > hi[i - j] for j in range(1, strength + 1)) and all(hi[i] > hi[i + j] for j in range(1, strength + 1)):
            ph.append((i, float(hi[i]), "H"))
        if all(lo[i] < lo[i - j] for j in range(1, strength + 1)) and all(lo[i] < lo[i + j] for j in range(1, strength + 1)):
            pl.append((i, float(lo[i]), "L"))
    return ph, pl


def zigzag(ph, pl):
    seq = []
    for idx, price, kind in sorted(ph + pl):
        if seq and seq[-1][2] == kind:
            if (kind == "H" and price > seq[-1][1]) or (kind == "L" and price < seq[-1][1]):
                seq[-1] = (idx, price, kind)
        else:
            seq.append((idx, price, kind))
    return seq


def rolling_vwap(df, win):
    pv = (df["close"] * df["volume"]).to_numpy(float)
    v = df["volume"].to_numpy(float)
    spv = pd.Series(pv).rolling(win, min_periods=win // 2).sum().to_numpy()
    sv = pd.Series(v).rolling(win, min_periods=win // 2).sum().to_numpy()
    return spv / np.where(sv > 0, sv, np.nan)


def state_series(df, atr):
    vwap = rolling_vwap(df, VWAP_WIN)
    z = (df["close"].to_numpy(float) - vwap) / np.where(atr > 0, atr, np.nan)
    b = np.clip(np.round(z / BINW), -K, K)
    return b  # nan donde no hay vwap


def row_norm(C):
    r = C.sum(1, keepdims=True)
    return np.divide(C, r, out=np.zeros_like(C), where=r > 0)


def weighted_entropy(C):
    M = row_norm(C); w = C.sum(1); ent = np.zeros(len(M))
    for i in range(len(M)):
        p = M[i][M[i] > 0]
        ent[i] = -(p * np.log(p)).sum() if len(p) else 0.0
    return (ent * w).sum() / w.sum() / np.log(len(M))  # normalizado [0,1]


def analyze(name, path):
    df = pd.read_parquet(path)
    atr = atr_wilder(df)
    st = state_series(df, atr)
    seq = zigzag(*find_pivots(df, STRENGTH))
    pts = [st[i] for i, _, _ in seq if not np.isnan(st[i])]
    n = 2 * K + 1
    fr = np.array(pts[:-1]); to = np.array(pts[1:])
    C = np.zeros((n, n))
    for a, b in zip(fr, to):
        C[int(a + K), int(b + K)] += 1
    M = row_norm(C)
    H = weighted_entropy(C)

    # null: barajar las llegadas (rompe el link salida->llegada)
    rng = np.random.default_rng(0); Hs = np.empty(NULLS)
    for k in range(NULLS):
        tos = rng.permutation(to); Cs = np.zeros((n, n))
        for a, b in zip(fr, tos):
            Cs[int(a + K), int(b + K)] += 1
        Hs[k] = weighted_entropy(Cs)
    z = (H - Hs.mean()) / (Hs.std() + 1e-9)

    # eigen
    ev = np.linalg.eigvals(M); ev = ev[np.argsort(-np.abs(ev))]
    lam2 = abs(ev[1]); gap = 1 - lam2
    comp = ev[np.abs(ev.imag) > 1e-6]; cyc = None
    if len(comp):
        c = comp[np.argmax(np.abs(comp))]; ang = abs(np.angle(c))
        if ang > 1e-3:
            cyc = 2 * np.pi / ang

    # ocupacion (donde el precio pasa el tiempo, todas las velas)
    occ = np.array([np.sum(st == s) for s in range(-K, K + 1)], float); occ /= occ.sum()

    # mapa de contraccion E[|llegada| | |salida|]
    contr = {}
    for k in range(0, K + 1):
        m = np.abs(fr) == k
        if m.sum() >= 10:
            contr[k] = (np.abs(to[m]).mean(), int(m.sum()))

    print(f"\n{'='*60}\n{name}  jumps={len(fr)}  estados={n} (+-{K} a {BINW} ATR/bin)\n{'='*60}")
    print(f"entropia(M)={H:.3f} | null(azar)={Hs.mean():.3f}+-{Hs.std():.3f} | z={z:+.1f}")
    print(f"  -> {'ESTRUCTURA real' if z < -2 else 'indistinguible del azar'}"
          f" (mas negativo = mas predecible que el azar)")
    print(f"|l2|={lam2:.3f}  spectral gap={gap:.3f}  (gap chico=memoria larga)")
    print(f"modo ciclico: {('periodo ~%.1f saltos' % cyc) if cyc else 'no dominante'}")
    print("orbitales (ocupacion por estado, ATR desde VWAP):")
    for o in np.argsort(-occ)[:5]:
        print(f"    {((o-K)*BINW):+.2f} ATR : {occ[o]*100:4.1f}%")
    print("contraccion  E[|llegada| | |salida|]  (regla de seleccion):")
    for k, (mv, cnt) in contr.items():
        flag = "revierte" if mv < k - 0.15 else ("se aleja" if mv > k + 0.15 else "neutro")
        print(f"    |salida|={k} (n={cnt:>4}) -> |llegada|={mv:.2f}  [{flag}]")
    return dict(name=name, M=M, C=C, H=H, z=z, gap=gap, cyc=cyc, occ=occ)


def main():
    res = [analyze(n, p) for n, p in SYMBOLS.items()]
    print(f"\n{'#'*60}\nDECOHERENCIA: BTC vs SOL (mas energia -> mas estructura?)\n{'#'*60}")
    for r in res:
        print(f"  {r['name']}: entropia={r['H']:.3f} (z={r['z']:+.1f})  gap={r['gap']:.3f}")
    if len(res) == 2:
        btc, sol = res[0], res[1]
        print(f"  -> BTC {'MAS' if btc['H'] < sol['H'] else 'NO mas'} estructurado que SOL "
              f"(entropia {btc['H']:.3f} vs {sol['H']:.3f})")

    # heatmaps
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, len(res), figsize=(6.5 * len(res), 5.5))
        if len(res) == 1:
            axes = [axes]
        ticks = [f"{(i-K)*BINW:+.1f}" for i in range(2 * K + 1)]
        for ax, r in zip(axes, res):
            im = ax.imshow(r["M"], cmap="magma", origin="lower", aspect="auto")
            ax.set_xticks(range(2 * K + 1)); ax.set_xticklabels(ticks, rotation=90, fontsize=7)
            ax.set_yticks(range(2 * K + 1)); ax.set_yticklabels(ticks, fontsize=7)
            ax.set_xlabel("nivel de LLEGADA (ATR desde VWAP)")
            ax.set_ylabel("nivel de SALIDA")
            ax.set_title(f"{r['name']}  M[salida->llegada]   H={r['H']:.3f} (z={r['z']:+.1f})")
            fig.colorbar(im, ax=ax, fraction=0.046)
        fig.tight_layout(); fig.savefig("transition_matrix.png", dpi=110)
        print("\nPLOT -> transition_matrix.png")
    except Exception as e:
        print(f"\n(sin plot: {e})")


if __name__ == "__main__":
    main()
