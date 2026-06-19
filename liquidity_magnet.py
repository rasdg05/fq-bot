# -*- coding: utf-8 -*-
"""
================================================================================
  liquidity_magnet — MOTOR DE IMANES DE LIQUIDEZ (capa 1: imanes + enumeracion)
  by RasDG_Sol + Claude
================================================================================
Tesis (RasDG): la LIQUIDEZ determina el precio. No predecimos el crecimiento del
mercado -> medimos hacia QUE liquidez va a ir el precio. La senal no es "creo que
sube"; es "el precio va a buscar el iman X". Los imanes son zonas que la liquidez
tiende a buscar:

  · VWAP daily        — ancla de valor (si macro vende pero el VWAP sostiene compra,
                        el precio tiende a barrer la liquidez).
  · racimo de MAs     — el cluster de medias moviles (EMA/SMA/Hull) = zona-iman;
                        la DIVERGENCIA precio-vs-VWMA es el tell (compradores por
                        volumen defendiendo debajo del cloud, o al reves).
  · pools de liquidez — max/min con toques (ya en ict_smc: field.pool_high/low).
  · max/min previos    — liquidez obvia (stops descansando).

Esta capa solo COMPUTA y ENUMERA los imanes (puro, testeable). El director (modo
continuacion/reversion + score de pull con calor de liquidaciones) es la capa 2.
================================================================================
"""
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


# ============================================================
# MEDIAS MOVILES (puras, sobre pandas; sin pandas_ta)
# ============================================================
def _sma(s, n):
    return s.rolling(n).mean()


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _wma(s, n):
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


def _hull(s, n):
    half = max(1, n // 2)
    return _wma(2.0 * _wma(s, half) - _wma(s, n), max(1, int(math.sqrt(n))))


def _vwma(price, vol, n):
    num = (price * vol).rolling(n).sum()
    den = vol.rolling(n).sum()
    return num / den.replace(0, np.nan)


# ============================================================
# IMAN 1: VWAP DAILY (ancla de valor)
# ============================================================
def _anchor_mask(df):
    """Mascara booleana 'desde la ultima medianoche UTC' si hay timestamps usables
    (columna 'timestamp' en ms/datetime o un DatetimeIndex); si no -> None."""
    try:
        ts = None
        if "timestamp" in df.columns:
            ts = pd.to_datetime(df["timestamp"], utc=True, unit="ms", errors="coerce")
            if ts.isna().all():
                ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        elif isinstance(df.index, pd.DatetimeIndex):
            ts = df.index.tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
            ts = pd.Series(ts, index=df.index)
        if ts is None or ts.isna().all():
            return None
        last_day = ts.iloc[-1].normalize()
        return (ts >= last_day).to_numpy()
    except Exception:
        return None


def daily_vwap(df, *, fallback_bars=96):
    """VWAP anclado al inicio del dia UTC (sum(tp*vol)/sum(vol)). Si no hay
    timestamps usables -> VWAP rodante sobre las ultimas `fallback_bars` velas
    (96 x 15m ~= 24h), buena aproximacion. float o None."""
    try:
        if df is None or len(df) == 0 or "volume" not in df.columns:
            return None
        tp = (df["high"].astype(float) + df["low"].astype(float)
              + df["close"].astype(float)) / 3.0
        vol = df["volume"].astype(float)
        mask = _anchor_mask(df)
        if mask is not None and mask.any():
            tpv = float((tp.to_numpy()[mask] * vol.to_numpy()[mask]).sum())
            vv = float(vol.to_numpy()[mask].sum())
        else:
            tpv = float((tp.iloc[-fallback_bars:] * vol.iloc[-fallback_bars:]).sum())
            vv = float(vol.iloc[-fallback_bars:].sum())
        return (tpv / vv) if vv > 0 else None
    except Exception:
        return None


# ============================================================
# IMAN 2: RACIMO DE MEDIAS MOVILES (+ tell de divergencia VWMA)
# ============================================================
def ma_cloud(df, *, periods=(20, 50, 100, 200)):
    """Racimo de MAs como zona-iman + el tell de DIVERGENCIA precio vs VWMA.
    Devuelve dict o None:
      low/high/center : rango y mediana del cluster de MAs (EMA+SMA por periodo + Hull9)
      vwma            : VWMA(20) (la media que pesa por volumen)
      price           : ultimo close
      below           : price < center (debajo del cloud = stack bajista)
      vwma_above      : price > vwma (compradores por volumen sostienen)
      divergence      : (below y vwma_above) o (arriba del cloud y debajo del vwma)
                        -> el caso 'macro vende pero el volumen compra' (o al reves)
    """
    try:
        if df is None or "close" not in df.columns or len(df) < 10:
            return None
        close = df["close"].astype(float)
        price = float(close.iloc[-1])
        # usa los periodos que la data permite (el bot fetchea ~200 velas -> entran
        # 20/50/100/200; con menos, los que quepan). MA con NaN se descarta abajo.
        usable = [n for n in periods if n <= len(df)]
        if not usable:
            return None
        mas = []
        for n in usable:
            mas.append(float(_ema(close, n).iloc[-1]))
            mas.append(float(_sma(close, n).iloc[-1]))
        mas.append(float(_hull(close, 9).iloc[-1]))
        mas = [m for m in mas if m == m and m > 0]      # descarta NaN
        if not mas:
            return None
        vwma = None
        if "volume" in df.columns:
            v = float(_vwma(close, df["volume"].astype(float), 20).iloc[-1])
            vwma = v if v == v and v > 0 else None
        mas_sorted = sorted(mas)
        center = mas_sorted[len(mas_sorted) // 2]        # mediana
        below = price < center
        out = {"low": min(mas), "high": max(mas), "center": center,
               "vwma": vwma, "price": price, "below": below,
               "vwma_above": None, "divergence": False}
        if vwma is not None:
            vwma_above = price > vwma
            out["vwma_above"] = vwma_above
            out["divergence"] = (below and vwma_above) or ((not below) and (not vwma_above))
        return out
    except Exception:
        return None


# ============================================================
# ENUMERACION DE IMANES
# ============================================================
@dataclass
class Magnet:
    price: float
    kind: str          # vwap|ma_cloud|pool_high|pool_low|prior_high|prior_low
    side: str          # 'above' | 'below' (respecto al precio actual)
    note: str = ""


def enumerate_magnets(df, field, price, *, prior_bars=96):
    """Lista de imanes de liquidez cerca del precio: VWAP daily, racimo de MAs,
    pools (ya en el field de ict_smc), y max/min previos. Cada uno con su lado
    (arriba/abajo del precio) -> la capa 2 elige hacia cual va el precio."""
    price = float(price)
    mags = []

    def add(p, kind, note=""):
        try:
            p = float(p)
        except (TypeError, ValueError):
            return
        if p != p or p <= 0:
            return
        mags.append(Magnet(p, kind, "above" if p >= price else "below", note))

    add(daily_vwap(df), "vwap", "VWAP daily")
    cloud = ma_cloud(df)
    if cloud:
        add(cloud["center"], "ma_cloud", "racimo MAs")

    if field is not None:
        ph = getattr(field, "pool_high", None)
        pl = getattr(field, "pool_low", None)
        if ph is not None:
            add(getattr(ph, "price", None), "pool_high", "liquidez sell-side")
        if pl is not None:
            add(getattr(pl, "price", None), "pool_low", "liquidez buy-side")

    if df is not None and len(df) > 5 and "high" in df.columns:
        window = df.iloc[-prior_bars:-1] if len(df) > prior_bars else df.iloc[:-1]
        if len(window):
            add(float(window["high"].astype(float).max()), "prior_high", "max previo")
            add(float(window["low"].astype(float).min()), "prior_low", "min previo")

    return mags


# ============================================================
# DIRECTOR (capa 2): modo (continuacion/reversion) + target + senal
# ============================================================
def context_mode(cloud):
    """Modo y direccion desde el cloud de MAs (v1; proxy de la entropia multi-TF):
      · DIVERGENCIA (precio debajo del cloud pero sobre VWMA, o al reves) -> 'reversal':
        el volumen defiende contra el stack -> sweep & reverse hacia el cloud.
      · sin divergencia -> 'continuation' en la direccion del stack (precio vs cloud).
    Devuelve (mode, direction) con direction in {'long','short',None}. La integracion
    de field.bias_4h/1h + entropy_cognition (entropia multi-TF plena) es refinamiento.
    """
    if not cloud:
        return "none", None
    below = bool(cloud.get("below"))
    if cloud.get("divergence"):
        # below & vwma_above -> compran abajo -> reversion LONG hacia el cloud;
        # above & vwma_below -> distribuyen arriba -> reversion SHORT hacia el cloud.
        return "reversal", ("long" if below else "short")
    return "continuation", ("short" if below else "long")


def _heat(liq_snapshot, direction):
    """Calor de liquidaciones A FAVOR de la direccion [0,1] (tesis squeeze)."""
    if not liq_snapshot or not liq_snapshot.get("fresh"):
        return 0.0
    intensity = max(0.0, min(1.0, float(liq_snapshot.get("intensity", 0.0))))
    skew = max(-1.0, min(1.0, float(liq_snapshot.get("skew", 0.0))))
    want = 1.0 if direction == "long" else -1.0
    return max(0.0, intensity * max(0.0, want * skew))


def best_target(df, field, price, *, liq_snapshot=None, vol_score=0.0,
                min_rr=1.5, stop_buffer=0.0015):
    """Senal del Motor de Imanes (v1): elige modo+direccion (context_mode), busca la
    SIGUIENTE liquidez (iman) en esa direccion con R:R >= min_rr, y arma la senal
    {direction, mode, entry, stop, tp, rr, pull, why}. None si no hay setup valido.
    tp = la liquidez a tomar (el iman); stop = mas alla del iman opuesto cercano
    (invalidacion estructural); pull [0,1] = confianza (volumen + calor + modo)."""
    mode, direction = context_mode(ma_cloud(df))
    if direction is None:
        return None
    mags = enumerate_magnets(df, field, float(price))
    return build_signal(float(price), mags, mode, direction, liq_snapshot=liq_snapshot,
                        vol_score=vol_score, min_rr=min_rr, stop_buffer=stop_buffer)


def build_signal(price, magnets, mode, direction, *, liq_snapshot=None, vol_score=0.0,
                 min_rr=1.5, stop_buffer=0.0015):
    """Arma la senal a partir de imanes YA enumerados + modo/direccion. Reutilizado
    por best_target (vela a vela) y por el backtest vectorizado (mismo criterio)."""
    price = float(price)
    want_above = (direction == "long")
    side = [m for m in magnets if (m.price > price) == want_above and m.price != price]
    opp = [m for m in magnets if (m.price < price) == want_above and m.price != price]
    if not side:
        return None
    # target = la liquidez mas CERCANA en la direccion (la proxima a ser buscada)
    target = min(side, key=lambda m: m.price) if want_above \
        else max(side, key=lambda m: m.price)
    tp = target.price
    # stop = mas alla del iman opuesto mas cercano (o un buffer si no hay)
    if opp:
        inval = max(opp, key=lambda m: m.price).price if want_above \
            else min(opp, key=lambda m: m.price).price
    else:
        inval = price
    stop = inval * (1 - stop_buffer) if want_above else inval * (1 + stop_buffer)
    risk, reward = abs(price - stop), abs(tp - price)
    if risk <= 0 or reward <= 0:
        return None
    rr = reward / risk
    if rr < min_rr:
        return None
    pull = max(0.0, min(1.0, 0.45 * float(vol_score)
                        + 0.40 * _heat(liq_snapshot, direction)
                        + 0.15 * (1.0 if mode == "reversal" else 0.6)))
    return {"direction": direction, "mode": mode, "entry": price, "stop": float(stop),
            "tp": float(tp), "rr": float(rr), "pull": float(pull),
            "target_kind": target.kind,
            "why": "{} {} -> {} @ {:.4f} (RR {:.2f}, pull {:.2f})".format(
                mode, direction, target.kind, tp, rr, pull)}
