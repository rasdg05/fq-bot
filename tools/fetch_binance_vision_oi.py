# -*- coding: utf-8 -*-
"""
================================================================================
  fetch_binance_vision_oi — Open Interest REAL histórico (GRATIS, sin comprar)
  by RasDG_Sol + Claude
================================================================================
Espejo de fetch_binance_vision_cvd, pero para OI (posicionamiento). El archivo
público de Binance (data.binance.vision) publica el dataset `metrics` de futuros
con el OI muestreado cada 5m (sum_open_interest_value, USD) DESDE ~2020-09 — misma
fuente que el CVD. Por eso el OI se puede DSR-validar en backtest IGUAL que el CVD,
sin comprar nada ni esperar el colector forward.

Bonus del MISMO dataset (gratis, ya quedan en el parquet por si se validan después):
  toptrader_ls — long/short ratio de top traders
  taker_ls     — taker long/short volume ratio

Los metrics ya vienen a 5m (~288 filas/día, archivos chicos) -> mucho más liviano
que los aggTrades del CVD; no hay que agregar tick-level.

Uso:
  python tools/fetch_binance_vision_oi.py BTCUSDT --start 2021-01-01 --end 2026-06-26
Salida: $FQ_AGG_OI_DIR/oi_hist_<SYM>.parquet  (ts, oi_usd, toptrader_ls, taker_ls) 5m.
================================================================================
"""
import argparse
import io
import os
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pandas as pd

BASE = "https://data.binance.vision/data/futures/um/daily/metrics"
DEFAULT_DIR = os.environ.get("FQ_AGG_OI_DIR") or ("/data" if os.path.isdir("/data") else "data/okx")
COLS = ["ts", "oi_usd", "toptrader_ls", "taker_ls"]


def _days(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _day(sym, d):
    """Baja el metrics 5m del día -> [ts, oi_usd, toptrader_ls, taker_ls]. None si el
    archivo no existe (día previo a la inception / aún no subido)."""
    url = "%s/%s/%s-metrics-%s.zip" % (BASE, sym, sym, d.isoformat())
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            df = pd.read_csv(z.open(z.namelist()[0]))
    except Exception:
        return None
    if df.empty:
        return None
    df.columns = [c.strip().lower() for c in df.columns]
    if "create_time" not in df.columns or "sum_open_interest_value" not in df.columns:
        return None
    ts = (pd.to_datetime(df["create_time"], utc=True)
            .values.astype("datetime64[ms]").astype("int64"))
    out = pd.DataFrame({
        "ts": ts,
        "oi_usd": pd.to_numeric(df["sum_open_interest_value"], errors="coerce"),
        "toptrader_ls": pd.to_numeric(df.get("sum_toptrader_long_short_ratio"), errors="coerce"),
        "taker_ls": pd.to_numeric(df.get("sum_taker_long_short_vol_ratio"), errors="coerce"),
    })
    return out.dropna(subset=["oi_usd"])


def fetch(sym, start, end, out_dir=DEFAULT_DIR, workers=None):
    path = os.path.join(out_dir, "oi_hist_%s.parquet" % sym)
    os.makedirs(out_dir, exist_ok=True)
    have = pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame(columns=COLS)
    done_days = set(pd.to_datetime(have["ts"], unit="ms").dt.date.unique().tolist()) if len(have) else set()
    parts = [have] if len(have) else []
    todo = [d for d in _days(start, end) if d not in done_days]
    # descarga CONCURRENTE (network-bound). Cada día es independiente. Override por
    # env FQ_OI_WORKERS; default 12. Los metrics son chicos -> esto vuela.
    w = workers or int(os.environ.get("FQ_OI_WORKERS", "12"))
    n_new = 0
    with ThreadPoolExecutor(max_workers=max(1, w)) as ex:
        for g in ex.map(lambda d: _day(sym, d), todo):
            if g is None or g.empty:
                continue
            parts.append(g)
            n_new += 1
            if n_new % 100 == 0:
                print("[oi-hist] %s: %d días nuevos..." % (sym, n_new))
    if not parts:
        print("[oi-hist] %s: sin data" % sym)
        return path
    out = (pd.concat(parts, ignore_index=True)
             .drop_duplicates("ts").sort_values("ts").reset_index(drop=True))
    tmp = path + ".tmp"
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    span = (out.ts.max() - out.ts.min()) / 8.64e7
    print("[oi-hist] %s: +%d días -> %d barras 5m (%.0f días) %s"
          % (sym, n_new, len(out), span, path))
    return path


def main(argv):
    p = argparse.ArgumentParser(description="OI histórico real desde data.binance.vision (gratis).")
    p.add_argument("symbol", help="p.ej. SOLUSDT, BTCUSDT")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--out-dir", default=DEFAULT_DIR)
    a = p.parse_args(argv)
    fetch(a.symbol, date.fromisoformat(a.start), date.fromisoformat(a.end), a.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
