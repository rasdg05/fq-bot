# -*- coding: utf-8 -*-
"""
FQ v4.1 SIGNAL BOT v2.0 - RasDG_Sol
Fibonacci Cuantico v4.1 - Emergent Time and Curved Price-Space

Production-grade rewrite:
- ASCII-only source (zero encoding issues)
- Robust error handling
- Full command suite: /status /analisis /niveles /sesion /pspace /macro /about /help
- Intra-candle evaluation at minute 12
- Operating window 05:00-17:00 CDMX
- Macro threshold 0.08 percent
- P-Space minimum 2 masses
- Single source of truth for state
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


# ============================================================
#  CONFIG (env vars in Railway)
# ============================================================
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

SYMBOL                = "SOL-USDT-SWAP"
SYMBOL_BTC            = "BTC-USDT-SWAP"
SYMBOL_ETH            = "ETH-USDT-SWAP"
TIMEFRAME             = "15m"
LOOP_SECONDS          = 60
INTRA_CANDLE_MINUTES  = 12
SIGNAL_COOLDOWN_HOURS = 2

# Operating window CDMX (UTC-6)
WINDOW_START_HOUR = 5
WINDOW_END_HOUR   = 17

# FQ v4.1 thresholds (tuned 2026-05-07)
MACRO_THRESHOLD_PCT     = 0.0008   # 0.08 percent
TECH_MIN_ALIGNED        = 5         # of 7 indicators
PSPACE_MIN_MASSES       = 2
PMASTER_MIN             = 2.618     # phi squared
RR_MIN_TP_DIVINO        = 1.8

# FQ constants
PHI     = 1.6180339887
PHI_SQ  = PHI * PHI
PHI_INV = 1.0 / PHI

SESSION_WEIGHTS = {
    "asia":    0.50,
    "london":  0.80,
    "ny":      1.00,
    "overlap": 1.20,
}


# ============================================================
#  GLOBAL STATE (shared between threads)
# ============================================================
class BotState:
    def __init__(self):
        self.start_time         = datetime.now(timezone.utc)
        self.last_signal_ts     = None
        self.last_signal_dir    = None
        self.last_signal_price  = 0.0
        self.last_signal_levels = None
        self.signals_today      = 0
        self.signals_total      = 0
        self.last_btc_chg       = 0.0
        self.last_eth_chg       = 0.0
        self.last_sol_price     = 0.0
        self.last_eval_ts       = None
        self.last_eval_result   = "Esperando primera vela"
        self.telegram_offset    = 0
        self.lock               = threading.Lock()

STATE = BotState()


# ============================================================
#  LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("fq_bot")


# ============================================================
#  TELEGRAM
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
#  DATA
# ============================================================
def fetch_ohlcv(exchange, symbol, timeframe, limit=200):
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def add_indicators(df):
    df = df.copy()
    df["rsi6"]   = ta.rsi(df["close"], length=6)
    df["rsi12"]  = ta.rsi(df["close"], length=12)
    df["rsi14"]  = ta.rsi(df["close"], length=14)
    df["rsi24"]  = ta.rsi(df["close"], length=24)
    df["ema9"]   = ta.ema(df["close"], length=9)
    df["ema20"]  = ta.ema(df["close"], length=20)
    df["ema50"]  = ta.ema(df["close"], length=50)
    df["ema200"] = ta.ema(df["close"], length=200)
    df["sma20"]  = ta.sma(df["close"], length=20)
    df["sma50"]  = ta.sma(df["close"], length=50)

    bb = ta.bbands(df["close"], length=20, std=2)
    if bb is not None and not bb.empty:
        df["bb_lower"] = bb.iloc[:, 0]
        df["bb_mid"]   = bb.iloc[:, 1]
        df["bb_upper"] = bb.iloc[:, 2]

    macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd_df is not None and not macd_df.empty:
        df["macd"]        = macd_df.iloc[:, 0]
        df["macd_signal"] = macd_df.iloc[:, 2]

    df["vol_ma20"] = df["volume"].rolling(20).mean()
    return df


# ============================================================
#  TIME / SESSION
# ============================================================
CDMX_TZ = timezone(timedelta(hours=-6))


def cdmx_now():
    return datetime.now(CDMX_TZ)


def cdmx_now_str():
    return cdmx_now().strftime("%Y-%m-%d %H:%M CDMX")


def get_session():
    now = cdmx_now()
    h = now.hour + now.minute / 60.0
    if 7.5  <= h < 10.0: return ("overlap", SESSION_WEIGHTS["overlap"])
    if 10.0 <= h < 15.0: return ("ny",      SESSION_WEIGHTS["ny"])
    if 2.0  <= h <  7.5: return ("london",  SESSION_WEIGHTS["london"])
    return ("asia", SESSION_WEIGHTS["asia"])


def in_trading_window():
    now = cdmx_now()
    return WINDOW_START_HOUR <= now.hour < WINDOW_END_HOUR


# ============================================================
#  DECOHERENCE TESTS (Theta(D) gate)
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
    last  = df.iloc[-1]
    price = last["close"]
    indicators = ["ema9", "ema20", "ema50", "ema200", "sma20", "sma50"]
    aligned = total = 0
    for col in indicators:
        v = last.get(col)
        if v is None or pd.isna(v):
            continue
        total += 1
        if direction == "long"  and price > v: aligned += 1
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
#  P-SPACE MASS DETECTION
# ============================================================
def detect_pspace(df, direction):
    last      = df.iloc[-1]
    price     = last["close"]
    threshold = price * 0.006  # 0.6 percent tolerance
    masses    = []

    # Structural nodes (highest weight)
    high_50 = df["high"].iloc[-50:].max()
    low_50  = df["low"].iloc[-50:].min()
    if abs(price - high_50) <= threshold:
        masses.append({"name": "Resistencia estructural 50v", "price": float(high_50), "weight": 1.0})
    if abs(price - low_50) <= threshold:
        masses.append({"name": "Soporte estructural 50v", "price": float(low_50), "weight": 1.0})

    # Technical: moving averages
    for name, col in [("EMA50", "ema50"), ("EMA200", "ema200"),
                       ("SMA20", "sma20"), ("SMA50", "sma50"),
                       ("EMA20", "ema20")]:
        v = last.get(col)
        if v is not None and not pd.isna(v) and abs(price - v) <= threshold:
            masses.append({"name": name, "price": float(v), "weight": 0.6})

    # Bollinger
    bbu = last.get("bb_upper")
    bbl = last.get("bb_lower")
    if bbu is not None and not pd.isna(bbu) and abs(price - bbu) <= threshold:
        masses.append({"name": "BB Upper", "price": float(bbu), "weight": 0.6})
    if bbl is not None and not pd.isna(bbl) and abs(price - bbl) <= threshold:
        masses.append({"name": "BB Lower", "price": float(bbl), "weight": 0.6})

    # Volume anomaly
    vol_ma = last.get("vol_ma20")
    if vol_ma is not None and not pd.isna(vol_ma) and last["volume"] > 1.8 * vol_ma:
        masses.append({"name": "Volumen anomalo", "price": float(price), "weight": 0.9})

    # Psychological round number
    rounded = round(price)
    if abs(price - rounded) <= threshold:
        masses.append({"name": "Psicologico ${}".format(int(rounded)), "price": float(rounded), "weight": 0.8})

    return {
        "passed": len(masses) >= PSPACE_MIN_MASSES,
        "count":  len(masses),
        "masses": masses,
    }


# ============================================================
#  LAPLACIAN (harmonicity breakdown)
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
#  LEVELS (Entry, SL, 4 TPs including divine)
# ============================================================
def calculate_levels(df, direction):
    last  = df.iloc[-1]
    entry = float(last["close"])
    high  = float(df["high"].iloc[-50:].max())
    low   = float(df["low"].iloc[-50:].min())
    rng   = high - low

    if direction == "long":
        ema50_v = last.get("ema50")
        ema50_v = float(ema50_v) if ema50_v is not None and not pd.isna(ema50_v) else entry * 0.98
        sl  = min(ema50_v, float(df["low"].iloc[-10:].min())) * 0.998
        tp1 = entry + (rng * PHI_INV * PHI_INV)
        tp2 = entry + (rng * PHI_INV)
        tp3 = entry * (1 + (rng / entry) * PHI_INV)
        tp4 = entry + (rng * PHI_INV * PHI)
    else:
        ema50_v = last.get("ema50")
        ema50_v = float(ema50_v) if ema50_v is not None and not pd.isna(ema50_v) else entry * 1.02
        sl  = max(ema50_v, float(df["high"].iloc[-10:].max())) * 1.002
        tp1 = entry - (rng * PHI_INV * PHI_INV)
        tp2 = entry - (rng * PHI_INV)
        tp3 = entry * (1 - (rng / entry) * PHI_INV)
        tp4 = entry - (rng * PHI_INV * PHI)

    risk = abs(entry - sl)
    return {
        "entry": entry, "sl": sl,
        "tp1": tp1, "tp2": tp2, "tp3": tp3, "tp4": tp4,
        "risk": risk,
        "rr_tp1": abs(tp1 - entry) / risk if risk > 0 else 0,
        "rr_tp2": abs(tp2 - entry) / risk if risk > 0 else 0,
        "rr_tp3": abs(tp3 - entry) / risk if risk > 0 else 0,
        "rr_tp4": abs(tp4 - entry) / risk if risk > 0 else 0,
    }


# ============================================================
#  SIGNAL MESSAGE
# ============================================================
def build_signal_msg(direction, levels, decoh, masses, session, w_clock, p_master, lap, intra=False):
    side = "LONG" if direction == "long" else "SHORT"
    side_emoji = "[LONG]" if direction == "long" else "[SHORT]"

    if p_master >= PHI ** 3:
        leverage, sizing, tier = "8x", "10%", "phi^3 (alta conviccion)"
    elif p_master >= PHI_SQ:
        leverage, sizing, tier = "5x", "5%",  "phi^2 (standard)"
    else:
        leverage, sizing, tier = "3x", "2%",  "phi (scalp)"

    masas_text = "\n".join([
        "  - {}: ${:.2f}".format(m["name"], m["price"])
        for m in masses["masses"][:5]
    ])

    intra_note = "\n[INTRA-VELA - confirmar al cierre]" if intra else ""

    msg = (
        "<b>SENAL FQ v4.1 - DECOHERENCIA CONFIRMADA</b>{intra}\n\n"
        "<b>SOL/USDT PERPETUAL</b>\n"
        "{side_emoji} {side} - Confianza: {tier}\n"
        "{when} - Sesion: <b>{session}</b> (W={w})\n\n"
        "----- NIVELES DIVINOS -----\n"
        "Entrada: <b>${entry:.2f}</b>\n"
        "SL:      ${sl:.2f}  ({risk_pct:.2f}%)\n\n"
        "TP1 (30%): ${tp1:.2f}  R:R {rr1:.2f}\n"
        "TP2 (30%): ${tp2:.2f}  R:R {rr2:.2f}\n"
        "TP3 (25%): ${tp3:.2f}  *DIVINO*  R:R {rr3:.2f}\n"
        "TP4 (15%): ${tp4:.2f}  R:R {rr4:.2f}\n\n"
        "Apalancamiento max: <b>{lev}</b>\n"
        "Tamano: {size} equity\n\n"
        "----- DECOHERENCIA Theta(D) = 1 -----\n"
        "Macro:    BTC {btc:+.2f}% | ETH {eth:+.2f}%\n"
        "Tecnica:  {tec_a}/{tec_t} indicadores alineados\n"
        "Liquidez: RSI 6/12/24 = {r6:.0f}/{r12:.0f}/{r24:.0f}\n"
        "P-Space:  {pscount} masas en confluencia\n"
        "Laplaciano: ratio {lap_r:.2f} {lap_ico}\n\n"
        "<b>Masas detectadas:</b>\n{masas}\n\n"
        "<b>P_master = {pm:.2f}</b>\n\n"
        "----- INVALIDACION -----\n"
        "- Cierre 15m {cmp} ${sl:.2f} -> cerrar\n"
        "- 90 min sin progreso -> revisar\n"
        "- SL nunca se mueve hacia abajo (Regla 4)\n\n"
        "#FQv41 #SOLUSDT #{tag}"
    ).format(
        intra=intra_note, side_emoji=side_emoji, side=side, tier=tier,
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
        lap_ico="[OK]" if lap["active"] else "[OFF]",
        masas=masas_text, pm=p_master,
        cmp="<" if direction == "long" else ">",
        tag=side,
    )
    return msg


# ============================================================
#  COMMAND RESPONSES
# ============================================================
def cmd_help():
    return (
        "<b>FQ v4.1 BOT - COMANDOS</b>\n\n"
        "/status   - Estado bot y mercado\n"
        "/analisis - Analisis FQ completo en vivo\n"
        "/niveles  - Niveles de trade hipoteticos ahora\n"
        "/sesion   - Sesion activa y W_clock\n"
        "/pspace   - Masas P-Space alrededor del precio\n"
        "/macro    - Estado decoherencia macro BTC/ETH\n"
        "/about    - Sobre el sistema FQ v4.1\n"
        "/help     - Esta ayuda\n\n"
        "----- SENALES AUTOMATICAS -----\n"
        "Bot monitorea SOL/USDT cada 15 min.\n"
        "Solo envia senal con Theta(D)=1 (decoherencia 3/3).\n"
        "Ventana operativa: 05:00-17:00 CDMX.\n"
        "Promedio esperado: 1-3 senales/dia de alta conviccion.\n\n"
        "El silencio es disciplina. Calidad sobre cantidad.\n\n"
        "#FQv41"
    )


def cmd_about():
    return (
        "<b>FIBONACCI CUANTICO v4.1</b>\n"
        "<i>Emergent Time and Curved Price-Space</i>\n"
        "by RasDG_Sol\n\n"
        "----- FUNDAMENTOS -----\n"
        "El mercado no esta en un estado definido.\n"
        "Esta en superposicion de historias competidoras.\n"
        "Una senal solo existe cuando colapsan.\n\n"
        "<b>4 Pilares:</b>\n"
        "I.   Decoherencia 3/3 (Hartle, Solvay 2005)\n"
        "II.  Tiempo emergente W_clock (Page-Wootters)\n"
        "III. P-Space curvado por liquidez (Oreste 2011)\n"
        "IV.  Laplaciano discreto (Knill Harvard 2020)\n\n"
        "----- MASTER EQUATION v4.1 -----\n"
        "P_master = Theta(D) * k(p) * phi^n * W_clock * H_lap\n\n"
        "Si Theta(D) = 0 -> P_master = 0 -> no trade.\n"
        "Sin excepcion. Sin override.\n\n"
        "----- PARAMETROS ACTUALES -----\n"
        "Par: SOL/USDT Perpetual\n"
        "Exchange: OKX (datos)\n"
        "Timeframe: 15 minutos\n"
        "Ventana: 05:00-17:00 CDMX\n"
        "Macro threshold: 0.08%\n"
        "P-Space minimo: 2 masas\n"
        "Cooldown: 2h entre senales\n"
        "Max leverage: 8x (phi^3-coupled)\n\n"
        "phi = 1.6180339887\n\n"
        "#FQv41 #RasDG"
    )


def cmd_status(exchange):
    session, w = get_session()
    ventana = "ACTIVA" if in_trading_window() else "INACTIVA"

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
        ult = "Hace {}h {}m | {} @ ${:.2f}".format(
            h, m,
            (STATE.last_signal_dir or "").upper(),
            STATE.last_signal_price)
    else:
        ult = "Ninguna aun"

    macro_ok = (abs(STATE.last_btc_chg) > MACRO_THRESHOLD_PCT * 100 and
                abs(STATE.last_eth_chg) > MACRO_THRESHOLD_PCT * 100)

    return (
        "<b>STATUS - FQ v4.1 BOT</b>\n\n"
        "{when}\n"
        "Uptime: {h}h {m}m\n"
        "Exchange: OKX (en vivo)\n\n"
        "----- MERCADO -----\n"
        "SOL/USDT: <b>${px:.2f}</b> ({chg:+.2f}%)\n"
        "BTC 15m:  {btc:+.2f}%\n"
        "ETH 15m:  {eth:+.2f}%\n\n"
        "----- SISTEMA -----\n"
        "Ventana: {vent} (05:00-17:00 CDMX)\n"
        "Sesion: <b>{ses}</b> (W={w})\n"
        "Senales hoy: {st}\n"
        "Senales total: {stt}\n"
        "Ultima senal: {ult}\n\n"
        "----- DECOHERENCIA -----\n"
        "Macro: BTC {btc:+.2f}% | ETH {eth:+.2f}%\n"
        "Gate: {gate}\n"
        "Ultima eval: {evr}\n\n"
        "#FQv41 #Status"
    ).format(
        when=cdmx_now_str(), h=up_h, m=up_m,
        px=sol_px, chg=sol_chg,
        btc=STATE.last_btc_chg, eth=STATE.last_eth_chg,
        vent=ventana, ses=session.upper(), w=w,
        st=STATE.signals_today, stt=STATE.signals_total,
        ult=ult,
        gate="DECOHERENTE" if macro_ok else "EN SUPERPOSICION",
        evr=STATE.last_eval_result,
    )


def cmd_sesion():
    session, w = get_session()
    now = cdmx_now()
    h = now.hour + now.minute / 60.0

    sesiones = [
        ("asia",    "00:00-07:00 CDMX", "W=0.50 - Solo excepcion (RSI<25 + CHoCH)"),
        ("london",  "02:00-07:30 CDMX", "W=0.80 - Apertura europea"),
        ("overlap", "07:30-10:00 CDMX", "W=1.20 - MAXIMA ENERGIA"),
        ("ny",      "10:00-15:00 CDMX", "W=1.00 - Sesion NY pura"),
    ]

    lineas = []
    for nombre, horario, desc in sesiones:
        marker = "-> " if nombre == session else "   "
        lineas.append("{}{} ({})\n   {}".format(marker, nombre.upper(), horario, desc))

    nota = ""
    if session == "overlap":
        rem = int((10.0 - h) * 60)
        nota = "\n\nOverlap cierra en {} minutos".format(max(0, rem))
    elif session == "ny":
        rem = int((15.0 - h) * 60)
        nota = "\n\nNY cierra en {} minutos".format(max(0, rem))

    return (
        "<b>SESION ACTUAL - FQ v4.1</b>\n\n"
        "{when}\n"
        "Sesion activa: <b>{ses}</b>\n"
        "W_clock: <b>{w}</b>{nota}\n\n"
        "----- CALENDARIO -----\n\n"
        "{lst}\n\n"
        "Ventana operativa del bot:\n"
        "<b>05:00 - 17:00 CDMX</b>\n\n"
        "El W_clock multiplica P_master.\n"
        "Overlap (1.20) = mayor probabilidad de senal.\n\n"
        "#FQv41 #Clock"
    ).format(
        when=cdmx_now_str(),
        ses=session.upper(), w=w,
        nota=nota,
        lst="\n\n".join(lineas),
    )


def cmd_macro(exchange):
    macro = test_macro(exchange)
    direction = macro.get("direction") or "neutral"
    gate = "DECOHERENTE - direccion {}".format(direction.upper()) if macro["passed"] else "EN SUPERPOSICION"

    btc_dir = "ALCISTA" if macro["btc_change"] > 0 else "BAJISTA"
    eth_dir = "ALCISTA" if macro["eth_change"] > 0 else "BAJISTA"

    needed = MACRO_THRESHOLD_PCT * 100

    return (
        "<b>MACRO DECOHERENCE - BTC/ETH</b>\n\n"
        "{when}\n\n"
        "----- MOVIMIENTO 15m (vs hace 1h) -----\n"
        "BTC: <b>{btc:+.2f}%</b> ({btc_d})\n"
        "ETH: <b>{eth:+.2f}%</b> ({eth_d})\n\n"
        "Threshold requerido: +/- {th:.2f}% en AMBOS\n"
        "Direccion: misma para ambos\n\n"
        "----- GATE -----\n"
        "<b>{gate}</b>\n\n"
        "{ana}\n\n"
        "#FQv41 #Macro"
    ).format(
        when=cdmx_now_str(),
        btc=macro["btc_change"], btc_d=btc_dir,
        eth=macro["eth_change"], eth_d=eth_dir,
        th=needed,
        gate=gate,
        ana=("Macro permite entrada en direccion " + direction.upper()
             if macro["passed"]
             else "Mercado lateral. No hay conviccion direccional macro."),
    )


def cmd_pspace(exchange):
    try:
        df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
        df = add_indicators(df)
        last = df.iloc[-1]
        price = float(last["close"])

        # Try both directions for completeness
        ps_long  = detect_pspace(df, "long")
        # detect_pspace doesn't actually use direction - same result
        masses = ps_long["masses"]

        if not masses:
            masas_txt = "Sin masas detectadas en zona cercana."
        else:
            lines = []
            for m in masses[:8]:
                dist_pct = abs(price - m["price"]) / price * 100
                lines.append("  {} - ${:.2f} (dist {:.2f}%, w={:.1f})".format(
                    m["name"], m["price"], dist_pct, m["weight"]))
            masas_txt = "\n".join(lines)

        gate = "VALIDO ({} masas)".format(len(masses)) if len(masses) >= PSPACE_MIN_MASSES else \
               "INSUFICIENTE ({} masas, requeridas >={})".format(len(masses), PSPACE_MIN_MASSES)

        return (
            "<b>P-SPACE MASS DETECTION</b>\n\n"
            "{when}\n"
            "Precio actual: <b>${px:.2f}</b>\n\n"
            "----- MASAS DETECTADAS -----\n"
            "{ms}\n\n"
            "Gate P-Space: <b>{g}</b>\n\n"
            "Tolerancia: 0.6% del precio\n"
            "Masas con peso 1.0 = estructurales\n"
            "Masas con peso 0.6-0.9 = tecnicas/volumen\n\n"
            "#FQv41 #PSpace"
        ).format(when=cdmx_now_str(), px=price, ms=masas_txt, g=gate)
    except Exception as e:
        log.error("Error pspace: {}\n{}".format(e, traceback.format_exc()))
        return "Error al calcular P-Space: {}".format(e)


def cmd_niveles(exchange):
    try:
        df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
        df = add_indicators(df)
        last = df.iloc[-1]
        price = float(last["close"])

        # Get likely direction from recent momentum
        last5 = df["close"].iloc[-5:].values
        direction = "long" if last5[-1] > last5[0] else "short"

        levels_long  = calculate_levels(df, "long")
        levels_short = calculate_levels(df, "short")

        return (
            "<b>NIVELES HIPOTETICOS - FQ v4.1</b>\n"
            "<i>Si entraras AHORA mismo</i>\n\n"
            "{when}\n"
            "Precio: <b>${px:.2f}</b>\n\n"
            "============ LONG ============\n"
            "Entrada: ${e:.2f}\n"
            "SL:      ${sl:.2f} ({rp:.2f}%)\n"
            "TP1:     ${t1:.2f}  R:R {r1:.2f}\n"
            "TP2:     ${t2:.2f}  R:R {r2:.2f}\n"
            "TP3:     ${t3:.2f}  *DIVINO*  R:R {r3:.2f}\n"
            "TP4:     ${t4:.2f}  R:R {r4:.2f}\n\n"
            "============ SHORT ============\n"
            "Entrada: ${es:.2f}\n"
            "SL:      ${sls:.2f} ({rps:.2f}%)\n"
            "TP1:     ${ts1:.2f}  R:R {rs1:.2f}\n"
            "TP2:     ${ts2:.2f}  R:R {rs2:.2f}\n"
            "TP3:     ${ts3:.2f}  *DIVINO*  R:R {rs3:.2f}\n"
            "TP4:     ${ts4:.2f}  R:R {rs4:.2f}\n\n"
            "Direccion sugerida (momentum 5v): <b>{d}</b>\n\n"
            "ATENCION: Niveles calculados, no son senal\n"
            "valida hasta que pasen el gate Theta(D).\n\n"
            "#FQv41 #Niveles"
        ).format(
            when=cdmx_now_str(), px=price, d=direction.upper(),
            e=levels_long["entry"], sl=levels_long["sl"],
            rp=(levels_long["risk"]/levels_long["entry"]*100),
            t1=levels_long["tp1"], r1=levels_long["rr_tp1"],
            t2=levels_long["tp2"], r2=levels_long["rr_tp2"],
            t3=levels_long["tp3"], r3=levels_long["rr_tp3"],
            t4=levels_long["tp4"], r4=levels_long["rr_tp4"],
            es=levels_short["entry"], sls=levels_short["sl"],
            rps=(levels_short["risk"]/levels_short["entry"]*100),
            ts1=levels_short["tp1"], rs1=levels_short["rr_tp1"],
            ts2=levels_short["tp2"], rs2=levels_short["rr_tp2"],
            ts3=levels_short["tp3"], rs3=levels_short["rr_tp3"],
            ts4=levels_short["tp4"], rs4=levels_short["rr_tp4"],
        )
    except Exception as e:
        log.error("Error niveles: {}\n{}".format(e, traceback.format_exc()))
        return "Error al calcular niveles: {}".format(e)


def cmd_analisis(exchange):
    try:
        df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
        df = add_indicators(df)
        last = df.iloc[-1]
        session, w_clock = get_session()

        macro = test_macro(exchange)
        direction = macro.get("direction") or "long"

        tecnica  = test_technical(df, direction)
        liquidez = test_liquidity(df, direction)
        masses   = detect_pspace(df, direction)
        lap      = laplacian_check(df)

        theta_d = macro["passed"] and tecnica["passed"] and liquidez["passed"]

        bb_pos = ""
        bbu, bbl = last.get("bb_upper"), last.get("bb_lower")
        if bbu is not None and not pd.isna(bbu) and bbl is not None and not pd.isna(bbl):
            if last["close"] > bbu:    bb_pos = "Sobre BB Upper [precaucion]"
            elif last["close"] < bbl:  bb_pos = "Bajo BB Lower [precaucion]"
            else:                       bb_pos = "Dentro de Bollinger"

        veredicto = ("[OK] SETUP EN FORMACION - candidato real" if theta_d else
                     "[--] SIN SETUP - mercado en superposicion")

        ico = lambda b: "[OK]" if b else "[--]"

        return (
            "<b>ANALISIS FQ v4.1 - EN VIVO</b>\n\n"
            "{when}\n"
            "SOL/USDT: <b>${px:.2f}</b>\n"
            "Sesion: {ses} (W={w})\n\n"
            "----- GATE Theta(D) -----\n"
            "{im} Macro:    BTC {bc:+.2f}% | ETH {ec:+.2f}%\n"
            "{it} Tecnica:  {ta}/{tt} indicadores alineados\n"
            "{il} Liquidez: RSI 6/12/24 = {r6:.0f}/{r12:.0f}/{r24:.0f}\n"
            "{ip} P-Space:  {pc} masas\n"
            "{ip2} Laplaciano: ratio {lr:.2f}\n\n"
            "<b>Theta(D) = {td}</b>\n\n"
            "----- INDICADORES -----\n"
            "EMA 50:  ${e50:.2f}\n"
            "EMA 200: ${e200:.2f}\n"
            "RSI 14:  {r14:.1f}\n"
            "MACD:    {mc:.3f} / Signal: {ms:.3f}\n"
            "{bb}\n\n"
            "----- VEREDICTO -----\n"
            "{ver}\n"
            "Ventana operativa: {vent}\n\n"
            "#FQv41 #Analisis"
        ).format(
            when=cdmx_now_str(), px=float(last["close"]), ses=session.upper(), w=w_clock,
            im=ico(macro["passed"]),  bc=macro["btc_change"], ec=macro["eth_change"],
            it=ico(tecnica["passed"]), ta=tecnica["aligned"], tt=tecnica["total"],
            il=ico(liquidez["passed"]),
            r6=liquidez["rsi6"], r12=liquidez["rsi12"], r24=liquidez["rsi24"],
            ip=ico(masses["passed"]), pc=masses["count"],
            ip2="[OK]" if lap["active"] else "[--]", lr=lap["ratio"],
            td="1 - DECOHERENTE" if theta_d else "0 - SUPERPOSICION",
            e50=float(last.get("ema50") or 0), e200=float(last.get("ema200") or 0),
            r14=float(last.get("rsi14") or 0),
            mc=float(last.get("macd") or 0), ms=float(last.get("macd_signal") or 0),
            bb=bb_pos,
            ver=veredicto,
            vent="ACTIVA" if in_trading_window() else "INACTIVA",
        )
    except Exception as e:
        log.error("Error analisis: {}\n{}".format(e, traceback.format_exc()))
        return "Error al analizar: {}".format(e)


# ============================================================
#  EVALUATE SETUP (the actual signal engine)
# ============================================================
def evaluate_setup(exchange, intra=False):
    if not in_trading_window():
        STATE.last_eval_result = "Fuera de ventana 05-17 CDMX"
        return False

    df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
    df = add_indicators(df)
    if len(df) < 50:
        STATE.last_eval_result = "Datos insuficientes"
        return False

    with STATE.lock:
        STATE.last_sol_price = float(df["close"].iloc[-1])
        STATE.last_eval_ts   = datetime.now(timezone.utc)

    session, w_clock = get_session()

    # 1. Macro gate
    macro = test_macro(exchange)
    if not macro["passed"]:
        msg = "Macro NO decoherente (BTC {:+.2f}% / ETH {:+.2f}%)".format(
            macro["btc_change"], macro["eth_change"])
        log.info(msg)
        STATE.last_eval_result = msg
        return False

    direction = macro["direction"]

    # 2. Technical gate
    tecnica = test_technical(df, direction)
    if not tecnica["passed"]:
        msg = "Tecnica NO decoherente ({}/{})".format(tecnica["aligned"], tecnica["total"])
        log.info(msg)
        STATE.last_eval_result = msg
        return False

    # 3. Liquidity gate
    liquidez = test_liquidity(df, direction)
    if not liquidez["passed"]:
        msg = "Liquidez NO decoherente (RSI {:.0f}/{:.0f}/{:.0f})".format(
            liquidez["rsi6"], liquidez["rsi12"], liquidez["rsi24"])
        log.info(msg)
        STATE.last_eval_result = msg
        return False

    # 4. P-Space gate
    masses = detect_pspace(df, direction)
    if not masses["passed"]:
        msg = "P-Space insuficiente ({} masas)".format(masses["count"])
        log.info(msg)
        STATE.last_eval_result = msg
        return False

    # 5. Laplacian (modulator, not gate)
    lap = laplacian_check(df)
    h_factor = 1.0 if lap["active"] else 0.7

    # 6. P_master
    p_master = (PHI ** 1) * w_clock * h_factor
    p_master *= 1 + (masses["count"] - 2) * 0.15

    if p_master < PMASTER_MIN:
        msg = "P_master {:.2f} < {:.2f}".format(p_master, PMASTER_MIN)
        log.info(msg)
        STATE.last_eval_result = msg
        return False

    # 7. R:R sanity check
    levels = calculate_levels(df, direction)
    if levels["rr_tp3"] < RR_MIN_TP_DIVINO:
        msg = "R:R TP divino {:.2f} < {:.2f}".format(levels["rr_tp3"], RR_MIN_TP_DIVINO)
        log.info(msg)
        STATE.last_eval_result = msg
        return False

    # PASSED - send signal
    decoh = {"macro": macro, "tecnica": tecnica, "liquidez": liquidez}
    msg = build_signal_msg(direction, levels, decoh, masses, session, w_clock, p_master, lap, intra=intra)

    if telegram_send(msg):
        log.info("SIGNAL SENT: {} P_master={:.2f} intra={}".format(direction.upper(), p_master, intra))
        with STATE.lock:
            STATE.last_signal_ts    = datetime.now(timezone.utc)
            STATE.last_signal_dir   = direction
            STATE.last_signal_price = levels["entry"]
            STATE.last_signal_levels = levels
            STATE.signals_today    += 1
            STATE.signals_total    += 1
            STATE.last_eval_result = "SENAL ENVIADA: {} @ ${:.2f}".format(direction.upper(), levels["entry"])
        return True
    return False


# ============================================================
#  COMMAND LISTENER (separate thread)
# ============================================================
COMMANDS = {}  # populated in main


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

                # Strip @botname suffix
                if "@" in text:
                    text = text.split("@")[0]

                log.info("Cmd received: {}".format(text))

                if text in COMMANDS:
                    handler = COMMANDS[text]
                    try:
                        if text == "/analisis":
                            telegram_send("Analizando mercado en tiempo real...", chat_id)
                        if text == "/niveles":
                            telegram_send("Calculando niveles FQ...", chat_id)
                        if text == "/pspace":
                            telegram_send("Detectando masas P-Space...", chat_id)
                        response = handler(exchange) if handler.__code__.co_argcount > 0 else handler()
                        telegram_send(response, chat_id)
                    except Exception as e:
                        log.error("Error executing {}: {}\n{}".format(text, e, traceback.format_exc()))
                        telegram_send("Error ejecutando comando: {}".format(e), chat_id)

            time.sleep(2)

        except Exception as e:
            log.error("Listener loop error: {}\n{}".format(e, traceback.format_exc()))
            time.sleep(10)


# ============================================================
#  MAIN
# ============================================================
def main():
    global COMMANDS

    log.info("=" * 60)
    log.info("  FQ v4.1 SIGNAL BOT v2.0 - RasDG_Sol")
    log.info("  Window: {}-{} CDMX | Macro: {:.2f}% | P-Space>={}".format(
        WINDOW_START_HOUR, WINDOW_END_HOUR,
        MACRO_THRESHOLD_PCT * 100, PSPACE_MIN_MASSES))
    log.info("=" * 60)

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("FATAL: Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID env vars")
        sys.exit(1)

    exchange = ccxt.okx({"enableRateLimit": True, "timeout": 20000})

    # Build command map (defined here to capture exchange)
    COMMANDS = {
        "/start":     lambda exc=None: cmd_help(),
        "/help":      lambda exc=None: cmd_help(),
        "/about":     lambda exc=None: cmd_about(),
        "/sesion":    lambda exc=None: cmd_sesion(),
        "/status":    cmd_status,
        "/analisis":  cmd_analisis,
        "/niveles":   cmd_niveles,
        "/pspace":    cmd_pspace,
        "/macro":     cmd_macro,
    }

    # Startup message
    telegram_send(
        "<b>Bot FQ v4.1 v2.0 ACTIVO</b>\n\n"
        "Monitoreando SOL/USDT (OKX) cada 15 min.\n"
        "Ventana: 05:00-17:00 CDMX\n"
        "Eval intra-vela: minuto 12\n\n"
        "Comandos: /status /analisis /niveles /sesion /pspace /macro /about /help"
    )

    # Start command listener in background thread
    t = threading.Thread(target=command_listener, args=(exchange,), daemon=True)
    t.start()

    last_candle_ts  = None
    last_intra_ts   = None
    last_signal_ts  = None
    cooldown        = timedelta(hours=SIGNAL_COOLDOWN_HOURS)

    log.info("Main loop started")

    while True:
        try:
            df_check = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=2)
            current_ts = df_check["timestamp"].iloc[-1]
            now_utc    = datetime.now(timezone.utc)
            candle_dt  = current_ts.to_pydatetime().replace(tzinfo=timezone.utc)
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

            time.sleep(LOOP_SECONDS)

        except KeyboardInterrupt:
            log.info("Shutdown requested")
            break
        except Exception as e:
            log.error("Main loop error: {}\n{}".format(e, traceback.format_exc()))
            time.sleep(LOOP_SECONDS)


if __name__ == "__main__":
    main()
