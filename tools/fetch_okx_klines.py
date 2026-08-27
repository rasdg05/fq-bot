#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_okx_klines — OHLCV 5m histórico de OKX SPOT, que es la regla con la que se
cosecharon los cubos (`cosecha_shard --exchange okx`, por defecto).

POR QUÉ NO VALE BINANCE. Verificado sobre SOL (ago-2026): el `entry_price` de las
señales del cubo coincide EXACTO con el close de OKX spot (5/5) y con nada de
Binance (0/5 en el swap; contra klines de futuros de Binance, el 22% de los entries
cae FUERA del [low, high] de la vela correspondiente). Re-etiquetar un cubo con
velas de otro venue no es "un poco de ruido": mueve el bar en que salta la barrera
y con él la vida del trade, que es justo lo que la excursión en vida recorta.

OJO CON EL DIRECTORIO. `fetch_binance_vision_klines` escribe por defecto en
`data/okx/` — un nombre heredado que guarda velas de BINANCE. No mezcles: este
tool escribe en `data/okx_real/` y sella la procedencia en el parquet.

MECÁNICA. /api/v5/market/history-candles pagina hacia ATRÁS: `after` = "más nuevo
que" excluyente, 100 velas por llamada, ~20 req/2s por IP. Se baja por tramos y se
cachea incremental: re-ejecutable, retoma donde quedó (el contenedor es efímero;
un job de horas TIENE que sobrevivir a un corte).

Uso:
  python tools/fetch_okx_klines.py SOL-USDT --start 2021-06-15 --end 2026-07-01
  python tools/fetch_okx_klines.py --from-cubes          # deduce símbolos y rangos
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
from datetime import timedelta

import pandas as pd

API = "https://www.okx.com/api/v5/market/history-candles"
DEFAULT_DIR = os.environ.get("FQ_OKX_DIR", "data/okx_real")
COLS = ["ts", "open", "high", "low", "close", "volume"]
BAR_MS = 300_000
LIMIT = 100
VENUE = "okx_spot"


def _get(inst, after_ms, tries=4):
    """Una página (<=100 velas), más viejas que after_ms. curl: urllib recibe 403
    del proxy de salida en este entorno."""
    url = "%s?instId=%s&bar=5m&limit=%d&after=%d" % (API, inst, LIMIT, after_ms)
    for k in range(tries):
        r = subprocess.run(["curl", "-sS", "--max-time", "40", url],
                           capture_output=True, text=True)
        try:
            j = json.loads(r.stdout)
        except Exception:
            time.sleep(1.5 * (k + 1))
            continue
        if j.get("code") == "0":
            return j.get("data", [])
        time.sleep(1.5 * (k + 1))          # rate limit / error transitorio
    return None


def fetch(inst, start, end, out_dir=DEFAULT_DIR, pause=0.11):
    """Baja [start, end] hacia atrás. Incremental: no re-pide lo ya cacheado."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "kl_%s_5m.parquet" % inst.replace("-", "_"))
    have = pd.read_parquet(path) if os.path.exists(path) else pd.DataFrame(columns=COLS)
    seen = set(have["ts"].astype("int64").tolist()) if len(have) else set()
    lo = int(pd.Timestamp(start).value // 10**6)
    hi = int(pd.Timestamp(end).value // 10**6)

    parts = [have] if len(have) else []
    cursor = hi
    n_new = 0
    vacias = 0
    t0 = time.time()
    while cursor > lo:
        # Si ya tenemos toda esta ventana cacheada, salta sin pedirla.
        ventana = [cursor - i * BAR_MS for i in range(1, LIMIT + 1)]
        if all(t in seen for t in ventana):
            cursor -= LIMIT * BAR_MS
            continue
        data = _get(inst, cursor)
        if data is None:
            print("  [okx] %s: fallo persistente en %d; corto" % (inst, cursor))
            break
        if not data:
            vacias += 1
            if vacias >= 3:
                break                      # antes de la inception del par
            cursor -= LIMIT * BAR_MS
            continue
        vacias = 0
        df = pd.DataFrame([r[:6] for r in data], columns=COLS)
        df["ts"] = df["ts"].astype("int64")
        for c in COLS[1:]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna()
        parts.append(df)
        n_new += len(df)
        seen.update(df["ts"].tolist())
        cursor = int(df["ts"].min())       # 'after' es excluyente: sigue desde ahí
        if n_new and n_new % 20000 < LIMIT:
            print("  [okx] %s: %d velas nuevas (%.0fs) hasta %s"
                  % (inst, n_new, time.time() - t0,
                     pd.Timestamp(cursor, unit="ms")), flush=True)
        time.sleep(pause)
        # Guardado periodico: el contenedor es efimero.
        if n_new and n_new % 50000 < LIMIT:
            _save(parts, path)
    if not parts:
        print("  [okx] %s: sin data" % inst)
        return path
    out = _save(parts, path)
    print("  [okx] %s: +%d -> %d velas 5m (%s .. %s) %s"
          % (inst, n_new, len(out), pd.Timestamp(out.ts.min(), unit="ms"),
             pd.Timestamp(out.ts.max(), unit="ms"), path), flush=True)
    return path


def _save(parts, path):
    out = (pd.concat(parts, ignore_index=True)
             .drop_duplicates("ts").sort_values("ts").reset_index(drop=True))
    out.attrs["venue"] = VENUE
    tmp = path + ".tmp"
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    parts[:] = [out]
    return out


def instruments_from_cubes(cube_dir="cosecha_cubes"):
    """(instId, start, end) por cubo: el rango de señales + margen de horizonte."""
    outs = []
    for f in sorted(glob.glob(os.path.join(cube_dir, "tp_cube_*.parquet"))):
        sym = os.path.basename(f).replace("tp_cube_", "").replace(".parquet", "")
        d = pd.read_parquet(f, columns=["entry_ts"])
        outs.append((sym.replace("_", "-"),
                     (d.entry_ts.min() - timedelta(days=2)).date(),
                     (d.entry_ts.max() + timedelta(days=4)).date()))
    return outs


def main(argv=None):
    p = argparse.ArgumentParser(description="Klines 5m de OKX spot")
    p.add_argument("inst", nargs="?", help="p.ej. SOL-USDT")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--out-dir", default=DEFAULT_DIR)
    p.add_argument("--from-cubes", action="store_true")
    a = p.parse_args(argv)
    jobs = instruments_from_cubes() if a.from_cubes else [(a.inst, a.start, a.end)]
    for inst, s, e in jobs:
        print(">>> %s  %s -> %s" % (inst, s, e), flush=True)
        fetch(inst, s, e, a.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
