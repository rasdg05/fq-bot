# -*- coding: utf-8 -*-
"""
================================================================================
  fetch_binance_vision_klines — OHLCV 5m REAL histórico (GRATIS, sin comprar)
  by RasDG_Sol + Claude
================================================================================
F1 (residual de impacto raíz-cuadrada) necesita, por barra: el RETORNO realizado,
la VOLATILIDAD y la PARTICIPACIÓN del flujo firmado. El dataset `klines` de Binance
Vision lo da TODO en un archivo liviano (una fila por barra, no tick-level como
aggTrades): incluye `taker_buy_base_volume`, así que el flujo firmado neto sale de
ahí mismo (signed = 2·taker_buy − volume), sin bajar los aggTrades pesados.

  futures/um/daily/klines/<SYM>/5m/<SYM>-5m-<YYYY-MM-DD>.zip
  cols: open_time, open, high, low, close, volume, close_time, quote_volume,
        count, taker_buy_volume, taker_buy_quote_volume, ignore

Espejo de fetch_binance_vision_cvd: baja DIARIOS concurrentes, cachea 5m compacto,
re-ejecutable (saltea días ya hechos). Tolera el header opcional de los CSV nuevos.

Uso:
  python tools/fetch_binance_vision_klines.py SOLUSDT --start 2021-01-01 --end 2026-06-27
Salida: $FQ_CVD_DIR/kl_hist_<SYM>.parquet  (ts, open, high, low, close, volume,
        taker_buy_base) barras 5m.
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

import numpy as np
import pandas as pd

BASE = "https://data.binance.vision/data/futures/um/daily/klines"
DEFAULT_DIR = os.environ.get("FQ_CVD_DIR") or ("/data" if os.path.isdir("/data") else "data/okx")
COLS = ["ts", "open", "high", "low", "close", "volume", "taker_buy_base"]
_RAW = ["open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def _days(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _klines_day(sym, d):
    """Baja el klines 5m del día -> [ts, open, high, low, close, volume, taker_buy_base].
    None si el archivo no existe (día previo a la inception / aún no subido)."""
    url = "%s/%s/5m/%s-5m-%s.zip" % (BASE, sym, sym, d.isoformat())
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            df = pd.read_csv(z.open(z.namelist()[0]), header=None, names=_RAW)
    except Exception:
        return None
    if df.empty:
        return None
    # los CSV nuevos a veces traen header: la 1ra fila no parsea a número -> se cae sola
    df["ts"] = pd.to_numeric(df["open_time"], errors="coerce")
    for c in ("open", "high", "low", "close", "volume", "taker_buy_volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["ts", "close", "volume"])
    df["ts"] = df["ts"].astype("int64")
    df["taker_buy_base"] = df["taker_buy_volume"].fillna(0.0)
    return df[COLS]


def fetch(sym, start, end, out_dir=DEFAULT_DIR, workers=None):
    path = os.path.join(out_dir, "kl_hist_%s.parquet" % sym)
    os.makedirs(out_dir, exist_ok=True)
    have = pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame(columns=COLS)
    done_days = set((pd.to_datetime(have["ts"], unit="ms").dt.date.unique()).tolist()) if len(have) else set()
    parts = [have] if len(have) else []
    todo = [d for d in _days(start, end) if d not in done_days]
    w = workers or int(os.environ.get("FQ_KL_WORKERS", "12"))
    n_new = 0
    with ThreadPoolExecutor(max_workers=max(1, w)) as ex:
        for g in ex.map(lambda d: _klines_day(sym, d), todo):
            if g is None:
                continue
            parts.append(g)
            n_new += 1
            if n_new % 100 == 0:
                print("[kl-hist] %s: %d días nuevos..." % (sym, n_new))
    if not parts:
        print("[kl-hist] %s: sin data" % sym)
        return path
    out = (pd.concat(parts, ignore_index=True)
             .drop_duplicates("ts").sort_values("ts").reset_index(drop=True))
    tmp = path + ".tmp"
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    span = (out.ts.max() - out.ts.min()) / 8.64e7
    print("[kl-hist] %s: +%d días -> %d barras 5m (%.0f días) %s"
          % (sym, n_new, len(out), span, path))
    return path


def main(argv):
    p = argparse.ArgumentParser(description="Klines 5m histórico real desde data.binance.vision (gratis).")
    p.add_argument("symbol", help="p.ej. SOLUSDT, BTCUSDT")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--out-dir", default=DEFAULT_DIR)
    a = p.parse_args(argv)
    fetch(a.symbol, date.fromisoformat(a.start), date.fromisoformat(a.end), a.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
