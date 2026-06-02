# -*- coding: utf-8 -*-
"""
================================================================================
  PUBLIC SCHEDULER - cron interno del bot publico
  by RasDG_Sol + Claude

  Coordina:
   - Anuncios de cierres +1R (poll cada CLOSURE_POLL_MIN minutos)
   - Lecturas del dia (2 slots fijos por dia CDMX)
   - CTAs rotativos (2 slots por dia)
   - Stats semanales (domingos 18:00 CDMX)

  No envia mensajes directamente - llama callbacks que el caller registra.
================================================================================
"""
import time
import logging
import threading
from datetime import datetime, timezone, timedelta

import public_format as fmt
import public_outcome_announcer as poa
import public_content_generator as pcg

log = logging.getLogger("fq_public_sched")

CDMX_TZ = timezone(timedelta(hours=-6))

# ============================================================
# CONFIG DE SLOTS (hora CDMX)
# ============================================================
SLOTS_LECTURA = [
    (8, 30),    # antes de NY open
    (15, 0),    # cierre NY
]

SLOTS_CTA = [
    (11, 0),
    (14, 0),    # mid-day NY
    (18, 0),    # tarde
    (20, 0),
]

SLOTS_MANTRA = [
    (6, 0),     # amanecer CDMX / apertura Asia
    (22, 30),   # cierre NY / night cap
]

# Domingo 18:00 CDMX (weekday 6 en datetime: lun=0, dom=6)
SLOT_STATS_SEMANAL = (6, 18, 0)  # (weekday, hour, minute)

CLOSURE_POLL_MIN = 8        # poll cierres cada 8 min
NEW_SIG_POLL_MIN = 2        # poll senales nuevas cada 2 min (FOMO inmediato)
TP3_POLL_MIN     = 3        # poll celebraciones TP3 cada 3 min (animo fresco)
SLOT_TOLERANCE_MIN = 6      # disparar slot dentro de +-6 min de la hora exacta

# ============================================================
# ESTADO INTERNO - evita dobles disparos en el mismo slot
# ============================================================
class SchedulerState:
    def __init__(self):
        self.last_lectura_slot_key   = None     # "YYYY-MM-DD-08:30"
        self.last_cta_slot_key       = None
        self.last_mantra_slot_key    = None
        self.last_weekly_stats_key   = None     # "YYYY-WW"
        self.last_closure_check_ts   = None
        self.last_new_sig_check_ts   = None
        self.last_tp3_check_ts       = None
        self.cta_rotation_idx        = 0
        self.lock                    = threading.Lock()

# ============================================================
# HELPERS DE TIEMPO
# ============================================================
def _cdmx_now():
    return datetime.now(CDMX_TZ)

def _slot_key(slot_h, slot_m, dt=None):
    if dt is None:
        dt = _cdmx_now()
    return "{}-{:02d}:{:02d}".format(dt.strftime("%Y-%m-%d"), slot_h, slot_m)

def _is_within_slot(now_dt, slot_h, slot_m, tolerance_min=SLOT_TOLERANCE_MIN):
    target = now_dt.replace(hour=slot_h, minute=slot_m, second=0, microsecond=0)
    diff_min = abs((now_dt - target).total_seconds() / 60.0)
    return diff_min <= tolerance_min

# ============================================================
# CORE TICK - llamado cada N segundos por el main loop
# ============================================================
def scheduler_tick(state, send_callback):
    """
    Revisa todos los slots y dispara los que toquen.

    send_callback(text, kind, title) -> int (numero de chats que recibieron)
    """
    try:
        _check_closures(state, send_callback)
        _check_new_signals(state, send_callback)
        _check_tp3_celebrations(state, send_callback)
        _check_lecturas(state, send_callback)
        _check_ctas(state, send_callback)
        _check_mantras(state, send_callback)
        _check_weekly_stats(state, send_callback)
    except Exception as e:
        log.error("scheduler_tick: {}".format(e))

# ============================================================
# 1. CIERRES +1R
# ============================================================
def _check_closures(state, send_callback):
    now = datetime.now(timezone.utc)
    if state.last_closure_check_ts and (now - state.last_closure_check_ts).total_seconds() < CLOSURE_POLL_MIN * 60:
        return
    state.last_closure_check_ts = now

    closures = poa.get_new_closures_to_announce()
    if not closures:
        return
    log.info("Closures to announce: {}".format(len(closures)))
    stats_7d = poa.compute_short_stats_7d()
    for c in closures:
        try:
            msg = fmt.build_closure_announcement(c, stats_7d)
            sent = send_callback(msg, kind="closure",
                                  title="#{} {}".format(c["id"], c["outcome"]))
            poa.mark_announced(c["id"], outcome=c.get("outcome"),
                               pnl_r=c.get("pnl_r"))
            log.info("Closure #{} anunciado a {} chats".format(c["id"], sent or 0))
        except Exception as e:
            log.error("closure announce error #{}: {}".format(c.get("id"), e))

# ============================================================
# 1B. TEASERS DE SENAL NUEVA (sin niveles)
# ============================================================
def _check_new_signals(state, send_callback):
    now = datetime.now(timezone.utc)
    if state.last_new_sig_check_ts and (now - state.last_new_sig_check_ts).total_seconds() < NEW_SIG_POLL_MIN * 60:
        return
    state.last_new_sig_check_ts = now

    new_sigs = poa.get_new_signals_to_announce()
    if not new_sigs:
        return
    log.info("New signals to tease: {}".format(len(new_sigs)))
    for s in new_sigs:
        try:
            msg = fmt.build_new_signal_teaser(s)
            label = fmt.conviction_label(float(s.get("p_master_final") or 0))
            sent = send_callback(msg, kind="new_signal",
                                  title="#{} {} {}".format(s["id"], s.get("direction","?"), label))
            poa.mark_new_announced(s["id"], direction=s.get("direction"), tier=label)
            log.info("Teaser senal nueva #{} enviado a {} chats".format(s["id"], sent or 0))
        except Exception as e:
            log.error("new signal teaser error #{}: {}".format(s.get("id"), e))

# ============================================================
# 1C. CELEBRACIONES DE TP3 (animo para los usuarios)
# ============================================================
def _check_tp3_celebrations(state, send_callback):
    now = datetime.now(timezone.utc)
    if state.last_tp3_check_ts and (now - state.last_tp3_check_ts).total_seconds() < TP3_POLL_MIN * 60:
        return
    state.last_tp3_check_ts = now

    tp3s = poa.get_new_tp3_to_announce()
    if not tp3s:
        return
    log.info("TP3 celebrations to announce: {}".format(len(tp3s)))
    for t in tp3s:
        try:
            msg = fmt.build_tp3_celebration(t)
            sent = send_callback(msg, kind="tp3",
                                  title="#{} {}".format(t["id"], t.get("direction", "?")))
            poa.mark_tp3_announced(t["id"], direction=t.get("direction"),
                                   hit_price=t.get("hit_price"))
            log.info("TP3 #{} celebrado a {} chats".format(t["id"], sent or 0))
        except Exception as e:
            log.error("tp3 celebration error #{}: {}".format(t.get("id"), e))

# ============================================================
# 2. LECTURAS DEL DIA (Sonnet 1-2 al dia)
# ============================================================
def _check_lecturas(state, send_callback):
    now = _cdmx_now()
    for slot_h, slot_m in SLOTS_LECTURA:
        if not _is_within_slot(now, slot_h, slot_m):
            continue
        key = _slot_key(slot_h, slot_m, now)
        with state.lock:
            if state.last_lectura_slot_key == key:
                return
            state.last_lectura_slot_key = key
        log.info("Slot lectura activado: {}".format(key))

        titulo, cuerpo = pcg.generate_lectura()
        if not titulo or not cuerpo:
            log.warning("Generacion de lectura fallo - skipping slot")
            return
        msg = fmt.wrap_lectura(titulo, cuerpo)
        sent = send_callback(msg, kind="lectura", title=titulo)
        log.info("Lectura '{}' enviada a {} chats".format(titulo, sent or 0))
        return  # solo un slot por tick

# ============================================================
# 3. CTAs ROTATIVOS (templates estaticos, no quema LLM)
# ============================================================
def _check_ctas(state, send_callback):
    now = _cdmx_now()
    for slot_h, slot_m in SLOTS_CTA:
        if not _is_within_slot(now, slot_h, slot_m):
            continue
        key = _slot_key(slot_h, slot_m, now)
        with state.lock:
            if state.last_cta_slot_key == key:
                return
            state.last_cta_slot_key = key
            idx = state.cta_rotation_idx
            state.cta_rotation_idx += 1
        log.info("Slot CTA activado: {} idx={}".format(key, idx))

        msg = fmt.build_cta(idx)
        sent = send_callback(msg, kind="cta", title="rot_{}".format(idx))
        log.info("CTA #{} enviado a {} chats".format(idx, sent or 0))
        return

# ============================================================
# 3B. MANTRAS MISTRAL QUANTUM (texto plano, sin LLM, deterministico)
# ============================================================
def _check_mantras(state, send_callback):
    now = _cdmx_now()
    for slot_h, slot_m in SLOTS_MANTRA:
        if not _is_within_slot(now, slot_h, slot_m):
            continue
        key = _slot_key(slot_h, slot_m, now)
        with state.lock:
            if state.last_mantra_slot_key == key:
                return
            state.last_mantra_slot_key = key
        idx = fmt.pick_mantra_idx_for_today(slot_h=slot_h)
        log.info("Slot mantra activado: {} idx={}".format(key, idx))

        msg = fmt.build_mantra(idx)
        sent = send_callback(msg, kind="mantra", title="m_{}".format(idx))
        log.info("Mantra #{} enviado a {} chats".format(idx, sent or 0))
        return

# ============================================================
# 4. STATS SEMANALES (domingos 18:00 CDMX)
# ============================================================
def _check_weekly_stats(state, send_callback):
    now = _cdmx_now()
    weekday, slot_h, slot_m = SLOT_STATS_SEMANAL
    if now.weekday() != weekday:
        return
    if not _is_within_slot(now, slot_h, slot_m):
        return
    week_key = "{}-W{:02d}".format(now.year, now.isocalendar()[1])
    with state.lock:
        if state.last_weekly_stats_key == week_key:
            return
        state.last_weekly_stats_key = week_key
    log.info("Slot stats semanal activado: {}".format(week_key))

    stats = poa.compute_weekly_stats()
    if not stats:
        log.info("Sin data para stats semanales - skipping")
        return
    msg = fmt.build_weekly_stats(stats)
    sent = send_callback(msg, kind="stats", title="weekly_{}".format(week_key))
    log.info("Stats semanales enviadas a {} chats".format(sent or 0))

# ============================================================
# THREAD WRAPPER
# ============================================================
def run_scheduler_loop(state, send_callback, tick_seconds=60, stop_event=None):
    """Loop principal del scheduler. Bloqueante - corre en su propio thread."""
    log.info("Scheduler iniciado (tick cada {}s)".format(tick_seconds))
    while True:
        if stop_event is not None and stop_event.is_set():
            log.info("Scheduler stop event recibido")
            break
        try:
            scheduler_tick(state, send_callback)
        except Exception as e:
            log.error("scheduler loop error: {}".format(e))
        time.sleep(tick_seconds)
