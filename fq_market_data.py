# -*- coding: utf-8 -*-
"""
================================================================================
  FQ MARKET DATA - acceso a velas (OHLCV) + indicadores tecnicos
  by RasDG_Sol + Claude

  Etapa 2 de la migracion del monolito (ver ARCHITECTURE.md). Aisla el I/O del
  exchange y el calculo de indicadores (pandas-ta) detras de una frontera
  pequena:

    - fetch_ohlcv(exchange, symbol, timeframe, limit) -> DataFrame OHLCV.
    - add_indicators(df)                              -> DataFrame + indicadores.

  El exchange se recibe por parametro (ccxt o cualquier objeto con
  .fetch_ohlcv), de modo que estas funciones se pueden mockear facilmente en
  tests sin tocar red. No dependen de globals del monolito.
================================================================================
"""
import pandas as pd
import pandas_ta as ta

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def fetch_ohlcv(exchange, symbol, timeframe, limit=200):
    """Descarga velas OHLCV del exchange y las devuelve como DataFrame con el
    timestamp ya convertido a datetime."""
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=OHLCV_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def add_indicators(df):
    """Anade los indicadores tecnicos que consume el motor (RSI multi-periodo,
    EMAs, SMAs, Bollinger, MACD, ATR y media de volumen). No muta el df de
    entrada (trabaja sobre una copia)."""
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
