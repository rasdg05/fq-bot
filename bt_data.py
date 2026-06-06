# -*- coding: utf-8 -*-
"""
================================================================================
  BT DATA - construccion de datasets historicos OHLCV (multi-exchange)
  by RasDG_Sol + Claude

  Etapa 1 del harness de research (backtest / walk-forward / entrenamiento).
  Ver ARCHITECTURE.md: piezas puras y testeables, sin red en los tests.

  El objetivo: descargar histgrico OHLCV completo de un simbolo (SOL/USDT y
  derivados) desde uno o varios exchanges, deduplicar, verificar continuidad
  (gaps) y persistir a Parquet. Ese dataset alimenta:
    - el motor de backtest/replay,
    - el etiquetado (triple-barrier) para el GBM,
    - la curva de equity y las metricas de riesgo.

  Diseno mockeable: el exchange entra por parametro (cualquier objeto con
  .fetch_ohlcv(symbol, timeframe, since, limit), estilo ccxt). Los tests usan
  un exchange falso y NO tocan red. make_exchange() crea instancias ccxt reales
  con import perezoso, de modo que el modulo se importa sin ccxt instalado.
================================================================================
"""
import logging
import os
import time

import pandas as pd

log = logging.getLogger("bt_data")

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

# Milisegundos por barra para cada timeframe soportado.
TIMEFRAME_MS = {
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "2h": 2 * 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


def timeframe_ms(timeframe):
    """Milisegundos que dura una barra del timeframe. Lanza si no se soporta."""
    try:
        return TIMEFRAME_MS[timeframe]
    except KeyError:
        raise ValueError(f"timeframe no soportado: {timeframe!r}")


# ============================================================
# DESCARGA PAGINADA (walk-forward sobre el tiempo)
# ============================================================
def fetch_ohlcv_range(
    exchange,
    symbol,
    timeframe,
    since_ms,
    until_ms,
    page_limit=1000,
    max_pages=100_000,
    sleep_s=0.0,
):
    """Descarga OHLCV de [since_ms, until_ms) paginando con el parametro `since`.

    Avanza el cursor al timestamp de la ultima vela + un intervalo, hasta cubrir
    el rango o dejar de progresar. Deduplica por timestamp y ordena ascendente.
    Devuelve un DataFrame con OHLCV_COLUMNS (timestamp en datetime64[ns], UTC
    naive, igual que fq_market_data.fetch_ohlcv).

    `sleep_s` introduce una pausa entre paginas (cortesia de rate-limit en uso
    real; 0 en tests).
    """
    if until_ms <= since_ms:
        return _empty_frame()

    tf_ms = timeframe_ms(timeframe)
    cursor = since_ms
    rows = []
    pages = 0

    while cursor < until_ms and pages < max_pages:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe,
                                     since=cursor, limit=page_limit)
        pages += 1
        if not batch:
            break

        # Filtra a la ventana pedida y acumula.
        for candle in batch:
            ts = candle[0]
            if ts >= until_ms:
                break
            if ts >= since_ms:
                rows.append(candle)

        last_ts = batch[-1][0]
        # Sin progreso => evita loop infinito (exchange devuelve la misma pagina).
        if last_ts < cursor:
            break
        next_cursor = last_ts + tf_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor

        if sleep_s:
            time.sleep(sleep_s)

    if not rows:
        return _empty_frame()

    df = pd.DataFrame(rows, columns=OHLCV_COLUMNS)
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp")
    df = df.reset_index(drop=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def _empty_frame():
    df = pd.DataFrame(columns=OHLCV_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


# ============================================================
# VERIFICACION DE INTEGRIDAD (gaps / duplicados)
# ============================================================
def check_continuity(df, timeframe):
    """Audita la continuidad temporal de un DataFrame OHLCV ya ordenado.

    Devuelve un dict con:
      - n: numero de filas
      - duplicates: timestamps duplicados
      - gaps: lista de (ts_antes, ts_despues, barras_faltantes) donde el salto
              entre velas consecutivas excede un intervalo del timeframe
      - missing_bars: total de barras faltantes (suma de gaps)
      - expected: barras esperadas si la serie fuese perfecta
      - completeness: n / expected (1.0 = sin huecos)

    Un dataset apto para backtest/entrenamiento deberia tener completeness alta
    y, si hay gaps, que esten documentados (paradas del exchange, etc.).
    """
    n = len(df)
    if n == 0:
        return {"n": 0, "duplicates": 0, "gaps": [], "missing_bars": 0,
                "expected": 0, "completeness": 1.0}

    # Resolucion-independiente: trabajamos con Timedelta, no con int64 (la
    # resolucion de datetime64 cambia entre versiones de pandas).
    tf_td = pd.Timedelta(milliseconds=timeframe_ms(timeframe))
    ts = df["timestamp"]
    duplicates = int(ts.duplicated().sum())

    deltas = ts.diff().dropna()
    gaps = []
    missing = 0
    ts_values = ts.tolist()
    for i, delta in enumerate(deltas, start=1):
        if delta > tf_td:
            missing_here = int(delta / tf_td) - 1
            if missing_here > 0:
                gaps.append((ts_values[i - 1], ts_values[i], missing_here))
                missing += missing_here

    span = ts_values[-1] - ts_values[0]
    expected = int(span / tf_td) + 1
    completeness = (n / expected) if expected > 0 else 1.0
    return {
        "n": n,
        "duplicates": duplicates,
        "gaps": gaps,
        "missing_bars": missing,
        "expected": expected,
        "completeness": completeness,
    }


# ============================================================
# PERSISTENCIA (Parquet; pyarrow import perezoso)
# ============================================================
def to_parquet(df, path):
    """Persiste el DataFrame a Parquet (crea el directorio si hace falta)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def load_parquet(path):
    """Carga un dataset OHLCV desde Parquet."""
    return pd.read_parquet(path)


def dataset_path(data_dir, exchange_name, symbol, timeframe):
    """Ruta canonica del dataset: <data_dir>/<exchange>/<symbol>_<tf>.parquet.

    El simbolo se sanea (SOL/USDT -> SOL-USDT) para que sea valido en disco.
    """
    safe_symbol = symbol.replace("/", "-").replace(":", "_")
    return os.path.join(data_dir, exchange_name, f"{safe_symbol}_{timeframe}.parquet")


# ============================================================
# ORQUESTACION
# ============================================================
def build_dataset(
    exchange,
    symbol,
    timeframe,
    since_ms,
    until_ms,
    out_path=None,
    exchange_name=None,
    data_dir="data",
    page_limit=1000,
    sleep_s=0.0,
):
    """Descarga el rango, audita continuidad y (si out_path o exchange_name)
    persiste a Parquet. Devuelve (df, report) donde report incluye la auditoria
    de continuidad y la ruta de salida si se persistio.
    """
    df = fetch_ohlcv_range(
        exchange, symbol, timeframe, since_ms, until_ms,
        page_limit=page_limit, sleep_s=sleep_s,
    )
    report = check_continuity(df, timeframe)

    saved_to = None
    if out_path is None and exchange_name is not None:
        out_path = dataset_path(data_dir, exchange_name, symbol, timeframe)
    if out_path is not None and report["n"] > 0:
        saved_to = to_parquet(df, out_path)
    report["saved_to"] = saved_to

    log.info(
        "build_dataset %s %s %s: n=%d completeness=%.4f gaps=%d -> %s",
        exchange_name or "?", symbol, timeframe,
        report["n"], report["completeness"], len(report["gaps"]), saved_to,
    )
    return df, report


# ============================================================
# FABRICA DE EXCHANGES (ccxt; import perezoso)
# ============================================================
def make_exchange(name, market_type="spot"):
    """Crea un exchange ccxt con rate-limit activado. Import perezoso para que
    el modulo se importe (y se testee) sin ccxt instalado.

    name: "binance" | "bybit" | cualquier id valido de ccxt.
    market_type: "spot" | "swap" (perpetuo) | "future".
    """
    import ccxt  # perezoso a proposito

    klass = getattr(ccxt, name)
    options = {"enableRateLimit": True}
    if market_type in ("swap", "future"):
        options["options"] = {"defaultType": market_type}
    return klass(options)
