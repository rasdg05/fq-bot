#!/usr/bin/env python3
"""fetch_dukascopy — baja OHLCV histórico de Dukascopy al formato del pipeline.

Escribe data/dukascopy/<sym>_<tf>.parquet [ts, open, high, low, close, volume]
(igual que build_dataset) para que la cosecha lo CACHEE y construya el cubo —
desacople data/venue: validamos TradFi sobre esta historia profunda; la señal se
ejecuta en el perp (MEXC). Transfiere KL (precio) + base; NO el order-flow (CVD).

  python tools/fetch_dukascopy.py --symbol XAU/USD --tf 5m --years 2
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

INTERVAL_ATTR = {"1m": "INTERVAL_MIN_1", "5m": "INTERVAL_MIN_5",
                 "15m": "INTERVAL_MIN_15", "1h": "INTERVAL_HOUR_1"}


def _resolve(I, keyword):
    k = keyword.upper().replace("/", "").replace("_", "")
    return [n for n in dir(I) if "INSTRUMENT" in n and k in n.upper().replace("_", "")]


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True, help="p.ej. XAU/USD, LIGHT, USA500")
    p.add_argument("--tf", default="5m")
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)

    import dukascopy_python as dk
    from dukascopy_python import instruments as I
    INTERVAL = getattr(dk, INTERVAL_ATTR.get(a.tf, "INTERVAL_MIN_5"))
    OFFER = getattr(dk, "OFFER_SIDE_BID")

    cands = _resolve(I, a.symbol)
    if not cands:
        print("instrumento NO resuelto para '%s'. Candidatos IDX (para S&P/Nasdaq):" % a.symbol)
        for n in sorted(dir(I)):
            if "INSTRUMENT_IDX" in n:
                print("   ", n)
        return 1
    inst_name = cands[0]
    inst = getattr(I, inst_name)
    print("[dukascopy] %s -> %s  (tf=%s, %.1f años)" % (a.symbol, inst_name, a.tf, a.years), flush=True)

    end = datetime.now(timezone.utc).replace(tzinfo=None)
    start = end - timedelta(days=int(a.years * 365))
    frames = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=90), end)
        try:
            df = dk.fetch(inst, INTERVAL, OFFER, cur, nxt)
            n = 0 if df is None else len(df)
            if n:
                frames.append(df)
            print("  %s..%s -> %d barras" % (cur.date(), nxt.date(), n), flush=True)
        except Exception as e:
            print("  %s..%s ERR %s" % (cur.date(), nxt.date(), str(e)[:90]), flush=True)
        cur = nxt

    if not frames:
        print("SIN DATA")
        return 1
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df.columns = [c.lower() for c in df.columns]
    idx = pd.DatetimeIndex(df.index)
    ts_ms = (idx.asi8 // 1_000_000).astype("int64")
    vol = df["volume"] if "volume" in df.columns else 0.0
    out = pd.DataFrame({
        "ts": ts_ms,
        "open": df["open"].astype(float).values,
        "high": df["high"].astype(float).values,
        "low": df["low"].astype(float).values,
        "close": df["close"].astype(float).values,
        "volume": (vol.astype(float).values if hasattr(vol, "astype") else vol),
    }).dropna().reset_index(drop=True)

    if a.out:
        path = a.out
    else:
        sys.path.insert(0, ".")
        import bt_data
        path = bt_data.dataset_path("data", "dukascopy", a.symbol, a.tf)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.to_parquet(path, index=False)
    span = (out.ts.max() - out.ts.min()) / 1000 / 86400 if len(out) else 0
    print("OK %s  filas=%d  span %.0f días (%.1f años)  %s..%s" % (
        path, len(out), span, span / 365.0,
        datetime.utcfromtimestamp(out.ts.min() / 1000).date(),
        datetime.utcfromtimestamp(out.ts.max() / 1000).date()), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
