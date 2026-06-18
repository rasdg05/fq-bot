# -*- coding: utf-8 -*-
"""
================================================================================
  FUNDING_OI - features ESTRUCTURALES de funding-rate (+ open interest)
  by RasDG_Sol + Claude

  El pivote del veredicto deflactado (run #65): el deflactado MATO la prediccion
  direccional (mejor forward DSR=0.41, PBO=0.55 = suerte). En vez de PREDECIR
  direccion, COSECHAMOS un premio ESTRUCTURAL:
    - los EXTREMOS de funding revierten a la media (financiar un lado caro es
      insostenible -> presion de reversion). fund_zscore mide ese extremo.
    - el OPEN INTEREST confirma o desenmascara un movimiento: OI sube con el
      precio = conviccion (continuacion); OI cae contra el precio = squeeze /
      cierre de posiciones (reversion). oi_price_div codifica ese signo.
  No adivinamos hacia donde va el precio; medimos la TENSION del libro de
  perpetuos y dejamos que el harness (modelo [3/4] + retrieval/gate ORO) decida
  si esa tension paga edge OOS/forward.

  Pieza testeable, mismo contrato que bt_features.cross_asset_features:
    - fetch_*  : red (ccxt OKX), import perezoso, cacheado a Parquet. En tests se
                 mockea el exchange -> NUNCA toca red.
    - funding_oi_features / attach_funding_oi_features : DataFrames in -> in, PURO,
                 CAUSAL por construccion (merge_asof backward + shift + ventanas
                 trailing). Sin red, sin estado.

  LEAKAGE (lo que se revisa): una feature en la vela primaria t SOLO puede leer
  funding/OI con timestamp <= t. El funding LIQUIDA al FINAL de cada ventana ~8h;
  usamos el ULTIMO funding YA LIQUIDADO (shift=1 -> una ventana en formacion no se
  usa). Ver el docstring de funding_oi_features para el argumento completo.
================================================================================
"""
import logging
import os

import numpy as np
import pandas as pd

log = logging.getLogger("funding_oi")

# Profundidad de funding/OI que OKX expone via ccxt (documentado a partir de la
# fuente de ccxt 4.5.x; validar en Hetzner con red real):
#   funding (publicGetPublicFundingRateHistory): granularidad ~8h, paginado por
#       'before'/'after' hacia atras; historia tipica ~3 meses (NO años).
#   OI history (publicGetRubikStatContractsOpenInterestVolume): Rubik trading-data,
#       periodos 5m/1H/1D, ventana RECIENTE rodante (semanas, NO años) -> SHALLOW.
# Por eso el caller degrada a FUNDING-ONLY si el OI no cubre la ventana primaria.
FUNDING_TIMEFRAME = "8h"           # OKX liquida funding cada ~8h
DEFAULT_FUNDING_LOOKBACK_DAYS = 365 * 3
DEFAULT_OI_PERIOD = "1H"           # 5m | 1H | 1D (unico set que admite el Rubik)

# CANDIDATOS de exchange para el funding MAS PROFUNDO alcanzable (Part C). OKX
# expone solo ~3 meses de funding via ccxt; antes de decidir si el backtest de
# reversion es viable hay que medir CUAL exchange da mas MESES. Orden por
# profundidad esperada (de la fuente de ccxt 4.5.x; validar en Hetzner con red):
#   bybit         (publicGetV5MarketFundingHistory): ~2 años, paginado backward.
#   gate          (publicFuturesGetSettleFundingRate): historia LARGA (>1 año).
#   binanceusdm   (fapiPublicGetFundingRate, settled cada 8h): historia LARGA pero
#                 451 (geo-block) en muchos runners cloud -> se captura + salta.
#   kucoinfutures (futuresPublicGetContractFundingRates): meses.
#   hyperliquid   (funding HORARIO, settled cada 1h): historia variable; granular.
#   okx           (publicGetPublicFundingRateHistory): ~3 meses (shallow, el actual).
# Cada id debe existir en ccxt y soportar fetchFundingRateHistory; los que no,
# se saltan con aviso (nunca crashea: la idea es PROBARLOS TODOS y reportar).
FUNDING_EXCHANGE_CANDIDATES = (
    "okx", "bybit", "gate", "kucoinfutures", "hyperliquid", "binanceusdm",
)
# Simbolo de perp por exchange para un base dado (BTC/SOL/ETH). El sufijo de
# settlement difiere por venue; ccxt normaliza casi todo a 'BASE/USDT:USDT', pero
# algunos perps son USDC o tienen un quote distinto. Se intenta el candidato y, si
# el exchange no lo reconoce, el probe degrada (no asume un unico formato).
FUNDING_PERP_QUOTE = {
    "okx": "USDT", "bybit": "USDT", "gate": "USDT",
    "kucoinfutures": "USDT", "hyperliquid": "USDC", "binanceusdm": "USDT",
}

# Prefijos de TODAS las features. El loader las inyecta en eventos/estados y, por
# estar en bt_features._numeric_feature_columns (modelo) y en
# bt_retrieval.DEFAULT_NUMERIC (vector), las consumen el GBM del [3/4] Y el vector
# k-NN del retrieval + gate ORO. Single source of truth: FUNDING_OI_FEATURE_COLUMNS.
FUND_PREFIX = "fund_"
OI_PREFIX = "oi_"

# Columnas de FUNDING (siempre disponibles si hay df_funding).
FUNDING_FEATURE_COLUMNS = (
    "fund_rate", "fund_zscore", "fund_cum", "fund_sign_streak",
)
# Columnas de OI (solo si df_oi presente; si no, quedan ausentes -> el vector las
# imputa a 0, igual que cualquier feature ausente).
OI_FEATURE_COLUMNS = (
    "oi_chg", "oi_price_div", "oi_zscore",
)
# Conjunto completo que el modelo y el vector deben reconocer (prefijos fund_/oi_).
FUNDING_OI_FEATURE_COLUMNS = FUNDING_FEATURE_COLUMNS + OI_FEATURE_COLUMNS


# ============================================================
# RUTAS DE CACHE (estilo bt_data.dataset_path)
# ============================================================
def funding_path(data_dir, exchange_name, symbol):
    """Ruta canonica del cache de funding: <data_dir>/<exchange>/<SYM>_funding.parquet.

    El simbolo se sanea (BTC/USDT:USDT -> BTC-USDT_USDT) igual que bt_data.
    """
    safe_symbol = symbol.replace("/", "-").replace(":", "_")
    return os.path.join(data_dir, exchange_name, f"{safe_symbol}_funding.parquet")


def open_interest_path(data_dir, exchange_name, symbol):
    """Ruta canonica del cache de OI: <data_dir>/<exchange>/<SYM>_oi.parquet."""
    safe_symbol = symbol.replace("/", "-").replace(":", "_")
    return os.path.join(data_dir, exchange_name, f"{safe_symbol}_oi.parquet")


def _to_parquet(df, path):
    """Persiste a Parquet (crea el directorio). Identico a bt_data.to_parquet."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    df.to_parquet(path, index=False)
    return path


# ============================================================
# FETCH FUNDING (red; ccxt OKX). Mockeable: exchange entra por parametro.
# ============================================================
def fetch_funding_history(
    exchange, symbol, data_dir="data", *,
    exchange_name=None, lookback_days=DEFAULT_FUNDING_LOOKBACK_DAYS,
    page_limit=100, max_pages=100_000, sleep_s=0.0, now_ms=None,
    use_cache=True,
):
    """Descarga el historico de funding de `symbol` paginando hacia ADELANTE (por
    `since`) tan lejos como el exchange lo exponga, y lo cachea a Parquet. Si el
    cache existe, lo CARGA.

    exchange : objeto estilo ccxt con .fetch_funding_rate_history(symbol, since,
               limit, params). En tests se mockea -> sin red.
    Devuelve un DataFrame con columnas:
       timestamp(datetime64[ns], UTC naive)  ·  funding_rate(float)
    point-in-time: funding_rate es la tasa PUBLICADA/liquidada (OKX la expone como
    realizedRate via ccxt), sin revisiones ni futuro.

    Paginacion FORWARD (idiom unificado de ccxt): arrancamos en
    `since = now - lookback_days` y avanzamos el cursor al timestamp MAS NUEVO de
    cada pagina (since = newest+1), pidiendo lo POSTERIOR, hasta que (a) alcanzamos
    el presente, (b) la pagina no progresa (ya vista, o el exchange IGNORA `since` y
    repite la ventana reciente), o (c) viene vacia. bybit/gate/binance/kucoin
    exponen AÑOS por `since`; el viejo `before` hacia atras solo lo respetaba OKX
    (shallow) y dejaba al resto capado en 100 filas. Nunca crashea por pagina vacia.
    """
    ex_name = exchange_name or getattr(exchange, "id", None) or "okx"
    path = funding_path(data_dir, ex_name, symbol)
    if use_cache and os.path.exists(path):
        log.info("fetch_funding_history: cache HIT %s", path)
        return pd.read_parquet(path)

    now_ms = int(now_ms if now_ms is not None else _now_ms())
    floor_ms = now_ms - int(lookback_days) * 86_400_000
    rows = []
    seen = set()
    cursor = floor_ms      # `since`: pedimos lo POSTERIOR a `cursor`, hacia adelante
    pages = 0
    while pages < max_pages:
        batch = exchange.fetch_funding_rate_history(
            symbol, since=int(cursor), limit=page_limit)
        pages += 1
        if not batch:
            break
        progressed = False
        newest = cursor
        for item in batch:
            ts = item.get("timestamp")
            if ts is None:
                continue
            ts = int(ts)
            if ts > newest:
                newest = ts
            if ts in seen:
                continue
            seen.add(ts)
            rate = item.get("fundingRate")
            rows.append((ts, _to_float(rate)))
            progressed = True
        # parada: alcanzamos el presente; o la pagina no avanzo (ya vista, o el
        # exchange IGNORA `since` y repite la ventana reciente -> corte limpio, sin
        # loop); o vino vacia (fin del historico). Nunca crashea.
        if newest >= now_ms:
            break
        if not progressed or newest <= cursor:
            break
        cursor = newest + 1    # siguiente pagina: lo posterior al mas nuevo visto
        if sleep_s:
            _sleep(sleep_s)

    df = _funding_frame(rows, floor_ms)
    if len(df):
        _to_parquet(df, path)
        log.info("fetch_funding_history: %s %s n=%d [%s .. %s] -> %s",
                 ex_name, symbol, len(df), df["timestamp"].iloc[0],
                 df["timestamp"].iloc[-1], path)
    else:
        log.warning("fetch_funding_history: %s %s SIN datos (historico vacio)",
                    ex_name, symbol)
    return df


def _funding_frame(rows, floor_ms):
    cols = ["timestamp", "funding_rate"]
    if not rows:
        out = pd.DataFrame(columns=cols)
        out["timestamp"] = pd.to_datetime(out["timestamp"])
        out["funding_rate"] = out["funding_rate"].astype(float)
        return out
    df = pd.DataFrame(rows, columns=["ts_ms", "funding_rate"])
    df = df[df["ts_ms"] >= floor_ms]
    df = df.drop_duplicates(subset="ts_ms").sort_values("ts_ms").reset_index(drop=True)
    out = pd.DataFrame({
        "timestamp": pd.to_datetime(df["ts_ms"], unit="ms"),
        "funding_rate": pd.to_numeric(df["funding_rate"], errors="coerce"),
    })
    return out


# ============================================================
# PART C — FUNDING MULTI-EXCHANGE: el MAS PROFUNDO alcanzable.
# Mockeable: las fabricas de exchange entran por parametro (en tests, sin red).
# ============================================================
def perp_symbol_for(exchange_id, base, *, quote=None):
    """Simbolo de perp ccxt canonico para `base` (BTC/SOL/ETH) en `exchange_id`.

    ccxt unifica casi todo a 'BASE/QUOTE:QUOTE' (perp lineal liquidado en QUOTE).
    El quote por defecto sale de FUNDING_PERP_QUOTE (USDT salvo hyperliquid=USDC).
    Devuelve p.ej. 'BTC/USDT:USDT'. No toca red; el caller valida contra
    exchange.markets si quiere.
    """
    q = (quote or FUNDING_PERP_QUOTE.get(exchange_id, "USDT")).upper()
    return f"{base.upper()}/{q}:{q}"


def probe_funding_depth(
    base, *, exchange_ids=FUNDING_EXCHANGE_CANDIDATES, make_exchange=None,
    data_dir="data", lookback_days=DEFAULT_FUNDING_LOOKBACK_DAYS,
    page_limit=100, max_pages=100_000, now_ms=None, use_cache=True, sleep_s=0.0,
):
    """Prueba una LISTA de exchanges y mide la PROFUNDIDAD de funding alcanzable
    para el perp de `base` (BTC/SOL/ETH). Para cada exchange registra
    [start, end] + n_rows + meses + el simbolo usado, o el motivo de fallo
    (sin red / 451 geo-block / sin soporte / vacio). NUNCA crashea: cada exchange
    se prueba en su propio try -> los que fallan se reportan, no abortan el resto.

    make_exchange : callable(exchange_id) -> objeto ccxt-like con
                    .fetch_funding_rate_history y opcionalmente .markets / .has.
                    En tests se inyecta un fake (sin red). Si None, usa
                    bt_data.make_exchange(id, 'swap') (red real, p.ej. en Hetzner).
    Devuelve una lista de dicts (uno por exchange), ORDENADA por meses descendente
    (los reachable primero), cada uno:
      {exchange, symbol, ok, n_rows, start, end, months, source, error}
    'source' = ruta del Parquet cacheado (si se bajaron filas), si no None.
    Es la TABLA que decide si el backtest de funding es viable (meses suficientes)
    o si se va forward-only. El caller la imprime con format_depth_table.
    """
    if make_exchange is None:
        def make_exchange(_id):
            import bt_data
            return bt_data.make_exchange(_id, "swap")

    out = []
    for ex_id in exchange_ids:
        rec = {"exchange": ex_id, "symbol": None, "ok": False, "n_rows": 0,
               "start": None, "end": None, "months": 0.0, "source": None,
               "error": None}
        try:
            ex = make_exchange(ex_id)
        except Exception as e:           # ccxt sin el id, o fabrica falla
            rec["error"] = f"make_exchange: {type(e).__name__}: {str(e)[:120]}"
            out.append(rec)
            continue

        symbol = perp_symbol_for(ex_id, base)
        rec["symbol"] = symbol
        try:
            df = fetch_funding_history(
                ex, symbol, data_dir=data_dir, exchange_name=ex_id,
                lookback_days=lookback_days, page_limit=page_limit,
                max_pages=max_pages, now_ms=now_ms, use_cache=use_cache,
                sleep_s=sleep_s)
        except Exception as e:
            # 451 (geo-block, binance en runners cloud), NetworkError (env sin
            # red), BadSymbol, etc. -> se reporta y se sigue con el siguiente.
            rec["error"] = f"{type(e).__name__}: {str(e)[:160]}"
            out.append(rec)
            continue

        if df is None or len(df) == 0:
            rec["error"] = "historico vacio"
            out.append(rec)
            continue

        rng = _range_of(df)
        rec.update({
            "ok": True, "n_rows": int(len(df)),
            "start": rng[0], "end": rng[1],
            "months": _months_between(rng[0], rng[1]),
            "source": funding_path(data_dir, ex_id, symbol),
        })
        out.append(rec)

    # reachable (ok) primero, por meses desc; luego los fallidos (meses 0).
    out.sort(key=lambda r: (r["ok"], r["months"]), reverse=True)
    return out


def fetch_funding_history_best(
    base, *, exchange_ids=FUNDING_EXCHANGE_CANDIDATES, make_exchange=None,
    data_dir="data", **probe_kwargs):
    """Prueba la lista de exchanges y devuelve el funding del MAS PROFUNDO.

    Atajo sobre probe_funding_depth para el caller que solo quiere los datos: corre
    el probe, elige el exchange con MAS meses de funding reachable, y devuelve
    (df_funding, best_record, depth_table). df_funding sale del cache que el probe
    ya escribio (cero red extra). Si NINGUN exchange fue reachable -> (None, None,
    depth_table) y el caller decide forward-only / Hetzner. Mockeable: misma
    inyeccion make_exchange que el probe (tests sin red).
    """
    table = probe_funding_depth(
        base, exchange_ids=exchange_ids, make_exchange=make_exchange,
        data_dir=data_dir, **probe_kwargs)
    reachable = [r for r in table if r["ok"]]
    if not reachable:
        return None, None, table
    best = reachable[0]               # tabla ya ordenada por meses desc
    df = pd.read_parquet(best["source"]) if best["source"] else None
    return df, best, table


def _months_between(start, end):
    """Meses (~30.44 dias) entre dos timestamps. 0.0 si no computable."""
    try:
        days = (pd.Timestamp(end) - pd.Timestamp(start)).total_seconds() / 86_400.0
        return round(max(days, 0.0) / 30.4375, 2)
    except Exception:
        return 0.0


def format_depth_table(table):
    """Formatea la tabla de probe_funding_depth como texto legible (un fondo la
    mira para decidir backtest-viable vs forward-only). Devuelve un str con una
    fila por exchange: meses / n / rango / simbolo / estado."""
    lines = [
        "  exchange       meses     n   rango (funding)                          "
        "         simbolo / motivo",
        "  " + "-" * 104,
    ]
    for r in table:
        if r["ok"]:
            rng = f"{r['start']} .. {r['end']}"
            status = r["symbol"] or ""
            lines.append(
                f"  {r['exchange']:<12} {r['months']:>6.2f} {r['n_rows']:>6}  "
                f"{rng:<48} {status}")
        else:
            lines.append(
                f"  {r['exchange']:<12} {'--':>6} {'--':>6}  "
                f"{'(no alcanzable)':<48} {r.get('symbol') or ''}  "
                f"<- {r['error']}")
    reachable = [r for r in table if r["ok"]]
    if reachable:
        best = reachable[0]
        lines.append("  " + "-" * 104)
        lines.append(
            f"  >> MAS PROFUNDO: {best['exchange']} con {best['months']:.2f} meses "
            f"({best['n_rows']} filas) -> fuente del backtest de funding.")
    else:
        lines.append("  " + "-" * 104)
        lines.append("  >> NINGUN exchange alcanzable en este entorno (red bloqueada"
                     " o geo-block). Corre el probe en Hetzner; mientras, forward-only.")
    return "\n".join(lines)


# ============================================================
# FETCH OPEN INTEREST (red; ccxt OKX). SHALLOW: degrada con gracia.
# ============================================================
def fetch_open_interest_history(
    exchange, symbol, data_dir="data", *,
    exchange_name=None, period=DEFAULT_OI_PERIOD,
    lookback_days=DEFAULT_FUNDING_LOOKBACK_DAYS, sleep_s=0.0, now_ms=None,
    use_cache=True,
):
    """Descarga el historico de OPEN INTEREST de `symbol` SI el exchange lo soporta.

    OKX OI history (Rubik trading-data) es a menudo SHALLOW (semanas, no años) y
    keyed por periodo 5m/1H/1D. Esta funcion:
      - si el exchange NO soporta fetch_open_interest_history -> devuelve
        (None, None) sin crashear (el caller sigue FUNDING-ONLY).
      - si soporta -> baja lo disponible y devuelve (df, (start, end)) donde df
        tiene columnas timestamp(datetime) · open_interest(float, valor USD) y
        (start,end) es el RANGO REAL cubierto (para que el caller decida si cubre
        la ventana primaria o degrada a funding-only).
      - cualquier error de red/parse -> (None, None) + warning (degrada con gracia).

    point-in-time: open_interest es el SNAPSHOT publicado por OKX en cada bucket,
    sin revisiones ni futuro.
    """
    ex_name = exchange_name or getattr(exchange, "id", None) or "okx"
    path = open_interest_path(data_dir, ex_name, symbol)
    if use_cache and os.path.exists(path):
        log.info("fetch_open_interest_history: cache HIT %s", path)
        df = pd.read_parquet(path)
        return df, _range_of(df)

    if not _supports_oi(exchange):
        log.info("fetch_open_interest_history: %s NO soporta OI history -> "
                 "funding-only", ex_name)
        return None, None

    now_ms = int(now_ms if now_ms is not None else _now_ms())
    since_ms = now_ms - int(lookback_days) * 86_400_000
    try:
        # OKX ignora `since` para muchos buckets y devuelve la ventana reciente
        # rodante; pasamos since+until por si el adaptador los respeta, pero
        # NO asumimos profundidad: tomamos lo que venga.
        batch = exchange.fetch_open_interest_history(
            symbol, timeframe=period, since=since_ms,
            params={"until": now_ms})
    except Exception as e:   # red, BadRequest, parse... -> degrada
        log.warning("fetch_open_interest_history: %s %s fallo (%s: %s) -> "
                    "funding-only", ex_name, symbol, type(e).__name__, str(e)[:160])
        return None, None

    rows = []
    for item in (batch or []):
        ts = item.get("timestamp")
        if ts is None:
            continue
        val = item.get("openInterestValue")
        if val is None:
            val = item.get("openInterestAmount")
        rows.append((int(ts), _to_float(val)))
    df = _oi_frame(rows)
    if len(df):
        _to_parquet(df, path)
        rng = _range_of(df)
        log.info("fetch_open_interest_history: %s %s n=%d [%s .. %s] -> %s",
                 ex_name, symbol, len(df), rng[0], rng[1], path)
        return df, rng
    log.warning("fetch_open_interest_history: %s %s historico vacio -> funding-only",
                ex_name, symbol)
    return None, None


def _oi_frame(rows):
    cols = ["timestamp", "open_interest"]
    if not rows:
        out = pd.DataFrame(columns=cols)
        out["timestamp"] = pd.to_datetime(out["timestamp"])
        out["open_interest"] = out["open_interest"].astype(float)
        return out
    df = pd.DataFrame(rows, columns=["ts_ms", "open_interest"])
    df = df.drop_duplicates(subset="ts_ms").sort_values("ts_ms").reset_index(drop=True)
    return pd.DataFrame({
        "timestamp": pd.to_datetime(df["ts_ms"], unit="ms"),
        "open_interest": pd.to_numeric(df["open_interest"], errors="coerce"),
    })


def _supports_oi(exchange):
    """True si el exchange anuncia (ccxt .has) que soporta OI history."""
    has = getattr(exchange, "has", None)
    if isinstance(has, dict):
        return bool(has.get("fetchOpenInterestHistory"))
    # objeto mock sin .has pero con el metodo -> asumimos soporte
    return callable(getattr(exchange, "fetch_open_interest_history", None))


def _range_of(df):
    if df is None or len(df) == 0:
        return None
    ts = pd.to_datetime(df["timestamp"])
    return (ts.iloc[0], ts.iloc[-1])


# ============================================================
# FEATURES CAUSALES (puro: DataFrames in -> DataFrame in)
# ============================================================
def funding_oi_features(
    df_primary, df_funding, df_oi=None, *,
    z_win=96, cum_win=24, shift=1,
):
    """Features ESTRUCTURALES de funding (+ OI) alineadas CAUSALMENTE a cada vela
    del primario. Pieza PURA: DataFrames in -> DataFrame in (sin red ni estado).

    df_primary : OHLCV con columna 'timestamp' (datetime). Define el indice/orden.
    df_funding : timestamp(datetime) · funding_rate(float). Granularidad ~8h (OKX);
                 NO tiene que coincidir con el TF primario (merge_asof lo alinea).
    df_oi      : opcional. timestamp(datetime) · open_interest(float). Si None, las
                 columnas oi_* NO se emiten (el caller/vector las trata como
                 ausentes -> imputadas a 0).

    DEVUELVE un DataFrame con UNA fila por vela primaria (mismo orden/longitud que
    df_primary). Columnas (todas con prefijo fund_/oi_):
      fund_rate        : ULTIMO funding YA LIQUIDADO con timestamp <= t (≤ t-shift
                         ventanas de funding). Es el premio que se esta cobrando.
      fund_zscore      : (fund_rate - media_movil) / std_movil sobre z_win ventanas
                         de funding (trailing). |z| grande = EXTREMO -> revierte.
      fund_cum         : suma de funding sobre cum_win ventanas (trailing). Presion
                         acumulada de un lado (carry pagado/cobrado en la ventana).
      fund_sign_streak : nº de ventanas de funding CONSECUTIVAS del mismo signo
                         (con signo: +N si las ultimas N son >0, -N si <0). Mide
                         persistencia de un lado (sesgo estructural sostenido).
      oi_chg           : pct-change del OI sobre cum_win ventanas de OI (trailing).
      oi_price_div     : sign(oi_chg) * sign(ret_primario sobre la MISMA ventana).
                         +1 = OI y precio en el mismo sentido (CONFIRMA: dinero
                         nuevo empuja el move) ; -1 = divergen (SQUEEZE: el move es
                         cierre de posiciones, no conviccion).
      oi_zscore        : z-score del OI sobre z_win ventanas de OI (trailing).

    ---------------------------------------------------------------------------
    LEAKAGE (el punto que se revisa). Una feature en la vela primaria t SOLO puede
    leer funding/OI con timestamp <= t (jamas el futuro):

    1) FUNDING LIQUIDA AL FINAL DE LA VENTANA ~8h. La tasa fechada en T se conoce y
       liquida al CERRAR esa ventana en T. En el instante de la decision del
       primario en t, una ventana de funding que aun no ha cerrado NO es conocible.
       Por eso desplazamos las features de funding shift=1 ventana ANTES de alinear
       -> en t se usa el ULTIMO funding YA LIQUIDADO (timestamp <= t-shift_ventanas),
       nunca una ventana en formacion. Eleccion CONSERVADORA y documentada (mismo
       criterio open-stamped que cross_asset_features con shift_cross=1).

    2) ALINEACION via pd.merge_asof(..., direction="backward"): a cada vela primaria
       t le empareja la fila de funding/OI con timestamp MAS RECIENTE que NO sea
       posterior a t. Nunca rellena desde el futuro (forward-fill), nunca centrada.
       Como funding es esparso (~8h) frente al primario (p.ej. 15m), backward reusa
       el ultimo funding liquidado para todas las velas primarias hasta el siguiente
       -> exactamente lo que un trader ve en vivo.

    3) Todas las ventanas rolling (zscore mean/std, cum, sign_streak, oi_chg/zscore)
       son TRAILING con min_periods: el valor en la fila k usa SOLO filas <= k de la
       propia serie de funding/OI. Sin ventana futura, sin centrado.

    4) El OI se trata identico: snapshot en su propio timestamp, desplazado shift y
       alineado backward. Su ret de precio en oi_price_div es el del PRIMARIO hasta
       t (pct_change trailing), no futuro.

    El resultado: el valor fund_*/oi_* en t NO refleja ningun funding/OI posterior a
    t (de hecho, ni la ventana fechada en t si aun no cerro: solo <= t-shift). La
    maquinaria OOS/embargo/OOT existente se mantiene honesta porque estas columnas
    son, por construccion, funcion solo del pasado.
    """
    n = len(df_primary)
    out = pd.DataFrame(index=range(n))
    for c in FUNDING_FEATURE_COLUMNS:
        out[c] = np.nan
    if df_primary is None or n == 0:
        return out
    if df_funding is None or len(df_funding) == 0:
        return out

    # --- serie de funding: features sobre su PROPIA serie (trailing) ---
    fr = pd.DataFrame({
        "timestamp": pd.to_datetime(df_funding["timestamp"]),
        "funding_rate": pd.to_numeric(df_funding["funding_rate"], errors="coerce"),
    }).sort_values("timestamp").reset_index(drop=True)
    rate = fr["funding_rate"]
    feat = pd.DataFrame({"timestamp": fr["timestamp"]})
    feat["fund_rate"] = rate
    roll = rate.rolling(int(z_win), min_periods=2)
    mean = roll.mean()
    std = roll.std()
    feat["fund_zscore"] = ((rate - mean) / std).replace([np.inf, -np.inf], np.nan)
    feat["fund_cum"] = rate.rolling(int(cum_win), min_periods=1).sum()
    feat["fund_sign_streak"] = _signed_streak(rate)

    # (1) CONSERVADOR: desplaza shift ventanas de funding ANTES de alinear -> la
    # ventana en formacion en t (funding_ts == t, aun sin liquidar) NO se usa; se
    # toma la ultima YA LIQUIDADA. NaN inicial limpio.
    fcols = [c for c in feat.columns if c != "timestamp"]
    if shift:
        feat[fcols] = feat[fcols].shift(int(shift))

    merged = _merge_backward(df_primary, feat, fcols)
    for c in FUNDING_FEATURE_COLUMNS:
        out[c] = merged[c].to_numpy() if c in merged.columns else np.nan

    # --- OI (opcional) ---
    if df_oi is not None and len(df_oi) > 0:
        oi = pd.DataFrame({
            "timestamp": pd.to_datetime(df_oi["timestamp"]),
            "open_interest": pd.to_numeric(df_oi["open_interest"], errors="coerce"),
        }).sort_values("timestamp").reset_index(drop=True)
        val = oi["open_interest"]
        ofeat = pd.DataFrame({"timestamp": oi["timestamp"]})
        ofeat["oi_chg"] = val.pct_change(int(cum_win))
        oroll = val.rolling(int(z_win), min_periods=2)
        ofeat["oi_zscore"] = (
            (val - oroll.mean()) / oroll.std()).replace([np.inf, -np.inf], np.nan)
        ocols = [c for c in ofeat.columns if c != "timestamp"]
        if shift:
            ofeat[ocols] = ofeat[ocols].shift(int(shift))
        omerged = _merge_backward(df_primary, ofeat, ocols)

        # oi_price_div = sign(oi_chg) * sign(ret_primario sobre la MISMA ventana).
        # ret del PRIMARIO hasta t (trailing, sin futuro).
        p_close = pd.to_numeric(df_primary["close"], errors="coerce").reset_index(drop=True)
        p_ret = p_close.pct_change(int(cum_win))
        oi_chg = omerged["oi_chg"].to_numpy()
        div = np.sign(oi_chg) * np.sign(p_ret.to_numpy())
        # NaN si falta cualquiera de los dos signos
        div = np.where(np.isnan(oi_chg) | ~np.isfinite(p_ret.to_numpy()), np.nan, div)

        out["oi_chg"] = oi_chg
        out["oi_zscore"] = omerged["oi_zscore"].to_numpy()
        out["oi_price_div"] = div
    return out


def _signed_streak(rate):
    """nº de valores CONSECUTIVOS del mismo signo terminando en cada posicion, CON
    signo: +k si las ultimas k son >0, -k si <0, 0 si la actual es 0/NaN. Trailing
    puro (cada posicion mira solo hacia atras). Vectorizado en un pase O(n)."""
    s = np.sign(np.asarray(pd.to_numeric(rate, errors="coerce"), dtype="float64"))
    out = np.zeros(len(s), dtype="float64")
    run = 0
    prev = 0.0
    for i in range(len(s)):
        x = s[i]
        if not np.isfinite(x) or x == 0.0:
            run = 0
            prev = 0.0
            out[i] = 0.0
            continue
        if x == prev:
            run += 1
        else:
            run = 1
            prev = x
        out[i] = run * x
    return out


def _merge_backward(df_primary, feat, value_cols):
    """merge_asof backward de `feat` (con 'timestamp') sobre las velas primarias:
    a cada vela t le pega la fila de feat con timestamp MAS RECIENTE <= t. Preserva
    el orden original del primario. Causal por construccion (nunca mira > t)."""
    prim = pd.DataFrame({
        "timestamp": pd.to_datetime(df_primary["timestamp"]).to_numpy()})
    prim["_pos"] = np.arange(len(prim))
    prim = prim.sort_values("timestamp")
    f = feat.sort_values("timestamp")
    merged = pd.merge_asof(prim, f, on="timestamp", direction="backward")
    merged = merged.sort_values("_pos").reset_index(drop=True)
    for c in value_cols:
        if c not in merged.columns:
            merged[c] = np.nan
    return merged


def attach_funding_oi_features(events, df_primary, df_funding, df_oi=None, **kwargs):
    """Inyecta las columnas fund_/oi_ (funding_oi_features) en un DataFrame de
    eventos/estados, casando por entry_index (posicion en df_primary).

    Mismo contrato que bt_features.attach_cross_asset_features:
    events: DataFrame con columna 'entry_index' (posicion de la vela primaria).
    Devuelve `events` con las columnas fund_/oi_ anexadas (no muta el original).
    Causal: cada fila recibe el valor de SU entry_index, que solo leyo funding/OI
    <= esa vela. No reordena los eventos. Tolerante a entry_index NaN / fuera de
    rango / negativo (rellena NaN en esas filas, no revienta).

    Columnas emitidas:
      - fund_* SIEMPRE (si hay df_funding; si no, NaN).
      - oi_*   SOLO si df_oi presente (si no, no se anaden: ausentes -> el vector
               las imputa a 0). Esto mantiene la semantica funding-only limpia.
    """
    want_oi = df_oi is not None and len(df_oi) > 0
    cols = list(FUNDING_FEATURE_COLUMNS) + (list(OI_FEATURE_COLUMNS) if want_oi else [])

    if events is None:
        return events
    if len(events) == 0:
        out = events.copy()
        for c in cols:
            if c not in out.columns:
                out[c] = np.nan
        return out

    ff = funding_oi_features(df_primary, df_funding, df_oi, **kwargs)
    ei = pd.to_numeric(events["entry_index"], errors="coerce").to_numpy()
    out = events.copy()
    n = len(ff)
    for c in cols:
        vals = np.full(len(out), np.nan)
        if c in ff.columns:
            ok = np.isfinite(ei) & (ei >= 0) & (ei < n)
            idx = ei[ok].astype(int)
            vals[ok] = ff[c].to_numpy()[idx]
        out[c] = vals
    return out


# ============================================================
# Utilidades (aisladas para test/mocks)
# ============================================================
def _to_float(x):
    try:
        if x is None:
            return np.nan
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def _now_ms():
    import time
    return int(time.time() * 1000)


def _sleep(s):
    import time
    time.sleep(s)
