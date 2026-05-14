# -*- coding: utf-8 -*-
"""
================================================================================
  KILLZONES + PD ARRAYS MODULE - FQ v4.1.1 Refactor
  Refinamiento temporal (killzones ICT) y direccional (jerarquia PD)
================================================================================
"""
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("fq_killzones")

CDMX_TZ = timezone(timedelta(hours=-6))

# ============================================================
# KILLZONES ICT en hora CDMX (UTC-6)
# Prioridad superior gana en overlap (Silver Bullet > London/NY Open > resto)
# ============================================================
KILLZONES_CDMX = [
    # name,             start,  end,  w_kz, priority,       order
    ("silver_bullet_lo", 3.0,   4.0,  1.40, "maxima",       1),
    ("silver_bullet_ny", 9.0,   10.0, 1.40, "maxima",       1),
    ("london_open_kz",   2.0,   5.0,  1.20, "alta",         2),
    ("ny_am_kz",         8.0,   11.0, 1.20, "alta",         2),
    ("london_close_kz",  9.5,   11.0, 1.00, "media",        3),
    ("ny_pm_kz",         13.0,  16.0, 1.10, "media-alta",   2),
    ("asia_kz",          19.0,  22.0, 0.70, "media",        3),
]

W_OUTSIDE_KZ = 0.60
PRIO_OUTSIDE = "baja"

# Map de SESSION_WEIGHTS legacy (asia/london/ny/overlap) - heredado
LEGACY_SESSION_WEIGHTS = {
    "asia":    0.50,
    "london":  0.80,
    "ny":      1.00,
    "overlap": 1.20,
}

# ============================================================
# CURRENT KILLZONE
# ============================================================
def current_killzone(now_cdmx=None):
    """
    Devuelve la killzone activa con su peso. Si hay overlap,
    gana la de mayor prioridad (silver bullet > open > resto).
    """
    if now_cdmx is None:
        now_cdmx = datetime.now(CDMX_TZ)
    h = now_cdmx.hour + now_cdmx.minute / 60.0

    # Buscar todas las KZ activas
    active = []
    for name, start, end, w, prio, order in KILLZONES_CDMX:
        # Crossing midnight no aplica a estas (todas dentro de 0-24)
        if start <= h < end:
            active.append((name, start, end, w, prio, order))

    if not active:
        # Calcular tiempo hasta proxima KZ
        next_kz = _next_killzone(h)
        return {
            "name":               "fuera",
            "priority":           PRIO_OUTSIDE,
            "w_kz":               W_OUTSIDE_KZ,
            "minutes_in_kz":      0,
            "minutes_to_next_kz": next_kz["minutes_until"],
            "next_kz_name":       next_kz["name"],
        }

    # Si hay multiples activas, gana el de menor "order"
    active.sort(key=lambda x: x[5])
    name, start, end, w, prio, _ = active[0]
    minutes_in = int((h - start) * 60)
    minutes_to_end = int((end - h) * 60)
    return {
        "name":               name,
        "priority":           prio,
        "w_kz":               w,
        "minutes_in_kz":      minutes_in,
        "minutes_to_next_kz": minutes_to_end,
        "next_kz_name":       "fin_kz",
    }

def _next_killzone(h):
    """Distancia a la proxima killzone"""
    next_kz = None
    min_dist = 999
    for name, start, end, w, prio, order in KILLZONES_CDMX:
        if start > h:
            dist = start - h
        else:
            dist = (24.0 - h) + start
        if dist < min_dist:
            min_dist = dist
            next_kz = name
    return {"name": next_kz or "asia_kz", "minutes_until": int(min_dist * 60)}

# ============================================================
# SESSION LEGACY (mantiene la asignacion vieja para hibrido)
# ============================================================
def get_legacy_session(now_cdmx=None):
    """Sesion vieja del bot: asia/london/ny/overlap.
       Returns (name, w_clock_legacy)"""
    if now_cdmx is None:
        now_cdmx = datetime.now(CDMX_TZ)
    h = now_cdmx.hour + now_cdmx.minute / 60.0
    if 7.5 <= h < 10.0:
        return "overlap", LEGACY_SESSION_WEIGHTS["overlap"]
    if 10.0 <= h < 15.0:
        return "ny", LEGACY_SESSION_WEIGHTS["ny"]
    if 2.0 <= h < 7.5:
        return "london", LEGACY_SESSION_WEIGHTS["london"]
    return "asia", LEGACY_SESSION_WEIGHTS["asia"]

# ============================================================
# HYBRID W_EFFECTIVE (decision 2 del usuario)
# ============================================================
def compute_w_effective(w_clock_legacy, w_killzone, n_closed_v2, decay_n=50):
    """
    Hibrido alpha-decay: empieza 100% w_clock_legacy, decae a 100% w_killzone
    conforme buckets v2 acumulan cerradas.
    
    alpha = max(0, 1 - n_closed_v2 / decay_n)
    w_eff = w_clock_legacy * alpha + w_killzone * (1 - alpha)
    """
    alpha = max(0.0, 1.0 - (n_closed_v2 / float(decay_n)))
    w_eff = (w_clock_legacy * alpha) + (w_killzone * (1.0 - alpha))
    return w_eff, alpha

# ============================================================
# REFINE FIELD - llena fase D del FieldState
# ============================================================
def refine_field_timing(field, n_closed_v2=0, decay_n=50):
    """Llena los campos de Fase D del FieldState con killzone + hibrido"""
    kz = current_killzone()
    field.killzone = kz["name"]
    field.killzone_priority = kz["priority"]
    field.w_killzone = kz["w_kz"]
    field.minutes_in_kz = kz["minutes_in_kz"]
    field.minutes_to_next_kz = kz["minutes_to_next_kz"]

    _, w_legacy = get_legacy_session()
    field.w_clock_legacy = w_legacy
    w_eff, alpha = compute_w_effective(w_legacy, field.w_killzone,
                                        n_closed_v2, decay_n)
    field.w_effective = w_eff
    return alpha
