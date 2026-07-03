#!/usr/bin/env python3
"""validate_long_gates — los 4 experimentos del deep-research "mejora-longs-bull-2026"
(MEMORY/investigacion/), medidos measure-first sobre los cubos, con el MISMO gate que
validó el CVD (deflated Sharpe + CPCV + PBO de tools/validation_gate.py).

Contexto (medido): los LONGS colapsaron post-2023 (2025: +0.02R vs shorts +0.21R),
concentrado en ALTS (SOL +0.01) con majors sanos (BTC/ETH +0.33/+0.32). Hipótesis
verificadas por el research (BIS WP1087, JFM 2026, Cogent E&F 2026, RIBF 2026):

  --exp funding   1) El funding alto = long crowded -> los LONGS pagan con funding
                     negativo/neutral y mueren en la cola caliente (>15% APR sostenido).
  --exp breadth   2) Los LONGS de ALTS solo pagan en alt-season (breadth 90d alto:
                     % del universo que le gana a BTC). Majors como contraste.
  --exp cvd_ortho 3) El CVD tiene componente informado PERMANENTE solo separado del
                     "chase": long CVD-confirmado SIN retorno previo corriendo > con chase.
  --exp onchain   4) Throttle lento: los LONGS de BTC mueren en euforia on-chain
                     (NUPL>=0.75) — bandas de CoinMetrics community (gratis, causal).

Data GRATIS y causal: data.binance.vision (funding + klines 1d mensuales),
kl_hist_* 5m locales (taker_buy_base -> CVD), coinmetrics/data (btc.csv).

  python tools/validate_long_gates.py --fetch            # baja/cachea la data (una vez)
  python tools/validate_long_gates.py --exp all
  python tools/validate_long_gates.py --self-test        # sintético, sin red
"""
import argparse
import io
import os
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import validation_gate as vg          # noqa: E402
import fetch_cvd as fc                # noqa: E402

CUBES = {  # slug del cubo -> símbolo Binance
    "BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "BCH": "BCHUSDT",
    "BNB": "BNBUSDT", "XRP": "XRPUSDT", "LTC": "LTCUSDT", "DOGE": "DOGEUSDT",
    "ADA": "ADAUSDT", "AVAX": "AVAXUSDT", "LINK": "LINKUSDT", "DOT": "DOTUSDT",
    "TRX": "TRXUSDT",
}
MAJORS = {"BTC", "ETH"}
LG = "data/longgates"
VISION = "https://data.binance.vision/data/futures/um/monthly"
CM_BTC = "https://raw.githubusercontent.com/coinmetrics/data/master/csv/btc.csv"
BASELINE_8H = 0.0001          # 0.01%/8h = 10.95% APR (baseline Binance)
APR15_8H = 0.15 / (3 * 365)   # 15% APR en tasa por-evento de 8h


# ---------------------------------------------------------------- data
def _months(y0=2019, m0=9):
    today = date.today()
    y, m = y0, m0
    while (y, m) <= (today.year, today.month):
        yield "%04d-%02d" % (y, m)
        m += 1
        if m > 12:
            y, m = y + 1, 1


def _zip_csv(url, names):
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            df = pd.read_csv(z.open(z.namelist()[0]), header=None, names=names)
        return df
    except Exception:
        return None


def fetch_funding(sym):
    """Funding mensual -> parquet [ts(ms), rate]. Re-ejecutable (cachea)."""
    path = os.path.join(LG, "fund_%s.parquet" % sym)
    if os.path.exists(path):
        return path
    cols = ["calc_time", "funding_interval_hours", "last_funding_rate"]
    parts = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for df in ex.map(lambda ym: _zip_csv(
                "%s/fundingRate/%s/%s-fundingRate-%s.zip" % (VISION, sym, sym, ym), cols),
                _months()):
            if df is not None:
                parts.append(df)
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    df["ts"] = pd.to_numeric(df["calc_time"], errors="coerce")
    df["rate"] = pd.to_numeric(df["last_funding_rate"], errors="coerce")
    df = (df.dropna(subset=["ts", "rate"]).drop_duplicates("ts")
            .sort_values("ts")[["ts", "rate"]].reset_index(drop=True))
    df.to_parquet(path, index=False)
    return path


def fetch_daily(sym):
    """Klines 1d mensuales -> parquet [ts(ms) open_time, close]. Para el breadth 90d."""
    path = os.path.join(LG, "daily_%s.parquet" % sym)
    if os.path.exists(path):
        return path
    raw = ["open_time", "open", "high", "low", "close", "volume", "close_time",
           "qv", "n", "tb", "tbq", "ig"]
    parts = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for df in ex.map(lambda ym: _zip_csv(
                "%s/klines/%s/1d/%s-1d-%s.zip" % (VISION, sym, sym, ym), raw), _months()):
            if df is not None:
                parts.append(df[["open_time", "close"]])
    if not parts:
        return None
    df = pd.concat(parts, ignore_index=True)
    df["ts"] = pd.to_numeric(df["open_time"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = (df.dropna().drop_duplicates("ts").sort_values("ts")[["ts", "close"]]
            .reset_index(drop=True))
    df.to_parquet(path, index=False)
    return path


def fetch_onchain():
    """CoinMetrics community btc.csv -> parquet [ts(ms), mc, rc]. El CSV ya no publica
    CapRealUSD pero SÍ CapMVRVCur (= MC/RC), así que rc = mc/mvrv — mismo NUPL causal
    ((mc-rc)/mc = 1 - 1/MVRV) sin cambiar el consumidor."""
    path = os.path.join(LG, "onchain_btc.parquet")
    if os.path.exists(path):
        return path
    df = pd.read_csv(CM_BTC, usecols=["time", "CapMrktCurUSD", "CapMVRVCur"])
    # OJO pandas 2.x: fechas date-only parsean a datetime64[s]; normalizar a ms SIEMPRE
    df["ts"] = pd.to_datetime(df["time"], utc=True).values.astype("datetime64[ms]").astype("int64")
    df["mc"] = pd.to_numeric(df["CapMrktCurUSD"], errors="coerce")
    df["rc"] = df["mc"] / pd.to_numeric(df["CapMVRVCur"], errors="coerce")
    df = (df.dropna(subset=["ts", "mc", "rc"])[["ts", "mc", "rc"]]
            .sort_values("ts").reset_index(drop=True))
    df.to_parquet(path, index=False)
    return path


def cmd_fetch():
    os.makedirs(LG, exist_ok=True)
    print("== fetch: funding + daily 1d (13 símbolos) + onchain BTC ==")
    for sym in CUBES.values():
        f = fetch_funding(sym)
        d = fetch_daily(sym)
        print("  %-9s funding=%s daily=%s" % (sym, "OK" if f else "-", "OK" if d else "-"))
    print("  onchain: %s" % ("OK" if fetch_onchain() else "-"))


# ---------------------------------------------------------------- fires
def load_fires(tp="tp1", horizon=96, cube_dir="cosecha_cubes"):
    parts = []
    for slug in CUBES:
        p = os.path.join(cube_dir, "tp_cube_%s_USDT.parquet" % slug)
        if not os.path.exists(p):
            continue
        c = pd.read_parquet(p)
        d = c[(c["fired"] == True) & (c["tp"] == tp) & (c["horizon"] == horizon)]  # noqa: E712
        d = d.drop_duplicates("entry_index").copy()
        d["sym"] = slug
        d["ts"] = pd.to_datetime(d["entry_ts"]).values.astype("datetime64[ms]").astype("int64")
        parts.append(d[["sym", "ts", "direction", "pnl_r"]])
    return pd.concat(parts, ignore_index=True).sort_values("ts").reset_index(drop=True)


def _asof(series_ts, series_val, ts):
    """Último valor con series_ts <= ts (causal). NaN si no hay."""
    i = np.searchsorted(series_ts, ts, side="right") - 1
    return series_val[i] if i >= 0 else np.nan


# ---------------------------------------------------------------- gate report
def _dsr(seg, base, n_trials):
    if len(seg) < 30:
        return None
    srs = [np.mean(base) / (np.std(base, ddof=1) or 1), np.mean(seg) / (np.std(seg, ddof=1) or 1)]
    return vg.deflated_sharpe_ratio(np.asarray(seg, float), n_trials=n_trials,
                                    sr_trials_std=max(float(np.std(srs)), 0.01))


def gate_report(df_long, mask, n_trials, label):
    """df_long: fires LONG (orden temporal) con pnl_r; mask: bool del subset gateado.
    Imprime uplift, DSR deflactado, CPCV-OOS y PBO — el gate completo de la casa."""
    base = df_long["pnl_r"].to_numpy(float)
    seg = base[mask.to_numpy(bool)]
    if len(seg) < 30:
        print("  [%s] n=%d <30 — sin poder estadístico" % (label, len(seg)))
        return None
    upl = seg.mean() - base.mean()
    d = _dsr(seg, base, n_trials)
    # CPCV: mediana OOS del uplift del subset en cada camino de test
    paths = vg.cpcv_paths(len(base), n_groups=6, n_test_groups=2)
    m = mask.to_numpy(bool)
    oos = []
    for _, te in paths:
        te = np.asarray(te, int)
        if m[te].sum() >= 5:
            oos.append(base[te][m[te]].mean() - base[te].mean())
    oos = np.asarray(oos, float)
    # PBO: bloques temporales x configs {gated, complemento}
    nb = 12
    blocks = np.array_split(np.arange(len(base)), nb)
    perf = np.full((nb, 2), np.nan)
    for i, b in enumerate(blocks):
        b = np.asarray(b, int)
        if m[b].sum() >= 3:
            perf[i, 0] = base[b][m[b]].mean()
        if (~m[b]).sum() >= 3:
            perf[i, 1] = base[b][~m[b]].mean()
    perf = perf[~np.isnan(perf).any(axis=1)]
    p = vg.pbo(perf) if len(perf) >= 6 else float("nan")
    ok_dsr = bool(d and d["significant"])
    ok_oos = len(oos) > 0 and float(np.median(oos)) > 0
    ok_pbo = (not np.isnan(p)) and p < 0.5
    print("  [%s] n=%d  expR=%+.3f (base %+.3f, uplift %+.3f)" % (label, len(seg), seg.mean(), base.mean(), upl))
    print("        DSR=%s %s · CPCV-OOS med=%+.3f (%d paths, %.0f%%>0) %s · PBO=%.2f %s"
          % ("%.3f" % d["dsr"] if d else "n/a", "✓" if ok_dsr else "✗",
             float(np.median(oos)) if len(oos) else float("nan"), len(oos),
             100 * float((oos > 0).mean()) if len(oos) else 0, "✓" if ok_oos else "✗",
             p, "✓" if ok_pbo else "✗"))
    verdict = ok_dsr and ok_oos and ok_pbo
    print("        -> %s" % ("PASA el gate" if verdict else "NO PASA (o falta poder)"))
    return {"n": int(len(seg)), "uplift": float(upl), "dsr": d["dsr"] if d else None,
            "oos_med": float(np.median(oos)) if len(oos) else None, "pbo": float(p),
            "pass": bool(verdict)}


def slow_gate_report(df_long, mask, n_trials, label, n_blocks=40, boots=4000, seed=7):
    """Gate para REGÍMENES LENTOS (p.ej. NUPL: meses en una banda). El PBO/CSCV clásico
    no es computable ahí (bloques enteros de un solo lado) — NO por falta de cómputo,
    sino porque no hay varianza intra-bloque. Protocolo alterno, declarado por adelantado:
      (a) DSR deflactado (igual que siempre),
      (b) BOOTSTRAP DE BLOQUES contiguos (respeta la autocorrelación del régimen):
          P(uplift>0) sobre remuestreos de bloques temporales,
      (c) CONSISTENCIA POR MITADES temporales (uplift>0 en AMBAS mitades = ~2 ciclos).
    PASA sólo con (a) ✓ y (b) >=0.95 y (c) ambas mitades >0. Más estricto en espíritu,
    computable en régimen lento. El juez final sigue siendo el forward."""
    rng = np.random.default_rng(seed)
    base = df_long["pnl_r"].to_numpy(float)
    m = mask.to_numpy(bool)
    if m.sum() < 30:
        print("  [%s] n=%d <30 — sin poder" % (label, int(m.sum())))
        return None
    upl = base[m].mean() - base.mean()
    d = _dsr(base[m], base, n_trials)
    blocks = np.array_split(np.arange(len(base)), n_blocks)
    ups = []
    for _ in range(boots):
        idx = np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))])
        bm = m[idx]
        if bm.sum() >= 10 and (~bm).sum() >= 10:
            ups.append(base[idx][bm].mean() - base[idx].mean())
    ups = np.asarray(ups, float)
    p_pos = float((ups > 0).mean()) if len(ups) else float("nan")
    half = len(base) // 2
    h = []
    for sl in (slice(0, half), slice(half, None)):
        bm, bb = m[sl], base[sl]
        h.append(bb[bm].mean() - bb.mean() if bm.sum() >= 15 else float("nan"))
    ok_dsr = bool(d and d["significant"])
    ok_boot = (not np.isnan(p_pos)) and p_pos >= 0.95
    ok_half = all(not np.isnan(x) and x > 0 for x in h)
    print("  [%s] n=%d  expR=%+.3f (base %+.3f, uplift %+.3f)" % (label, int(m.sum()), base[m].mean(), base.mean(), upl))
    print("        DSR=%s %s · bootstrap-bloques P(uplift>0)=%.3f (%d resamples) %s · mitades: %+.3f / %+.3f %s"
          % ("%.3f" % d["dsr"] if d else "n/a", "✓" if ok_dsr else "✗", p_pos, len(ups),
             "✓" if ok_boot else "✗", h[0], h[1], "✓" if ok_half else "✗"))
    verdict = ok_dsr and ok_boot and ok_half
    print("        -> %s" % ("PASA (protocolo régimen-lento)" if verdict else "NO PASA (o falta poder)"))
    return {"n": int(m.sum()), "uplift": float(upl), "dsr": d["dsr"] if d else None,
            "p_boot": p_pos, "halves": h, "pass": bool(verdict)}


def bucket_table(df, col, edges, labels, title):
    print("\n  %s (LONGS | contraste SHORTS):" % title)
    for lo, hi, lab in zip(edges[:-1], edges[1:], labels):
        for dirn, name in ((1, "L"), (-1, "S")):
            s = df[(df.direction == dirn) & (df[col] >= lo) & (df[col] < hi)]
            if dirn == 1:
                line = "    %-22s L: n=%4d expR=%+.3f WR=%2.0f%%" % (
                    lab, len(s), s.pnl_r.mean() if len(s) else float("nan"),
                    100 * (s.pnl_r > 0).mean() if len(s) else 0)
            else:
                line += "   | S: n=%4d expR=%+.3f" % (len(s), s.pnl_r.mean() if len(s) else float("nan"))
        print(line)


# ---------------------------------------------------------------- experimentos
def exp_funding(fires, lg=LG):
    print("\n================ EXP 1 — FUNDING GATE (longs) ================")
    out = []
    for slug, sym in CUBES.items():
        p = os.path.join(lg, "fund_%s.parquet" % sym)
        if not os.path.exists(p):
            continue
        f = pd.read_parquet(p)
        fts, fr = f.ts.to_numpy(np.int64), f.rate.to_numpy(float)
        # percentil causal 90d + sostenida (media de las últimas 3)
        sub = fires[fires.sym == slug].copy()
        rates, pctls, sus = [], [], []
        for t in sub.ts.to_numpy(np.int64):
            i = np.searchsorted(fts, t, side="right") - 1
            if i < 0:
                rates.append(np.nan); pctls.append(np.nan); sus.append(np.nan)
                continue
            rates.append(fr[i])
            w = fr[max(0, i - 269):i + 1]          # ~90d de eventos 8h
            pctls.append(float((w <= fr[i]).mean()))
            sus.append(float(np.mean(fr[max(0, i - 2):i + 1])))
        sub["rate"], sub["pctl"], sub["sus"] = rates, pctls, sus
        out.append(sub)
    d = pd.concat(out, ignore_index=True).dropna(subset=["rate"]).sort_values("ts").reset_index(drop=True)
    print("  fires con funding causal: %d / %d" % (len(d), len(fires)))
    bucket_table(d, "rate", [-1, 0, BASELINE_8H, APR15_8H, 1],
                 ["funding <= 0", "0 .. baseline(0.01%)", "baseline .. 15% APR", ">= 15% APR"],
                 "expR por nivel de funding en la entrada")
    longs = d[d.direction == 1].reset_index(drop=True)
    res = {}
    res["neg_neutral"] = gate_report(longs, longs.rate <= BASELINE_8H, 5, "LONG & funding<=baseline")
    res["no_crowded"] = gate_report(longs, longs.sus < APR15_8H, 5, "LONG & NO sostenido>=15%APR (veto cola)")
    res["pctl_low"] = gate_report(longs, longs.pctl <= 0.5, 5, "LONG & funding pctl90d<=0.5")
    return res


def exp_breadth(fires, lg=LG):
    print("\n================ EXP 2 — ALT-SEASON BREADTH GATE (longs de alts) ================")
    closes = {}
    for slug, sym in CUBES.items():
        p = os.path.join(lg, "daily_%s.parquet" % sym)
        if os.path.exists(p):
            closes[slug] = pd.read_parquet(p)
    if "BTC" not in closes:
        print("  (falta daily BTC — corre --fetch)")
        return {}
    # panel diario de retornos 90d
    idx = closes["BTC"].ts.to_numpy(np.int64)
    r90 = {}
    for slug, c in closes.items():
        s = pd.Series(c.close.to_numpy(float), index=c.ts.to_numpy(np.int64))
        s = s.reindex(idx).ffill()
        r90[slug] = s / s.shift(90) - 1.0
    alts = [s for s in r90 if s not in MAJORS]
    beat = pd.DataFrame({s: (r90[s] > r90["BTC"]).astype(float).where(r90[s].notna()) for s in alts})
    breadth = beat.mean(axis=1, skipna=True)          # % de alts que le ganan a BTC (90d)
    bts, bval = idx, breadth.to_numpy(float)
    d = fires.copy()
    # causal: breadth del CIERRE del día anterior
    d["breadth"] = [_asof(bts, bval, t - 86_400_000) for t in d.ts.to_numpy(np.int64)]
    d = d.dropna(subset=["breadth"]).sort_values("ts").reset_index(drop=True)
    d_alt = d[~d.sym.isin(MAJORS)].reset_index(drop=True)
    print("  fires de ALTS con breadth causal: %d (majors de contraste: %d)"
          % (len(d_alt), len(d) - len(d_alt)))
    bucket_table(d_alt, "breadth", [0, 0.25, 0.5, 0.75, 1.01],
                 ["<25% (BTC season)", "25-50%", "50-75%", ">=75% (altseason)"],
                 "ALTS: expR por breadth 90d (día previo)")
    longs = d_alt[d_alt.direction == 1].reset_index(drop=True)
    res = {}
    res["alt50"] = gate_report(longs, longs.breadth >= 0.5, 4, "ALT-LONG & breadth>=50%")
    res["alt75"] = gate_report(longs, longs.breadth >= 0.75, 4, "ALT-LONG & breadth>=75% (altseason)")
    mj = d[(d.sym.isin(MAJORS)) & (d.direction == 1)].reset_index(drop=True)
    if len(mj) > 50:
        print("  contraste majors-LONG breadth>=0.5: expR=%+.3f (n=%d) vs base %+.3f"
              % (mj[mj.breadth >= 0.5].pnl_r.mean(), int((mj.breadth >= 0.5).sum()), mj.pnl_r.mean()))
    return res


def exp_cvd_ortho(fires, kl_dir="data/okx"):
    print("\n================ EXP 3 — CVD ORTOGONALIZADO (flow sin chase, longs) ================")
    out = []
    for slug, sym in CUBES.items():
        p = os.path.join(kl_dir, "kl_hist_%s.parquet" % sym)
        if not os.path.exists(p):
            continue
        k = pd.read_parquet(p)
        if "taker_buy_base" not in k.columns:
            continue
        kts = k.ts.to_numpy(np.int64)
        buy = k.taker_buy_base.to_numpy(float)
        sell = (k.volume.to_numpy(float) - buy).clip(min=0)
        close = k.close.to_numpy(float)
        sub = fires[fires.sym == slug].copy()
        imb, pret = [], []
        for t in sub.ts.to_numpy(np.int64):
            j = np.searchsorted(kts, t)                 # barras ESTRICTAMENTE antes
            if j < 25:
                imb.append(np.nan); pret.append(np.nan)
                continue
            w = slice(j - 24, j)
            f = fc.cvd_features(pd.DataFrame({"ts": kts[w], "buy_vol": buy[w], "sell_vol": sell[w]}), win=24)
            imb.append(f["imbalance"])
            pret.append(close[j - 1] / close[j - 24] - 1.0)
        sub["imb"], sub["pret"] = imb, pret
        out.append(sub)
    d = pd.concat(out, ignore_index=True).dropna(subset=["imb"]).sort_values("ts").reset_index(drop=True)
    print("  fires con CVD+retorno causal: %d / %d (símbolos con kl_hist)" % (len(d), len(fires)))
    longs = d[d.direction == 1].reset_index(drop=True)
    conf = longs[longs.imb >= 0.55].reset_index(drop=True)     # CVD confirma el long
    print("  LONGS CVD-confirmados (imb>=0.55): n=%d expR=%+.3f | no-confirmados: n=%d expR=%+.3f"
          % (len(conf), conf.pnl_r.mean(), (longs.imb < 0.55).sum(), longs[longs.imb < 0.55].pnl_r.mean()))
    bucket_table(pd.concat([conf.assign(direction=1)]), "pret", [-1, 0, 0.01, 1],
                 ["pret<=0 (flow SIN chase)", "0..1% (chase leve)", ">1% (chase)"],
                 "LONGS confirmados: expR por retorno previo (24 barras)")
    res = {}
    res["sin_chase"] = gate_report(conf, conf.pret <= 0, 3, "LONG CVD✓ & SIN chase (pret<=0)")
    return res


def exp_onchain(fires, lg=LG):
    print("\n================ EXP 4 — THROTTLE ON-CHAIN (NUPL, longs) ================")
    p = os.path.join(lg, "onchain_btc.parquet")
    if not os.path.exists(p):
        print("  (falta onchain — corre --fetch)")
        return {}
    oc = pd.read_parquet(p)
    nupl = ((oc.mc - oc.rc) / oc.mc).to_numpy(float)
    ots = oc.ts.to_numpy(np.int64)
    d = fires.copy()
    d["nupl"] = [_asof(ots, nupl, t - 86_400_000) for t in d.ts.to_numpy(np.int64)]  # día previo
    d = d.dropna(subset=["nupl"]).sort_values("ts").reset_index(drop=True)
    print("  fires con NUPL causal (día previo): %d / %d" % (len(d), len(fires)))
    bucket_table(d, "nupl", [-2, 0, 0.25, 0.5, 0.75, 2],
                 ["<0 capitulación", "0-0.25 esperanza", "0.25-0.5 optimismo",
                  "0.5-0.75 codicia", ">=0.75 euforia"],
                 "expR por banda NUPL de BTC (throttle de mercado)")
    longs = d[d.direction == 1].reset_index(drop=True)
    res = {}
    res["no_euforia"] = gate_report(longs, longs.nupl < 0.75, 3, "LONG & NUPL<0.75 (veto euforia)")
    res["bajo_codicia"] = gate_report(longs, longs.nupl < 0.5, 3, "LONG & NUPL<0.5")
    # régimen LENTO: el CSCV/PBO clásico no computa (bloques de un solo lado) ->
    # protocolo alterno declarado (bootstrap de bloques + mitades), mismo espíritu anti-overfit.
    res["bajo_codicia_slow"] = slow_gate_report(longs, longs.nupl < 0.5, 3,
                                                "LONG & NUPL<0.5 [protocolo régimen-lento]")
    return res


# ---------------------------------------------------------------- self-test
def _self_test():
    import tempfile
    rng = np.random.default_rng(0)
    lg = tempfile.mkdtemp()
    n = 3000
    t0 = 1_600_000_000_000
    fires = pd.DataFrame({
        "sym": rng.choice(["SOL", "BTC"], n),
        "ts": t0 + np.sort(rng.integers(0, 4 * 365 * 86_400_000, n)),
        "direction": rng.choice([1, -1], n),
        "pnl_r": rng.choice([-1.0, 2.0], n)})
    # funding sintético 8h + daily + onchain
    fts = np.arange(t0 - 90 * 86_400_000, fires.ts.max() + 1, 8 * 3_600_000, dtype=np.int64)
    for sym in ("SOLUSDT", "BTCUSDT"):
        pd.DataFrame({"ts": fts, "rate": rng.normal(1e-4, 2e-4, len(fts))}).to_parquet(
            os.path.join(lg, "fund_%s.parquet" % sym), index=False)
    dts = np.arange(t0 - 200 * 86_400_000, fires.ts.max() + 1, 86_400_000, dtype=np.int64)
    for slug, sym in CUBES.items():
        if slug in ("SOL", "BTC"):
            pd.DataFrame({"ts": dts, "close": 100 * np.exp(np.cumsum(rng.normal(0, .02, len(dts))))}
                         ).to_parquet(os.path.join(lg, "daily_%s.parquet" % sym), index=False)
    pd.DataFrame({"ts": dts, "mc": 1e12 * np.exp(np.cumsum(rng.normal(0, .01, len(dts)))),
                  "rc": 8e11 * np.ones(len(dts))}).to_parquet(
        os.path.join(lg, "onchain_btc.parquet"), index=False)
    r1 = exp_funding(fires, lg=lg)
    r4 = exp_onchain(fires, lg=lg)
    assert r1 and any(v for v in r1.values())
    assert r4 and any(v for v in r4.values())
    # breadth con solo 1 alt (SOL): igual corre y reporta
    exp_breadth(fires, lg=lg)
    print("\nself-test OK (funding/breadth/onchain corren end-to-end en sintético)")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--exp", choices=["funding", "breadth", "cvd_ortho", "onchain", "all"])
    p.add_argument("--tp", default="tp1")
    p.add_argument("--horizon", type=int, default=96)
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)
    if a.self_test:
        return _self_test()
    if a.fetch:
        cmd_fetch()
        return 0
    if not a.exp:
        print("usa --fetch, --exp all|funding|breadth|cvd_ortho|onchain, o --self-test")
        return 0
    fires = load_fires(tp=a.tp, horizon=a.horizon)
    print("fires cargados: %d (%s/h%d, %d símbolos) — LONGS %d / SHORTS %d"
          % (len(fires), a.tp, a.horizon, fires.sym.nunique(),
             (fires.direction == 1).sum(), (fires.direction == -1).sum()))
    if a.exp in ("funding", "all"):
        exp_funding(fires)
    if a.exp in ("breadth", "all"):
        exp_breadth(fires)
    if a.exp in ("cvd_ortho", "all"):
        exp_cvd_ortho(fires)
    if a.exp in ("onchain", "all"):
        exp_onchain(fires)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
