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
  - XAU (oro)          -> OKX  `XAU-USDT-SWAP` (velas + funding; venue de cripto)
  - índices/FX/materias -> MEXC contract (kline + funding + ticker 24h): Nasdaq 100,
    S&P 500, Dow (US30), WTI, Brent (UKOIL) y majors de FX (EUR/GBP/AUD contra USD).
    El contrato XXX_USDT cotiza como XXX/USD, así que el funding se lee sin invertir.

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
CAL_OUT = os.environ.get("FQ_CALENDAR_PATH") or (
    "/data/cockpit_calendar.json" if os.path.isdir("/data") else "data/cockpit_calendar.json")
INTERVAL = int(os.environ.get("FQ_ANALYSIS_INTERVAL", "180"))
CAL_INTERVAL = int(os.environ.get("FQ_CALENDAR_INTERVAL", "3600"))   # el calendario cambia lento
SPARK_N = 48
UA = {"User-Agent": "fq-analysis"}

# Calendario económico: feed semanal PÚBLICO y gratis de ForexFactory (faireconomy).
# Solo lectura, best-effort — jamás bloquea nada. Traducimos país->moneda e impacto
# al español; nos quedamos con lo accionable (High/Medium) y lo que aún no ocurre.
CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_IMPACT_ES = {"High": "alto", "Medium": "medio", "Low": "bajo", "Holiday": "feriado"}
_CCY_NAME = {"USD": "EE.UU.", "EUR": "Eurozona", "GBP": "Reino Unido", "JPY": "Japón",
             "CNY": "China", "AUD": "Australia", "CAD": "Canadá", "CHF": "Suiza",
             "NZD": "N. Zelanda"}

# Instrumentos de análisis. display = etiqueta amable para el portal. Sumar uno es
# una línea: la capa de análisis (regime + funding) es genérica por símbolo.
INSTRUMENTS = [
    # índices
    {"key": "NAS100", "venue": "mexc", "display": "Nasdaq 100",     "mexc": "NAS100_USDT"},
    {"key": "SPX500", "venue": "mexc", "display": "S&P 500",        "mexc": "SPX500_USDT"},
    {"key": "US30",   "venue": "mexc", "display": "Dow Jones · US30", "mexc": "US30_USDT"},
    # materias primas
    {"key": "XAU",    "venue": "okx",  "display": "Oro · XAU",      "okx": "XAU-USDT-SWAP", "fund_sym": "XAU/USDT"},
    {"key": "USOIL",  "venue": "mexc", "display": "Petróleo · WTI",  "mexc": "USOIL_USDT"},
    {"key": "UKOIL",  "venue": "mexc", "display": "Petróleo · Brent", "mexc": "UKOIL_USDT"},
    # divisas (FX majors). Directos: el contrato XXX_USDT cotiza como XXX/USD, así
    # que el LONG del contrato == LONG del par: el termómetro se lee sin invertir.
    {"key": "EUR",    "venue": "mexc", "display": "Euro · EUR/USD",  "mexc": "EUR_USDT"},
    {"key": "GBP",    "venue": "mexc", "display": "Libra · GBP/USD",  "mexc": "GBP_USDT"},
    {"key": "AUD",    "venue": "mexc", "display": "Aussie · AUD/USD", "mexc": "AUD_USDT"},
    # invertidos: el contrato cotiza XXX/USD pero se muestra USD/XXX (1/precio) y con
    # el lado del funding volteado (long del par = short del contrato). Ver _mexc_instrument.
    {"key": "JPY",    "venue": "mexc", "display": "Yen · USD/JPY",    "mexc": "JPY_USDT", "invert": True},
    {"key": "CAD",    "venue": "mexc", "display": "Loonie · USD/CAD", "mexc": "CAD_USDT", "invert": True},
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
    """MEXC contract: kline + ticker (24h) + funding history (percentil). Con
    `invert`: el contrato XXX_USDT cotiza como XXX/USD; para mostrar USD/XXX
    (p.ej. USD/JPY) invertimos precio, spark y régimen (1/precio) Y el lado del
    funding — el LONG del par es el SHORT del contrato, así que pctl y rate se
    voltean. Sin esto, USD/JPY saldría en $0.0067 y el termómetro al revés."""
    sym = inst["mexc"]; inv = bool(inst.get("invert"))
    k = _get("https://contract.mexc.com/api/v1/contract/kline/%s?interval=Min5&limit=%d"
             % (sym, 300))
    kd = (k or {}).get("data") or {}
    closes = [float(x) for x in (kd.get("close") or [])]  # MEXC: ya cronológico
    if len(closes) < 16:
        return None
    if inv:
        closes = [1.0 / c for c in closes if c]           # XXX/USD -> USD/XXX
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
            chg = float(rf) * 100.0
            out["chg_24h"] = round(-chg if inv else chg, 2)
    except Exception:
        pass
    try:                                            # funding + percentil desde la historia
        f = _get("https://contract.mexc.com/api/v1/contract/funding_rate/%s" % sym)
        rate = float((f.get("data") or {}).get("fundingRate"))
        out["funding_rate"] = round(-rate if inv else rate, 8)
        h = _get("https://contract.mexc.com/api/v1/contract/funding_rate/history"
                 "?symbol=%s&page_num=1&page_size=200" % sym)
        hist = [float(x["fundingRate"]) for x in
                ((h.get("data") or {}).get("resultList") or []) if "fundingRate" in x]
        if len(hist) >= 10:
            pctl = sum(1 for v in hist if v <= rate) / float(len(hist))
            if inv:
                pctl = 1.0 - pctl                          # long del par = short del contrato
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


def _atomic_write(path, payload):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh, default=str)
    os.replace(tmp, path)                            # atómico: el server jamás lee a medias


def run_once():
    symbols = {}
    for inst in INSTRUMENTS:
        row = build_one(inst)
        if row:
            symbols[inst["key"]] = row
    _atomic_write(OUT, {"updated": time.time(), "symbols": symbols})
    return symbols


def fetch_calendar(max_events=40):
    """Calendario económico de la semana (ForexFactory, gratis). Devuelve solo
    eventos de impacto alto/medio que AÚN no ocurrieron, en español. Best-effort:
    cualquier fallo devuelve [] y el portal simplemente no muestra la sección."""
    import datetime as _dt
    try:
        rows = _get(CAL_URL, timeout=15)
    except Exception as e:
        sys.stderr.write("[analysis] calendario: %s\n" % e)
        return []
    now = _dt.datetime.now(_dt.timezone.utc)
    out = []
    for ev in rows or []:
        impact = ev.get("impact")
        if impact not in ("High", "Medium"):
            continue
        try:
            when = _dt.datetime.fromisoformat(ev.get("date"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=_dt.timezone.utc)
        except Exception:
            continue
        if when < now:                               # solo lo que viene
            continue
        ccy = (ev.get("country") or "").upper()
        out.append({
            "title": ev.get("title"),
            "ccy": ccy,
            "region": _CCY_NAME.get(ccy, ccy),
            "impact": _IMPACT_ES.get(impact, impact.lower()),
            "impact_rank": 2 if impact == "High" else 1,
            "ts": when.astimezone(_dt.timezone.utc).isoformat(),
            "forecast": ev.get("forecast") or "",
            "previous": ev.get("previous") or "",
        })
    out.sort(key=lambda e: e["ts"])
    return out[:max_events]


def run_calendar_once():
    events = fetch_calendar()
    _atomic_write(CAL_OUT, {"updated": time.time(), "events": events})
    return events


def main():
    if "--once" in sys.argv:
        syms = run_once()
        cal = run_calendar_once()
        sys.stdout.write("[analysis] once -> %s | calendario: %d eventos\n"
                         % (", ".join(sorted(syms)) or "(sin datos)", len(cal)))
        return 0
    sys.stdout.write("[analysis] feeder cada %ds -> %s (+ calendario cada %ds)\n"
                     % (INTERVAL, OUT, CAL_INTERVAL))
    sys.stdout.flush()
    last_cal = 0.0
    while True:
        try:
            run_once()
        except Exception as e:
            sys.stderr.write("[analysis] loop: %s\n" % e)
        if time.time() - last_cal >= CAL_INTERVAL:
            try:
                run_calendar_once()
                last_cal = time.time()
            except Exception as e:
                sys.stderr.write("[analysis] calendario loop: %s\n" % e)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
