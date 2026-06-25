# -*- coding: utf-8 -*-
"""
trailing_backtest — backtest PATH-BASED de salida con trailing stop vs tp4 fijo.

POR QUE existe: el cubo trae mfe_r/mae_r de HORIZONTE COMPLETO — incluyen el
movimiento POST-salida e ignoran el orden MFE/MAE. NO sirven para evaluar una
salida (un MFE de +22R despues de pegar el stop es inalcanzable). Esto camina las
velas REALES por trade, respetando el stop, y simula varios trailings contra el
tp4 fijo.

Geometria del cubo: entry_price, stop_price (-> R=|entry-stop|), direction (+1/-1),
celda tp4/h576 como baseline (pnl_r). Symbol-agnostico: corre sobre cualquier
(cubo, velas). SOL/BTC ya; ETH apenas se coseche su cubo (queda a punto: el
autodetect lo suma solo cuando aparece cosecha_cubes/tp_cube_ETH_USDT.parquet).

No-lookahead: el trailing en la barra i usa el pico HASTA i-1; recien ahi se chequea
el low/high de i contra el stop. El fill se asume al nivel del stop (radar; un gap
llenaria peor).

Uso:
  python tools/trailing_backtest.py                  # autodetect cosecha_cubes + data/okx
  python tools/trailing_backtest.py SOL_USDT BTC_USDT # simbolos puntuales
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

TP, HOR = "tp4", 576
# config: nombre -> (trail_R detras del pico, be_R = mover a breakeven tras +be_R)
CONFIGS = {
    "trail1R":    (1.0, None),
    "trail1.5R":  (1.5, None),
    "trail2R":    (2.0, None),
    "trail2.5R":  (2.5, None),
    "trail3R":    (3.0, None),
    "trail4R":    (4.0, None),
    "BE+trail2R": (2.0, 1.0),
}


def _sim(entry, stop, dirn, high, low, close, trail_R, be_R):
    R = abs(entry - stop)
    if R <= 0 or len(high) < 5:
        return np.nan
    if dirn == 1:
        peak = np.maximum.accumulate(high)
        peak_prev = np.concatenate([[entry], peak[:-1]])     # pico ANTES de la barra
        eff = np.maximum(stop, peak_prev - trail_R * R)      # ratchea hacia arriba
        if be_R is not None:
            eff = np.where(peak_prev >= entry + be_R * R, np.maximum(eff, entry), eff)
        hit = low <= eff
        if hit.any():
            i = int(np.argmax(hit))
            return (eff[i] - entry) / R
        return (close[-1] - entry) / R
    else:
        trough = np.minimum.accumulate(low)
        trough_prev = np.concatenate([[entry], trough[:-1]])
        eff = np.minimum(stop, trough_prev + trail_R * R)    # ratchea hacia abajo
        if be_R is not None:
            eff = np.where(trough_prev <= entry - be_R * R, np.minimum(eff, entry), eff)
        hit = high >= eff
        if hit.any():
            i = int(np.argmax(hit))
            return (entry - eff[i]) / R
        return (entry - close[-1]) / R


def run_symbol(cube_path, candle_path):
    c = pd.read_parquet(cube_path)
    c["tp"] = c["tp"].astype(str)
    c["horizon"] = c["horizon"].astype(int)
    e = c[(c.tp == TP) & (c.horizon == HOR)].copy()
    e["ts"] = pd.to_datetime(e["entry_ts"])
    oh = pd.read_parquet(candle_path).sort_values("timestamp").reset_index(drop=True)
    oh["ts"] = pd.to_datetime(oh["timestamp"], unit="ms")
    ts = oh["ts"].values
    H, L, C = oh["high"].values, oh["low"].values, oh["close"].values
    e = e[(e.ts >= oh["ts"].min()) & (e.ts <= oh["ts"].max())]
    base, res, cover = [], {k: [] for k in CONFIGS}, 0
    for _, r in e.iterrows():
        i0 = int(np.searchsorted(ts, np.datetime64(r.ts)))
        if i0 >= len(H) - 5:
            continue
        j = min(i0 + HOR, len(H))
        h, l, cl = H[i0:j], L[i0:j], C[i0:j]
        cover += 1
        base.append(r.pnl_r)
        for k, (tr, be) in CONFIGS.items():
            res[k].append(_sim(r.entry_price, r.stop_price, int(r.direction), h, l, cl, tr, be))
    return base, res, cover, len(e)


def _stat(v):
    v = np.asarray(v, dtype=float)
    v = v[~np.isnan(v)]
    if len(v) == 0:
        return float("nan"), float("nan"), 0
    return v.mean(), (v > 0).mean() * 100, len(v)


def main(argv):
    syms = argv[1:] if len(argv) > 1 else None
    pairs = []
    for cube in sorted(glob.glob("cosecha_cubes/tp_cube_*.parquet")):
        sym = os.path.basename(cube).replace("tp_cube_", "").replace(".parquet", "")
        if syms and sym not in syms:
            continue
        base = sym.split("_")[0]
        cands = glob.glob("data/okx/*%s*_5m.parquet" % base)
        pairs.append((sym, cube, cands[0] if cands else None))

    allb, allres = [], {k: [] for k in CONFIGS}
    for sym, cube, cand in pairs:
        if not cand or not os.path.exists(cand):
            print("  %s: sin velas (data/okx/*%s*_5m), skip" % (sym, sym.split("_")[0]))
            continue
        base, res, cover, nev = run_symbol(cube, cand)
        if cover < 10:
            print("  %s: cobertura %d insuficiente (velas no cubren los eventos)" % (sym, cover))
            continue
        bm, bwr, _ = _stat(base)
        print("\n### %s  (%d/%d eventos con velas) ###" % (sym, cover, nev))
        print("  tp4 fijo (baseline):  exp=%+.3f  WR=%.0f%%" % (bm, bwr))
        for k in CONFIGS:
            m, wr, _ = _stat(res[k])
            print("  %-13s exp=%+.3f  WR=%.0f%%  vs tp4: %+.3fR%s"
                  % (k, m, wr, m - bm, "  <<<" if m > bm else ""))
        allb += base
        for k in CONFIGS:
            allres[k] += res[k]

    if len([p for p in pairs if p[2]]) > 1 and allb:
        bm, bwr, n = _stat(allb)
        print("\n### POOLED (%d eventos) ###" % n)
        print("  tp4 fijo: exp=%+.3f  WR=%.0f%%" % (bm, bwr))
        for k in CONFIGS:
            m, _, _ = _stat(allres[k])
            print("  %-13s exp=%+.3f  vs tp4: %+.3fR%s" % (k, m, m - bm, "  <<<" if m > bm else ""))
    print("\n(radar si las velas no cubren toda la historia del cubo; "
          "salida = stop taker, sin el +0.04R del TP-maker)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
