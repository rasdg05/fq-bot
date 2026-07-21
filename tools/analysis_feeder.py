#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analysis_feeder — capa de ANÁLISIS (no señales) para pares fuera del motor:
oro (XAU) y Nasdaq 100 (NAS100), y cualquier otro que se sume.

Idea (encargo RasDG): NO emitimos señales automáticas en estos pares — pero sí
les aplicamos el MISMO edge de análisis que a cripto (sentimiento del mercado vía
kl_regime_live, termómetro de apalancados vía funding), como "un par más en
observación". Sin cosechar cientos de corridas: es análisis, no un algoritmo nuevo.

Arquitectura DESACOPLADA (regla de hierro: por la interfaz jamás se cae la señal):
este proceso NO comparte estado con el motor. Escribe su propio archivo
`/data/cockpit_extra.json`; el cockpit_server lo MEZCLA con el `cockpit.json` del
motor al servir `/cockpit.json`. Si el feeder muere, el panel de cripto sigue
intacto. Hijo no-crítico del launcher con FQ_ANALYSIS_EXTRA=1.

Fuentes (públicas, sin claves):
  - XAU     -> OKX  `XAU-USDT-SWAP`  (velas + funding; mismo venue que cripto)
  - NAS100  -> MEXC contract `NAS100_USDT` (kline + funding + ticker 24h)

Uso:
  FQ_ANALYSIS_EXTRA=1 python tools/analysis_feeder.py         # loop
  python tools/analysis_feeder.py --once                      # una pasada (test)
"""
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

OUT = os.environ.get("FQ_ANALYSIS_EXTRA_PATH") or (
    "/data/cockpit_extra.json" if os.path.isdir("/data") else "data/cockpit_extra.json")
INTERVAL = int(os.environ.get("FQ_ANALYSIS_INTERVAL", "180"))
SPARK_N = 48
UA = {"User-Agent": "fq-analysis"}

# Instrumentos de análisis. display = etiqueta amable para el portal. Sumar uno es
# una línea: la capa de análisis (regime + funding) es genérica por símbolo.
INSTRUMENTS = [
    {"key": "XAU",    "venue": "okx",  "display": "Oro · XAU",     "okx": "XAU-USDT-SWAP", "fund_sym": "XAU/USDT"},
    {"key": "NAS100", "venue": "mexc", "display": "Nasdaq 100",    "mexc": "NAS100_USDT"},
    {"key": "SPX500", "venue": "mexc", "display": "S&P 500",       "mexc": "SPX500_USDT"},
    {"key": "USOIL",  "venue": "mexc", "display": "Petróleo · WTI", "mexc": "USOIL_USDT"},
]


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _kl(closes):
    """Régimen (sentimiento del mercado) reusando el mismo cálculo del motor."""
    try:
        import motor_paper
        return motor_paper.kl_regime_live([float(x) for x in closes[-64:]])
    except Exception:
        return None


def _okx_instrument(inst):
    """Oro por OKX: velas 5m + funding (reusa el camino ya probado del motor)."""
    d = _get("https://www.okx.com/api/v5/market/candles?instId=%s&bar=5m&limit=%d"
             % (inst["okx"], 300))
    rows = d.get("data") or []
    if not rows:
        return None
    rows = list(reversed(rows))                     # OKX: newest-first -> cronológico
    closes = [float(r[4]) for r in rows]
    price = closes[-1]
    out = {"analysis": True, "display": inst["display"], "price": price,
           "spark": closes[-SPARK_N:], "updated": time.time()}
    kl = _kl(closes)
    if kl:
        out["irrev"] = round(float(kl["irrev"]), 4)
        out["kl_low"] = bool(kl["low"])
    # cambio 24h: 288 velas de 5m; si no alcanza, usa lo que haya
    base = closes[-289] if len(closes) >= 289 else closes[0]
    if base:
        out["chg_24h"] = round((price - base) / base * 100.0, 2)
    try:
        import motor_paper
        rate, pctl = motor_paper.funding_pctl_live(inst["fund_sym"])
        if pctl is not None:
            out["funding_rate"] = round(float(rate), 8)
            out["funding_pctl"] = round(float(pctl), 3)
    except Exception:
        pass
    return out


def _mexc_instrument(inst):
    """Nasdaq por MEXC contract: kline + ticker (24h) + funding history (percentil)."""
    sym = inst["mexc"]
    k = _get("https://contract.mexc.com/api/v1/contract/kline/%s?interval=Min5&limit=%d"
             % (sym, 300))
    kd = (k or {}).get("data") or {}
    closes = [float(x) for x in (kd.get("close") or [])]  # MEXC: ya cronológico
    if len(closes) < 16:
        return None
    price = closes[-1]
    out = {"analysis": True, "display": inst["display"], "price": price,
           "spark": closes[-SPARK_N:], "updated": time.time()}
    kl = _kl(closes)
    if kl:
        out["irrev"] = round(float(kl["irrev"]), 4)
        out["kl_low"] = bool(kl["low"])
    try:                                            # ticker: cambio 24h real del venue
        t = _get("https://contract.mexc.com/api/v1/contract/ticker?symbol=%s" % sym)
        rf = (t.get("data") or {}).get("riseFallRate")
        if rf is not None:
            out["chg_24h"] = round(float(rf) * 100.0, 2)
    except Exception:
        pass
    try:                                            # funding + percentil desde la historia
        f = _get("https://contract.mexc.com/api/v1/contract/funding_rate/%s" % sym)
        rate = float((f.get("data") or {}).get("fundingRate"))
        out["funding_rate"] = round(rate, 8)
        h = _get("https://contract.mexc.com/api/v1/contract/funding_rate/history"
                 "?symbol=%s&page_num=1&page_size=200" % sym)
        hist = [float(x["fundingRate"]) for x in
                ((h.get("data") or {}).get("resultList") or []) if "fundingRate" in x]
        if len(hist) >= 10:
            pctl = sum(1 for v in hist if v <= rate) / float(len(hist))
            out["funding_pctl"] = round(pctl, 3)
    except Exception:
        pass
    return out


def build_one(inst):
    try:
        if inst["venue"] == "okx":
            return _okx_instrument(inst)
        if inst["venue"] == "mexc":
            return _mexc_instrument(inst)
    except Exception as e:
        sys.stderr.write("[analysis] %s: %s\n" % (inst["key"], e))
    return None


def run_once():
    symbols = {}
    for inst in INSTRUMENTS:
        row = build_one(inst)
        if row:
            symbols[inst["key"]] = row
    payload = {"updated": time.time(), "symbols": symbols}
    d = os.path.dirname(OUT)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh, default=str)
    os.replace(tmp, OUT)                             # atómico: el server jamás lee a medias
    return symbols


def main():
    if "--once" in sys.argv:
        syms = run_once()
        sys.stdout.write("[analysis] once -> %s\n" % ", ".join(sorted(syms)) if syms
                         else "[analysis] once -> (sin datos)\n")
        return 0
    sys.stdout.write("[analysis] feeder cada %ds -> %s\n" % (INTERVAL, OUT))
    sys.stdout.flush()
    while True:
        try:
            run_once()
        except Exception as e:
            sys.stderr.write("[analysis] loop: %s\n" % e)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
