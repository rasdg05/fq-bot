"""
========================================================================
  FQ v4.1 SIGNAL BOT — RasDG_Sol
  Fibonacci Cuántico v4.1 — Emergent Time & Curved Price-Space
  
  Monitorea SOL/USDT cada 15 minutos.
  Aplica gate de decoherencia 3/3 + P-Space + Laplaciano.
  Envía señales a Telegram solo si Theta(D)=1 y P_master >= phi^2.
  Responde comandos: /status /analisis /sesion /about /help
========================================================================
"""

import os
import time
import logging
import threading
from datetime import datetime, timezone, timedelta

import ccxt
import pandas as pd
import pandas_ta as ta
import requests

# ============================================================
#  CONFIGURACION (se lee de variables de entorno en Railway)
# ============================================================
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SYMBOL           = "SOL-USDT-SWAP"   # Perpetuo en OKX
TIMEFRAME        = "15m"
CHECK_INTERVAL_SECONDS = 60

# ============================================================
#  CONSTANTES FQ v4.1
# ============================================================
PHI     = 1.6180339887
PHI_SQ  = PHI * PHI       # 2.618
PHI_INV = 1 / PHI         # 0.618

SESSION_WEIGHTS = {
    "asia":    0.50,
    "london":  0.80,
    "ny":      1.00,
    "overlap": 1.20,
}

# ============================================================
#  ESTADO GLOBAL (compartido entre hilos)
# ============================================================
BOT_STATE = {
    "start_time":       datetime.now(timezone.utc),
    "last_signal_ts":   None,
    "last_signal_dir":  None,
    "last_signal_price": None,
    "signals_today":    0,
    "signals_total":    0,
    "last_candle_ts":   None,
    "last_btc_chg":     0.0,
    "last_eth_chg":     0.0,
    "last_sol_price":   0.0,
    "last_eval_ts":     None,
    "telegram_offset":  0,
}

# ============================================================
#  LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("fq_bot")


# ============================================================
#  HELPERS DE TELEGRAM
# ============================================================
def send_telegram(message: str, chat_id: str = None) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("TELEGRAM_TOKEN o TELEGRAM_CHAT_ID no configurados")
        return False
    target = chat_id or TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": target,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        log.error(f"Telegram send error: {e}")
        return False


def get_telegram_updates(offset: int) -> list:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"offset": offset, "timeout": 30, "allowed_updates": ["message"]}
    try:
        r = requests.get(url, params=params, timeout=35)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception as e:
        log.error(f"Telegram getUpdates error: {e}")
    return []


# ============================================================
#  FETCH DE DATOS
# ============================================================
def fetch_ohlcv(exchange, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


# ============================================================
#  INDICADORES
# ============================================================
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rsi6"]  = ta.rsi(df["close"], length=6)
    df["rsi12"] = ta.rsi(df["close"], length=12)
    df["rsi14"] = ta.rsi(df["close"], length=14)
    df["rsi24"] = ta.rsi(df["close"], length=24)
    df["ema9"]  = ta.ema(df["close"], length=9)
    df["ema20"] = ta.ema(df["close"], length=20)
    df["ema50"] = ta.ema(df["close"], length=50)
    df["ema200"]= ta.ema(df["close"], length=200)
    df["sma20"] = ta.sma(df["close"], length=20)
    df["sma50"] = ta.sma(df["close"], length=50)
    bb = ta.bbands(df["close"], length=20, std=2)
    if bb is not None and not bb.empty:
        df["bb_lower"] = bb.iloc[:, 0]
        df["bb_mid"]   = bb.iloc[:, 1]
        df["bb_upper"] = bb.iloc[:, 2]
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        df["macd"]        = macd.iloc[:, 0]
        df["macd_signal"] = macd.iloc[:, 2]
        df["macd_hist"]   = macd.iloc[:, 1]
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    return df


# ============================================================
#  CLOCK (sesion CDMX)
# ============================================================
def get_session_weight() -> tuple:
    cdmx = timezone(timedelta(hours=-6))
    now  = datetime.now(cdmx)
    h    = now.hour + now.minute / 60.0
    if 7.5  <= h < 10.0: return ("overlap", SESSION_WEIGHTS["overlap"])
    if 10.0 <= h < 15.0: return ("ny",      SESSION_WEIGHTS["ny"])
    if 2.0  <= h <  7.5: return ("london",  SESSION_WEIGHTS["london"])
    return ("asia", SESSION_WEIGHTS["asia"])


def in_trading_window() -> bool:
    cdmx = timezone(timedelta(hours=-6))
    now  = datetime.now(cdmx)
    return 7 <= now.hour < 15


def cdmx_now_str() -> str:
    cdmx = timezone(timedelta(hours=-6))
    return datetime.now(cdmx).strftime("%Y-%m-%d %H:%M CDMX")


# ============================================================
#  TEST DE DECOHERENCIA
# ============================================================
def test_macro_decoherence(exchange) -> dict:
    result = {"passed": False, "direction": None, "btc_change": 0, "eth_change": 0}
    try:
        btc = fetch_ohlcv(exchange, "BTC-USDT-SWAP", "15m", limit=20)
        eth = fetch_ohlcv(exchange, "ETH-USDT-SWAP", "15m", limit=20)
        btc_chg = (btc["close"].iloc[-1] - btc["close"].iloc[-4]) / btc["close"].iloc[-4]
        eth_chg = (eth["close"].iloc[-1] - eth["close"].iloc[-4]) / eth["close"].iloc[-4]
        result["btc_change"] = btc_chg * 100
        result["eth_change"] = eth_chg * 100
        BOT_STATE["last_btc_chg"] = btc_chg * 100
        BOT_STATE["last_eth_chg"] = eth_chg * 100
        if btc_chg > 0.0015 and eth_chg > 0.0015:
            result["passed"] = True
            result["direction"] = "long"
        elif btc_chg < -0.0015 and eth_chg < -0.0015:
            result["passed"] = True
            result["direction"] = "short"
    except Exception as e:
        log.error(f"Error macro decoherence: {e}")
    return result


def test_technical_decoherence(df: pd.DataFrame, direction: str) -> dict:
    last  = df.iloc[-1]
    price = last["close"]
    mas = {"ema9": last["ema9"], "ema20": last["ema20"], "ema50": last["ema50"],
           "ema200": last["ema200"], "sma20": last["sma20"], "sma50": last["sma50"]}
    aligned = total = 0
    for val in mas.values():
        if pd.isna(val): continue
        total += 1
        if direction == "long"  and price > val: aligned += 1
        if direction == "short" and price < val: aligned += 1
    if not pd.isna(last.get("macd", float("nan"))):
        total += 1
        if direction == "long"  and last["macd"] > last["macd_signal"]: aligned += 1
        if direction == "short" and last["macd"] < last["macd_signal"]: aligned += 1
    return {"passed": aligned >= 5 and total >= 6, "aligned": aligned, "total": total}


def test_liquidity_decoherence(df: pd.DataFrame, direction: str) -> dict:
    last = df.iloc[-1]
    r6, r12, r24 = last["rsi6"], last["rsi12"], last["rsi24"]
    if pd.isna(r6) or pd.isna(r12) or pd.isna(r24):
        return {"passed": False, "rsi6": 0, "rsi12": 0, "rsi24": 0}
    if direction == "long":  passed = r6 > 50 and r12 > 50 and r24 > 50
    else:                    passed = r6 < 50 and r12 < 50 and r24 < 50
    return {"passed": passed, "rsi6": r6, "rsi12": r12, "rsi24": r24}


# ============================================================
#  P-SPACE
# ============================================================
def detect_pspace_masses(df: pd.DataFrame, direction: str) -> dict:
    last      = df.iloc[-1]
    price     = last["close"]
    threshold = price * 0.005
    masses    = []
    high_50   = df["high"].iloc[-50:].max()
    low_50    = df["low"].iloc[-50:].min()
    if abs(price - high_50) <= threshold: masses.append(("Resistencia estructural 50v", high_50, 1.0))
    if abs(price - low_50)  <= threshold: masses.append(("Soporte estructural 50v",    low_50,  1.0))
    for name, val in [("EMA50", last["ema50"]), ("EMA200", last["ema200"]),
                       ("SMA20", last["sma20"]), ("SMA50",  last["sma50"])]:
        if not pd.isna(val) and abs(price - val) <= threshold:
            masses.append((name, val, 0.6))
    if not pd.isna(last.get("bb_upper", float("nan"))) and abs(price - last["bb_upper"]) <= threshold:
        masses.append(("BB Upper", last["bb_upper"], 0.6))
    if not pd.isna(last.get("bb_lower", float("nan"))) and abs(price - last["bb_lower"]) <= threshold:
        masses.append(("BB Lower", last["bb_lower"], 0.6))
    if not pd.isna(last["vol_ma20"]) and last["volume"] > 2 * last["vol_ma20"]:
        masses.append(("Volumen anomalo", price, 0.9))
    rounded = round(price)
    if abs(price - rounded) <= threshold:
        masses.append((f"Psicologico ${rounded}", rounded, 0.8))
    return {"passed": len(masses) >= 3, "count": len(masses), "masses": masses}


# ============================================================
#  LAPLACIANO
# ============================================================
def laplacian_signal(df: pd.DataFrame) -> dict:
    closes = df["close"].values
    if len(closes) < 20: return {"active": False, "ratio": 0}
    lap = [closes[i+1] - 2*closes[i] + closes[i-1] for i in range(1, len(closes)-1)]
    if len(lap) < 10: return {"active": False, "ratio": 0}
    norm_now = abs(lap[-1])
    norm_lag = sum(abs(x) for x in lap[-6:-1]) / 5
    if norm_lag == 0: return {"active": False, "ratio": 0}
    ratio = norm_now / norm_lag
    return {"active": ratio > PHI, "ratio": ratio}


# ============================================================
#  NIVELES
# ============================================================
def calculate_levels(df: pd.DataFrame, direction: str) -> dict:
    last  = df.iloc[-1]
    entry = last["close"]
    high  = df["high"].iloc[-50:].max()
    low   = df["low"].iloc[-50:].min()
    rango = high - low
    if direction == "long":
        sl  = min(last["ema50"], df["low"].iloc[-10:].min()) * 0.998
        tp1 = entry + (rango * PHI_INV * PHI_INV)
        tp2 = entry + (rango * PHI_INV)
        tp3 = entry * (1 + (rango / entry) * PHI_INV)
        tp4 = entry + (rango * PHI_INV * PHI)
    else:
        sl  = max(last["ema50"], df["high"].iloc[-10:].max()) * 1.002
        tp1 = entry - (rango * PHI_INV * PHI_INV)
        tp2 = entry - (rango * PHI_INV)
        tp3 = entry * (1 - (rango / entry) * PHI_INV)
        tp4 = entry - (rango * PHI_INV * PHI)
    risk = abs(entry - sl)
    return {
        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3, "tp4": tp4,
        "risk": risk,
        "rr_tp1": abs(tp1 - entry) / risk if risk > 0 else 0,
        "rr_tp2": abs(tp2 - entry) / risk if risk > 0 else 0,
        "rr_tp3": abs(tp3 - entry) / risk if risk > 0 else 0,
        "rr_tp4": abs(tp4 - entry) / risk if risk > 0 else 0,
    }


# ============================================================
#  GENERADOR DE SABANA
# ============================================================
def generate_signal_message(direction, levels, decoherence, masses,
                             session_name, w_clock, p_master, laplacian):
    side_emoji = "🟢 LONG" if direction == "long" else "🔴 SHORT"
    if p_master >= PHI**3:   leverage, sizing, tier = "8x", "10% equity", "φ³ (alta conviccion)"
    elif p_master >= PHI_SQ: leverage, sizing, tier = "5x", "5% equity",  "φ² (standard)"
    else:                    leverage, sizing, tier = "3x", "2% equity",  "φ (scalp)"
    masas_text = "\n".join([f"  • {m[0]}: ${m[1]:.2f}" for m in masses["masses"][:5]])

    msg = f"""🚨 <b>SEÑAL FQ v4.1 — DECOHERENCIA CONFIRMADA</b> 🚨

📊 <b>SOL/USDT PERPETUAL</b>
{side_emoji} · Confianza: {tier}
⏰ {cdmx_now_str()} · Sesion: <b>{session_name.upper()}</b> (W={w_clock})

━━━━━━━━━━━━━━━━━━━━━━━
🎯 <b>NIVELES DIVINOS</b>
━━━━━━━━━━━━━━━━━━━━━━━
Entrada:  <b>${levels['entry']:.2f}</b>
SL:       ${levels['sl']:.2f}  ({(levels['risk']/levels['entry']*100):.2f}%)

TP1 (30%): ${levels['tp1']:.2f}  · R:R {levels['rr_tp1']:.2f}
TP2 (30%): ${levels['tp2']:.2f}  · R:R {levels['rr_tp2']:.2f}
TP3 (25%): ${levels['tp3']:.2f}  ✨ <b>DIVINO</b> · R:R {levels['rr_tp3']:.2f}
TP4 (15%): ${levels['tp4']:.2f}  · R:R {levels['rr_tp4']:.2f}

⚙️ Apalancamiento max: <b>{leverage}</b>
💰 Tamaño: {sizing}

━━━━━━━━━━━━━━━━━━━━━━━
🔬 <b>DECOHERENCIA Theta(D) = 1</b>
━━━━━━━━━━━━━━━━━━━━━━━
✅ Macro: BTC {decoherence['macro']['btc_change']:+.2f}% · ETH {decoherence['macro']['eth_change']:+.2f}%
✅ Tecnica: {decoherence['tecnica']['aligned']}/{decoherence['tecnica']['total']} MAs alineadas
✅ Liquidez: RSI 6/12/24 = {decoherence['liquidez']['rsi6']:.0f}/{decoherence['liquidez']['rsi12']:.0f}/{decoherence['liquidez']['rsi24']:.0f}
✅ P-Space: {masses['count']} masas en confluencia
{('✅' if laplacian['active'] else '⚠️')} Laplaciano: ratio {laplacian['ratio']:.2f}

<b>Masas detectadas:</b>
{masas_text}

<b>P_master = {p_master:.2f}</b>

━━━━━━━━━━━━━━━━━━━━━━━
🛡️ <b>INVALIDACION</b>
━━━━━━━━━━━━━━━━━━━━━━━
• Cierre 15m {'<' if direction == 'long' else '>'} ${levels['sl']:.2f} → cerrar
• 90 min sin progreso → revisar
• SL nunca se mueve hacia abajo (Regla 4)

#FQv41 #SOLUSDT #{direction.upper()}"""
    return msg


# ============================================================
#  RESPUESTAS A COMANDOS
# ============================================================
def cmd_status(exchange) -> str:
    session_name, w_clock = get_session_weight()
    ventana = "✅ ACTIVA" if in_trading_window() else "⛔ INACTIVA (fuera de 07-15 CDMX)"
    uptime_delta = datetime.now(timezone.utc) - BOT_STATE["start_time"]
    horas = int(uptime_delta.total_seconds() // 3600)
    minutos = int((uptime_delta.total_seconds() % 3600) // 60)

    # Precio actual
    try:
        ticker = exchange.fetch_ticker(SYMBOL)
        sol_price = ticker["last"]
        sol_chg   = ticker.get("percentage", 0) or 0
        BOT_STATE["last_sol_price"] = sol_price
    except:
        sol_price = BOT_STATE["last_sol_price"]
        sol_chg   = 0

    ultima_señal = "Ninguna aún"
    if BOT_STATE["last_signal_ts"]:
        delta = datetime.now(timezone.utc) - BOT_STATE["last_signal_ts"]
        h = int(delta.total_seconds() // 3600)
        m = int((delta.total_seconds() % 3600) // 60)
        dir_str = BOT_STATE["last_signal_dir"].upper() if BOT_STATE["last_signal_dir"] else "?"
        ultima_señal = f"Hace {h}h {m}m · {dir_str} @ ${BOT_STATE['last_signal_price']:.2f}"

    return f"""📊 <b>STATUS — FQ v4.1 BOT</b>

🕐 {cdmx_now_str()}
⏱ Uptime: {horas}h {minutos}m
🔌 Exchange: OKX (datos en vivo)

━━━━━━━━━━━━━━━━━━━━━━━
💹 <b>MERCADO</b>
━━━━━━━━━━━━━━━━━━━━━━━
SOL/USDT: <b>${sol_price:.2f}</b> ({sol_chg:+.2f}%)
BTC 15m:  {BOT_STATE['last_btc_chg']:+.2f}%
ETH 15m:  {BOT_STATE['last_eth_chg']:+.2f}%

━━━━━━━━━━━━━━━━━━━━━━━
⚙️ <b>SISTEMA</b>
━━━━━━━━━━━━━━━━━━━━━━━
Ventana operativa: {ventana}
Sesion actual: <b>{session_name.upper()}</b> (W={w_clock})
Señales hoy: {BOT_STATE['signals_today']}
Señales total: {BOT_STATE['signals_total']}
Ultima señal: {ultima_señal}

━━━━━━━━━━━━━━━━━━━━━━━
🔬 <b>DECOHERENCIA ACTUAL</b>
━━━━━━━━━━━━━━━━━━━━━━━
Macro: BTC {BOT_STATE['last_btc_chg']:+.2f}% · ETH {BOT_STATE['last_eth_chg']:+.2f}%
Gate: {'✅ DECOHERENTE' if abs(BOT_STATE['last_btc_chg']) > 0.15 and abs(BOT_STATE['last_eth_chg']) > 0.15 else '⏳ EN SUPERPOSICION'}

#FQv41 #Status"""


def cmd_sesion() -> str:
    session_name, w_clock = get_session_weight()
    cdmx = timezone(timedelta(hours=-6))
    now  = datetime.now(cdmx)
    h    = now.hour + now.minute / 60.0

    sesiones = {
        "asia":    ("00:00 – 07:00 CDMX", "W=0.50 · Solo Asia exception (RSI<25 + CHoCH)"),
        "london":  ("02:00 – 07:30 CDMX", "W=0.80 · Apertura europea"),
        "overlap": ("07:30 – 10:00 CDMX", "W=1.20 · ⭐ MÁXIMA ENERGÍA · Interferencia constructiva"),
        "ny":      ("10:00 – 15:00 CDMX", "W=1.00 · Sesion NY pura"),
    }

    lineas = []
    for nombre, (horario, desc) in sesiones.items():
        activa = "▶️" if nombre == session_name else "  "
        lineas.append(f"{activa} <b>{nombre.upper()}</b>\n    {horario}\n    {desc}")

    mins_to_close = ""
    if session_name == "overlap":
        cierre = 10.0
        remaining_min = int((cierre - h) * 60)
        mins_to_close = f"\n⏰ Overlap cierra en: {remaining_min} minutos"
    elif session_name == "ny":
        cierre = 15.0
        remaining_min = int((cierre - h) * 60)
        mins_to_close = f"\n⏰ Ventana cierra en: {remaining_min} minutos"

    return f"""🕐 <b>SESION ACTUAL — FQ v4.1</b>

{cdmx_now_str()}
Sesion activa: <b>{session_name.upper()}</b>
W_clock: <b>{w_clock}</b>{mins_to_close}

━━━━━━━━━━━━━━━━━━━━━━━
📅 <b>CALENDARIO DE SESIONES</b>
━━━━━━━━━━━━━━━━━━━━━━━

{chr(10).join(lineas)}

━━━━━━━━━━━━━━━━━━━━━━━
💡 El W_clock multiplica P_master.
Overlap (1.20) = mayor probabilidad de señal válida.
Asia sin excepción = no trade bajo FQ v4.1.

#FQv41 #Clock"""


def cmd_analisis(exchange) -> str:
    try:
        df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
        df = add_indicators(df)
        last = df.iloc[-1]
        session_name, w_clock = get_session_weight()

        # Macro
        macro = test_macro_decoherence(exchange)
        direction = macro["direction"] or "long"

        # Tecnica y liquidez
        tecnica  = test_technical_decoherence(df, direction)
        liquidez = test_liquidity_decoherence(df, direction)
        masses   = detect_pspace_masses(df, direction)
        laplacian= laplacian_signal(df)

        # Gate
        theta_d = macro["passed"] and tecnica["passed"] and liquidez["passed"]

        # Nivel de Bollinger
        bb_pos = ""
        if not pd.isna(last.get("bb_upper", float("nan"))):
            if last["close"] > last["bb_upper"]:  bb_pos = "⚠️ Sobre BB Upper"
            elif last["close"] < last["bb_lower"]: bb_pos = "⚠️ Bajo BB Lower"
            else:                                  bb_pos = "✅ Dentro de Bollinger"

        return f"""🔬 <b>ANALISIS FQ v4.1 — EN VIVO</b>

⏰ {cdmx_now_str()}
💹 SOL/USDT: <b>${last['close']:.2f}</b>
Sesion: {session_name.upper()} (W={w_clock})

━━━━━━━━━━━━━━━━━━━━━━━
🎯 <b>GATE DECOHERENCIA Theta(D)</b>
━━━━━━━━━━━━━━━━━━━━━━━
{'✅' if macro['passed'] else '❌'} Macro: BTC {macro['btc_change']:+.2f}% · ETH {macro['eth_change']:+.2f}%
{'✅' if tecnica['passed'] else '❌'} Tecnica: {tecnica['aligned']}/{tecnica['total']} MAs alineadas
{'✅' if liquidez['passed'] else '❌'} Liquidez: RSI 6/12/24 = {liquidez['rsi6']:.0f}/{liquidez['rsi12']:.0f}/{liquidez['rsi24']:.0f}
{'✅' if masses['passed'] else '❌'} P-Space: {masses['count']} masas detectadas
{'✅' if laplacian['active'] else '⚠️'} Laplaciano: ratio {laplacian['ratio']:.2f}

<b>Theta(D) = {'1 ✅ DECOHERENTE' if theta_d else '0 ❌ EN SUPERPOSICION'}</b>

━━━━━━━━━━━━━━━━━━━━━━━
📐 <b>INDICADORES CLAVE</b>
━━━━━━━━━━━━━━━━━━━━━━━
EMA 50:  ${last['ema50']:.2f}
EMA 200: ${last['ema200']:.2f}
RSI 14:  {last['rsi14']:.1f}
MACD:    {last['macd']:.3f} / Signal: {last['macd_signal']:.3f}
{bb_pos}

━━━━━━━━━━━━━━━━━━━━━━━
🏁 <b>VEREDICTO</b>
━━━━━━━━━━━━━━━━━━━━━━━
{'🟢 SETUP EN FORMACION — esperar confirmacion' if theta_d else '⏳ SIN SETUP — mercado en superposicion'}
{'Ventana operativa: ✅ ACTIVA' if in_trading_window() else 'Ventana operativa: ⛔ INACTIVA'}

#FQv41 #Analisis"""
    except Exception as e:
        return f"❌ Error al analizar: {e}"


def cmd_about() -> str:
    return """🧬 <b>FIBONACCI CUÁNTICO v4.1</b>
<i>Emergent Time & Curved Price-Space</i>
by RasDG_Sol

━━━━━━━━━━━━━━━━━━━━━━━
📐 <b>FUNDAMENTOS</b>
━━━━━━━━━━━━━━━━━━━━━━━
El mercado no está en un estado definido.
Está en superposición de historias competidoras.
Una señal solo existe cuando esas historias colapsan.

<b>4 Pilares:</b>
I.   Decoherencia 3/3 (Hartle, Solvay 2005)
II.  Tiempo emergente — W_clock por sesion (Page-Wootters)
III. P-Space curvado por masas de liquidez (Oreste 2011)
IV.  Laplaciano discreto — ruptura de armonicidad (Knill 2020)

━━━━━━━━━━━━━━━━━━━━━━━
⚙️ <b>MASTER EQUATION v4.1</b>
━━━━━━━━━━━━━━━━━━━━━━━
P_master = Θ(D) · κ(p) · φⁿ · W_clock · H_Laplaciano

Si Θ(D) = 0 → P_master = 0 → no trade.
Sin excepcion. Sin override.

━━━━━━━━━━━━━━━━━━━━━━━
📊 <b>PARAMETROS</b>
━━━━━━━━━━━━━━━━━━━━━━━
Par: SOL/USDT Perpetual
Exchange datos: OKX
Timeframe: 15 minutos
Ventana: 07:00–15:00 CDMX
Max leverage: 8x (φ³-coupled)
Cooldown: 2h entre señales

φ = 1.6180339887

#FQv41 #RasDG"""


def cmd_help() -> str:
    return """🤖 <b>FQ v4.1 SIGNAL BOT — COMANDOS</b>

/status — Estado del bot y mercado en tiempo real
/analisis — Análisis FQ v4.1 completo de SOL/USDT ahora mismo
/sesion — Sesión activa, W_clock y calendario de sesiones
/about — Sobre el sistema Fibonacci Cuántico v4.1
/help — Esta ayuda

━━━━━━━━━━━━━━━━━━━━━━━
📡 <b>SEÑALES AUTOMATICAS</b>
━━━━━━━━━━━━━━━━━━━━━━━
El bot monitorea SOL/USDT cada 15 minutos.
Solo envía señal cuando Theta(D)=1 (decoherencia 3/3).
Promedio: 1-3 señales por día de alta convicción.

El silencio es disciplina. No cantidad, calidad.

#FQv41"""


# ============================================================
#  MOTOR DE EVALUACION
# ============================================================
def evaluate_setup(exchange) -> bool:
    if not in_trading_window():
        return False
    df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
    df = add_indicators(df)
    if len(df) < 50:
        log.warning("Datos insuficientes")
        return False
    BOT_STATE["last_sol_price"] = df["close"].iloc[-1]
    BOT_STATE["last_eval_ts"]   = datetime.now(timezone.utc)
    session_name, w_clock = get_session_weight()
    macro = test_macro_decoherence(exchange)
    if not macro["passed"]:
        log.info(f"Macro NO decoherente: BTC {macro['btc_change']:.2f}% / ETH {macro['eth_change']:.2f}%")
        return False
    direction = macro["direction"]
    log.info(f"Macro decoherente: {direction.upper()}")
    tecnica = test_technical_decoherence(df, direction)
    if not tecnica["passed"]:
        log.info(f"Tecnica NO decoherente: {tecnica['aligned']}/{tecnica['total']}")
        return False
    liquidez = test_liquidity_decoherence(df, direction)
    if not liquidez["passed"]:
        log.info(f"Liquidez NO decoherente: RSI {liquidez['rsi6']:.0f}/{liquidez['rsi12']:.0f}/{liquidez['rsi24']:.0f}")
        return False
    masses = detect_pspace_masses(df, direction)
    if not masses["passed"]:
        log.info(f"P-Space insuficiente: {masses['count']} masas")
        return False
    laplacian = laplacian_signal(df)
    h_factor  = 1.0 if laplacian["active"] else 0.7
    p_master  = 1.0 * 1.0 * (PHI ** 1) * w_clock * h_factor
    p_master *= 1 + (masses["count"] - 3) * 0.15
    if p_master < PHI_SQ:
        log.info(f"P_master {p_master:.2f} < phi^2 ({PHI_SQ:.2f})")
        return False
    levels = calculate_levels(df, direction)
    if levels["rr_tp3"] < 2.0:
        log.info(f"R:R TP divino insuficiente: {levels['rr_tp3']:.2f}")
        return False
    decoherence = {"macro": macro, "tecnica": tecnica, "liquidez": liquidez}
    msg = generate_signal_message(direction, levels, decoherence, masses,
                                   session_name, w_clock, p_master, laplacian)
    if send_telegram(msg):
        log.info(f"✅ SEÑAL ENVIADA: {direction.upper()} · P_master {p_master:.2f}")
        BOT_STATE["last_signal_ts"]    = datetime.now(timezone.utc)
        BOT_STATE["last_signal_dir"]   = direction
        BOT_STATE["last_signal_price"] = levels["entry"]
        BOT_STATE["signals_today"]    += 1
        BOT_STATE["signals_total"]    += 1
        return True
    return False


# ============================================================
#  HILO DE COMANDOS — escucha mensajes entrantes
# ============================================================
def command_listener(exchange):
    """Hilo separado que escucha mensajes entrantes y responde comandos."""
    log.info("Command listener iniciado")
    while True:
        try:
            updates = get_telegram_updates(BOT_STATE["telegram_offset"])
            for update in updates:
                BOT_STATE["telegram_offset"] = update["update_id"] + 1
                msg = update.get("message", {})
                text = msg.get("text", "").strip().lower()
                chat_id = str(msg.get("chat", {}).get("id", ""))

                # Solo responde al chat autorizado
                if chat_id != TELEGRAM_CHAT_ID:
                    continue

                log.info(f"Comando recibido: {text}")

                if text in ["/status", "/status@rasdg_quantum_signals_bot"]:
                    send_telegram(cmd_status(exchange), chat_id)

                elif text in ["/analisis", "/analisis@rasdg_quantum_signals_bot"]:
                    send_telegram("⏳ Analizando mercado en tiempo real...", chat_id)
                    send_telegram(cmd_analisis(exchange), chat_id)

                elif text in ["/sesion", "/sesion@rasdg_quantum_signals_bot"]:
                    send_telegram(cmd_sesion(), chat_id)

                elif text in ["/about", "/about@rasdg_quantum_signals_bot"]:
                    send_telegram(cmd_about(), chat_id)

                elif text in ["/help", "/help@rasdg_quantum_signals_bot", "/start"]:
                    send_telegram(cmd_help(), chat_id)

            time.sleep(3)

        except Exception as e:
            log.error(f"Error en command_listener: {e}")
            time.sleep(10)


# ============================================================
#  LOOP PRINCIPAL
# ============================================================
def main():
    log.info("=" * 60)
    log.info("  FQ v4.1 SIGNAL BOT — RasDG_Sol")
    log.info("=" * 60)

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("FALTA TELEGRAM_TOKEN o TELEGRAM_CHAT_ID")
        return

    send_telegram(
        "🤖 <b>Bot FQ v4.1 ACTIVO</b>\n"
        "Monitoreando SOL/USDT cada 15 min.\n"
        "Solo enviaré señales con decoherencia 3/3 confirmada.\n\n"
        "Comandos disponibles: /status /analisis /sesion /about /help"
    )

    exchange = ccxt.okx({"enableRateLimit": True})

    # Iniciar hilo de comandos en paralelo
    listener = threading.Thread(
        target=command_listener,
        args=(exchange,),
        daemon=True
    )
    listener.start()

    last_candle_ts = None
    last_signal_ts = None
    cooldown       = timedelta(hours=2)

    while True:
        try:
            df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=2)
            current_ts = df["timestamp"].iloc[-1]

            if last_candle_ts is None or current_ts > last_candle_ts:
                last_candle_ts = current_ts
                BOT_STATE["last_candle_ts"] = current_ts
                log.info(f"Vela nueva: {current_ts}")

                now = datetime.now(timezone.utc)
                if last_signal_ts and (now - last_signal_ts) < cooldown:
                    remaining = cooldown - (now - last_signal_ts)
                    log.info(f"Cooldown activo: {remaining}")
                else:
                    if evaluate_setup(exchange):
                        last_signal_ts = now
                        BOT_STATE["last_signal_ts"] = now

            time.sleep(CHECK_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            log.info("Bot detenido por usuario")
            break
        except Exception as e:
            log.error(f"Error en loop: {e}")
            time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
