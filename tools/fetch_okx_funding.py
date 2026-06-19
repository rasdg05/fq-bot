# -*- coding: utf-8 -*-
"""
================================================================================
  fetch_okx_funding — historico de FUNDING RATE (OKX public, sin API key)
  by RasDG_Sol + Claude
================================================================================
Pagina /public/funding-rate-history hacia atras y guarda parquet (fundingRate +
fundingTime ms, ascendente). Alimenta el backtest de CARRY (la ruta con edge
comprobado: short perp delta-neutral cobra funding cuando es positivo).

Uso:
    python tools/fetch_okx_funding.py SOL-USDT-SWAP 3000 data/okx/SOL_funding.parquet
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
    req = urllib.request.Request("%s%s?%s" % (BASE, path, q),
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch(inst_id, n=3000, *, pause=0.12):
    """DataFrame ascendente con n funding rates (o las que haya). OKX paga c/8h."""
    rows, after, seen = [], None, set()
    while len(rows) < n:
        try:
            j = _get("/api/v5/public/funding-rate-history",
                     {"instId": inst_id, "after": after, "limit": 100})
        except Exception as e:
            print("[fund] error: %s -> reintento" % str(e)[:90])
            time.sleep(1.0)
            continue
        data = j.get("data", [])
        if not data:
            break
        for c in data:
            ts = int(c["fundingTime"])
            if ts in seen:
                continue
            seen.add(ts)
            rows.append((ts, float(c["fundingRate"])))
        after = data[-1]["fundingTime"]
        time.sleep(pause)
    df = pd.DataFrame(rows, columns=["fundingTime", "fundingRate"])
    return df.drop_duplicates("fundingTime").sort_values("fundingTime").reset_index(drop=True)


def main(argv):
    if len(argv) < 4:
        print("uso: python tools/fetch_okx_funding.py <instId> <n> <salida.parquet>")
        return 2
    inst, n, out = argv[1], int(argv[2]), argv[3]
    df = fetch(inst, n)
    if df.empty:
        print("[fund] sin datos")
        return 1
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    df.to_parquet(out, index=False)
    days = (df["fundingTime"].iloc[-1] - df["fundingTime"].iloc[0]) / 8.64e7
    print("[fund] %s: %d puntos (%.0f dias) -> %s" % (inst, len(df), days, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
