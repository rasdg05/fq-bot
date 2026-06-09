# -*- coding: utf-8 -*-
"""
================================================================================
  FQ v5.1 SIGNAL BOT - "MISTRAL EMERGENT TIME EDITION"
  Fibonacci Cuantico v5.1 - QTE + Postulado tau(t) Tiempo Emergente
  by RasDG_Sol + Claude
================================================================================

  CHANGELOG v5.1 (Mistral Emergent Time):
    - Modulo quantum_timelines.py: Monte Carlo de 500 paths futuros
      bajo restricciones estructurales reales (ICT/SMC)
    - SL/TP anclado a estructura ICT (OB, pools, swing, FVG) anti-stop-hunt
    - Output en probabilidades reales: P(TP_i), P(SL), EV en R, coherencia
    - QAOA-inspired optimizer sobre niveles candidatos (constraints P(SL)<=35%)
    - Routing tier-aware /analisis: admin detallado, VIP curado Mistral
    - Comando /timelines (admin): 2000 paths, ASCII histograms, drawdown dist
    - Claude follow-up VIP breve (4 bullets, 320 tokens) con probabilidades QTE

  CHANGELOG v3.2 (Evolution Patch):
    - Modulo entropy_cognition.py: ledger SQLite + outcome tracker
    - Modulador kappa_evo (+-15% sobre P_master, NO sobre Theta(D))
    - Self-audit Opus cada 25 senales cerradas
    - Backup automatico de ledger a Telegram cada 10 senales
    - Comandos nuevos: /metrics /entropy /ledger /evolve /audit
    - Outcome tracker: monitorea cada senal hasta TP/SL/timeout (8h)

  CHANGELOG v3.1:
    - Integracion Claude (Anthropic API) como co-pilot tactico
      * /claude   - lectura tactica manual (Sonnet 4.5)
      * /analisis - ahora incluye lectura Claude (Sonnet 4.5)
      * /pspace   - ahora incluye lectura Claude (Sonnet 4.5)
      * /niveles  - ahora incluye afinacion Claude (Sonnet 4.5)
      * Senales P_master >= phi^3 - co-pilot Opus 4.6 auto-disparado
    - Market context module:
      * Funding rate, Open Interest, Long/Short ratio (OKX)
      * Order book walls + presion de libro
      * Detector de eventos: CHoCH, breakouts, divergencias RSI, volumen
      * Patrones de vela: hammer, shooting star, engulfing
      * Evolucion vela-a-vela ultimas 5 velas
    - Snapshots inteligentes especializados por comando

  CHANGELOG v3.0:
    - Ventana operativa 24H (W_clock solo modula, no bloquea)
    - /niveles con planes de entrada contextuales
    - /pspace con doble lectura: ejecutiva + tecnica
    - /sesion completamente reescrito con W_clock dinamico
    - Interfaz pulida con glyphs profesionales

  ASCII-only source, zero encoding issues.
================================================================================
"""
import os
import sys
import re
import time
import logging
import threading
import traceback
from datetime import datetime, timezone, timedelta
import ccxt
import pandas as pd
import requests

# Modulos FQ v3.1
import claude_integration as claude_ai
import market_context as mctx

# Modulos FQ v3.2 (Evolution Patch)
import entropy_cognition as ev
import claude_evolution as ev_claude
import legal
from ops import heartbeat

# Progress tracker (v5.1) - alertas intermedias en senal activa (TP1/TP2/TP3)
try:
    import signal_progress_tracker as spt
    PROGRESS_TRACKER_AVAILABLE = True
except ImportError:
    PROGRESS_TRACKER_AVAILABLE = False
    spt = None

# Tactical tracker (v5.4) - mismo progress (SL a BE en TP1, etc.) pero para las
# ALERTAS TACTICAS del VIP, que NO viven en el ledger.
try:
    import tactical_tracker
    TACTICAL_TRACKER_AVAILABLE = True
except ImportError:
    TACTICAL_TRACKER_AVAILABLE = False
    tactical_tracker = None

# Modulos FQ v4.1.1 (ICT/SMC Refactor) - cargan solo si flag ON
try:
    import ict_smc
    import killzones_pd
    import fusion_engine
    import field_reports
    ICT_MODULES_AVAILABLE = True
except ImportError as _e:
    ICT_MODULES_AVAILABLE = False
    ict_smc = killzones_pd = fusion_engine = field_reports = None

# Modulos FQ v4.2+ (Mistral curated VIP format - v5.0 Quantum)
try:
    import vip_format
    VIP_FORMAT_AVAILABLE = True
except ImportError:
    VIP_FORMAT_AVAILABLE = False
    vip_format = None

# Modulos FQ v5.0 (Quantum Timelines Engine)
try:
    import quantum_timelines as qt
    QTE_AVAILABLE = True
except ImportError:
    QTE_AVAILABLE = False
    qt = None

# Modulo FQ v5.x (Battle Planner - veredicto certero + zonas de acumulacion)
try:
    import battle_planner
    BATTLE_PLANNER_AVAILABLE = True
except ImportError:
    BATTLE_PLANNER_AVAILABLE = False
    battle_planner = None

# Modulos FQ v5.1 (Postulado tau(t) - Phase E)
try:
    import emergent_time
    EMERGENT_TIME_MODULE_AVAILABLE = True
except ImportError:
    EMERGENT_TIME_MODULE_AVAILABLE = False
    emergent_time = None

# Modulo FQ v5.2 (Volume Quality - modulador + veto en horas muertas)
try:
    import volume_quality
    VOLUME_QUALITY_AVAILABLE = True
except ImportError:
    VOLUME_QUALITY_AVAILABLE = False
    volume_quality = None

# Modulos FQ v4.0 (Mistral - VIP System)
try:
    import vip_system as vip
    import payments as pay
    VIP_ENABLED = True
except ImportError:
    VIP_ENABLED = False
    vip = None
    pay = None

# ============================================================
# CONFIG
# ============================================================
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

SYMBOL      = "SOL-USDT-SWAP"
SYMBOL_BTC  = "BTC-USDT-SWAP"
SYMBOL_ETH  = "ETH-USDT-SWAP"

LOOP_SECONDS = 60

# 24H operativo - W_clock solo modula
WINDOW_24H = True

# FQ v4.1 thresholds (calibrado 2026-05-07 v3.0)
MACRO_THRESHOLD_PCT = 0.0005    # MISTRAL: 0.05% (era 0.08%), ventana deslizante
TECH_MIN_ALIGNED    = 5         # de 7 indicadores
PSPACE_MIN_MASSES   = 2
RR_MIN_TP_DIVINO    = 1.8

# ============================================================
# MULTI-TIMEFRAME PROFILES (mayo 2026 - bajo volumen, multi-TF)
# ============================================================
# Cada TF emite en su propio ciclo con label, cooldown e intra-vela propios.
# Cooldowns independientes por TF: una senal 5m NO bloquea 15m ni 1h.
# 15m queda como anchor con valores identicos al regimen pre-refactor.
TF_PROFILES = {
    "5m": {
        "label":                  "INTRADIA",
        "INTRA_CANDLE_MINUTES":   2,
        "SIGNAL_COOLDOWN_MINUTES": 20,
        "PULLBACK_VOL_MULT":      1.5,
        "BREAKOUT_VOL_MULT":      1.7,
        "PMASTER_MIN":            1.95,
        "context_mid":            "15m",
        "context_high":           "1h",
        "sub_tf":                 "1m",
        # FQ v5.1 Phase E - calibrado para scalping intradia
        "PHASE_E_N_PATHS":        200,    # menos paths: el 5m evalua mas seguido
        "PHASE_E_COOLDOWN_MIN":   20,     # = SIGNAL_COOLDOWN_MINUTES del 5m
    },
    "15m": {
        "label":                  "SCALPING",
        "INTRA_CANDLE_MINUTES":   7,     # anchor: identico a pre-refactor
        "SIGNAL_COOLDOWN_MINUTES": 60,    # anchor: 1h
        "PULLBACK_VOL_MULT":      1.3,
        "BREAKOUT_VOL_MULT":      1.5,
        "PMASTER_MIN":            1.80,   # anchor: calibrado 2026-05-10
        "context_mid":            "1h",
        "context_high":           "4h",
        "sub_tf":                 "1m",
        "PHASE_E_N_PATHS":        300,    # baseline del postulado
        "PHASE_E_COOLDOWN_MIN":   60,
    },
    "1h": {
        "label":                  "SWING",
        "INTRA_CANDLE_MINUTES":   25,
        "SIGNAL_COOLDOWN_MINUTES": 180,
        "PULLBACK_VOL_MULT":      1.2,
        "BREAKOUT_VOL_MULT":      1.4,
        "PMASTER_MIN":            1.70,
        "context_mid":            "4h",
        "context_high":           "1d",
        "sub_tf":                 "5m",
        "PHASE_E_N_PATHS":        500,    # corre poco, mas paths para mejor precision
        "PHASE_E_COOLDOWN_MIN":   180,
    },
}

# Orden de evaluacion en el main loop (secuencial).
# Default: 5m+15m (intradia/scalping). 1h SWING opt-in via FQ_INCLUDE_1H=1.
# Override completo con FQ_TIMEFRAMES="5m,15m" (CSV).
#
# FQ v5.2: la operativa intradia 1m/3m NO se canaliza via el motor clasico
# (preserva 5m/15m/1h calibrados). Se sirve desde la via "field signal"
# (radar/battle_planner) en FIELD_TIMEFRAMES (mas abajo), con TPs cortos y
# promocion a VIP cuando volumen + edge cumplen.
def _resolve_timeframes():
    raw = os.environ.get("FQ_TIMEFRAMES", "").strip()
    if raw:
        tfs = tuple(t.strip() for t in raw.split(",") if t.strip() in TF_PROFILES)
        if tfs:
            return tfs
    tfs = ["5m", "15m"]
    if os.environ.get("FQ_INCLUDE_1H", "").strip() in ("1", "true", "yes"):
        tfs.append("1h")
    return tuple(tfs)


# ============================================================
# FIELD SIGNAL TIMEFRAMES (FQ v5.2 -> v5.3)
# Canal independiente: radar/battle_planner corre sobre estas velas y
# promueve al VIP como ALERTA TACTICA. NO toca el gate clasico.
#  - 15m: ya existia (RADAR original). Sigue ahi.
#  - 5m:  canal de campo afinado (v5.3). Reemplaza al 3m como TF intradia
#         por defecto: menos ruido, setups con mas cuerpo.
#  - 3m:  RETIRADO del default (v5.3). Abrir el edge a 3m generaba demasiados
#         falsos positivos y senales encimadas que sangraban la cuenta. Sigue
#         disponible solo via override explicito FQ_FIELD_TIMEFRAMES para
#         experimentar, nunca por defecto.
#  - 1m:  opt-in via FQ_FIELD_INCLUDE_1M=1 (mas agresivo, mas ruido).
# Override CSV: FQ_FIELD_TIMEFRAMES="5m,15m"
# ============================================================
_VALID_FIELD_TFS = ("1m", "3m", "5m", "15m", "1h")
def _resolve_field_timeframes():
    raw = os.environ.get("FQ_FIELD_TIMEFRAMES", "").strip()
    if raw:
        tfs = tuple(t.strip() for t in raw.split(",") if t.strip() in _VALID_FIELD_TFS)
        if tfs:
            return tfs
    # v5.3: default = 5m afinado + 15m original. 3m ya NO entra por defecto.
    tfs = ["5m", "15m"]
    if os.environ.get("FQ_FIELD_INCLUDE_1M", "").strip() in ("1", "true", "yes"):
        tfs.insert(0, "1m")
    return tuple(tfs)

FIELD_TIMEFRAMES = _resolve_field_timeframes()

TIMEFRAMES = _resolve_timeframes()

# Aliases legacy: comandos manuales y paths admin siguen usando 15m por default.
TIMEFRAME             = "15m"
INTRA_CANDLE_MINUTES  = TF_PROFILES["15m"]["INTRA_CANDLE_MINUTES"]
SIGNAL_COOLDOWN_HOURS = TF_PROFILES["15m"]["SIGNAL_COOLDOWN_MINUTES"] / 60.0
PMASTER_MIN           = TF_PROFILES["15m"]["PMASTER_MIN"]

# Gate QTE (Quantum Timelines Engine) - si una senal pasa P_master pero el
# QTE da P(SL) alto o EV bajo, se rechaza para no quemar suscriptores.
QTE_GATE_ENABLED = os.environ.get("FQ_QTE_GATE_ENABLED", "1").strip() in ("1","true","yes")
QTE_GATE_MAX_P_SL = float(os.environ.get("FQ_QTE_MAX_P_SL", "0.40"))
QTE_GATE_MIN_EV   = float(os.environ.get("FQ_QTE_MIN_EV", "1.20"))

# Cooldown VIP para /analisis - evita gasto de API y quema a proposito.
# Admin bypasea (es RasDG). Free no llega aqui (PREMIUM_COMMANDS gate).
# Set FQ_VIP_ANALISIS_COOLDOWN_MIN=0 para desactivar.
VIP_ANALISIS_COOLDOWN_SEC = int(os.environ.get("FQ_VIP_ANALISIS_COOLDOWN_MIN", "30")) * 60
_VIP_ANALISIS_LAST = {}  # chat_id (str) -> epoch seconds del ultimo /analisis

# RADAR proactivo (FQ v5.x): en vela nueva, si el battle planner ve un setup
# operable (EJECUTAR/ACUMULAR) avisa al admin entre senales. NO afloja el gate
# automatico - es inteligencia anticipada. Admin-only por defecto (blast radius).
# Set FQ_RADAR_ENABLED=0 para desactivar; FQ_RADAR_COOLDOWN_MIN controla el spam.
#
# v6 (peticion RasDG, jun-2026): DEFAULT OFF. Se matan las senales TACTICAS para
# conservar SOLO senales VIP de pura lectura en cadencia (oro). Lo unico que
# cuelga del radar es la promocion a ALERTA TACTICA del VIP; el path VIP clasico
# (_evaluate_setup_v411 -> fusion_engine) es independiente y sigue intacto.
# Reversible: FQ_RADAR_ENABLED=1 reactiva el radar/tacticas.
RADAR_ENABLED      = os.environ.get("FQ_RADAR_ENABLED", "0").strip() in ("1", "true", "yes")
# v5.4 (peticion RasDG, jun-2026): el RADAR sigue CORRIENDO (de el cuelga la
# promocion a ALERTA TACTICA del VIP), pero su lectura admin-only entre senales
# -la "inteligencia anticipada"- se APAGA por defecto: era ruido que solo hacia
# perder dinero. Solo interesan las alertas tacticas. El comando manual /campo
# sigue vivo bajo demanda. Override: FQ_RADAR_ADMIN_READOUT=1 para reactivarla.
RADAR_ADMIN_READOUT_ENABLED = os.environ.get(
    "FQ_RADAR_ADMIN_READOUT", "0").strip() in ("1", "true", "yes")
# v5.2: cooldown por-TF (1m/3m/15m corren independientes)
_RADAR_LAST_TF = {}  # tf_id -> {"ts","verdict","direction","ev","p_sl"}

# v5.3: la logica PURA del radar (cooldowns por TF, gate de conviccion y
# anti-flip por fuerza relativa) vive en fq_radar.py - primera tajada de la
# migracion del monolito (ver ARCHITECTURE.md). Aqui solo quedan el feature
# flag y el estado mutable del loop. Reexportamos los simbolos para no romper
# referencias/tests que aun apuntan a fq_bot_v3_2.*
import fq_radar
from fq_radar import (
    RADAR_COOLDOWN_SEC, RADAR_COOLDOWN_FIELD_SEC, RADAR_COOLDOWN_5M_SEC,
    RADAR_FLIP_EV_RATIO, RADAR_FLIP_EV_MIN, RADAR_FLIP_MAX_PSL,
    RADAR_MIN_EV_FIELD, RADAR_MIN_EV_15M, RADAR_MAX_PSL, RADAR_MIN_REACH,
    _FIELD_FAST_TFS,
    _radar_cooldown_for, _radar_has_conviction, _radar_emit_decision,
)

# ALERTA TACTICA al VIP (FQ v5.2 -> ACTIVADA por defecto en v5.3): cuando el
# RADAR encuentra un setup operable + convicción (gate fq_radar) + volumen real
# >= 0.85 + no franja muerta + edge robusto, se difunde al VIP/trial como ALERTA
# TACTICA FQ con TPs INTELIGENTES. En caso contrario se mantiene el envío
# admin-only del RADAR legacy.
#
# v5.3 (peticion RasDG, jun-2026): con el canal 5m afinado y el gate de
# convicción en su sitio, se activa por defecto para que las señales lleguen al
# VIP. Se puede desactivar con FQ_TACTICAL_VIP_ENABLED=0.
TACTICAL_VIP_ENABLED = os.environ.get("FQ_TACTICAL_VIP_ENABLED", "1").strip() in ("1", "true", "yes")
# Bar de promocion a VIP: la CONVICCION la define el edge (ya filtrado por el
# gate de convicción del radar). Para la probabilidad se permite hasta "media"
# (P(SL) <= 0.55), alineado con RADAR_MAX_PSL, para no excluir señales utiles
# tipo "Edge fuerte · probabilidad media". Override: FQ_TACTICAL_MAX_PSL.
TACTICAL_PROMOTE_MAX_PSL = float(os.environ.get("FQ_TACTICAL_MAX_PSL", "0.55"))
TACTICAL_PROMOTE_MIN_EV  = float(os.environ.get("FQ_TACTICAL_MIN_EV",  "0.70"))
# Gate de volumen POR TIPO de senal (v5.3, peticion RasDG, jun-2026):
#  - EJECUTAR_AHORA (entrada a mercado YA): exige confirmacion de volumen /
#    momentum en la vela del setup.
#  - ACUMULAR_EN_ZONA (limite esperando regreso a la zona/FVG): la vela del
#    setup es un pullback de bajo volumen POR NATURALEZA; exigirle momentum
#    medía lo que no importa y descartaba buenas señales (sobre todo en verano
#    / horas de menor liquidez). Basta un piso que descarte tape muerto; la
#    calidad la dan reach_prob + ev_cond + no-franja-muerta.
TACTICAL_VOL_MIN_EXECUTE  = float(os.environ.get("FQ_TACTICAL_VOL_MIN",      "0.85"))
TACTICAL_VOL_MIN_ACUMULA  = float(os.environ.get("FQ_TACTICAL_VOL_MIN_ACUM", "0.60"))

# Seguimiento EN VIVO de las ALERTAS TACTICAS (v5.4: SL a BE en TP1, parcial en
# TP2, trailing en TP3). Peticion RasDG (jun-2026): DESACTIVADO por defecto - el
# goteo de mensajes de seguimiento de las tacticas era ruido. La ALERTA TACTICA
# de ENTRADA se sigue enviando, y el progreso de las senales del LEDGER no se
# toca. Override: FQ_TACTICAL_TRACKING_ENABLED=1 para reactivar el seguimiento.
TACTICAL_TRACKING_ENABLED = os.environ.get(
    "FQ_TACTICAL_TRACKING_ENABLED", "0").strip() in ("1", "true", "yes")

# ============================================================
# FEATURE FLAGS v4.1.1 - ICT/SMC Refactor
# ============================================================
# Auto-enable cuando los modulos ICT/SMC cargan; permite override explicito.
_ict_default = "1" if ICT_MODULES_AVAILABLE else "0"
ENABLE_ICT_LAYER     = os.environ.get("FQ_ENABLE_ICT", _ict_default) == "1"
# Reportes de campo automaticos desactivados: con 3 TFs emitiendo, los reportes
# "no hubo senal" se vuelven ruido. El comando /campo sigue disponible bajo demanda.
ENABLE_FIELD_REPORTS = False
WEEKEND_VETO_LEGACY  = os.environ.get("FQ_WEEKEND_VETO", "1") == "1"
# WEEKEND_ADMIN_ONLY: cuando ON, el veto de fin de semana se "apaga" SOLO para
# el admin: el motor sigue generando senales en finde (no se corta la evaluacion)
# pero broadcast_to_subscribers las entrega UNICAMENTE al admin. VIP/trial/free
# siguen sin recibir nada hasta la reapertura (domingo 22:00 UTC).
WEEKEND_ADMIN_ONLY   = os.environ.get("FQ_WEEKEND_ADMIN_ONLY", "1") == "1"
# Cuando ENABLE_ICT_LAYER=1, evaluate_setup delega a fusion_engine.evaluate_signal

# FQ constants
PHI       = 1.6180339887
PHI_SQ    = PHI * PHI
PHI_CB    = PHI ** 3
PHI_INV   = 1.0 / PHI
ALPHA_FS  = 1.0 / 137.507        # constante estructura fina
B_CONST   = PHI_SQ / ALPHA_FS + 2.71828 + 3.14159  # = 364.6247

SESSION_WEIGHTS = {
    "asia":    0.50,
    "london":  0.80,
    "ny":      1.00,
    "overlap": 1.20,
}

# Glyphs UI - jerarquia profesional.
# Separadores, bullets y flechas beben del design line canonico (branding) para
# que TODA superficie del bot comparta la misma linea visual. Los markers de
# estado [OK]/[--]/[!] se mantienen por legibilidad en lecturas tecnicas admin.
import branding as _brand
G = {
    "ok":    "[OK]",
    "fail":  "[--]",
    "warn":  "[!]",
    "long":  _brand.GLYPHS["long"],
    "short": _brand.GLYPHS["short"],
    "phi":   "phi",
    "div":   "*",
    "bullet": _brand.GLYPHS["bullet_act"],
    "arrow": "->",
    "fence": _brand.RULE,
    "thin":  "─" * 30,
}

# ============================================================
# GLOBAL STATE
# ============================================================
def _tf_dict(default=None):
    """Helper: dict por TF inicializado con valor default (factory si callable)."""
    return {tf: (default() if callable(default) else default) for tf in TIMEFRAMES}

class BotState:
    def __init__(self):
        self.start_time           = datetime.now(timezone.utc)
        # ---- Singular (backward compat con comandos admin /status, /audit, heartbeat) ----
        # Refleja la senal/eval mas reciente entre todos los TFs.
        self.last_signal_ts       = None
        self.last_signal_dir      = None
        self.last_signal_price    = 0.0
        self.last_signal_levels   = None
        self.last_score_result    = None
        self.last_regime          = None
        self.last_eval_ts         = None
        self.last_eval_result     = "Esperando primera vela"
        self.last_eval_diagnostic = {}
        # ---- Per-TF (multi-TF emission v4.4) ----
        # Cada TF mantiene su propio cooldown y diagnostico de eval independiente.
        self.last_signal_ts_tf       = _tf_dict(None)
        self.last_signal_dir_tf      = _tf_dict(None)
        self.last_signal_price_tf    = _tf_dict(0.0)
        self.last_signal_levels_tf   = _tf_dict(None)
        self.last_score_result_tf    = _tf_dict(None)
        self.last_regime_tf          = _tf_dict(None)
        self.last_eval_ts_tf         = _tf_dict(None)
        self.last_eval_result_tf     = _tf_dict("Esperando primera vela")
        self.last_eval_diagnostic_tf = _tf_dict(dict)
        # ---- Globales cross-TF ----
        self.signals_today        = 0
        self.signals_total        = 0
        self.last_btc_chg         = 0.0
        self.last_eth_chg         = 0.0
        self.last_sol_price       = 0.0
        self.telegram_offset      = 0
        self.day_marker           = None
        self.lock                 = threading.Lock()

STATE = BotState()

# ============================================================
# LOGGING
# ============================================================
import fq_logging
fq_logging.setup()
log = logging.getLogger("fq_bot_v3")

# ============================================================
# TELEGRAM
# ============================================================
def _html_escape(s):
    """Escapa &,<,> para incrustar texto dinamico (p.ej. el reason del gate,
    "vol_score=0.78<0.85") en mensajes HTML de Telegram sin romper el parse."""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _escape_claude(reading):
    """Escapa el texto libre de Claude antes de incrustarlo en un mensaje HTML
    de Telegram. Claude responde en texto plano (sin tags), asi que un '<', '>'
    o '&' suelto en su prosa (p.ej. 'RSI >45', 'P(SL) < 0.3', 'R&D') rompe el
    parse de Telegram; el fallback reenvia sin parse_mode y borra TODO el
    formato <b>/<i> del mensaje. Escapar aqui preserva el formato del template
    (sus tags no pasan por esta funcion). Devuelve '' si reading es falsy, lo
    que mantiene intactos los guards 'if reading:' / 'if not reading:'."""
    return _html_escape(reading) if reading else ""


def _strip_html_tags(s):
    """Quita tags HTML simples (los que empiezan con letra: <b>, </i>, <a ...>)
    dejando intacto texto tipo "<0.85". Para el fallback a texto plano sin
    parse_mode, donde los tags se verian crudos."""
    return re.sub(r"</?[a-zA-Z][^>]*>", "", s)


def telegram_send(text, chat_id=None):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")
        return False
    target = chat_id or TELEGRAM_CHAT_ID
    url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN)

    def _post(payload):
        try:
            r = requests.post(url, json=payload, timeout=15)
            return r
        except Exception as e:
            log.error("Telegram exception: {}".format(e))
            return None

    # Intento 1: con HTML parse mode (formato normal)
    payload = {
        "chat_id": target,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    r = _post(payload)
    if r is not None and r.status_code == 200:
        return True

    # Si fallo por parse de HTML (400 con can't parse entities),
    # reintentar SIN parse_mode para que Telegram lo trate como texto plano.
    # Comun cuando Claude responde con (200k) o <X> que parecen tags.
    if r is not None and r.status_code == 400 and "can't parse entities" in r.text:
        log.info("Telegram HTML parse fallo, reintentando como texto plano...")
        payload.pop("parse_mode", None)
        # Sin parse_mode los tags se verian crudos (<b>, <i>...). Quitarlos
        # para dejar texto limpio (preserva "<0.85").
        payload["text"] = _strip_html_tags(text)
        r2 = _post(payload)
        if r2 is not None and r2.status_code == 200:
            return True
        if r2 is not None:
            log.warning("Telegram send failed (plain retry) {}: {}".format(
                r2.status_code, r2.text[:200]))
        return False

    if r is not None:
        log.warning("Telegram send failed {}: {}".format(r.status_code, r.text[:200]))
    return False

def broadcast_to_subscribers(text, include_admin=True, tiers=None):
    """
    MISTRAL: Envia un mensaje (tipicamente una senal o anuncio operativo)
    a todos los usuarios con suscripcion activa: VIP, TRIAL, ADMIN.

    - Dedupea por chat_id (un admin VIP no recibe doble).
    - Errores por usuario individual no rompen el broadcast.
    - Si VIP_ENABLED es False o falla, hace fallback al admin unico (TELEGRAM_CHAT_ID).
    - Devuelve (sent, failed) para logging.

    Args:
        text: mensaje a enviar (mismo formato que telegram_send)
        include_admin: incluir al admin TELEGRAM_CHAT_ID aunque no este en BD
        tiers: lista opcional de tiers a incluir. Default: vip + trial + admin

    Uso tipico:
        broadcast_to_subscribers(signal_msg)   # senal completa
        broadcast_to_subscribers(opus_reading) # follow-up Opus
    """
    if tiers is None:
        tiers = ["vip", "trial", "admin"]

    # WEEKEND ADMIN-ONLY GATE: con el mercado cerrado (finde) y el bypass admin
    # activo, el motor sigue generando pero la entrega se restringe al admin.
    # VIP/trial/free no reciben senales/anuncios hasta la reapertura.
    if WEEKEND_ADMIN_ONLY and ICT_MODULES_AVAILABLE:
        try:
            if killzones_pd.is_weekend_closed():
                tiers = ["admin"]
                include_admin = True
        except Exception:
            pass

    sent = 0
    failed = 0
    seen = set()

    # Fallback: si VIP no esta cargado, solo manda al admin
    if not VIP_ENABLED or vip is None:
        if include_admin and TELEGRAM_CHAT_ID:
            ok = telegram_send(text, TELEGRAM_CHAT_ID)
            return (1 if ok else 0, 0 if ok else 1)
        return (0, 0)

    # Recolectar destinatarios desde BD
    try:
        recipients = []
        for tier in tiers:
            try:
                users = vip.get_all_users(tier=tier, limit=1000)
                recipients.extend(users)
            except Exception as e:
                log.warning("broadcast: error getting tier {}: {}".format(tier, e))

        # Asegurar que el admin original siempre reciba (si no esta en BD aun)
        if include_admin and TELEGRAM_CHAT_ID:
            seen.add(str(TELEGRAM_CHAT_ID))
            ok = telegram_send(text, TELEGRAM_CHAT_ID)
            if ok:
                sent += 1
            else:
                failed += 1

        for u in recipients:
            cid = str(u.get("chat_id", "")).strip()
            if not cid or cid in seen:
                continue
            # Saltar VIPs/trials cuya suscripcion ya expiro
            try:
                effective = vip.get_effective_tier(cid)
                if effective == "free":
                    continue
            except Exception:
                pass
            seen.add(cid)
            try:
                ok = telegram_send(text, cid)
                if ok:
                    sent += 1
                else:
                    failed += 1
            except Exception as e:
                log.warning("broadcast to {}: {}".format(cid, e))
                failed += 1

        log.info("Broadcast: sent={} failed={} (tiers={})".format(sent, failed, tiers))
        return (sent, failed)

    except Exception as e:
        log.error("broadcast_to_subscribers fatal: {}".format(e))
        # Fallback final al admin
        if include_admin and TELEGRAM_CHAT_ID:
            telegram_send(text, TELEGRAM_CHAT_ID)
        return (sent, failed)

def telegram_get_updates(offset, timeout=25):
    url = "https://api.telegram.org/bot{}/getUpdates".format(TELEGRAM_TOKEN)
    params = {"offset": offset, "timeout": timeout, "allowed_updates": ["message"]}
    try:
        r = requests.get(url, params=params, timeout=timeout + 10)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception as e:
        log.warning("Telegram getUpdates error: {}".format(e))
    return []

# ============================================================
# DATA
# ============================================================
# v5.3 etapa 2: el acceso a velas + indicadores vive en fq_market_data.py
# (ver ARCHITECTURE.md). Se reexporta para no tocar los ~30 call sites que
# usan fetch_ohlcv()/add_indicators() como nombres del modulo.
import fq_market_data
from fq_market_data import fetch_ohlcv, add_indicators

# ============================================================
# TIME / SESSION
# ============================================================
CDMX_TZ = timezone(timedelta(hours=-6))

def cdmx_now():
    return datetime.now(CDMX_TZ)

def cdmx_now_str():
    return cdmx_now().strftime("%Y-%m-%d %H:%M CDMX")

def get_session():
    """Returns (session_name, w_clock, time_to_next_session_minutes, next_session_name)"""
    now = cdmx_now()
    h = now.hour + now.minute / 60.0

    # Definicion de sesiones (CDMX)
    if 7.5 <= h < 10.0:
        return ("overlap", SESSION_WEIGHTS["overlap"], int((10.0 - h) * 60), "ny")
    if 10.0 <= h < 15.0:
        return ("ny", SESSION_WEIGHTS["ny"], int((15.0 - h) * 60), "asia")
    if 2.0 <= h < 7.5:
        return ("london", SESSION_WEIGHTS["london"], int((7.5 - h) * 60), "overlap")
    # Asia: 15:00-02:00 (cross midnight)
    if h >= 15.0:
        rem = int((24.0 + 2.0 - h) * 60)
    else:  # 0 <= h < 2.0
        rem = int((2.0 - h) * 60)
    return ("asia", SESSION_WEIGHTS["asia"], rem, "london")

def session_quality_label(w_clock):
    """Etiqueta cualitativa del W_clock"""
    if w_clock >= 1.20: return "MAXIMA ENERGIA"
    if w_clock >= 1.00: return "ALTA"
    if w_clock >= 0.80: return "MEDIA"
    return "BAJA - Operar con precaucion"

# ============================================================
# DECOHERENCE TESTS - Pillar I
# ============================================================
def test_macro(exchange):
    """
    MISTRAL: Ventana deslizante (no punto-a-punto).
    Compara precio actual vs min/max de las 4 velas previas.
    Evita falsos negativos cuando BTC corrige entre velas.
    """
    out = {
        "passed": False, "direction": None,
        "btc_change": 0.0, "eth_change": 0.0,
        "diagnostic": "",
    }
    try:
        btc = fetch_ohlcv(exchange, SYMBOL_BTC, "15m", limit=20)
        eth = fetch_ohlcv(exchange, SYMBOL_ETH, "15m", limit=20)

        # Ventana 4 velas previas como base
        btc_base_low  = float(btc["close"].iloc[-6:-2].min())
        btc_base_high = float(btc["close"].iloc[-6:-2].max())
        btc_now       = float(btc["close"].iloc[-1])
        eth_base_low  = float(eth["close"].iloc[-6:-2].min())
        eth_base_high = float(eth["close"].iloc[-6:-2].max())
        eth_now       = float(eth["close"].iloc[-1])

        # Momentum bull/bear desde extremos recientes
        btc_bull = (btc_now - btc_base_low)  / btc_base_low  if btc_base_low  > 0 else 0
        eth_bull = (eth_now - eth_base_low)  / eth_base_low  if eth_base_low  > 0 else 0
        btc_bear = (btc_base_high - btc_now) / btc_base_high if btc_base_high > 0 else 0
        eth_bear = (eth_base_high - eth_now) / eth_base_high if eth_base_high > 0 else 0

        # Display: signo segun direccion dominante
        btc_mid = (btc_base_low + btc_base_high) / 2
        eth_mid = (eth_base_low + eth_base_high) / 2
        out["btc_change"] = btc_bull * 100 if btc_now >= btc_mid else -btc_bear * 100
        out["eth_change"] = eth_bull * 100 if eth_now >= eth_mid else -eth_bear * 100

        with STATE.lock:
            STATE.last_btc_chg = out["btc_change"]
            STATE.last_eth_chg = out["eth_change"]

        if btc_bull >= MACRO_THRESHOLD_PCT and eth_bull >= MACRO_THRESHOLD_PCT:
            out["passed"] = True
            out["direction"] = "long"
            out["diagnostic"] = "BULL OK BTC+{:.3f}% ETH+{:.3f}%".format(
                btc_bull*100, eth_bull*100)
        elif btc_bear >= MACRO_THRESHOLD_PCT and eth_bear >= MACRO_THRESHOLD_PCT:
            out["passed"] = True
            out["direction"] = "short"
            out["diagnostic"] = "BEAR OK BTC-{:.3f}% ETH-{:.3f}%".format(
                btc_bear*100, eth_bear*100)
        else:
            need = MACRO_THRESHOLD_PCT * 100
            best_bull = min(btc_bull, eth_bull) * 100
            best_bear = min(btc_bear, eth_bear) * 100
            if best_bull >= best_bear:
                out["diagnostic"] = "bull falta {:.3f}% (BTC+{:.3f}% ETH+{:.3f}%)".format(
                    need - best_bull, btc_bull*100, eth_bull*100)
            else:
                out["diagnostic"] = "bear falta {:.3f}% (BTC-{:.3f}% ETH-{:.3f}%)".format(
                    need - best_bear, btc_bear*100, eth_bear*100)
    except Exception as e:
        log.error("Macro test error: {}".format(e))
        out["diagnostic"] = "ERROR: " + str(e)[:60]
    return out

def test_technical(df, direction):
    last = df.iloc[-1]
    price = last["close"]
    indicators = ["ema9", "ema20", "ema50", "ema200", "sma20", "sma50"]
    aligned = total = 0
    for col in indicators:
        v = last.get(col)
        if v is None or pd.isna(v):
            continue
        total += 1
        if direction == "long" and price > v:  aligned += 1
        if direction == "short" and price < v: aligned += 1
    macd_v = last.get("macd")
    sig_v  = last.get("macd_signal")
    if macd_v is not None and sig_v is not None and not pd.isna(macd_v) and not pd.isna(sig_v):
        total += 1
        if direction == "long"  and macd_v > sig_v: aligned += 1
        if direction == "short" and macd_v < sig_v: aligned += 1
    return {
        "passed":  aligned >= TECH_MIN_ALIGNED and total >= 6,
        "aligned": aligned,
        "total":   total,
    }

def test_liquidity(df, direction):
    last = df.iloc[-1]
    r6, r12, r24 = last.get("rsi6"), last.get("rsi12"), last.get("rsi24")
    if any(pd.isna(x) for x in [r6, r12, r24]):
        return {"passed": False, "rsi6": 0, "rsi12": 0, "rsi24": 0}
    if direction == "long":
        passed = r6 > 50 and r12 > 50 and r24 > 50
    else:
        passed = r6 < 50 and r12 < 50 and r24 < 50
    return {"passed": passed, "rsi6": r6, "rsi12": r12, "rsi24": r24}

# ============================================================
# P-SPACE - Pillar III (curvatura k(p) por masas)
# ============================================================
def detect_pspace(df):
    last = df.iloc[-1]
    price = float(last["close"])
    threshold = price * 0.006  # 0.6% tolerancia
    masses = []

    # Estructurales (peso 1.0)
    high_50 = float(df["high"].iloc[-50:].max())
    low_50  = float(df["low"].iloc[-50:].min())
    if abs(price - high_50) <= threshold:
        masses.append({"name": "Resistencia 50v", "price": high_50, "weight": 1.0, "type": "resistance"})
    if abs(price - low_50) <= threshold:
        masses.append({"name": "Soporte 50v", "price": low_50, "weight": 1.0, "type": "support"})

    # Medias moviles (peso 0.6-0.7)
    ma_map = [
        ("EMA50",  "ema50",  0.7),
        ("EMA200", "ema200", 0.8),
        ("EMA20",  "ema20",  0.6),
        ("SMA20",  "sma20",  0.6),
        ("SMA50",  "sma50",  0.7),
    ]
    for name, col, w in ma_map:
        v = last.get(col)
        if v is not None and not pd.isna(v) and abs(price - float(v)) <= threshold:
            mtype = "support" if price >= float(v) else "resistance"
            masses.append({"name": name, "price": float(v), "weight": w, "type": mtype})

    # Bollinger (peso 0.6)
    bbu = last.get("bb_upper")
    bbl = last.get("bb_lower")
    bbm = last.get("bb_mid")
    if bbu is not None and not pd.isna(bbu) and abs(price - float(bbu)) <= threshold:
        masses.append({"name": "BB Upper", "price": float(bbu), "weight": 0.6, "type": "resistance"})
    if bbl is not None and not pd.isna(bbl) and abs(price - float(bbl)) <= threshold:
        masses.append({"name": "BB Lower", "price": float(bbl), "weight": 0.6, "type": "support"})
    if bbm is not None and not pd.isna(bbm) and abs(price - float(bbm)) <= threshold:
        mtype = "support" if price >= float(bbm) else "resistance"
        masses.append({"name": "BB Media", "price": float(bbm), "weight": 0.5, "type": mtype})

    # Volumen anomalo (peso 0.9)
    vol_ma = last.get("vol_ma20")
    if vol_ma is not None and not pd.isna(vol_ma) and last["volume"] > 1.8 * float(vol_ma):
        masses.append({"name": "Volumen anomalo", "price": price, "weight": 0.9, "type": "neutral"})

    # Psicologico (peso 0.7)
    rounded = round(price)
    if abs(price - rounded) <= threshold:
        mtype = "support" if price >= rounded else "resistance"
        masses.append({"name": "Psicologico ${}".format(int(rounded)), "price": float(rounded), "weight": 0.7, "type": mtype})

    # Calcular curvatura k(p) - suma ponderada de masas dividida por dispersion
    total_weight = sum(m["weight"] for m in masses)
    supports = [m for m in masses if m["type"] == "support"]
    resistances = [m for m in masses if m["type"] == "resistance"]
    support_weight = sum(m["weight"] for m in supports)
    resistance_weight = sum(m["weight"] for m in resistances)

    return {
        "passed":            len(masses) >= PSPACE_MIN_MASSES,
        "count":             len(masses),
        "masses":            masses,
        "total_weight":      total_weight,
        "support_weight":    support_weight,
        "resistance_weight": resistance_weight,
        "supports":          supports,
        "resistances":       resistances,
    }

# ============================================================
# LAPLACIAN - Pillar IV
# ============================================================
def laplacian_check(df):
    closes = df["close"].values
    if len(closes) < 20:
        return {"active": False, "ratio": 0.0}
    lap = []
    for i in range(1, len(closes) - 1):
        lap.append(closes[i + 1] - 2 * closes[i] + closes[i - 1])
    if len(lap) < 10:
        return {"active": False, "ratio": 0.0}
    norm_now = abs(lap[-1])
    norm_lag = sum(abs(x) for x in lap[-6:-1]) / 5.0
    if norm_lag == 0:
        return {"active": False, "ratio": 0.0}
    ratio = norm_now / norm_lag
    return {"active": ratio > PHI, "ratio": ratio}

# ============================================================
# MOMENTUM & STRUCTURE BIAS
# ============================================================
def detect_bias(df):
    """Detecta sesgo direccional estructural multi-TF interno"""
    last = df.iloc[-1]
    price = float(last["close"])
    closes = df["close"].iloc[-20:].values

    # Momentum corto (5v) y medio (20v)
    mom_5  = (closes[-1] - closes[-6])  / closes[-6]  if len(closes) >= 6  else 0
    mom_20 = (closes[-1] - closes[0])   / closes[0]   if len(closes) >= 20 else 0

    # Posicion vs EMAs clave
    ema50  = last.get("ema50")
    ema200 = last.get("ema200")
    above_50  = ema50  is not None and not pd.isna(ema50)  and price > float(ema50)
    above_200 = ema200 is not None and not pd.isna(ema200) and price > float(ema200)

    score = 0
    if mom_5  > 0:  score += 1
    if mom_5  < 0:  score -= 1
    if mom_20 > 0:  score += 1
    if mom_20 < 0:  score -= 1
    if above_50:    score += 1
    else:           score -= 1
    if above_200:   score += 2
    else:           score -= 2

    if score >= 3:    bias = "alcista"
    elif score >= 1:  bias = "alcista debil"
    elif score <= -3: bias = "bajista"
    elif score <= -1: bias = "bajista debil"
    else:             bias = "lateral"

    return {
        "bias":      bias,
        "score":     score,
        "mom_5":     mom_5 * 100,
        "mom_20":    mom_20 * 100,
        "above_50":  above_50,
        "above_200": above_200,
    }

# ============================================================
# LEVELS CALCULATION
# ============================================================
def calculate_levels(df, direction):
    last = df.iloc[-1]
    entry = float(last["close"])
    high = float(df["high"].iloc[-50:].max())
    low  = float(df["low"].iloc[-50:].min())
    rng  = high - low

    if direction == "long":
        ema50_v = last.get("ema50")
        ema50_v = float(ema50_v) if ema50_v is not None and not pd.isna(ema50_v) else entry * 0.99
        sl  = min(ema50_v, float(df["low"].iloc[-10:].min())) * 0.998
        tp1 = entry + (rng * PHI_INV * PHI_INV)
        tp2 = entry + (rng * PHI_INV)
        # tp3: peldano intermedio REAL entre tp2 (0.618*rng) y tp4 (1.0*rng).
        # Antes era entry*(1+(rng/entry)*PHI_INV) == entry+rng*PHI_INV == tp2
        # (mismo precio que tp2): la "escalera" tenia 3 peldanos, no 4. Ahora usa
        # el punto medio aureo (1+PHI_INV)/2 ~= 0.809*rng -> cuatro TPs distintos
        # y monotonos.
        tp3 = entry + (rng * (1.0 + PHI_INV) / 2.0)
        tp4 = entry + (rng * PHI_INV * PHI)
    else:
        ema50_v = last.get("ema50")
        ema50_v = float(ema50_v) if ema50_v is not None and not pd.isna(ema50_v) else entry * 1.01
        sl  = max(ema50_v, float(df["high"].iloc[-10:].max())) * 1.002
        tp1 = entry - (rng * PHI_INV * PHI_INV)
        tp2 = entry - (rng * PHI_INV)
        # tp3: peldano intermedio REAL entre tp2 y tp4 (simetrico al long). Antes
        # == tp2 por construccion; ahora punto medio aureo (1+PHI_INV)/2.
        tp3 = entry - (rng * (1.0 + PHI_INV) / 2.0)
        tp4 = entry - (rng * PHI_INV * PHI)

    risk = abs(entry - sl)
    return {
        "entry": entry, "sl": sl,
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "tp4": tp4,
        "risk":   risk,
        "rr_tp1": abs(tp1 - entry) / risk if risk > 0 else 0,
        "rr_tp2": abs(tp2 - entry) / risk if risk > 0 else 0,
        "rr_tp3": abs(tp3 - entry) / risk if risk > 0 else 0,
        "rr_tp4": abs(tp4 - entry) / risk if risk > 0 else 0,
    }

# ============================================================
# LEVELS V2 - SL ANTI STOP-HUNT + TPs ESTRUCTURALES (F1 v5.0)
# ============================================================
# Reemplazo opcional de calculate_levels que ancla SL a estructura
# ICT (OB / liquidity pool / swing low / FVG) y TPs a liquidez real
# (P-Space resistances, pools no barridos, OB opuestos, Fib extensions).
# calculate_levels original NO se modifica - cero rupturas.

SL_ANCHOR_LABELS = {
    "OB_bullish":      "Order Block alcista",
    "OB_bearish":      "Order Block bajista",
    "pool_low":        "pool de liquidez (sin barrer)",
    "pool_high":       "pool de liquidez (sin barrer)",
    "post_sweep_low":  "reaccion post-sweep (low)",
    "post_sweep_high": "reaccion post-sweep (high)",
    "swing_low":       "swing low estructural",
    "swing_high":      "swing high estructural",
    "FVG_bottom":      "FVG bullish (borde inferior)",
    "FVG_top":         "FVG bearish (borde superior)",
    "EMA50":           "EMA50 (fallback)",
    "low_20":          "low de 20 velas (fallback)",
    "high_20":         "high de 20 velas (fallback)",
    "ATR_clamp":       "clamp ATR (anti-SL excesivo)",
}

TP_KIND_LABELS = {
    "pspace_R":       "resistencia P-Space",
    "pspace_S":       "soporte P-Space",
    "BSL_target":     "liquidez sin barrer",
    "SSL_target":     "liquidez sin barrer",
    "OB_bear":        "Order Block opuesto",
    "OB_bull":        "Order Block opuesto",
    "FVG_bear":       "FVG bajista",
    "FVG_bull":       "FVG alcista",
    "fib_1272":       "extension 1.272",
    "fib_1618":       "extension 1.618",
    "fib_fallback":   "extension Fib",
}

# ============================================================
# LONGITUD DE ONDA DE TPs POR TIMEFRAME (FQ v5.5)
# ============================================================
# Las bandas R:R de los TPs son relativas al riesgo (distancia al SL). En TFs
# rapidos (5m/3m/1m) el SL es ajustado y el precio recorre esa distancia en
# pocas velas -> los 3 TPs se ejecutaban "demasiado rapido" (onda corta). En
# 15m el problema opuesto: TP3/TP4 se sobre-extendian y el momentum se evaporaba
# antes de llegar. Este factor escala las bandas por TF para que el espaciado de
# los objetivos tenga sentido TEMPORAL en cada marco, sin inventar precios:
#   >1  alarga la onda (mas espacio entre TPs)  -> TFs rapidos
#   =1  baseline 15m (con cap anti-sobre-extension)
# Cada TP sigue anclado a estructura real (pools/OB/FVG/fib/pspace); el factor
# solo mueve la BANDA donde se busca ese anclaje.
TP_WAVELENGTH_FACTORS = {
    "1m":  1.50,
    "3m":  1.35,
    "5m":  1.20,
    "15m": 1.00,
    "1h":  1.00,
    "4h":  1.00,
}

def _tf_wavelength_factor(tf):
    """Factor de longitud de onda de los TPs para el timeframe dado. 1.0 si
    el TF no esta mapeado (no altera el comportamiento baseline)."""
    try:
        return float(TP_WAVELENGTH_FACTORS.get(tf, 1.0))
    except (TypeError, ValueError):
        return 1.0

def _safe_atr(last, entry):
    """ATR seguro: usa atr14 si existe, sino 0.5% del entry."""
    atr = last.get("atr14")
    if atr is None or pd.isna(atr):
        return entry * 0.005
    return float(atr)

def _collect_sl_candidates_long(entry, atr, buffer, field_data):
    """
    Devuelve lista de candidatos SL para LONG con (price_sl, anchor_label).
    Ordenados por proximidad al entry (mas cercano primero).
    """
    cands = []

    # 1. Order Block bullish valido por debajo del entry
    ob_bull = field_data.get("ob_bullish")
    if ob_bull is not None and getattr(ob_bull, "still_valid", True):
        ob_low = float(ob_bull.low)
        if ob_low < entry:
            cands.append((ob_low - buffer, "OB_bullish"))

    # 2. Liquidity pool low
    pool_l = field_data.get("pool_low")
    if pool_l is not None and pool_l.price < entry:
        if not pool_l.swept:
            cands.append((pool_l.price - buffer, "pool_low"))
        else:
            # Sweep ya cumplido - SL mas generoso debajo de la reaccion
            cands.append((pool_l.price - buffer * 1.5, "post_sweep_low"))

    # 3. Swing low estructural (ultimo pivot low)
    pivot_lows = field_data.get("pivot_lows") or []
    if pivot_lows:
        last_pl = pivot_lows[-1]
        pl_price = float(last_pl.price) if hasattr(last_pl, "price") else float(last_pl)
        if pl_price < entry:
            cands.append((pl_price - buffer, "swing_low"))

    # 4. FVG bullish bottom mas cercano por debajo
    fvgs = field_data.get("fvgs") or []
    bull_fvgs_below = [f for f in fvgs
                      if getattr(f, "direction", "") == "bullish"
                      and float(f.bottom) < entry]
    if bull_fvgs_below:
        closest = max(bull_fvgs_below, key=lambda f: float(f.bottom))
        cands.append((float(closest.bottom) - buffer * 0.5, "FVG_bottom"))

    # 5. EMA50 fallback
    ema50 = field_data.get("ema50")
    if ema50 is not None and ema50 < entry:
        cands.append((ema50 - buffer, "EMA50"))

    # 6. Low 20 velas - ultimo fallback
    low_20 = field_data.get("low_20")
    if low_20 is not None and low_20 < entry:
        cands.append((low_20 - buffer, "low_20"))

    cands.sort(key=lambda c: entry - c[0])  # mas cercanos primero
    return cands

def _collect_sl_candidates_short(entry, atr, buffer, field_data):
    """Simetrico para SHORT - todos los candidatos por encima del entry."""
    cands = []

    ob_bear = field_data.get("ob_bearish")
    if ob_bear is not None and getattr(ob_bear, "still_valid", True):
        ob_high = float(ob_bear.high)
        if ob_high > entry:
            cands.append((ob_high + buffer, "OB_bearish"))

    pool_h = field_data.get("pool_high")
    if pool_h is not None and pool_h.price > entry:
        if not pool_h.swept:
            cands.append((pool_h.price + buffer, "pool_high"))
        else:
            cands.append((pool_h.price + buffer * 1.5, "post_sweep_high"))

    pivot_highs = field_data.get("pivot_highs") or []
    if pivot_highs:
        last_ph = pivot_highs[-1]
        ph_price = float(last_ph.price) if hasattr(last_ph, "price") else float(last_ph)
        if ph_price > entry:
            cands.append((ph_price + buffer, "swing_high"))

    fvgs = field_data.get("fvgs") or []
    bear_fvgs_above = [f for f in fvgs
                      if getattr(f, "direction", "") == "bearish"
                      and float(f.top) > entry]
    if bear_fvgs_above:
        closest = min(bear_fvgs_above, key=lambda f: float(f.top))
        cands.append((float(closest.top) + buffer * 0.5, "FVG_top"))

    ema50 = field_data.get("ema50")
    if ema50 is not None and ema50 > entry:
        cands.append((ema50 + buffer, "EMA50"))

    high_20 = field_data.get("high_20")
    if high_20 is not None and high_20 > entry:
        cands.append((high_20 + buffer, "high_20"))

    cands.sort(key=lambda c: c[0] - entry)
    return cands

def _compute_sl_v2(entry, atr, direction, field_data):
    """
    Calcula SL anti-stop-hunt anclado a estructura ICT.
    Devuelve (sl_price, anchor_label).
    """
    buffer = max(0.6 * atr, 0.0015 * entry)

    if direction == "long":
        cands = _collect_sl_candidates_long(entry, atr, buffer, field_data)
    else:
        cands = _collect_sl_candidates_short(entry, atr, buffer, field_data)

    if not cands:
        # Fallback ultimo: 1.5*ATR del entry
        if direction == "long":
            return entry - max(1.5 * atr, 0.015 * entry), "ATR_clamp"
        else:
            return entry + max(1.5 * atr, 0.015 * entry), "ATR_clamp"

    # De los 3 mas cercanos, tomar el MAS LEJANO (margen anti-hunt)
    top3 = cands[:3]
    if direction == "long":
        sl_price, anchor = min(top3, key=lambda c: c[0])  # menor precio = mas lejos
    else:
        sl_price, anchor = max(top3, key=lambda c: c[0])  # mayor precio = mas lejos

    # Sanity clamp: SL no mas alla del 5% del entry
    sl_dist_pct = abs(entry - sl_price) / entry
    if sl_dist_pct > 0.05:
        clamp_dist = min(2.5 * atr, 0.025 * entry)
        if direction == "long":
            sl_price = entry - clamp_dist
        else:
            sl_price = entry + clamp_dist
        anchor = "ATR_clamp"

    return sl_price, anchor

def _collect_tp_targets(entry, direction, field_data, pspace):
    """
    Recolecta targets candidatos en la direccion del trade.
    Devuelve list[dict(price, kind, weight)].
    """
    targets = []
    is_long = direction == "long"

    # P-Space masses (resistances arriba para LONG, supports abajo para SHORT)
    if pspace:
        if is_long:
            for m in pspace.get("resistances", []):
                if m["price"] > entry:
                    targets.append({"price": float(m["price"]),
                                    "kind": "pspace_R",
                                    "weight": float(m.get("weight", 1.0))})
        else:
            for m in pspace.get("supports", []):
                if m["price"] < entry:
                    targets.append({"price": float(m["price"]),
                                    "kind": "pspace_S",
                                    "weight": float(m.get("weight", 1.0))})

    # Liquidity pools NO barridos = BSL/SSL targets (mas peso)
    if is_long:
        pool_h = field_data.get("pool_high")
        if pool_h is not None and not pool_h.swept and pool_h.price > entry:
            targets.append({"price": float(pool_h.price),
                            "kind": "BSL_target", "weight": 1.5})
    else:
        pool_l = field_data.get("pool_low")
        if pool_l is not None and not pool_l.swept and pool_l.price < entry:
            targets.append({"price": float(pool_l.price),
                            "kind": "SSL_target", "weight": 1.5})

    # Order Block opuesto
    if is_long:
        ob_bear = field_data.get("ob_bearish")
        if ob_bear is not None and ob_bear.still_valid and float(ob_bear.low) > entry:
            targets.append({"price": float(ob_bear.low),
                            "kind": "OB_bear", "weight": 1.2})
    else:
        ob_bull = field_data.get("ob_bullish")
        if ob_bull is not None and ob_bull.still_valid and float(ob_bull.high) < entry:
            targets.append({"price": float(ob_bull.high),
                            "kind": "OB_bull", "weight": 1.2})

    # FVG opuestos
    fvgs = field_data.get("fvgs") or []
    if is_long:
        bear_fvgs = [f for f in fvgs if f.direction == "bearish" and float(f.bottom) > entry]
        for f in bear_fvgs:
            targets.append({"price": float(f.bottom), "kind": "FVG_bear", "weight": 0.9})
    else:
        bull_fvgs = [f for f in fvgs if f.direction == "bullish" and float(f.top) < entry]
        for f in bull_fvgs:
            targets.append({"price": float(f.top), "kind": "FVG_bull", "weight": 0.9})

    # Fib extensions 127.2% y 161.8%
    swing_high = field_data.get("swing_high_recent")
    swing_low = field_data.get("swing_low_recent")
    if swing_high is not None and swing_low is not None and swing_high > swing_low:
        rng = swing_high - swing_low
        if is_long:
            targets.append({"price": swing_low + rng * 1.272,
                            "kind": "fib_1272", "weight": 0.8})
            targets.append({"price": swing_low + rng * 1.618,
                            "kind": "fib_1618", "weight": 0.8})
        else:
            targets.append({"price": swing_high - rng * 1.272,
                            "kind": "fib_1272", "weight": 0.8})
            targets.append({"price": swing_high - rng * 1.618,
                            "kind": "fib_1618", "weight": 0.8})

    return targets

def _pick_tp_in_band(targets, entry, risk, rr_min, rr_max, prefer_kinds, direction):
    """
    Encuentra el mejor TP dentro del rango R:R [rr_min, rr_max].
    1) Filtra targets con kind en prefer_kinds y R dentro de banda
    2) Si no hay, prueba sin filtro de kind
    3) Si tampoco, devuelve None
    """
    is_long = direction == "long"

    def in_band(t):
        if is_long and t["price"] <= entry: return False
        if not is_long and t["price"] >= entry: return False
        rr = abs(t["price"] - entry) / risk if risk > 0 else 0
        return rr_min <= rr <= rr_max

    in_band_list = [t for t in targets if in_band(t)]
    if not in_band_list:
        return None

    preferred = [t for t in in_band_list if t["kind"] in prefer_kinds]
    pool = preferred if preferred else in_band_list

    if is_long:
        return min(pool, key=lambda t: -t["weight"] * 1000 + t["price"])
    return min(pool, key=lambda t: -t["weight"] * 1000 - t["price"])

def _compute_tps_v2(entry, sl, direction, field_data, pspace, tf=None):
    """
    Calcula TPs anclados a liquidez/estructura real.
    Devuelve list de 4 dicts: [{price, kind, rr}, ...]

    FQ v5.5:
      - Bandas R:R con CAP anti-sobre-extension: TP3 <= 5R y TP4 <= 6.5R
        (baseline 15m) en vez de techo abierto. Antes TP4 podia caer en 5R..inf
        prefiriendo siempre la extension Fib mas lejana -> "no llegaba / tardaba
        demasiadas horas".
      - Escala las bandas por timeframe (`tf`) via _tf_wavelength_factor para
        que la longitud de onda sea coherente con el marco (5m no ejecuta los
        TPs en minutos; 15m no se sobre-extiende).
      - Anclaje tecnico reforzado: si no hay estructural en la banda exacta,
        expande +-20% buscando liquidez/estructura REAL antes de proyectar un
        objetivo sintetico (menos "humo").
    """
    risk = abs(entry - sl)
    if risk <= 0:
        return []

    wf = _tf_wavelength_factor(tf)
    targets = _collect_tp_targets(entry, direction, field_data, pspace)
    tps = []

    # Bandas base 15m (lo, hi en R) con cap anti-sobre-extension. Se escalan
    # por TF: en marcos rapidos la onda se alarga; en 15m queda baseline.
    base_bands = [
        (1.2, 2.0, ["BSL_target", "SSL_target", "pspace_R", "pspace_S", "OB_bear", "OB_bull"]),
        (2.0, 3.5, ["BSL_target", "SSL_target", "fib_1272", "pspace_R", "pspace_S"]),
        (3.5, 5.0, ["fib_1618", "fib_1272", "pspace_R", "pspace_S", "BSL_target", "SSL_target"]),
        (5.0, 6.5, ["fib_1618", "fib_1272", "pspace_R", "pspace_S"]),
    ]
    sign = 1.0 if direction == "long" else -1.0

    for rr_min, rr_max, prefer in base_bands:
        lo, hi = rr_min * wf, rr_max * wf
        # 1) estructura preferida dentro de la banda
        tp = _pick_tp_in_band(targets, entry, risk, lo, hi, prefer, direction)
        # 2) cualquier estructura real cercana (banda expandida) antes que humo
        if tp is None:
            tp = _pick_tp_in_band(targets, entry, risk, lo * 0.8, hi * 1.2,
                                  [], direction)
        # 3) ultimo recurso: proyeccion R honesta (no liquidez inventada)
        if tp is None:
            rr_target = (lo + min(hi, lo + 1.0 * wf)) / 2.0
            tp = {"price": entry + sign * risk * rr_target,
                  "kind": "fib_fallback", "weight": 0.5}
        rr = abs(tp["price"] - entry) / risk
        tps.append({"price": tp["price"], "kind": tp["kind"], "rr": rr})

    return _enforce_tp_monotonic(tps, entry, risk, direction)


def _enforce_tp_monotonic(tps, entry, risk, direction, min_step_r=0.25):
    """Garantiza R estrictamente creciente entre TPs. Las bandas escaladas por
    TF pueden, en bordes, devolver un TP_{n+1} no mas lejano que TP_n; en ese
    caso se empuja el siguiente min_step_r por encima del previo (precio
    derivado del R, sigue siendo tecnico)."""
    sign = 1.0 if direction == "long" else -1.0
    prev_rr = 0.0
    for t in tps:
        if t["rr"] <= prev_rr:
            new_rr = prev_rr + min_step_r
            t["rr"] = round(new_rr, 4)
            t["price"] = round(entry + sign * risk * new_rr, 6)
        prev_rr = t["rr"]
    return tps

def _build_field_data_standalone(df_15m, df_1h, df_4h):
    """
    Construye field_data dict reutilizando ict_smc detectores cuando esten
    disponibles. Si no, usa fallbacks basicos.
    """
    fd = {}
    last = df_15m.iloc[-1]

    # Fallbacks basicos siempre disponibles
    fd["ema50"] = float(last.get("ema50")) if last.get("ema50") is not None and not pd.isna(last.get("ema50")) else None
    fd["low_20"] = float(df_15m["low"].iloc[-20:].min())
    fd["high_20"] = float(df_15m["high"].iloc[-20:].max())
    fd["swing_high_recent"] = float(df_15m["high"].iloc[-50:].max())
    fd["swing_low_recent"] = float(df_15m["low"].iloc[-50:].min())

    # Detectores ICT si disponibles
    if ICT_MODULES_AVAILABLE and ict_smc is not None:
        try:
            pivot_highs, pivot_lows = ict_smc.find_pivots(df_15m)
            fd["pivot_highs"] = pivot_highs
            fd["pivot_lows"] = pivot_lows

            obs = ict_smc.detect_order_blocks(df_15m)
            fd["ob_bullish"] = obs.get("bullish")
            fd["ob_bearish"] = obs.get("bearish")

            pool_h, pool_l, recent_sweep = ict_smc.detect_liquidity_pools(
                df_15m, pivot_highs, pivot_lows)
            fd["pool_high"] = pool_h
            fd["pool_low"] = pool_l
            fd["recent_sweep"] = recent_sweep

            fd["fvgs"] = ict_smc.detect_fvgs(df_15m)
        except Exception as e:
            log.warning("ICT detectors fallback (calc_levels_v2): {}".format(e))

    return fd

def calculate_levels_v2(df, direction, df_1h=None, df_4h=None, df_1m=None,
                        pspace=None, tf=None):
    """
    Nueva calculadora de niveles con SL anclado a estructura ICT y TPs
    anclados a liquidez real. Compatible con calculate_levels (devuelve
    mismas keys) + extra: sl_anchor, tp_meta, atr.

    `tf`: timeframe de la senal (5m/15m/1h...). Ajusta la longitud de onda de
    los TPs para que el espaciado sea coherente con el marco (v5.5).
    """
    last = df.iloc[-1]
    entry = float(last["close"])
    atr = _safe_atr(last, entry)

    field_data = _build_field_data_standalone(df, df_1h, df_4h)

    sl, anchor = _compute_sl_v2(entry, atr, direction, field_data)
    tps = _compute_tps_v2(entry, sl, direction, field_data, pspace, tf=tf)

    risk = abs(entry - sl)
    result = {
        "entry": entry, "sl": sl,
        "risk": risk,
        "atr": atr,
        "sl_anchor": anchor,
        "tp_meta": tps,
    }

    for i in range(4):
        if i < len(tps):
            result["tp{}".format(i+1)] = tps[i]["price"]
            result["rr_tp{}".format(i+1)] = tps[i]["rr"]
        else:
            result["tp{}".format(i+1)] = entry
            result["rr_tp{}".format(i+1)] = 0.0

    return result

# ============================================================
# TRIGGER PLAN GENERATOR (el corazon de /niveles v3.0)
# ============================================================
def build_trigger_plan(df, direction, pspace, bias):
    """
    Genera plan de entrada contextual segun masas P-Space.
    Decide entre: pullback / breakout / retest / wait
    Devuelve dict con: zona, trigger, confirmacion, invalidacion, plan_b
    """
    last = df.iloc[-1]
    price = float(last["close"])
    atr = last.get("atr14")
    atr = float(atr) if atr is not None and not pd.isna(atr) else price * 0.005

    # Buscar masas relevantes
    if direction == "long":
        # Para long: buscar soporte cercano abajo
        candidate_zones = sorted(pspace["supports"], key=lambda m: abs(price - m["price"]))
        zone_above = sorted([m for m in pspace["resistances"] if m["price"] > price], key=lambda m: m["price"] - price)
    else:
        candidate_zones = sorted(pspace["resistances"], key=lambda m: abs(price - m["price"]))
        zone_above = sorted([m for m in pspace["supports"] if m["price"] < price], key=lambda m: price - m["price"])

    has_close_mass = len(candidate_zones) > 0 and abs(candidate_zones[0]["price"] - price) <= atr * 0.5

    # Decision tree
    if has_close_mass:
        # Modo PULLBACK / RETEST
        zone_mass = candidate_zones[0]
        zone_price = zone_mass["price"]
        zone_low  = zone_price - atr * 0.3
        zone_high = zone_price + atr * 0.3
        if direction == "long":
            zone_str = "${:.2f} - ${:.2f}".format(zone_low, zone_high)
            trigger = "Vela 15m de cuerpo verde >= 50% del rango cerrando arriba de ${:.2f}".format(zone_price)
            confirmation = (
                "Volumen >= 1.3x MA20 en la vela de trigger\n"
                "RSI6 cruzando arriba de 50 desde zona oversold\n"
                "Mecha inferior tocando ${:.2f} y rechazo claro".format(zone_low)
            )
            invalidation = "Cierre 15m por debajo de ${:.2f} (zona perdida)".format(zone_low - atr * 0.2)
            mode = "PULLBACK A SOPORTE ({})".format(zone_mass["name"])
        else:
            zone_str = "${:.2f} - ${:.2f}".format(zone_low, zone_high)
            trigger = "Vela 15m de cuerpo rojo >= 50% del rango cerrando debajo de ${:.2f}".format(zone_price)
            confirmation = (
                "Volumen >= 1.3x MA20 en la vela de trigger\n"
                "RSI6 cruzando debajo de 50 desde zona overbought\n"
                "Mecha superior tocando ${:.2f} y rechazo claro".format(zone_high)
            )
            invalidation = "Cierre 15m por arriba de ${:.2f} (zona perdida)".format(zone_high + atr * 0.2)
            mode = "PULLBACK A RESISTENCIA ({})".format(zone_mass["name"])

    elif zone_above and abs(zone_above[0]["price"] - price) <= atr * 1.5:
        # Modo BREAKOUT
        target_mass = zone_above[0]
        target_price = target_mass["price"]
        if direction == "long":
            zone_str = "Sobre ${:.2f} con cierre 15m + retest exitoso".format(target_price)
            trigger = "Cierre 15m > ${:.2f} con cuerpo > 60% rango + volumen >= 1.5x MA20".format(target_price)
            confirmation = (
                "Retest de ${:.2f} sin perder zona (mecha permitida)\n"
                "RSI14 > 60 sostenido\n"
                "MACD cruz alcista o histograma creciente".format(target_price)
            )
            invalidation = "Cierre 15m de regreso debajo de ${:.2f} (breakout fallido)".format(target_price - atr * 0.3)
            mode = "BREAKOUT BULL ({})".format(target_mass["name"])
        else:
            zone_str = "Bajo ${:.2f} con cierre 15m + retest exitoso".format(target_price)
            trigger = "Cierre 15m < ${:.2f} con cuerpo > 60% rango + volumen >= 1.5x MA20".format(target_price)
            confirmation = (
                "Retest de ${:.2f} sin recuperar zona\n"
                "RSI14 < 40 sostenido\n"
                "MACD cruz bajista o histograma decreciente".format(target_price)
            )
            invalidation = "Cierre 15m de regreso arriba de ${:.2f} (breakout fallido)".format(target_price + atr * 0.3)
            mode = "BREAKOUT BEAR ({})".format(target_mass["name"])

    else:
        # Modo WAIT - sin masa cercana clara
        if direction == "long":
            target_low  = price - atr * 1.5
            zone_str = "${:.2f} - ${:.2f} (esperar pullback)".format(target_low, target_low + atr * 0.5)
            trigger = "Pullback hacia EMA50 o soporte estructural mas cercano + vela de rechazo"
            confirmation = (
                "RSI6 < 30 en pullback (oversold)\n"
                "Volumen menor en pullback que en avance previo\n"
                "Vela martillo o engulfing alcista"
            )
            invalidation = "Cierre 15m debajo de soporte estructural identificado"
            mode = "WAIT - sin masa inmediata, buscar pullback profundo"
        else:
            target_high = price + atr * 1.5
            zone_str = "${:.2f} - ${:.2f} (esperar pullback)".format(target_high - atr * 0.5, target_high)
            trigger = "Pullback hacia EMA50 o resistencia estructural mas cercana + vela de rechazo"
            confirmation = (
                "RSI6 > 70 en pullback (overbought)\n"
                "Volumen menor en pullback que en bajada previa\n"
                "Vela estrella fugaz o engulfing bajista"
            )
            invalidation = "Cierre 15m arriba de resistencia estructural identificada"
            mode = "WAIT - sin masa inmediata, buscar pullback profundo"

    # Plan B - direccion contraria
    if direction == "long":
        plan_b = "Si invalida: evaluar SHORT desde resistencia mas cercana arriba"
    else:
        plan_b = "Si invalida: evaluar LONG desde soporte mas cercano abajo"

    return {
        "mode":         mode,
        "zone":         zone_str,
        "trigger":      trigger,
        "confirmation": confirmation,
        "invalidation": invalidation,
        "plan_b":       plan_b,
    }

# ============================================================
# SIGNAL MESSAGE BUILDER
# ============================================================
def build_signal_msg(direction, levels, decoh, masses, session, w_clock, p_master, lap, intra=False):
    side = "LONG" if direction == "long" else "SHORT"
    side_glyph = G["long"] if direction == "long" else G["short"]

    if p_master >= PHI_CB:
        leverage, sizing, tier = "8x", "10%", "phi^3 (alta conviccion)"
    elif p_master >= PHI_SQ:
        leverage, sizing, tier = "5x", "5%",  "phi^2 (standard)"
    else:
        leverage, sizing, tier = "3x", "2%",  "phi (scalp)"

    # Asia penalty warning
    asia_warn = ""
    if w_clock <= 0.50:
        asia_warn = "\n{} ASIA W={:.2f} - Reducir size un 50%".format(G["warn"], w_clock)
        if leverage == "8x": leverage = "5x"
        elif leverage == "5x": leverage = "3x"

    masas_text = "\n".join([
        "  {} {}: ${:.2f}  (w={:.1f})".format(G["bullet"], m["name"], m["price"], m["weight"])
        for m in masses["masses"][:5]
    ])

    intra_note = "\n{} INTRA-VELA - confirmar al cierre 15m".format(G["warn"]) if intra else ""

    risk_pct_val = (levels["risk"] / levels["entry"] * 100) if levels.get("entry") else 0
    if risk_pct_val < 1.0:    risk_lbl = "Bajo"
    elif risk_pct_val < 2.0:  risk_lbl = "Medio"
    else:                     risk_lbl = "Alto"

    rule = "━" * 30
    intra_note = "\n  Confirmar al cierre 15m" if intra else ""

    msg = (
        "{rule}\n"
        "  ▰ Senal FQ · SOL/USDT\n"
        "  {when}{intra}\n"
        "{rule}\n"
        "  {arrow} {side}        Conviccion {tier}\n"
        "\n"
        "  ▸ Entry    ${entry:.2f}\n"
        "  ▸ Stop     ${sl:.2f}    Riesgo {risk}\n"
        "\n"
        "  ▸ TP1  30%   ${tp1:.2f}    R {rr1:.2f}\n"
        "  ▸ TP2  30%   ${tp2:.2f}    R {rr2:.2f}\n"
        "  ▸ TP3  25%   ${tp3:.2f}    R {rr3:.2f}\n"
        "  ▸ TP4  15%   ${tp4:.2f}    R {rr4:.2f}\n"
        "{rule}\n"
        "  Leverage {lev}   Size {size}\n"
        "  SL inmutable.\n"
        "{rule}\n"
        "  #FQ #SOLUSDT #{tag}"
    ).format(
        rule=rule, intra=intra_note, arrow=side_glyph, side=side, tier=tier,
        when=cdmx_now_str(),
        entry=levels["entry"], sl=levels["sl"], risk=risk_lbl,
        tp1=levels["tp1"], rr1=levels["rr_tp1"],
        tp2=levels["tp2"], rr2=levels["rr_tp2"],
        tp3=levels["tp3"], rr3=levels["rr_tp3"],
        tp4=levels["tp4"], rr4=levels["rr_tp4"],
        lev=leverage, size=sizing, tag=side,
    )
    return msg

# ============================================================
# COMMAND: /help (tier-aware via vip_format)
# ============================================================
def _resolve_tier(chat_id=None):
    """Devuelve 'admin','vip','trial','free' segun chat_id"""
    if chat_id and str(chat_id) == str(TELEGRAM_CHAT_ID):
        return "admin"
    if VIP_ENABLED and chat_id:
        try:
            u = vip.get_or_create_user(chat_id)
            t = u.get("tier", "free")
            return t if t in ("admin","vip","trial","free") else "free"
        except Exception:
            return "free"
    return "free"

def cmd_help(chat_id=None):
    if VIP_FORMAT_AVAILABLE:
        return vip_format.help_for_tier(_resolve_tier(chat_id))
    # Fallback legacy
    return "/status /lectura /miestado /renovar /about /help"

# ============================================================
# COMMAND: /about (tier-aware via vip_format)
# ============================================================
def cmd_about(chat_id=None):
    if VIP_FORMAT_AVAILABLE:
        return vip_format.about_for_tier(_resolve_tier(chat_id))
    return "FQ - senales SOL/USDT con disciplina sistematica."

# ============================================================
# COMMAND: /status
# ============================================================
def cmd_status(exchange):
    session, w, rem, next_s = get_session()
    try:
        ticker = exchange.fetch_ticker(SYMBOL)
        sol_px  = float(ticker.get("last") or 0)
        sol_chg = float(ticker.get("percentage") or 0)
        with STATE.lock:
            STATE.last_sol_price = sol_px
    except Exception as e:
        log.warning("Ticker fetch error: {}".format(e))
        sol_px = STATE.last_sol_price
        sol_chg = 0

    up_delta = datetime.now(timezone.utc) - STATE.start_time
    up_h = int(up_delta.total_seconds() // 3600)
    up_m = int((up_delta.total_seconds() % 3600) // 60)

    if STATE.last_signal_ts:
        delta = datetime.now(timezone.utc) - STATE.last_signal_ts
        h = int(delta.total_seconds() // 3600)
        m = int((delta.total_seconds() % 3600) // 60)
        ult = "Hace {}h {}m  |  {} @ ${:.2f}".format(
            h, m, (STATE.last_signal_dir or "").upper(), STATE.last_signal_price)
    else:
        ult = "Ninguna aun"

    macro_ok = (abs(STATE.last_btc_chg) > MACRO_THRESHOLD_PCT * 100 and
                abs(STATE.last_eth_chg) > MACRO_THRESHOLD_PCT * 100)

    return (
        "<b>STATUS - FQ</b>\n"
        "{fence}\n\n"
        "{when}\n"
        "Uptime: {h}h {m}m  |  Exchange: OKX live\n\n"
        "<b>MERCADO</b>\n"
        "SOL/USDT:  <b>${px:.2f}</b>  ({chg:+.2f}%)\n"
        "BTC 15m:   {btc:+.2f}%\n"
        "ETH 15m:   {eth:+.2f}%\n\n"
        "<b>SESION</b>\n"
        "Activa:    <b>{ses}</b>  (W={w:.2f})\n"
        "Cambio en: {rem} min {arrow} {nxt}\n\n"
        "<b>SENALES</b>\n"
        "Hoy:       {st}\n"
        "Total:     {stt}\n"
        "Ultima:    {ult}\n\n"
        "<b>DECOHERENCIA</b>\n"
        "Gate macro: <b>{gate}</b>\n"
        "Ultima eval: {evr}\n\n"
        "Ventana operativa: 24H\n\n"
        "#FQ #Status"
    ).format(
        fence=G["fence"],
        when=cdmx_now_str(), h=up_h, m=up_m,
        px=sol_px, chg=sol_chg,
        btc=STATE.last_btc_chg, eth=STATE.last_eth_chg,
        ses=session.upper(), w=w, rem=rem, nxt=next_s.upper(),
        arrow=G["arrow"],
        st=STATE.signals_today, stt=STATE.signals_total, ult=ult,
        gate="DECOHERENTE" if macro_ok else "EN SUPERPOSICION",
        evr=STATE.last_eval_result,
    )

# ============================================================
# COMMAND: /sesion - REESCRITO COMPLETO
# ============================================================
def cmd_sesion():
    session, w_clock, rem, next_s = get_session()
    quality = session_quality_label(w_clock)
    now = cdmx_now()

    # Tabla de sesiones con marker en activa
    sesiones = [
        ("asia",    "15:00 - 02:00", "0.50", "Asia / Tokio - Liquidez baja, mechas falsas comunes"),
        ("london",  "02:00 - 07:30", "0.80", "Apertura europea - Volatilidad creciente"),
        ("overlap", "07:30 - 10:00", "1.20", "London/NY OVERLAP - Maxima energia del dia"),
        ("ny",      "10:00 - 15:00", "1.00", "NY pura - Tendencia y continuacion"),
    ]

    lineas = []
    for nombre, horario, w, desc in sesiones:
        if nombre == session:
            marker = "{} ".format(G["arrow"])
            wrap_open, wrap_close = "<b>", "</b>"
        else:
            marker = "  "
            wrap_open, wrap_close = "", ""
        lineas.append(
            "{m}{o}{n}{c}  W={w}\n   {h}\n   {d}".format(
                m=marker, o=wrap_open, n=nombre.upper(), c=wrap_close,
                w=w, h=horario, d=desc
            )
        )

    # Notas operativas segun sesion
    if session == "overlap":
        nota = (
            "{ok} Maxima energia. Setups con mejor seguimiento.\n"
            "{ok} P_master se multiplica por 1.20.\n"
            "{ok} Ventana ideal para size completo (phi^3 = 8x permitido)."
        ).format(ok=G["ok"])
    elif session == "ny":
        nota = (
            "{ok} Sesion limpia, tendencias claras.\n"
            "{ok} P_master normal (W=1.00).\n"
            "{warn} Cuidado con reversion en ultima hora (14:00-15:00)."
        ).format(ok=G["ok"], warn=G["warn"])
    elif session == "london":
        nota = (
            "{ok} Apertura europea, volatilidad creciente.\n"
            "{warn} Esperar confirmacion antes de entrada.\n"
            "{warn} Falsos breakouts comunes en primera hora."
        ).format(ok=G["ok"], warn=G["warn"])
    else:  # asia
        nota = (
            "{warn} Sesion baja energia. P_master {x} 0.50.\n"
            "{warn} Operar con sizing reducido al 50%.\n"
            "{warn} Mechas falsas frecuentes sobre niveles BB.\n"
            "{warn} Solo entradas con confluencia muy alta."
        ).format(warn=G["warn"], x="*")

    # Calcular impacto del W_clock en P_master
    p_min_efectivo = PMASTER_MIN / w_clock if w_clock > 0 else 999
    impacto = (
        "P_master minimo ajustado por sesion: {:.2f}\n"
        "(P_master base / W_clock = {:.2f} / {:.2f})"
    ).format(p_min_efectivo, PMASTER_MIN, w_clock)

    return (
        "<b>SESION ACTIVA - FQ</b>\n"
        "{fence}\n\n"
        "{when}\n\n"
        "Sesion:     <b>{ses}</b>\n"
        "W_clock:    <b>{w:.2f}</b>\n"
        "Calidad:    <b>{q}</b>\n"
        "Cambia en:  {rem} min {arrow} {nxt}\n\n"
        "{thin}\n"
        "  CALENDARIO COMPLETO (CDMX)\n"
        "{thin}\n\n"
        "{lst}\n\n"
        "{thin}\n"
        "  NOTAS OPERATIVAS\n"
        "{thin}\n"
        "{nota}\n\n"
        "{thin}\n"
        "  IMPACTO EN P_MASTER\n"
        "{thin}\n"
        "{imp}\n\n"
        "El W_clock modula la senal, no la bloquea.\n"
        "Bot operativo 24H en ventana abierta.\n\n"
        "#FQ #Sesion"
    ).format(
        fence=G["fence"], thin=G["thin"],
        when=cdmx_now_str(),
        ses=session.upper(), w=w_clock, q=quality,
        rem=rem, nxt=next_s.upper(), arrow=G["arrow"],
        lst="\n\n".join(lineas),
        nota=nota, imp=impacto,
    )

# ============================================================
# COMMAND: /macro
# ============================================================
def cmd_macro(exchange):
    macro = test_macro(exchange)
    direction = macro.get("direction") or "neutral"

    if macro["passed"]:
        gate = "DECOHERENTE - direccion {}".format(direction.upper())
        gate_glyph = G["ok"]
    else:
        gate = "EN SUPERPOSICION"
        gate_glyph = G["fail"]

    btc_dir = "ALCISTA" if macro["btc_change"] > 0 else "BAJISTA"
    eth_dir = "ALCISTA" if macro["eth_change"] > 0 else "BAJISTA"
    needed = MACRO_THRESHOLD_PCT * 100

    if macro["passed"]:
        analisis = (
            "Macro permite entrada en direccion {}.\n"
            "BTC y ETH alineados moviendose juntos.\n"
            "Falta verificar tecnica y liquidez."
        ).format(direction.upper())
    else:
        if abs(macro["btc_change"]) < needed and abs(macro["eth_change"]) < needed:
            analisis = "Mercado lateral. Ningun activo supera threshold.\nEsperar movimiento direccional claro."
        elif (macro["btc_change"] > 0 and macro["eth_change"] < 0) or (macro["btc_change"] < 0 and macro["eth_change"] > 0):
            analisis = "BTC y ETH en direcciones opuestas.\nNo hay conviccion macro consistente."
        else:
            analisis = "Movimiento existe pero por debajo del threshold.\nMercado debil, esperar fuerza."

    return (
        "<b>MACRO DECOHERENCE - BTC/ETH</b>\n"
        "{fence}\n\n"
        "{when}\n\n"
        "{thin}\n"
        "  MOVIMIENTO 15m (vs hace 1h)\n"
        "{thin}\n"
        "BTC:  <b>{btc:+.2f}%</b>  ({btc_d})\n"
        "ETH:  <b>{eth:+.2f}%</b>  ({eth_d})\n\n"
        "Threshold:  +/- {th:.2f}%  (en AMBOS)\n"
        "Direccion:  misma para ambos\n\n"
        "{thin}\n"
        "  GATE\n"
        "{thin}\n"
        "{gg} <b>{gate}</b>\n\n"
        "{ana}\n\n"
        "#FQ #Macro"
    ).format(
        fence=G["fence"], thin=G["thin"],
        when=cdmx_now_str(),
        btc=macro["btc_change"], btc_d=btc_dir,
        eth=macro["eth_change"], eth_d=eth_dir,
        th=needed, gg=gate_glyph, gate=gate, ana=analisis,
    )

# ============================================================
# COMMAND: /pspace - DOBLE LECTURA (ejecutiva + tecnica)
# ============================================================
def cmd_pspace(exchange):
    try:
        df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
        df = add_indicators(df)
        last = df.iloc[-1]
        price = float(last["close"])
        ps = detect_pspace(df)
        bias = detect_bias(df)

        masses = ps["masses"]
        if not masses:
            masas_txt = "Sin masas detectadas en zona cercana (precio en vacio)."
        else:
            sorted_m = sorted(masses, key=lambda m: abs(price - m["price"]))
            lines = []
            for m in sorted_m[:8]:
                dist_pct = abs(price - m["price"]) / price * 100
                pos = "abajo" if m["price"] < price else ("arriba" if m["price"] > price else "exacto")
                tipo = m.get("type", "neutral")
                tipo_g = "S" if tipo == "support" else ("R" if tipo == "resistance" else "N")
                lines.append(
                    "  [{tg}] {n:<22} ${p:.2f}  {pos:>6}  {d:.2f}%  w={w:.1f}".format(
                        tg=tipo_g, n=m["name"], p=m["price"], pos=pos, d=dist_pct, w=m["weight"]
                    )
                )
            masas_txt = "\n".join(lines)

        # Curvatura kappa(p) - balance soporte/resistencia
        sw = ps["support_weight"]
        rw = ps["resistance_weight"]
        total_w = sw + rw
        if total_w > 0:
            curv_balance = (sw - rw) / total_w  # -1 a +1
        else:
            curv_balance = 0

        if curv_balance > 0.5:
            direccion_resistencia = "ALCISTA"
            interpretacion = "Soportes dominantes. Curvatura empuja precio hacia ARRIBA."
        elif curv_balance > 0.15:
            direccion_resistencia = "alcista debil"
            interpretacion = "Mas soportes que resistencias. Sesgo alcista marginal."
        elif curv_balance < -0.5:
            direccion_resistencia = "BAJISTA"
            interpretacion = "Resistencias dominantes. Curvatura empuja precio hacia ABAJO."
        elif curv_balance < -0.15:
            direccion_resistencia = "bajista debil"
            interpretacion = "Mas resistencias que soportes. Sesgo bajista marginal."
        else:
            direccion_resistencia = "EQUILIBRIO"
            interpretacion = "Soportes y resistencias balanceados. Precio en zona de batalla."

        # Resumen ejecutivo
        if len(masses) >= 4:
            densidad = "ALTA - Zona de alta gravedad ({} masas)".format(len(masses))
            tactica_exec = "Precio atrapado en confluencia. Esperar ruptura clara o rebote con volumen."
        elif len(masses) >= 2:
            densidad = "MEDIA - {} masas en zona".format(len(masses))
            tactica_exec = "Confluencia operativa. Buscar reaccion en la masa mas cercana."
        elif len(masses) == 1:
            densidad = "BAJA - Solo 1 masa"
            tactica_exec = "Insuficiente para gate P-Space. Esperar acercamiento a mas masas."
        else:
            densidad = "VACIO - Precio en P-Space libre"
            tactica_exec = "Sin estructura cercana. Movimiento libre, propenso a impulsos largos."

        # Lectura tactica masa por masa (top 3)
        tactica_lines = []
        if masses:
            sorted_m = sorted(masses, key=lambda m: abs(price - m["price"]))[:3]
            for m in sorted_m:
                dist_pct = abs(price - m["price"]) / price * 100
                if m["type"] == "support":
                    accion = "Si toca: esperar rebote con vela de rechazo + volumen.\n     Si rompe (cierre debajo): aceleracion bajista probable."
                elif m["type"] == "resistance":
                    accion = "Si toca: esperar rechazo con vela bajista + volumen.\n     Si rompe (cierre arriba): aceleracion alcista probable."
                else:
                    accion = "Zona neutral - observar reaccion del precio."
                tactica_lines.append(
                    "  {} {} (${:.2f}, {:.2f}% lejos):\n     {}".format(
                        G["bullet"], m["name"], m["price"], dist_pct, accion
                    )
                )
        tactica_text = "\n\n".join(tactica_lines) if tactica_lines else "Sin masas para evaluar."

        gate = "VALIDO ({} masas)".format(len(masses)) if len(masses) >= PSPACE_MIN_MASSES else \
               "INSUFICIENTE ({} masas, requeridas >={})".format(len(masses), PSPACE_MIN_MASSES)

        return (
            "<b>P-SPACE - CURVATURA kappa(p)</b>\n"
            "{fence}\n\n"
            "{when}\n"
            "Precio actual: <b>${px:.2f}</b>\n"
            "Sesgo estructural: {bias}\n\n"
            "{thin}\n"
            "  RESUMEN EJECUTIVO\n"
            "{thin}\n"
            "Densidad: <b>{dens}</b>\n"
            "Curvatura: <b>{cd}</b>\n"
            "  {interp}\n\n"
            "<b>Tactica:</b> {tex}\n\n"
            "{thin}\n"
            "  MASAS DETECTADAS\n"
            "{thin}\n"
            "Formato: [tipo] nombre  precio  pos  dist  peso\n"
            "Tipo: S=soporte R=resistencia N=neutral\n\n"
            "{ms}\n\n"
            "{thin}\n"
            "  LECTURA TACTICA POR MASA\n"
            "{thin}\n{tac}\n\n"
            "{thin}\n"
            "  METRICAS\n"
            "{thin}\n"
            "Peso soportes:    {sw:.2f}\n"
            "Peso resistencias: {rw:.2f}\n"
            "Balance kappa(p): {cb:+.2f}  (-1 bajista / +1 alcista)\n"
            "Tolerancia zona:  0.6% del precio\n\n"
            "Gate P-Space: <b>{g}</b>\n\n"
            "#FQ #PSpace"
        ).format(
            fence=G["fence"], thin=G["thin"],
            when=cdmx_now_str(), px=price, bias=bias["bias"].upper(),
            dens=densidad, cd=direccion_resistencia, interp=interpretacion,
            tex=tactica_exec, ms=masas_txt, tac=tactica_text,
            sw=sw, rw=rw, cb=curv_balance, g=gate,
        )
    except Exception as e:
        log.error("Error pspace: {}\n{}".format(e, traceback.format_exc()))
        return "Error al calcular P-Space: {}".format(e)

# ============================================================
# COMMAND: /niveles - PLANES DE ENTRADA CONTEXTUALES
# ============================================================
def cmd_niveles(exchange):
    try:
        df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
        df = add_indicators(df)
        last = df.iloc[-1]
        price = float(last["close"])

        bias = detect_bias(df)
        ps = detect_pspace(df)

        # Determinar direccion sugerida basada en bias
        if "alcista" in bias["bias"]:
            direction_main = "long"
        elif "bajista" in bias["bias"]:
            direction_main = "short"
        else:
            direction_main = "long"  # default neutral

        levels_long  = calculate_levels(df, "long")
        levels_short = calculate_levels(df, "short")

        plan_long  = build_trigger_plan(df, "long",  ps, bias)
        plan_short = build_trigger_plan(df, "short", ps, bias)

        bias_str = bias["bias"].upper()
        if direction_main == "long":
            primary_label = "LONG (sugerido por bias)"
            secondary_label = "SHORT (contraria, plan defensivo)"
            primary_plan = plan_long
            secondary_plan = plan_short
            primary_lvl = levels_long
            secondary_lvl = levels_short
            primary_tag = "LONG"
            secondary_tag = "SHORT"
        else:
            primary_label = "SHORT (sugerido por bias)"
            secondary_label = "LONG (contraria, plan defensivo)"
            primary_plan = plan_short
            secondary_plan = plan_long
            primary_lvl = levels_short
            secondary_lvl = levels_long
            primary_tag = "SHORT"
            secondary_tag = "LONG"

        return (
            "<b>NIVELES + TRIGGERS - FQ</b>\n"
            "{fence}\n\n"
            "{when}\n"
            "Precio: <b>${px:.2f}</b>\n"
            "Sesgo estructural: <b>{bias}</b>  (score {sc:+d})\n"
            "Momentum 5v: {m5:+.2f}%  |  20v: {m20:+.2f}%\n\n"
            "{thin}\n"
            "  PLAN PRIMARIO {plab}\n"
            "{thin}\n"
            "<b>Modo: {mode}</b>\n\n"
            "<b>Zona de entrada:</b>\n  {zone}\n\n"
            "<b>Trigger:</b>\n  {trg}\n\n"
            "<b>Confirmacion:</b>\n  {cnf}\n\n"
            "<b>Niveles si entras:</b>\n"
            "  Entry:  ${e:.2f}\n"
            "  SL:     ${sl:.2f}  ({rp:.2f}%)\n"
            "  TP1:    ${t1:.2f}  R:R {r1:.2f}\n"
            "  TP2:    ${t2:.2f}  R:R {r2:.2f}\n"
            "  TP3 {div}: ${t3:.2f}  R:R {r3:.2f}\n"
            "  TP4:    ${t4:.2f}  R:R {r4:.2f}\n\n"
            "<b>Invalidacion:</b>\n  {inv}\n\n"
            "<b>Plan B:</b>\n  {pb}\n\n"
            "{thin}\n"
            "  PLAN SECUNDARIO {slab}\n"
            "{thin}\n"
            "<b>Modo: {mode2}</b>\n\n"
            "<b>Zona:</b> {zone2}\n"
            "<b>Trigger:</b> {trg2}\n\n"
            "<b>Niveles:</b>\n"
            "  Entry:  ${e2:.2f}  |  SL: ${sl2:.2f}\n"
            "  TP1:    ${t12:.2f}  ({r12:.2f}R)\n"
            "  TP3 {div}: ${t32:.2f}  ({r32:.2f}R)\n\n"
            "{thin}\n"
            "  REGLAS DE ORO\n"
            "{thin}\n"
            "{b} Estos niveles NO son senal hasta gate Theta(D) = 1\n"
            "{b} El trigger es la condicion minima de entrada\n"
            "{b} La confirmacion DEBE cumplirse antes del click\n"
            "{b} SL nunca se mueve hacia atras (Regla 4)\n"
            "{b} Si invalida sin tocar trigger {arrow} no era setup\n\n"
            "#FQ #Niveles"
        ).format(
            fence=G["fence"], thin=G["thin"],
            when=cdmx_now_str(), px=price, bias=bias_str, sc=bias["score"],
            m5=bias["mom_5"], m20=bias["mom_20"],
            plab=primary_label, slab=secondary_label,
            mode=primary_plan["mode"], zone=primary_plan["zone"],
            trg=primary_plan["trigger"], cnf=primary_plan["confirmation"],
            inv=primary_plan["invalidation"], pb=primary_plan["plan_b"],
            e=primary_lvl["entry"], sl=primary_lvl["sl"],
            rp=(primary_lvl["risk"]/primary_lvl["entry"]*100),
            t1=primary_lvl["tp1"], r1=primary_lvl["rr_tp1"],
            t2=primary_lvl["tp2"], r2=primary_lvl["rr_tp2"],
            t3=primary_lvl["tp3"], r3=primary_lvl["rr_tp3"],
            t4=primary_lvl["tp4"], r4=primary_lvl["rr_tp4"],
            mode2=secondary_plan["mode"],
            zone2=secondary_plan["zone"][:80],
            trg2=secondary_plan["trigger"][:120],
            e2=secondary_lvl["entry"], sl2=secondary_lvl["sl"],
            t12=secondary_lvl["tp1"], r12=secondary_lvl["rr_tp1"],
            t32=secondary_lvl["tp3"], r32=secondary_lvl["rr_tp3"],
            div=G["div"], b=G["bullet"], arrow=G["arrow"],
        )
    except Exception as e:
        log.error("Error niveles: {}\n{}".format(e, traceback.format_exc()))
        return "Error al calcular niveles: {}".format(e)

# ============================================================
# PHASE E INFORMATIVO - sync_score sin Phase A-D (para /analisis)
# ============================================================
def compute_phase_e_informative(df, direction, tf_id="15m"):
    """Computa sync_score + 4 phi_* sin construir field completo. Uso
    informativo para /analisis. Devuelve dict con sync_score, tier y
    breakdown completo, o None si no se puede computar.

    Diferencia con Phase E real en fusion_engine:
    - No carga bucket_memory (phi_memory=1.0 neutral en modo informativo).
    - Usa w_clock de get_session() como proxy de w_killzone.
    - Skip regime_consistency/killzone_alignment/streak_health del sync_score
      compuesto - solo reporta tau y sus 4 componentes (es lo que Sonnet usa).
    """
    if not EMERGENT_TIME_MODULE_AVAILABLE or emergent_time is None:
        return None
    try:
        # phi_clock: w_clock como proxy de w_killzone (en alpha-blend se mezclan)
        _session, w_clock_val, _, _ = get_session()

        # phi_horizon: QTE payload
        qte_payload = None
        if QTE_AVAILABLE and qt is not None:
            try:
                qa = qt.quantum_analysis(
                    df, direction=direction,
                    ict_module=ict_smc if ICT_MODULES_AVAILABLE else None,
                    n_paths=300, run_optimizer=False,
                )
                qte_payload = emergent_time.build_qte_payload_from_quantum_analysis(qa)
            except Exception as e:
                log.warning("QTE en compute_phase_e_informative fallo: {}".format(e))

        # phi_refractory: delta desde ultima senal del TF
        last_ts = STATE.last_signal_ts_tf.get(tf_id) if hasattr(STATE, "last_signal_ts_tf") else None
        delta_min = None
        if last_ts:
            try:
                if isinstance(last_ts, (int, float)):
                    last_dt = datetime.fromtimestamp(float(last_ts), tz=timezone.utc)
                else:
                    last_dt = last_ts
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                delta_min = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60.0
            except Exception:
                delta_min = None

        # cooldown del TF profile
        cooldown_tf = TF_PROFILES.get(tf_id, {}).get(
            "PHASE_E_COOLDOWN_MIN", emergent_time.COOLDOWN_REF_MINUTES)

        # tau con bucket=None -> phi_memory=1.0 (neutral, modo informativo)
        tau_data = emergent_time.tau(
            w_killzone=w_clock_val, bucket_memory=None,
            qte_payload=qte_payload, delta_minutes=delta_min,
            cooldown_minutes=cooldown_tf,
        )

        # Sync_score informativo: solo el componente tau (peso 1.0).
        # Sin regime_consistency/killzone_alignment/streak porque no tenemos
        # field/bucket. Reportamos tau directamente como "sync informativo".
        sync_informative = tau_data["tau"]
        mods = emergent_time.sync_modulators(sync_informative)

        return {
            "sync_score":     sync_informative,
            "tier":           mods["tier"],
            "phi_clock":      tau_data["phi_clock"],
            "phi_memory":     tau_data["phi_memory"],  # 1.0 = no medido
            "phi_horizon":    tau_data["phi_horizon"],
            "phi_refractory": tau_data["phi_refractory"],
            "tau":            tau_data["tau"],
            "regime_modal":   qte_payload.get("regime_modal") if qte_payload else None,
            "coherence":      qte_payload.get("coherence") if qte_payload else None,
            "p_sl_qte":       qte_payload.get("p_sl") if qte_payload else None,
            "ev_r_qte":       qte_payload.get("ev_r") if qte_payload else None,
            "delta_min":      delta_min,
            "cooldown_min":   cooldown_tf,
            "w_clock_proxy":  w_clock_val,
        }
    except Exception as e:
        log.warning("compute_phase_e_informative error: {}".format(e))
        return None

# ============================================================
# COMMAND: /analisis
# ============================================================
def cmd_analisis(exchange):
    try:
        df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
        df = add_indicators(df)
        last = df.iloc[-1]
        session, w_clock, _, _ = get_session()

        macro = test_macro(exchange)
        direction = macro.get("direction") or "long"

        tecnica  = test_technical(df, direction)
        liquidez = test_liquidity(df, direction)
        masses   = detect_pspace(df)
        lap      = laplacian_check(df)
        bias     = detect_bias(df)

        theta_d = macro["passed"] and tecnica["passed"] and liquidez["passed"]

        # P_master estimado si pasara
        h_factor = 1.0 if lap["active"] else 0.7
        p_master_estimate = (PHI ** 1) * w_clock * h_factor * (1 + max(0, masses["count"] - 2) * 0.15)

        bb_pos = ""
        bbu, bbl = last.get("bb_upper"), last.get("bb_lower")
        if bbu is not None and not pd.isna(bbu) and bbl is not None and not pd.isna(bbl):
            if last["close"] > float(bbu):   bb_pos = "Sobre BB Upper - sobrecomprado corto"
            elif last["close"] < float(bbl): bb_pos = "Bajo BB Lower - sobrevendido corto"
            else:                            bb_pos = "Dentro de Bollinger"

        # ---- DERIVATIVES CONTEXT (funding + OI trend + L/S ratio) ----
        # Visible para RasDG en /analisis. Claude ya los ve via snapshot_for_general.
        deriv_block = ""
        try:
            funding = mctx.get_funding_rate(SYMBOL)
            oi      = mctx.get_open_interest(SYMBOL)
            oi_hist = mctx.get_oi_history(symbol=SYMBOL)
            ls      = mctx.get_long_short_ratio(symbol="SOL")

            f_line  = "Funding:   N/A"
            oi_line = "OI:        N/A"
            ls_line = "L/S ratio: N/A"

            if funding:
                f_pct = funding["current_pct"]
                f_line = "Funding:   {:+.4f}%  (next {})\n             {}".format(
                    f_pct, funding["next_time_str"],
                    mctx.funding_interpretation(f_pct))

            if oi:
                if oi_hist:
                    tr = mctx.oi_trend_analysis(oi_hist)
                    oi_line = "OI:        ${:.1f}M  ({:+.2f}% 4h)\n             {}".format(
                        oi["millions"], tr["change_pct"], tr["trend"])
                else:
                    oi_line = "OI:        ${:.1f}M".format(oi["millions"])

            if ls:
                ls_line = "L/S ratio: {:.2f}  (avg5 {:.2f})\n             {}".format(
                    ls["current"], ls["avg_5"],
                    mctx.ls_ratio_interpretation(ls["current"]))

            deriv_block = (
                "{thin}\n"
                "  MERCADO DERIVATIVOS\n"
                "{thin}\n"
                "{f}\n{o}\n{l}\n\n"
            ).format(thin=G["thin"], f=f_line, o=oi_line, l=ls_line)
        except Exception as e:
            log.warning("Derivatives block failed (non-fatal): {}".format(e))
            deriv_block = ""

        if theta_d:
            veredicto = "{} SETUP EN FORMACION - candidato real".format(G["ok"])
        else:
            veredicto = "{} SIN SETUP - mercado en superposicion".format(G["fail"])

        ico = lambda b: G["ok"] if b else G["fail"]

        # FQ v5.1: Phase E informativo (sync_score + 4 phi)
        phase_e = compute_phase_e_informative(df, direction, tf_id=TIMEFRAME)
        phase_e_block = ""
        if phase_e is not None:
            pm_str = "{:.2f}".format(phase_e["phi_memory"]) + " (informativo)" \
                if phase_e["phi_memory"] is not None else "N/A"
            refrac_line = "phi_refractory: {:.2f}".format(phase_e["phi_refractory"])
            if phase_e["delta_min"] is None:
                refrac_line += " (sin senal previa)"
            else:
                refrac_line += " (delta {:.0f}min / cooldown {:.0f}min)".format(
                    phase_e["delta_min"], phase_e["cooldown_min"])
            qte_line = ""
            if phase_e["p_sl_qte"] is not None:
                qte_line = "QTE:       P(SL)={:.0%}  EV={:+.2f}R  regimen={}\n".format(
                    phase_e["p_sl_qte"], phase_e["ev_r_qte"],
                    phase_e["regime_modal"] or "?")
            phase_e_block = (
                "{thin}\n"
                "  PHASE E - SYNC EMERGENTE tau(t)\n"
                "{thin}\n"
                "sync_score: <b>{s:.2f}</b>  tier=<b>{t}</b>\n"
                "tau:        {tau:.3f}\n"
                "phi_clock:  {pc:.2f}  (w_clock={wc:.2f})\n"
                "phi_memory: {pm}\n"
                "phi_horizon: {ph:.2f}\n"
                "{rl}\n"
                "{qte}\n"
            ).format(
                thin=G["thin"],
                s=phase_e["sync_score"], t=phase_e["tier"],
                tau=phase_e["tau"], pc=phase_e["phi_clock"], wc=phase_e["w_clock_proxy"],
                pm=pm_str, ph=phase_e["phi_horizon"],
                rl=refrac_line, qte=qte_line,
            )

        return (
            "<b>ANALISIS FQ - LIVE</b>\n"
            "{fence}\n\n"
            "{when}\n"
            "SOL/USDT:  <b>${px:.2f}</b>\n"
            "Sesion:    {ses}  (W={w:.2f})\n"
            "Sesgo:     <b>{bias}</b>  (score {sc:+d})\n\n"
            "{thin}\n"
            "  GATE Theta(D) - DECOHERENCIA 3/3\n"
            "{thin}\n"
            "{im} Macro:    BTC {bc:+.2f}% | ETH {ec:+.2f}%\n"
            "{it} Tecnica:  {ta}/{tt} indicadores\n"
            "{il} Liquidez: RSI 6/12/24 = {r6:.0f}/{r12:.0f}/{r24:.0f}\n"
            "{ip} P-Space:  {pc} masas\n"
            "{ip2} Laplaciano: ratio {lr:.2f}\n\n"
            "<b>Theta(D) = {td}</b>\n"
            "P_master estimado: {pm:.2f}  (min {pmin:.2f})\n\n"
            "{thin}\n"
            "  INDICADORES CLAVE\n"
            "{thin}\n"
            "EMA 50:    ${e50:.2f}\n"
            "EMA 200:   ${e200:.2f}\n"
            "RSI 14:    {r14:.1f}\n"
            "MACD:      {mc:.3f}  /  Signal: {ms:.3f}\n"
            "Bollinger: {bb}\n\n"
            "{deriv}"
            "{phase_e}"
            "{thin}\n"
            "  VEREDICTO MATEMATICO\n"
            "{thin}\n"
            "{ver}\n\n"
            "#FQ #Analisis"
        ).format(
            fence=G["fence"], thin=G["thin"],
            when=cdmx_now_str(), px=float(last["close"]),
            ses=session.upper(), w=w_clock, bias=bias["bias"].upper(), sc=bias["score"],
            im=ico(macro["passed"]), bc=macro["btc_change"], ec=macro["eth_change"],
            it=ico(tecnica["passed"]), ta=tecnica["aligned"], tt=tecnica["total"],
            il=ico(liquidez["passed"]),
            r6=liquidez["rsi6"], r12=liquidez["rsi12"], r24=liquidez["rsi24"],
            ip=ico(masses["passed"]), pc=masses["count"],
            ip2=G["ok"] if lap["active"] else G["fail"], lr=lap["ratio"],
            td="1 - DECOHERENTE" if theta_d else "0 - SUPERPOSICION",
            pm=p_master_estimate, pmin=PMASTER_MIN,
            e50=float(last.get("ema50") or 0), e200=float(last.get("ema200") or 0),
            r14=float(last.get("rsi14") or 0),
            mc=float(last.get("macd") or 0), ms=float(last.get("macd_signal") or 0),
            bb=bb_pos, deriv=deriv_block, phase_e=phase_e_block, ver=veredicto,
        )
    except Exception as e:
        log.error("Error analisis: {}\n{}".format(e, traceback.format_exc()))
        return "Error al analizar: {}".format(e)

# ============================================================
# EVALUATE SETUP - signal engine
# ============================================================
def evaluate_setup(exchange, tf_id="15m", intra=False):
    """Punto de entrada para evaluar un setup en un TF especifico.
    tf_id: '5m'/'15m'/'1h'. Default '15m' por compat con llamadas legacy."""
    # ============================================================
    # WEEKEND VETO - aplica a ambos flujos
    # ============================================================
    # Si WEEKEND_ADMIN_ONLY esta ON, NO cortamos la generacion en finde: dejamos
    # que el motor evalue y la senal se genere; el filtrado a admin-only ocurre
    # luego en broadcast_to_subscribers (entrega), no aqui (generacion).
    if WEEKEND_VETO_LEGACY and not WEEKEND_ADMIN_ONLY and ICT_MODULES_AVAILABLE:
        try:
            if killzones_pd.is_weekend_closed():
                wk = killzones_pd.weekend_status()
                msg = "WEEKEND VETO: mercado cerrado ({} {:.1f}UTC)".format(
                    wk["weekday_label"], wk["hour_utc"])
                STATE.last_eval_result_tf[tf_id] = msg
                STATE.last_eval_result = msg
                STATE.last_eval_diagnostic = {"stage": "weekend_veto", "reason": msg, "tf_id": tf_id}
                STATE.last_eval_diagnostic_tf[tf_id] = STATE.last_eval_diagnostic
                return False
        except Exception:
            pass

    # ============================================================
    # CIRUGIA v4.1.1: delegate a fusion_engine cuando ICT layer ON
    # ============================================================
    if ENABLE_ICT_LAYER and ICT_MODULES_AVAILABLE:
        return _evaluate_setup_v411(exchange, tf_id=tf_id, intra=intra)

    # ============================================================
    # FLUJO LEGACY (cuando flag OFF) - INTACTO
    # ============================================================
    # 24H operativo - sin restriccion de ventana
    df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
    df = add_indicators(df)
    if len(df) < 50:
        STATE.last_eval_result = "Datos insuficientes"
        return False

    with STATE.lock:
        STATE.last_sol_price = float(df["close"].iloc[-1])
        STATE.last_eval_ts   = datetime.now(timezone.utc)

    session, w_clock, _, _ = get_session()
    price = float(df["close"].iloc[-1])

    # GATE 1: MACRO (ventana deslizante)
    macro = test_macro(exchange)
    if not macro["passed"]:
        msg = "MACRO {} | BTC {:+.3f}% ETH {:+.3f}%".format(
            macro.get("diagnostic", "FAIL"),
            macro["btc_change"], macro["eth_change"])
        log.info("EVAL ${:.2f} W={:.2f} | {}".format(price, w_clock, msg))
        STATE.last_eval_result = msg
        STATE.last_eval_diagnostic = {"stage": "macro", "reason": msg, "price": price}
        return False
    direction = macro["direction"]

    # GATE 2: TECNICA
    tecnica = test_technical(df, direction)
    if not tecnica["passed"]:
        msg = "TEC FAIL {}/{} dir={}".format(tecnica["aligned"], tecnica["total"], direction)
        log.info("EVAL ${:.2f} | MACRO OK | {}".format(price, msg))
        STATE.last_eval_result = msg
        STATE.last_eval_diagnostic = {"stage": "tecnica", "reason": msg, "price": price}
        return False

    # GATE 3: LIQUIDEZ
    liquidez = test_liquidity(df, direction)
    if not liquidez["passed"]:
        msg = "LIQ FAIL RSI {:.0f}/{:.0f}/{:.0f} dir={}".format(
            liquidez["rsi6"], liquidez["rsi12"], liquidez["rsi24"], direction)
        log.info("EVAL ${:.2f} | MACRO+TEC OK | {}".format(price, msg))
        STATE.last_eval_result = msg
        STATE.last_eval_diagnostic = {"stage": "liquidez", "reason": msg, "price": price}
        return False

    # GATE 4: P-SPACE
    masses = detect_pspace(df)
    if not masses["passed"]:
        msg = "PSPACE FAIL {} masas (need>={})".format(masses["count"], PSPACE_MIN_MASSES)
        log.info("EVAL ${:.2f} | gates 1-3 OK | {}".format(price, msg))
        STATE.last_eval_result = msg
        STATE.last_eval_diagnostic = {"stage": "pspace", "reason": msg, "price": price}
        return False

    lap = laplacian_check(df)
    h_factor = 1.0 if lap["active"] else 0.7

    # P_master raw (formula original FQ v4.1)
    p_master_raw = (PHI ** 1) * w_clock * h_factor
    p_master_raw *= 1 + (masses["count"] - 2) * 0.15

    # MODULADOR ENTROPICO kappa_evo (+-15% basado en historico del bucket)
    # NO toca Theta(D). Solo afila P_master post-gate.
    tier = ev.tier_from_pmaster(p_master_raw)
    csign = ev.curvature_sign(masses.get("support_weight", 0),
                              masses.get("resistance_weight", 0))
    kappa_evo, bucket_stats = ev.compute_kappa_evo(session, tier, direction, csign)
    p_master = p_master_raw * kappa_evo

    if bucket_stats:
        log.info("kappa_evo={:.3f} bucket=({},{},{},{}) n={} WR={:.0%} Exp={:+.2f}R".format(
            kappa_evo, session, tier, direction, csign,
            bucket_stats["n"], bucket_stats["win_rate"], bucket_stats["expectancy"]))

    if p_master < PMASTER_MIN:
        msg = "P_master {:.2f}<{:.2f} (raw={:.2f} k={:.3f} W={:.2f} {})".format(
            p_master, PMASTER_MIN, p_master_raw, kappa_evo, w_clock, session)
        log.info("EVAL ${:.2f} | gates 1-4 OK | {}".format(price, msg))
        STATE.last_eval_result = msg
        STATE.last_eval_diagnostic = {
            "stage": "p_master", "reason": msg, "price": price,
            "p_master": p_master, "p_master_raw": p_master_raw,
            "kappa_evo": kappa_evo, "w_clock": w_clock, "session": session,
        }
        return False

    levels = calculate_levels(df, direction)
    # FQ v5.5: los TPs del motor clasico eran rango-Fib puro (TP2==TP3, TP4 a 1x
    # rango), sin anclaje a liquidez real -> "humo". Reanclamos TP1..TP4 a
    # estructura real (pools/OB/FVG/fib/pspace) con longitud de onda por TF,
    # MANTENIENDO el SL/entry/risk legacy intactos (no toca gates 1-4 ni el SL).
    try:
        _fd = _build_field_data_standalone(df, None, None)
        _stps = _compute_tps_v2(levels["entry"], levels["sl"], direction,
                                _fd, masses, tf=tf_id)
        if _stps:
            for _i, _t in enumerate(_stps[:4]):
                levels["tp{}".format(_i + 1)] = _t["price"]
                levels["rr_tp{}".format(_i + 1)] = _t["rr"]
            levels["tp_meta"] = _stps
    except Exception as _e:
        log.warning("TPs estructurales (evaluate_setup) fallo, uso legacy: {}".format(_e))
    if levels["rr_tp3"] < RR_MIN_TP_DIVINO:
        msg = "R:R TP divino {:.2f} < {:.2f}".format(levels["rr_tp3"], RR_MIN_TP_DIVINO)
        log.info(msg)
        STATE.last_eval_result = msg
        return False

    decoh = {"macro": macro, "tecnica": tecnica, "liquidez": liquidez}
    log.info("SENAL DISPARADA ${:.2f} {} P={:.2f} W={:.2f} intra={}".format(
        price, direction.upper(), p_master, w_clock, intra))
    STATE.last_eval_diagnostic = {"stage": "fired", "price": price, "direction": direction,
                                   "p_master": p_master, "session": session}
    msg = build_signal_msg(direction, levels, decoh, masses, session, w_clock, p_master, lap, intra)
    # MISTRAL: broadcast a todos los VIP/trial/admin activos
    bsent, bfailed = broadcast_to_subscribers(msg)
    if bsent > 0:
        log.info("SIGNAL SENT: {} P_master={:.2f} W={:.2f} intra={} | broadcast sent={} failed={}".format(
            direction.upper(), p_master, w_clock, intra, bsent, bfailed))
        with STATE.lock:
            STATE.last_signal_ts     = datetime.now(timezone.utc)
            STATE.last_signal_dir    = direction
            STATE.last_signal_price  = levels["entry"]
            STATE.last_signal_levels = levels
            STATE.signals_today     += 1
            STATE.signals_total     += 1
            STATE.last_eval_result   = "SENAL ENVIADA: {} @ ${:.2f}".format(
                direction.upper(), levels["entry"])

        # REGISTRO EN LEDGER EVOLUTIVO
        try:
            ledger_data = {
                "direction":         direction,
                "entry":             levels["entry"],
                "sl":                levels["sl"],
                "tp1":               levels["tp1"],
                "tp2":               levels["tp2"],
                "tp3":               levels["tp3"],
                "tp4":               levels["tp4"],
                "p_master_raw":      p_master_raw,
                "p_master_final":    p_master,
                "kappa_evo":         kappa_evo,
                "session":           session,
                "w_clock":           w_clock,
                "pspace_count":      masses["count"],
                "support_weight":    masses.get("support_weight", 0),
                "resistance_weight": masses.get("resistance_weight", 0),
                "macro_btc":         macro["btc_change"],
                "macro_eth":         macro["eth_change"],
                "rsi6":              liquidez["rsi6"],
                "rsi12":             liquidez["rsi12"],
                "rsi24":             liquidez["rsi24"],
                "h_lap_active":      1 if lap["active"] else 0,
                "snapshot": {
                    "decoh_summary": {
                        "macro": {k: v for k, v in macro.items() if k != "passed"},
                        "tecnica_aligned": tecnica.get("aligned"),
                    },
                    "masses_count": masses["count"],
                    "levels": levels,
                    "intra": intra,
                },
            }
            sid = ev.log_signal(ledger_data)
            if sid and bucket_stats:
                ev.log_evolution_event(
                    ev.make_bucket_key(session, tier, direction, csign),
                    bucket_stats["n"], bucket_stats["win_rate"],
                    bucket_stats["expectancy"], kappa_evo,
                )
        except Exception as e:
            log.error("Ledger write error: {}".format(e))

        # OPUS CO-PILOT para senales de alta conviccion (P_master >= phi^3)
        if claude_ai.is_available() and claude_ai.is_high_conviction(p_master):
            try:
                log.info("Triggering Opus co-pilot for high-conviction signal")
                broadcast_to_subscribers(
                    "<b>Senal de alta conviccion detectada</b>\n"
                    "Activando co-pilot Opus 4.6 para revision final..."
                )
                signal_data = {
                    "direction":    direction,
                    "p_master":     p_master,
                    "session":      session,
                    "w_clock":      w_clock,
                    "entry":        levels["entry"],
                    "sl":           levels["sl"],
                    "tp1":          levels["tp1"],
                    "tp2":          levels["tp2"],
                    "tp3":          levels["tp3"],
                    "tp4":          levels["tp4"],
                    "rr_tp1":       levels["rr_tp1"],
                    "rr_tp2":       levels["rr_tp2"],
                    "rr_tp3":       levels["rr_tp3"],
                    "rr_tp4":       levels["rr_tp4"],
                    "risk_pct":     (levels["risk"] / levels["entry"] * 100),
                    "pspace_count": masses["count"],
                    "price":        levels["entry"],
                }
                snapshot = mctx.snapshot_for_signal(df, signal_data, decoh)
                opus_reading = _escape_claude(claude_ai.signal_copilot(snapshot))
                if opus_reading:
                    opus_msg = (
                        "<b>OPUS 4.6 - REVISION FINAL DE SENAL</b>\n"
                        "{thin}\n\n{r}\n\n"
                        "{thin}\nDecision final: SIEMPRE tuya.\n"
                        "El gate matematico ya valido el setup.\n"
                        "Esta lectura es para AFINAR, no validar.\n\n"
                        "#FQ #Opus #SenalAltaConviccion"
                    ).format(thin=G["thin"], r=opus_reading)
                    # Split si es muy largo
                    parts = split_telegram_message(opus_msg)
                    for p in parts:
                        broadcast_to_subscribers(p)
            except Exception as e:
                log.error("Opus co-pilot error: {}\n{}".format(e, traceback.format_exc()))

        return True
    return False

# ============================================================
# F2 — Gate ORO de retrieval en PAPEL (admin-only; default OFF)
# ============================================================
# Por vela del TF primario clasifica el estado con el gate de retrieval (F2) y,
# si es ORO, abre en PAPEL (sella en el HashLedger que audita el Reconciler) y
# avisa SOLO al admin. SIN broadcast a VIP. Se activa con FQ_GOLD_LIVE=1 + un
# artefacto en FQ_RETRIEVAL_DIR. Todo en try/except: jamas rompe el loop de eval.
GOLD_LIVE_ENABLED = os.environ.get("FQ_GOLD_LIVE", "0").strip() in ("1", "true", "yes")
GOLD_LIVE_SYMBOL  = os.environ.get("FQ_GOLD_SYMBOL", "SOL/USDT")
GOLD_LIVE_TF      = os.environ.get("FQ_GOLD_TF", "5m")
_GOLD_RUNTIME = None
_GOLD_RUNTIME_TRIED = False


def _gold_admin_notify(sig, verdict, pos):
    """Aviso admin-only del gate ORO en paper. Tres tipos: senal ORO sellada
    (sig!=None), alerta de cobertura, y digest periodico (sig=None)."""
    try:
        if sig is None:
            v = verdict if isinstance(verdict, dict) else {}
            if v.get("alert"):
                msg = "⚠️ <b>Gold gate</b>: {} (faltan: {})".format(
                    v["alert"], ", ".join(v.get("missing", [])))
            elif "digest" in v:
                c = v["digest"]
                msg = ("📊 <b>Gold paper</b> ({tk} velas) — ORO {g} · BASE {b} · "
                       "ABSTAIN {a} · abiertas {o}").format(
                           tk=v.get("ticks", "?"), g=c.get("gold", 0),
                           b=c.get("base", 0), a=c.get("abstain", 0),
                           o=v.get("open", 0))
            else:
                return
            broadcast_to_subscribers(msg, tiers=["admin"])
            return
        d = "LONG" if sig["direction"] > 0 else "SHORT"
        exp = verdict.get("expectancy_r")
        msg = ("🥇 <b>ORO (paper)</b> {sym} {d}\n"
               "entry {e:.4f} · SL {s:.4f} · TP1 {t:.4f}\n"
               "vecindario exp≈{x} · n={n} · pid={pid}\n"
               "<i>Solo registro forward (0% real).</i>").format(
                   sym=GOLD_LIVE_SYMBOL, d=d, e=sig["entry"], s=sig["stop"],
                   t=sig["tp"], x=("%.3fR" % exp) if exp is not None else "?",
                   n=verdict.get("n_in_radius", "?"), pid=pos.pid)
        broadcast_to_subscribers(msg, tiers=["admin"])
    except Exception as e:
        log.warning("[gold] notify admin: %s", e)


def _gold_runtime():
    """Lazy-init del runtime paper (una vez). None si no se puede armar."""
    global _GOLD_RUNTIME, _GOLD_RUNTIME_TRIED
    if _GOLD_RUNTIME is not None or _GOLD_RUNTIME_TRIED:
        return _GOLD_RUNTIME
    _GOLD_RUNTIME_TRIED = True
    try:
        import gold_paper
        _GOLD_RUNTIME = gold_paper.GoldPaperRuntime.from_env(
            GOLD_LIVE_SYMBOL, calculate_levels_fn=calculate_levels,
            notify_fn=_gold_admin_notify)
        log.info("[gold] runtime paper ORO activo (%s, dir=%s)",
                 GOLD_LIVE_SYMBOL, os.environ.get("FQ_RETRIEVAL_DIR"))
    except Exception as e:
        log.warning("[gold] no se pudo armar el runtime paper: %s", e)
        _GOLD_RUNTIME = None
    return _GOLD_RUNTIME


def _gold_paper_eval(field, report, df_primary, price, tf_id):
    """Hook por vela: corre el gate ORO en paper en el TF primario. No-op si
    FQ_GOLD_LIVE!=1. Nunca rompe el loop (todo en try/except)."""
    if not GOLD_LIVE_ENABLED or tf_id != GOLD_LIVE_TF:
        return
    rt = _gold_runtime()
    if rt is None:
        return
    try:
        hi = float(df_primary["high"].iloc[-1])
        lo = float(df_primary["low"].iloc[-1])
        rt.on_bar(field, report, df_primary, price, high=hi, low=lo,
                  ts=datetime.now(timezone.utc))
    except Exception as e:
        log.warning("[gold] on_bar: %s", e)


# ============================================================
# v4.1.1 — _evaluate_setup_v411 (delegate al fusion_engine)
# ============================================================
def _evaluate_setup_v411(exchange, tf_id="15m", intra=False):
    """
    Flujo v4.1.1 multi-TF: construye FieldState multi-TF y delega a fusion_engine.

    tf_id: timeframe primario ("5m" / "15m" / "1h"). Determina el perfil de
    cooldown, intra-vela, volumen y P_master, y los TFs de contexto.

    El motor matematico (P_master = phi*W*H_lap*...) se mantiene INTACTO,
    pero ahora vive dentro de fusion_engine.evaluate_signal y opera POST
    cuatro fases A/B/C/D (sesgo, liquidez, confluencia, killzone+CRT+memoria).
    """
    profile = TF_PROFILES[tf_id]
    tf_label = profile["label"]
    tf_pmin = profile["PMASTER_MIN"]
    ctx_mid = profile["context_mid"]
    ctx_high = profile["context_high"]
    sub_tf = profile["sub_tf"]
    # FQ v5.2: RR_MIN_TP3 puede ser por-TF (3m=1.50 para intradia corto).
    # Si el perfil no lo trae, cae al global RR_MIN_TP_DIVINO=1.8.
    tf_rr_min = profile.get("RR_MIN_TP3", RR_MIN_TP_DIVINO)
    try:
        # 1. Fetch multi-TF segun perfil
        df_primary = fetch_ohlcv(exchange, SYMBOL, tf_id, limit=200)
        df_primary = add_indicators(df_primary)
        if len(df_primary) < 50:
            msg = "Datos insuficientes {}".format(tf_id)
            STATE.last_eval_result_tf[tf_id] = msg
            STATE.last_eval_result = msg
            return False
        df_ctx_mid = fetch_ohlcv(exchange, SYMBOL, ctx_mid, limit=100)
        df_ctx_mid = add_indicators(df_ctx_mid)
        df_ctx_high = fetch_ohlcv(exchange, SYMBOL, ctx_high, limit=100)
        df_ctx_high = add_indicators(df_ctx_high)
        try:
            df_sub = fetch_ohlcv(exchange, SYMBOL, sub_tf, limit=30)
            df_sub = add_indicators(df_sub)
        except Exception:
            df_sub = None  # sub-TF es opcional para CRT

        price = float(df_primary["close"].iloc[-1])
        with STATE.lock:
            STATE.last_sol_price = price
            now = datetime.now(timezone.utc)
            STATE.last_eval_ts_tf[tf_id] = now
            STATE.last_eval_ts = now

        # 2. Config a fusion_engine (incluye tf_id para bucket keys y PMASTER por TF)
        # LAST_SIGNAL_TS + PHASE_E_* alimentan Phase E (FQ v5.1) calibrado por TF
        config = {
            "PHI":              PHI,
            "PMASTER_MIN":      tf_pmin,
            "RR_MIN_TP_DIVINO": tf_rr_min,  # FQ v5.2: por-TF (3m corre con 1.50)
            "TF_ID":            tf_id,
            "TF_LABEL":         tf_label,
            "PULLBACK_VOL_MULT": profile["PULLBACK_VOL_MULT"],
            "BREAKOUT_VOL_MULT": profile["BREAKOUT_VOL_MULT"],
            "LAST_SIGNAL_TS":   STATE.last_signal_ts_tf.get(tf_id),
            "PHASE_E_N_PATHS":  profile.get("PHASE_E_N_PATHS"),
            "PHASE_E_COOLDOWN_MIN": profile.get("PHASE_E_COOLDOWN_MIN"),
        }

        # 3. Delegate principal. Pasamos primary/ctx_mid/ctx_high/sub manteniendo
        # los nombres posicionales df_15m, df_1h, df_4h, df_1m por compat con
        # fusion_engine que opera sobre estos roles, independiente del TF concreto.
        fire, field, report = fusion_engine.evaluate_signal(
            df_primary, df_ctx_mid, df_ctx_high, df_sub,
            detect_pspace, laplacian_check, calculate_levels,
            config, intra=intra
        )

        # 4. Logging unificado por TF
        decision = report.get("decision", "?")
        log.info("EVAL v4.1.1 [{}/{}] ${:.2f} | {} | {}".format(
            tf_label, tf_id, price, decision.upper(), field.summary_line()))
        diag = {
            "stage":  decision,
            "reason": report.get("reason", ""),
            "price":  price,
            "tf_id":  tf_id,
            "tf_label": tf_label,
            "field_summary": field.summary_line(),
            "decision_report": {k: v for k, v in report.items()
                                if k not in ("masses", "lap")},
        }
        STATE.last_eval_diagnostic_tf[tf_id] = diag
        STATE.last_eval_diagnostic = diag

        # F2: gate ORO de retrieval en PAPEL (admin-only; no-op si FQ_GOLD_LIVE!=1)
        _gold_paper_eval(field, report, df_primary, price, tf_id)

        # 4B. Gate QTE LEGACY (post-fire). Si Phase E (FQ v5.1) esta activo,
        # el QTE ya fue procesado pre-fusion como input al P_master con sync gate,
        # asi que el gate legacy se salta para no doble-vetar la misma senal.
        # Flag OFF -> comportamiento v5.0 exacto (legacy gate corre).
        _phase_e_active = getattr(fusion_engine, "EMERGENT_TIME_ENABLED", False)
        if fire and QTE_GATE_ENABLED and QTE_AVAILABLE and qt is not None \
           and not _phase_e_active:
            try:
                levels_q = report.get("levels", {})
                direction_q = report.get("direction")
                if levels_q and direction_q:
                    qte_levels_in = {
                        "entry": levels_q["entry"], "sl": levels_q["sl"],
                        "tp1":   levels_q["tp1"],   "tp2": levels_q["tp2"],
                        "tp3":   levels_q["tp3"],
                    }
                    qa_gate = qt.quantum_analysis(
                        df_primary, direction=direction_q, levels=qte_levels_in,
                        ict_module=ict_smc if ICT_MODULES_AVAILABLE else None,
                        n_paths=500, run_optimizer=False,
                    )
                    p_sl_q = float(qa_gate["probabilities"].get("p_sl", 0.0))
                    ev_q   = float(qa_gate["probabilities"].get("expected_R", 0.0))
                    if p_sl_q > QTE_GATE_MAX_P_SL or ev_q < QTE_GATE_MIN_EV:
                        reason = "QTE veto: P(SL)={:.2f} max={:.2f} | EV={:.2f} min={:.2f}".format(
                            p_sl_q, QTE_GATE_MAX_P_SL, ev_q, QTE_GATE_MIN_EV)
                        log.warning("[{}/{}] {} - senal rechazada".format(tf_label, tf_id, reason))
                        STATE.last_eval_result_tf[tf_id] = "QTE-VETO [{}] P_SL={:.2f} EV={:.2f}".format(
                            tf_id, p_sl_q, ev_q)
                        STATE.last_eval_result = STATE.last_eval_result_tf[tf_id]
                        fire = False
            except Exception as qte_e:
                log.warning("QTE gate error [{}]: {}".format(tf_id, qte_e))

        # 5. Disparo (los reportes-campo automaticos estan apagados; /campo sigue manual)
        if fire:
            # SENAL ALINEADA — formato unico LIMPIO para admin y VIP (peticion
            # RasDG, jun-2026): encabezado iconico "🎯 Senal FQ VIP" + insignia
            # de CALIDAD, sin la jerga/matematica del reporte tecnico. El
            # FieldState completo se sigue persistiendo en el ledger (paso 6),
            # asi que el detalle tecnico no se pierde. Fallback al reporte Capa 5
            # si vip_format no esta disponible.
            if VIP_FORMAT_AVAILABLE and vip_format is not None:
                msg = vip_format.build_vip_signal(
                    field, report, tf_label=tf_label, tf_id=tf_id)
            else:
                msg = field_reports.build_signal_report(
                    field, report, tf_label=tf_label, tf_id=tf_id, pmin=tf_pmin)
            bsent, _ = broadcast_to_subscribers(msg)
            if bsent > 0:
                pm_data = report["p_master_data"]
                levels = report["levels"]
                direction = report["direction"]
                with STATE.lock:
                    now = datetime.now(timezone.utc)
                    # Per-TF (cooldown independiente por TF)
                    STATE.last_signal_ts_tf[tf_id]     = now
                    STATE.last_signal_dir_tf[tf_id]    = direction
                    STATE.last_signal_price_tf[tf_id]  = levels["entry"]
                    STATE.last_signal_levels_tf[tf_id] = levels
                    STATE.last_score_result_tf[tf_id]  = report.get("score")
                    STATE.last_regime_tf[tf_id]        = report.get("regime")
                    STATE.last_eval_result_tf[tf_id]   = "SENAL [{}]: {} @ ${:.2f} P={:.2f}".format(
                        tf_id, direction.upper(), levels["entry"], pm_data["p_master"])
                    # Singular: refleja la senal mas reciente cross-TF
                    STATE.last_signal_ts     = now
                    STATE.last_signal_dir    = direction
                    STATE.last_signal_price  = levels["entry"]
                    STATE.last_signal_levels = levels
                    STATE.signals_today     += 1
                    STATE.signals_total     += 1
                    STATE.last_score_result  = report.get("score")
                    STATE.last_regime        = report.get("regime")
                    STATE.last_eval_result   = STATE.last_eval_result_tf[tf_id]

                # 6. LEDGER v2 con FieldState completo
                try:
                    ledger_data = {
                        "direction":         direction,
                        "entry":             levels["entry"],
                        "sl":                levels["sl"],
                        "tp1":               levels["tp1"],
                        "tp2":               levels["tp2"],
                        "tp3":               levels["tp3"],
                        "tp4":               levels["tp4"],
                        "p_master_raw":      pm_data["p_master_raw"],
                        "p_master_final":    pm_data["p_master"],
                        "kappa_evo":         pm_data["kappa_evo"],
                        "session":           field.killzone,  # killzone como session v2
                        "w_clock":           pm_data["w_effective"],
                        "pspace_count":      report["masses"]["count"],
                        "support_weight":    report["masses"].get("support_weight", 0),
                        "resistance_weight": report["masses"].get("resistance_weight", 0),
                        "macro_btc":         0.0,  # ya no se usa gate macro
                        "macro_eth":         0.0,
                        "rsi6":              0, "rsi12": 0, "rsi24": 0,
                        "h_lap_active":      1 if report["lap"]["active"] else 0,
                        "alpha_hybrid":      pm_data["alpha_hybrid"],
                        "tf_id":             tf_id,
                        "snapshot": {
                            "field": field.summary_line(),
                            "confluence": field.confluence_list,
                            "levels": levels,
                            "intra": intra,
                            "tf_id": tf_id,
                            "tf_label": tf_label,
                        },
                    }
                    # Prefiere log_signal_v3 (con concepts ICT) si disponible
                    if hasattr(ev, "log_signal_v3"):
                        try:
                            concepts = ict_smc.compile_concept_flags(field)
                        except Exception:
                            concepts = {}
                        weekend_flag = False
                        try:
                            weekend_flag = killzones_pd.is_weekend_closed()
                        except Exception:
                            pass
                        ledger_data["kappa_evo"] = pm_data["kappa_evo"]
                        ev.log_signal_v3(
                            ledger_data, field, concepts,
                            weekend_flag=weekend_flag,
                            kappa_method=pm_data.get("kappa_method", "thompson"),
                        )
                    elif hasattr(ev, "log_signal_v2"):
                        ev.log_signal_v2(ledger_data, field)
                    else:
                        # fallback al log legacy si patch v2 no esta aplicado
                        ev.log_signal(ledger_data)
                except Exception as e:
                    log.error("Ledger v2 write: {}".format(e))

                # 7. Opus co-pilot para alta conviccion (heredado)
                if claude_ai.is_available() and claude_ai.is_high_conviction(pm_data["p_master"]):
                    try:
                        broadcast_to_subscribers(
                            "<b>Senal alta conviccion v4.1.1</b>\n"
                            "Activando Opus 4.6 para revision final..."
                        )
                        signal_data = {
                            "direction": direction, "p_master": pm_data["p_master"],
                            "session": field.killzone, "w_clock": pm_data["w_effective"],
                            "entry": levels["entry"], "sl": levels["sl"],
                            "tp1": levels["tp1"], "tp2": levels["tp2"],
                            "tp3": levels["tp3"], "tp4": levels["tp4"],
                            "rr_tp1": levels["rr_tp1"], "rr_tp2": levels["rr_tp2"],
                            "rr_tp3": levels["rr_tp3"], "rr_tp4": levels["rr_tp4"],
                            "risk_pct": (levels["risk"] / levels["entry"] * 100),
                            "pspace_count": report["masses"]["count"], "price": levels["entry"],
                        }
                        decoh = {
                            "macro": {"btc_change": 0, "eth_change": 0},
                            "tecnica": {"aligned": field.confluence_count,
                                        "total": field.confluence_count},
                            "liquidez": {"rsi6": 0, "rsi12": 0, "rsi24": 0},
                        }
                        snapshot = mctx.snapshot_for_signal(df_primary, signal_data, decoh)
                        opus_reading = _escape_claude(claude_ai.signal_copilot(snapshot))
                        if opus_reading:
                            opus_msg = (
                                "<b>OPUS 4.6 — REVISION v4.1.1</b>\n"
                                "{thin}\n\n{r}\n\n"
                                "{thin}\nDecision final: TUYA.\n"
                                "#FQ1 #Opus"
                            ).format(thin=G["thin"], r=opus_reading)
                            for p in split_telegram_message(opus_msg):
                                broadcast_to_subscribers(p)
                    except Exception as e:
                        log.error("Opus copilot v4.1.1: {}".format(e))
                return True
            return False
        else:
            # NO HAY SENAL: silenciar. Reportes de campo automaticos quedan desactivados
            # (constante ENABLE_FIELD_REPORTS=False) - el comando manual /campo sigue vivo.
            msg = "v4.1.1 [{}] {} | {}".format(
                tf_id, decision, report.get("reason", "")[:80])
            STATE.last_eval_result_tf[tf_id] = msg
            STATE.last_eval_result = msg
            return False
    except Exception as e:
        log.error("_evaluate_setup_v411[{}]: {}\n{}".format(tf_id, e, traceback.format_exc()))
        msg = "v4.1.1 [{}] EXCEPTION: {}".format(tf_id, str(e)[:80])
        STATE.last_eval_result_tf[tf_id] = msg
        STATE.last_eval_result = msg
        return False

# ============================================================
# COMMAND: /claude - lectura tactica manual
# ============================================================
def cmd_claude(exchange):
    """Comando manual para invocar lectura tactica de Claude"""
    if not claude_ai.is_available():
        return (
            "<b>CLAUDE NO DISPONIBLE</b>\n"
            "{fence}\n\n"
            "Falta configurar ANTHROPIC_API_KEY en variables de entorno.\n"
            "O instalar: pip install anthropic\n\n"
            "Una vez configurado, /claude dara lectura tactica\n"
            "del estado del mercado interno + externo en vivo.\n\n"
            "#FQ #Setup"
        ).format(fence=G["fence"])

    try:
        df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
        df = add_indicators(df)
        last = df.iloc[-1]
        session, w_clock, _, _ = get_session()
        macro = test_macro(exchange)
        direction_test = macro.get("direction") or "long"
        tecnica = test_technical(df, direction_test)
        liquidez = test_liquidity(df, direction_test)
        masses = detect_pspace(df)
        bias = detect_bias(df)
        theta_d = macro["passed"] and tecnica["passed"] and liquidez["passed"]

        basic_state = {
            "price":        float(last["close"]),
            "session":      session,
            "w_clock":      w_clock,
            "bias":         bias["bias"],
            "bias_score":   bias["score"],
            "mom_5":        bias["mom_5"],
            "mom_20":       bias["mom_20"],
            "btc_chg":      macro["btc_change"],
            "eth_chg":      macro["eth_change"],
            "tec_aligned":  tecnica["aligned"],
            "tec_total":    tecnica["total"],
            "rsi6":         liquidez["rsi6"],
            "rsi12":        liquidez["rsi12"],
            "rsi24":        liquidez["rsi24"],
            "rsi14":        float(last.get("rsi14") or 0),
            "pspace_count": masses["count"],
            "theta_d":      theta_d,
            "ema50":        float(last.get("ema50") or 0),
            "ema200":       float(last.get("ema200") or 0),
            "macd":         float(last.get("macd") or 0),
        }

        snapshot = mctx.snapshot_for_general(df, basic_state)
        reading = _escape_claude(claude_ai.tactical_general(snapshot))

        return (
            "<b>CLAUDE - LECTURA TACTICA</b>\n"
            "{fence}\n\n"
            "{when}  |  SOL ${px:.2f}\n"
            "Sesion: {ses} (W={w:.2f}) | Sesgo: {bias}\n\n"
            "{thin}\n\n"
            "{reading}\n\n"
            "{thin}\n"
            "#FQ #Lectura"
        ).format(
            fence=G["fence"], thin=G["thin"],
            when=cdmx_now_str(), px=basic_state["price"],
            ses=session.upper(), w=w_clock, bias=bias["bias"].upper(),
            reading=reading,
        )
    except Exception as e:
        log.error("Error /claude: {}\n{}".format(e, traceback.format_exc()))
        return "Error generando lectura: {}".format(e)


# ============================================================
# COMMAND LISTENER
# ============================================================
COMMANDS = {}
CLAUDE_FOLLOWUP = {}  # comando -> funcion que produce snapshot + lectura

def split_telegram_message(text, max_length=4000):
    """Telegram limita 4096 chars. Hacemos split inteligente."""
    if len(text) <= max_length:
        return [text]
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break
        # Cortar en doble newline si es posible
        cut = text.rfind("\n\n", 0, max_length)
        if cut == -1:
            cut = text.rfind("\n", 0, max_length)
        if cut == -1:
            cut = max_length
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return parts

def send_long(text, chat_id):
    """Envia mensaje largo en partes si excede limite"""
    parts = split_telegram_message(text)
    for i, p in enumerate(parts):
        if len(parts) > 1:
            p = "({}/{})\n{}".format(i+1, len(parts), p)
        telegram_send(p, chat_id)

def claude_followup_general(exchange):
    """Genera lectura Claude para /analisis"""
    if not claude_ai.is_available():
        return None
    try:
        df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
        df = add_indicators(df)
        last = df.iloc[-1]
        session, w_clock, _, _ = get_session()
        macro = test_macro(exchange)
        direction_test = macro.get("direction") or "long"
        tecnica = test_technical(df, direction_test)
        liquidez = test_liquidity(df, direction_test)
        masses = detect_pspace(df)
        bias = detect_bias(df)
        theta_d = macro["passed"] and tecnica["passed"] and liquidez["passed"]
        basic_state = {
            "price": float(last["close"]), "session": session, "w_clock": w_clock,
            "bias": bias["bias"], "bias_score": bias["score"],
            "mom_5": bias["mom_5"], "mom_20": bias["mom_20"],
            "btc_chg": macro["btc_change"], "eth_chg": macro["eth_change"],
            "tec_aligned": tecnica["aligned"], "tec_total": tecnica["total"],
            "rsi6": liquidez["rsi6"], "rsi12": liquidez["rsi12"], "rsi24": liquidez["rsi24"],
            "rsi14": float(last.get("rsi14") or 0),
            "pspace_count": masses["count"], "theta_d": theta_d,
            "ema50": float(last.get("ema50") or 0),
            "ema200": float(last.get("ema200") or 0),
            "macd": float(last.get("macd") or 0),
        }
        snapshot = mctx.snapshot_for_general(df, basic_state)
        reading = _escape_claude(claude_ai.tactical_general(snapshot))
        return (
            "<b>CLAUDE - Lectura tactica del analisis</b>\n"
            "{thin}\n\n{r}\n\n"
            "{thin}\nModelo: Sonnet 4.5\n#FQ #Claude"
        ).format(thin=G["thin"], r=reading)
    except Exception as e:
        log.error("Claude followup analisis error: {}".format(e))
        return None

def _battle_snapshot(plan):
    """Aplana el battle plan a un dict compacto para el snapshot de Claude."""
    if not plan:
        return None
    z = plan.get("primary_zone")
    out = {
        "verdict":       plan["verdict"],
        "headline":      plan["headline"],
        "rationale":     plan["rationale"],
        "trigger":       plan.get("trigger"),
        "invalidation":  plan["invalidation"],
        "market_ev":     plan["market"]["ev"],
        "market_p_sl":   plan["market"]["p_sl"],
        "market_entry":  plan["market"]["entry"],
        "tps":           plan.get("tps"),
    }
    if z:
        out["zone"] = {
            "label": z["label"], "low": z["low"], "high": z["high"],
            "reach_prob": z["reach_prob"], "ev_cond": z["ev_cond"],
            "p_sl_cond": z["p_sl_cond"], "accumulate": z.get("accumulate"),
        }
    return out


def _extension_score(plan, qa):
    """
    FQ v5.2: estima cuanta confianza tenemos en que el precio se extienda
    mucho mas alla del TP1/TP2. Devuelve [0,1].

    Combina 3 factores:
      - coherencia QTE (que tan ordenadas estan las trayectorias simuladas)
      - dominio del regimen (cuan dominante es bull_continuation o bear_reversal)
      - EV de mercado (cuanto premio condicional hay)

    Mayor score -> TP3 puede estirarse a estructural lejano (1:6 si esta).
    Menor score -> TP3 cap conservador (~2.5R).
    """
    if not plan or not qa:
        return 0.0
    coh = float(qa.get("coherence", 0.0) or 0.0)
    regime_pct = float(plan.get("regime_pct", qa.get("dominant_regime_pct", 0.0)) or 0.0)
    ev = float((plan.get("market") or {}).get("ev", 0.0) or 0.0)

    ext = 0.0
    if coh >= 0.65:   ext += 0.4
    elif coh >= 0.50: ext += 0.2
    if regime_pct >= 0.55: ext += 0.3
    elif regime_pct >= 0.45: ext += 0.15
    if ev >= 1.5:   ext += 0.3
    elif ev >= 1.0: ext += 0.15
    return min(ext, 1.0)


def _pick_structural_in_rr_band(structural_tps, entry, sl, direction, rr_min, rr_max):
    """Elige el mejor structural TP en banda [rr_min, rr_max]. None si no hay."""
    risk = abs(entry - sl)
    if risk <= 0 or not structural_tps:
        return None
    is_long = direction == "long"
    candidates = []
    for tp in structural_tps:
        price = tp.get("price") if isinstance(tp, dict) else None
        if price is None:
            continue
        try:
            price = float(price)
        except (TypeError, ValueError):
            continue
        if is_long and price <= entry:
            continue
        if (not is_long) and price >= entry:
            continue
        rr_val = abs(price - entry) / risk
        if rr_min <= rr_val <= rr_max:
            candidates.append({"price": price, "rr": rr_val,
                                "kind": tp.get("kind", "structural")})
    if not candidates:
        return None
    # Preferir el de mayor R (deja mas espacio) si en banda alta;
    # menor R si banda baja (mas conservador). Banda media: el mas centrado.
    mid = (rr_min + rr_max) / 2
    candidates.sort(key=lambda c: abs(c["rr"] - mid))
    return candidates[0]


def _synth_tp(entry, sl, direction, rr):
    risk = abs(entry - sl)
    sign = 1.0 if direction == "long" else -1.0
    return {"price": round(entry + sign * risk * rr, 4),
            "rr": rr, "kind": "synthetic"}


def _compute_tactical_tps(direction, entry, sl, structural_tps=None, plan=None,
                          qa=None, tf=None):
    """
    FQ v5.2 TP PICKER CONTEXTUAL.

    Filosofia: TP1 siempre cercano (asegura el dia), TP2 en banda media
    (donde la practica demostro alcanzable), TP3 adaptado al contexto:
      - extension_score alto -> deja correr a estructural lejano (hasta ~6.5R)
      - extension_score medio -> cap [2.5R, 4R]
      - extension_score bajo -> cap 2.5R

    Cierres parciales fijos (40/35/25) calibrados sobre las dos ganadoras
    historicas que cerraron en TP2. Si structural_tps esta vacio o plan/qa
    son None, hace fallback a 1.0R/1.8R/2.5R.

    FQ v5.5:
      - Cap anti-sobre-extension en contexto favorable: 8.0R -> 6.5R, para que
        TP3 de maxima calidad siga llegando antes de que el momentum se evapore.
      - Longitud de onda por timeframe (`tf`): las bandas y los synth se escalan
        por _tf_wavelength_factor para que las senales de campo de 5m no
        ejecuten los 3 TPs en minutos (onda demasiado corta).

    Args:
        direction: "long"|"short"
        entry: precio de entrada
        sl: precio de stop
        structural_tps: list opcional de {"price","kind"} desde levels["tp_meta"]
        plan: dict opcional del battle_planner (regime_pct, market.ev)
        qa: dict opcional del QTE (coherence, dominant_regime_pct)
        tf: timeframe de la senal (escala la longitud de onda)

    Returns: lista de 3 dicts [{price, rr, weight_pct, kind}].
    """
    risk = abs(entry - sl)
    if risk <= 0:
        return []
    ext = _extension_score(plan, qa) if (plan or qa) else 0.0
    wf = _tf_wavelength_factor(tf)

    # TP1: 1.0R-1.5R. Prefiere estructural si esta en banda; sino synth 1.0R.
    tp1 = _pick_structural_in_rr_band(structural_tps, entry, sl, direction, 1.0 * wf, 1.5 * wf) \
        or _synth_tp(entry, sl, direction, 1.0 * wf)

    # TP2: 1.5R-2.5R. Prefiere estructural; sino synth 1.8R.
    tp2 = _pick_structural_in_rr_band(structural_tps, entry, sl, direction, 1.5 * wf, 2.5 * wf) \
        or _synth_tp(entry, sl, direction, 1.8 * wf)

    # TP3: depende de extension_score (contexto en tiempo real)
    if ext >= 0.70:
        # contexto favorable -> deja correr al estructural mas lejano operable.
        # Banda [2.5R, 6.5R]: cubre Fib 1.618 (~3-4R) y pspace targets (~5-6R)
        # sin sobre-extender. Si no hay estructural en banda, synth 3.0R.
        tp3 = _pick_structural_in_rr_band(structural_tps, entry, sl, direction, 2.5 * wf, 6.5 * wf) \
            or _synth_tp(entry, sl, direction, 3.0 * wf)
    elif ext >= 0.40:
        # contexto medio -> banda [2.5R, 4.0R]. Estructural si esta; sino 2.5R.
        tp3 = _pick_structural_in_rr_band(structural_tps, entry, sl, direction, 2.5 * wf, 4.0 * wf) \
            or _synth_tp(entry, sl, direction, 2.5 * wf)
    else:
        # contexto debil -> cap conservador a 2.5R. No regalamos R:R.
        tp3 = _synth_tp(entry, sl, direction, 2.5 * wf)

    # Garantizar orden monotono (TP2 > TP1, TP3 > TP2 en distancia R)
    tps_sorted = sorted([tp1, tp2, tp3], key=lambda t: t["rr"])
    weights = [40, 35, 25]
    out = []
    for tp, w in zip(tps_sorted, weights):
        out.append({"price": round(tp["price"], 4),
                    "rr": round(tp["rr"], 2),
                    "weight_pct": w,
                    "kind": tp.get("kind", "synthetic")})
    return out


def _should_promote_tactical_to_vip(plan, vol_data, killzone_name):
    """
    Decide si la alerta tactica se difunde al VIP (o solo al admin como antes).

    Criterios (todos AND, conservadores):
      - Volumen POR TIPO: EJECUTAR exige >= TACTICAL_VOL_MIN_EXECUTE (0.85);
        ACUMULAR solo un piso TACTICAL_VOL_MIN_ACUMULA (0.60) - la vela de zona
        es de bajo volumen por naturaleza.
      - NO estamos en franja muerta (14-15 manipulacion 2PM / 15-16 CDMX /
        viernes >=14 CDMX)
      - NO es un LONG de bajo volumen en la apertura asiatica (asia_open):
        bull-fakeout guard, ver volume_quality.asia_open_fakeout_veto.
      - El edge condicional supera umbrales decentes:
          EJECUTAR_AHORA: market.ev >= 0.70 y market.p_sl <= 0.55
          ACUMULAR:       zone.ev_cond >= 1.0 y zone.reach_prob >= 0.35
      - Flag FQ_TACTICAL_VIP_ENABLED=1
    """
    if not TACTICAL_VIP_ENABLED:
        return False, "TACTICAL_VIP flag off"

    v = plan.get("verdict")

    # Gate de volumen segun el tipo de senal (ver constantes arriba).
    vol_min = (TACTICAL_VOL_MIN_ACUMULA if v == "ACUMULAR_EN_ZONA"
               else TACTICAL_VOL_MIN_EXECUTE)
    if vol_data is not None:
        vs = vol_data.get("score", 1.0)
        if vs < vol_min:
            return False, "vol_score={:.2f}<{:.2f}".format(vs, vol_min)

    if VOLUME_QUALITY_AVAILABLE and volume_quality is not None:
        if volume_quality.is_dead_window():
            return False, "dead window: " + (
                volume_quality.dead_window_label() or "?")

        # Asia-open bull-fakeout guard (peticion RasDG, jun-2026): la apertura
        # asiatica abre con barridos alcistas en liquidez delgada. Un LONG
        # tactico de bajo volumen ahi (sobre todo ACUMULAR, que usa piso de vol
        # relajado) es la trampa que deja un FVG alcista y revierte -> SL en
        # minutos. Exige volumen genuino para promover longs en asia_open.
        vs_guard = (vol_data.get("score", 1.0) if vol_data is not None else 1.0)
        fk_veto, fk_reason = volume_quality.asia_open_fakeout_veto(
            plan.get("direction"), vs_guard, killzone_name)
        if fk_veto:
            return False, fk_reason

    mkt = plan.get("market") or {}
    if v == "EJECUTAR_AHORA":
        if (mkt.get("ev") or 0) < TACTICAL_PROMOTE_MIN_EV:
            return False, "market.ev<{:.2f}".format(TACTICAL_PROMOTE_MIN_EV)
        if (mkt.get("p_sl") or 1.0) > TACTICAL_PROMOTE_MAX_PSL:
            return False, "market.p_sl>{:.2f}".format(TACTICAL_PROMOTE_MAX_PSL)
    elif v == "ACUMULAR_EN_ZONA":
        z = plan.get("primary_zone") or {}
        if (z.get("ev_cond") or 0) < 1.0:
            return False, "zone.ev_cond<1.0"
        if (z.get("reach_prob") or 0) < 0.35:
            return False, "zone.reach_prob<0.35"
        # CLAVE (v5.3, peticion RasDG): respetar la probabilidad condicional
        # DESDE la zona. reach_prob solo dice que el precio regresa a la zona;
        # p_sl_cond dice que tan probable es palmar el SL una vez dentro. El bot
        # ya la calcula y la muestra ("Desde zona · prob. baja"), pero el gate la
        # ignoraba -> promovia ACUMULAs de baja probabilidad que terminaban en
        # SL. Mismo bar que EJECUTAR: se permite hasta "media", se corta "baja".
        if (z.get("p_sl_cond") or 1.0) > TACTICAL_PROMOTE_MAX_PSL:
            return False, "zone.p_sl_cond>{:.2f}".format(TACTICAL_PROMOTE_MAX_PSL)
    else:
        return False, "verdict not tactical-eligible"

    return True, "promote: vol+edge OK"


def radar_check(exchange, tf_id="15m"):
    """
    RADAR proactivo + ALERTA TACTICA (FQ v5.3):

    Hasta v5.1: en vela nueva 15m, si battle_planner veia setup OPERABLE
    (EJECUTAR_AHORA / ACUMULAR_EN_ZONA) avisaba SOLO al admin como
    "inteligencia anticipada, no es senal automatica".

    Desde v5.3:
      - Corre en FIELD_TIMEFRAMES (default 5m+15m; 3m retirado, 1m opt-in).
        El 5m es el canal de campo afinado; el 15m mantiene el comportamiento
        original.
      - Gate de CONVICCION: sin edge claro no emite NADA (ver
        _radar_has_conviction). Mata el ruido de baja conviccion que sangraba
        la cuenta con 3m (falsos positivos + senales encimadas).
      - Cooldown PER-TF (ver _radar_cooldown_for) con anti-flip por fuerza
        relativa.
      - Cuando vol_score>=0.85, NO franja muerta y edge robusto -> promueve
        al VIP+trial como ALERTA TACTICA FQ con TPs INTELIGENTES que mezclan
        estructurales lejanos cuando el contexto lo justifica (1:6 si la
        oportunidad esta) con cap conservador cuando no.
      - En caso contrario, RADAR admin-only original.
    """
    if not (RADAR_ENABLED and QTE_AVAILABLE and qt is not None
            and BATTLE_PLANNER_AVAILABLE and battle_planner is not None
            and VIP_FORMAT_AVAILABLE and vip_format is not None):
        return
    try:
        now_s = time.time()
        df = fetch_ohlcv(exchange, SYMBOL, tf_id, limit=200)
        df = add_indicators(df)
        if len(df) < 50:
            return
        last = df.iloc[-1]
        bias = detect_bias(df)
        masses = detect_pspace(df)
        direction = "long" if "alcista" in bias["bias"] else (
            "short" if "bajista" in bias["bias"] else "long")
        levels = calculate_levels_v2(df, direction, pspace=masses, tf=tf_id)
        qte_levels = {"entry": levels["entry"], "sl": levels["sl"],
                      "tp1": levels["tp1"], "tp2": levels["tp2"],
                      "tp3": levels["tp3"], "tp4": levels["tp4"]}
        # 1m/3m -> menos paths para latencia; 15m -> mantiene 2000
        n_paths_tf = 800 if tf_id in ("1m", "3m") else 2000
        qa = qt.quantum_analysis(
            df, direction=direction, levels=qte_levels,
            ict_module=ict_smc if ICT_MODULES_AVAILABLE else None,
            n_paths=n_paths_tf, run_optimizer=False, return_paths=True,
            adaptive=True)
        if qa.get("paths") is None:
            return
        fd = _build_field_data_standalone(df, None, None)
        plan = battle_planner.build_battle_plan(
            direction, float(last["close"]), fd, levels, qa["paths"], qa,
            atr=levels.get("atr"))

        # Solo avisar de setups realmente operables
        if plan["verdict"] not in ("EJECUTAR_AHORA", "ACUMULAR_EN_ZONA"):
            return

        # Gate de CONVICCION (v5.3, peticion RasDG): sin edge claro, mejor nada.
        # Mata el ruido de "Edge - probabilidad media" en TFs de campo antes de
        # gastar cooldown/volumen/promocion.
        has_conv, conv_reason = _radar_has_conviction(plan, tf_id)
        if not has_conv:
            log.info("RADAR descartado por baja conviccion [%s]: %s %s (%s)",
                     tf_id, plan["verdict"], direction, conv_reason)
            return

        # Cooldown PER-TF con anti-flip por fuerza relativa (ver _radar_emit_decision).
        last_radar = _RADAR_LAST_TF.get(tf_id) or {}
        cd = _radar_cooldown_for(tf_id)
        new_ev  = float((plan.get("market") or {}).get("ev")   or 0.0)
        new_psl = float((plan.get("market") or {}).get("p_sl") or 1.0)
        action, flip_replace = _radar_emit_decision(
            last_radar, now_s, direction, new_ev, new_psl, cd)
        if action == "skip":
            if last_radar.get("direction") != direction:
                log.info("RADAR flip suprimido [%s]: prev_dir=%s prev_ev=%.2f -> "
                         "new_dir=%s new_ev=%.2f new_psl=%.2f (no supera umbral "
                         "ratio=%.2f min_ev=%.2f max_psl=%.2f)",
                         tf_id, last_radar.get("direction"),
                         float(last_radar.get("ev") or 0.0),
                         direction, new_ev, new_psl,
                         RADAR_FLIP_EV_RATIO, RADAR_FLIP_EV_MIN, RADAR_FLIP_MAX_PSL)
            return
        if flip_replace:
            log.info("RADAR flip ACEPTADO [%s]: prev_dir=%s prev_ev=%.2f -> "
                     "new_dir=%s new_ev=%.2f (reemplaza anterior)",
                     tf_id, last_radar.get("direction"),
                     float(last_radar.get("ev") or 0.0),
                     direction, new_ev)

        # No duplicar si una senal automatica disparo hace poco en este TF
        last_sig = STATE.last_signal_ts_tf.get(tf_id)
        if last_sig:
            try:
                lt = last_sig if isinstance(last_sig, datetime) else \
                    datetime.fromtimestamp(float(last_sig), tz=timezone.utc)
                if lt.tzinfo is None:
                    lt = lt.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - lt).total_seconds() < 1800:
                    return
            except Exception:
                pass

        _RADAR_LAST_TF[tf_id] = {"ts": now_s, "verdict": plan["verdict"],
                                  "direction": direction,
                                  "ev": new_ev, "p_sl": new_psl}

        # FQ v5.2: calcular calidad de volumen del TF para decidir promocion a VIP.
        #
        # FIX (jun-2026, RasDG): radar_check corre al DETECTAR vela nueva (ver loop
        # principal: solo dispara cuando el TF esta en new_candle_tfs). En ese
        # instante df.iloc[-1] es la vela RECIEN ABIERTA (0-LOOP_SECONDS de vida),
        # con volumen parcial casi nulo. volume_score = vol_last/MA(20) sobre esa
        # vela daba ratios artificialmente bajos (p.ej. vol_score=0.11 en pleno
        # horario de Asia) que jamas superaban el gate de EJECUTAR (>=0.85), de
        # modo que setups de edge fuerte casi nunca se promovian al VIP. El volumen
        # del setup solo es medible una vez que la vela CIERRA: usamos la ultima
        # vela cerrada (df sin la vela en formacion).
        vol_data = None
        if VOLUME_QUALITY_AVAILABLE and volume_quality is not None:
            try:
                df_closed = df.iloc[:-1] if len(df) > 1 else df
                vol_data = volume_quality.volume_score(df_closed)
            except Exception as e:
                log.warning("radar_check: volume_score error: {}".format(e))

        # Killzone activa para el header
        kz_name = None
        try:
            if ICT_MODULES_AVAILABLE:
                kz_info = killzones_pd.current_killzone()
                kz_name = kz_info.get("name")
        except Exception:
            pass

        # Decidir destino: VIP (con tactical alert) vs admin-only (RADAR legacy)
        promote, reason = _should_promote_tactical_to_vip(plan, vol_data, kz_name)

        if promote:
            # === ALERTA TACTICA al VIP+trial+admin con TPs INTELIGENTES ===
            if plan["verdict"] == "EJECUTAR_AHORA":
                t_entry = float(plan["market"]["entry"])
                t_sl = float(plan["invalidation"])
            else:  # ACUMULAR_EN_ZONA
                z = plan["primary_zone"]
                accs = z.get("accumulate") or []
                if accs:
                    total_w = sum(a.get("weight_pct", 0) for a in accs) or 100.0
                    t_entry = sum(a["price"] * a.get("weight_pct", 0)
                                  for a in accs) / total_w
                else:
                    t_entry = float(z["ref"])
                t_sl = float(plan["invalidation"])

            # TP picker contextual: structural_tps de levels + plan + qa
            structural_tps = levels.get("tp_meta") or []
            tps_short = _compute_tactical_tps(
                direction, t_entry, t_sl,
                structural_tps=structural_tps, plan=plan, qa=qa, tf=tf_id)

            vol_label = (volume_quality.volume_quality_label(vol_data["score"])
                         if vol_data else None)
            tf_label = tf_id
            msg = vip_format.build_tactical_alert(plan, tps_short,
                                                  vol_label=vol_label,
                                                  killzone_name=kz_name,
                                                  tf_label=tf_label)
            if flip_replace:
                msg = ("<b>⚠️ FLIP — REEMPLAZA anterior {}</b>\n"
                       "<i>El radar previo del {} queda invalidado por mayor edge.</i>\n\n").format(
                    "LONG→SHORT" if direction == "short" else "SHORT→LONG",
                    tf_id) + msg
            # FQ v5.2: incluye trial igual que las senales clasicas
            sent, failed = broadcast_to_subscribers(
                msg, tiers=["vip", "trial", "admin"])

            # FQ v5.4: persistir la tactica para seguirla en vivo (SL a BE en
            # TP1, parcial en TP2, trailing en TP3). No toca el ledger.
            # Solo si el seguimiento esta activo (off por defecto: sin
            # seguimiento no tiene sentido persistir la tactica).
            if (TACTICAL_TRACKING_ENABLED
                    and TACTICAL_TRACKER_AVAILABLE and tactical_tracker is not None):
                try:
                    tp_prices = [t.get("price") for t in tps_short]
                    while len(tp_prices) < 3:
                        tp_prices.append(None)
                    tactical_tracker.record_tactical(
                        tf=tf_id, direction=direction,
                        entry=t_entry, sl=t_sl,
                        tp1=tp_prices[0], tp2=tp_prices[1], tp3=tp_prices[2])
                except Exception as te:
                    log.warning("record_tactical error [%s]: %s", tf_id, te)

            log.info("TACTICAL ALERT [%s] enviada: %s %s sent=%d failed=%d (vol=%s, kz=%s, ext_tps=%s, flip=%s)",
                     tf_id, plan["verdict"], direction, sent, failed,
                     vol_label or "?", kz_name or "?",
                     [(t["rr"], t["kind"]) for t in tps_short],
                     flip_replace)
            return

        # === RADAR legacy admin-only (sin promocion) ===
        # v5.4: la "inteligencia anticipada" al admin esta apagada por defecto
        # (ver RADAR_ADMIN_READOUT_ENABLED). Si no se promovio a tactica, no se
        # emite NADA: menos ruido. /campo sigue disponible bajo demanda.
        if not RADAR_ADMIN_READOUT_ENABLED:
            log.info("RADAR admin-only suprimido (inteligencia anticipada off) "
                     "[%s]: %s %s motivo=%s flip=%s",
                     tf_id, plan["verdict"], direction, reason, flip_replace)
            return
        body = vip_format.build_battle_block(plan)
        suffix = "\n<i>El gate automatico sigue intacto. Confirma con /analisis.</i>"
        if reason:
            # El reason del gate puede traer '<'/'>' (p.ej. "vol_score=0.78<0.85"
            # o "market.p_sl>0.55") que rompen el parse HTML de Telegram y harian
            # caer el mensaje a texto plano con los tags crudos. Escaparlos.
            suffix += "\n<i>(no promovida: {})</i>".format(_html_escape(reason))
        # En TFs de campo (1m/3m/5m) etiqueta el RADAR con el TF para no confundir
        # con el 15m original.
        tf_tag = " [{}]".format(tf_id) if tf_id in _FIELD_FAST_TFS else ""
        flip_header = ""
        if flip_replace:
            flip_header = ("<b>⚠️ FLIP — REEMPLAZA anterior {}</b>\n"
                           "<i>El radar previo del {} queda invalidado por mayor edge.</i>\n\n").format(
                "LONG→SHORT" if direction == "short" else "SHORT→LONG",
                tf_id)
        msg = (flip_header +
               "<b>📡 RADAR FQ{tf} — setup armandose</b>\n"
               "<i>No es senal automatica. Inteligencia anticipada.</i>\n\n"
               "{body}{suffix}").format(tf=tf_tag, body=body, suffix=suffix)
        telegram_send(msg, TELEGRAM_CHAT_ID)
        log.info("RADAR enviado (admin-only) [%s]: %s %s motivo=%s flip=%s",
                 tf_id, plan["verdict"], direction, reason, flip_replace)
    except Exception as e:
        log.warning("radar_check error [{}]: {}".format(tf_id, e))


def build_analisis_context(exchange):
    """
    Computa UNA sola vez el contexto pesado de /analisis (df + indicadores,
    sesgo, niveles, QTE de 2000 paths con optimizer + paths, battle plan) para
    COMPARTIRLO entre el mensaje curado (cmd_analisis_vip) y la lectura de Claude
    (claude_followup_analisis_vip). Evita re-simular el QTE por cada /analisis.

    Devuelve dict {df,last,bias,masses,direction,pm_est,levels,qa,plan} o None si
    no hay datos suficientes. qa/plan pueden ser None si el QTE/planner fallan.
    """
    df = fetch_ohlcv(exchange, SYMBOL, "15m", limit=200)
    df = add_indicators(df)
    if len(df) < 50:
        return None
    last = df.iloc[-1]
    bias = detect_bias(df)
    masses = detect_pspace(df)
    direction = "long" if "alcista" in bias["bias"] else (
        "short" if "bajista" in bias["bias"] else "long")

    session, w_clock, _, _ = get_session()
    lap = laplacian_check(df)
    h_factor = 1.0 if lap["active"] else 0.7
    pm_est = PHI * w_clock * h_factor * (1 + max(0, masses["count"] - 2) * 0.15)

    levels = calculate_levels_v2(df, direction, pspace=masses, tf="15m")

    # QTE: una sola corrida 2000 paths + optimizer + paths. Sirve al mensaje
    # curado, al battle plan y a la lectura de Claude (incl. bloque optimizer).
    qa = None
    if QTE_AVAILABLE and qt is not None:
        try:
            qte_levels = {"entry": levels["entry"], "sl": levels["sl"],
                          "tp1": levels["tp1"], "tp2": levels["tp2"],
                          "tp3": levels["tp3"], "tp4": levels["tp4"]}
            qa = qt.quantum_analysis(
                df, direction=direction, levels=qte_levels,
                ict_module=ict_smc if ICT_MODULES_AVAILABLE else None,
                n_paths=2000, run_optimizer=True, return_paths=True,
                adaptive=True)
        except Exception as ex:
            log.warning("QTE en build_analisis_context fallo: {}".format(ex))

    # Battle plan sobre los paths recien simulados (sin re-simular)
    plan = None
    if (BATTLE_PLANNER_AVAILABLE and battle_planner is not None
            and qa is not None and qa.get("paths") is not None):
        try:
            fd = _build_field_data_standalone(df, None, None)
            plan = battle_planner.build_battle_plan(
                direction=direction, current_price=float(last["close"]),
                field_data=fd, levels=levels,
                paths=qa["paths"], qa=qa, atr=levels.get("atr"))
        except Exception as ex:
            log.warning("battle_planner en build_analisis_context fallo: {}".format(ex))

    return {"df": df, "last": last, "bias": bias, "masses": masses,
            "direction": direction, "pm_est": pm_est, "levels": levels,
            "qa": qa, "plan": plan}


def claude_followup_analisis_vip(exchange, ctx=None):
    """
    Follow-up Claude VERSION VIP: 4 bullets decisivos. Reutiliza el contexto
    pesado (df, niveles, QTE 2000 paths, battle plan) si el router pasa `ctx`,
    evitando re-simular el QTE. Si ctx es None, lo computa por su cuenta.
    """
    if not claude_ai.is_available():
        return None
    try:
        if ctx is None:
            ctx = build_analisis_context(exchange)
        if not ctx:
            return None
        last = ctx["last"]
        bias = ctx["bias"]
        masses = ctx["masses"]
        direction = ctx["direction"]
        levels = ctx["levels"]
        qa = ctx.get("qa")
        plan = ctx.get("plan")

        snapshot = {
            "price": float(last["close"]),
            "direction": direction,
            "bias": bias["bias"],
            "entry": levels["entry"],
            "sl": levels["sl"],
            "sl_anchor": levels.get("sl_anchor", "-"),
            "tp1": levels["tp1"], "rr_tp1": levels["rr_tp1"],
            "tp2": levels["tp2"], "rr_tp2": levels["rr_tp2"],
            "tp3": levels["tp3"], "rr_tp3": levels["rr_tp3"],
            "pspace_count": masses["count"],
            "rsi14": float(last.get("rsi14") or 0),
        }

        # QTE ya simulado en el contexto compartido -> snapshot que ve Claude
        if qa is not None:
            probs = qa["probabilities"]
            snapshot.update({
                "qte_n_paths": qa["n_paths"],
                "qte_p_tp1": probs["p_tp1"],
                "qte_p_tp2": probs["p_tp2"],
                "qte_p_sl":  probs["p_sl"],
                "qte_ev":    probs["expected_R"],
                "qte_dominant_regime": qa["dominant_regime"],
                "qte_dominant_pct":    qa["dominant_regime_pct"],
                # Probabilidades de tocar cada TP antes que SL (utiles, no 0)
                "qte_p_reach_tp1": probs.get("p_reach_tp1"),
                "qte_p_reach_tp2": probs.get("p_reach_tp2"),
                "qte_p_reach_tp3": probs.get("p_reach_tp3"),
                "qte_p_timeout":   probs.get("p_timeout"),
                "qte_win_rate":    probs.get("win_rate"),
                "qte_coherence":   qa.get("coherence"),
                "qte_regimes_top3": list(qa["regimes"].items())[:3],
            })
            # Veredicto canonico (misma fuente que VIP/admin) para alinear la
            # lectura de Claude con el resto de superficies.
            _v = qa.get("verdict")
            if _v:
                snapshot["qte_verdict_label"] = _v["label"]
                snapshot["qte_verdict_grade"] = _v["grade"]
            # Alternativa del optimizer (advisory) si el QAOA hallo niveles
            opt = qa.get("optimized_levels")
            vb = qa.get("vs_baseline")
            if opt and vb:
                snapshot.update({
                    "qte_opt_sl":  opt["sl"],
                    "qte_opt_tp1": opt["tp1"],
                    "qte_opt_tp2": opt["tp2"],
                    "qte_opt_tp3": opt["tp3"],
                    "qte_opt_ev":  opt["expected_R"],
                    "qte_opt_p_sl": opt["p_sl"],
                    "qte_vs_delta_R":       vb["delta_R"],
                    "qte_vs_baseline_p_sl": vb["baseline_p_sl"],
                    "qte_vs_baseline_ev":   vb["baseline_ev_R"],
                })

        # PLAN DE BATALLA ya construido en el contexto -> Claude lo confirma/corrige
        if plan is not None:
            snapshot["battle"] = _battle_snapshot(plan)

        # FQ v5.1: Phase E informativo - usa el df del contexto (sin re-fetch)
        phase_e = compute_phase_e_informative(ctx["df"], direction, tf_id="15m")
        if phase_e is not None:
            snapshot.update({
                "phase_e_sync_score":   phase_e["sync_score"],
                "phase_e_tier":         phase_e["tier"],
                "phase_e_tau":          phase_e["tau"],
                "phase_e_phi_clock":    phase_e["phi_clock"],
                "phase_e_phi_memory":   phase_e["phi_memory"],
                "phase_e_phi_horizon":  phase_e["phi_horizon"],
                "phase_e_phi_refractory": phase_e["phi_refractory"],
                "phase_e_coherence":    phase_e["coherence"],
                "phase_e_regime_modal": phase_e["regime_modal"],
                "phase_e_delta_min":    phase_e["delta_min"],
                "phase_e_cooldown_min": phase_e["cooldown_min"],
            })

        reading = _escape_claude(claude_ai.tactical_analisis_vip(snapshot))
        if not reading:
            return None
        rule = "━" * 30
        return (
            "{rule}\n"
            "  ◆ Claude — Lectura breve\n"
            "{rule}\n"
            "{r}\n"
            "{rule}"
        ).format(rule=rule, r=reading)
    except Exception as e:
        log.error("Claude followup analisis VIP error: {}".format(e))
        return None

def claude_followup_pspace(exchange):
    """Genera lectura Claude para /pspace"""
    if not claude_ai.is_available():
        return None
    try:
        df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
        df = add_indicators(df)
        last = df.iloc[-1]
        ps = detect_pspace(df)
        bias = detect_bias(df)
        sw = ps["support_weight"]
        rw = ps["resistance_weight"]
        total_w = sw + rw
        curv_balance = (sw - rw) / total_w if total_w > 0 else 0
        basic_state = {
            "price": float(last["close"]),
            "bias": bias["bias"], "bias_score": bias["score"],
            "curvature_balance": curv_balance,
        }
        snapshot = mctx.snapshot_for_pspace(df, basic_state, ps)
        reading = _escape_claude(claude_ai.tactical_pspace(snapshot))
        return (
            "<b>CLAUDE - Lectura P-Space + libro</b>\n"
            "{thin}\n\n{r}\n\n"
            "{thin}\nModelo: Sonnet 4.5\n#FQ #Claude"
        ).format(thin=G["thin"], r=reading)
    except Exception as e:
        log.error("Claude followup pspace error: {}".format(e))
        return None

def claude_followup_niveles(exchange):
    """Genera lectura Claude para /niveles"""
    if not claude_ai.is_available():
        return None
    try:
        df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
        df = add_indicators(df)
        last = df.iloc[-1]
        session, w_clock, _, _ = get_session()
        bias = detect_bias(df)
        ps = detect_pspace(df)
        if "alcista" in bias["bias"]:
            direction_main = "long"
        elif "bajista" in bias["bias"]:
            direction_main = "short"
        else:
            direction_main = "long"
        levels = calculate_levels(df, direction_main)
        plan_primary = build_trigger_plan(df, direction_main, ps, bias)
        plan_secondary = build_trigger_plan(df, "short" if direction_main == "long" else "long", ps, bias)
        basic_state = {
            "price": float(last["close"]),
            "session": session, "w_clock": w_clock,
            "bias": bias["bias"], "bias_score": bias["score"],
            "plan_sl": levels["sl"], "plan_tp3": levels["tp3"],
        }
        snapshot = mctx.snapshot_for_niveles(df, basic_state, plan_primary, plan_secondary)
        reading = _escape_claude(claude_ai.tactical_niveles(snapshot))
        return (
            "<b>CLAUDE - Afinacion del plan</b>\n"
            "{thin}\n\n{r}\n\n"
            "{thin}\nModelo: Sonnet 4.5\n#FQ #Claude"
        ).format(thin=G["thin"], r=reading)
    except Exception as e:
        log.error("Claude followup niveles error: {}".format(e))
        return None


def command_listener(exchange):
    """
    MISTRAL: Listener multiusuario con VIP access control.
    - Acepta mensajes de cualquier chat_id
    - Registra usuario automaticamente
    - Verifica tier antes de ejecutar comandos premium
    - Claude follow-up corre en thread separado (no bloquea)
    """
    log.info("Command listener (multi-user) started")
    while True:
        try:
            updates = telegram_get_updates(STATE.telegram_offset)
            for upd in updates:
                STATE.telegram_offset = upd["update_id"] + 1
                raw_msg = upd.get("message", {})
                text_raw = (raw_msg.get("text") or "").strip()
                if not text_raw:
                    continue

                chat_data = raw_msg.get("chat", {})
                chat_id    = str(chat_data.get("id", ""))
                username   = chat_data.get("username") or ""
                first_name = chat_data.get("first_name") or ""

                if not chat_id:
                    continue

                # Normalizar comando
                text = text_raw.lower()
                if "@" in text:
                    text = text.split("@")[0]
                raw_parts = text_raw.split()
                cmd_name  = text.split()[0] if text.split() else ""
                raw_args  = raw_parts[1:] if len(raw_parts) > 1 else []

                if not cmd_name.startswith("/"):
                    continue

                log.info("Cmd: {} from {} ({})".format(cmd_name, chat_id, username))

                # === REGISTRO DE USUARIO (VIP system) ===
                if VIP_ENABLED:
                    try:
                        user = vip.get_or_create_user(chat_id, username=username, first_name=first_name)
                        # Welcome a usuarios nuevos
                        if user.get("is_new"):
                            if VIP_FORMAT_AVAILABLE:
                                tier = user.get("tier", "free")
                                telegram_send(vip_format.build_welcome_for_tier(tier), chat_id)
                            else:
                                telegram_send(
                                    "Bienvenido a FQ\n"
                                    "Senales SOL/USDT con disciplina sistematica.\n"
                                    "Usa /precio para tarifas o /codigo XXXX si tienes codigo.",
                                    chat_id)
                            # Aviso de riesgo una sola vez (primer contacto)
                            try:
                                telegram_send(legal.build_disclaimer(), chat_id)
                            except Exception:
                                pass
                    except Exception as e:
                        log.error("VIP user registration error: {}".format(e))
                        # Non-fatal: continuar sin VIP
                        user = {"tier": "admin" if chat_id == TELEGRAM_CHAT_ID else "free"}

                    # === COMANDOS VIP SELF-SERVICE ===
                    if cmd_name == "/precio":
                        telegram_send(vip.format_precio_message(), chat_id)
                        continue
                    if cmd_name == "/miestado":
                        telegram_send(vip.format_user_status(chat_id), chat_id)
                        continue
                    if cmd_name == "/legal":
                        send_long(legal.build_legal_menu(), chat_id)
                        continue
                    if cmd_name in ("/resultados", "/track"):
                        try:
                            summary = ev.get_results_summary()
                            telegram_send(vip_format.build_resultados(summary), chat_id)
                        except Exception as e:
                            log.error("/resultados error: {}".format(e))
                            telegram_send("Resultados no disponibles ahora.", chat_id)
                        continue
                    if cmd_name == "/vip":
                        _cmd_vip_flow(exchange, chat_id, raw_args)
                        continue
                    if cmd_name == "/renovar":
                        _cmd_vip_flow(exchange, chat_id, [])
                        continue
                    if cmd_name == "/codigo":
                        if not raw_args:
                            telegram_send("Uso: /codigo TU-CODIGO\nEjemplo: /codigo RASDG-AB12CD", chat_id)
                        else:
                            code = raw_args[0].strip().upper()
                            ok, msg_r, days = vip.redeem_code(code, chat_id, username)
                            if ok:
                                telegram_send(
                                    "<b>Codigo aplicado</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                    "{m}\n\nAcceso VIP activo. Usa /help para comandos.".format(m=msg_r),
                                    chat_id)
                            else:
                                telegram_send("<b>Codigo invalido</b>\n{}".format(msg_r), chat_id)
                        continue

                    # === COMANDOS ADMIN ===
                    if chat_id == TELEGRAM_CHAT_ID:
                        if cmd_name == "/gencode":
                            _cmd_admin_gencode(chat_id, raw_args)
                            continue
                        if cmd_name == "/usuarios":
                            telegram_send(vip.format_users_list(20), chat_id)
                            continue
                        if cmd_name == "/stats":
                            telegram_send(vip.format_admin_stats(), chat_id)
                            continue
                        if cmd_name == "/grant":
                            _cmd_admin_grant(chat_id, raw_args)
                            continue
                        if cmd_name == "/revoke":
                            _cmd_admin_revoke(chat_id, raw_args)
                            continue
                        if cmd_name == "/broadcast":
                            _cmd_admin_broadcast(chat_id, raw_parts[1:])
                            continue

                    # === ACCESS CONTROL para comandos premium ===
                    PREMIUM_COMMANDS = {
                        "/analisis", "/niveles", "/pspace", "/claude", "/ia",
                        "/metrics", "/entropy", "/ledger", "/evolve", "/audit",
                    }
                    if cmd_name in PREMIUM_COMMANDS:
                        tier = vip.get_effective_tier(chat_id)
                        if tier not in ("vip", "trial", "admin"):
                            telegram_send(
                                "<b>Acceso VIP requerido</b>\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                "El comando {} requiere suscripcion VIP.\n\n"
                                "▸ /precio para ver planes\n"
                                "▸ /codigo XXXX para canjear codigo\n"
                                "▸ /vip para adquirir acceso".format(cmd_name), chat_id)
                            continue
                else:
                    # Sin VIP system: solo admin (chat_id original)
                    if chat_id != TELEGRAM_CHAT_ID:
                        telegram_send("Bot privado. Contactar a RasDG_Sol.", chat_id)
                        continue

                # === COMANDOS TIER-AWARE (chat_id-aware) ===
                # /help y /about adaptan contenido segun tier del invocador
                if cmd_name in ("/help", "/about", "/start"):
                    try:
                        if cmd_name == "/about":
                            send_long(cmd_about(chat_id), chat_id)
                        else:
                            send_long(cmd_help(chat_id), chat_id)
                    except Exception as e:
                        log.error("tier-aware handler {}: {}".format(cmd_name, e))
                        send_long("Error: {}".format(str(e)[:200]), chat_id)
                    continue

                # === ADMIN-ONLY GATE ===
                ADMIN_ONLY = {"/audit", "/entropy", "/metrics", "/ledger",
                              "/evolve", "/concepts", "/weekend", "/campo",
                              "/gencode", "/grant", "/broadcast",
                              "/atribucion", "/regimen", "/sweep",
                              "/timelines"}
                if cmd_name in ADMIN_ONLY and str(chat_id) != str(TELEGRAM_CHAT_ID):
                    telegram_send(
                        "Comando no disponible. Usa /help para ver tus comandos.",
                        chat_id)
                    continue

                # === /analisis TIER-AWARE (F1 v5.0): admin=lectura completa, VIP=curado ===
                if cmd_name == "/analisis":
                    tier_loc = "free"
                    if str(chat_id) == str(TELEGRAM_CHAT_ID):
                        tier_loc = "admin"
                    elif VIP_ENABLED and vip is not None:
                        try:
                            tier_loc = vip.get_effective_tier(chat_id)
                        except Exception:
                            tier_loc = "free"

                    # Cooldown VIP/trial: 30 min entre /analisis por usuario.
                    # Admin no rate-limitado. Se marca el timestamp antes de la llamada
                    # cara para que errores transitorios no permitan spam-retry.
                    if tier_loc in ("vip", "trial") and VIP_ANALISIS_COOLDOWN_SEC > 0:
                        now_s = time.time()
                        last_s = _VIP_ANALISIS_LAST.get(str(chat_id), 0)
                        remaining = VIP_ANALISIS_COOLDOWN_SEC - (now_s - last_s)
                        if remaining > 0:
                            mins = int(remaining // 60)
                            secs = int(remaining % 60)
                            telegram_send(
                                "<b>/analisis en cooldown</b>\n"
                                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                                "Espera <b>{}m {:02d}s</b> antes del siguiente analisis.\n\n"
                                "Cooldown VIP = {} min por usuario. Protege la API y\n"
                                "asegura que cada lectura que pidas sea fresca.\n\n"
                                "Las senales automaticas siguen llegando sin limite.".format(
                                    mins, secs, VIP_ANALISIS_COOLDOWN_SEC // 60),
                                chat_id)
                            continue
                        _VIP_ANALISIS_LAST[str(chat_id)] = now_s

                    telegram_send("Lectura tactica en proceso - Claude Sonnet 4.6...", chat_id)
                    try:
                        # Contexto pesado (QTE 2000 + battle plan) UNA sola vez,
                        # compartido entre mensaje curado y lectura de Claude.
                        analisis_ctx = None
                        if tier_loc == "admin":
                            response = cmd_lectura(exchange)
                            fu_fn = claude_followup_general
                        else:
                            analisis_ctx = build_analisis_context(exchange)
                            response = cmd_analisis_vip(exchange, ctx=analisis_ctx)
                            fu_fn = claude_followup_analisis_vip
                        send_long(response, chat_id)

                        if claude_ai.is_available():
                            def _send_fu_analisis(fn=fu_fn, cid=chat_id, ctx=analisis_ctx):
                                try:
                                    telegram_send("Claude interpretando datos...", cid)
                                    # El follow-up VIP reutiliza el ctx; el admin no lo usa.
                                    fu = fn(exchange, ctx=ctx) if ctx is not None else fn(exchange)
                                    if fu:
                                        send_long(fu, cid)
                                except Exception as fu_e:
                                    log.error("Claude fu /analisis err: {}".format(fu_e))
                            threading.Thread(target=_send_fu_analisis, daemon=True).start()
                    except Exception as e:
                        log.error("/analisis tier-aware error: {}\n{}".format(
                            e, traceback.format_exc()))
                        telegram_send("Error: {}".format(str(e)[:200]), chat_id)
                    continue

                # === COMANDOS NORMALES (FQ) ===
                if cmd_name in COMMANDS:
                    handler = COMMANDS[cmd_name]
                    try:
                        loading_map = {
                            "/lectura":  "Lectura tactica en proceso - Claude Sonnet 4.6...",
                            "/analisis": "Lectura tactica en proceso - Claude Sonnet 4.6...",
                            "/niveles":  "Lectura tactica en proceso - Claude Sonnet 4.6...",
                            "/pspace":   "Lectura tactica en proceso - Claude Sonnet 4.6...",
                            "/claude":   "Lectura tactica en proceso - Claude Sonnet 4.6...",
                            "/ia":       "Lectura tactica en proceso - Claude Sonnet 4.6...",
                        }
                        if cmd_name in loading_map:
                            telegram_send(loading_map[cmd_name], chat_id)

                        # Ejecutar handler
                        response = handler(exchange) if handler.__code__.co_argcount > 0 else handler()
                        send_long(response, chat_id)

                        # Claude follow-up en THREAD SEPARADO (no bloquea el listener)
                        if cmd_name in CLAUDE_FOLLOWUP and claude_ai.is_available():
                            def _send_claude_fu(c=cmd_name, cid=chat_id):
                                try:
                                    telegram_send("Claude interpretando datos...", cid)
                                    fu = CLAUDE_FOLLOWUP[c](exchange)
                                    if fu:
                                        send_long(fu, cid)
                                except Exception as fu_e:
                                    log.error("Claude followup thread error: {}".format(fu_e))
                            threading.Thread(target=_send_claude_fu, daemon=True).start()

                    except Exception as e:
                        log.error("Error executing {}: {}\n{}".format(
                            cmd_name, e, traceback.format_exc()))
                        telegram_send("Error: {}".format(str(e)[:200]), chat_id)

            time.sleep(2)
        except Exception as e:
            log.error("Listener loop error: {}\n{}".format(e, traceback.format_exc()))
            time.sleep(10)


# ============================================================
# VIP COMMAND HELPERS
# ============================================================
def _cmd_vip_flow(exchange, chat_id, args):
    """Flujo /vip - elegir plan y metodo de pago"""
    if not VIP_ENABLED:
        telegram_send("Sistema VIP no disponible.", chat_id)
        return
    if not args:
        msg = (
            "<b>ADQUIRIR VIP</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        for pid, info in vip.PLAN_PRICES.items():
            if pid == "trial_7d":
                continue
            msg += "<b>{}</b> - ${} USD\n".format(info["label"], info["price_usd"])
            msg += "  {} dias | /vip {} stripe | /vip {} crypto\n\n".format(
                info["days"], pid, pid)
        msg += "Metodos: stripe (tarjeta) o crypto (USDT)"
        telegram_send(msg, chat_id)
        return

    plan_id = args[0].lower()
    method  = args[1].lower() if len(args) > 1 else "stripe"

    if plan_id not in vip.PLAN_PRICES or plan_id == "trial_7d":
        telegram_send("Plan invalido. Usa /vip para ver opciones.", chat_id)
        return

    plan_info = vip.PLAN_PRICES[plan_id]

    if method == "stripe":
        if not pay.stripe_available():
            telegram_send("Stripe no configurado.\nUsa: /vip {} crypto".format(plan_id), chat_id)
            return
        url, err = pay.create_stripe_checkout(chat_id, plan_id)
        if not url:
            telegram_send("Error: {}".format(err), chat_id)
            return
        telegram_send(
            "<b>{}</b>\n${} USD - {} dias\n\n"
            "<b>Pagar con tarjeta:</b>\n{}\n\n"
            "Acceso se activa automaticamente.".format(
                plan_info["label"], plan_info["price_usd"], plan_info["days"], url),
            chat_id)

    elif method in ("crypto", "trc20", "erc20"):
        network = method if method in ("trc20", "erc20") else "trc20"
        result, err = pay.create_crypto_payment(chat_id, plan_id, network)
        if not result:
            telegram_send("Error: {}".format(err), chat_id)
            return
        telegram_send(
            "<b>{}</b> - USDT-{}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Monto exacto: <code>{:.4f}</code> USDT\n\n"
            "<b>Wallet:</b>\n<code>{}</code>\n\n"
            "Ref: {}\nExpira en {} horas.\n\n"
            "Verificacion automatica cada 5 min.".format(
                plan_info["label"], network.upper(),
                result["amount"], result["wallet"],
                result["ref_id"], result["expires_in_hours"]),
            chat_id)
    else:
        telegram_send("Metodo invalido. Usa stripe o crypto.", chat_id)


def _cmd_admin_gencode(admin_cid, args):
    days = 7
    kind = "gift"
    note = None
    if len(args) >= 1:
        try:
            days = int(args[0])
        except ValueError:
            telegram_send("Uso: /gencode 7 trial mi-amigo", admin_cid)
            return
    if len(args) >= 2:
        kind = args[1].lower()
    if len(args) >= 3:
        note = " ".join(args[2:])
    if days <= 7:    plan = "trial_7d"
    elif days <= 30: plan = "vip_30d"
    elif days <= 90: plan = "vip_90d"
    elif days <= 365: plan = "vip_365d"
    else:            plan = "lifetime"
    code = vip.generate_code(duration_days=days, plan=plan, kind=kind,
                             created_by=admin_cid, note=note)
    telegram_send(
        "<b>Codigo generado</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Codigo: <code>{code}</code>\n"
        "Duracion: {d} dias | Plan: {p}\n"
        "{note}\n"
        "El usuario ejecuta: /codigo {code}".format(
            code=code, d=days, p=plan,
            note="Nota: {}\n".format(note) if note else ""),
        admin_cid)


def _cmd_admin_grant(admin_cid, args):
    if len(args) < 2:
        telegram_send("Uso: /grant CHAT_ID PLAN\nPlanes: trial_7d vip_30d vip_90d vip_365d lifetime", admin_cid)
        return
    target, plan = args[0], args[1].lower()
    if plan not in vip.PLAN_PRICES:
        telegram_send("Plan invalido.", admin_cid)
        return
    info = vip.PLAN_PRICES[plan]
    exp = vip.grant_subscription(target, plan, info["days"], source="admin_grant", referrer=admin_cid)
    telegram_send("Acceso otorgado a {}\n{} hasta {}".format(target, plan, exp.strftime("%Y-%m-%d")), admin_cid)
    try:
        telegram_send(
            "<b>Acceso VIP otorgado</b>\nPlan: {}\nExpira: {}\n\nUsa /help para comandos.".format(
                info["label"], exp.strftime("%Y-%m-%d")), target)
    except Exception:
        pass


def _cmd_admin_revoke(admin_cid, args):
    if not args:
        telegram_send("Uso: /revoke CHAT_ID [razon]", admin_cid)
        return
    target = args[0]
    reason = " ".join(args[1:]) if len(args) > 1 else "admin_revoke"
    vip.revoke_subscription(target, reason)
    telegram_send("Acceso revocado para {}.".format(target), admin_cid)


def _cmd_admin_broadcast(admin_cid, raw_args):
    if not raw_args:
        telegram_send("Uso: /broadcast MENSAJE", admin_cid)
        return
    message = " ".join(raw_args)
    users = vip.get_all_users(tier=vip.TIER_VIP, limit=500) +             vip.get_all_users(tier=vip.TIER_TRIAL, limit=500)
    sent = failed = 0
    for u in users:
        ok = telegram_send(
            "<b>RasDG_Sol</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n{}".format(message),
            u["chat_id"])
        if ok: sent += 1
        else:  failed += 1
    telegram_send("Broadcast: {} enviados, {} fallidos.".format(sent, failed), admin_cid)

# ============================================================
# EVOLUTION COMMANDS (v3.2)
# ============================================================
def send_db_backup_to_telegram():
    """Envia el .db actual al chat como documento"""
    db_path = ev.export_db_path()
    if not db_path:
        log.warning("Backup: DB path no existe")
        return False
    url = "https://api.telegram.org/bot{}/sendDocument".format(TELEGRAM_TOKEN)
    try:
        with open(db_path, "rb") as f:
            files = {"document": (
                "fq_ledger_{}.db".format(
                    datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")),
                f
            )}
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": "Ledger backup - {} senales totales".format(
                    ev.count_signals(closed_only=False)),
            }
            r = requests.post(url, data=data, files=files, timeout=60)
            if r.status_code == 200:
                log.info("DB backup enviado a Telegram")
                return True
            log.error("Backup HTTP {}: {}".format(r.status_code, r.text[:200]))
    except Exception as e:
        log.error("send_db_backup_to_telegram: {}".format(e))
    return False

def cmd_audit_manual(exchange):
    """Trigger manual de self-audit"""
    n = ev.count_signals(closed_only=True)
    if not claude_ai.is_available():
        return "Claude no disponible. Configura ANTHROPIC_API_KEY."

    # Reconcilia primero por si hay outcomes pendientes
    try:
        ev.reconcile_outcomes(fetch_ohlcv, exchange, SYMBOL, TIMEFRAME)
    except Exception as e:
        log.error("Pre-audit reconcile error: {}".format(e))

    n = ev.count_signals(closed_only=True)
    if n == 0:
        return "Sin senales cerradas aun. El audit requiere data."

    prompt = ev.build_audit_prompt_v3() if hasattr(ev, "build_audit_prompt_v3") else ev.build_audit_prompt()
    if not prompt:
        return "No hay data suficiente para audit."

    telegram_send(
        "<b>AUDIT MANUAL - OPUS 4.6</b>\n"
        "Procesando {} senales cerradas...".format(n)
    )
    response = ev_claude.self_audit(prompt)
    metrics = ev.get_global_metrics()
    ev.save_audit(n, metrics, response)

    return (
        "<b>AUDIT MANUAL - OPUS 4.6</b>\n"
        "{thin}\n\n{r}\n\n"
        "{thin}\nSugerencias - RasDG decide.\n"
        "#SelfAudit #FQ"
    ).format(thin=G["thin"], r=response)

def cmd_entropy(exchange=None):
    return ev.format_entropy_telegram()

def cmd_metrics(exchange=None):
    return ev.format_metrics_telegram()

def cmd_ledger(exchange=None):
    return ev.format_ledger_telegram(10)

def cmd_evolve(exchange=None):
    """Estado del modulador kappa_evo - que buckets estan activos"""
    e = ev.compute_entropy_metrics()
    if e["n_total"] == 0:
        return "Sin data evolutiva aun."
    bp = ev._bucket_performance_table()
    if not bp:
        return (
            "<b>KAPPA EVO STATUS</b>\n"
            "Senales totales: {}\n"
            "Senales cerradas: {}\n"
            "Ningun bucket aun tiene >=4 cerradas.\n"
            "kappa_evo = 1.0 en todo (modo neutral).".format(
                e["n_total"], e["n_closed"])
        )
    bp.sort(key=lambda x: x["expectancy"], reverse=True)
    lines = ["<b>KAPPA EVO - BUCKETS ACTIVOS</b>", ""]
    for b in bp:
        n_min = ev.KAPPA_EVO_MIN_SAMPLES
        if b["n"] >= n_min:
            tag = "MOD"
        else:
            tag = "watch"
        lines.append("[{}] {} | n={} WR={:.0%} Exp={:+.2f}R".format(
            tag, b["bucket"], b["n"], b["win_rate"], b["expectancy"]))
    lines.append("")
    lines.append(
        "MOD = bucket modulando kappa_evo (n>={})".format(ev.KAPPA_EVO_MIN_SAMPLES))
    lines.append("watch = juntando data, sin modular aun")
    lines.append("")
    lines.append("<b>Cap absoluto:</b> kappa_evo en [0.85, 1.15]")
    return "\n".join(lines)

# ============================================================
# ADMIN COMMANDS v4.3 - capa ML
# ============================================================
def cmd_atribucion(exchange=None):
    """Atribucion Shapley de la ultima senal disparada"""
    try:
        import signal_scorer
        with STATE.lock:
            last_score = getattr(STATE, "last_score_result", None)
        if last_score is None:
            return ("Sin atribuciones aun. Se guarda automaticamente con cada "
                    "senal disparada bajo v4.3.")
        return signal_scorer.format_attribution_telegram(last_score)
    except Exception as e:
        return "Error /atribucion: {}".format(str(e)[:200])

def cmd_regimen(exchange):
    """Estado actual del regime detector"""
    try:
        import regime_detector
        df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=80)
        df = add_indicators(df)
        regime = regime_detector.detect_regime(df)
        return regime_detector.format_regime_telegram(regime)
    except Exception as e:
        return "Error /regimen: {}".format(str(e)[:200])

def cmd_sweep(exchange=None):
    """Greedy threshold sweep sobre el ledger cerrado"""
    try:
        import signal_scorer
        with ev._lock:
            conn = ev._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM signals WHERE outcome IS NOT NULL ORDER BY id"
                ).fetchall()
                closed = [dict(r) for r in rows]
            finally:
                conn.close()
        if not closed:
            return "Ledger vacio. Necesita >=10 senales cerradas."
        sweep = signal_scorer.threshold_sweep(closed)
        if not sweep:
            return ("Sweep: cerradas insuficientes en ventana ({} totales). "
                    "Necesita >=10 cerradas por nivel de threshold.".format(len(closed)))
        return signal_scorer.format_sweep_telegram(sweep, current_threshold=PMASTER_MIN)
    except Exception as e:
        return "Error /sweep: {}".format(str(e)[:200])

def cmd_lectura(exchange):
    """
    /lectura - vista consolidada multi-TF.
    Para cada TF (5m INTRADIA / 15m SCALPING / 1h SWING) muestra: bias,
    masas P-Space, P_master estimado vs umbral del perfil, niveles
    entry/SL/TP1-4 con R:R, y cooldown restante. Despues opcionalmente
    una lectura tactica de Claude sobre el TF anchor (15m).
    """
    try:
        session, w_clock, _, _ = get_session()
        now_utc = datetime.now(timezone.utc)

        tf_blocks = []
        anchor_price = None
        anchor_df = None
        for tf_id in TIMEFRAMES:
            profile = TF_PROFILES[tf_id]
            tf_label = profile["label"]
            try:
                df = fetch_ohlcv(exchange, SYMBOL, tf_id, limit=200)
                df = add_indicators(df)
                if len(df) < 50:
                    tf_blocks.append("<b>[{} {}]</b> datos insuficientes\n".format(
                        tf_label, tf_id))
                    continue
                last = df.iloc[-1]
                price = float(last["close"])
                if tf_id == "15m":
                    anchor_price = price
                    anchor_df = df

                bias = detect_bias(df)
                masses = detect_pspace(df)
                lap = laplacian_check(df)

                if "alcista" in bias["bias"]:
                    direction = "long"
                elif "bajista" in bias["bias"]:
                    direction = "short"
                else:
                    direction = "long"  # default neutral
                dir_glyph = G["long"] if direction == "long" else G["short"]

                # F1 v5.0: niveles anti-stop-hunt con anclaje estructural ICT
                levels = calculate_levels_v2(df, direction, pspace=masses, tf=tf_id)

                h_factor = 1.0 if lap["active"] else 0.7
                pm_est = PHI * w_clock * h_factor * (1 + max(0, masses["count"] - 2) * 0.15)
                pmin = profile["PMASTER_MIN"]

                last_sig_ts = STATE.last_signal_ts_tf.get(tf_id)
                cooldown_min = profile["SIGNAL_COOLDOWN_MINUTES"]
                if last_sig_ts:
                    elapsed_min = (now_utc - last_sig_ts).total_seconds() / 60.0
                    if elapsed_min < cooldown_min:
                        cd_str = "{:.0f}m restantes".format(cooldown_min - elapsed_min)
                    else:
                        cd_str = "listo"
                else:
                    cd_str = "listo"

                risk_pct = (levels["risk"] / levels["entry"]) * 100
                sl_anchor_lbl = SL_ANCHOR_LABELS.get(
                    levels.get("sl_anchor", ""), levels.get("sl_anchor", "-"))
                tp_meta = levels.get("tp_meta") or []
                tp_kinds = [TP_KIND_LABELS.get(t["kind"], t["kind"]) for t in tp_meta[:4]]
                while len(tp_kinds) < 4:
                    tp_kinds.append("-")

                # F2 v5.0: QTE para TF anchor 15m (admin recibe block detallado)
                qte_admin_block = ""
                if tf_id == "15m" and QTE_AVAILABLE and qt is not None:
                    try:
                        qte_levels = {"entry": levels["entry"], "sl": levels["sl"],
                                      "tp1": levels["tp1"], "tp2": levels["tp2"],
                                      "tp3": levels["tp3"]}
                        qa15 = qt.quantum_analysis(
                            df, direction=direction, levels=qte_levels,
                            ict_module=ict_smc if ICT_MODULES_AVAILABLE else None,
                            n_paths=500, run_optimizer=True)
                        qte_admin_block = "\n" + qt.build_qte_block_admin(qa15) + "\n"
                    except Exception as ex:
                        log.warning("QTE en cmd_lectura TF15m fallo: {}".format(ex))

                block = (
                    "<b>[{lab} {tf}]</b>  Precio: ${px:.2f}\n"
                    "Bias: <b>{b}</b>  Masas P: {mc}  P_est: {pme:.2f}/{pmn:.2f}\n"
                    "Direccion sugerida: {dg} <b>{dir}</b>\n"
                    "Entry: <b>${e:.2f}</b>   SL: ${sl:.2f}  ({rp:.2f}%)\n"
                    "  anclado a {sla}\n"
                    "TP1: ${t1:.2f}  R:R {r1:.2f}  ({k1})\n"
                    "TP2: ${t2:.2f}  R:R {r2:.2f}  ({k2})\n"
                    "TP3: ${t3:.2f}  R:R {r3:.2f}  ({k3})\n"
                    "TP4: ${t4:.2f}  R:R {r4:.2f}  ({k4})\n"
                    "Cooldown: {cd}\n{qte}"
                ).format(
                    lab=tf_label, tf=tf_id, px=price,
                    b=bias["bias"].upper(), mc=masses["count"],
                    pme=pm_est, pmn=pmin,
                    dg=dir_glyph, dir=direction.upper(),
                    e=levels["entry"], sl=levels["sl"], rp=risk_pct,
                    sla=sl_anchor_lbl,
                    t1=levels["tp1"], r1=levels["rr_tp1"], k1=tp_kinds[0],
                    t2=levels["tp2"], r2=levels["rr_tp2"], k2=tp_kinds[1],
                    t3=levels["tp3"], r3=levels["rr_tp3"], k3=tp_kinds[2],
                    t4=levels["tp4"], r4=levels["rr_tp4"], k4=tp_kinds[3],
                    cd=cd_str, qte=qte_admin_block,
                )
                tf_blocks.append(block)
            except Exception as ex:
                log.warning("lectura TF {} error: {}".format(tf_id, ex))
                tf_blocks.append("<b>[{} {}]</b> error: {}\n".format(
                    tf_label, tf_id, str(ex)[:80]))

        # Header (usa precio del anchor 15m si esta disponible)
        header_price = anchor_price if anchor_price is not None else 0.0
        header = (
            "<b>LECTURA MULTI-TF - FQ v4.4</b>\n"
            "{fence}\n"
            "{when}  |  SOL: <b>${px:.2f}</b>\n"
            "Sesion: {ses}  (W={w:.2f})\n\n"
            "{thin}\n"
            "  NIVELES + ESTADO POR TIMEFRAME\n"
            "{thin}\n"
        ).format(
            fence=G["fence"], thin=G["thin"],
            when=cdmx_now_str(), px=header_price,
            ses=session.upper(), w=w_clock,
        )

        # Lectura Claude opcional sobre el TF anchor (15m)
        claude_block = ""
        if claude_ai.is_available() and anchor_df is not None:
            try:
                last_a = anchor_df.iloc[-1]
                macro = test_macro(exchange)
                direction_test = macro.get("direction") or "long"
                tecnica = test_technical(anchor_df, direction_test)
                liquidez = test_liquidity(anchor_df, direction_test)
                masses_a = detect_pspace(anchor_df)
                bias_a = detect_bias(anchor_df)
                theta_d = macro["passed"] and tecnica["passed"] and liquidez["passed"]
                basic_state = {
                    "price": float(last_a["close"]), "session": session, "w_clock": w_clock,
                    "bias": bias_a["bias"], "bias_score": bias_a["score"],
                    "mom_5": bias_a["mom_5"], "mom_20": bias_a["mom_20"],
                    "btc_chg": macro["btc_change"], "eth_chg": macro["eth_change"],
                    "tec_aligned": tecnica["aligned"], "tec_total": tecnica["total"],
                    "rsi6": liquidez["rsi6"], "rsi12": liquidez["rsi12"], "rsi24": liquidez["rsi24"],
                    "rsi14": float(last_a.get("rsi14") or 0),
                    "pspace_count": masses_a["count"], "theta_d": theta_d,
                    "ema50": float(last_a.get("ema50") or 0),
                    "ema200": float(last_a.get("ema200") or 0),
                    "macd": float(last_a.get("macd") or 0),
                }
                snapshot = mctx.snapshot_for_general(anchor_df, basic_state)
                reading = _escape_claude(claude_ai.tactical_general(snapshot))
                if reading:
                    claude_block = (
                        "\n{thin}\n"
                        "  LECTURA TACTICA (Claude Sonnet, TF anchor 15m)\n"
                        "{thin}\n"
                        "{r}\n\n"
                    ).format(thin=G["thin"], r=reading)
            except Exception as ex:
                log.warning("lectura Claude block error: {}".format(ex))

        tail = (
            "{thin}\n"
            "Estos niveles son la propuesta del bot por TF. El motor solo dispara\n"
            "automaticamente cuando P_master supera el min del perfil. SL no se\n"
            "mueve hacia atras (Regla 4).\n\n"
            "#FQ #Lectura #MultiTF"
        ).format(thin=G["thin"])

        return header + "\n".join(tf_blocks) + claude_block + tail
    except Exception as e:
        log.error("cmd_lectura: {}\n{}".format(e, traceback.format_exc()))
        return "Error en lectura: {}".format(str(e)[:200])

# ============================================================
# /analisis VIP - F1 v5.0 (curado, formato Mistral)
# ============================================================
def cmd_analisis_vip(exchange, ctx=None):
    """
    Version VIP de /analisis. Muestra el TF anchor 15m con formato Mistral curado
    liderado por el PLAN DE BATALLA. Reutiliza `ctx` (build_analisis_context) si el
    router lo pasa, evitando re-simular el QTE; si es None lo computa por su cuenta.
    """
    try:
        if ctx is None:
            ctx = build_analisis_context(exchange)
        if not ctx:
            return "Datos insuficientes para analisis."

        if VIP_FORMAT_AVAILABLE and vip_format is not None:
            return vip_format.build_vip_analisis(
                direction=ctx["direction"],
                levels=ctx["levels"],
                bias=ctx["bias"],
                pm_est=ctx["pm_est"],
                last=ctx["last"],
                qa=ctx.get("qa"),
                plan=ctx.get("plan"),
            )
        return "Formato VIP no disponible."
    except Exception as e:
        log.error("cmd_analisis_vip: {}\n{}".format(e, traceback.format_exc()))
        return "Error en analisis VIP: {}".format(str(e)[:200])

def cmd_timelines(exchange):
    """
    /timelines (admin) - Quantum Timelines Engine deep dive.
    Simula 2000 paths, muestra distribucion de regimenes, optimizer QAOA
    y ASCII histogram de los precios finales.
    """
    if not QTE_AVAILABLE or qt is None:
        return "QTE no disponible (modulo quantum_timelines.py no cargado)."

    try:
        df_15m = fetch_ohlcv(exchange, SYMBOL, "15m", limit=200)
        df_15m = add_indicators(df_15m)
        if len(df_15m) < 50:
            return "Datos insuficientes para QTE."

        last = df_15m.iloc[-1]
        masses = detect_pspace(df_15m)
        bias = detect_bias(df_15m)
        direction = "long" if "alcista" in bias["bias"] else (
            "short" if "bajista" in bias["bias"] else "long")

        levels = calculate_levels_v2(df_15m, direction, pspace=masses, tf="15m")
        qte_levels = {"entry": levels["entry"], "sl": levels["sl"],
                      "tp1": levels["tp1"], "tp2": levels["tp2"],
                      "tp3": levels["tp3"]}

        qa = qt.quantum_analysis(
            df_15m, direction=direction, levels=qte_levels,
            ict_module=ict_smc if ICT_MODULES_AVAILABLE else None,
            n_paths=2000, run_optimizer=True)

        # ASCII histogram de precios finales. Reusa los paths ya simulados por
        # quantum_analysis (final_prices) en vez de re-simular 2000 paths. Es
        # identico porque ambos usan seed=42 (default de quantum_analysis).
        finals = qa.get("final_prices")
        if finals is None:   # fallback defensivo si la key no esta
            paths, _ = qt.generate_paths(
                df_15m, n_paths=2000, horizon=qt.DEFAULT_HORIZON,
                ict_module=ict_smc if ICT_MODULES_AVAILABLE else None, seed=42)
            finals = paths[:, -1]
        nbins = 20
        hist, edges = _np_histogram_safe(finals, nbins)
        max_count = max(hist) if max(hist) > 0 else 1
        hist_lines = []
        for i, c in enumerate(hist):
            bar_len = int(c / max_count * 24)
            hist_lines.append("  ${:.2f}  {} {:d}".format(
                (edges[i] + edges[i+1]) / 2, "█" * bar_len, c))
        hist_block = "\n".join(hist_lines)

        block = qt.build_qte_block_admin(qa)
        rule = "━" * 30

        return (
            "<b>QTE DEEP DIVE</b>\n"
            "{rule}\n"
            "Direccion:     {dir}\n"
            "Entry:         ${e:.2f}\n"
            "SL anchor:     {sla}\n\n"
            "{block}\n\n"
            "DISTRIBUCION DE CIERRES FINALES (24h):\n"
            "{hist}\n"
            "{rule}\n"
            "#FQ #QTE #EmergentTime #Timelines"
        ).format(
            rule=rule, dir=direction.upper(), e=levels["entry"],
            sla=SL_ANCHOR_LABELS.get(
                levels.get("sl_anchor", ""), levels.get("sl_anchor", "-")),
            block=block, hist=hist_block,
        )
    except Exception as e:
        log.error("cmd_timelines: {}\n{}".format(e, traceback.format_exc()))
        return "Error en /timelines: {}".format(str(e)[:200])

def _np_histogram_safe(values, nbins):
    """Wrapper minimo para histogram de numpy sin importar np a nivel modulo."""
    import numpy as _np
    h, e = _np.histogram(values, bins=nbins)
    return h.tolist(), e.tolist()

def cmd_concepts(exchange=None):
    """Desglose de edge por concepto ICT individual (v3)"""
    if hasattr(ev, "format_concepts_telegram"):
        return ev.format_concepts_telegram()
    return "Modulo v3 no disponible. Ejecuta migrate_schema_v3 primero."

def cmd_weekend(exchange=None):
    """Estado del filtro fin de semana"""
    if not ICT_MODULES_AVAILABLE:
        return "Modulo killzones_pd no cargado."
    try:
        wk = killzones_pd.weekend_status()
        wstatus = "CERRADO (veto activo)" if wk["closed"] else "MERCADO ABIERTO"
        lines = [
            "<b>WEEKEND FILTER STATUS</b>",
            "",
            "Estado actual: <b>{}</b>".format(wstatus),
            "Dia UTC:       {} ({:.2f}h)".format(wk["weekday_label"], wk["hour_utc"]),
            "",
            "Veto: viernes 22:00 UTC -> domingo 22:00 UTC",
            "    = sabado completo + viernes noche/domingo am",
            "",
            "Toggle env: FQ_WEEKEND_VETO=0 para desactivar.",
        ]
        # Si hay perf data, agregar
        if hasattr(ev, "get_weekend_performance"):
            wp = ev.get_weekend_performance()
            if wp and wp.get("weekday") and wp.get("weekend"):
                lines.append("")
                lines.append("<b>Performance historica:</b>")
                wkd, wke = wp["weekday"], wp["weekend"]
                lines.append("  Weekday: n={} WR={:.0%} Exp={:+.2f}R".format(
                    wkd["n"], wkd["win_rate"], wkd["expectancy"]))
                lines.append("  Weekend: n={} WR={:.0%} Exp={:+.2f}R".format(
                    wke["n"], wke["win_rate"], wke["expectancy"]))
        return "\n".join(lines)
    except Exception as e:
        return "Error /weekend: {}".format(str(e)[:200])

def cmd_campo(exchange):
    """v4.1.1: Lectura on-demand del estado del campo (sin disparar senal)"""
    if not (ENABLE_ICT_LAYER and ICT_MODULES_AVAILABLE):
        return ("<b>Lectura de campo ICT/SMC</b>\n"
                "Flag desactivado. Setea FQ_ENABLE_ICT=1 en Railway para activar.")
    try:
        df_15m = add_indicators(fetch_ohlcv(exchange, SYMBOL, "15m", limit=200))
        df_1h  = add_indicators(fetch_ohlcv(exchange, SYMBOL, "1h",  limit=100))
        df_4h  = add_indicators(fetch_ohlcv(exchange, SYMBOL, "4h",  limit=100))
        try:
            df_1m = add_indicators(fetch_ohlcv(exchange, SYMBOL, "1m", limit=30))
        except Exception:
            df_1m = None
        masses = detect_pspace(df_15m)
        lap = laplacian_check(df_15m)
        field = ict_smc.read_field(df_15m, df_1h, df_4h, df_1m, masses, lap)
        n_v2 = ev.count_closed_v2_buckets() if hasattr(ev, "count_closed_v2_buckets") else 0
        killzones_pd.refine_field_timing(field, n_v2, 50)
        # Construir reporte como si la senal hubiese fallado en pre_check
        report = {"decision": "field_only", "failed_at": "manual",
                  "direction_inferred": field.propose_direction() or "?",
                  "reason": "Lectura on-demand"}
        return field_reports.build_field_only_report(field, report)
    except Exception as e:
        return "Error /campo: {}".format(str(e)[:200])

def evolution_periodic_hook(exchange):
    """
    Hook llamado cuando alguno de los TFs cierra vela nueva.
    1. Reconcilia outcomes pendientes en CADA TF (cada uno usa sus propias velas)
    2. Notifica cierres relevantes (TP3+ o SL grande)
    3. Trigger self-audit si toca (cada 25 cerradas)
    4. Backup ledger si toca (cada 10 totales)
    """
    try:
        # Progress checks: alertas intermedias en senales abiertas (TP1/TP2/TP3 hits)
        # Se ejecutan ANTES del reconcile para que las alertas se manden aunque
        # la senal cierre en TP4 en la misma vela.
        if PROGRESS_TRACKER_AVAILABLE and spt is not None:
            for tf_id in TIMEFRAMES:
                try:
                    df_open = fetch_ohlcv(exchange, SYMBOL, tf_id, limit=50)
                    if df_open is None or len(df_open) == 0:
                        continue
                    for sig in ev.get_open_signals():
                        events = spt.check_progress_events(sig, df_open)
                        for kind, price in events:
                            if not spt.mark_progress_event(sig["id"], kind, price):
                                continue
                            # TP3 de una senal REAL -> celebracion a TODOS (animo).
                            # El resto de eventos (tp1/tp2/be/parcial) son guia
                            # operativa: solo vip+admin.
                            if kind == "tp3_hit":
                                msg = spt.build_tp3_celebration(sig, price)
                                event_tiers = ["vip", "trial", "admin"]
                            else:
                                msg = spt.build_progress_alert(sig, kind, price)
                                event_tiers = ["vip", "admin"]
                            try:
                                broadcast_to_subscribers(msg, tiers=event_tiers)
                            except Exception as be:
                                log.error("progress broadcast error: {}".format(be))
                except Exception as e:
                    log.error("progress check [{}]: {}".format(tf_id, e))

        # Progress de ALERTAS TACTICAS (VIP): no estan en el ledger, se siguen
        # aparte. Mismo mensaje operativo (SL a BE en TP1, parcial, trailing).
        # Se chequea contra velas 5m (mas granular -> detecta el toque antes);
        # limit alto para cubrir el horizonte de seguimiento de la tactica.
        if (TACTICAL_TRACKING_ENABLED
                and TACTICAL_TRACKER_AVAILABLE and tactical_tracker is not None
                and PROGRESS_TRACKER_AVAILABLE and spt is not None):
            try:
                df_tac = fetch_ohlcv(exchange, SYMBOL, "5m", limit=200)
                for display, kind, price in tactical_tracker.check_tactical_progress(df_tac):
                    msg = spt.build_progress_alert(display, kind, price,
                                                   label=tactical_tracker.LABEL)
                    try:
                        broadcast_to_subscribers(msg, tiers=["vip", "trial", "admin"])
                    except Exception as be:
                        log.error("tactical progress broadcast error: {}".format(be))
            except Exception as e:
                log.error("tactical progress check: {}".format(e))

        closed = []
        # Reconciliar por TF: cada outcome se resuelve contra las velas del TF
        # que origino la senal (5m signal vs 5m candles, 1h vs 1h, etc.).
        for tf_id in TIMEFRAMES:
            try:
                closed.extend(ev.reconcile_outcomes(fetch_ohlcv, exchange, SYMBOL, tf_id))
            except Exception as e:
                log.error("reconcile [{}] error: {}".format(tf_id, e))
        for c in closed:
            outcome = c["outcome"]
            relevant = (
                outcome in ("tp3", "tp4") or
                (outcome == "sl") or
                (outcome == "timeout")
            )
            if relevant:
                if outcome.startswith("tp"):
                    emoji = "[OK]"
                elif outcome == "sl":
                    emoji = "[--]"
                else:
                    emoji = "[~~]"
                telegram_send(
                    "{em} <b>Senal #{id} cerrada</b>\n"
                    "Direccion: {dir}\n"
                    "Entry: ${ent:.2f} -> Salida: ${exi:.2f}\n"
                    "Outcome: {out}  PnL: {pnl:+.2f}R\n"
                    "Duracion: {mn} min\n"
                    "Tier: {tier}  P_master: {pm:.2f}".format(
                        em=emoji, id=c["id"], dir=c["direction"].upper(),
                        ent=c["entry_price"], exi=c["exit_price"],
                        out=outcome.upper(), pnl=c["pnl_r"],
                        mn=c["minutes_open"], tier=c["tier"],
                        pm=c["p_master_final"],
                    )
                )

        # Self-audit cada 25 cerradas
        if ev.should_trigger_audit() and claude_ai.is_available():
            n = ev.count_signals(closed_only=True)
            log.info("Triggering self-audit Opus (n={})".format(n))
            broadcast_to_subscribers(
                "<b>SELF-AUDIT EVOLUTIVO ACTIVADO</b>\n"
                "{} senales cerradas. Opus 4.6 auditando ledger...".format(n)
            )
            prompt = ev.build_audit_prompt_v3() if hasattr(ev, "build_audit_prompt_v3") else ev.build_audit_prompt()
            if prompt:
                opus_response = ev_claude.self_audit(prompt)
                metrics = ev.get_global_metrics()
                ev.save_audit(n, metrics, opus_response)
                audit_msg = (
                    "<b>AUDIT EVOLUTIVO - OPUS 4.6</b>\n"
                    "{thin}\n\n{r}\n\n"
                    "{thin}\n"
                    "Estas son SUGERENCIAS. RasDG decide.\n"
                    "#FQ #SelfAudit"
                ).format(thin=G["thin"], r=opus_response)
                for p in split_telegram_message(audit_msg):
                    broadcast_to_subscribers(p)

        # Backup cada N senales totales (configurable via FQ_BACKUP_EVERY_N).
        # mark_backup_done() evita re-envio en cada cierre de vela.
        if ev.should_trigger_backup():
            try:
                send_db_backup_to_telegram()
            finally:
                ev.mark_backup_done()

    except Exception as e:
        log.error("evolution_periodic_hook error: {}\n{}".format(
            e, traceback.format_exc()))

# ============================================================
# MAIN
# ============================================================
def main():
    global COMMANDS
    log.info("=" * 70)
    log.info("  FQ v5.1 SIGNAL BOT - MISTRAL EMERGENT TIME EDITION")
    log.info("  Window: 24H | Macro: {:.2f}% | Intra:{}m | P-Space>={} | P_master>={:.2f}".format(
        MACRO_THRESHOLD_PCT * 100, INTRA_CANDLE_MINUTES, PSPACE_MIN_MASSES, PMASTER_MIN))
    log.info("  Claude integration: {}".format("ENABLED" if claude_ai.is_available() else "DISABLED"))
    log.info("  kappa_evo cap: +-{:.0%}  audit cada {} cerradas".format(
        ev.KAPPA_EVO_MAX, ev.AUDIT_EVERY_N_CLOSED))
    log.info("=" * 70)

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("FATAL: Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID env vars")
        sys.exit(1)

    # Inicializar ledger evolutivo
    ev.init_db()
    # Migracion schema v2 (idempotente)
    if hasattr(ev, "migrate_schema_v2"):
        try:
            ev.migrate_schema_v2()
            log.info("Schema v2 ICT/SMC migrado")
        except Exception as e:
            log.warning("migrate_schema_v2: {}".format(e))
    # Migracion schema v3 (idempotente - concepts ICT + Thompson)
    if hasattr(ev, "migrate_schema_v3"):
        try:
            ev.migrate_schema_v3()
            log.info("Schema v3 ICT concepts + Thompson migrado")
        except Exception as e:
            log.warning("migrate_schema_v3: {}".format(e))
    # Migracion schema v4 (idempotente - dimension TF para emision multi-timeframe)
    if hasattr(ev, "migrate_schema_v4"):
        try:
            ev.migrate_schema_v4()
            log.info("Schema v4 tf_id migrado")
        except Exception as e:
            log.warning("migrate_schema_v4: {}".format(e))
    log.info("Evolution ledger: {}".format(ev.DB_PATH))
    log.info("ICT layer:    {}".format("ON" if (ENABLE_ICT_LAYER and ICT_MODULES_AVAILABLE) else "OFF"))
    log.info("Weekend veto: {}{}".format(
        "ON" if WEEKEND_VETO_LEGACY else "OFF",
        " (admin-only: genera en finde, entrega solo admin)" if WEEKEND_ADMIN_ONLY else ""))

    # Inicializar sistema VIP
    if VIP_ENABLED:
        try:
            vip.init_vip_db()
            log.info("VIP system: {}".format(vip.VIP_DB_PATH))
        except Exception as e:
            log.warning("VIP init warning (non-fatal): {}".format(e))
    else:
        log.warning("VIP system disabled (vip_system.py not found)")

    exchange = ccxt.okx({"enableRateLimit": True, "timeout": 20000})

    # FQ v4.2 MISTRAL: comandos visibles en BotFather son los 6 minimal.
    # Los antiguos siguen funcionando como aliases internos para no romper
    # a quien los tenga memorizados, pero no aparecen en el menu publico.
    COMMANDS = {
        # ============ VIP VISIBLES (BotFather) ============
        "/start":    lambda exc=None: cmd_help(),
        "/help":     lambda exc=None: cmd_help(),
        "/about":    lambda exc=None: cmd_about(),
        "/status":   cmd_status,
        "/lectura":  cmd_lectura,
        # /miestado y /renovar son manejados en vip_system handlers arriba
        # ============ ALIASES INTERNOS (ocultos del menu BotFather) ============
        "/analisis": cmd_lectura,    # consolidado en /lectura
        "/niveles":  cmd_lectura,
        "/pspace":   cmd_lectura,
        "/claude":   cmd_lectura,
        "/ia":       cmd_lectura,
        "/sesion":   lambda exc=None: cmd_sesion(),  # legacy alias
        "/macro":    cmd_macro,                       # legacy alias
        # ============ ADMIN ONLY (gated por chat_id en command_listener) ============
        "/audit":     cmd_audit_manual,
        "/entropy":   lambda exc=None: cmd_entropy(),
        "/metrics":   lambda exc=None: cmd_metrics(),
        "/ledger":    lambda exc=None: cmd_ledger(),
        "/evolve":    lambda exc=None: cmd_evolve(),
        "/campo":     cmd_campo,
        "/concepts":  lambda exc=None: cmd_concepts(),
        "/weekend":   lambda exc=None: cmd_weekend(),
        # ============ ADMIN v4.3 - capa ML ============
        "/atribucion": lambda exc=None: cmd_atribucion(),
        "/regimen":    cmd_regimen,
        "/sweep":      lambda exc=None: cmd_sweep(),
        # ============ ADMIN v5.0 - Quantum Timelines ============
        "/timelines":  cmd_timelines,
    }

    # Comandos que reciben follow-up automatico de Claude
    # NOTA: /analisis usa routing tier-aware en command_listener (NO va aqui)
    global CLAUDE_FOLLOWUP
    CLAUDE_FOLLOWUP = {
        "/pspace":   claude_followup_pspace,
        "/niveles":  claude_followup_niveles,
    }

    claude_status = "ACTIVO" if claude_ai.is_available() else "INACTIVO"
    telegram_send(
        "{header}\n"
        "\n"
        "  Motor en pista · eval cada 15 min\n"
        "  SOL/USDT · OKX\n"
        "  Claude: <b>{cs}</b>".format(
            header=_brand.lux_header("FQ · Bot online", "Luces verdes"),
            cs=claude_status)
    )

    t = threading.Thread(target=command_listener, args=(exchange,), daemon=True)
    t.start()

    # Estado por TF: cada TF rastrea su propia vela actual, intra-ts y cooldown
    last_candle_ts = {tf: None for tf in TIMEFRAMES}
    last_intra_ts  = {tf: None for tf in TIMEFRAMES}
    cooldowns = {tf: timedelta(minutes=TF_PROFILES[tf]["SIGNAL_COOLDOWN_MINUTES"])
                 for tf in TIMEFRAMES}

    log.info("Main loop started - multi-TF: {}".format(", ".join(
        "{}({})".format(tf, TF_PROFILES[tf]["label"]) for tf in TIMEFRAMES)))
    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            any_new_candle = False  # Para evolution_periodic_hook
            new_candle_tfs = set()  # TFs que cerraron vela nueva esta iteracion

            # Iteracion secuencial sobre los 3 TFs. Cooldowns independientes por TF:
            # una senal en 5m NO bloquea 15m ni 1h. Intencional - no se pierde
            # ninguna oportunidad inter-TF.
            for tf_id in TIMEFRAMES:
                try:
                    df_check = fetch_ohlcv(exchange, SYMBOL, tf_id, limit=2)
                    current_ts = df_check["timestamp"].iloc[-1]
                    candle_dt = current_ts.to_pydatetime().replace(tzinfo=timezone.utc)
                    elapsed_min = (now_utc - candle_dt).total_seconds() / 60.0
                    intra_threshold = TF_PROFILES[tf_id]["INTRA_CANDLE_MINUTES"]

                    is_new_candle  = (last_candle_ts[tf_id] is None or
                                      current_ts > last_candle_ts[tf_id])
                    is_intra_ready = (elapsed_min >= intra_threshold and
                                      last_intra_ts[tf_id] != current_ts and
                                      not is_new_candle)

                    if is_new_candle:
                        last_candle_ts[tf_id] = current_ts
                        last_intra_ts[tf_id]  = None
                        any_new_candle = True
                        new_candle_tfs.add(tf_id)
                        log.info("[{}] New candle closed: {}".format(tf_id, current_ts))

                    should_eval = is_new_candle or is_intra_ready
                    eval_intra  = is_intra_ready and not is_new_candle

                    if should_eval:
                        if eval_intra:
                            log.info("[{}] Intra-candle eval at {:.1f}m".format(tf_id, elapsed_min))
                            last_intra_ts[tf_id] = current_ts
                        last_ts = STATE.last_signal_ts_tf.get(tf_id)
                        if last_ts and (now_utc - last_ts) < cooldowns[tf_id]:
                            rem = cooldowns[tf_id] - (now_utc - last_ts)
                            log.info("[{}] Cooldown active: {}".format(tf_id, rem))
                        else:
                            evaluate_setup(exchange, tf_id=tf_id, intra=eval_intra)
                            # last_signal_ts_tf se actualiza dentro de _evaluate_setup_v411
                            # cuando la senal efectivamente dispara y broadcastea.
                except Exception as e:
                    log.error("Eval [{}] error: {}".format(tf_id, e))

            # EVOLUTION HOOK - corre si alguno de los TFs cerro vela nueva
            if any_new_candle:
                evolution_periodic_hook(exchange)

            # RADAR proactivo / ALERTA TACTICA (FQ v5.3):
            #   - Corre en FIELD_TIMEFRAMES (default 5m+15m; 1m opt-in, 3m retirado).
            #   - 15m mantiene el comportamiento original (admin-only).
            #   - 5m es el canal de campo afinado: cierra junto con el motor clasico
            #     (esta en TIMEFRAMES) y el RADAR corre en su vela nueva con un gate
            #     de conviccion fuerte. Si una senal clasica disparo en 5m hace poco,
            #     radar_check se autodescarta (no encima senales).
            #   - 1m/3m (solo si se opta in) son via "señal de campo" pura que el
            #     motor clasico no atiende; se chequean cada iteracion con su propio
            #     cooldown porque sus velas son rapidas y el loop no las trackea.
            for field_tf in FIELD_TIMEFRAMES:
                try:
                    if field_tf in new_candle_tfs:
                        radar_check(exchange, field_tf)
                        continue
                    # Para 1m/3m que NO estan en TIMEFRAMES (motor clasico), el loop
                    # no actualiza last_candle_ts; chequeamos directo cada iteracion
                    # con su propio cooldown interno (RADAR_LAST_TF).
                    if field_tf not in TIMEFRAMES and field_tf in ("1m", "3m"):
                        radar_check(exchange, field_tf)
                except Exception as rad_e:
                    log.warning("radar_check loop [{}]: {}".format(field_tf, rad_e))

            # Reset diario de signals_today
            today = cdmx_now().date()
            if STATE.day_marker is None or STATE.day_marker != today:
                with STATE.lock:
                    STATE.day_marker = today
                    if STATE.day_marker is not None:
                        STATE.signals_today = 0

            # Polling crypto payments cada 5 min (no critico)
            if VIP_ENABLED and int(now_utc.timestamp()) % 300 < LOOP_SECONDS:
                try:
                    confirmed = pay.crypto_polling_check()
                    for pid in confirmed:
                        log.info("Crypto payment confirmed: {}".format(pid))
                        telegram_send(
                            "<b>Pago crypto confirmado</b>\n"
                            "Payment #{} verificado on-chain.\n"
                            "Suscripcion VIP activada.".format(pid))
                except Exception as e:
                    log.warning("Crypto polling error: {}".format(e))

            # Latido para el watchdog (cada iteracion del loop ~60s)
            try:
                heartbeat.beat("vip")
            except Exception:
                pass

            # Heartbeat cada hora con estado por TF
            now_h = int(now_utc.timestamp()) // 3600
            if not hasattr(STATE, "_last_heartbeat_h") or STATE._last_heartbeat_h != now_h:
                STATE._last_heartbeat_h = now_h
                tf_summaries = []
                for tf in TIMEFRAMES:
                    d_tf = STATE.last_eval_diagnostic_tf.get(tf) or {}
                    tf_summaries.append("{}={}".format(tf, d_tf.get("stage", "?")))
                log.info("HEARTBEAT | Senales hoy:{} total:{} | TFs: {}".format(
                    STATE.signals_today, STATE.signals_total,
                    " ".join(tf_summaries)))

            time.sleep(LOOP_SECONDS)
        except KeyboardInterrupt:
            log.info("Shutdown requested")
            break
        except Exception as e:
            log.error("Main loop error: {}\n{}".format(e, traceback.format_exc()))
            time.sleep(LOOP_SECONDS)

if __name__ == "__main__":
    main()
