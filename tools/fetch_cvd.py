# -*- coding: utf-8 -*-
"""
fetch_cvd — colector FORWARD de CVD (Cumulative Volume Delta) + feature de order-flow.

El research (research/herramientas_quant_2026.md) dio el hallazgo de microestructura:
el ORDER-FLOW FIRMADO (taker buy − sell = CVD), NO el volumen sin firmar, mueve el
precio a corto plazo (relación ~lineal). Nuestro trigger actual (FQ_USE_VOL_LIQ_TRIGGER)
usa volumen SIN firmar -> esto es el upgrade evidenciado. Y es GRATIS: el taker
buy/sell por barra ya lo dan los exchanges (OKX rubik taker-volume; Binance futures
data). Railway no está geo-bloqueado -> agrega multi-venue.

Espejo de fetch_agg_oi: cada poll baja el taker buy/sell por barra 5m de cada venue,
formato LARGO (ts, ccy, exchange, buy_vol, sell_vol) append-dedupe en /data. El CVD =
cumsum(buy − sell). cvd_features() computa el signal firmado (slope + imbalance) para,
una vez VALIDADO forward, reemplazar el trigger de volumen-sin-firmar. 0% real.

Uso:
    python tools/fetch_cvd.py --once / --loop / --report
Salida: $FQ_CVD_DIR/cvd.parquet (def /data si existe, si no data/okx).
Hijo NO-crítico del launcher (FQ_CVD_COLLECT=1).
"""
import json
import os
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

OUT_DIR = os.environ.get("FQ_CVD_DIR") or ("/data" if os.path.isdir("/data") else "data/okx")
LEDGER = os.path.join(OUT_DIR, "cvd.parquet")
CCYS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LTC"]


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_okx(ccy):
    """OKX rubik taker-volume -> [ts, buy_vol, sell_vol] (USD notional, 5m)."""
    j = _get("https://www.okx.com/api/v5/rubik/stat/taker-volume"
             "?ccy=%s&instType=CONTRACTS&period=5m" % ccy)
    rows = [(int(r[0]), float(r[2]), float(r[1])) for r in j.get("data", [])]  # [ts, sell, buy]
    return pd.DataFrame(rows, columns=["ts", "buy_vol", "sell_vol"])


def fetch_binance(ccy):
    """Binance taker buy/sell volume (geo en sandbox; anda en Railway)."""
    j = _get("https://fapi.binance.com/futures/data/takerlongshortRatio"
             "?symbol=%sUSDT&period=5m&limit=500" % ccy)
    rows = [(int(r["timestamp"]), float(r["buyVol"]), float(r["sellVol"])) for r in j]
    return pd.DataFrame(rows, columns=["ts", "buy_vol", "sell_vol"])


SOURCES = {"okx": fetch_okx, "binance": fetch_binance}


# ----------------------------- feature de order-flow firmado -----------------------------
def cvd_features(df, win=24):
    """Dado un DataFrame [ts, buy_vol, sell_vol] (UN símbolo, UN venue o agregado),
    devuelve el signal de order-flow FIRMADO de las últimas `win` barras:
      cvd        — cumulative volume delta (cumsum de buy−sell) al final
      cvd_slope  — pendiente del CVD en la ventana (signo = presión neta reciente)
      imbalance  — fracción de taker-buy en la ventana [0..1] (0.5 = neutral)
    Puro; sin red. Es el candidato a reemplazar el trigger de volumen-SIN-firmar."""
    d = df.sort_values("ts")
    buy = d["buy_vol"].to_numpy(float)
    sell = d["sell_vol"].to_numpy(float)
    delta = buy - sell
    cvd = np.cumsum(delta)
    w = min(win, len(cvd))
    if w < 2:
        return {"cvd": float(cvd[-1]) if len(cvd) else 0.0, "cvd_slope": 0.0, "imbalance": 0.5, "n": int(len(cvd))}
    seg = cvd[-w:]
    slope = float(np.polyfit(np.arange(w), seg, 1)[0])
    tb, ts_ = buy[-w:].sum(), sell[-w:].sum()
    imb = float(tb / (tb + ts_)) if (tb + ts_) > 0 else 0.5
    return {"cvd": float(cvd[-1]), "cvd_slope": slope, "imbalance": imb, "n": int(len(cvd))}


def confirms_direction(feat, direction, imb_min=0.55):
    """¿El order-flow firmado CONFIRMA la dirección del setup? LONG quiere CVD subiendo
    (slope>0) e imbalance comprador (>imb_min); SHORT al revés. Es el reemplazo
    EVIDENCIADO del trigger de volumen sin firmar — a validar forward antes de cablear."""
    if direction in (1, "long", "buy"):
        return feat["cvd_slope"] > 0 and feat["imbalance"] >= imb_min
    if direction in (-1, "short", "sell"):
        return feat["cvd_slope"] < 0 and feat["imbalance"] <= (1 - imb_min)
    return False


# ----------------------------- colector forward -----------------------------
def append_dedupe(path, new):
    if new.empty:
        return None
    if os.path.exists(path):
        try:
            new = pd.concat([pd.read_parquet(path), new], ignore_index=True)
        except Exception as e:
            print("[cvd] read %s: %s (reescribo)" % (path, e))
    out = (new.drop_duplicates(["ts", "ccy", "exchange"])
              .sort_values(["ccy", "exchange", "ts"]).reset_index(drop=True))
    tmp = path + ".tmp"
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    return out


def run_once():
    os.makedirs(OUT_DIR, exist_ok=True)
    frames, ok = [], {}
    for ccy in CCYS:
        for ex, fn in SOURCES.items():
            try:
                df = fn(ccy)
                if not df.empty:
                    df = df.copy()
                    df["ccy"] = ccy
                    df["exchange"] = ex
                    frames.append(df[["ts", "ccy", "exchange", "buy_vol", "sell_vol"]])
                    ok[ex] = ok.get(ex, 0) + 1
            except Exception as e:
                if ok.get("_err_%s" % ex) is None:
                    print("[cvd] %s ERROR (%s): %s" % (ex, ccy, str(e)[:80]))
                    ok["_err_%s" % ex] = 1
            time.sleep(0.12)
    if not frames:
        print("[cvd] sin data este poll")
        return
    out = append_dedupe(LEDGER, pd.concat(frames, ignore_index=True))
    vend = ", ".join("%s:%d" % (e, n) for e, n in ok.items() if not e.startswith("_"))
    if out is not None:
        span = (out.ts.max() - out.ts.min()) / 8.64e7
        print("[cvd] %d filas (venues: %s) span %.1fd -> %s" % (len(out), vend, span, LEDGER))


def report():
    if not os.path.exists(LEDGER):
        print("[cvd] sin ledger en %s (corré --once primero)" % LEDGER)
        return 1
    df = pd.read_parquet(LEDGER)
    print("=== CVD / order-flow firmado — últimas 24 barras (agregado por venue) ===")
    print("símbolo | imbalance | cvd_slope | lectura")
    for ccy in CCYS:
        d = df[df.ccy == ccy]
        if d.empty:
            continue
        agg = d.groupby("ts", as_index=False)[["buy_vol", "sell_vol"]].sum()
        f = cvd_features(agg, win=24)
        lect = "comprador" if f["imbalance"] > 0.55 else ("vendedor" if f["imbalance"] < 0.45 else "neutral")
        print("%-7s |   %.2f    | %+.2e | %s" % (ccy, f["imbalance"], f["cvd_slope"], lect))
    print("\n(signal firmado: reemplazo EVIDENCIADO del trigger de volumen-sin-firmar; "
          "validar forward con el gate DSR antes de cablear a la señal)")
    return 0


def main(argv):
    mode = argv[1] if len(argv) > 1 else "--once"
    if mode == "--report":
        return report()
    if mode == "--loop":
        interval = int(os.environ.get("FQ_CVD_INTERVAL", "3600"))
        print("[cvd] loop cada %ds -> %s (venues: %s)" % (interval, OUT_DIR, ", ".join(SOURCES)))
        while True:
            run_once()
            time.sleep(interval)
    else:
        run_once()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
