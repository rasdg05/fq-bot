#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""regime_timeline — construye una línea de tiempo de RÉGIMEN de mercado a partir de
OHLCV, reusando la MISMA irreversibilidad KL validada en producción
(validate_regime_irreversibility.irreversibility). Es el insumo de la Fase 2 del
Psicólogo (marca/vision_psicologo_broker.md): con esto etiquetamos cada trade del
usuario con el clima de mercado que había cuando lo tomó — la ventaja que
HybridTrader no tiene, porque ellos no tienen motor de mercado propio.

Taxonomía (2 ejes, en el lenguaje del cockpit):
  · frío/caliente  = irreversibilidad KL (bajo = reversible = donde vive el edge)
  · con/sin dirección = |momentum| reciente
    -> frío·con dirección · frío·en rango · caliente·tendencia · caliente·sin dirección

Solo LEE OHLCV y calcula; no toca el motor ni difunde nada.
"""
from __future__ import annotations

import bisect
import sys

import numpy as np

sys.path.insert(0, ".")
sys.path.insert(0, "tools")
from validate_regime_irreversibility import irreversibility  # noqa: E402

FRIO_DIR = "frío·con dirección"
FRIO_RANGO = "frío·en rango"
CALIENTE_TEND = "caliente·tendencia"
CALIENTE_SINDIR = "caliente·sin dirección"
LABELS = (FRIO_DIR, FRIO_RANGO, CALIENTE_TEND, CALIENTE_SINDIR)


def classify(closes, *, kl_thr=0.34, kl_lookback=64, mom_lookback=20, mom_thr=0.01):
    """Etiqueta de régimen para una ventana de cierres (usa la cola). None si no hay
    suficiente historia. kl_thr=0.34 es el umbral validado (mismo que el bot)."""
    c = np.asarray([x for x in closes if x == x], dtype=float)   # dropna
    if len(c) < 16:
        return None
    irr = float(irreversibility(c[-kl_lookback:]))
    frio = irr < kl_thr
    if len(c) > mom_lookback and c[-mom_lookback] > 0:
        mom = c[-1] / c[-mom_lookback] - 1.0
    else:
        mom = 0.0
    con_dir = abs(mom) >= mom_thr
    if frio:
        return FRIO_DIR if con_dir else FRIO_RANGO
    return CALIENTE_TEND if con_dir else CALIENTE_SINDIR


def build_timeline(bars, *, warmup=64, step=1, **kw):
    """bars: lista de (datetime, close) ASCENDENTE. Devuelve [(datetime, label)]
    calculada en ventana creciente (el label en la barra i usa closes[:i+1] — sin
    mirar el futuro)."""
    ts = [b[0] for b in bars]
    cl = [b[1] for b in bars]
    out = []
    for i in range(warmup, len(bars), step):
        lab = classify(cl[:i + 1], **kw)
        if lab:
            out.append((ts[i], lab))
    return out


def regime_at(timeline, dt):
    """Último régimen en/antes de `dt`. timeline: [(datetime, label)] ascendente."""
    if not timeline:
        return None
    ts = [t for t, _ in timeline]
    i = bisect.bisect_right(ts, dt) - 1
    return timeline[i][1] if i >= 0 else None


def timeline_from_ohlcv(df, *, ts_col=None, close_col="close", **kw):
    """DataFrame OHLCV -> timeline. Detecta la columna de tiempo (timestamp/ts/…),
    la interpreta como ms epoch si es numérica, y ordena ascendente."""
    import pandas as pd
    from datetime import datetime, timezone

    if ts_col is None:
        for cand in ("timestamp", "ts", "time", "open_time", "date"):
            if cand in df.columns:
                ts_col = cand
                break
    if ts_col is None or close_col not in df.columns:
        return []
    tcol = df[ts_col]
    if np.issubdtype(tcol.dtype, np.number):
        def _conv(v):
            v = float(v)
            if v > 1e12:
                v /= 1000.0
            return datetime.fromtimestamp(v, tz=timezone.utc).replace(tzinfo=None)
        times = [_conv(v) for v in tcol]
    else:
        times = list(pd.to_datetime(tcol))
    closes = pd.to_numeric(df[close_col], errors="coerce").tolist()
    bars = sorted(zip(times, closes), key=lambda b: b[0])
    return build_timeline(bars, **kw)


def timelines_from_klines_dir(symbols, klines_dir, *, symbol_to_file=None, **kw):
    """Para cada símbolo, busca kl_hist_<file>.(parquet|csv) en klines_dir (mismo
    formato que el fetcher/numerai) y construye su timeline. symbol_to_file mapea el
    símbolo del broker (US100, BTCUSD) al basename de klines (BTCUSDT). Best-effort:
    los símbolos sin klines se omiten (no se inventa régimen)."""
    import os
    import numerai_crypto_pipeline as ncp   # reusa _read_klines/_kl_path (parquet|csv)

    out = {}
    for sym in symbols:
        base = (symbol_to_file or {}).get(sym, sym)
        path = None
        for ext in ("parquet", "csv"):
            p = os.path.join(klines_dir, "kl_hist_%s.%s" % (base, ext))
            if os.path.exists(p):
                path = p
                break
        if not path:
            continue
        tl = timeline_from_ohlcv(ncp._read_klines(path), **kw)
        if tl:
            out[sym] = tl
    return out
