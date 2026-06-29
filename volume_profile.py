# -*- coding: utf-8 -*-
"""
================================================================================
  VOLUME PROFILE MODULE — FQ
  POC + Value Area (VAH/VAL) desde OHLCV — la pata de "referencia de volumen"
  de la confluencia triple (estructura + volumen + order-flow).
================================================================================

  Por qué: el setup de mayor probabilidad junta un nivel ESTRUCTURAL, una
  referencia de VOLUMEN y una confirmacion de ORDER-FLOW en el mismo precio. El
  bot ya tenia estructura (pivotes/OB/PD/VWAP en ict_smc + liquidity_magnet) y
  order-flow (CVD). Faltaba el volumen-por-precio: POC (precio de control) y
  Value Area (rango que acumula el 70% del volumen). Este modulo lo agrega.

  Sirve a CUALQUIER simbolo (cripto y TradFi): se deriva solo de precio+volumen.

  Aproximacion sin ticks: el volumen de cada vela se reparte UNIFORME sobre su
  rango [low, high] en bins de precio (las velas planas van al bin de su close).
  POC = bin de mayor volumen. Value Area = rango contiguo alrededor del POC que
  acumula `va_pct` del volumen, creciendo hacia el lado vecino mas pesado (regla
  clasica de Market Profile, aprox. de a un bin).

  Causalidad: daily_volume_profile usa solo las velas del dia UTC en curso;
  prior_day_profile usa el dia UTC ANTERIOR completo (niveles conocidos al abrir
  -> feature CAUSAL, apta para el gate DSR como CVD/F2/KL). PURO: sin I/O, sin red.
================================================================================
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class VolumeProfile:
    poc: float            # precio de control (centro del bin de mayor volumen)
    vah: float            # value area high
    val: float            # value area low
    total_volume: float
    n_bins: int

    def position(self, price):
        """'premium' (price>VAH) / 'discount' (price<VAL) / 'value' (dentro)."""
        return vp_position(price, self)


# ============================================================
# HELPERS
# ============================================================
def _series_days(df):
    """Fecha UTC por vela, desde 'timestamp' (ms o datetime) o DatetimeIndex.
    None si no hay timestamps usables."""
    ts = None
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], utc=True, unit="ms", errors="coerce")
        if ts.isna().all():
            ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    elif isinstance(df.index, pd.DatetimeIndex):
        idx = df.index.tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
        ts = pd.Series(idx, index=df.index)
    if ts is None or ts.isna().all():
        return None
    return ts.dt.normalize().to_numpy()


def _volume_by_price(low, high, close, vol, edges):
    """Histograma volumen-por-precio. Velas con rango: reparto UNIFORME sobre
    [low,high]; velas planas (high==low): todo el volumen al bin del close."""
    hist = np.zeros(len(edges) - 1)
    span = high - low
    flat = span <= 0
    rng = ~flat
    if rng.any():
        lo, hi, v, sp = low[rng], high[rng], vol[rng], span[rng]
        for j in range(len(edges) - 1):
            ov = np.clip(np.minimum(hi, edges[j + 1]) - np.maximum(lo, edges[j]), 0.0, None)
            hist[j] += np.sum(v * ov / sp)
    if flat.any():
        idx = np.clip(np.searchsorted(edges, close[flat], side="right") - 1, 0, len(edges) - 2)
        np.add.at(hist, idx, vol[flat])
    return hist


def _value_area(hist, va_pct):
    """(poc_i, lo_i, hi_i): indices del POC y de los bordes de la Value Area.
    Expande de a un bin hacia el lado vecino mas pesado hasta cubrir va_pct."""
    total = float(hist.sum())
    if total <= 0:
        return None
    poc_i = int(np.argmax(hist))
    lo_i = hi_i = poc_i
    acc = float(hist[poc_i])
    target = va_pct * total
    n = len(hist)
    while acc < target and (lo_i > 0 or hi_i < n - 1):
        up = hist[hi_i + 1] if hi_i < n - 1 else -1.0
        dn = hist[lo_i - 1] if lo_i > 0 else -1.0
        if up >= dn:
            hi_i += 1
            acc += float(hist[hi_i])
        else:
            lo_i -= 1
            acc += float(hist[lo_i])
    return poc_i, lo_i, hi_i


# ============================================================
# API
# ============================================================
def volume_profile(df, *, n_bins=50, va_pct=0.70):
    """POC + Value Area sobre TODAS las velas de df. VolumeProfile o None.

    n_bins: resolucion del histograma sobre [min(low), max(high)] del tramo.
    va_pct: fraccion del volumen dentro de la Value Area (0.70 estandar).
    """
    try:
        if df is None or len(df) == 0 or "volume" not in df.columns:
            return None
        low = df["low"].astype(float).to_numpy()
        high = df["high"].astype(float).to_numpy()
        close = df["close"].astype(float).to_numpy()
        vol = df["volume"].astype(float).to_numpy()
        pmin, pmax = float(np.nanmin(low)), float(np.nanmax(high))
        if not (np.isfinite(pmin) and np.isfinite(pmax)) or pmax <= pmin:
            return None
        edges = np.linspace(pmin, pmax, n_bins + 1)
        centers = (edges[:-1] + edges[1:]) / 2.0
        hist = _volume_by_price(low, high, close, vol, edges)
        va = _value_area(hist, va_pct)
        if va is None:
            return None
        poc_i, lo_i, hi_i = va
        return VolumeProfile(
            poc=float(centers[poc_i]), vah=float(centers[hi_i]),
            val=float(centers[lo_i]), total_volume=float(hist.sum()), n_bins=n_bins)
    except Exception:
        return None


def vp_position(price, profile):
    """'premium' (price>VAH) / 'discount' (price<VAL) / 'value' (dentro) / 'unknown'."""
    if profile is None:
        return "unknown"
    p = float(price)
    if p > profile.vah:
        return "premium"
    if p < profile.val:
        return "discount"
    return "value"


def _profile_of_day(df, days, day_key, n_bins, va_pct):
    pos = np.flatnonzero(days == day_key)
    if len(pos) == 0:
        return None
    return volume_profile(df.iloc[pos], n_bins=n_bins, va_pct=va_pct)


def daily_volume_profile(df, *, n_bins=50, va_pct=0.70):
    """Perfil del dia UTC EN CURSO (la fecha de la ultima vela). Si no hay
    timestamps usables, cae al perfil de todo df."""
    days = _series_days(df)
    if days is None:
        return volume_profile(df, n_bins=n_bins, va_pct=va_pct)
    return _profile_of_day(df, days, days[-1], n_bins, va_pct)


def prior_day_profile(df, *, n_bins=50, va_pct=0.70):
    """Perfil del dia UTC ANTERIOR completo — niveles de referencia CAUSALES
    (POC/VAH/VAL conocidos al abrir el dia en curso). None si no hay dia previo
    o no hay timestamps usables."""
    days = _series_days(df)
    if days is None:
        return None
    uniq = pd.unique(days)
    if len(uniq) < 2:
        return None
    return _profile_of_day(df, days, uniq[-2], n_bins, va_pct)
