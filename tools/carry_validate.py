# -*- coding: utf-8 -*-
"""
carry_validate — valida el FUNDING CARRY en historia LARGA multi-régimen.

El sandbox solo alcanza OKX (funding ~3 meses); por eso el carry estaba validado
en UN régimen (favorable) y SOL ya salia negativo (canario). Este script —pensado
para CI (red abierta) o Railway— baja funding PROFUNDO via ccxt (Binance primero,
que llega a la inception del contrato; fallback a otros) y corre carry_metrics
OVERALL + POR AÑO. La lectura clave: ¿el APY se mantiene en el BEAR (2022) o se
desploma como SOL? Si colapsa, el carry es prima de RÉGIMEN, no all-weather.

FUENTE PRIMARIA (2026-06): data.binance.vision (archivo público S3/CDN, NO la API).
A diferencia de la API de Binance/Bybit/Gate —geo-bloqueada en sandbox y a veces en
CI—, el archivo SÍ es alcanzable y trae funding desde la inception. ccxt queda como
FALLBACK por si el archivo no responde. Asi la validación corre IGUAL en sandbox y CI.

Uso: python tools/carry_validate.py --since 2021-06-01
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carry_backtest as cb  # noqa: E402
import fetch_binance_vision_funding as bvf  # noqa: E402

BASKET = ["BTC", "ETH", "BNB", "XRP", "DOGE", "LTC", "ADA", "SOL"]
# orden: el de funding mas profundo primero (Binance llega a inception).
EXCHANGES = ["binance", "bybit", "okx", "gate", "kucoinfutures"]


def _try_binance_vision(since_year):
    """Camino PRIMARIO: archivo público (alcanzable en sandbox y CI). Devuelve True
    si pudo bajar y reportar; False si el archivo no responde (-> fallback ccxt)."""
    print("[carry-validate] fuente PRIMARIA: data.binance.vision (archivo público)")
    end = 2026
    bvf.download(bvf.SYMS, since_year, end, bvf.DEFAULT_CACHE)
    data = {}
    for s in bvf.SYMS:
        df = bvf.load_funding(s, since_year, end, bvf.DEFAULT_CACHE)
        if not df.empty:
            data[s] = df
    if not data:
        print("[carry-validate] archivo no respondió -> fallback ccxt")
        return False
    print("[carry-validate] cargados: " + ", ".join("%s(%d)" % (s, len(d)) for s, d in data.items()))
    clean = [s for s in (x.split("-")[0] + "USDT" for x in cb.CLEAN_BASKET) if s in data]
    bvf.report(data, clean)
    return True


def _pick_exchange():
    import ccxt
    for name in EXCHANGES:
        try:
            ex = getattr(ccxt, name)({"enableRateLimit": True,
                                      "options": {"defaultType": "future"}})
            ex.load_markets()
            print("[carry-validate] fuente de funding: %s" % name)
            return ex, name
        except Exception as e:
            print("  %s no reachable: %s" % (name, str(e)[:60]))
    return None, None


def _fetch_funding(ex, base, since_ms):
    """Pagina fetch_funding_rate_history hacia adelante hasta hoy."""
    sym = "%s/USDT:USDT" % base
    rows, cur = [], since_ms
    for _ in range(400):
        b = None
        for lim in (1000, 200):
            try:
                b = ex.fetch_funding_rate_history(sym, since=cur, limit=lim)
                break
            except Exception:
                continue
        if not b:
            break
        rows += b
        cur = b[-1]["timestamp"] + 1
        if len(b) < 100:
            break
    return rows


def main(argv):
    p = argparse.ArgumentParser(description="Valida el funding carry multi-regimen.")
    p.add_argument("--since", default="2021-06-01", help="ISO date (YYYY-MM-DD)")
    p.add_argument("--no-archive", action="store_true", help="saltar el archivo, ir directo a ccxt")
    a = p.parse_args(argv)

    since_year = int(a.since[:4])
    if not a.no_archive:
        try:
            if _try_binance_vision(since_year):
                return 0
        except Exception as e:
            print("[carry-validate] archivo falló (%s) -> fallback ccxt" % str(e)[:80])

    ex, exname = _pick_exchange()
    if ex is None:
        print("[carry-validate] ningun exchange alcanzable -> no se puede validar.")
        return 1
    since_ms = ex.parse8601(a.since + "T00:00:00Z")

    print("\n=== CARRY multi-régimen · fuente=%s · desde %s ===" % (exname, a.since))
    print("%-5s %6s %6s %8s %8s %8s %6s   %s"
          % ("sym", "n", "dias", "APY", "Sharpe", "maxDD", "%+", "APY por año"))
    print("-" * 92)
    summary = []
    for base in BASKET:
        rows = _fetch_funding(ex, base, since_ms)
        if len(rows) < 50:
            print("%-5s pocos datos (n=%d)" % (base, len(rows)))
            continue
        df = pd.DataFrame({"ts": [r["timestamp"] for r in rows],
                           "f": [r.get("fundingRate") for r in rows]}).dropna()
        df = df.drop_duplicates("ts").sort_values("ts")
        df["year"] = pd.to_datetime(df["ts"], unit="ms").dt.year
        m = cb.carry_metrics(df["f"].to_numpy(float))
        per_year = " ".join(
            "%d:%+.0f%%" % (y, cb.carry_metrics(g["f"].to_numpy(float))["apy"] * 100)
            for y, g in df.groupby("year"))
        print("%-5s %6d %6.0f %+7.1f%% %7.1f %7.2f%% %5.0f%%   %s"
              % (base, m["n"], m["n"] / 3.0, m["apy"] * 100, m["sharpe"],
                 m["max_dd_frac"] * 100, m["pct_positive"] * 100, per_year))
        summary.append((base, m, per_year))

    print("\nLECTURA:")
    print("  · APY por año + en bull Y bear (2022) -> carry ALL-WEATHER (escalable).")
    print("  · APY que colapsa/negativo en 2022 -> prima de RÉGIMEN (cuidado leverage).")
    print("  · SOL es el canario: si es negativo en varios años, excluirlo del basket.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
