# -*- coding: utf-8 -*-
"""
================================================================================
  REGIME DETECTOR - cross-validation de regimes de mercado
  by RasDG_Sol + Claude (FQ v4.3)

  Detecta cambios de regimen para que el ensemble scorer ajuste su exigencia.
  Tres senales independientes votan:

   1) KL drift en distribucion de buckets (entropy_cognition.kl_divergence)
   2) Volatility z-score (ATR actual vs trailing 50)
   3) Win-rate trend (last 10 closed vs prior 10)

  Si 2 de 3 disparan -> shift_moderate. Si 3 -> deriva.

  NO modifica P_master. Solo enriquece el contexto del scorer.

  Fuentes:
   - KL divergence: ya existia en entropy_cognition.kl_divergence()
   - Volatility regime: concepto general, ver _KNOWLEDGE_NOTES.md #5
================================================================================
"""
import os
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("fq_regime")

# ============================================================
# UMBRALES (env-overridable)
# ============================================================
KL_SHIFT_THRESHOLD     = float(os.environ.get("FQ_REGIME_KL", "1.5"))
VOL_Z_SHIFT_THRESHOLD  = float(os.environ.get("FQ_REGIME_VOL_Z", "2.0"))
WR_DELTA_THRESHOLD     = float(os.environ.get("FQ_REGIME_WR_DELTA", "0.20"))
MIN_CLOSED_FOR_REGIME  = int(os.environ.get("FQ_REGIME_MIN_N", "20"))

# ============================================================
# Detectores individuales
# ============================================================
def _kl_flag():
    """True si KL drift bucket distribution > umbral"""
    try:
        import entropy_cognition as ev
        em = ev.compute_entropy_metrics()
        kl = em.get("kl_drift_25v25", 0.0)
        n_closed = em.get("n_closed", 0)
        if n_closed < MIN_CLOSED_FOR_REGIME:
            return False, kl, "n={} insuf".format(n_closed)
        return kl >= KL_SHIFT_THRESHOLD, kl, "KL={:.2f} thr={:.2f}".format(
            kl, KL_SHIFT_THRESHOLD)
    except Exception as e:
        return False, 0.0, "err: {}".format(str(e)[:40])

def _vol_z_flag(df_15m):
    """ATR(14) actual vs trailing ATR z-score. df_15m debe tener columna atr14"""
    try:
        if df_15m is None or len(df_15m) < 60 or "atr14" not in df_15m.columns:
            return False, 0.0, "datos insuf"
        atr_series = df_15m["atr14"].dropna()
        if len(atr_series) < 50:
            return False, 0.0, "atr len < 50"
        current = float(atr_series.iloc[-1])
        trailing = atr_series.iloc[-60:-1]
        mean = float(trailing.mean())
        std = float(trailing.std()) if float(trailing.std()) > 0 else 1e-9
        z = (current - mean) / std
        return abs(z) >= VOL_Z_SHIFT_THRESHOLD, z, "ATR z={:.2f} thr=+-{:.2f}".format(
            z, VOL_Z_SHIFT_THRESHOLD)
    except Exception as e:
        return False, 0.0, "err: {}".format(str(e)[:40])

def _wr_trend_flag():
    """Win-rate ultimas 10 vs prior 10 cerradas"""
    try:
        import entropy_cognition as ev
        with ev._lock:
            conn = ev._connect()
            try:
                rows = conn.execute(
                    "SELECT outcome FROM signals WHERE " + ev.AUDITABLE_SQL +
                    "ORDER BY ts_closed DESC LIMIT 20"
                ).fetchall()
            finally:
                conn.close()
        if len(rows) < 20:
            return False, 0.0, "n={} insuf".format(len(rows))
        last10 = rows[:10]
        prior10 = rows[10:20]
        def _wr(rs):
            wins = sum(1 for r in rs if r["outcome"] in ("tp1","tp2","tp3","tp4"))
            return wins / len(rs) if rs else 0
        wr_last = _wr(last10)
        wr_prior = _wr(prior10)
        delta = wr_last - wr_prior
        return abs(delta) >= WR_DELTA_THRESHOLD, delta, \
               "WR last={:.0%} prior={:.0%} delta={:+.0%}".format(
                   wr_last, wr_prior, delta)
    except Exception as e:
        return False, 0.0, "err: {}".format(str(e)[:40])

# ============================================================
# DETECCION AGREGADA
# ============================================================
def detect_regime(df_15m=None):
    """
    Returns dict:
      state:       'stable' | 'shift_moderate' | 'deriva'
      flags_fired: list de nombres de flags activos
      details:     dict por-flag con detail string
      recommend:   'normal' | 'tighten' | 'pause'
    """
    kl_fired, kl_val, kl_det      = _kl_flag()
    vol_fired, vol_z, vol_det     = _vol_z_flag(df_15m)
    wr_fired, wr_delta, wr_det    = _wr_trend_flag()

    flags = []
    if kl_fired:  flags.append("kl_drift")
    if vol_fired: flags.append("vol_z")
    if wr_fired:  flags.append("wr_trend")
    n_fired = len(flags)

    if n_fired >= 3:
        state, recommend = "deriva", "pause"
    elif n_fired == 2:
        state, recommend = "shift_moderate", "tighten"
    else:
        state, recommend = "stable", "normal"

    return {
        "state":       state,
        "flags_fired": flags,
        "n_flags":     n_fired,
        "recommend":   recommend,
        "details": {
            "kl_drift": {"fired": kl_fired, "value": kl_val, "detail": kl_det},
            "vol_z":    {"fired": vol_fired, "value": vol_z, "detail": vol_det},
            "wr_trend": {"fired": wr_fired, "value": wr_delta, "detail": wr_det},
        },
        "ts": datetime.now(timezone.utc).isoformat(),
    }

def format_regime_telegram(regime):
    """Mensaje para /regimen admin command"""
    rule = "━" * 30
    state_emoji = {
        "stable":         "estable",
        "shift_moderate": "shift moderado",
        "deriva":         "DERIVA - cambio regimen",
    }
    rec_explain = {
        "normal":   "Scorer opera con threshold estandar (>=0.55)",
        "tighten":  "Scorer exige threshold elevado (>=0.70)",
        "pause":    "Recomendado: NO nuevos trades hasta estabilizar",
    }
    lines = [
        rule,
        "  ◆ FQ · Regime Detector",
        rule,
        "  Estado:     {}".format(state_emoji.get(regime["state"], regime["state"])),
        "  Flags ON:   {} de 3".format(regime["n_flags"]),
        "  Recomienda: {}".format(rec_explain.get(regime["recommend"], regime["recommend"])),
        "",
    ]
    for name, info in regime["details"].items():
        mark = "[+]" if info["fired"] else "[.]"
        lines.append("  {} {:<10} {}".format(mark, name, info["detail"]))
    lines.append(rule)
    return "\n".join(lines)
