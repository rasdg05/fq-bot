#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_okx_life_windows — baja de OKX spot SOLO las velas que cada señal del cubo
llegó a vivir, que es lo que hace falta para sellar la excursión EN VIDA.

Por qué no el histórico continuo: son 74.000 peticiones (~7,5 h en serie) para
7,4M velas de las que la excursión en vida usa el 8%. Las señales son ralas
(~1.000 por símbolo en 5 años) y viven poco (bars_held p50 = 21 velas, p90 = 92),
así que pedir la ventana de cada una cuesta 15.186 peticiones (~30 min). La
ventana del HORIZONTE completo costaría 77.619 — y esa excursión ya la trae el
cubo viejo, no hay que volver a medirla.

Venue: OKX SPOT, verificado contra el entry_price del cubo (ver
tools/fetch_okx_klines.py). Cache incremental por símbolo: re-ejecutable.

Uso:
  python tools/fetch_okx_life_windows.py                 # todos los cubos
  python tools/fetch_okx_life_windows.py --symbols SOL_USDT --workers 4
"""
import argparse
import glob
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fetch_okx_klines as OK      # noqa: E402

BAR_MS = OK.BAR_MS
OUT_DIR = os.environ.get("FQ_OKX_DIR", "data/okx_real")
MARGEN = 2                          # velas de cortesía tras la muerte más tardía
# Ventana MINIMA hacia adelante, igual para TODA señal viva o muerta. Existe por
# la circularidad: comparar el recorrido de ganadores contra el de perdedores es
# tautológico (un ganador tocó el TP, luego su MFE >= rr por definición; un
# perdedor no, por definición). La única comparación no circular es sobre una
# ventana FIJA que no dependa del desenlace. 96 velas = el horizonte más corto
# del cubo, y es GRATIS: la API devuelve 100 velas por llamada, así que pedir la
# ventana que acaba en entry+96 cuesta la misma petición que pedir entry+5.
MIN_FWD = 96

_lock = threading.Lock()
_hechas = [0]


def ventanas(cube):
    """(entry_ms, n_velas) por señal: hasta la muerte de su celda más longeva."""
    g = cube.groupby(["entry_ts", "direction"])["bars_held"].max()
    return [(int(pd.Timestamp(ts).value // 10**6), max(int(b) + MARGEN, MIN_FWD))
            for (ts, _), b in g.items()]


def bajar_simbolo(sym, total_reqs=None):
    inst = sym.replace("_", "-")
    path = os.path.join(OUT_DIR, "kl_life_%s.parquet" % sym)
    cube = pd.read_parquet("cosecha_cubes/tp_cube_%s.parquet" % sym,
                           columns=["entry_ts", "direction", "bars_held"])
    have = pd.read_parquet(path) if os.path.exists(path) else None
    velas = {} if have is None else dict(zip(have["ts"].astype("int64"),
                                             zip(have["high"], have["low"], have["close"])))
    n0 = len(velas)
    for entry_ms, need in ventanas(cube):
        objetivo = [entry_ms + i * BAR_MS for i in range(1, need + 1)]
        if all(t in velas for t in objetivo):
            continue
        cursor = entry_ms + (need + 1) * BAR_MS
        tope = entry_ms + BAR_MS
        while cursor > tope:
            data = OK._get(inst, cursor)
            with _lock:
                _hechas[0] += 1
            if not data:
                break
            for r in data:
                t = int(r[0])
                velas[t] = (float(r[2]), float(r[3]), float(r[4]))   # high, low, close
            cursor = min(int(r[0]) for r in data)
            time.sleep(0.05)
    if not velas:
        print("  %-10s sin velas" % sym, flush=True)
        return None
    os.makedirs(OUT_DIR, exist_ok=True)
    df = (pd.DataFrame([(t, *v) for t, v in velas.items()],
                       columns=["ts", "high", "low", "close"])
            .sort_values("ts").reset_index(drop=True))
    tmp = path + ".tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    print("  %-10s %d velas (+%d)  -> %s" % (sym, len(df), len(df) - n0, path), flush=True)
    return path


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="*", default=None)
    p.add_argument("--workers", type=int, default=5)
    a = p.parse_args(argv)
    syms = [os.path.basename(f).replace("tp_cube_", "").replace(".parquet", "")
            for f in sorted(glob.glob("cosecha_cubes/tp_cube_*.parquet"))]
    if a.symbols:
        syms = [s for s in syms if s in a.symbols]
    t0 = time.time()
    print("VENTANAS EN VIDA (OKX spot) — %d simbolos, %d workers" % (len(syms), a.workers), flush=True)
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(bajar_simbolo, syms))
    print("hecho en %.1f min (%d peticiones)" % ((time.time() - t0) / 60, _hechas[0]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
