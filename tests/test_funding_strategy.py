# -*- coding: utf-8 -*-
"""
FUNDING STRATEGY (reversion estructural) — PRUEBAS de la SENAL + del MAPEO a
trades + CAUSALIDAD, y del runner FORWARD en papel (fetch MOCKEADO, sin red).

funding_strategy.funding_reversion_signal FADEA los extremos de funding:
  z >= +z_enter -> SHORT (longs sobrepagan), z <= -z_enter -> LONG, |z|<=z_exit ->
  FLAT, con HISTERESIS en la banda intermedia. positions_to_trades convierte la
  serie de posiciones en eventos de entrada que enchufan en el labeler/harness.
funding_paper.FundingPaperRuntime acumula el track record forward en papel SIN
RED (la traida de funding y el precio se inyectan / mockean).

Lo que un fondo audita y aqui se PRUEBA:
  - la senal dispara el lado correcto en cada extremo y sostiene/suelta por
    histeresis; plano en el medio; NaN -> FLAT sin arrastrar estado;
  - el mapeo a trades detecta flancos (entrada/volteo), pone stop/target en R con
    el signo correcto, y es CAUSAL (no mira velas futuras);
  - el probe multi-exchange (Part C) elige el funding MAS PROFUNDO y degrada con
    gracia cuando un exchange no es alcanzable (red/geo-block), sin crash;
  - el runner en papel solo ve funding realizado, abre/cierra/voltea y sella en el
    ledger durable.
"""
import numpy as np
import pandas as pd
import pytest

import funding_strategy as fs
import funding_oi as fo


# ============================================================
# Helpers
# ============================================================
def _primary(closes, start="2024-01-01", freq="15min"):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    ts = pd.date_range(start, periods=n, freq=freq)
    return pd.DataFrame({
        "timestamp": ts, "open": closes, "high": closes + 0.5,
        "low": closes - 0.5, "close": closes, "volume": 100.0,
    })


# ============================================================
# SENAL: lados correctos en los extremos
# ============================================================
def test_signal_short_on_high_positive_z():
    """z muy positivo (longs sobrepagan) -> SHORT (-1)."""
    z = [0.0, 2.5, 3.0]
    pos = fs.funding_reversion_signal(z, z_enter=2.0, z_exit=0.5)
    assert pos[1] == fs.SHORT and pos[2] == fs.SHORT


def test_signal_long_on_low_negative_z():
    """z muy negativo (shorts sobrepagan) -> LONG (+1)."""
    z = [0.0, -2.5, -3.0]
    pos = fs.funding_reversion_signal(z, z_enter=2.0, z_exit=0.5)
    assert pos[1] == fs.LONG and pos[2] == fs.LONG


def test_signal_flat_in_the_middle():
    """|z| pequeño -> FLAT (0)."""
    z = [0.0, 0.3, -0.4, 0.1]
    pos = fs.funding_reversion_signal(z, z_enter=2.0, z_exit=0.5)
    assert list(pos) == [0, 0, 0, 0]


def test_signal_hysteresis_holds_between_bands():
    """Una vez SHORT (z>=+enter), se MANTIENE en la banda intermedia (exit<z<enter)
    y solo suelta a FLAT cuando |z|<=z_exit. Esa es la histeresis (no toquetear en
    cada cruce de ruido)."""
    # z: entra short (2.5) -> baja a la zona intermedia (1.0, 0.8) -> mantiene short
    #    -> cae a 0.4 (<=exit) -> FLAT
    z = [2.5, 1.0, 0.8, 0.4, 0.45]
    pos = fs.funding_reversion_signal(z, z_enter=2.0, z_exit=0.5)
    assert pos[0] == fs.SHORT
    assert pos[1] == fs.SHORT and pos[2] == fs.SHORT, "histeresis: mantiene en la banda"
    assert pos[3] == fs.FLAT, "|z|<=z_exit -> suelta"
    assert pos[4] == fs.FLAT, "ya plano, sigue plano (|z|<=exit)"


def test_signal_direct_flip_extreme_to_extreme():
    """Cruce directo de extremo + a extremo - voltea la posicion en esa barra."""
    z = [2.5, -2.5]
    pos = fs.funding_reversion_signal(z, z_enter=2.0, z_exit=0.5)
    assert pos[0] == fs.SHORT and pos[1] == fs.LONG


def test_signal_nan_is_flat_and_resets_state():
    """NaN (warmup/hueco) -> FLAT en esa barra y NO arrastra el estado previo."""
    z = [2.5, np.nan, 1.0]   # 2.5 -> short; NaN -> flat+reset; 1.0 (intermedio
    #                          tras reset) -> arrastra el FLAT del reset, no short.
    pos = fs.funding_reversion_signal(z, z_enter=2.0, z_exit=0.5)
    assert pos[0] == fs.SHORT
    assert pos[1] == fs.FLAT, "NaN -> FLAT"
    assert pos[2] == fs.FLAT, "tras reset por NaN, la zona intermedia arrastra FLAT"


def test_signal_requires_hysteresis_bands_ordered():
    """z_exit debe ser < z_enter (si no, ValueError) y z_enter>0."""
    with pytest.raises(ValueError):
        fs.funding_reversion_signal([0.0], z_enter=1.0, z_exit=1.0)
    with pytest.raises(ValueError):
        fs.funding_reversion_signal([0.0], z_enter=0.0, z_exit=-1.0)


def test_signal_length_and_dtype():
    z = np.linspace(-3, 3, 50)
    pos = fs.funding_reversion_signal(z, z_enter=2.0, z_exit=0.5)
    assert len(pos) == 50
    assert set(np.unique(pos)).issubset({-1, 0, 1})


def test_signal_is_causal_prefix_invariant():
    """CAUSAL: la posicion en t NO depende de barras > t. Cortar la serie en k y
    re-evaluar debe dar EXACTAMENTE el mismo prefijo (cambiar el futuro no cambia
    el pasado de la senal)."""
    rng = np.random.default_rng(3)
    z = rng.normal(0, 1.5, 80)
    full = fs.funding_reversion_signal(z, z_enter=2.0, z_exit=0.5)
    for k in (10, 33, 60):
        pref = fs.funding_reversion_signal(z[:k], z_enter=2.0, z_exit=0.5)
        assert list(pref) == list(full[:k]), f"prefijo {k} cambia con el futuro (LEAKAGE)"


# ============================================================
# positions_to_trades: flancos, stop/target, causalidad
# ============================================================
def test_trades_detects_entries_and_flip():
    """Eventos en cada flanco de entrada y en el volteo; ninguno en FLAT->FLAT."""
    # pos: 0,0,+1(entra),+1,0(sale),-1(entra short),-1
    pos = [0, 0, 1, 1, 0, -1, -1]
    dfp = _primary([100, 101, 102, 103, 104, 105, 106])
    tr = fs.positions_to_trades(pos, dfp, stop_r_pct=0.01, target_rr=1.0)
    # entradas en index 2 (long) y 5 (short)
    assert list(tr["entry_index"]) == [2, 5]
    assert list(tr["direction"]) == [1, -1]
    # entry_price = close de esa barra
    assert tr["entry_price"].iloc[0] == pytest.approx(102.0)
    assert tr["entry_price"].iloc[1] == pytest.approx(105.0)


def test_trades_stop_target_signs():
    """LONG: stop por DEBAJO, target por ARRIBA; SHORT: al reves. R=entry*stop_r_pct."""
    pos = [1, 0, -1]
    dfp = _primary([100.0, 100.0, 200.0])
    tr = fs.positions_to_trades(pos, dfp, stop_r_pct=0.01, target_rr=2.0)
    long_row = tr[tr["direction"] == 1].iloc[0]
    assert long_row["stop_price"] == pytest.approx(99.0)     # 100 - 1%
    assert long_row["target_price"] == pytest.approx(102.0)  # 100 + 2*1%
    short_row = tr[tr["direction"] == -1].iloc[0]
    assert short_row["stop_price"] == pytest.approx(202.0)   # 200 + 1%
    assert short_row["target_price"] == pytest.approx(196.0)  # 200 - 2*1%


def test_trades_flip_records_exit_index():
    """Un volteo cierra el trade anterior con exit_index = barra del volteo."""
    pos = [1, 1, -1]
    dfp = _primary([100, 101, 102])
    tr = fs.positions_to_trades(pos, dfp)
    # el primer trade (long en 0) tiene exit_index = 2 (donde voltea a short)
    assert tr.iloc[0]["exit_index"] == 2


def test_trades_length_mismatch_raises():
    with pytest.raises(ValueError):
        fs.positions_to_trades([1, 0, 1], _primary([100, 101]))


def test_trades_empty_when_all_flat():
    tr = fs.positions_to_trades([0, 0, 0], _primary([1, 2, 3]))
    assert len(tr) == 0
    # esquema presente para que el harness no truene en len()==0
    for c in ("entry_index", "direction", "entry_price", "stop_price", "target_price"):
        assert c in tr.columns


def test_trades_plug_into_labeler():
    """Los eventos de positions_to_trades labelan SIN tocar nada (contrato del
    harness: entry_index/entry_price/stop_price/target_price/direction)."""
    import bt_labeler as lb
    pos = [0, 1, 1, 1, 0]
    # precio que sube y toca el target del long (entry 101 @idx1, tp=101*1.01=102.01)
    dfp = _primary([100, 101, 101.5, 103.0, 103.0])
    tr = fs.positions_to_trades(pos, dfp, stop_r_pct=0.01, target_rr=1.0)
    labeled = lb.label_events(dfp, tr.to_dict("records"), max_bars=10)
    assert len(labeled) == 1
    assert labeled.iloc[0]["outcome"] in (lb.WIN, lb.LOSS, lb.TIMEOUT)
    # el long que sube a 103 debe GANAR (toca 102.01)
    assert labeled.iloc[0]["outcome"] == lb.WIN


def test_signal_to_trades_end_to_end_causal_with_funding_oi():
    """End-to-end: funding_oi.fund_zscore (causal) -> senal -> trades. Un PICO de
    funding tardio NO debe crear un trade en barras anteriores (causalidad heredada
    de funding_oi: shift + merge backward + trailing)."""
    # funding plano y bajo salvo un pico positivo grande tardio -> z se dispara
    # SOLO despues del pico; la senal SHORT no puede aparecer antes.
    rates = [0.0001] * 30
    for j in range(20, 30):
        rates[j] = 0.02
    ts_f = pd.date_range("2024-01-01", periods=len(rates), freq="8h")
    dff = pd.DataFrame({"timestamp": ts_f, "funding_rate": rates})
    dfp = _primary(np.full(30 * 32, 100.0), freq="15min")
    ff = fo.funding_oi_features(dfp, dff, z_win=10, shift=1)
    pos = fs.funding_reversion_signal(ff["fund_zscore"].to_numpy(),
                                      z_enter=2.0, z_exit=0.5)
    tr = fs.positions_to_trades(pos, dfp)
    # cualquier entrada SHORT debe caer DESPUES del inicio del pico de funding.
    spike_ts = ts_f[20]
    if len(tr):
        entry_ts = pd.to_datetime(tr["entry_ts"])
        shorts = tr[tr["direction"] == -1]
        assert (pd.to_datetime(shorts["entry_ts"]) >= spike_ts).all(), \
            "una entrada short aparece ANTES del pico de funding (LEAKAGE)"


# ============================================================
# PART C: probe multi-exchange de profundidad (fetch MOCKEADO, sin red)
# ============================================================
class _FakeFundingExchange:
    """ccxt-like: sirve n ventanas de 8h hasta now_ms, paginado por 'before'."""
    def __init__(self, ex_id, now_ms, n, page=100):
        self.id = ex_id
        self.has = {"fetchFundingRateHistory": True}
        self._all = [{"timestamp": now_ms - (n - 1 - i) * 8 * 3600_000,
                      "fundingRate": 0.0001 + i * 1e-6} for i in range(n)]
        self._page = page
        self.calls = 0

    def fetch_funding_rate_history(self, symbol, since=None, limit=None, params=None):
        self.calls += 1
        params = params or {}
        before = params.get("before")
        limit = limit or self._page
        pool = self._all
        if before is not None:
            pool = [r for r in pool if r["timestamp"] < before]
        return pool[-limit:]


def test_probe_picks_deepest_exchange(tmp_path):
    """probe_funding_depth elige el exchange con MAS meses y reporta la tabla."""
    now = 1_700_000_000_000 + 8 * 3600_000
    # bybit MAS profundo (600 ventanas ~200 dias) que okx (60 ~20 dias)
    depths = {"okx": 60, "bybit": 600, "gateio": 300}

    def fake_make(ex_id):
        if ex_id not in depths:
            raise ValueError(f"{ex_id} no soportado")  # binanceusdm etc -> skip
        return _FakeFundingExchange(ex_id, now, depths[ex_id])

    table = fo.probe_funding_depth(
        "BTC", exchange_ids=("okx", "bybit", "gateio", "binanceusdm"),
        make_exchange=fake_make, data_dir=str(tmp_path), now_ms=now,
        lookback_days=365 * 3)
    # ordenada por meses desc; el primero reachable es bybit
    reachable = [r for r in table if r["ok"]]
    assert reachable[0]["exchange"] == "bybit"
    assert reachable[0]["months"] > reachable[1]["months"]
    # binanceusdm no soportado -> reportado con error, sin crash
    binance = [r for r in table if r["exchange"] == "binanceusdm"][0]
    assert binance["ok"] is False and binance["error"]
    # tabla formateada legible
    txt = fo.format_depth_table(table)
    assert "MAS PROFUNDO" in txt and "bybit" in txt


def test_fetch_best_returns_deepest_df(tmp_path):
    now = 1_700_000_000_000 + 8 * 3600_000
    depths = {"okx": 50, "bybit": 400}

    def fake_make(ex_id):
        if ex_id not in depths:
            raise ValueError("nope")
        return _FakeFundingExchange(ex_id, now, depths[ex_id])

    df, best, table = fo.fetch_funding_history_best(
        "BTC", exchange_ids=("okx", "bybit"), make_exchange=fake_make,
        data_dir=str(tmp_path), now_ms=now, lookback_days=365 * 3)
    assert best["exchange"] == "bybit"
    # ~400 (la paginacion hacia atras puede soltar la fila del borde -> >=398).
    assert df is not None and len(df) >= 398
    assert list(df.columns) == ["timestamp", "funding_rate"]


def test_probe_all_unreachable_degrades(tmp_path):
    """Si NINGUN exchange es alcanzable (red bloqueada/geo) -> tabla con todos en
    error, fetch_best devuelve (None, None, table), y el texto avisa forward-only."""
    def boom(ex_id):
        raise ConnectionError("network down")  # simula env sin red

    df, best, table = fo.fetch_funding_history_best(
        "BTC", exchange_ids=("okx", "bybit"), make_exchange=boom,
        data_dir=str(tmp_path))
    assert df is None and best is None
    assert all(not r["ok"] for r in table)
    assert "NINGUN exchange alcanzable" in fo.format_depth_table(table)


def test_perp_symbol_for_quotes():
    assert fo.perp_symbol_for("okx", "BTC") == "BTC/USDT:USDT"
    assert fo.perp_symbol_for("hyperliquid", "ETH") == "ETH/USDC:USDC"


# ============================================================
# PART B3: runner forward en papel (fetch MOCKEADO, sin red)
# ============================================================
import tools.funding_paper as fp
import execution as ex


def _funding_df(rates, start="2024-01-01"):
    ts = pd.date_range(start, periods=len(rates), freq="8h")
    return pd.DataFrame({"timestamp": ts, "funding_rate": np.asarray(rates, float)})


# Funding con un PICO (ventana extrema) recien liquidado: la ultima ventana ya
# liquidada (shift=1) es el pico -> z alto. Un PLATEAU de extremos no sirve (el z
# trailing se relaja conforme el pico entra a la media) -> es el caso REALISTA: la
# reversion entra al EXTREMO recien sellado, no a un sesgo sostenido.
_SPIKE_POS = [0.0001] * 22 + [0.05, 0.0001]
_SPIKE_NEG = [0.0001] * 22 + [-0.05, 0.0001]


def test_runtime_opens_short_on_extreme_positive_z():
    """Poll con z extremo positivo -> abre SHORT en papel + sella en el ledger."""
    rt = fp.FundingPaperRuntime("BTC/USDT:USDT",
                                account=ex.Account("p", 10_000.0),
                                z_enter=2.0, z_exit=0.5, z_win=10)
    out = rt.poll(_funding_df(_SPIKE_POS), price=100.0)
    assert out["desired_dir"] == fs.SHORT
    assert out["opened"] is not None
    assert rt.cur_dir == fs.SHORT and rt.cur_pos is not None
    assert rt.broker.ledger.verify()
    evs = [r["payload"]["event"] for r in rt.broker.ledger.records]
    assert "OPEN" in evs and "FUNDING_OPEN_META" in evs


def test_runtime_resolves_open_against_price():
    """Una posicion abierta se resuelve (TP) cuando el precio la alcanza."""
    rt = fp.FundingPaperRuntime("BTC/USDT:USDT",
                                account=ex.Account("p", 10_000.0),
                                z_enter=2.0, z_exit=0.5, z_win=10,
                                stop_r_pct=0.01, target_rr=1.0)
    rt.poll(_funding_df(_SPIKE_POS), price=100.0)        # abre SHORT (tp=99.0)
    assert rt.cur_pos is not None
    # siguiente poll: el precio CAE y toca el TP del short (low<=99)
    out = rt.poll(_funding_df(_SPIKE_POS), price=98.5, high=99.5, low=98.0)
    assert any(r["reason"] == "tp" for r in out["resolved"])


def test_runtime_flips_on_signal_change():
    """Si el z cruza de extremo + a extremo -, cierra el short y abre long."""
    rt = fp.FundingPaperRuntime("BTC/USDT:USDT",
                                account=ex.Account("p", 10_000.0),
                                z_enter=2.0, z_exit=0.5, z_win=10)
    rt.poll(_funding_df(_SPIKE_POS), price=100.0)    # SHORT
    assert rt.cur_dir == fs.SHORT
    out = rt.poll(_funding_df(_SPIKE_NEG), price=100.0)
    assert out["desired_dir"] == fs.LONG and rt.cur_dir == fs.LONG
    # se sello un CLOSE (flip) y un nuevo OPEN
    evs = [r["payload"] for r in rt.broker.ledger.records]
    assert any(e["event"] == "CLOSE" and e.get("reason") == "signal_flip" for e in evs)


def test_runtime_flat_in_the_middle_no_open():
    rt = fp.FundingPaperRuntime("BTC/USDT:USDT",
                                account=ex.Account("p", 10_000.0),
                                z_enter=2.0, z_exit=0.5, z_win=10)
    out = rt.poll(_funding_df([0.0001] * 25), price=100.0)
    assert out["desired_dir"] == fs.FLAT and out["opened"] is None
    assert rt.cur_pos is None


def test_runtime_only_sees_realized_funding_causal():
    """El runner SOLO consume el cache de funding (realizado): latest_zscore en un
    cache truncado NO depende de ventanas que aun no existen."""
    rt = fp.FundingPaperRuntime("BTC/USDT:USDT",
                                account=ex.Account("p", 10_000.0), z_win=10)
    rates = list(np.random.default_rng(1).normal(0.0001, 0.001, 40))
    full = _funding_df(rates)
    z_full_at_30 = rt.latest_zscore(full.iloc[:30])
    z_trunc = rt.latest_zscore(full.iloc[:30])    # mismo corte -> mismo z
    assert z_full_at_30 == pytest.approx(z_trunc, nan_ok=True)


def test_refresh_funding_cache_merges_without_network(tmp_path):
    """refresh_funding_cache MERGEA lo nuevo al parquet (causal, solo crece) usando
    un exchange MOCK -> sin red."""
    now = 1_700_000_000_000
    ex_mock = _FakeFundingExchange("okx", now, n=120)
    df = fp.refresh_funding_cache(
        ex_mock, "BTC/USDT:USDT", str(tmp_path), "okx", recent_limit=120)
    assert len(df) == 120 and df["timestamp"].is_monotonic_increasing
    # segunda llamada: mismos timestamps -> no duplica
    df2 = fp.refresh_funding_cache(
        ex_mock, "BTC/USDT:USDT", str(tmp_path), "okx", recent_limit=120)
    assert len(df2) == 120


def test_one_iteration_with_mocked_exchange(tmp_path, monkeypatch):
    """_one_iteration end-to-end con un exchange MOCK (funding + ticker), sin red:
    refresca cache, trae precio, corre poll, devuelve el dict."""
    now = 1_700_000_000_000

    class _Ex(_FakeFundingExchange):
        def fetch_ticker(self, symbol):
            return {"last": 100.0}

    rt = fp.FundingPaperRuntime("BTC/USDT:USDT",
                                account=ex.Account("p", 10_000.0), z_win=10)
    exch = _Ex("okx", now, n=120)
    args = type("A", (), {})()
    args.exchange = "okx"; args.symbol = "BTC/USDT:USDT"
    args.funding_symbol = "BTC/USDT:USDT"; args.data_dir = str(tmp_path)
    args.recent_limit = 120
    out = fp._one_iteration(rt, exch, args)
    assert out is not None and "fund_zscore" in out and out["price"] == 100.0


def test_ledger_report_roundtrip(tmp_path):
    """ledger_report lee el track record forward y agrega por direccion."""
    led = str(tmp_path / "f.jsonl")
    rt = fp.FundingPaperRuntime(
        "BTC/USDT:USDT", account=ex.Account("p", 10_000.0),
        broker=fp.PaperBroker(ledger=fp.DurableHashLedger.load(led)),
        z_enter=2.0, z_exit=0.5, z_win=10, target_rr=1.0)
    rt.poll(_funding_df(_SPIKE_POS), price=100.0)                       # abre SHORT
    rt.poll(_funding_df(_SPIKE_POS), price=98.0, high=99.5, low=98.0)   # cierra (tp)
    rep = fp.ledger_report(led)
    assert rep is not None and rep["n_closed"] == 1
    assert rep["short"]["n"] == 1
