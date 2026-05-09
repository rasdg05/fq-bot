# -*- coding: utf-8 -*-
"""
================================================================================
  FQ v4.1 SIGNAL BOT v3.1 - "BUGATTI EDITION + CLAUDE COPILOT"
  Fibonacci Cuantico v4.1 - Emergent Time and Curved Price-Space
  by RasDG_Sol
================================================================================

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
import time
import logging
import threading
import traceback
from datetime import datetime, timezone, timedelta
import ccxt
import pandas as pd
import pandas_ta as ta
import requests

# Modulos FQ v3.1
import claude_integration as claude_ai
import market_context as mctx

# ============================================================
# CONFIG
# ============================================================
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

SYMBOL      = "SOL-USDT-SWAP"
SYMBOL_BTC  = "BTC-USDT-SWAP"
SYMBOL_ETH  = "ETH-USDT-SWAP"
TIMEFRAME   = "15m"

LOOP_SECONDS          = 60
INTRA_CANDLE_MINUTES  = 12
SIGNAL_COOLDOWN_HOURS = 2

# 24H operativo - W_clock solo modula
WINDOW_24H = True

# FQ v4.1 thresholds (calibrado 2026-05-07 v3.0)
MACRO_THRESHOLD_PCT = 0.0008    # 0.08%
TECH_MIN_ALIGNED    = 5         # de 7 indicadores
PSPACE_MIN_MASSES   = 2
PMASTER_MIN = 2.30      # calibrado post-validacion abril 2026
RR_MIN_TP_DIVINO    = 1.8

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

# Glyphs UI - jerarquia profesional
G = {
    "ok":    "[OK]",
    "fail":  "[--]",
    "warn":  "[!]",
    "long":  "[LONG]",
    "short": "[SHORT]",
    "phi":   "phi",
    "div":   "*",
    "bullet": "-",
    "arrow": "->",
    "fence": "================================",
    "thin":  "--------------------------------",
}

# ============================================================
# GLOBAL STATE
# ============================================================
class BotState:
    def __init__(self):
        self.start_time           = datetime.now(timezone.utc)
        self.last_signal_ts       = None
        self.last_signal_dir      = None
        self.last_signal_price    = 0.0
        self.last_signal_levels   = None
        self.signals_today        = 0
        self.signals_total        = 0
        self.last_btc_chg         = 0.0
        self.last_eth_chg         = 0.0
        self.last_sol_price       = 0.0
        self.last_eval_ts         = None
        self.last_eval_result     = "Esperando primera vela"
        self.telegram_offset      = 0
        self.day_marker           = None
        self.lock                 = threading.Lock()

STATE = BotState()

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("fq_bot_v3")

# ============================================================
# TELEGRAM
# ============================================================
def telegram_send(text, chat_id=None):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")
        return False
    target = chat_id or TELEGRAM_CHAT_ID
    url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN)
    payload = {
        "chat_id": target,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            log.warning("Telegram send failed {}: {}".format(r.status_code, r.text[:200]))
            return False
        return True
    except Exception as e:
        log.error("Telegram exception: {}".format(e))
        return False

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
def fetch_ohlcv(exchange, symbol, timeframe, limit=200):
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df

def add_indicators(df):
    df = df.copy()
    df["rsi6"]  = ta.rsi(df["close"], length=6)
    df["rsi12"] = ta.rsi(df["close"], length=12)
    df["rsi14"] = ta.rsi(df["close"], length=14)
    df["rsi24"] = ta.rsi(df["close"], length=24)
    df["ema9"]   = ta.ema(df["close"], length=9)
    df["ema20"]  = ta.ema(df["close"], length=20)
    df["ema50"]  = ta.ema(df["close"], length=50)
    df["ema200"] = ta.ema(df["close"], length=200)
    df["sma20"] = ta.sma(df["close"], length=20)
    df["sma50"] = ta.sma(df["close"], length=50)
    bb = ta.bbands(df["close"], length=20, std=2)
    if bb is not None and not bb.empty:
        df["bb_lower"] = bb.iloc[:, 0]
        df["bb_mid"]   = bb.iloc[:, 1]
        df["bb_upper"] = bb.iloc[:, 2]
    macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd_df is not None and not macd_df.empty:
        df["macd"]        = macd_df.iloc[:, 0]
        df["macd_signal"] = macd_df.iloc[:, 2]
    atr = ta.atr(df["high"], df["low"], df["close"], length=14)
    if atr is not None:
        df["atr14"] = atr
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    return df

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
    out = {"passed": False, "direction": None, "btc_change": 0.0, "eth_change": 0.0}
    try:
        btc = fetch_ohlcv(exchange, SYMBOL_BTC, "15m", limit=20)
        eth = fetch_ohlcv(exchange, SYMBOL_ETH, "15m", limit=20)
        btc_chg = (btc["close"].iloc[-1] - btc["close"].iloc[-4]) / btc["close"].iloc[-4]
        eth_chg = (eth["close"].iloc[-1] - eth["close"].iloc[-4]) / eth["close"].iloc[-4]
        out["btc_change"] = btc_chg * 100
        out["eth_change"] = eth_chg * 100
        with STATE.lock:
            STATE.last_btc_chg = btc_chg * 100
            STATE.last_eth_chg = eth_chg * 100
        if btc_chg > MACRO_THRESHOLD_PCT and eth_chg > MACRO_THRESHOLD_PCT:
            out["passed"] = True
            out["direction"] = "long"
        elif btc_chg < -MACRO_THRESHOLD_PCT and eth_chg < -MACRO_THRESHOLD_PCT:
            out["passed"] = True
            out["direction"] = "short"
    except Exception as e:
        log.error("Macro test error: {}".format(e))
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
        tp3 = entry * (1 + (rng / entry) * PHI_INV)
        tp4 = entry + (rng * PHI_INV * PHI)
    else:
        ema50_v = last.get("ema50")
        ema50_v = float(ema50_v) if ema50_v is not None and not pd.isna(ema50_v) else entry * 1.01
        sl  = max(ema50_v, float(df["high"].iloc[-10:].max())) * 1.002
        tp1 = entry - (rng * PHI_INV * PHI_INV)
        tp2 = entry - (rng * PHI_INV)
        tp3 = entry * (1 - (rng / entry) * PHI_INV)
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

    msg = (
        "<b>SENAL FQ v4.1 - DECOHERENCIA Theta(D) = 1</b>{intra}\n\n"
        "<b>{side_glyph}  SOL/USDT  {side}</b>\n"
        "Conviccion: <b>{tier}</b>{asia_warn}\n"
        "{when}  |  Sesion: <b>{session}</b> (W={w:.2f})\n\n"
        "{fence}\n"
        "  NIVELES DIVINOS\n"
        "{fence}\n"
        "Entrada:  <b>${entry:.2f}</b>\n"
        "SL:       ${sl:.2f}  ({risk_pct:.2f}%)\n\n"
        "TP1 30%:  ${tp1:.2f}    R:R {rr1:.2f}\n"
        "TP2 30%:  ${tp2:.2f}    R:R {rr2:.2f}\n"
        "TP3 25%:  ${tp3:.2f} {div}  R:R {rr3:.2f}\n"
        "TP4 15%:  ${tp4:.2f}    R:R {rr4:.2f}\n\n"
        "Apalancamiento max:  <b>{lev}</b>\n"
        "Tamano sugerido:     {size} equity\n\n"
        "{fence}\n"
        "  GATE Theta(D) = 1\n"
        "{fence}\n"
        "{ok} Macro:    BTC {btc:+.2f}% | ETH {eth:+.2f}%\n"
        "{ok} Tecnica:  {tec_a}/{tec_t} indicadores alineados\n"
        "{ok} Liquidez: RSI 6/12/24 = {r6:.0f}/{r12:.0f}/{r24:.0f}\n"
        "{ok} P-Space:  {pscount} masas en confluencia\n"
        "{lap_g} Laplaciano: ratio {lap_r:.2f}\n\n"
        "<b>Masas en zona:</b>\n{masas}\n\n"
        "<b>P_master = {pm:.2f}</b>  (min {pmin:.2f})\n"
        "P_master = Theta(D) {dot} kappa(p) {dot} phi^n {dot} W {dot} H_lap\n\n"
        "{fence}\n"
        "  INVALIDACION\n"
        "{fence}\n"
        "{bullet} Cierre 15m {cmp} ${sl:.2f} {arrow} CERRAR\n"
        "{bullet} 90 min sin progreso a TP1 {arrow} REVISAR\n"
        "{bullet} SL nunca se mueve hacia abajo (Regla 4)\n\n"
        "#FQv41 #SOLUSDT #{tag}"
    ).format(
        intra=intra_note, side_glyph=side_glyph, side=side, tier=tier, asia_warn=asia_warn,
        when=cdmx_now_str(), session=session.upper(), w=w_clock,
        entry=levels["entry"], sl=levels["sl"],
        risk_pct=(levels["risk"] / levels["entry"] * 100),
        tp1=levels["tp1"], rr1=levels["rr_tp1"],
        tp2=levels["tp2"], rr2=levels["rr_tp2"],
        tp3=levels["tp3"], rr3=levels["rr_tp3"],
        tp4=levels["tp4"], rr4=levels["rr_tp4"],
        lev=leverage, size=sizing,
        btc=decoh["macro"]["btc_change"], eth=decoh["macro"]["eth_change"],
        tec_a=decoh["tecnica"]["aligned"], tec_t=decoh["tecnica"]["total"],
        r6=decoh["liquidez"]["rsi6"], r12=decoh["liquidez"]["rsi12"], r24=decoh["liquidez"]["rsi24"],
        pscount=masses["count"], lap_r=lap["ratio"],
        lap_g=G["ok"] if lap["active"] else G["fail"],
        ok=G["ok"], div=G["div"], dot="*",
        bullet=G["bullet"], arrow=G["arrow"],
        masas=masas_text, pm=p_master, pmin=PMASTER_MIN,
        cmp="<" if direction == "long" else ">",
        tag=side, fence=G["fence"],
    )
    return msg

# ============================================================
# COMMAND: /help
# ============================================================
def cmd_help():
    return (
        "<b>FQ v4.1 BOT v3.1 - BUGATTI + CLAUDE</b>\n"
        "{fence}\n\n"
        "<b>COMANDOS:</b>\n"
        "/status    Estado bot, mercado, ultima senal\n"
        "/analisis  Analisis FQ + lectura Claude (Sonnet)\n"
        "/niveles   Plan de entrada + afinacion Claude\n"
        "/pspace    Masas P-Space + libro + lectura Claude\n"
        "/sesion    Sesion actual + W_clock dinamico\n"
        "/macro     Decoherencia macro BTC/ETH\n"
        "/claude    Lectura tactica completa (Sonnet 4.5)\n"
        "/ia        Alias de /claude\n"
        "/about     Sobre el sistema FQ v4.1\n"
        "/help      Esta ayuda\n\n"
        "{fence}\n\n"
        "<b>MOTOR DE SENALES + CLAUDE COPILOT</b>\n\n"
        "Monitoreo 24/7. Solo emite senal con Theta(D) = 1.\n"
        "Senales con P_master >= phi^3 (4.236) reciben\n"
        "co-pilot Opus 4.6 con afinacion automatica.\n\n"
        "Ventana operativa: <b>24 HORAS</b>\n"
        "Asia (W=0.50) reduce sizing automaticamente.\n\n"
        "<b>QUE VE CLAUDE:</b>\n"
        "{b} Datos internos: indicadores, masas, decoherencia\n"
        "{b} Datos externos: funding, OI, L/S ratio, walls\n"
        "{b} Eventos: CHoCH, breakouts, divergencias, volumen\n"
        "{b} Evolucion vela-a-vela ultimas 5 velas\n\n"
        "El silencio es disciplina. Calidad sobre cantidad.\n\n"
        "#FQv41 #BugattiEdition"
    ).format(fence=G["fence"], b=G["bullet"])

# ============================================================
# COMMAND: /about
# ============================================================
def cmd_about():
    return (
        "<b>FIBONACCI CUANTICO v4.1</b>\n"
        "<i>Emergent Time and Curved Price-Space</i>\n"
        "by RasDG_Sol  |  Bot v3.0 Bugatti Edition\n"
        "{fence}\n\n"
        "<b>FUNDAMENTOS</b>\n\n"
        "El mercado no esta en un estado definido.\n"
        "Esta en superposicion de historias competidoras.\n"
        "Una senal solo existe cuando colapsan.\n\n"
        "<b>CUATRO PILARES:</b>\n"
        "I.   Decoherencia 3/3 (Hartle, Solvay 2005)\n"
        "II.  Tiempo emergente W_clock (Page-Wootters)\n"
        "III. P-Space curvado kappa(p) (Oreste 2011)\n"
        "IV.  Laplaciano discreto (Knill, Harvard 2020)\n\n"
        "{thin}\n"
        "<b>MASTER EQUATION v4.1</b>\n"
        "{thin}\n"
        "P_master = Theta(D) {dot} kappa(p) {dot} phi^n {dot} W_clock {dot} H_lap\n\n"
        "Si Theta(D) = 0 {arrow} P_master = 0 {arrow} no trade.\n"
        "Sin excepcion. Sin override.\n\n"
        "<b>CONSTANTES:</b>\n"
        "phi    = 1.6180339887\n"
        "phi^2  = 2.6180\n"
        "phi^3  = 4.2360\n"
        "alpha  = 1/137.507\n"
        "B      = phi^2/alpha + e + pi = 364.6247\n\n"
        "<b>PARAMETROS ACTUALES:</b>\n"
        "Par:        SOL/USDT Perpetual\n"
        "Exchange:   OKX (datos)\n"
        "Timeframe:  15 minutos\n"
        "Ventana:    24 HORAS (modulado por W_clock)\n"
        "Macro thr:  0.08%\n"
        "P-Space:    minimo 2 masas\n"
        "P_master:   minimo 2.618 (phi^2)\n"
        "Cooldown:   2h entre senales\n"
        "Leverage:   max 8x (phi^3-coupled)\n\n"
        "#FQv41 #RasDG"
    ).format(fence=G["fence"], thin=G["thin"], dot="*", arrow=G["arrow"])

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
        "<b>STATUS - FQ v4.1 BOT v3.0</b>\n"
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
        "#FQv41 #Status"
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
        "<b>SESION ACTIVA - FQ v4.1</b>\n"
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
        "#FQv41 #Sesion"
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
        "#FQv41 #Macro"
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
            "#FQv41 #PSpace"
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
            "<b>NIVELES + TRIGGERS - FQ v4.1</b>\n"
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
            "#FQv41 #Niveles"
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

        if theta_d:
            veredicto = "{} SETUP EN FORMACION - candidato real".format(G["ok"])
        else:
            veredicto = "{} SIN SETUP - mercado en superposicion".format(G["fail"])

        ico = lambda b: G["ok"] if b else G["fail"]

        return (
            "<b>ANALISIS FQ v4.1 - LIVE</b>\n"
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
            "{thin}\n"
            "  VEREDICTO MATEMATICO\n"
            "{thin}\n"
            "{ver}\n\n"
            "#FQv41 #Analisis"
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
            bb=bb_pos, ver=veredicto,
        )
    except Exception as e:
        log.error("Error analisis: {}\n{}".format(e, traceback.format_exc()))
        return "Error al analizar: {}".format(e)

# ============================================================
# EVALUATE SETUP - signal engine
# ============================================================
def evaluate_setup(exchange, intra=False):
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

    macro = test_macro(exchange)
    if not macro["passed"]:
        msg = "Macro NO decoherente (BTC {:+.2f}% / ETH {:+.2f}%)".format(
            macro["btc_change"], macro["eth_change"])
        log.info(msg)
        STATE.last_eval_result = msg
        return False
    direction = macro["direction"]

    tecnica = test_technical(df, direction)
    if not tecnica["passed"]:
        msg = "Tecnica NO decoherente ({}/{})".format(tecnica["aligned"], tecnica["total"])
        log.info(msg)
        STATE.last_eval_result = msg
        return False

    liquidez = test_liquidity(df, direction)
    if not liquidez["passed"]:
        msg = "Liquidez NO decoherente (RSI {:.0f}/{:.0f}/{:.0f})".format(
            liquidez["rsi6"], liquidez["rsi12"], liquidez["rsi24"])
        log.info(msg)
        STATE.last_eval_result = msg
        return False

    masses = detect_pspace(df)
    if not masses["passed"]:
        msg = "P-Space insuficiente ({} masas)".format(masses["count"])
        log.info(msg)
        STATE.last_eval_result = msg
        return False

    lap = laplacian_check(df)
    h_factor = 1.0 if lap["active"] else 0.7

    p_master = (PHI ** 1) * w_clock * h_factor
    p_master *= 1 + (masses["count"] - 2) * 0.15

    if p_master < PMASTER_MIN:
        msg = "P_master {:.2f} < {:.2f} (W={:.2f}, sesion {})".format(
            p_master, PMASTER_MIN, w_clock, session)
        log.info(msg)
        STATE.last_eval_result = msg
        return False

    levels = calculate_levels(df, direction)
    if levels["rr_tp3"] < RR_MIN_TP_DIVINO:
        msg = "R:R TP divino {:.2f} < {:.2f}".format(levels["rr_tp3"], RR_MIN_TP_DIVINO)
        log.info(msg)
        STATE.last_eval_result = msg
        return False

    decoh = {"macro": macro, "tecnica": tecnica, "liquidez": liquidez}
    msg = build_signal_msg(direction, levels, decoh, masses, session, w_clock, p_master, lap, intra)
    if telegram_send(msg):
        log.info("SIGNAL SENT: {} P_master={:.2f} W={:.2f} intra={}".format(
            direction.upper(), p_master, w_clock, intra))
        with STATE.lock:
            STATE.last_signal_ts     = datetime.now(timezone.utc)
            STATE.last_signal_dir    = direction
            STATE.last_signal_price  = levels["entry"]
            STATE.last_signal_levels = levels
            STATE.signals_today     += 1
            STATE.signals_total     += 1
            STATE.last_eval_result   = "SENAL ENVIADA: {} @ ${:.2f}".format(
                direction.upper(), levels["entry"])

        # OPUS CO-PILOT para senales de alta conviccion (P_master >= phi^3)
        if claude_ai.is_available() and claude_ai.is_high_conviction(p_master):
            try:
                log.info("Triggering Opus co-pilot for high-conviction signal")
                telegram_send(
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
                opus_reading = claude_ai.signal_copilot(snapshot)
                if opus_reading:
                    opus_msg = (
                        "<b>OPUS 4.6 - REVISION FINAL DE SENAL</b>\n"
                        "{thin}\n\n{r}\n\n"
                        "{thin}\nDecision final: SIEMPRE tuya.\n"
                        "El gate matematico ya valido el setup.\n"
                        "Esta lectura es para AFINAR, no validar.\n\n"
                        "#FQv41 #Opus #SenalAltaConviccion"
                    ).format(thin=G["thin"], r=opus_reading)
                    # Split si es muy largo
                    parts = split_telegram_message(opus_msg)
                    for p in parts:
                        telegram_send(p)
            except Exception as e:
                log.error("Opus co-pilot error: {}\n{}".format(e, traceback.format_exc()))

        return True
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
            "#FQv41 #Setup"
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
        reading = claude_ai.tactical_general(snapshot)

        return (
            "<b>CLAUDE - LECTURA TACTICA</b>\n"
            "{fence}\n\n"
            "{when}  |  SOL ${px:.2f}\n"
            "Sesion: {ses} (W={w:.2f}) | Sesgo: {bias}\n\n"
            "{thin}\n\n"
            "{reading}\n\n"
            "{thin}\n"
            "Modelo: Sonnet 4.5  |  Co-pilot FQ v4.1\n\n"
            "#FQv41 #Claude"
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
        reading = claude_ai.tactical_general(snapshot)
        return (
            "<b>CLAUDE - Lectura tactica del analisis</b>\n"
            "{thin}\n\n{r}\n\n"
            "{thin}\nModelo: Sonnet 4.5\n#FQv41 #Claude"
        ).format(thin=G["thin"], r=reading)
    except Exception as e:
        log.error("Claude followup analisis error: {}".format(e))
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
        reading = claude_ai.tactical_pspace(snapshot)
        return (
            "<b>CLAUDE - Lectura P-Space + libro</b>\n"
            "{thin}\n\n{r}\n\n"
            "{thin}\nModelo: Sonnet 4.5\n#FQv41 #Claude"
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
        reading = claude_ai.tactical_niveles(snapshot)
        return (
            "<b>CLAUDE - Afinacion del plan</b>\n"
            "{thin}\n\n{r}\n\n"
            "{thin}\nModelo: Sonnet 4.5\n#FQv41 #Claude"
        ).format(thin=G["thin"], r=reading)
    except Exception as e:
        log.error("Claude followup niveles error: {}".format(e))
        return None


def command_listener(exchange):
    log.info("Command listener started")
    while True:
        try:
            updates = telegram_get_updates(STATE.telegram_offset)
            for upd in updates:
                STATE.telegram_offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                text = (msg.get("text") or "").strip().lower()
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if chat_id != TELEGRAM_CHAT_ID:
                    continue

                if "@" in text:
                    text = text.split("@")[0]

                log.info("Cmd received: {}".format(text))

                if text in COMMANDS:
                    handler = COMMANDS[text]
                    try:
                        if text == "/analisis":
                            telegram_send("Analizando mercado en tiempo real...", chat_id)
                        elif text == "/niveles":
                            telegram_send("Construyendo plan de entrada FQ...", chat_id)
                        elif text == "/pspace":
                            telegram_send("Mapeando masas P-Space y orderbook...", chat_id)
                        elif text == "/claude":
                            telegram_send("Espejo en tiempo real - consultando Claude...", chat_id)
                        response = handler(exchange) if handler.__code__.co_argcount > 0 else handler()
                        send_long(response, chat_id)

                        # Claude follow-up para comandos compatibles
                        if text in CLAUDE_FOLLOWUP and claude_ai.is_available():
                            telegram_send("Claude esta interpretando los datos...", chat_id)
                            followup = CLAUDE_FOLLOWUP[text](exchange)
                            if followup:
                                send_long(followup, chat_id)
                    except Exception as e:
                        log.error("Error executing {}: {}\n{}".format(text, e, traceback.format_exc()))
                        telegram_send("Error ejecutando comando: {}".format(e), chat_id)
            time.sleep(2)
        except Exception as e:
            log.error("Listener loop error: {}\n{}".format(e, traceback.format_exc()))
            time.sleep(10)

# ============================================================
# MAIN
# ============================================================
def main():
    global COMMANDS
    log.info("=" * 70)
    log.info("  FQ v4.1 SIGNAL BOT v3.1 - BUGATTI + CLAUDE COPILOT")
    log.info("  Window: 24H | Macro: {:.2f}% | P-Space>={} | P_master>={:.2f}".format(
        MACRO_THRESHOLD_PCT * 100, PSPACE_MIN_MASSES, PMASTER_MIN))
    log.info("  Claude integration: {}".format("ENABLED" if claude_ai.is_available() else "DISABLED"))
    log.info("=" * 70)

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("FATAL: Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID env vars")
        sys.exit(1)

    exchange = ccxt.okx({"enableRateLimit": True, "timeout": 20000})

    COMMANDS = {
        "/start":    lambda exc=None: cmd_help(),
        "/help":     lambda exc=None: cmd_help(),
        "/about":    lambda exc=None: cmd_about(),
        "/sesion":   lambda exc=None: cmd_sesion(),
        "/status":   cmd_status,
        "/analisis": cmd_analisis,
        "/niveles":  cmd_niveles,
        "/pspace":   cmd_pspace,
        "/macro":    cmd_macro,
        "/claude":   cmd_claude,
        "/ia":       cmd_claude,  # alias
    }

    # Comandos que reciben follow-up automatico de Claude
    global CLAUDE_FOLLOWUP
    CLAUDE_FOLLOWUP = {
        "/analisis": claude_followup_general,
        "/pspace":   claude_followup_pspace,
        "/niveles":  claude_followup_niveles,
    }

    claude_status = "ACTIVO (Sonnet+Opus)" if claude_ai.is_available() else "INACTIVO"
    telegram_send(
        "<b>FQ v4.1 BOT v3.1 - BUGATTI + CLAUDE</b>\n"
        "{fence}\n\n"
        "Monitoreando SOL/USDT (OKX) cada 15 min.\n"
        "Ventana operativa: <b>24 HORAS</b>\n"
        "Eval intra-vela: minuto 12\n"
        "Claude integration: <b>{cs}</b>\n\n"
        "<b>Co-pilot tactico:</b>\n"
        "{b} /analisis, /pspace, /niveles -> Sonnet 4.5\n"
        "{b} /claude o /ia -> lectura tactica manual\n"
        "{b} Senales P_master >= phi^3 -> Opus 4.6 auto\n\n"
        "<b>Que ve Claude:</b>\n"
        "{b} Indicadores + masas + decoherencia (interno)\n"
        "{b} Funding + OI + L/S ratio + walls (externo)\n"
        "{b} Eventos: CHoCH, breakouts, divergencias\n"
        "{b} Evolucion vela-a-vela ultimas 5 velas\n\n"
        "Comandos: /status /analisis /niveles /pspace\n"
        "          /sesion /macro /claude /about /help".format(
            fence=G["fence"], b=G["bullet"], cs=claude_status)
    )

    t = threading.Thread(target=command_listener, args=(exchange,), daemon=True)
    t.start()

    last_candle_ts = None
    last_intra_ts  = None
    last_signal_ts = None
    cooldown = timedelta(hours=SIGNAL_COOLDOWN_HOURS)

    log.info("Main loop started")
    while True:
        try:
            df_check = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=2)
            current_ts = df_check["timestamp"].iloc[-1]
            now_utc = datetime.now(timezone.utc)
            candle_dt = current_ts.to_pydatetime().replace(tzinfo=timezone.utc)
            elapsed_min = (now_utc - candle_dt).total_seconds() / 60.0

            is_new_candle  = (last_candle_ts is None or current_ts > last_candle_ts)
            is_intra_ready = (elapsed_min >= INTRA_CANDLE_MINUTES and
                              last_intra_ts != current_ts and
                              not is_new_candle)

            if is_new_candle:
                last_candle_ts = current_ts
                last_intra_ts  = None
                log.info("New candle closed: {}".format(current_ts))

            should_eval = is_new_candle or is_intra_ready
            eval_intra  = is_intra_ready and not is_new_candle

            if should_eval:
                if eval_intra:
                    log.info("Intra-candle eval at {:.1f}m".format(elapsed_min))
                    last_intra_ts = current_ts
                if last_signal_ts and (now_utc - last_signal_ts) < cooldown:
                    rem = cooldown - (now_utc - last_signal_ts)
                    log.info("Cooldown active: {}".format(rem))
                else:
                    if evaluate_setup(exchange, intra=eval_intra):
                        last_signal_ts = now_utc

            # Reset diario de signals_today
            today = cdmx_now().date()
            if STATE.day_marker is None or STATE.day_marker != today:
                with STATE.lock:
                    STATE.day_marker = today
                    if STATE.day_marker is not None:
                        STATE.signals_today = 0

            time.sleep(LOOP_SECONDS)
        except KeyboardInterrupt:
            log.info("Shutdown requested")
            break
        except Exception as e:
            log.error("Main loop error: {}\n{}".format(e, traceback.format_exc()))
            time.sleep(LOOP_SECONDS)

if __name__ == "__main__":
    main()
