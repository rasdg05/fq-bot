# -*- coding: utf-8 -*-
"""
fetch_agg_oi — colector FORWARD de Open Interest AGREGADO multi-exchange.

El colector de OKX (fetch_okx_oi) ve UN solo exchange. El OI que mueve el mercado
es el AGREGADO (Binance domina el perp, + Bybit + OKX). Coinglass lo da agregado
pero pide API key. Como RAILWAY no está geo-bloqueado (el sandbox sí: Binance 451,
Bybit 403), el bot le pega DIRECTO a cada venue y suma -> OI agregado, sin key.

Espejo de fetch_okx_oi: cada poll baja la ventana 5m reciente de OI de cada exchange,
normaliza a USD, y appendea-dedupea a un parquet durable en formato LARGO
(ts, ccy, exchange, oi_usd). El agregado = groupby(ts,ccy).sum() downstream (--report).
Así, en semanas, junta OI agregado 5m para medir si su cambio/divergencia predice
precio (lo que el research dirá si vale; esto es el PREREQUISITO: juntar la data).

Fuentes y unidad:
  · OKX    rubik open-interest-volume   -> USD directo. (anda en sandbox)
  · Binance futures/data/openInterestHist -> sumOpenInterestValue (USD). (geo en sandbox)
  · Bybit  v5/market/open-interest (coin) × markPrice -> USD aprox. (geo en sandbox)
Defensivo: si un venue falla (geo/caída), se saltea y se registra lo que haya.

Uso:
    python tools/fetch_agg_oi.py --once     # una pasada (todos los símbolos/venues)
    python tools/fetch_agg_oi.py --loop     # loop (FQ_AGG_OI_INTERVAL seg, def 3600)
    python tools/fetch_agg_oi.py --report   # último OI por venue + agregado
Salida: $FQ_AGG_OI_DIR/agg_oi.parquet (def /data si existe, si no data/okx).

Pure stdlib + pandas. Hijo NO-crítico del launcher (FQ_AGG_OI_COLLECT=1).
"""
import json
import os
import sys
import time
import urllib.request

import pandas as pd

OUT_DIR = os.environ.get("FQ_AGG_OI_DIR") or ("/data" if os.path.isdir("/data") else "data/okx")
LEDGER = os.path.join(OUT_DIR, "agg_oi.parquet")
CCYS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LTC"]


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ---- fetchers por exchange: cada uno devuelve DataFrame [ts, oi_usd] o vacío ----
def fetch_okx(ccy):
    j = _get("https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume"
             "?ccy=%s&period=5m" % ccy)
    rows = [(int(r[0]), float(r[1])) for r in j.get("data", [])]
    return pd.DataFrame(rows, columns=["ts", "oi_usd"])


def fetch_binance(ccy):
    j = _get("https://fapi.binance.com/futures/data/openInterestHist"
             "?symbol=%sUSDT&period=5m&limit=500" % ccy)
    rows = [(int(r["timestamp"]), float(r["sumOpenInterestValue"])) for r in j]
    return pd.DataFrame(rows, columns=["ts", "oi_usd"])


def fetch_bybit(ccy):
    sym = "%sUSDT" % ccy
    oi = _get("https://api.bybit.com/v5/market/open-interest"
              "?category=linear&symbol=%s&intervalTime=5min&limit=200" % sym)
    lst = oi.get("result", {}).get("list", [])
    if not lst:
        return pd.DataFrame(columns=["ts", "oi_usd"])
    tk = _get("https://api.bybit.com/v5/market/tickers?category=linear&symbol=%s" % sym)
    px = float(tk["result"]["list"][0]["markPrice"])   # USD aprox = coin_OI × px actual
    rows = [(int(r["timestamp"]), float(r["openInterest"]) * px) for r in lst]
    return pd.DataFrame(rows, columns=["ts", "oi_usd"])


SOURCES = {"okx": fetch_okx, "binance": fetch_binance, "bybit": fetch_bybit}


def append_dedupe(path, new):
    """Espejo de fetch_okx_oi.append_dedupe; clave (ts, ccy, exchange)."""
    if new.empty:
        return None
    if os.path.exists(path):
        try:
            new = pd.concat([pd.read_parquet(path), new], ignore_index=True)
        except Exception as e:
            print("[agg-oi] read %s: %s (reescribo)" % (path, e))
    out = (new.drop_duplicates(["ts", "ccy", "exchange"])
              .sort_values(["ccy", "exchange", "ts"]).reset_index(drop=True))
    tmp = path + ".tmp"
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)   # atómico
    return out


def run_once():
    os.makedirs(OUT_DIR, exist_ok=True)
    frames, ok = [], {}
    for ccy in CCYS:
        for ex, fn in SOURCES.items():
            try:
                df = fn(ccy)
                if not df.empty:
                    df = df.copy()
                    df["ccy"] = ccy
                    df["exchange"] = ex
                    frames.append(df[["ts", "ccy", "exchange", "oi_usd"]])
                    ok[ex] = ok.get(ex, 0) + 1
            except Exception as e:
                # geo-block (sandbox) o caída: se saltea, no rompe el colector
                ok.setdefault(ex, 0)
                if ok.get("_err_%s" % ex) is None:
                    print("[agg-oi] %s ERROR (%s): %s" % (ex, ccy, str(e)[:80]))
                    ok["_err_%s" % ex] = 1
            time.sleep(0.12)
    if not frames:
        print("[agg-oi] sin data este poll (¿todos los venues caídos/geo?)")
        return
    out = append_dedupe(LEDGER, pd.concat(frames, ignore_index=True))
    vend = ", ".join("%s:%d" % (e, n) for e, n in ok.items() if not e.startswith("_"))
    if out is not None:
        span = (out.ts.max() - out.ts.min()) / 8.64e7
        print("[agg-oi] %d filas (%d venues activos: %s) span %.1fd -> %s"
              % (len(out), len([e for e in ok if not e.startswith('_') and ok[e]]),
                 vend, span, LEDGER))


def report():
    if not os.path.exists(LEDGER):
        print("[agg-oi] sin ledger en %s (corré --once primero)" % LEDGER)
        return 1
    df = pd.read_parquet(LEDGER)
    print("=== OI AGREGADO — última lectura por símbolo (USD) ===")
    print("símbolo |   agregado   |  venues")
    for ccy in CCYS:
        d = df[df.ccy == ccy]
        if d.empty:
            continue
        # último OI por exchange (su ts más reciente), luego sumo
        latest = d.sort_values("ts").groupby("exchange").tail(1)
        agg = latest["oi_usd"].sum()
        per = "  ".join("%s $%.2fB" % (r.exchange, r.oi_usd / 1e9) for _, r in latest.iterrows())
        print("%-7s | $%8.2fB | %s" % (ccy, agg / 1e9, per))
    print("\n(agregado = suma del último OI de cada venue; serie 5m en el parquet "
          "para medir cambio/divergencia vs precio cuando el research lo valide)")
    return 0


def main(argv):
    mode = argv[1] if len(argv) > 1 else "--once"
    if mode == "--report":
        return report()
    if mode == "--loop":
        interval = int(os.environ.get("FQ_AGG_OI_INTERVAL", "3600"))
        print("[agg-oi] loop cada %ds -> %s (venues: %s)"
              % (interval, OUT_DIR, ", ".join(SOURCES)))
        while True:
            run_once()
            time.sleep(interval)
    else:
        run_once()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
