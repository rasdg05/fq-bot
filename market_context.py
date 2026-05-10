# -*- coding: utf-8 -*-
"""
================================================================================
  MARKET CONTEXT MODULE - FQ v4.1 Bot v3.1
  Real-time mirror of internal + external market state
================================================================================

  Funciones:
    - Funding rate, Open Interest, Long/Short ratio (OKX)
    - Order book depth y liquidity walls
    - Detector de eventos: CHoCH, breakouts, divergencias RSI, volumen anomalo
    - Snapshots especializados por comando (inteligentes)

  Filosofia:
    Claude ve EXACTAMENTE lo que el bot ve, vela por vela.
    Por dentro: indicadores, masas, decoherencia, P_master
    Por fuera: funding, OI, walls, sentiment de derivatives
    Eventos pre-detectados: el bot hace el grunt work, Claude interpreta

================================================================================
"""
import logging
import traceback
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone

log = logging.getLogger("fq_market_ctx")

# ============================================================
# OKX ENDPOINTS (publicos, no requieren auth)
# ============================================================
OKX_BASE = "https://www.okx.com"

def _safe_get(url, params=None, timeout=10):
    """
    GET con diagnostico explicito.
    Loguea status code y mensaje de OKX para que fallos no sean silenciosos.
    Causas comunes de fallo:
      - 403: geo-block del datacenter (OKX bloquea muchas IPs cloud)
      - 429: rate limit
      - 50029: error de OKX (instId invalido, parametros mal)
    """
    short = url.replace("https://www.okx.com", "")
    try:
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code != 200:
            log.warning("OKX HTTP {} on {} (params={}) body={}".format(
                r.status_code, short, params, r.text[:200]))
            return None
        data = r.json()
        code = data.get("code")
        if code != "0":
            log.warning("OKX code={} msg={} on {} (params={})".format(
                code, data.get("msg", ""), short, params))
            return None
        return data.get("data", [])
    except requests.exceptions.Timeout:
        log.warning("OKX TIMEOUT on {} (params={})".format(short, params))
    except Exception as e:
        log.warning("OKX exception {} on {} (params={}): {}".format(
            type(e).__name__, short, params, e))
    return None

# ============================================================
# BYBIT FALLBACK (V5 API - perpetuals linear)
# Bybit V5 funciona desde IPs de cloud US (Railway, AWS us-east, etc.)
# sin geo-block. Binance fapi devuelve HTTP 451 desde esas ubicaciones.
# ============================================================
BYBIT_BASE = "https://api.bybit.com"

# Mapeo simbolo: SOL-USDT-SWAP (OKX) -> SOLUSDT (Bybit)
def _okx_to_bybit_symbol(okx_sym):
    if okx_sym.endswith("-USDT-SWAP"):
        return okx_sym.replace("-USDT-SWAP", "USDT")
    return okx_sym.replace("-", "")

def _safe_get_bybit(path, params=None, timeout=10):
    """GET a Bybit V5 con diagnostico explicito.
    Bybit envuelve la respuesta en {retCode, retMsg, result: {...}}."""
    url = "{}{}".format(BYBIT_BASE, path)
    try:
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code != 200:
            log.warning("Bybit HTTP {} on {} (params={}) body={}".format(
                r.status_code, path, params, r.text[:200]))
            return None
        data = r.json()
        if data.get("retCode") != 0:
            log.warning("Bybit retCode={} retMsg={} on {} (params={})".format(
                data.get("retCode"), data.get("retMsg"), path, params))
            return None
        return data.get("result", {})
    except requests.exceptions.Timeout:
        log.warning("Bybit TIMEOUT on {} (params={})".format(path, params))
    except Exception as e:
        log.warning("Bybit exception {} on {} (params={}): {}".format(
            type(e).__name__, path, params, e))
    return None

def get_funding_rate_bybit(symbol="SOL-USDT-SWAP"):
    """Funding rate desde Bybit V5 (/v5/market/tickers)."""
    bsym = _okx_to_bybit_symbol(symbol)
    result = _safe_get_bybit("/v5/market/tickers",
                             params={"category": "linear", "symbol": bsym})
    if not result:
        return None
    try:
        items = result.get("list", [])
        if not items:
            return None
        d = items[0]
        funding = float(d.get("fundingRate", 0))  # ya viene como decimal, ej 0.0001
        next_time_ms = int(d.get("nextFundingTime", 0))
        return {
            "current_pct":   funding * 100,
            "next_pct":      funding * 100,  # Bybit no separa current/next
            "next_time_ms":  next_time_ms,
            "next_time_str": datetime.fromtimestamp(next_time_ms / 1000, tz=timezone.utc).strftime("%H:%M UTC") if next_time_ms else "N/A",
            "_source":       "bybit",
        }
    except Exception as e:
        log.warning("Bybit funding parse error: {}".format(e))
        return None

def get_open_interest_bybit(symbol="SOL-USDT-SWAP"):
    """OI actual desde Bybit V5. Tickers ya trae openInterest + openInterestValue."""
    bsym = _okx_to_bybit_symbol(symbol)
    result = _safe_get_bybit("/v5/market/tickers",
                             params={"category": "linear", "symbol": bsym})
    if not result:
        return None
    try:
        items = result.get("list", [])
        if not items:
            return None
        d = items[0]
        oi_contracts = float(d.get("openInterest", 0))
        oi_usd       = float(d.get("openInterestValue", 0))
        return {
            "contracts": oi_contracts,
            "usd":       oi_usd,
            "millions":  oi_usd / 1_000_000,
            "_source":   "bybit",
        }
    except Exception as e:
        log.warning("Bybit OI parse error: {}".format(e))
        return None

def get_oi_history_bybit(symbol="SOL-USDT-SWAP", period="15min", limit=10):
    """OI history desde Bybit V5 (/v5/market/open-interest).
    Periodos validos: 5min, 15min, 30min, 1h, 4h, 1d.
    """
    bsym = _okx_to_bybit_symbol(symbol)
    result = _safe_get_bybit("/v5/market/open-interest",
                             params={"category": "linear", "symbol": bsym,
                                     "intervalTime": period, "limit": limit})
    if not result:
        return None
    try:
        items = result.get("list", [])
        if not items:
            return None
        # Bybit devuelve mas reciente PRIMERO (igual que OKX) - no invertir
        out = []
        for x in items:
            out.append({
                "ts":  int(x.get("timestamp", 0)),
                "oi":  float(x.get("openInterest", 0)),
                "vol": 0.0,  # Bybit en este endpoint no expone volumen junto al OI
            })
        return out[:limit]
    except Exception as e:
        log.warning("Bybit OI history parse error: {}".format(e))
        return None

def get_long_short_ratio_bybit(symbol="SOL", period="15min"):
    """L/S ratio desde Bybit V5 (/v5/market/account-ratio).
    Bybit devuelve buyRatio/sellRatio que suman 1.0; ratio = buy/sell.
    """
    bsym = "{}USDT".format(symbol) if not symbol.endswith("USDT") else symbol
    result = _safe_get_bybit("/v5/market/account-ratio",
                             params={"category": "linear", "symbol": bsym,
                                     "period": period, "limit": 5})
    if not result:
        return None
    try:
        items = result.get("list", [])
        if not items:
            return None
        # Bybit: mas reciente primero
        ratios = []
        for x in items:
            buy  = float(x.get("buyRatio", 0))
            sell = float(x.get("sellRatio", 0))
            if sell > 0:
                ratios.append(buy / sell)
        if not ratios:
            return None
        current = ratios[0]
        avg_5 = sum(ratios) / len(ratios)
        return {"current": current, "avg_5": avg_5, "history": ratios, "_source": "bybit"}
    except Exception as e:
        log.warning("Bybit L/S parse error: {}".format(e))
        return None

# ============================================================
# FUNDING RATE
# ============================================================
def _safe_float(v, default=0.0):
    """float() tolerante: strings vacios, None, o invalidos -> default."""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def _safe_int(v, default=0):
    """int() tolerante: strings vacios, None, o invalidos -> default."""
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default

def get_funding_rate(symbol="SOL-USDT-SWAP"):
    """
    Funding rate actual + proximo timestamp.
    Funding > 0: longs pagan a shorts (mercado long-heavy)
    Funding < 0: shorts pagan a longs (mercado short-heavy)
    Si OKX falla (geo-block en VPS), cae a Bybit fapi automaticamente.
    """
    data = _safe_get("{}/api/v5/public/funding-rate".format(OKX_BASE),
                     params={"instId": symbol})
    if not data:
        log.info("Funding: OKX fallo, intentando Bybit fallback...")
        return get_funding_rate_bybit(symbol)
    d = data[0]
    try:
        funding      = _safe_float(d.get("fundingRate"))
        next_funding = _safe_float(d.get("nextFundingRate"))
        next_time    = _safe_int(d.get("nextFundingTime"))
        return {
            "current_pct":   funding * 100,
            "next_pct":      next_funding * 100,
            "next_time_ms":  next_time,
            "next_time_str": datetime.fromtimestamp(next_time / 1000, tz=timezone.utc).strftime("%H:%M UTC") if next_time else "N/A",
            "_source":       "okx",
        }
    except Exception as e:
        log.warning("Funding: OKX parse fallo (raw={}, err={}), intentando Bybit fallback...".format(
            d, e))
        return get_funding_rate_bybit(symbol)

def funding_interpretation(funding_pct):
    """Interpretacion cualitativa del funding"""
    if funding_pct > 0.05:    return "EXTREMO LONG - squeeze short improbable, longs muy apilados (peligro de flush)"
    if funding_pct > 0.02:    return "ALTO LONG - longs cargados, riesgo de pullback"
    if funding_pct > 0.005:   return "Neutral-long - presion alcista normal"
    if funding_pct > -0.005:  return "NEUTRAL - mercado balanceado"
    if funding_pct > -0.02:   return "Neutral-short - presion bajista moderada"
    if funding_pct > -0.05:   return "ALTO SHORT - shorts cargados, riesgo de squeeze alcista"
    return "EXTREMO SHORT - squeeze long improbable, shorts muy apilados (peligro de squeeze)"

# ============================================================
# OPEN INTEREST
# ============================================================
def get_open_interest(symbol="SOL-USDT-SWAP"):
    """
    Open Interest = numero de contratos abiertos.
    Crecimiento de OI + precio subiendo = nuevas posiciones long
    Crecimiento de OI + precio bajando = nuevas posiciones short
    OI cayendo = cierre de posiciones
    Fallback automatico a Bybit si OKX falla.
    """
    data = _safe_get("{}/api/v5/public/open-interest".format(OKX_BASE),
                     params={"instType": "SWAP", "instId": symbol})
    if not data:
        log.info("OI: OKX fallo, intentando Bybit fallback...")
        return get_open_interest_bybit(symbol)
    d = data[0]
    try:
        oi_contracts = _safe_float(d.get("oi"))
        oi_usd       = _safe_float(d.get("oiUsd"))
        return {
            "contracts": oi_contracts,
            "usd":       oi_usd,
            "millions":  oi_usd / 1_000_000,
            "_source":   "okx",
        }
    except Exception as e:
        log.warning("OI: OKX parse fallo (raw={}, err={}), intentando Bybit fallback...".format(
            d, e))
        return get_open_interest_bybit(symbol)

def _okx_period(period):
    """OKX rubik/stat acepta solo: 5m, 1H, 1D. Traducimos lo demas a lo mas cercano."""
    p = period.lower()
    if p in ("5m", "15m", "30m"):
        return "5m"
    if p in ("1h", "2h", "4h"):
        return "1H"
    return "1D"

def _bybit_period(period):
    """Bybit V5 acepta: 5min, 15min, 30min, 1h, 4h, 1d."""
    p = period.lower()
    mapping = {"5m": "5min", "15m": "15min", "30m": "30min",
               "1h": "1h", "4h": "4h", "1d": "1d"}
    return mapping.get(p, "15min")

def get_oi_history(symbol="SOL-USDT-SWAP", period="15m", limit=10):
    """OI history. Endpoint rubik/stat de OKX es muy bloqueado en VPS -> Bybit fallback.
    OKX solo acepta period en [5m, 1H, 1D] - traducimos internamente."""
    import time
    end_ms   = int(time.time() * 1000)
    begin_ms = end_ms - (3600 * 1000 * 4)  # ultimas 4h
    data = _safe_get(
        "{}/api/v5/rubik/stat/contracts/open-interest-volume".format(OKX_BASE),
        params={"ccy": "SOL", "period": _okx_period(period),
                "begin": str(begin_ms), "end": str(end_ms)}
    )
    if not data:
        log.info("OI history: OKX rubik/stat fallo, intentando Bybit fallback...")
        return get_oi_history_bybit(symbol, _bybit_period(period), limit)
    try:
        return [{"ts": _safe_int(x[0]), "oi": _safe_float(x[1]), "vol": _safe_float(x[2])}
                for x in data[:limit]]
    except Exception as e:
        log.warning("OI history: OKX parse fallo (raw_first={}, err={}), intentando Bybit fallback...".format(
            data[0] if data else None, e))
        return get_oi_history_bybit(symbol, _bybit_period(period), limit)

def oi_trend_analysis(oi_history):
    """Analiza tendencia de OI en ultimos N puntos"""
    if not oi_history or len(oi_history) < 3:
        return {"trend": "N/A", "change_pct": 0}
    recent = oi_history[0]["oi"]
    older  = oi_history[-1]["oi"]
    change_pct = (recent - older) / older * 100 if older > 0 else 0
    if change_pct > 5:    trend = "OI EXPANDIENDO FUERTE - dinero nuevo entrando"
    elif change_pct > 1:  trend = "OI creciendo - posiciones nuevas"
    elif change_pct > -1: trend = "OI estable"
    elif change_pct > -5: trend = "OI contrayendo - cierre de posiciones"
    else:                 trend = "OI COLAPSANDO - desapalancamiento masivo"
    return {"trend": trend, "change_pct": change_pct}

# ============================================================
# LONG/SHORT RATIO
# ============================================================
def get_long_short_ratio(symbol="SOL", period="15m"):
    """L/S ratio. Endpoint rubik/stat de OKX es muy bloqueado en VPS -> Bybit fallback.
    OKX solo acepta period en [5m, 1H, 1D] - traducimos internamente."""
    import time
    end_ms   = int(time.time() * 1000)
    begin_ms = end_ms - (3600 * 1000 * 4)
    data = _safe_get(
        "{}/api/v5/rubik/stat/contracts/long-short-account-ratio".format(OKX_BASE),
        params={"ccy": symbol, "period": _okx_period(period),
                "begin": str(begin_ms), "end": str(end_ms)}
    )
    if not data:
        log.info("L/S ratio: OKX rubik/stat fallo, intentando Bybit fallback...")
        return get_long_short_ratio_bybit(symbol, _bybit_period(period))
    try:
        ratios  = [_safe_float(x[1]) for x in data[:5]]
        ratios  = [r for r in ratios if r > 0]  # filtrar ceros (parse fallido)
        if not ratios:
            raise ValueError("ratios vacios despues de filtrar")
        current = ratios[0]
        avg_5   = sum(ratios) / len(ratios)
        return {"current": current, "avg_5": avg_5, "history": ratios, "_source": "okx"}
    except Exception as e:
        log.warning("L/S ratio: OKX parse fallo (raw_first={}, err={}), intentando Bybit fallback...".format(
            data[0] if data else None, e))
        return get_long_short_ratio_bybit(symbol, _bybit_period(period))

def ls_ratio_interpretation(ratio):
    """Interpretacion del L/S ratio"""
    if ratio > 3.0:    return "EXTREMO LONG (>3.0) - posible techo, contrarios cargan shorts"
    if ratio > 2.0:    return "Alto long ({:.2f}) - mercado optimista"
    if ratio > 1.3:    return "Long-biased ({:.2f}) - sesgo alcista normal"
    if ratio > 0.8:    return "BALANCEADO ({:.2f}) - sin sesgo claro"
    if ratio > 0.5:    return "Short-biased ({:.2f}) - sesgo bajista"
    return "EXTREMO SHORT ({:.2f}) - posible piso, contrarios cargan longs".format(ratio)

# ============================================================
# ORDER BOOK
# ============================================================
def get_order_book(symbol="SOL-USDT-SWAP", depth=20):
    """Order book con profundidad N"""
    data = _safe_get("{}/api/v5/market/books".format(OKX_BASE),
                     params={"instId": symbol, "sz": depth})
    if not data:
        return None
    try:
        ob = data[0]
        bids = [[float(x[0]), float(x[1])] for x in ob.get("bids", [])]
        asks = [[float(x[0]), float(x[1])] for x in ob.get("asks", [])]
        return {"bids": bids, "asks": asks}
    except Exception:
        return None

def detect_liquidity_walls(order_book, current_price, threshold_multiplier=3.0):
    """
    Detecta walls (acumulacion de liquidez) en bid y ask.
    Wall = orden N veces mayor al promedio de su lado.
    """
    if not order_book:
        return {"bid_walls": [], "ask_walls": []}

    bids = order_book["bids"]
    asks = order_book["asks"]
    if not bids or not asks:
        return {"bid_walls": [], "ask_walls": []}

    avg_bid_size = sum(b[1] for b in bids) / len(bids)
    avg_ask_size = sum(a[1] for a in asks) / len(asks)

    bid_walls = []
    for price, size in bids:
        if size > avg_bid_size * threshold_multiplier:
            dist_pct = (current_price - price) / current_price * 100
            bid_walls.append({"price": price, "size": size, "dist_pct": dist_pct})

    ask_walls = []
    for price, size in asks:
        if size > avg_ask_size * threshold_multiplier:
            dist_pct = (price - current_price) / current_price * 100
            ask_walls.append({"price": price, "size": size, "dist_pct": dist_pct})

    return {
        "bid_walls": bid_walls[:3],
        "ask_walls": ask_walls[:3],
        "avg_bid_size": avg_bid_size,
        "avg_ask_size": avg_ask_size,
    }

def order_book_pressure(order_book, current_price, range_pct=0.5):
    """
    Calcula presion de compra vs venta dentro de N% del precio.
    Devuelve ratio de bid_volume / ask_volume.
    > 1.5: compradores dominan
    < 0.66: vendedores dominan
    """
    if not order_book:
        return {"ratio": 1.0, "interpretation": "N/A"}

    bid_threshold = current_price * (1 - range_pct / 100)
    ask_threshold = current_price * (1 + range_pct / 100)

    bid_vol = sum(b[1] for b in order_book["bids"] if b[0] >= bid_threshold)
    ask_vol = sum(a[1] for a in order_book["asks"] if a[0] <= ask_threshold)

    if ask_vol == 0:
        ratio = 999
    else:
        ratio = bid_vol / ask_vol

    if ratio > 2.0:    interp = "COMPRADORES dominan fuerte ({:.2f}x)".format(ratio)
    elif ratio > 1.3:  interp = "Compradores ligeramente dominan ({:.2f}x)".format(ratio)
    elif ratio > 0.77: interp = "BALANCEADO ({:.2f}x)".format(ratio)
    elif ratio > 0.5:  interp = "Vendedores ligeramente dominan ({:.2f}x)".format(ratio)
    else:              interp = "VENDEDORES dominan fuerte ({:.2f}x)".format(ratio)

    return {"ratio": ratio, "interpretation": interp, "bid_vol": bid_vol, "ask_vol": ask_vol}

# ============================================================
# EVENT DETECTOR - el grunt work pre-procesado para Claude
# ============================================================
def detect_choch(df, lookback=20):
    """
    Change of Character - cuando estructura cambia de bullish a bearish o viceversa.
    Detecta higher-high/higher-low (HH/HL) o lower-high/lower-low (LH/LL).
    """
    if len(df) < lookback + 2:
        return None

    highs = df["high"].iloc[-lookback:].values
    lows = df["low"].iloc[-lookback:].values
    closes = df["close"].iloc[-lookback:].values

    # Pivots simples
    pivot_highs = []
    pivot_lows = []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            pivot_highs.append((i, highs[i]))
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            pivot_lows.append((i, lows[i]))

    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return None

    last_high = pivot_highs[-1][1]
    prev_high = pivot_highs[-2][1]
    last_low = pivot_lows[-1][1]
    prev_low = pivot_lows[-2][1]

    current_price = closes[-1]

    # CHoCH bullish: precio rompe ultimo lower-high despues de tendencia bajista
    if prev_high > last_high and current_price > prev_high:
        return {"type": "CHoCH BULLISH", "level": prev_high, "strength": (current_price - prev_high) / prev_high * 100}

    # CHoCH bearish: precio rompe ultimo higher-low despues de tendencia alcista
    if prev_low < last_low and current_price < prev_low:
        return {"type": "CHoCH BEARISH", "level": prev_low, "strength": (prev_low - current_price) / prev_low * 100}

    return None

def detect_breakout(df, period=20):
    """Detecta breakout reciente de range high/low"""
    if len(df) < period + 5:
        return None

    last_close = df["close"].iloc[-1]
    last_volume = df["volume"].iloc[-1]
    vol_ma = df["volume"].iloc[-20:].mean()

    # Range previo (excluyendo ultimas 3 velas)
    range_high = df["high"].iloc[-period-3:-3].max()
    range_low = df["low"].iloc[-period-3:-3].min()

    # Cuerpo de la vela actual
    body = abs(df["close"].iloc[-1] - df["open"].iloc[-1])
    rng = df["high"].iloc[-1] - df["low"].iloc[-1]
    body_pct = body / rng if rng > 0 else 0

    if last_close > range_high and last_volume > vol_ma * 1.3 and body_pct > 0.5:
        return {"type": "BREAKOUT BULLISH", "level": range_high,
                "vol_x": last_volume / vol_ma, "body_pct": body_pct * 100}
    if last_close < range_low and last_volume > vol_ma * 1.3 and body_pct > 0.5:
        return {"type": "BREAKOUT BEARISH", "level": range_low,
                "vol_x": last_volume / vol_ma, "body_pct": body_pct * 100}
    return None

def detect_rsi_divergence(df, lookback=15):
    """
    Detecta divergencia RSI-precio.
    Bullish: precio hace LL pero RSI hace HL (oversold extremo perdiendo fuerza)
    Bearish: precio hace HH pero RSI hace LH (overbought extremo perdiendo fuerza)
    """
    if len(df) < lookback + 5 or "rsi14" not in df.columns:
        return None

    closes = df["close"].iloc[-lookback:].values
    rsis = df["rsi14"].iloc[-lookback:].values

    # Encontrar dos minimos/maximos significativos
    if len(closes) < 10:
        return None

    # Ultimo minimo de precio en primer y segundo half
    half = len(closes) // 2
    min1_idx = closes[:half].argmin()
    min2_idx = half + closes[half:].argmin()
    max1_idx = closes[:half].argmax()
    max2_idx = half + closes[half:].argmax()

    # Bullish divergence
    if (closes[min2_idx] < closes[min1_idx] and rsis[min2_idx] > rsis[min1_idx]
        and rsis[min1_idx] < 35):
        return {"type": "DIVERGENCIA BULLISH",
                "rsi_change": rsis[min2_idx] - rsis[min1_idx],
                "price_change_pct": (closes[min2_idx] - closes[min1_idx]) / closes[min1_idx] * 100}

    # Bearish divergence
    if (closes[max2_idx] > closes[max1_idx] and rsis[max2_idx] < rsis[max1_idx]
        and rsis[max1_idx] > 65):
        return {"type": "DIVERGENCIA BEARISH",
                "rsi_change": rsis[max1_idx] - rsis[max2_idx],
                "price_change_pct": (closes[max2_idx] - closes[max1_idx]) / closes[max1_idx] * 100}

    return None

def detect_volume_anomaly(df):
    """Volumen anomalo en vela actual o reciente"""
    if len(df) < 20:
        return None

    vol_ma = df["volume"].iloc[-20:-1].mean()
    last_vol = df["volume"].iloc[-1]

    if last_vol > vol_ma * 2.5:
        body = df["close"].iloc[-1] - df["open"].iloc[-1]
        direction = "BULLISH" if body > 0 else "BEARISH"
        return {"type": "VOLUMEN ANOMALO {}".format(direction),
                "vol_x": last_vol / vol_ma}
    return None

def detect_candle_pattern(df):
    """Patrones de vela japonesa simples pero relevantes"""
    if len(df) < 3:
        return None

    o, h, l, c = (df["open"].iloc[-1], df["high"].iloc[-1],
                  df["low"].iloc[-1], df["close"].iloc[-1])
    body = abs(c - o)
    rng = h - l
    if rng == 0:
        return None

    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    body_pct = body / rng

    # Hammer (martillo bullish)
    if lower_wick > body * 2 and upper_wick < body * 0.3 and body_pct < 0.4:
        return {"type": "HAMMER (martillo bullish)", "context": "rechazo en zona de soporte"}

    # Shooting star (estrella fugaz bearish)
    if upper_wick > body * 2 and lower_wick < body * 0.3 and body_pct < 0.4:
        return {"type": "SHOOTING STAR (estrella fugaz bearish)", "context": "rechazo en zona de resistencia"}

    # Engulfing
    if len(df) >= 2:
        prev_o, prev_c = df["open"].iloc[-2], df["close"].iloc[-2]
        prev_body = abs(prev_c - prev_o)
        if body > prev_body * 1.2:
            if c > o and prev_c < prev_o and c > prev_o and o < prev_c:
                return {"type": "BULLISH ENGULFING", "context": "absorcion de vendedores"}
            if c < o and prev_c > prev_o and c < prev_o and o > prev_c:
                return {"type": "BEARISH ENGULFING", "context": "absorcion de compradores"}

    return None

def detect_all_events(df):
    """Corre todos los detectores y devuelve lista de eventos activos"""
    events = []
    for detector in [detect_choch, detect_breakout, detect_rsi_divergence,
                     detect_volume_anomaly, detect_candle_pattern]:
        try:
            result = detector(df)
            if result:
                events.append(result)
        except Exception as e:
            log.warning("Event detector {} error: {}".format(detector.__name__, e))
    return events

# ============================================================
# CANDLE EVOLUTION (ultimas N velas con deltas)
# ============================================================
def candle_evolution(df, n=5):
    """
    Devuelve las ultimas N velas con sus deltas para que Claude vea evolucion.
    Formato compacto, listo para prompt.
    """
    if len(df) < n:
        return []

    evolution = []
    for i in range(-n, 0):
        row = df.iloc[i]
        prev = df.iloc[i-1] if i > -len(df) else None

        body = row["close"] - row["open"]
        rng = row["high"] - row["low"]
        body_pct = (abs(body) / rng * 100) if rng > 0 else 0

        candle = {
            "idx":      i,
            "ts":       row["timestamp"].strftime("%H:%M") if hasattr(row["timestamp"], "strftime") else str(row["timestamp"]),
            "o":        round(float(row["open"]), 2),
            "h":        round(float(row["high"]), 2),
            "l":        round(float(row["low"]), 2),
            "c":        round(float(row["close"]), 2),
            "vol":      round(float(row["volume"]), 0),
            "color":    "verde" if body > 0 else "roja",
            "body_pct": round(body_pct, 0),
            "rsi":      round(float(row.get("rsi14", 0)), 1),
        }
        if prev is not None:
            candle["delta_close_pct"] = round((row["close"] - prev["close"]) / prev["close"] * 100, 2)
            candle["delta_vol_x"]     = round(row["volume"] / prev["volume"], 2) if prev["volume"] > 0 else 0
        evolution.append(candle)
    return evolution

# ============================================================
# SMART SNAPSHOT BUILDERS - especializados por comando
# ============================================================
def snapshot_for_general(df, basic_state):
    """Snapshot para /claude general - lectura tactica completa"""
    snap = dict(basic_state)
    snap["events"]            = detect_all_events(df)
    snap["candle_evolution"]  = candle_evolution(df, n=5)

    # Datos externos compactos. Siempre poblamos las keys, aunque OKX falle,
    # para que Claude distinga "no me pasaron el dato" vs "OKX cayo".
    funding = get_funding_rate()
    if funding:
        snap["funding_pct"]    = funding["current_pct"]
        snap["funding_interp"] = funding_interpretation(funding["current_pct"])
    else:
        snap["funding_pct"]    = "UNAVAILABLE"
        snap["funding_interp"] = "OKX no respondio (posible geo-block del servidor o rate-limit)"

    oi = get_open_interest()
    if oi:
        snap["oi_millions"] = oi["millions"]
    else:
        snap["oi_millions"] = "UNAVAILABLE"

    oi_hist = get_oi_history()
    if oi_hist:
        oi_trend = oi_trend_analysis(oi_hist)
        snap["oi_trend"]      = oi_trend["trend"]
        snap["oi_change_pct"] = oi_trend["change_pct"]
    else:
        snap["oi_trend"]      = "UNAVAILABLE"
        snap["oi_change_pct"] = "UNAVAILABLE"

    ls = get_long_short_ratio()
    if ls:
        snap["ls_ratio"]  = ls["current"]
        snap["ls_interp"] = ls_ratio_interpretation(ls["current"])
    else:
        snap["ls_ratio"]  = "UNAVAILABLE"
        snap["ls_interp"] = "OKX rubik/stat no respondio"

    return snap

def snapshot_for_pspace(df, basic_state, pspace_data):
    """Snapshot para /pspace - foco en libro y walls"""
    snap = dict(basic_state)
    snap["pspace_full"] = pspace_data

    ob = get_order_book()
    if ob:
        walls = detect_liquidity_walls(ob, basic_state["price"])
        snap["bid_walls"] = walls["bid_walls"]
        snap["ask_walls"] = walls["ask_walls"]
        pressure = order_book_pressure(ob, basic_state["price"], range_pct=0.5)
        snap["ob_pressure_ratio"]  = pressure["ratio"]
        snap["ob_pressure_interp"] = pressure["interpretation"]

    snap["events"] = detect_all_events(df)
    return snap

def snapshot_for_niveles(df, basic_state, plan_primary, plan_secondary):
    """Snapshot para /niveles - foco en setup y triggers"""
    snap = dict(basic_state)
    snap["plan_primary"]   = plan_primary
    snap["plan_secondary"] = plan_secondary
    snap["events"]         = detect_all_events(df)
    snap["candle_evolution"] = candle_evolution(df, n=3)

    funding = get_funding_rate()
    if funding:
        snap["funding_pct"]    = funding["current_pct"]
        snap["funding_interp"] = funding_interpretation(funding["current_pct"])

    ob = get_order_book()
    if ob:
        walls = detect_liquidity_walls(ob, basic_state["price"])
        snap["bid_walls"] = walls["bid_walls"]
        snap["ask_walls"] = walls["ask_walls"]
    return snap

def snapshot_for_signal(df, signal_data, decoh):
    """Snapshot para senal auto-disparada (Opus) - el mas completo"""
    snap = dict(signal_data)
    snap["decoherence"]      = decoh
    snap["events"]           = detect_all_events(df)
    snap["candle_evolution"] = candle_evolution(df, n=5)

    funding = get_funding_rate()
    if funding:
        snap["funding_pct"]    = funding["current_pct"]
        snap["funding_interp"] = funding_interpretation(funding["current_pct"])
        snap["next_funding"]   = funding["next_time_str"]

    oi = get_open_interest()
    if oi:
        snap["oi_millions"] = oi["millions"]
    oi_hist = get_oi_history()
    if oi_hist:
        oi_trend = oi_trend_analysis(oi_hist)
        snap["oi_trend"]      = oi_trend["trend"]
        snap["oi_change_pct"] = oi_trend["change_pct"]

    ls = get_long_short_ratio()
    if ls:
        snap["ls_ratio"]  = ls["current"]
        snap["ls_interp"] = ls_ratio_interpretation(ls["current"])

    ob = get_order_book()
    if ob:
        walls = detect_liquidity_walls(ob, signal_data.get("entry", signal_data.get("price", 0)))
        snap["bid_walls"] = walls["bid_walls"]
        snap["ask_walls"] = walls["ask_walls"]
        pressure = order_book_pressure(ob, signal_data.get("entry", signal_data.get("price", 0)))
        snap["ob_pressure_interp"] = pressure["interpretation"]

    return snap
