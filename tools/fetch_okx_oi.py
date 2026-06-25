# -*- coding: utf-8 -*-
"""
fetch_okx_oi - colector FORWARD de Open Interest (OKX public, sin API key).

El histórico de OI de OKX rubik es CORTO (5m: ~días). Para testear el láser hace
falta acumularlo HACIA ADELANTE: este colector baja la ventana 5m reciente de OI y
la appendea-dedupea a un parquet durable. Corriendo en loop (cada ~1h) sobre el
Volume de Railway, en unas semanas junta suficiente 5m OI para el test de
inversión de población / cascada.

Endpoint: /api/v5/rubik/stat/contracts/open-interest-volume?ccy=SOL&period=5m
  -> data: [[ts_ms, oi_usd, vol_usd], ...] (desc). Cada llamada trae ~2-3 días de
  5m, así que un poll horario solapa de sobra y nunca deja huecos.

Uso:
    python tools/fetch_okx_oi.py --once          # una pasada (todos los simbolos)
    python tools/fetch_okx_oi.py --loop          # loop (FQ_OI_INTERVAL seg, def 3600)
Salida: $FQ_OI_DIR/oi_<CCY>.parquet  (def /data si existe, si no data/okx).

Pure stdlib + pandas. CONSTRAINTS 7.
"""
import os
import sys
import time
import json
import logging
import urllib.request

import pandas as pd

log = logging.getLogger("fetch_okx_oi")
BASE = "https://www.okx.com"
CCYS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LTC"]
OUT_DIR = os.environ.get("FQ_OI_DIR") or ("/data" if os.path.isdir("/data") else "data/okx")


def _get(path, params, timeout=15):
    q = "&".join("%s=%s" % (k, v) for k, v in params.items() if v is not None)
    req = urllib.request.Request("%s%s?%s" % (BASE, path, q),
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_oi_5m(ccy):
    """DataFrame [ts, oi_usd, vol_usd] ascendente con la ventana 5m reciente."""
    j = _get("/api/v5/rubik/stat/contracts/open-interest-volume",
             {"ccy": ccy, "period": "5m"})
    rows = [(int(r[0]), float(r[1]), float(r[2])) for r in j.get("data", [])]
    return pd.DataFrame(rows, columns=["ts", "oi_usd", "vol_usd"]).sort_values("ts")


def append_dedupe(path, new):
    if new.empty:
        return None
    if os.path.exists(path):
        try:
            new = pd.concat([pd.read_parquet(path), new], ignore_index=True)
        except Exception as e:
            log.warning("read %s: %s (reescribo)", path, e)
    out = new.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    tmp = path + ".tmp"
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)   # atomico
    return out


def run_once():
    os.makedirs(OUT_DIR, exist_ok=True)
    for ccy in CCYS:
        path = os.path.join(OUT_DIR, "oi_%s.parquet" % ccy)
        try:
            df = fetch_oi_5m(ccy)
            out = append_dedupe(path, df)
            if out is not None:
                span = (out.ts.iloc[-1] - out.ts.iloc[0]) / 8.64e7
                print("[oi] %s: +%d -> %d pts (%.1f d) %s"
                      % (ccy, len(df), len(out), span, path))
        except Exception as e:
            print("[oi] %s ERROR: %s" % (ccy, str(e)[:100]))
        time.sleep(0.15)


def main(argv):
    mode = argv[1] if len(argv) > 1 else "--once"
    if mode == "--loop":
        interval = int(os.environ.get("FQ_OI_INTERVAL", "3600"))
        print("[oi] loop cada %ds -> %s" % (interval, OUT_DIR))
        while True:
            run_once()
            time.sleep(interval)
    else:
        run_once()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
