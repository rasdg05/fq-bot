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
UTC_TZ  = timezone.utc

# ============================================================
# KILLZONES ICT en hora CDMX (UTC-6) - v5.2 reforma
#
# Calibrado al estandar ICT (referencia: howtotrade.com Silver Bullet)
#   Silver Bullet London  : 3:00-4:00 AM EST (NY) = 2:00-3:00 CDMX
#   Silver Bullet NY AM   : 10:00-11:00 AM EST    = 9:00-10:00 CDMX
#   Silver Bullet NY PM   : 2:00-3:00 PM EST      = 1:00-2:00 CDMX (PM)
#
# Cambios v5.2 (calibrado contra senales tacticas observadas en 2026-06-01):
#   - asia_open (17:00-18:30): recompensa franja de la 6 PM donde el bot
#     historicamente daba senales rentables pero quedaban penalizadas como
#     "fuera de killzone".
#   - eu_pre_open (00:30-02:00): pre-apertura europea, momentum genuino.
#   - ny_close_hour (15:00-16:00): PENALTY explicito. Ultima hora de NY,
#     liquidez se evapora y el bot daba falsos positivos.
#   - asia_kz recortada (0.70 -> 0.65) para reflejar menor liquidez efectiva.
#
# Prioridad superior gana en overlap (Silver Bullet > Open > resto > penalty).
# El penalty (ny_close_hour) tiene la menor prioridad: cualquier KZ valida
# encima de el la sobreescribe.
# ============================================================
KILLZONES_CDMX = [
    # name,                 start,  end,  w_kz, priority,       order
    ("silver_bullet_lo",     2.0,   3.0,  1.40, "maxima",       1),
    ("silver_bullet_ny_am",  9.0,   10.0, 1.40, "maxima",       1),
    ("silver_bullet_ny_pm",  13.0,  14.0, 1.40, "maxima",       1),
    ("london_open_kz",       1.0,   5.0,  1.20, "alta",         2),
    ("ny_am_kz",             8.0,   11.0, 1.20, "alta",         2),
    ("ny_pm_kz",             13.0,  15.0, 1.10, "media-alta",   2),  # acortada: termina antes del penalty
    ("asia_open",            17.0,  18.5, 1.05, "alta-volumen", 2),  # nuevo: recompensa franja 6PM
    ("eu_pre_open",          0.5,   2.0,  1.05, "alta-volumen", 2),  # nuevo: pre-apertura EU
    ("london_close_kz",      9.5,   11.0, 1.00, "media",        3),
    ("asia_kz",              19.0,  22.0, 0.65, "media",        3),  # recortado de 0.70
    ("ny_close_hour",       15.0,  16.0, 0.45, "penalty",       9),  # nuevo: ultima hora NY (penalty)
]

W_OUTSIDE_KZ = 0.60
PRIO_OUTSIDE = "baja"

# ============================================================
# WEEKEND FILTER - veto total entre cierre semanal y apertura
# Cierre: viernes 17:00 EST (UTC-5) = 22:00 UTC
# Apertura: domingo 17:00 EST       = 22:00 UTC
# ============================================================
def is_weekend_closed(now_utc=None):
    """
    Devuelve True si estamos dentro del cierre semanal (sab/dom).

    Ventana cerrada: viernes 22:00 UTC -> domingo 22:00 UTC
    (cierre/apertura semanal de FX/futuros tradicionales)
    """
    if now_utc is None:
        now_utc = datetime.now(UTC_TZ)
    weekday = now_utc.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    h = now_utc.hour + now_utc.minute / 60.0
    if weekday == 5:                 # sabado entero
        return True
    if weekday == 4 and h >= 22.0:   # viernes despues de 22:00 UTC
        return True
    if weekday == 6 and h < 22.0:    # domingo antes de 22:00 UTC
        return True
    return False

def weekend_status():
    """Devuelve dict descriptivo del estado weekend.

    v5.2: agrega near_close (viernes >=14:00 CDMX). No es veto, solo señal
    informativa que volume_quality.is_dead_window tambien marca.
    """
    now_utc = datetime.now(UTC_TZ)
    closed = is_weekend_closed(now_utc)
    now_cdmx = now_utc.astimezone(CDMX_TZ)
    h_cdmx = now_cdmx.hour + now_cdmx.minute / 60.0
    near_close = (now_utc.weekday() == 4 and h_cdmx >= 14.0)
    return {
        "closed":          closed,
        "weekday_utc":     now_utc.weekday(),
        "weekday_label":   ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][now_utc.weekday()],
        "hour_utc":        now_utc.hour + now_utc.minute/60.0,
        "near_close":      near_close,
        "reason":          "weekend veto activo" if closed else (
                              "viernes cerca de cierre" if near_close else "mercado activo"),
    }

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
