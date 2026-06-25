# -*- coding: utf-8 -*-
"""
FUNDING / OPEN-INTEREST (estructural) — PRUEBAS DE CAUSALIDAD (anti-leakage)
                                        + FETCH MOCKEADO (sin red).

funding_oi.funding_oi_features / attach_funding_oi_features alinean features
ESTRUCTURALES de funding (extremos que revierten) y OI (confirma/squeeze) a cada
vela del primario. El punto que un fondo audita es que NINGUNA feature en la vela
primaria t pueda leer funding/OI posteriores a t -- y, por shift=1, ni siquiera la
ventana de funding fechada en t (aun sin liquidar): solo el ultimo YA LIQUIDADO.
Estos tests lo PRUEBAN sobre datos sinteticos, sin red ni motor:

  - un PICO de funding en t+1 NO aparece en fund_* en t (causal);
  - merge_asof backward sobre funding ESPARSO/desfasado (~8h vs 15m) reusa solo
    el ultimo funding liquidado <= t, jamas el futuro;
  - fund_zscore es trailing (mean/std solo del pasado);
  - attach casa por entry_index y tolera NaN / fuera de rango / negativo;
  - sin df_oi se emiten SOLO las fund_ (sin crash, sin oi_);
  - el fetch (funding y OI) se MOCKEA: pagina, cachea a Parquet, y degrada a
    funding-only si el exchange no soporta OI.
"""
import numpy as np
import pandas as pd
import pytest

import funding_oi as fo


# ============================================================
# Helpers sinteticos
# ============================================================
def _primary(n=120, start="2024-01-01", freq="15min", base=100.0):
    """OHLCV primario PLANO (close=base) salvo que se pase una serie."""
    ts = pd.date_range(start, periods=n, freq=freq)
    close = np.full(n, float(base))
    return pd.DataFrame({
        "timestamp": ts, "open": close, "high": close + 1.0,
        "low": close - 1.0, "close": close, "volume": 100.0,
    })


def _funding(rates, start="2024-01-01", freq="8h"):
    """Serie de funding ~8h desde una lista de tasas."""
    rates = np.asarray(rates, dtype=float)
    ts = pd.date_range(start, periods=len(rates), freq=freq)
    return pd.DataFrame({"timestamp": ts, "funding_rate": rates})


def _oi(values, start="2024-01-01", freq="1h"):
    values = np.asarray(values, dtype=float)
    ts = pd.date_range(start, periods=len(values), freq=freq)
    return pd.DataFrame({"timestamp": ts, "open_interest": values})


# ============================================================
# Estructura de salida
# ============================================================
def test_all_funding_columns_present_and_oi_absent_path():
    """Sin df_oi: salida con SOLO las fund_ (una fila por vela primaria), sin oi_."""
    dfp = _primary(n=60)
    dff = _funding([0.0001] * 30)
    ff = fo.funding_oi_features(dfp, dff, df_oi=None)
    for c in fo.FUNDING_FEATURE_COLUMNS:
        assert c in ff.columns, f"falta {c}"
    for c in fo.OI_FEATURE_COLUMNS:
        assert c not in ff.columns, f"oi_ no debe estar sin df_oi: {c}"
    assert len(ff) == len(dfp)


def test_oi_columns_present_when_oi_given():
    dfp = _primary(n=60)
    dff = _funding([0.0001] * 30)
    dfoi = _oi(np.linspace(1e9, 2e9, 120))
    ff = fo.funding_oi_features(dfp, dff, df_oi=dfoi)
    for c in fo.FUNDING_OI_FEATURE_COLUMNS:
        assert c in ff.columns, f"falta {c}"
    assert len(ff) == len(dfp)


# ============================================================
# CAUSALIDAD: el pico de funding del futuro NO se ve en t
# ============================================================
def test_funding_spike_at_t_plus_1_not_visible_at_t():
    """Un funding ALTO en la ventana j NO debe reflejarse en velas primarias cuyo
    ultimo funding liquidado es < la ventana j. Con shift=1, la ventana j recien
    pasa a ser 'liquidada' para las velas primarias DESPUES de que cierre j+1.

    Construccion: funding plano y bajo (0.0001) salvo un PICO en la ventana
    spike_w. Las velas primarias alrededor del INICIO de spike_w aun ven la
    ventana anterior (ya liquidada) -> fund_rate == 0.0001, no el pico.
    """
    base = 0.0001
    spike_w = 6
    rates = [base] * 14
    rates[spike_w] = 0.01            # pico 100x
    dff = _funding(rates, start="2024-01-01", freq="8h")
    # primario 15m que cubre las ventanas de funding
    dfp = _primary(n=14 * 32, freq="15min")   # 32 velas de 15m por ventana 8h
    ff = fo.funding_oi_features(dfp, dff, shift=1)

    # timestamps de cierre de cada ventana de funding
    fund_ts = pd.to_datetime(dff["timestamp"]).to_numpy()
    prim_ts = pd.to_datetime(dfp["timestamp"]).to_numpy()
    spike_open = fund_ts[spike_w]            # inicio/sello de la ventana del pico

    # Vela primaria JUSTO en el sello de la ventana del pico: con shift=1, el ultimo
    # funding LIQUIDADO disponible es <= la ventana spike_w-1 -> NO el pico.
    at_spike = int(np.searchsorted(prim_ts, spike_open))
    # algunas velas alrededor del sello (antes y en el instante)
    for k in (at_spike - 2, at_spike - 1, at_spike):
        if k < 0:
            continue
        assert ff["fund_rate"].iloc[k] == pytest.approx(base), (
            f"vela primaria {k} ve el pico de funding futuro (LEAKAGE): "
            f"fund_rate={ff['fund_rate'].iloc[k]}")

    # El pico (ventana spike_w, liquidada en su sello) se desplaza shift=1 -> queda
    # sobre el sello de la ventana spike_w+1, y merge_asof backward lo entrega a las
    # velas primarias a partir de ESE sello. Antes (sello de spike_w) NO se ve.
    appear_open = fund_ts[spike_w + 1]
    at_appear = int(np.searchsorted(prim_ts, appear_open))
    assert ff["fund_rate"].iloc[at_appear] == pytest.approx(0.01), (
        "el pico de funding debe verse una vez LIQUIDADO + shift (sello spike_w+1)")
    # y en el sello de spike_w (la ventana del pico en formacion bajo shift=1) AUN
    # no se ve: el ultimo liquidado es la ventana anterior (base).
    at_spike_sello = int(np.searchsorted(prim_ts, fund_ts[spike_w]))
    assert ff["fund_rate"].iloc[at_spike_sello] == pytest.approx(base), (
        "en el sello de la ventana del pico, shift=1 aun entrega el liquidado previo")


def test_shift_excludes_in_progress_funding_window():
    """La ventana de funding fechada EXACTAMENTE en t NO se usa para el primario t
    con shift=1 (usa la anterior, ya liquidada). El contraste con shift=0 (que SI
    la usaria) demuestra que el desplazamiento aporta la causalidad conservadora,
    no el merge_asof por si solo."""
    # funding: salta de 0.0 a 0.05 en la ventana 3 (sello t3)
    rates = [0.0, 0.0, 0.0, 0.05, 0.05, 0.05]
    dff = _funding(rates, freq="8h")
    dfp = _primary(n=6 * 32, freq="15min")
    fund_ts = pd.to_datetime(dff["timestamp"]).to_numpy()
    prim_ts = pd.to_datetime(dfp["timestamp"]).to_numpy()
    at_t3 = int(np.searchsorted(prim_ts, fund_ts[3]))   # vela en el sello de t3

    # shift=0: la ventana fechada en t3 (== t) SE usa -> ya se ve 0.05 en at_t3.
    ff0 = fo.funding_oi_features(dfp, dff, shift=0)
    assert ff0["fund_rate"].iloc[at_t3] == pytest.approx(0.05), (
        "con shift=0 la ventana fechada en t deberia verse en t")

    # shift=1 (conservador, default): esa ventana NO se usa aun en at_t3 -> 0.0.
    ff1 = fo.funding_oi_features(dfp, dff, shift=1)
    assert ff1["fund_rate"].iloc[at_t3] == pytest.approx(0.0), (
        "con shift=1 la ventana en formacion en t NO debe usarse (ultimo liquidado)")


# ============================================================
# merge_asof backward sobre funding esparso / desfasado
# ============================================================
def test_merge_asof_backward_sparse_funding_only_past():
    """Funding ESPARSO (~8h) vs primario (15m): cada vela primaria reusa el ultimo
    funding liquidado <= t (backward), nunca el siguiente. Y si el funding TERMINA
    antes del primario, las velas finales reusan el ultimo pasado (no NaN/futuro)."""
    rates = [0.001, 0.002, 0.003, 0.004]
    dff = _funding(rates, start="2024-01-01", freq="8h")
    # primario que se extiende MAS ALLA del ultimo funding
    dfp = _primary(n=6 * 32, freq="15min")
    ff = fo.funding_oi_features(dfp, dff, shift=1, z_win=4, cum_win=2)

    fund_ts = pd.to_datetime(dff["timestamp"]).to_numpy()
    prim_ts = pd.to_datetime(dfp["timestamp"]).to_numpy()

    # En una vela primaria dentro de la ventana k (>=1), con shift=1, el fund_rate
    # debe ser rates[k-1] (ultimo liquidado), no rates[k] (en formacion).
    at_w2 = int(np.searchsorted(prim_ts, fund_ts[2])) + 5   # bien dentro de la ventana 2
    assert ff["fund_rate"].iloc[at_w2] == pytest.approx(rates[1]), (
        f"backward+shift debe dar el funding liquidado anterior, no el actual: "
        f"got {ff['fund_rate'].iloc[at_w2]}")

    # Velas primarias mas alla del ULTIMO funding: reusan el ultimo liquidado
    # (rates[-2] por shift=1, ya que el ultimo sello aun 'en formacion' bajo shift).
    last = ff["fund_rate"].iloc[-1]
    assert np.isfinite(last), "no debe ser NaN por 'futuro' (backward reusa pasado)"
    assert last == pytest.approx(rates[-2]) or last == pytest.approx(rates[-1])


def test_fund_zscore_is_trailing():
    """fund_zscore en la ventana de funding j usa SOLO mean/std de funding <= j
    (trailing). Lo verificamos calculando el z trailing a mano sobre la serie de
    funding y comparando con el fund_zscore alineado a una vela primaria que cae en
    esa ventana (con shift=1 mira la ventana liquidada anterior)."""
    rng = np.random.default_rng(0)
    rates = rng.normal(0.0001, 0.0005, size=40)
    dff = _funding(rates, freq="8h")
    dfp = _primary(n=40 * 8, freq="1h")   # 8 velas de 1h por ventana 8h
    z_win, shift = 10, 1
    ff = fo.funding_oi_features(dfp, dff, z_win=z_win, shift=shift)

    # z trailing manual sobre la serie de funding
    s = pd.Series(rates)
    m = s.rolling(z_win, min_periods=2).mean()
    sd = s.rolling(z_win, min_periods=2).std()
    z_manual = ((s - m) / sd).shift(shift)   # mismo shift que el modulo

    fund_ts = pd.to_datetime(dff["timestamp"]).to_numpy()
    prim_ts = pd.to_datetime(dfp["timestamp"]).to_numpy()
    # vela primaria dentro de la ventana 25 -> ve el z (shifted) de la ventana 24
    j = 25
    at_j = int(np.searchsorted(prim_ts, fund_ts[j])) + 2
    got = ff["fund_zscore"].iloc[at_j]
    assert got == pytest.approx(z_manual.iloc[j], rel=1e-6, nan_ok=True), (
        f"fund_zscore no coincide con el z trailing manual: got {got} "
        f"exp {z_manual.iloc[j]}")
    # y NO debe coincidir con un z que incluya el futuro (centrado) -> sanity:
    assert not np.isnan(got)


def test_sign_streak_signed_and_trailing():
    """fund_sign_streak: +k si las ultimas k ventanas de funding son >0, -k si <0,
    reinicio en 0/cambio de signo. Trailing puro."""
    rates = [0.001, 0.001, 0.001, -0.002, -0.002, 0.0, 0.003]
    streak = fo._signed_streak(np.array(rates))
    assert list(streak) == [1.0, 2.0, 3.0, -1.0, -2.0, 0.0, 1.0], streak


# ============================================================
# OI: confirma (+1) vs squeeze (-1)
# ============================================================
def test_oi_price_div_confirm_and_squeeze():
    """oi_price_div = sign(oi_chg)*sign(ret_primario). OI y precio SUBIENDO juntos
    -> +1 (confirma). OI BAJANDO con precio SUBIENDO -> -1 (squeeze)."""
    n = 200
    # primario con tendencia ALCISTA clara (ret>0)
    ts = pd.date_range("2024-01-01", periods=n, freq="15min")
    close = np.linspace(100.0, 120.0, n)
    dfp = pd.DataFrame({"timestamp": ts, "open": close, "high": close + 1,
                        "low": close - 1, "close": close, "volume": 100.0})
    dff = _funding([0.0001] * 30)

    # OI tambien SUBIENDO -> confirma (+1)
    oi_up = _oi(np.linspace(1e9, 2e9, n), freq="15min")
    ff_up = fo.funding_oi_features(dfp, dff, df_oi=oi_up, cum_win=10, z_win=20)
    div_up = ff_up["oi_price_div"].dropna()
    assert (div_up == 1.0).mean() > 0.9, "OI y precio al alza -> +1 (confirma)"

    # OI BAJANDO mientras el precio sube -> squeeze (-1)
    oi_dn = _oi(np.linspace(2e9, 1e9, n), freq="15min")
    ff_dn = fo.funding_oi_features(dfp, dff, df_oi=oi_dn, cum_win=10, z_win=20)
    div_dn = ff_dn["oi_price_div"].dropna()
    assert (div_dn == -1.0).mean() > 0.9, "OI baja con precio al alza -> -1 (squeeze)"


# ============================================================
# attach por entry_index + tolerancia
# ============================================================
def test_attach_maps_by_entry_index_and_tolerates_bad_index():
    n = 14 * 32
    rates = [0.0001] * 14
    rates[6] = 0.02
    dff = _funding(rates, freq="8h")
    dfp = _primary(n=n, freq="15min")
    fund_ts = pd.to_datetime(dff["timestamp"]).to_numpy()
    prim_ts = pd.to_datetime(dfp["timestamp"]).to_numpy()
    # pico en la ventana 6 (sello fund_ts[6]); con shift=1 se ve a partir del sello
    # de la ventana 7 -> indice de una vela cuyo ultimo funding liquidado ES el pico
    at_appear = int(np.searchsorted(prim_ts, fund_ts[7]))
    # una vela con funding YA disponible pero anterior al pico (post sello ventana 2)
    at_avail = int(np.searchsorted(prim_ts, fund_ts[3]))

    events = pd.DataFrame({
        "entry_index": [at_avail, at_appear, np.nan, -5, n + 100, at_avail + 1],
        "foo": [1, 2, 3, 4, 5, 6],
        "entry_ts": pd.to_datetime("2024-01-01"),
    })
    out = fo.attach_funding_oi_features(events, dfp, dff, df_oi=None)

    assert "foo" in out.columns and "entry_index" in out.columns
    for c in fo.FUNDING_FEATURE_COLUMNS:
        assert c in out.columns
    # sin df_oi: NO se anaden oi_
    for c in fo.OI_FEATURE_COLUMNS:
        assert c not in out.columns
    assert len(out) == len(events)

    # la fila con entry_index=at_appear ve el pico ya liquidado
    r_app = out.iloc[1]
    assert r_app["fund_rate"] == pytest.approx(0.02)
    # la fila at_avail (funding disponible, pre-pico) ve la tasa base, no NaN
    assert out.iloc[0]["fund_rate"] == pytest.approx(0.0001)
    # indices patologicos (posiciones 2,3,4: NaN,-5,n+100) -> NaN, sin crash
    bad = out.iloc[[2, 3, 4]]
    assert bad["fund_rate"].isna().all()
    # validos (0,1,5) no NaN
    assert out.iloc[[0, 1, 5]]["fund_rate"].notna().all()


def test_attach_empty_and_none_funding_are_safe():
    dfp = _primary(n=40)
    dff = _funding([0.0001] * 10)

    empty = fo.attach_funding_oi_features(
        pd.DataFrame({"entry_index": []}), dfp, dff, df_oi=None)
    assert all(c in empty.columns for c in fo.FUNDING_FEATURE_COLUMNS)
    assert len(empty) == 0

    # funding None -> fund_ todo NaN, longitud == primario
    none_f = fo.funding_oi_features(dfp, None)
    assert len(none_f) == 40
    assert none_f["fund_rate"].isna().all()

    events = pd.DataFrame({"entry_index": [1, 2, 3], "foo": [9, 9, 9]})
    out_none = fo.attach_funding_oi_features(events, dfp, None, df_oi=None)
    assert all(c in out_none.columns for c in fo.FUNDING_FEATURE_COLUMNS)
    assert out_none["fund_rate"].isna().all()
    assert "foo" in out_none.columns


def test_attach_with_oi_adds_oi_columns():
    dfp = _primary(n=120)
    dff = _funding([0.0001] * 30)
    dfoi = _oi(np.linspace(1e9, 2e9, 120))
    events = pd.DataFrame({"entry_index": [10, 50, 100], "foo": [1, 2, 3]})
    out = fo.attach_funding_oi_features(events, dfp, dff, df_oi=dfoi)
    for c in fo.FUNDING_OI_FEATURE_COLUMNS:
        assert c in out.columns
    assert len(out) == 3


# ============================================================
# FETCH MOCKEADO (sin red): paginacion + cache + degradacion OI
# ============================================================
class _FakeFundingExchange:
    """Exchange ccxt-like que sirve funding paginado por `since` (hacia ADELANTE),
    SIN red — como bybit/gate/binance. n ventanas de 8h hasta now_ms."""

    id = "bybit"
    has = {"fetchFundingRateHistory": True, "fetchOpenInterestHistory": True}

    def __init__(self, now_ms, n=250, step_ms=8 * 3600_000, page=100):
        self._all = []   # ascendente por ts
        for i in range(n):
            ts = now_ms - (n - 1 - i) * step_ms
            self._all.append({"timestamp": ts, "fundingRate": 0.0001 + i * 1e-6,
                              "symbol": "BTC/USDT:USDT"})
        self._page = page
        self.calls = 0

    def fetch_funding_rate_history(self, symbol, since=None, limit=None, params=None):
        self.calls += 1
        limit = limit or self._page
        pool = self._all
        if since is not None:
            pool = [r for r in pool if r["timestamp"] >= since]
        # estilo bybit/gate: las MAS ANTIGUAS desde `since` (cabeza del pool), <=limit
        return pool[:limit]


class _FakeOIExchange:
    id = "okx"
    has = {"fetchOpenInterestHistory": True}

    def __init__(self, now_ms, n=200, step_ms=3600_000):
        self._all = [{"timestamp": now_ms - (n - 1 - i) * step_ms,
                      "openInterestValue": 1e9 + i * 1e6,
                      "symbol": "BTC/USDT:USDT"} for i in range(n)]

    def fetch_open_interest_history(self, symbol, timeframe="1H", since=None,
                                    limit=None, params=None):
        return list(self._all)


class _NoOIExchange:
    id = "okx"
    has = {"fetchFundingRateHistory": True, "fetchOpenInterestHistory": False}

    def fetch_funding_rate_history(self, symbol, since=None, limit=None, params=None):
        return []


def test_fetch_funding_history_paginates_and_caches(tmp_path):
    step = 8 * 3600_000
    # el ultimo row del fake cae en (now - step); pedimos con now un paso DESPUES
    # del ultimo row para que las 250 ventanas (ya cerradas) sean elegibles.
    now = 1_700_000_000_000 + step
    ex = _FakeFundingExchange(1_700_000_000_000, n=250, page=100)
    df = fo.fetch_funding_history(
        ex, "BTC/USDT:USDT", data_dir=str(tmp_path), exchange_name="okx",
        lookback_days=365, now_ms=now, sleep_s=0.0)
    # debe haber paginado (250 rows / 100 por pagina -> >=3 llamadas)
    assert ex.calls >= 3, f"no pagino lo suficiente: {ex.calls} llamadas"
    assert list(df.columns) == ["timestamp", "funding_rate"]
    assert len(df) == 250
    assert df["timestamp"].is_monotonic_increasing
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])
    # cache escrito
    path = fo.funding_path(str(tmp_path), "okx", "BTC/USDT:USDT")
    import os
    assert os.path.exists(path)
    # segunda llamada: cache HIT (no vuelve a paginar)
    ex2 = _FakeFundingExchange(now, n=250, page=100)
    df2 = fo.fetch_funding_history(
        ex2, "BTC/USDT:USDT", data_dir=str(tmp_path), exchange_name="okx",
        now_ms=now)
    assert ex2.calls == 0, "deberia cargar del cache, no pegarle al exchange"
    assert len(df2) == 250


def test_fetch_funding_respects_lookback_floor(tmp_path):
    now = 1_700_000_000_000
    # 250 ventanas de 8h ~= 83 dias. lookback 10 dias -> recorta a ~30 ventanas.
    ex = _FakeFundingExchange(now, n=250, page=100)
    df = fo.fetch_funding_history(
        ex, "BTC/USDT:USDT", data_dir=str(tmp_path), exchange_name="okx",
        lookback_days=10, now_ms=now)
    span_days = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).total_seconds() / 86400
    assert span_days <= 10.5, f"no respeto el floor de lookback: {span_days:.1f}d"
    assert len(df) < 250


class _IgnoresSinceExchange:
    """Exchange que IGNORA `since` y devuelve SIEMPRE la ventana mas reciente (el
    modo de falla real: bybit/binance frente al viejo cursor `before`). El fetch
    debe cortar limpio por 'sin progreso' y NO colgarse en un loop infinito."""

    id = "bybit"
    has = {"fetchFundingRateHistory": True}

    def __init__(self, now_ms, n=250, step_ms=8 * 3600_000, page=100):
        self._all = [{"timestamp": now_ms - (n - 1 - i) * step_ms,
                      "fundingRate": 0.0001, "symbol": "BTC/USDT:USDT"}
                     for i in range(n)]
        self._page = page
        self.calls = 0

    def fetch_funding_rate_history(self, symbol, since=None, limit=None, params=None):
        self.calls += 1
        limit = limit or self._page
        return self._all[-limit:]   # SIEMPRE las mas recientes; ignora `since`


def test_fetch_funding_ignores_since_terminates_no_loop(tmp_path):
    # Regresion del bug de profundidad: cuando el exchange ignora el cursor, el
    # fetch NO debe loopear; corta por 'sin progreso' tras un par de llamadas y
    # devuelve a lo sumo una ventana (page) de filas unicas.
    now = 1_700_000_000_000 + 8 * 3600_000
    ex = _IgnoresSinceExchange(1_700_000_000_000, n=250, page=100)
    df = fo.fetch_funding_history(
        ex, "BTC/USDT:USDT", data_dir=str(tmp_path), exchange_name="bybit",
        lookback_days=365, now_ms=now, sleep_s=0.0)
    assert ex.calls <= 3, f"deberia cortar rapido, no loopear: {ex.calls}"
    assert 0 < len(df) <= 100


def test_fetch_open_interest_history_mocked(tmp_path):
    now = 1_700_000_000_000
    ex = _FakeOIExchange(now, n=200)
    df, rng = fo.fetch_open_interest_history(
        ex, "BTC/USDT:USDT", data_dir=str(tmp_path), exchange_name="okx",
        now_ms=now)
    assert df is not None and len(df) == 200
    assert list(df.columns) == ["timestamp", "open_interest"]
    assert rng is not None and rng[0] < rng[1]
    import os
    assert os.path.exists(fo.open_interest_path(str(tmp_path), "okx", "BTC/USDT:USDT"))


def test_fetch_oi_unsupported_degrades_gracefully(tmp_path):
    """Exchange SIN soporte de OI -> (None, None), nunca crashea (funding-only)."""
    ex = _NoOIExchange()
    df, rng = fo.fetch_open_interest_history(
        ex, "BTC/USDT:USDT", data_dir=str(tmp_path), exchange_name="okx",
        now_ms=1_700_000_000_000)
    assert df is None and rng is None


def test_fetch_oi_network_error_degrades_gracefully(tmp_path):
    """Si el fetch de OI lanza (red/BadRequest), degrada a (None,None) sin crash."""
    class _Boom:
        id = "okx"
        has = {"fetchOpenInterestHistory": True}

        def fetch_open_interest_history(self, *a, **k):
            raise RuntimeError("network down")

    df, rng = fo.fetch_open_interest_history(
        _Boom(), "BTC/USDT:USDT", data_dir=str(tmp_path), now_ms=1_700_000_000_000)
    assert df is None and rng is None


def test_fetch_funding_empty_history_no_crash(tmp_path):
    """Historico de funding vacio -> DataFrame vacio con el esquema, sin crash."""
    class _Empty:
        id = "okx"
        has = {"fetchFundingRateHistory": True}

        def fetch_funding_rate_history(self, *a, **k):
            return []

    df = fo.fetch_funding_history(
        _Empty(), "BTC/USDT:USDT", data_dir=str(tmp_path), now_ms=1_700_000_000_000)
    assert list(df.columns) == ["timestamp", "funding_rate"]
    assert len(df) == 0
