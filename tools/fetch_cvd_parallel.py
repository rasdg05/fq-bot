#!/usr/bin/env python3
"""fetch_cvd_parallel — baja cvd_hist (5m buy/sell vol) en paralelo por día.

Envuelve `_agg_day_to_5m` de fetch_binance_vision_cvd con un ThreadPool para
acelerar el rango (los aggTrades diarios son independientes). Mismo formato de
salida que el fetcher serie: parquet [ts, buy_vol, sell_vol].

  python tools/fetch_cvd_parallel.py SOLUSDT --start 2024-06-01 --end 2026-06-26 \
         --out data/cvd_hist_SOLUSDT.parquet --workers 12
"""
import argparse
import datetime
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

sys.path.insert(0, "tools")
import fetch_binance_vision_cvd as f  # noqa: E402


def _days(start, end):
    d = start
    while d <= end:
        yield d
        d += datetime.timedelta(days=1)


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("symbol")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--workers", type=int, default=12)
    a = p.parse_args(argv)

    start = datetime.date.fromisoformat(a.start)
    end = datetime.date.fromisoformat(a.end)
    days = list(_days(start, end))
    total = len(days)
    print("[%s] %d días %s..%s  (%d workers)" % (a.symbol, total, start, end, a.workers), flush=True)

    rows = []
    done = 0
    fails = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(f._agg_day_to_5m, a.symbol, d): d for d in days}
        for fut in as_completed(futs):
            d = futs[fut]
            done += 1
            try:
                bars = fut.result()
                if bars is not None and len(bars):
                    rows.append(bars)
            except Exception as e:  # día faltante / 404 — se omite
                fails += 1
                if fails <= 5:
                    print("  miss %s: %s" % (d, str(e)[:80]), flush=True)
            if done % 50 == 0:
                print("  %d/%d  (%d miss)" % (done, total, fails), flush=True)

    if not rows:
        print("SIN datos.", flush=True)
        return 1
    df = pd.concat(rows, ignore_index=True).sort_values("ts").reset_index(drop=True)
    df = df.drop_duplicates("ts").reset_index(drop=True)
    df.to_parquet(a.out, index=False)
    print("OK %s  filas=%d  span %s..%s  (%d días miss)" % (
        a.out, len(df),
        pd.to_datetime(df.ts.min(), unit="ms"), pd.to_datetime(df.ts.max(), unit="ms"), fails), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
