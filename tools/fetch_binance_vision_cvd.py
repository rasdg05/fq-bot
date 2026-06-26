# -*- coding: utf-8 -*-
"""
================================================================================
  fetch_binance_vision_cvd — CVD/order-flow REAL histórico (GRATIS, sin comprar)
  by RasDG_Sol + Claude
================================================================================
El signal evidenciado del research es el order-flow FIRMADO (taker buy−sell = CVD),
que necesita el LADO AGRESOR de cada trade — dato que el OHLCV no tiene. En vez de
COMPRAR data o esperar el colector forward, se usa el archivo público de Binance
(data.binance.vision): publica los `aggTrades` con `is_buyer_maker` (el lado taker).
Igual que con el funding -> CVD histórico real, gratis, AHORA.

Los aggTrades crudos son ENORMES (~400MB/mes, ~4MB/día tick-level). Esto baja los
DIARIOS, los agrega a barras 5m (buy_vol/sell_vol) on-the-fly, y cachea SÓLO el 5m
compacto (un año ≈ 520k filas, parquet chico). Re-ejecutable: saltea días ya hechos.

  is_buyer_maker=False -> el TAKER COMPRÓ (buy_vol += qty)
  is_buyer_maker=True  -> el TAKER VENDIÓ (sell_vol += qty)

Uso:
  python tools/fetch_binance_vision_cvd.py SOLUSDT --start 2026-01-01 --end 2026-06-19
Salida: $FQ_CVD_DIR/cvd_hist_<SYM>.parquet  (ts, buy_vol, sell_vol) barras 5m.

Para la HISTORIA COMPLETA del cube (5 años) correr en GitHub-hosted/Hetzner (descarga
pesada); en el sandbox, una ventana reciente alcanza para el read real (vs proxy).
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

BASE = "https://data.binance.vision/data/futures/um/daily/aggTrades"
DEFAULT_DIR = os.environ.get("FQ_CVD_DIR") or ("/data" if os.path.isdir("/data") else "data/okx")


def _days(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _agg_day_to_5m(sym, d):
    """Baja el aggTrades del día y lo agrega a barras 5m [ts, buy_vol, sell_vol].
    Devuelve None si el archivo no existe (día previo a la inception / aún no subido)."""
    url = "%s/%s/%s-aggTrades-%s.zip" % (BASE, sym, sym, d.isoformat())
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            df = pd.read_csv(z.open(z.namelist()[0]),
                             usecols=["quantity", "transact_time", "is_buyer_maker"])
    except Exception:
        return None
    if df.empty:
        return None
    df["ts"] = (df["transact_time"] // 300000) * 300000
    df["buy"] = np.where(~df["is_buyer_maker"].astype(bool), df["quantity"], 0.0)
    df["sell"] = np.where(df["is_buyer_maker"].astype(bool), df["quantity"], 0.0)
    g = df.groupby("ts", as_index=False).agg(buy_vol=("buy", "sum"), sell_vol=("sell", "sum"))
    return g


def fetch(sym, start, end, out_dir=DEFAULT_DIR, workers=None):
    path = os.path.join(out_dir, "cvd_hist_%s.parquet" % sym)
    os.makedirs(out_dir, exist_ok=True)
    have = pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame(columns=["ts", "buy_vol", "sell_vol"])
    done_days = set((pd.to_datetime(have["ts"], unit="ms").dt.date.unique()).tolist()) if len(have) else set()
    parts = [have] if len(have) else []
    todo = [d for d in _days(start, end) if d not in done_days]
    # descarga CONCURRENTE: el job es network-bound (bajar aggTrades) -> paralelizar
    # baja 5 años de ~2h a ~25min. Cada día es independiente (download+agg). Override
    # workers por env (FQ_CVD_WORKERS); default 12 (acota memoria con días grandes de BTC).
    w = workers or int(os.environ.get("FQ_CVD_WORKERS", "12"))
    n_new = 0
    with ThreadPoolExecutor(max_workers=max(1, w)) as ex:
        for g in ex.map(lambda d: _agg_day_to_5m(sym, d), todo):
            if g is None:
                continue
            parts.append(g)
            n_new += 1
            if n_new % 50 == 0:
                print("[cvd-hist] %s: %d días nuevos..." % (sym, n_new))
    if not parts:
        print("[cvd-hist] %s: sin data" % sym)
        return path
    out = (pd.concat(parts, ignore_index=True)
             .drop_duplicates("ts").sort_values("ts").reset_index(drop=True))
    tmp = path + ".tmp"
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    span = (out.ts.max() - out.ts.min()) / 8.64e7
    print("[cvd-hist] %s: +%d días -> %d barras 5m (%.0f días) %s"
          % (sym, n_new, len(out), span, path))
    return path


def main(argv):
    p = argparse.ArgumentParser(description="CVD histórico real desde data.binance.vision (gratis).")
    p.add_argument("symbol", help="p.ej. SOLUSDT, BTCUSDT")
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    p.add_argument("--out-dir", default=DEFAULT_DIR)
    a = p.parse_args(argv)
    s = date.fromisoformat(a.start)
    e = date.fromisoformat(a.end)
    fetch(a.symbol, s, e, a.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
