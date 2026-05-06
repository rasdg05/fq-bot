"""
========================================================================
  FQ v4.1 SIGNAL BOT — RasDG_Sol
  Fibonacci Cuántico v4.1 — Emergent Time & Curved Price-Space
  
  Monitorea SOL/USDT cada 15 minutos.
  Aplica gate de decoherencia 3/3 + P-Space + Laplaciano.
  Envía señales a Telegram solo si Theta(D)=1 y P_master >= phi^2.
========================================================================
"""

import os
import time
import logging
from datetime import datetime, timezone, timedelta

import ccxt
import pandas as pd
import pandas_ta as ta
import requests

# ============================================================
#  CONFIGURACION (se lee de variables de entorno en Railway)
# ============================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SYMBOL = "SOL/USDT:USDT"           # Perpetuo en Binance
TIMEFRAME = "15m"
CHECK_INTERVAL_SECONDS = 60        # Revisa cada 60 segundos si hay vela nueva

# ============================================================
#  CONSTANTES FQ v4.1
# ============================================================
PHI = 1.6180339887
PHI_SQ = PHI * PHI                 # 2.618
PHI_INV = 1 / PHI                  # 0.618

# Pesos de sesion (CDMX, UTC-6)
SESSION_WEIGHTS = {
    "asia":    0.50,
    "london":  0.80,
    "ny":      1.00,
    "overlap": 1.20,
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
def send_telegram(message: str) -> bool:
    """Envia mensaje a Telegram. Retorna True si exitoso."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("TELEGRAM_TOKEN o TELEGRAM_CHAT_ID no configurados")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            return True
        log.error(f"Telegram error {r.status_code}: {r.text}")
        return False
    except Exception as e:
        log.error(f"Telegram exception: {e}")
        return False


# ============================================================
#  FETCH DE DATOS DE MERCADO
# ============================================================
def fetch_ohlcv(exchange, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
    """Descarga velas y retorna DataFrame con OHLCV."""
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


# ============================================================
#  CALCULO DE INDICADORES
# ============================================================
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega RSI, EMAs, Bollinger Bands, MACD."""
    df = df.copy()
    
    # RSI multi-periodo (Triple RSI FQ)
    df["rsi6"] = ta.rsi(df["close"], length=6)
    df["rsi12"] = ta.rsi(df["close"], length=12)
    df["rsi14"] = ta.rsi(df["close"], length=14)
    df["rsi24"] = ta.rsi(df["close"], length=24)
    
    # EMAs
    df["ema9"] = ta.ema(df["close"], length=9)
    df["ema20"] = ta.ema(df["close"], length=20)
    df["ema50"] = ta.ema(df["close"], length=50)
    df["ema200"] = ta.ema(df["close"], length=200)
    
    # SMAs
    df["sma20"] = ta.sma(df["close"], length=20)
    df["sma50"] = ta.sma(df["close"], length=50)
    
    # Bollinger Bands (20, 2)
    bb = ta.bbands(df["close"], length=20, std=2)
    if bb is not None and not bb.empty:
        df["bb_lower"] = bb.iloc[:, 0]
        df["bb_mid"] = bb.iloc[:, 1]
        df["bb_upper"] = bb.iloc[:, 2]
    
    # MACD
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        df["macd"] = macd.iloc[:, 0]
        df["macd_signal"] = macd.iloc[:, 2]
        df["macd_hist"] = macd.iloc[:, 1]
    
    # Volumen MA
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    
    return df


# ============================================================
#  CLOCK (sesion CDMX)
# ============================================================
def get_session_weight() -> tuple[str, float]:
    """Determina sesion actual y peso W_clock."""
    cdmx = timezone(timedelta(hours=-6))
    now = datetime.now(cdmx)
    h = now.hour + now.minute / 60.0
    
    # Overlap London/NY: 07:30 - 10:00 CDMX
    if 7.5 <= h < 10.0:
        return ("overlap", SESSION_WEIGHTS["overlap"])
    # NY: 10:00 - 15:00 CDMX
    if 10.0 <= h < 15.0:
        return ("ny", SESSION_WEIGHTS["ny"])
    # London: 02:00 - 07:30 CDMX
    if 2.0 <= h < 7.5:
        return ("london", SESSION_WEIGHTS["london"])
    # Asia (resto)
    return ("asia", SESSION_WEIGHTS["asia"])


def in_trading_window() -> bool:
    """Solo opera 07:00 - 15:00 CDMX."""
    cdmx = timezone(timedelta(hours=-6))
    now = datetime.now(cdmx)
    h = now.hour
    return 7 <= h < 15


# ============================================================
#  TEST DE DECOHERENCIA Theta(D) 3/3
# ============================================================
def test_macro_decoherence(exchange) -> dict:
    """BTC + ETH 15m direccion alcista o bajista alineada."""
    result = {"passed": False, "direction": None, "btc_change": 0, "eth_change": 0}
    try:
        btc = fetch_ohlcv(exchange, "BTC/USDT:USDT", "15m", limit=20)
        eth = fetch_ohlcv(exchange, "ETH/USDT:USDT", "15m", limit=20)
        
        btc_chg = (btc["close"].iloc[-1] - btc["close"].iloc[-4]) / btc["close"].iloc[-4]
        eth_chg = (eth["close"].iloc[-1] - eth["close"].iloc[-4]) / eth["close"].iloc[-4]
        
        result["btc_change"] = btc_chg * 100
        result["eth_change"] = eth_chg * 100
        
        # Mismo signo y movimiento >= 0.15%
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
    """Verifica >= 11 de 13 MAs alineadas con la direccion."""
    last = df.iloc[-1]
    price = last["close"]
    
    mas = {
        "ema9": last["ema9"],
        "ema20": last["ema20"],
        "ema50": last["ema50"],
        "ema200": last["ema200"],
        "sma20": last["sma20"],
        "sma50": last["sma50"],
    }
    
    aligned = 0
    total = 0
    for name, val in mas.items():
        if pd.isna(val):
            continue
        total += 1
        if direction == "long" and price > val:
            aligned += 1
        elif direction == "short" and price < val:
            aligned += 1
    
    # MACD
    if not pd.isna(last["macd"]):
        total += 1
        if direction == "long" and last["macd"] > last["macd_signal"]:
            aligned += 1
        elif direction == "short" and last["macd"] < last["macd_signal"]:
            aligned += 1
    
    # Necesitamos >= 5 de 7 (proxy del 11/13 de TradingView)
    passed = aligned >= 5 and total >= 6
    
    return {
        "passed": passed,
        "aligned": aligned,
        "total": total,
    }


def test_liquidity_decoherence(df: pd.DataFrame, direction: str) -> dict:
    """RSI multi-periodo en mismo regimen."""
    last = df.iloc[-1]
    rsi6 = last["rsi6"]
    rsi12 = last["rsi12"]
    rsi24 = last["rsi24"]
    
    if pd.isna(rsi6) or pd.isna(rsi12) or pd.isna(rsi24):
        return {"passed": False, "rsi6": 0, "rsi12": 0, "rsi24": 0}
    
    if direction == "long":
        passed = rsi6 > 50 and rsi12 > 50 and rsi24 > 50
    else:
        passed = rsi6 < 50 and rsi12 < 50 and rsi24 < 50
    
    return {
        "passed": passed,
        "rsi6": rsi6,
        "rsi12": rsi12,
        "rsi24": rsi24,
    }


# ============================================================
#  P-SPACE: detector de masas en confluencia
# ============================================================
def detect_pspace_masses(df: pd.DataFrame, direction: str) -> dict:
    """Cuenta masas P-Space cerca del precio actual."""
    last = df.iloc[-1]
    price = last["close"]
    masses = []
    threshold = price * 0.005  # 0.5% de tolerancia
    
    # Estructurales: high/low de las ultimas 50 velas
    high_50 = df["high"].iloc[-50:].max()
    low_50 = df["low"].iloc[-50:].min()
    if abs(price - high_50) <= threshold:
        masses.append(("Resistencia estructural 50v", high_50, 1.0))
    if abs(price - low_50) <= threshold:
        masses.append(("Soporte estructural 50v", low_50, 1.0))
    
    # Tecnicas: EMAs
    for name, val in [("EMA50", last["ema50"]), ("EMA200", last["ema200"]),
                       ("SMA20", last["sma20"]), ("SMA50", last["sma50"])]:
        if not pd.isna(val) and abs(price - val) <= threshold:
            masses.append((name, val, 0.6))
    
    # Bollinger
    if not pd.isna(last["bb_upper"]) and abs(price - last["bb_upper"]) <= threshold:
        masses.append(("BB Upper", last["bb_upper"], 0.6))
    if not pd.isna(last["bb_lower"]) and abs(price - last["bb_lower"]) <= threshold:
        masses.append(("BB Lower", last["bb_lower"], 0.6))
    
    # Volumen anomalo (vela actual con volumen > 2x media)
    if not pd.isna(last["vol_ma20"]) and last["volume"] > 2 * last["vol_ma20"]:
        masses.append(("Volumen anomalo", price, 0.9))
    
    # Psicologicos: numeros redondos cercanos
    rounded = round(price)
    if abs(price - rounded) <= threshold:
        masses.append((f"Psicologico ${rounded}", rounded, 0.8))
    
    return {
        "passed": len(masses) >= 3,
        "count": len(masses),
        "masses": masses,
    }


# ============================================================
#  LAPLACIANO DISCRETO: ruptura de armonicidad
# ============================================================
def laplacian_signal(df: pd.DataFrame) -> dict:
    """Detecta ruptura de armonicidad via norma Laplaciana lagged Fibonacci."""
    closes = df["close"].values
    if len(closes) < 20:
        return {"active": False, "ratio": 0}
    
    # Laplaciano discreto: f(n+1) - 2f(n) + f(n-1)
    lap = []
    for i in range(1, len(closes) - 1):
        lap.append(closes[i + 1] - 2 * closes[i] + closes[i - 1])
    
    if len(lap) < 10:
        return {"active": False, "ratio": 0}
    
    # Norma actual vs lag-5 (Fibonacci)
    norm_now = abs(lap[-1])
    norm_lag = sum(abs(x) for x in lap[-6:-1]) / 5  # promedio 5 anteriores
    
    if norm_lag == 0:
        return {"active": False, "ratio": 0}
    
    ratio = norm_now / norm_lag
    return {
        "active": ratio > PHI,  # > 1.618
        "ratio": ratio,
    }


# ============================================================
#  CALCULO DE NIVELES (entrada, SL, TPs)
# ============================================================
def calculate_levels(df: pd.DataFrame, direction: str) -> dict:
    """Calcula entrada, SL estructural y TPs divinos via phi."""
    last = df.iloc[-1]
    entry = last["close"]
    
    # Rango de referencia: max y min ultimas 50 velas
    high = df["high"].iloc[-50:].max()
    low = df["low"].iloc[-50:].min()
    rango = high - low
    
    if direction == "long":
        sl = min(last["ema50"], df["low"].iloc[-10:].min()) * 0.998  # 0.2% buffer
        tp1 = entry + (rango * PHI_INV * PHI_INV)  # phi^-2
        tp2 = entry + (rango * PHI_INV)            # phi^-1
        tp3 = entry * (1 + (rango / entry) * PHI_INV)  # TP DIVINO
        tp4 = entry + (rango * PHI_INV * PHI)      # phi
    else:
        sl = max(last["ema50"], df["high"].iloc[-10:].max()) * 1.002
        tp1 = entry - (rango * PHI_INV * PHI_INV)
        tp2 = entry - (rango * PHI_INV)
        tp3 = entry * (1 - (rango / entry) * PHI_INV)
        tp4 = entry - (rango * PHI_INV * PHI)
    
    risk = abs(entry - sl)
    
    return {
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,  # Divino
        "tp4": tp4,
        "risk": risk,
        "rr_tp1": abs(tp1 - entry) / risk if risk > 0 else 0,
        "rr_tp2": abs(tp2 - entry) / risk if risk > 0 else 0,
        "rr_tp3": abs(tp3 - entry) / risk if risk > 0 else 0,
        "rr_tp4": abs(tp4 - entry) / risk if risk > 0 else 0,
    }


# ============================================================
#  GENERADOR DE SABANA TELEGRAM
# ============================================================
def generate_signal_message(direction, levels, decoherence, masses,
                             session_name, w_clock, p_master, laplacian):
    """Genera la sabana completa estilo RasDG."""
    side_emoji = "🟢 LONG" if direction == "long" else "🔴 SHORT"
    
    if p_master >= PHI ** 3:
        leverage = "8x"
        sizing = "10% equity"
        tier = "phi^3 (alta conviccion)"
    elif p_master >= PHI_SQ:
        leverage = "5x"
        sizing = "5% equity"
        tier = "phi^2 (standard)"
    else:
        leverage = "3x"
        sizing = "2% equity"
        tier = "phi (scalp)"
    
    masas_text = "\n".join([f"  • {m[0]}: ${m[1]:.2f}" for m in masses["masses"][:5]])
    
    cdmx = timezone(timedelta(hours=-6))
    now_str = datetime.now(cdmx).strftime("%Y-%m-%d %H:%M CDMX")
    
    msg = f"""🚨 <b>SEÑAL FQ v4.1 — DECOHERENCIA CONFIRMADA</b> 🚨

📊 <b>SOL/USDT PERPETUAL</b>
{side_emoji} · Confianza: {tier}
⏰ {now_str} · Sesion: <b>{session_name.upper()}</b> (W={w_clock})

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

#FQv41 #SOLUSDT #{direction.upper()}
"""
    return msg


# ============================================================
#  MOTOR PRINCIPAL DE EVALUACION
# ============================================================
def evaluate_setup(exchange) -> bool:
    """Evalua la oportunidad actual. Retorna True si envio señal."""
    
    # 1. Ventana horaria
    if not in_trading_window():
        return False
    
    # 2. Datos
    df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=200)
    df = add_indicators(df)
    
    if len(df) < 50:
        log.warning("Datos insuficientes")
        return False
    
    # 3. Sesion
    session_name, w_clock = get_session_weight()
    
    # 4. Macro decoherence (define direccion)
    macro = test_macro_decoherence(exchange)
    if not macro["passed"]:
        log.info(f"Macro NO decoherente: BTC {macro['btc_change']:.2f}% / ETH {macro['eth_change']:.2f}%")
        return False
    
    direction = macro["direction"]
    log.info(f"Macro decoherente: {direction.upper()}")
    
    # 5. Tecnica decoherence
    tecnica = test_technical_decoherence(df, direction)
    if not tecnica["passed"]:
        log.info(f"Tecnica NO decoherente: {tecnica['aligned']}/{tecnica['total']}")
        return False
    
    # 6. Liquidez decoherence
    liquidez = test_liquidity_decoherence(df, direction)
    if not liquidez["passed"]:
        log.info(f"Liquidez NO decoherente: RSI {liquidez['rsi6']:.0f}/{liquidez['rsi12']:.0f}/{liquidez['rsi24']:.0f}")
        return False
    
    # 7. P-Space (>= 3 masas)
    masses = detect_pspace_masses(df, direction)
    if not masses["passed"]:
        log.info(f"P-Space insuficiente: {masses['count']} masas")
        return False
    
    # 8. Laplaciano (preferido pero no obligatorio, penaliza si no)
    laplacian = laplacian_signal(df)
    h_factor = 1.0 if laplacian["active"] else 0.7
    
    # 9. Calcular P_master
    n_aligned = 1  # solo evaluamos 15m por ahora
    p_master = 1.0 * 1.0 * (PHI ** n_aligned) * w_clock * h_factor
    
    # Boost por confluencia de masas
    p_master *= 1 + (masses["count"] - 3) * 0.15
    
    if p_master < PHI_SQ:
        log.info(f"P_master {p_master:.2f} < phi^2 ({PHI_SQ:.2f})")
        return False
    
    # 10. Calcular niveles y enviar
    levels = calculate_levels(df, direction)
    
    # Validacion final: R:R TP3 >= 2.0
    if levels["rr_tp3"] < 2.0:
        log.info(f"R:R TP divino insuficiente: {levels['rr_tp3']:.2f}")
        return False
    
    decoherence = {
        "macro": macro,
        "tecnica": tecnica,
        "liquidez": liquidez,
    }
    
    msg = generate_signal_message(direction, levels, decoherence, masses,
                                    session_name, w_clock, p_master, laplacian)
    
    if send_telegram(msg):
        log.info(f"✅ SEÑAL ENVIADA: {direction.upper()} · P_master {p_master:.2f}")
        return True
    return False


# ============================================================
#  LOOP PRINCIPAL
# ============================================================
def main():
    log.info("=" * 60)
    log.info("  FQ v4.1 SIGNAL BOT — RasDG_Sol")
    log.info("=" * 60)
    
    # Validar config
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("FALTA TELEGRAM_TOKEN o TELEGRAM_CHAT_ID")
        return
    
    # Mensaje de arranque
    send_telegram(
        "🤖 <b>Bot FQ v4.1 ACTIVO</b>\n"
        "Monitoreando SOL/USDT cada 15 min.\n"
        "Solo enviare señales con decoherencia 3/3 confirmada."
    )
    
    # Init exchange
    exchange = ccxt.binance({
        "options": {"defaultType": "swap"},
        "enableRateLimit": True,
    })
    
    last_candle_ts = None
    last_signal_ts = None
    cooldown = timedelta(hours=2)  # Min 2h entre señales
    
    while True:
        try:
            # Solo revisar cuando hay vela 15m nueva cerrada
            df = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=2)
            current_ts = df["timestamp"].iloc[-1]
            
            if last_candle_ts is None or current_ts > last_candle_ts:
                last_candle_ts = current_ts
                log.info(f"Vela nueva: {current_ts}")
                
                # Cooldown
                now = datetime.now(timezone.utc)
                if last_signal_ts and (now - last_signal_ts) < cooldown:
                    remaining = cooldown - (now - last_signal_ts)
                    log.info(f"Cooldown activo: {remaining}")
                else:
                    if evaluate_setup(exchange):
                        last_signal_ts = now
            
            time.sleep(CHECK_INTERVAL_SECONDS)
        
        except KeyboardInterrupt:
            log.info("Bot detenido por usuario")
            break
        except Exception as e:
            log.error(f"Error en loop: {e}")
            time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
