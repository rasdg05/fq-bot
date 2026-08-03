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


# Antigüedad máxima de la última barra CVD respecto al ts consultado. Si el
# colector lleva más de esto sin escribir, la "confirmación" ya no describe el
# flujo del momento del fire.
#
# Por qué existe este guard
# -------------------------
# La ventana es causal (ts < ts_ms) y luego .tail(lookback) — correcto mientras
# el parquet se actualice. Cuando el colector se para, `tail` devuelve SIEMPRE
# las mismas últimas barras, así que cvd_confirmation sigue contestando: mismo
# imbalance, para siempre, con cara de medición viva. En el ledger del motor
# (jul-2026) eso se ve crudo: ADA registró UN solo valor de imbalance en 45
# eventos a lo largo de un mes, DOGE/LTC/XRP/BNB igual, y cvd_confirmed salió
# True en 78 de 86 aperturas. Un filtro de order-flow que nunca rechaza no está
# filtrando: está decorando. Preferimos ausencia (None -> la feature no entra
# en el ledger ni en la decisión) antes que un dato rancio indistinguible de
# uno fresco.
CVD_MAX_STALENESS_MS = int(os.environ.get("FQ_CVD_MAX_STALENESS_MIN", "180")) * 60_000


def cvd_confirmation(cvd_path, ccy, ts_ms, direction, lookback=48, win=24,
                     imb_min=0.50, max_staleness_ms=None):
    """¿El order-flow firmado confirma la dirección EN ts_ms? Lee el CVD del colector
    (FQ_CVD_COLLECT), toma la ventana CAUSAL (barras con ts < ts_ms, sin look-ahead),
    agrega venues y confirma. imb_min default 0.50 = el umbral VALIDADO con DSR (SOL/BTC,
    5 años). Devuelve dict {confirmed, imbalance, cvd_slope, n, staleness_min} o None si
    no hay data suficiente O si la data es RANCIA (ver CVD_MAX_STALENESS_MS).
    Defensivo: jamás lanza (si falta el parquet/ccy/ventana -> None)."""
    import os as _os
    if not cvd_path or not _os.path.exists(cvd_path):
        return None
    if max_staleness_ms is None:
        max_staleness_ms = CVD_MAX_STALENESS_MS
    try:
        df = pd.read_parquet(cvd_path)
        d = df[df["ccy"] == ccy]
        if d.empty:
            return None
        agg = (d[d["ts"] < int(ts_ms)]
               .groupby("ts", as_index=False)[["buy_vol", "sell_vol"]].sum())
        w = agg.sort_values("ts").tail(lookback)
        if len(w) < win:
            return None
        # Guard de rancidez: la última barra debe estar razonablemente cerca del
        # ts consultado. Sin esto un colector parado produce una confirmación
        # constante e indistinguible de una medición viva.
        last_ts = int(w["ts"].iloc[-1])
        staleness_ms = int(ts_ms) - last_ts
        if max_staleness_ms and staleness_ms > max_staleness_ms:
            return None
        f = cvd_features(w, win=win)
        return {"confirmed": bool(confirms_direction(f, direction, imb_min=imb_min)),
                "imbalance": f["imbalance"], "cvd_slope": f["cvd_slope"], "n": f["n"],
                "staleness_min": round(staleness_ms / 60_000.0, 1)}
    except Exception:
        return None


# ----------------------------- 2o medidor: persistencia / memoria del flujo -----------------------------
def flow_persistence(df, win=24):
    """Memoria del flujo firmado en las ultimas `win` barras [ts, buy_vol, sell_vol]:
      ac1    — autocorrelacion lag-1 del SIGNO del flujo (order-splitting; >0 = persistente)
      netdir — signo de la presion neta reciente (sum buy-sell)
    Es el 2o medidor VALIDADO ortogonal al CVD (BFL 2008; BTC F2 persist DSR 0.997,
    premium CVD✓&persist✓ +0.562R DSR 0.995). ac1 = la medida canonica y robusta."""
    d = df.sort_values("ts")
    delta = d["buy_vol"].to_numpy(float) - d["sell_vol"].to_numpy(float)
    w = min(int(win), len(delta))
    if w < 4:
        return {"ac1": 0.0, "netdir": 0, "n": int(len(delta))}
    seg = delta[-w:]
    s = np.sign(seg).astype(float)
    s = s - s.mean()
    den = float((s * s).sum())
    ac1 = float((s[1:] * s[:-1]).sum() / den) if den > 0 else 0.0
    return {"ac1": ac1, "netdir": int(np.sign(seg.sum())), "n": int(len(delta))}


def confirms_persistence(feat, direction, thr=0.0):
    """El flujo firmado es PERSISTENTE y alineado con la direccion? ac1>thr (signos
    agrupados = metaorden trabajandose) y la presion neta va con el trade."""
    want = 1 if direction in (1, "long", "buy") else -1
    return feat["ac1"] > thr and feat["netdir"] == want


def persistence_confirmation(cvd_path, ccy, ts_ms, direction, lookback=48, win=24, thr=0.0):
    """Persistencia del flujo CAUSAL en ts_ms (espejo de cvd_confirmation). Lee el
    colector, agrega venues, toma la ventana causal (barras con ts < ts_ms) y confirma.
    Devuelve {persistent, ac1, netdir, n} o None. Defensivo: jamas lanza."""
    import os
    if not cvd_path or not os.path.exists(cvd_path):
        return None
    try:
        df = pd.read_parquet(cvd_path)
        d = df[df["ccy"] == ccy]
        if d.empty:
            return None
        agg = (d[d["ts"] < int(ts_ms)]
               .groupby("ts", as_index=False)[["buy_vol", "sell_vol"]].sum())
        w = agg.sort_values("ts").tail(lookback)
        if len(w) < win:
            return None
        f = flow_persistence(w, win=win)
        return {"persistent": bool(confirms_persistence(f, direction, thr=thr)),
                "ac1": f["ac1"], "netdir": f["netdir"], "n": f["n"]}
    except Exception:
        return None


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
