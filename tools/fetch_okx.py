# -*- coding: utf-8 -*-
"""
================================================================================
  fetch_okx — colector de OHLCV historico (OKX public, sin API key)
  by RasDG_Sol + Claude
================================================================================
Pagina /market/history-candles hacia atras y guarda parquet (open/high/low/close/
volume + timestamp ms, ascendente). Para alimentar el backtest del motor de imanes
con data REAL y objetiva.

Uso:
    python tools/fetch_okx.py SOL-USDT-SWAP 5m 25000 data/SOL_5m.parquet
    #                         instId        bar  n_velas  salida
================================================================================
"""
import os
import sys
import time
import json
import urllib.request

import pandas as pd

BASE = "https://www.okx.com"


def _get(path, params, timeout=15):
    q = "&".join("%s=%s" % (k, v) for k, v in params.items() if v is not None)
    url = "%s%s?%s" % (BASE, path, q)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch(inst_id, bar="5m", n=25000, *, pause=0.12):
    """Devuelve un DataFrame ascendente con n velas confirmadas (o las que haya)."""
    rows = []
    after = None              # ts: devolver velas ANTERIORES a este ts (hacia atras)
    seen = set()
    while len(rows) < n:
        try:
            j = _get("/api/v5/market/history-candles",
                     {"instId": inst_id, "bar": bar, "after": after, "limit": 100})
        except Exception as e:
            print("[okx] error: %s -> reintento" % str(e)[:100])
            time.sleep(1.0)
            continue
        data = j.get("data", [])
        if not data:
            break
        for c in data:
            ts = int(c[0])
            if ts in seen:
                continue
            seen.add(ts)
            # [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
            if len(c) > 8 and c[8] == "0":     # vela no cerrada -> saltar
                continue
            rows.append((ts, float(c[1]), float(c[2]), float(c[3]),
                         float(c[4]), float(c[5])))
        after = data[-1][0]                    # ts mas viejo de este lote
        if len(rows) % 2000 < 100:
            print("[okx] %s %s: %d velas..." % (inst_id, bar, len(rows)))
        time.sleep(pause)
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


def main(argv):
    if len(argv) < 5:
        print("uso: python tools/fetch_okx.py <instId> <bar> <n> <salida.parquet>")
        return 2
    inst, bar, n, out = argv[1], argv[2], int(argv[3]), argv[4]
    df = fetch(inst, bar, n)
    if df.empty:
        print("[okx] sin datos")
        return 1
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    df.to_parquet(out, index=False)
    span_h = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]) / 3.6e6
    print("[okx] %s: %d velas (%.0f h ~ %.1f dias) -> %s" % (
        inst, len(df), span_h, span_h / 24.0, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
