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

  futures/um/monthly/klines/<SYM>/5m/<SYM>-5m-<YYYY-MM>.zip   (pase 1, ~85x menos
                                                               peticiones)
  futures/um/daily/klines/<SYM>/5m/<SYM>-5m-<YYYY-MM-DD>.zip  (pase 2, relleno del
                                                               mes en curso)
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bt_data as btd          # noqa: E402

_ROOT = "https://data.binance.vision/data/futures/um"
BASE_D = _ROOT + "/daily/klines"
BASE_M = _ROOT + "/monthly/klines"
BASE = BASE_D                      # compat: lectores viejos del modulo
DEFAULT_DIR = os.environ.get("FQ_CVD_DIR") or ("/data" if os.path.isdir("/data")
               else ("data/okx" if os.path.isdir("data/okx") else "data/mercado"))
COLS = ["ts", "open", "high", "low", "close", "volume", "taker_buy_base"]
_RAW = ["open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]


def _days(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _months(start, end):
    """(anio, mes) de cada mes TOCADO por [start, end]. El fichero mensual trae
    el mes entero; bajar de mas es inofensivo (se deduplica por ts)."""
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _parse_zip(data):
    """CSV (posiblemente con header) dentro del zip -> DataFrame con COLS."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        df = pd.read_csv(z.open(z.namelist()[0]), header=None, names=_RAW)
    if df.empty:
        return None
    # los CSV nuevos a veces traen header: la 1ra fila no parsea a numero -> se cae sola
    df["ts"] = pd.to_numeric(df["open_time"], errors="coerce")
    for c in ("open", "high", "low", "close", "volume", "taker_buy_volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["ts", "close", "volume"])
    df["ts"] = df["ts"].astype("int64")
    df["taker_buy_base"] = df["taker_buy_volume"].fillna(0.0)
    return df[COLS]


def _klines_month(sym, ym):
    """Mes completo. None si aun no esta publicado (el mes en curso no lo esta)."""
    y, m = ym
    url = "%s/%s/5m/%s-5m-%04d-%02d.zip" % (BASE_M, sym, sym, y, m)
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return _parse_zip(r.read())
    except Exception:
        return None


def _klines_day(sym, d):
    """Baja el klines 5m del dia -> [ts, open, high, low, close, volume, taker_buy_base].
    None si el archivo no existe (dia previo a la inception / aun no subido)."""
    url = "%s/%s/5m/%s-5m-%s.zip" % (BASE_D, sym, sym, d.isoformat())
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return _parse_zip(r.read())
    except Exception:
        return None


def fetch(sym, start, end, out_dir=DEFAULT_DIR, workers=None):
    """Dos pases: MENSUAL primero (un fichero por mes), DIARIO despues para lo
    que falte (el mes en curso no tiene fichero mensual publicado). Re-ejecutable:
    lo ya cacheado no se vuelve a bajar."""
    path = os.path.join(out_dir, "kl_hist_%s.parquet" % sym)
    os.makedirs(out_dir, exist_ok=True)
    have = pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame(columns=COLS)
    parts = [have] if len(have) else []

    def _done_days():
        if not parts:
            return set()
        ts = pd.concat([p["ts"] for p in parts], ignore_index=True)
        return set(pd.to_datetime(ts, unit="ms").dt.date.unique().tolist())

    w = workers or int(os.environ.get("FQ_KL_WORKERS", "12"))
    done = _done_days()

    # --- pase 1: meses completos ---
    def _month_missing(ym):
        y, m = ym
        d = date(y, m, 1)
        while d.month == m and d <= end:
            if d >= start and d not in done:
                return True
            d += timedelta(days=1)
        return False

    todo_m = [ym for ym in _months(start, end) if _month_missing(ym)]
    n_m = 0
    with ThreadPoolExecutor(max_workers=max(1, w)) as ex:
        for g in ex.map(lambda ym: _klines_month(sym, ym), todo_m):
            if g is None:
                continue
            parts.append(g)
            n_m += 1

    # --- pase 2: dias sueltos que el mensual no cubrio ---
    done = _done_days()
    todo_d = [d for d in _days(start, end) if d not in done]
    n_d = 0
    with ThreadPoolExecutor(max_workers=max(1, w)) as ex:
        for g in ex.map(lambda d: _klines_day(sym, d), todo_d):
            if g is None:
                continue
            parts.append(g)
            n_d += 1

    if not parts:
        print("[kl-hist] %s: sin data" % sym)
        return path
    out = (pd.concat(parts, ignore_index=True)
             .drop_duplicates("ts").sort_values("ts").reset_index(drop=True))
    # Sella la procedencia EN EL DATO: el directorio por defecto se llamo
    # `data/okx/` durante meses y guardaba esto, que es de Binance.
    out = btd.stamp_venue(out, btd.VENUE_BINANCE_UM)
    tmp = path + ".tmp"
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    span = (out.ts.max() - out.ts.min()) / 8.64e7
    print("[kl-hist] %s: +%d meses +%d dias -> %d barras 5m (%.0f dias) %s"
          % (sym, n_m, n_d, len(out), span, path))
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
