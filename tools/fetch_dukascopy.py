#!/usr/bin/env python3
"""fetch_dukascopy — baja OHLCV histórico de Dukascopy al formato del pipeline.

Escribe data/dukascopy/<sym>_<tf>.parquet [ts, open, high, low, close, volume]
(igual que build_dataset) para que la cosecha lo CACHEE y construya el cubo —
desacople data/venue: validamos TradFi sobre esta historia profunda; la señal se
ejecuta en el perp (MEXC). Transfiere KL (precio) + base; NO el order-flow (CVD).

  python tools/fetch_dukascopy.py --symbol XAU/USD --tf 5m --years 2
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

INTERVAL_ATTR = {"1m": "INTERVAL_MIN_1", "5m": "INTERVAL_MIN_5",
                 "15m": "INTERVAL_MIN_15", "1h": "INTERVAL_HOUR_1"}


# Dukascopy nombra los índices distinto a los tickers de futuros (NQ/ES/YM).
# Mapeamos cada ticker común a substrings candidatos (se prueban en orden; el 1ro
# que matchea gana). NASDAQ = "USA 100 Technical Index" -> usatechidxusd -> el
# substring que resuelve es USATECH (por eso USA100 falló en el probe #116).
# NQ resolvió a INSTRUMENT_US_TECH_US_USD -> el patrón de índices US es
# US_<clave>_US. Por eso los alias prueban primero la forma US<clave> (sin _).
ALIASES = {
    "NQ":     ["USTEC", "USATECH", "USA100", "NAS100", "TECH100", "NDX"],
    "NAS100": ["USTEC", "USATECH", "USA100", "NAS100", "NDX"],
    "NASDAQ": ["USTEC", "USATECH", "USA100", "NAS100", "NDX"],
    "US100":  ["USTEC", "USATECH", "USA100", "US100", "NDX"],
    "ES":     ["US500", "USSPX", "USA500", "SPX", "SP500"],
    "SPX":    ["US500", "USSPX", "USA500", "SPX", "SP500"],
    "SP500":  ["US500", "USSPX", "USA500", "SPX", "SP500"],
    "US500":  ["US500", "USSPX", "USA500", "SPX", "SP500"],
    "WTI":    ["LIGHT", "WTI", "USOIL", "CRUDE"],   # WTI = Light Sweet Crude -> E_LIGHT
    "USOIL":  ["LIGHT", "WTI", "USOIL", "CRUDE"],
    "OIL":    ["LIGHT", "WTI", "USOIL"],
    "YM":     ["USDOW", "USA30", "US30", "DOW", "WALL"],
    "DOW":    ["USDOW", "USA30", "US30", "DOW", "WALL"],
    "US30":   ["USDOW", "USA30", "US30", "DOW"],
}


def _inst_names(I):
    return [n for n in dir(I) if "INSTRUMENT" in n]


def _match(names, kw):
    k = kw.upper().replace("/", "").replace("_", "").replace(" ", "")
    return [n for n in names if k in n.upper().replace("_", "")]


def _resolve(I, keyword):
    """Resuelve el instrumento por keyword, probando los alias de índices en orden.
    Devuelve la lista de matches (vacía si nada resuelve)."""
    names = _inst_names(I)
    key = keyword.upper().replace("/", "").replace(" ", "")
    for kw in ALIASES.get(key, [keyword]):
        hits = _match(names, kw)
        if hits:
            return hits
    return []


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", help="p.ej. XAU/USD, LIGHT, NQ, USATECH")
    p.add_argument("--tf", default="5m")
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--out", default=None)
    p.add_argument("--list-idx", action="store_true",
                   help="lista los instrumentos de índices disponibles y sale")
    a = p.parse_args(argv)

    import dukascopy_python as dk
    from dukascopy_python import instruments as I
    INTERVAL = getattr(dk, INTERVAL_ATTR.get(a.tf, "INTERVAL_MIN_5"))
    OFFER = getattr(dk, "OFFER_SIDE_BID")

    if a.list_idx:
        idx = sorted(n for n in _inst_names(I) if "IDX" in n.upper())
        print("== instrumentos IDX disponibles (%d) ==" % len(idx))
        for n in idx:
            print("   ", n)
        return 0
    if not a.symbol:
        print("--symbol requerido (o usa --list-idx)")
        return 2

    cands = _resolve(I, a.symbol)
    if not cands:
        print("instrumento NO resuelto para '%s'. Instrumentos IDX disponibles:" % a.symbol)
        for n in sorted(n for n in _inst_names(I) if "IDX" in n.upper()):
            print("   ", n)
        return 1
    inst_name = cands[0]
    inst = getattr(I, inst_name)
    print("[dukascopy] %s -> %s  (tf=%s, %.1f años)" % (a.symbol, inst_name, a.tf, a.years), flush=True)

    end = datetime.now(timezone.utc).replace(tzinfo=None)
    start = end - timedelta(days=int(a.years * 365))
    frames = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=90), end)
        try:
            df = dk.fetch(inst, INTERVAL, OFFER, cur, nxt)
            n = 0 if df is None else len(df)
            if n:
                frames.append(df)
            print("  %s..%s -> %d barras" % (cur.date(), nxt.date(), n), flush=True)
        except Exception as e:
            print("  %s..%s ERR %s" % (cur.date(), nxt.date(), str(e)[:90]), flush=True)
        cur = nxt

    if not frames:
        print("SIN DATA")
        return 1
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df.columns = [c.lower() for c in df.columns]
    # timestamp robusto entre versiones de pandas. asi8 daba 0 en el runner
    # (ts -> 1970); el index puede venir DatetimeIndex (tz-aware/naive) o columna.
    if not isinstance(df.index, pd.DatetimeIndex):
        tcol = next((c for c in df.columns if c in ("timestamp", "time", "date")), None)
        if tcol is None:
            print("sin timestamp usable. cols=%s idx_dtype=%s" % (list(df.columns), df.index.dtype))
            return 1
        df = df.set_index(pd.to_datetime(df[tcol], utc=True))
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    # Schema CANÓNICO del pipeline (bt_data.OHLCV_COLUMNS): la columna se llama
    # "timestamp" y es datetime64[ns] (UTC naive), igual que build_dataset — NO
    # "ts" ni epoch-ms int (cosecha_shard._data_range lee df["timestamp"]).
    ts = idx.values.astype("datetime64[ns]")
    print("[ts] dtype=%s primero=%s ultimo=%s" % (ts.dtype, idx[0], idx[-1]), flush=True)
    vol = df["volume"] if "volume" in df.columns else 0.0
    out = pd.DataFrame({
        "timestamp": ts,
        "open": df["open"].astype(float).values,
        "high": df["high"].astype(float).values,
        "low": df["low"].astype(float).values,
        "close": df["close"].astype(float).values,
        "volume": (vol.astype(float).values if hasattr(vol, "astype") else vol),
    }).dropna().reset_index(drop=True)

    if a.out:
        path = a.out
    else:
        sys.path.insert(0, ".")
        import bt_data
        path = bt_data.dataset_path("data", "dukascopy", a.symbol, a.tf)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out.to_parquet(path, index=False)
    t0 = out["timestamp"].min() if len(out) else None
    t1 = out["timestamp"].max() if len(out) else None
    span = (t1 - t0).total_seconds() / 86400.0 if len(out) else 0.0
    print("OK %s  filas=%d  span %.0f días (%.1f años)  %s..%s" % (
        path, len(out), span, span / 365.0,
        (t0.date() if t0 is not None else "—"),
        (t1.date() if t1 is not None else "—")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
