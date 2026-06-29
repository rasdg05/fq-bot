#!/usr/bin/env python3
"""probe_mexc_tradfi — mide la HISTORIA real de los TradFi de MEXC (make-or-break).

NO cosecha. Para una shortlist de símbolos (ya resueltos en ccxt), pagina fetch_ohlcv
HACIA ADELANTE desde ~2 años atrás para medir la profundidad REAL: cuántas barras 5m
sirve MEXC y desde qué fecha. Si solo da data reciente -> no hay cube validable.
También prueba qué timeframes soporta (3m no existe en MEXC).

  python tools/probe_mexc_tradfi.py
"""
import sys
import time
from datetime import datetime, timezone

import ccxt

# símbolos ya resueltos por la corrida anterior (swap USDT-M, los más líquidos)
SHORTLIST = ["XAU/USDT:USDT", "XAUT/USDT:USDT", "SPX500/USDT:USDT", "SPX/USDT:USDT",
             "NAS100/USDT:USDT", "USOIL/USDT:USDT", "UKOIL/USDT:USDT",
             "SILVER/USDT:USDT", "XPT/USDT:USDT", "COPPER/USDT:USDT"]


def history_depth(ex, sym, tf="5m", max_pages=80):
    """Pagina hacia adelante desde ~2 años atrás. Devuelve (n_barras, fecha0, span_dias)."""
    since = ex.milliseconds() - int(2 * 365 * 24 * 3600 * 1000)
    try:
        first = ex.fetch_ohlcv(sym, tf, since=since, limit=1000)
    except Exception as e:
        return ("ERR:" + str(e)[:60], None, None)
    if not first:
        return (0, None, None)
    bars = list(first)
    pages = 1
    while pages < max_pages:
        cursor = bars[-1][0] + 1
        try:
            b = ex.fetch_ohlcv(sym, tf, since=cursor, limit=1000)
        except Exception:
            break
        if not b or b[-1][0] <= bars[-1][0]:
            break
        bars += b
        pages += 1
        time.sleep(0.12)
    f0 = datetime.fromtimestamp(bars[0][0] / 1000, tz=timezone.utc).date().isoformat()
    span = (bars[-1][0] - bars[0][0]) / 1000 / 86400
    return (len(bars), f0, round(span, 1))


def main():
    print("== MEXC TradFi — historia real (paginando 5m) ==", flush=True)
    ex = ccxt.mexc({"options": {"defaultType": "swap"}, "enableRateLimit": True})
    m = ex.load_markets()
    tfs = sorted(ex.timeframes.keys()) if getattr(ex, "timeframes", None) else []
    print("timeframes soportados por MEXC: %s" % (", ".join(tfs) or "?"), flush=True)
    print("(¿3m? %s)\n" % ("SÍ" if "3m" in tfs else "NO — usar 1m o 5m"), flush=True)
    for s in SHORTLIST:
        if s not in m:
            print("  %-20s  (no está en markets)" % s, flush=True)
            continue
        n, f0, span = history_depth(ex, s, "5m")
        if isinstance(n, str):
            print("  %-20s  %s" % (s, n), flush=True)
        elif n == 0:
            print("  %-20s  SIN DATA 5m" % s, flush=True)
        else:
            yrs = (span or 0) / 365.0
            verdict = "✓ profundo" if span and span > 250 else ("~ok" if span and span > 90 else "🚩 fino")
            print("  %-20s  %7d barras 5m · desde %s · %5.0f días (%.1f años)  %s" % (
                s, n, f0, span or 0, yrs, verdict), flush=True)
    print("\nGuía: >250 días = cube usable · <90 días = demasiado fino para el gate.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
