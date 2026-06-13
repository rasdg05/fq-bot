#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REGRADE OFFLINE: divergencia CVD (proxy) sobre los eventos de un run de
research YA persistido (tp_cube_<sym>.parquet) — CERO replays.

Responde "¿las señales del motor con divergencia CVD alineada en la entrada
pagan mas que el resto?" usando exactamente los mismos labels y folds que el
run original (tp/horizonte + walk-forward purgado), para que el contraste sea
de manzanas con manzanas:

  base        = todas las señales del pool
  alineada    = LONG con divergencia bullish / SHORT con bearish (el playbook
                "precio en el nivel + CVD no confirma el move en contra")
  contra      = divergencia del lado opuesto (candidata a VETO si marca losers)
  sin_div     = sin divergencia en la ventana
  sin_dato    = ventana de velas insuficiente (cobertura del dato, no opinion)

HONESTIDAD: pnl_r del cubo es PRE-coste (label triple-barrier); restar la
carga media de costes del run para leer neto (#30: ~0.23R SOL / ~0.28R BTC,
via --cost-burden-r). Esto es un RADAR (estandar §6.6 del RETRIEVAL_PLAN):
un subset bueno se explota solo tras replicar en datos frescos y sobrevivir
el protocolo de F2.6 (corrida de confirmacion + leakage + paper forward).

Velas: usa un parquet local (layout data/<ex>/<sym>_<tf>.parquet) si se pasa
--candles; si no, baja POR EVENTO la ventana causal desde OKX
(history-candles, after=entry_ts => solo velas cerradas ANTES de la entrada)
y la cachea en --cache para que re-correr sea gratis.

Uso:
  python tools/regrade_cvd.py --cube tp_cube_SOL_USDT.parquet \
      --inst SOL-USDT-SWAP --lookback 96 --mode range \
      --cache /tmp/cvd_SOL.parquet --cost-burden-r 0.2334
"""
import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bt_ablation as ab          # noqa: E402
import bt_quality as ql           # noqa: E402
import bt_walkforward as wf       # noqa: E402
import cvd                        # noqa: E402

OKX_HISTORY = "https://www.okx.com/api/v5/market/history-candles"
BAR_MS = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000}


def _fetch_window_okx(inst, entry_ts, bar="5m", limit=100, session=None):
    """Ventana causal: hasta `limit` velas con open < entry_ts (ya cerradas
    al momento de la entrada). Devuelve DataFrame OHLCV ascendente."""
    import requests
    sess = session or requests.Session()
    after_ms = int(pd.Timestamp(entry_ts).value // 1_000_000)
    r = sess.get(OKX_HISTORY, params={"instId": inst, "bar": bar,
                                      "after": str(after_ms),
                                      "limit": str(limit)}, timeout=30)
    r.raise_for_status()
    data = r.json().get("data", [])
    rows = [(int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]),
             float(x[5])) for x in data]
    df = pd.DataFrame(rows, columns=["ts_ms", "open", "high", "low", "close",
                                     "volume"]).sort_values("ts_ms")
    df["timestamp"] = pd.to_datetime(df["ts_ms"], unit="ms")
    return df.reset_index(drop=True)


def _windows(events, args):
    """ts_entrada -> DataFrame de ventana causal (parquet local o fetch OKX
    con cache). La clave del cache es el ts de entrada."""
    out = {}
    if args.candles:
        cd = pd.read_parquet(args.candles)
        cd = cd.sort_values("timestamp").reset_index(drop=True)
        ts = pd.to_datetime(cd["timestamp"])
        for ets in events["entry_ts"].unique():
            mask = ts < pd.Timestamp(ets)
            out[ets] = cd.loc[mask].tail(args.lookback)
        return out, "parquet"

    cache = pd.read_parquet(args.cache) if (args.cache and
                                            os.path.exists(args.cache)) else None
    have = set(pd.to_datetime(cache["entry_ts"]).unique()) if cache is not None else set()
    fetched = []
    todo = [e for e in events["entry_ts"].unique() if pd.Timestamp(e) not in have]
    if todo:
        import requests
        sess = requests.Session()
        print(f"  [okx] bajando ventana causal de {len(todo)} eventos "
              f"({args.inst}, {args.bar}, lookback<={args.lookback})...")
        for i, ets in enumerate(sorted(todo)):
            w = _fetch_window_okx(args.inst, ets, bar=args.bar,
                                  limit=max(args.lookback, 10), session=sess)
            w["entry_ts"] = pd.Timestamp(ets)
            fetched.append(w)
            time.sleep(args.sleep)
            if (i + 1) % 50 == 0:
                print(f"  [okx] {i + 1}/{len(todo)}")
    allw = pd.concat([x for x in (cache, *fetched) if x is not None and len(x)],
                     ignore_index=True) if (cache is not None or fetched) else None
    if args.cache and fetched and allw is not None:
        allw.to_parquet(args.cache, index=False)
        print(f"  [cache] {args.cache} ({len(allw)} velas)")
    if allw is None:
        return {}, "vacio"
    allw["entry_ts"] = pd.to_datetime(allw["entry_ts"])
    for ets, grp in allw.groupby("entry_ts"):
        out[ets] = grp.sort_values("ts_ms").tail(args.lookback)
    return out, "okx"


def _print_table(tag, pool, burden):
    rows = []
    for klass in ("base", "alineada", "contra", "sin_div", "sin_dato"):
        sub = pool if klass == "base" else pool[pool["cvd_class"] == klass]
        st = ql.subset_stats(sub["pnl_r"])
        st_net = dict(st)
        if burden is not None and st["n"] > 0:
            st_net["expectancy_r"] = st["expectancy_r"] - burden
        rows.append({"subset": klass, "n": st["n"], "wr": st["wr"],
                     "exp_r_precoste": st["expectancy_r"],
                     "exp_r_neto~": (st_net["expectancy_r"]
                                     if burden is not None else float("nan")),
                     "total_r": st["total_r"]})
    t = pd.DataFrame(rows)
    print(f"\n  -- {tag} --")
    print("  " + t.to_string(index=False,
                             float_format=lambda v: f"{v:7.4f}").replace("\n", "\n  "))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cube", required=True, help="tp_cube_<sym>.parquet del run")
    p.add_argument("--inst", required=True, help="instId OKX (p.ej. SOL-USDT-SWAP)")
    p.add_argument("--tp", default="tp1")
    p.add_argument("--horizon", type=int, default=288)
    p.add_argument("--bar", default="5m")
    p.add_argument("--lookback", type=int, default=96)
    p.add_argument("--mode", default="range", choices=["range", "body"])
    p.add_argument("--n-splits", type=int, default=7)
    p.add_argument("--embargo", type=int, default=8)
    p.add_argument("--candles", default=None,
                   help="parquet OHLCV local (si no, fetch OKX por evento)")
    p.add_argument("--cache", default=None, help="parquet cache de ventanas OKX")
    p.add_argument("--sleep", type=float, default=0.15,
                   help="pausa entre requests OKX (rate limit)")
    p.add_argument("--cost-burden-r", type=float, default=None,
                   help="carga media de costes del run en R (para columna neta)")
    args = p.parse_args()

    cube = pd.read_parquet(args.cube)
    labeled = cube[(cube["tp"] == args.tp)
                   & (cube["horizon"] == args.horizon)].copy()
    labeled = labeled.sort_values("entry_index").reset_index(drop=True)
    labeled["entry_ts"] = pd.to_datetime(labeled["entry_ts"])
    print(f"eventos {args.tp}/h{args.horizon}: {len(labeled)} "
          f"({labeled['entry_ts'].min()} .. {labeled['entry_ts'].max()})")

    folds, valid_index = wf.folds_from_labeled(
        labeled, n_splits=args.n_splits, embargo=args.embargo)
    pooled = ab.pooled_oos_trades(labeled, folds, valid_index=valid_index)
    st = ql.subset_stats(pooled["pnl_r"])
    print(f"  [verificacion] OOS pooled: n={st['n']} exp_r={st['expectancy_r']:.6f} "
          f"(contrastar con el [2.5/4] base del run original)")

    wins, source = _windows(labeled, args)
    print(f"  [velas] fuente={source} ventanas={len(wins)}")

    def classify(row):
        w = wins.get(row["entry_ts"])
        if w is None or len(w) < 10:
            return "sin_dato"
        div = cvd.detect_cvd_divergence(w, lookback=args.lookback,
                                        mode=args.mode)
        return cvd.divergence_alignment(div, row["direction"])

    labeled["cvd_class"] = labeled.apply(classify, axis=1)
    pooled = ab.pooled_oos_trades(labeled, folds, valid_index=valid_index)

    print(f"\n[regrade CVD] inst={args.inst} lookback={args.lookback} "
          f"mode={args.mode} (pnl_r PRE-coste del label {args.tp}/h{args.horizon}"
          + (f"; neta~ resta {args.cost_burden_r:.4f}R" if args.cost_burden_r
             else "") + ")")
    _print_table(f"TODAS las etiquetadas (n={len(labeled)})", labeled,
                 args.cost_burden_r)
    _print_table(f"OOS pooled (n={len(pooled)})", pooled, args.cost_burden_r)
    print("\n  NOTA: radar, no prueba (multiples cortes). Se explota solo via "
          "el protocolo F2.6 (RETRIEVAL_PLAN §6.8): replica en datos frescos "
          "+ corrida de confirmacion + leakage_ok + paper forward.")


if __name__ == "__main__":
    main()
