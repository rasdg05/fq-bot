# -*- coding: utf-8 -*-
"""
================================================================================
  FQ RADAR - logica PURA de filtrado del radar / lectura de campo
  by RasDG_Sol + Claude

  Primera tajada de la migracion del monolito fq_bot_v3_2.py hacia modulos
  cohesivos (ver ARCHITECTURE.md). Aqui vive SOLO logica pura y sin estado:

    - Config (override-able por env) de cooldowns, gate de conviccion y anti-flip.
    - _radar_cooldown_for(tf_id)        -> ventana de cooldown segun el TF.
    - _radar_has_conviction(plan, tf)   -> gate de conviccion ("sin edge, nada").
    - _radar_emit_decision(...)         -> emitir / saltar / flip de reemplazo.

  NO contiene I/O, ni estado mutable, ni dependencias del runtime del bot
  (telegram, exchange, ledger). Eso permite testearlo de forma aislada y
  reusarlo desde el loop del monolito sin acoplar. El feature flag RADAR_ENABLED
  y el estado mutable _RADAR_LAST_TF se quedan en el caller (loop del bot).
================================================================================
"""
import os

# ============================================================
# COOLDOWNS POR TF
# ============================================================
# Cooldown base (15m / RADAR original).
RADAR_COOLDOWN_SEC = int(os.environ.get("FQ_RADAR_COOLDOWN_MIN", "90")) * 60
# Cooldown para field-TFs cortos (1m/3m son mas frecuentes).
RADAR_COOLDOWN_FIELD_SEC = int(os.environ.get("FQ_RADAR_FIELD_COOLDOWN_MIN", "15")) * 60
# Cooldown dedicado del 5m (canal de campo afinado v5.3). 5m cierra cada 5 min;
# 30 min = ~6 velas evita senales encimadas sin matar la reactividad.
RADAR_COOLDOWN_5M_SEC = int(os.environ.get("FQ_RADAR_5M_COOLDOWN_MIN", "30")) * 60

# TFs de campo "rapidos" (intradia): comparten gate de conviccion fuerte y
# etiqueta [tf] en el header para no confundirse con el 15m.
_FIELD_FAST_TFS = ("1m", "3m", "5m")

# ============================================================
# ANTI-FLIP POR FUERZA RELATIVA
# ------------------------------------------------------------
# Dentro del cooldown del TF, un cambio de direccion (long<->short) solo se
# emite si el EV nuevo supera al previo por RATIO, cumple un EV minimo absoluto
# y un P(SL) maximo. Evita el caso LONG@01:56 -> SHORT@02:09 cuando el bias del
# TF corto oscila.
# ============================================================
RADAR_FLIP_EV_RATIO = float(os.environ.get("FQ_RADAR_FLIP_EV_RATIO", "1.3"))
RADAR_FLIP_EV_MIN   = float(os.environ.get("FQ_RADAR_FLIP_EV_MIN",   "1.0"))
RADAR_FLIP_MAX_PSL  = float(os.environ.get("FQ_RADAR_FLIP_MAX_PSL",  "0.45"))

# ============================================================
# GATE DE CONVICCION DEL RADAR / LECTURA DE CAMPO (FQ v5.3)
# ------------------------------------------------------------
# Peticion RasDG (jun-2026): "no me des lectura de campo sin una conviccion de
# senal, de ser asi mejor nada". Hasta v5.2 el RADAR emitia ante CUALQUIER
# veredicto operable (EJECUTAR/ACUMULAR) sin importar la fuerza del edge, lo
# que producia ruido tipo "Edge - probabilidad media". v5.3 exige edge claro
# ANTES de emitir nada:
#   - TFs de campo (5m y menores): EV >= 1.5 (Edge fuerte).
#   - 15m (RADAR original): piso de EV >= 1.2 para recortar lo marginal sin
#     romper lo que ya funcionaba.
#   - ACUMULAR: ev_cond y reach_prob deben superar los mismos pisos.
#
# v5.3 (peticion RasDG, jun-2026): la CONVICCION la define el EDGE (R:R
# fuerte), no la probabilidad. Se permite hasta "probabilidad media"
# (P(SL) <= 0.55, que es el limite del label "Media") para no matar señales
# utiles tipo "Edge fuerte · probabilidad media" como el SHORT $79.10. La
# utilidad la carga el R:R. Todo override-able por env para tuning fino.
# ============================================================
RADAR_MIN_EV_FIELD = float(os.environ.get("FQ_RADAR_FIELD_MIN_EV", "1.5"))
RADAR_MIN_EV_15M   = float(os.environ.get("FQ_RADAR_MIN_EV",       "1.2"))
RADAR_MAX_PSL      = float(os.environ.get("FQ_RADAR_MAX_PSL",      "0.55"))
RADAR_MIN_REACH    = float(os.environ.get("FQ_RADAR_MIN_REACH",    "0.35"))


def _radar_cooldown_for(tf_id):
    """Cooldown del RADAR segun el TF (5m tiene su propia ventana)."""
    if tf_id == "5m":
        return RADAR_COOLDOWN_5M_SEC
    if tf_id in ("1m", "3m"):
        return RADAR_COOLDOWN_FIELD_SEC
    return RADAR_COOLDOWN_SEC


def _radar_has_conviction(plan, tf_id):
    """Gate de conviccion: sin edge claro, NO se emite RADAR/lectura de campo.

    Returns ``(ok, reason)``. ``ok=False`` -> "mejor nada" que ruido de baja
    conviccion. Los TFs de campo (5m y menores) exigen Edge fuerte; el 15m
    mantiene un piso mas suave para preservar el RADAR original.
    """
    min_ev = RADAR_MIN_EV_FIELD if tf_id in _FIELD_FAST_TFS else RADAR_MIN_EV_15M
    v = plan.get("verdict")
    if v == "EJECUTAR_AHORA":
        mkt = plan.get("market") or {}
        ev  = float(mkt.get("ev")   or 0.0)
        psl = float(mkt.get("p_sl") or 1.0)
        if ev < min_ev:
            return False, "ev={:.2f}<{:.2f}".format(ev, min_ev)
        if psl > RADAR_MAX_PSL:
            return False, "p_sl={:.2f}>{:.2f}".format(psl, RADAR_MAX_PSL)
        return True, "edge OK (ev={:.2f}, p_sl={:.2f})".format(ev, psl)
    if v == "ACUMULAR_EN_ZONA":
        z     = plan.get("primary_zone") or {}
        ev    = float(z.get("ev_cond")    or 0.0)
        reach = float(z.get("reach_prob") or 0.0)
        if ev < min_ev:
            return False, "zone.ev_cond={:.2f}<{:.2f}".format(ev, min_ev)
        if reach < RADAR_MIN_REACH:
            return False, "zone.reach={:.2f}<{:.2f}".format(reach, RADAR_MIN_REACH)
        return True, "zone edge OK (ev={:.2f}, reach={:.2f})".format(ev, reach)
    return False, "verdict not eligible"


def _radar_emit_decision(last_radar, now_s, direction, new_ev, new_psl,
                          cooldown_sec,
                          flip_ev_ratio=None, flip_ev_min=None, flip_max_psl=None):
    """Decide si el RADAR debe emitir o saltarse dado el estado previo del TF.

    Returns ``(action, flip_replace)``:
      - ``("emit", False)``: emite normal (fuera de cooldown o sin previo).
      - ``("emit", True)``:  emite como FLIP de reemplazo (direccion opuesta
        dentro del cooldown pero con edge claramente mayor).
      - ``("skip", False)``: NO emite (misma direccion en cooldown, o flip
        sin fuerza suficiente).

    Argumentos:
      last_radar:   ultimo estado del TF (dict con ts/direction/ev/p_sl) o None/{}
      now_s:        timestamp actual (segundos epoch)
      direction:    "long" o "short" del setup candidato
      new_ev, new_psl: EV (en R) y P(SL) del setup candidato
      cooldown_sec: ventana de cooldown del TF
      flip_*: umbrales para aceptar un flip (default = constantes del modulo)
    """
    ratio   = RADAR_FLIP_EV_RATIO if flip_ev_ratio is None else flip_ev_ratio
    min_ev  = RADAR_FLIP_EV_MIN   if flip_ev_min   is None else flip_ev_min
    max_psl = RADAR_FLIP_MAX_PSL  if flip_max_psl  is None else flip_max_psl
    last_radar = last_radar or {}
    elapsed_s = now_s - (last_radar.get("ts") or 0)
    within_cd = bool(last_radar.get("ts")) and elapsed_s < cooldown_sec
    if not within_cd:
        return ("emit", False)
    if last_radar.get("direction") == direction:
        return ("skip", False)
    prev_ev = float(last_radar.get("ev") or 0.0)
    strong_enough = (
        new_ev >= prev_ev * ratio
        and new_ev >= min_ev
        and new_psl <= max_psl
    )
    return ("emit", True) if strong_enough else ("skip", False)
