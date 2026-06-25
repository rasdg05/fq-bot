# -*- coding: utf-8 -*-
"""
================================================================================
  coin_fragility — score de FRAGILIDAD/QUIEBRA cross-seccional (datos gratis)
  by RasDG_Sol + Claude
================================================================================
El único hallazgo on-chain que sobrevivió la verificación adversarial como
CONSTRUIBLE y ÚTIL (ver research/edge_externo_2026.md): un modelo cross-seccional
de quiebra. ~28% de las monedas mueren en 1 año, ~80% en 5; un backtest que sólo
ve sobrevivientes sobreestima ~62% anualizado. Predictores documentados (Ma-Tu-Zhu,
'In Search of Cryptocurrency Failure'): monedas más GRANDES, menos VOLÁTILES, más
LÍQUIDAS y con mejor RETORNO reciente quiebran menos.

Para qué sirve ACÁ (no es alpha especulativo, es higiene):
  1. ANTES de sumar un símbolo al motor o al basket del carry -> chequear su fragilidad.
  2. Conciencia de survivorship: los frágiles de hoy son los muertos del backtest de mañana.

HONESTO: heurística con los SIGNOS de la literatura, NO un modelo fiteado con dataset
survivorship-corregido (eso exige data de monedas muertas — la lección misma). La EDAD
se OMITE a propósito: el paper marca su signo como contaminado por survivorship.

Datos: CoinGecko /coins/markets (gratis, sin key) — una sola llamada, cero rate-limit.
Score por RANK (robusto a outliers): 0 = sólido, 1 = frágil. Uso:
    python tools/coin_fragility.py            # top 150 por mcap + nuestros símbolos
    python tools/coin_fragility.py --top 250
================================================================================
"""
import argparse
import json
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

API = "https://api.coingecko.com/api/v3/coins/markets"
# nuestro universo: motor (8) + basket carry CLEAN. Se resaltan en el reporte.
OURS = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "ripple": "XRP",
        "litecoin": "LTC", "dogecoin": "DOGE", "cardano": "ADA", "binancecoin": "BNB"}


def fetch_markets(top, pages_pause=1.2):
    """Cross-sección de mercado: id, mcap, volumen, precio y % a varias ventanas."""
    rows, per = [], 250
    for page in range(1, (top // per) + 2):
        params = {
            "vs_currency": "usd", "order": "market_cap_desc", "per_page": per,
            "page": page, "price_change_percentage": "1h,24h,7d,30d",
            "sparkline": "false",
        }
        q = "&".join("%s=%s" % (k, v) for k, v in params.items())
        req = urllib.request.Request(API + "?" + q, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        if not data:
            break
        rows += data
        if len(rows) >= top:
            break
        time.sleep(pages_pause)
    return pd.DataFrame(rows).head(top)


def _rank01(s, ascending=True):
    """Rank a [0,1]. ascending=True -> valores altos ~1. Robusto a outliers/NaN."""
    r = s.rank(pct=True, ascending=ascending, na_option="bottom")
    return r.fillna(0.5).clip(0, 1)


def score(df):
    """Devuelve df con la fragilidad [0,1] (alto = frágil) y sus componentes.
    Signos (más frágil cuando): chico, ilíquido, volátil, momentum negativo."""
    d = df.copy()
    d["mcap"] = pd.to_numeric(d.get("market_cap"), errors="coerce")
    d["vol"] = pd.to_numeric(d.get("total_volume"), errors="coerce")
    for c in ("price_change_percentage_1h_in_currency",
              "price_change_percentage_24h_in_currency",
              "price_change_percentage_7d_in_currency",
              "price_change_percentage_30d_in_currency"):
        d[c] = pd.to_numeric(d.get(c), errors="coerce")
    rc = ["price_change_percentage_1h_in_currency", "price_change_percentage_24h_in_currency",
          "price_change_percentage_7d_in_currency", "price_change_percentage_30d_in_currency"]
    # proxies (sin series de precio, una sola llamada):
    d["turnover"] = d["vol"] / d["mcap"].replace(0, np.nan)          # liquidez relativa
    d["amihud"] = d["price_change_percentage_24h_in_currency"].abs() / (d["vol"] / 1e6).replace(0, np.nan)
    d["volproxy"] = d[rc].std(axis=1)                                # dispersión multi-ventana
    d["mom30"] = d["price_change_percentage_30d_in_currency"]

    # componentes de FRAGILIDAD (alto = más frágil):
    d["f_size"] = _rank01(d["mcap"], ascending=False)                # chico -> frágil
    d["f_illiq"] = 0.5 * _rank01(d["amihud"], ascending=True) + 0.5 * _rank01(d["turnover"], ascending=False)
    d["f_vol"] = _rank01(d["volproxy"], ascending=True)              # volátil -> frágil
    d["f_mom"] = _rank01(d["mom30"], ascending=False)                # momentum bajo -> frágil
    d["fragility"] = d[["f_size", "f_illiq", "f_vol", "f_mom"]].mean(axis=1)
    d["sym"] = d["symbol"].astype(str).str.upper()
    # stablecoin/pegged: casi sin movimiento en TODAS las ventanas -> sólido en el
    # modelo de quiebra, pero INÚTIL como candidato direccional (no se tradea su precio).
    d["is_stable"] = (d["volproxy"] < 1.0) & (d["mom30"].abs() < 3.0)
    return d.sort_values("fragility").reset_index(drop=True)


def _band(f):
    return "SÓLIDO" if f < 0.33 else ("MEDIO" if f < 0.66 else "FRÁGIL")


def report(d):
    n = len(d)
    print("=== FRAGILIDAD CROSS-SECCIONAL (%d monedas, CoinGecko) ===" % n)
    print("score 0=sólido .. 1=frágil  ·  componentes: size/illiq/vol/momentum\n")
    print("NUESTRO UNIVERSO (motor + basket carry):")
    print("  %-6s %-5s  frag   size illiq vol  mom   banda" % ("id", "sym"))
    ours = d[d["id"].isin(OURS)]
    for _, r in ours.sort_values("fragility").iterrows():
        print("  %-6s %-5s  %.2f   %.2f %.2f %.2f %.2f  %s"
              % (OURS.get(r["id"], r["sym"]), r["sym"], r["fragility"],
                 r["f_size"], r["f_illiq"], r["f_vol"], r["f_mom"], _band(r["fragility"])))
    miss = [v for k, v in OURS.items() if k not in set(d["id"])]
    if miss:
        print("  (fuera del top-%d, ilíquidas relativas: %s)" % (n, ", ".join(miss)))

    print("\nMÁS SÓLIDAS y TRADEABLES (no-stable — candidatas para ensanchar el motor):")
    tradeable = d[~d["is_stable"]]
    for _, r in tradeable.head(12).iterrows():
        flag = "  <- nuestra" if r["id"] in OURS else ""
        print("  %-14s %-6s frag %.2f  mcap $%.1fB  mom30 %+.0f%%%s"
              % (r["id"][:14], r["sym"], r["fragility"],
                 (r["mcap"] or 0) / 1e9, r["mom30"] if pd.notna(r["mom30"]) else 0, flag))

    print("\nMÁS FRÁGILES (evitar / candidatas a muerte — NO sumar al universo):")
    for _, r in d.tail(8).sort_values("fragility", ascending=False).iterrows():
        print("  %-14s %-6s frag %.2f  mcap $%.2fB  vol/mcap %.2f  mom30 %+.0f%%"
              % (r["id"][:14], r["sym"], r["fragility"], (r["mcap"] or 0) / 1e9,
                 r["turnover"] if pd.notna(r["turnover"]) else 0,
                 r["mom30"] if pd.notna(r["mom30"]) else 0))
    print("\n(heurística de literatura, no modelo fiteado; edad omitida — signo "
          "survivorship-contaminado. Fuente: research/edge_externo_2026.md)")


def main(argv):
    p = argparse.ArgumentParser(description="Score de fragilidad/quiebra cross-seccional.")
    p.add_argument("--top", type=int, default=150)
    a = p.parse_args(argv)
    df = fetch_markets(a.top)
    if df.empty:
        print("[fragility] sin data (¿CoinGecko inalcanzable?)")
        return 1
    d = score(df)
    # nota de frescura: CoinGecko a veces sirve snapshot por el proxy
    btc = d[d["id"] == "bitcoin"]
    if not btc.empty:
        print("[fragility] sanity: BTC precio $%.0f (verificar frescura si parece viejo)\n"
              % float(pd.to_numeric(btc.iloc[0].get("current_price"), errors="coerce") or 0))
    report(d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
