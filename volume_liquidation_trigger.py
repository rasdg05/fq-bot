# -*- coding: utf-8 -*-
"""
================================================================================
  volume_liquidation_trigger — confirmacion de disparo por VOLUMEN (+ LIQUIDACIONES)
  by RasDG_Sol + Claude
================================================================================
Reemplaza el VETO DEL SCORER over-fit (fusion_engine §11, gate de regime "deriva")
cuando FQ_USE_VOL_LIQ_TRIGGER=1.

Filosofia: si lo PREDICTIVO esta muerto (deflacion), un scorer ensemble que finge
predecir es la parte deshonesta. Confirmar el disparo sobre EVENTOS REALES Y
OBSERVABLES — un SURGE de volumen y/o INTENSIDAD de liquidaciones — es mas honesto
y da la frecuencia que VIP necesita. NO toca los gates ESTRUCTURALES (sesgo ICT,
liquidez, confluencia>=3, P_master, R:R): esos siguen exigiendo setup real. Solo
cambia el VETO predictivo por una CONFIRMACION de microestructura.

Liquidaciones: el snapshot lo provee liquidation_feed (fase 2: feed externo, p.ej.
el stream gratis !forceOrder@arr de Binance). SIN feed -> confirma SOLO por volumen
(degradacion segura: no rompe, no asume datos que no existen).

Todo lo pesado es inyectado / leido de columnas -> funciones puras y testeables.
Cada fire (con o sin este trigger) se sigue midiendo en motor_paper: VIP recibe y
el ledger mide en paralelo -> no se vuela a ciegas.
================================================================================
"""
import os


def _flag(name, default="0"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


ENABLED = _flag("FQ_USE_VOL_LIQ_TRIGGER", "0")
# Umbral de confirmacion combinado [0,1]. Deliberadamente MAS BAJO que el scorer
# (0.70) -> mas fires; pero > 0 -> real (exige surge de volumen y/o fuel de liq).
MIN_CONFIRM = float(os.environ.get("FQ_VOL_LIQ_MIN_CONFIRM", "0.30"))
VOL_WEIGHT = float(os.environ.get("FQ_VOL_LIQ_VOL_WEIGHT", "0.6"))
LIQ_WEIGHT = float(os.environ.get("FQ_VOL_LIQ_LIQ_WEIGHT", "0.4"))
# Surge de volumen: ratio reciente/baseline que mapea a score 1.0.
VOL_SURGE_MULT = float(os.environ.get("FQ_VOL_LIQ_SURGE_MULT", "1.4"))
# Tesis de liquidaciones: 'momentum' (squeeze: shorts liquidados -> fuel LONG) o
# 'reversion' (fade del cascade). Default momentum.
LIQ_THESIS = os.environ.get("FQ_VOL_LIQ_THESIS", "momentum").strip().lower()


def volume_surge_score(df_15m, *, lookback=20, surge_mult=None):
    """Score [0,1] del exceso de volumen reciente sobre el baseline. recent = media
    de las ultimas 3 velas; baseline = media de las `lookback` previas (excl. las 3
    recientes). 1.0 si ratio>=surge_mult, 0 si <=1.0, lineal entremedio. Sin datos
    -> 0.0 (conservador: no confirma sobre lo que no se ve)."""
    surge_mult = VOL_SURGE_MULT if surge_mult is None else surge_mult
    try:
        if df_15m is None or len(df_15m) < lookback + 3 or "volume" not in df_15m.columns:
            return 0.0, "sin volume data"
        recent = float(df_15m["volume"].iloc[-3:].mean())
        baseline = float(df_15m["volume"].iloc[-lookback:-3].mean())
        if baseline <= 0:
            return 0.0, "baseline 0"
        ratio = recent / baseline
        if ratio >= surge_mult:
            s = 1.0
        elif ratio <= 1.0:
            s = 0.0
        else:
            s = (ratio - 1.0) / (surge_mult - 1.0)
        return max(0.0, min(1.0, s)), "vol {:.2f}x".format(ratio)
    except Exception as e:
        return 0.0, "vol err: {}".format(str(e)[:40])


def liquidation_fuel_score(liq_snapshot, direction):
    """Score [0,1] del 'combustible' de liquidaciones para la direccion operable.

    liq_snapshot (de liquidation_feed) = dict con:
      intensity [0,1]  magnitud total de liquidaciones en la ventana (normalizada)
      skew      [-1,1] sesgo de lado: +1 todo SHORT liquidado, -1 todo LONG
      fresh     bool   el feed tiene datos recientes (si no -> no se usa)

    Tesis 'momentum'/squeeze (default): un LONG se favorece cuando se liquidan
    SHORTS (squeeze al alza, skew>0); un SHORT cuando se liquidan LONGS. Tesis
    'reversion': al reves (fade del cascade). Sin feed/no-fresh -> 0.0.
    """
    if not liq_snapshot or not liq_snapshot.get("fresh"):
        return 0.0, "sin liq"
    intensity = max(0.0, min(1.0, float(liq_snapshot.get("intensity", 0.0))))
    skew = max(-1.0, min(1.0, float(liq_snapshot.get("skew", 0.0))))
    want = 1.0 if direction == "long" else -1.0
    align = max(0.0, want * skew)              # cuanto del skew va A FAVOR (momentum)
    if LIQ_THESIS == "reversion":
        align = max(0.0, -want * skew)         # fade: long con LONGS liquidados
    s = max(0.0, min(1.0, intensity * align))
    return s, "liq int={:.2f} skew={:+.2f}".format(intensity, skew)


def confirm(df_15m, liq_snapshot, direction, *, min_confirm=None):
    """¿Confirma el disparo por VOLUMEN (+ LIQUIDACIONES)? Reemplaza el veto del
    scorer. Sin feed de liquidaciones -> confirma solo por volumen (no rompe).
    Devuelve (ok: bool, reason: str, score: float [0,1])."""
    thr = MIN_CONFIRM if min_confirm is None else min_confirm
    vol_s, vol_r = volume_surge_score(df_15m)
    liq_s, liq_r = liquidation_fuel_score(liq_snapshot, direction)
    if liq_snapshot and liq_snapshot.get("fresh"):
        denom = VOL_WEIGHT + LIQ_WEIGHT
        score = ((VOL_WEIGHT * vol_s + LIQ_WEIGHT * liq_s) / denom) if denom else vol_s
        src = "vol+liq"
    else:
        score = vol_s
        src = "vol-only"
    ok = score >= thr
    reason = "{} score={:.2f} (>={:.2f}? {}) [{} | {}]".format(
        src, score, thr, "OK" if ok else "NO", vol_r, liq_r)
    return ok, reason, score
