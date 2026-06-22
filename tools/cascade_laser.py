# -*- coding: utf-8 -*-
"""
cascade_laser.py - Fork #2: la cascada como laser, con tasa de descuento fiteada.

Hipotesis:
  (H1) La cascada (sweep + run impulsivo) tiene un ALCANCE que sigue una ley de
       supervivencia exponencial:  P(reach >= d) = e^(-rho * d).  -> fiteamos rho.
  (H2) La INVERSION DE POBLACION (apalancamiento unilateral; proxy = funding,
       alineado al disparo) MODULA esa tasa: mas inversion -> rho menor ->
       cascada mas profunda (la "ganancia del laser").

Cascada (proxy desde OHLCV, sin feed de liquidaciones):
  - leg = swing-a-swing (zigzag sobre find_pivots).
  - SWEEP: el leg rompe el pivote previo del mismo lado (toma su liquidez).
  - reach = EXTENSION mas alla del nivel barrido, en ATR (lo que corrio el laser
    despues de encender). Cascada = sweep impulsivo (speed en top tercil).
  - inversion = -direction * funding(<=t_trigger)  (down-cascade liquida longs ->
    crowded longs <-> funding>0 -> inversion alta). Causal: funding del pasado.

Limitaciones honestas: sin OI (funding es proxy debil, 8h, baja varianza); funding
cubre ~3 meses -> Parte B con menos eventos. Cascada es proxy de precio/vol, no
prints de liquidacion reales. Se reportan 2 umbrales para no cherry-pickear.

Pure numpy/pandas (+ matplotlib para el plot). CONSTRAINTS 7.
"""
import numpy as np
import pandas as pd

OHLC = "data/okx/SOL-USDT-SWAP_5m.parquet"
FUND = "data/okx/SOL-USDT-SWAP_funding.parquet"
STRENGTH = 3
H8 = 28800000  # 8h en ms
DAY = 86400000


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


def detect_cascades(df, atr, strength):
    ts = df["timestamp"].to_numpy()
    vol = df["volume"].to_numpy(float)
    seq = zigzag(*find_pivots(df, strength))
    out = []
    for j in range(2, len(seq)):
        i_end, p_end, k_end = seq[j]
        i_st, p_st, k_st = seq[j - 1]
        i_prior, p_prior, k_prior = seq[j - 2]  # mismo tipo que el fin (alterna)
        direction = -1 if k_end == "L" else 1
        a0 = atr[i_st]
        if not (a0 > 0 and np.isfinite(a0)):
            continue
        mag = abs(p_end - p_st)
        nbar = max(i_end - i_st, 1)
        depth_atr = mag / a0
        speed = depth_atr / nbar
        # sweep: rompe el pivote previo del mismo lado
        if direction == -1:
            swept = p_end < p_prior
            ext = (p_prior - p_end) / a0 if swept else 0.0
        else:
            swept = p_end > p_prior
            ext = (p_end - p_prior) / a0 if swept else 0.0
        # surge de volumen del leg vs baseline previo (causal)
        b0 = max(i_st - 20, 0)
        base = vol[b0:i_st].mean() if i_st > b0 else np.nan
        vsurge = (vol[i_st:i_end + 1].mean() / base) if base and base > 0 else np.nan
        out.append(dict(i_st=i_st, i_end=i_end, t=ts[i_st], direction=direction,
                        depth_atr=depth_atr, ext_atr=ext, nbar=nbar, speed=speed,
                        vsurge=vsurge, swept=bool(swept)))
    return pd.DataFrame(out)


def exp_fit_survival(d):
    """MLE exponencial: mu=media. Devuelve mu (alcance), rho=1/mu, y chequeo de
    forma (exponencial => mediana ~ mu*ln2)."""
    mu = d.mean()
    return mu, 1.0 / mu, np.median(d), mu * np.log(2)


def spearman(x, y):
    rx = pd.Series(x).rank().to_numpy(); ry = pd.Series(y).rank().to_numpy()
    return np.corrcoef(rx, ry)[0, 1]


def perm_pvalue(x, y, stat=spearman, n=3000, seed=0):
    rng = np.random.default_rng(seed)
    obs = stat(x, y); cnt = 0
    yy = np.array(y)
    for _ in range(n):
        if abs(stat(x, rng.permutation(yy))) >= abs(obs):
            cnt += 1
    return obs, (cnt + 1) / (n + 1)


def main():
    df = pd.read_parquet(OHLC)
    atr = atr_wilder(df)
    fnd = pd.read_parquet(FUND).sort_values("fundingTime")
    ft = fnd["fundingTime"].to_numpy(); fr = fnd["fundingRate"].to_numpy()
    print(f"OHLC: {len(df)} velas 5m | funding: {len(fnd)} pts 8h "
          f"({pd.to_datetime(ft[0],unit='ms').date()} -> {pd.to_datetime(ft[-1],unit='ms').date()})\n")

    casc = detect_cascades(df, atr, STRENGTH)
    swept = casc[casc.swept].copy()
    # impulso: speed en top tercil de los swept
    thr = swept.speed.quantile(0.667)
    swept["impulsive"] = swept.speed >= thr
    cas = swept[swept.impulsive].copy()
    print(f"legs={len(casc)} | swept={len(swept)} | cascadas(sweep+impulso top33%)={len(cas)} "
          f"(down={int((cas.direction<0).sum())} up={int((cas.direction>0).sum())})")

    # ---------- PARTE A: alcance y rho (7 meses, solo precio) ----------
    d = cas.ext_atr.to_numpy()
    d = d[(d > 0) & (d <= np.percentile(d, 99))]
    mu, rho, med, exp_med = exp_fit_survival(d)
    print("\n" + "=" * 60)
    print("PARTE A - Alcance de la cascada (extension mas alla del sweep)")
    print("=" * 60)
    print(f"n={len(d)} | reach MEDIA mu={mu:.2f} ATR -> rho=1/mu={rho:.3f} (1/ATR)")
    print(f"reach MEDIANA={med:.2f} ATR | exp predice mediana={exp_med:.2f}")
    print(f"-> forma: {'~exponencial' if abs(med-exp_med)/exp_med<0.25 else 'cola mas pesada que exp'}")

    # ---------- PARTE B: inversion (funding) modula rho? ----------
    cas = cas[cas.t >= ft[0]].copy()  # overlap con funding
    idx = np.searchsorted(ft, cas.t.to_numpy(), side="right") - 1
    f_last = np.where(idx >= 0, fr[np.clip(idx, 0, len(fr) - 1)], np.nan)
    # media de funding 24h previa (acumulacion)
    f24 = []
    for t in cas.t.to_numpy():
        m = (ft <= t) & (ft > t - DAY)
        f24.append(fr[m].mean() if m.any() else np.nan)
    cas["f_last"] = f_last; cas["f24"] = np.array(f24)
    cas["inv"] = -cas.direction * cas.f_last        # inversion al disparo
    cas["inv24"] = -cas.direction * cas.f24          # inversion sostenida 24h
    b = cas.dropna(subset=["ext_atr", "inv"])
    b = b[b.ext_atr > 0]
    print("\n" + "=" * 60)
    print("PARTE B - Inversion de poblacion (funding) vs alcance")
    print("=" * 60)
    print(f"cascadas en overlap con funding: {len(b)}")
    print(f"funding al disparo: media={np.nanmean(cas.f_last):.6f} std={np.nanstd(cas.f_last):.6f}")
    for col in ("inv", "inv24"):
        bb = b.dropna(subset=[col])
        if len(bb) < 30:
            print(f"  [{col}] n={len(bb)} insuficiente"); continue
        r, p = perm_pvalue(bb.ext_atr.to_numpy(), bb[col].to_numpy())
        pear = np.corrcoef(bb.ext_atr, bb[col])[0, 1]
        print(f"  [{col}] Spearman={r:+.3f} (perm p={p:.3f}) | Pearson={pear:+.3f} | n={len(bb)}")
        # terciles de inversion -> reach y rho por bin
        q = bb[col].quantile([0, 1/3, 2/3, 1.0]).to_numpy()
        labels = ["baja", "media", "alta"]
        print(f"     inversion -> reach medio (rho):")
        for k in range(3):
            seg = bb[(bb[col] >= q[k]) & (bb[col] <= q[k+1])] if k == 2 else bb[(bb[col] >= q[k]) & (bb[col] < q[k+1])]
            if len(seg):
                m = seg.ext_atr.mean()
                print(f"        {labels[k]:>5} (n={len(seg):>3}): reach={m:.2f} ATR  rho={1/m:.3f}")

    # ---------- plots ----------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(13, 5))
        ds = np.sort(d)
        surv = 1.0 - np.arange(len(ds)) / len(ds)
        ax[0].step(ds, surv, where="post", label="empirico")
        ax[0].plot(ds, np.exp(-ds / mu), "r--", label=f"exp(-d/{mu:.2f})")
        ax[0].set_yscale("log"); ax[0].set_xlabel("reach (ATR mas alla del sweep)")
        ax[0].set_ylabel("P(reach >= d)"); ax[0].set_title("Supervivencia de la cascada + fit")
        ax[0].legend()
        bb = b.dropna(subset=["inv"])
        if len(bb) > 10:
            ax[1].scatter(bb.inv, bb.ext_atr, s=14, alpha=.5)
            ax[1].set_xlabel("inversion = -dir * funding (al disparo)")
            ax[1].set_ylabel("reach (ATR)")
            ax[1].set_title(f"Reach vs inversion (n={len(bb)})")
        fig.tight_layout(); fig.savefig("cascade_laser.png", dpi=110)
        print("\nPLOT -> cascade_laser.png")
    except Exception as e:
        print(f"\n(sin plot: {e})")


if __name__ == "__main__":
    main()
