#!/usr/bin/env python3
"""probe_mexc_tradfi — resuelve los símbolos TradFi de MEXC en ccxt + su historia.

NO cosecha nada. Solo: (1) carga los mercados de MEXC (swap+spot), (2) encuentra los
candidatos TradFi (oro/plata/petróleo/índices), (3) por cada uno confirma que
fetch_ohlcv funciona en 3m y 5m y reporta DESDE CUÁNDO hay data (profundidad de
historia) — para elegir símbolo, TF y meses sin adivinar.

  python tools/probe_mexc_tradfi.py
"""
import sys
import time

import ccxt

TARGETS = ["GOLD", "XAU", "XAUT", "SILVER", "XAG", "OIL", "WTI", "BRENT",
           "SP500", "SPX", "NAS100", "NASDAQ", "NDX", "PLATINUM", "XPT", "COPPER", "GAS"]


def earliest_ohlcv(ex, sym, tf):
    """Aproxima la fecha del primer dato paginando desde 2019 hacia adelante."""
    try:
        since = ex.parse8601("2019-01-01T00:00:00Z")
        o = ex.fetch_ohlcv(sym, tf, since=since, limit=10)
        if o:
            return o[0][0], len(o)
        # si no devolvió desde 2019, pide los últimos para confirmar que existe
        o2 = ex.fetch_ohlcv(sym, tf, limit=10)
        if o2:
            return o2[0][0], len(o2)
        return None, 0
    except Exception as e:
        return ("ERR:" + str(e)[:50]), -1


def main():
    print("== MEXC TradFi probe ==", flush=True)
    found = {}
    for mtype in ("swap", "spot"):
        try:
            ex = ccxt.mexc({"options": {"defaultType": mtype}, "enableRateLimit": True})
            m = ex.load_markets()
        except Exception as e:
            print("  [%s] load_markets ERR: %s" % (mtype, str(e)[:80]), flush=True)
            continue
        hits = [s for s in m if any(t in s.upper().replace("/", "").replace(":", "")
                                    for t in TARGETS)]
        print("\n--- %s: %d candidatos ---" % (mtype, len(hits)), flush=True)
        for s in sorted(hits):
            info = m[s]
            ts, n = earliest_ohlcv(ex, s, "5m")
            if isinstance(ts, int):
                from datetime import datetime, timezone
                desde = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()
                # confirma 3m también
                ts3, n3 = earliest_ohlcv(ex, s, "3m")
                ok3 = "3m✓" if isinstance(ts3, int) else "3m✗"
                print("  %-26s type=%-5s active=%s  5m-desde=%s  %s" % (
                    s, info.get("type"), info.get("active"), desde, ok3), flush=True)
                found[s] = desde
            else:
                print("  %-26s  (sin OHLCV: %s)" % (s, ts), flush=True)
            time.sleep(0.15)
    print("\n== resumen: %d símbolos TradFi con data 5m ==" % len(found), flush=True)
    for s, d in sorted(found.items(), key=lambda kv: kv[1]):
        print("  %s  desde %s" % (s, d), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
