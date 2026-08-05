# -*- coding: utf-8 -*-
"""Capacidad (N8.4 + V3).

Lo de siempre: el edge degrada monótono con el capital, C½ llega antes que C0, y
más impacto = menos capacidad. Sin red ni cubo: serie de R sintética.

Y lo que V3 añadió, que es lo que hacía falta para que el número signifique algo:

* **La liquidez se mide, no se supone.** El default de catálogo (3e6 USD/barra)
  estaba 8x por debajo del BTC real. `require_measured` impide publicar con él.
* **La curva no puede depender de `fill_bars`.** Repartir la orden en 1 o en 96
  barras es un detalle de ejecución; bajo la ley raíz con σ escalada a la misma
  ventana que el volumen, la capacidad sale idéntica. Antes escalaba con
  `sqrt(fill_bars)` y elegir la ventana era elegir la respuesta.
* **Una capacidad sobre serie BRUTA es un techo** y solo sale por una puerta que
  la nombre así.
"""
import numpy as np
import pytest

from tools.capacity_analysis import (
    CapacityAssumedError, Liquidity, assumed_liquidity, capacity_curve,
    capital_where_impact_equals, impact_at, require_measured)


def _rs(mean_R=0.10, n=400, seed=0):
    rng = np.random.default_rng(seed)
    return list(rng.normal(mean_R, 1.0, size=n))


def _liq(**kw):
    """Liquidez con pinta de SOL real (medida en 2026-08): 4.3e6 USD/barra 5m,
    σ 35 bps por barra, stop del motor al 0.63% del precio."""
    d = dict(symbol="SOL_USDT", bar_notional=4.3e6, sigma_bar=0.0035,
             stop_frac=0.0063)
    d.update(kw)
    return Liquidity(d.pop("symbol"), d.pop("bar_notional"), d.pop("sigma_bar"),
                     d.pop("stop_frac"), n_bars=500_000,
                     source="velas:kl_hist_SOLUSDT.parquet", **d)


# ---------------------------------------------------------------- N8.4 (base)

def test_edge_degrades_monotonically_with_capital():
    rep = capacity_curve(_rs(), avg_bar_notional=3e6)
    edge = np.asarray(rep["curve"]["edge_r"])
    # a capital chico el edge ~ bruto; a capital grande, menor
    assert edge[0] > edge[-1]
    assert np.all(np.diff(edge) <= 1e-9)            # no-creciente
    assert abs(edge[0] - rep["mean_R_gross"]) < abs(edge[-1] - rep["mean_R_gross"])


def test_half_capacity_before_zero():
    rep = capacity_curve(_rs(mean_R=0.12), avg_bar_notional=3e6)
    assert rep["capital_half"] is not None
    assert rep["capital_zero"] is not None
    assert rep["capital_half"] < rep["capital_zero"]   # mitad antes que cero


def test_more_impact_means_less_capacity():
    soft = capacity_curve(_rs(), impact_coef=40.0, avg_bar_notional=3e6)
    hard = capacity_curve(_rs(), impact_coef=160.0, avg_bar_notional=3e6)
    assert hard["capital_half"] < soft["capital_half"]  # más impacto, antes cae


def test_requires_minimum_series():
    with pytest.raises(ValueError):
        capacity_curve([0.1])


# ------------------------------------------- V3: la ventana no elige el número

def test_capacity_is_invariant_to_fill_bars():
    """La regresión concreta: con σ por barra y liquidez por ventana, pasar de
    `fill_bars=1` a 24 multiplicaba la capacidad por 24 (C0 de $12k a $282k) sin
    que nada lo delatara. `fill_bars` es cómo troceas TU orden, no una propiedad
    del mercado: no puede mover dónde muere el edge."""
    ref = None
    for n in (1, 6, 24, 96):
        rep = capacity_curve(_rs(), liquidity=_liq(), fill_bars=n, basis="neto")
        if ref is None:
            ref = rep
            continue
        assert rep["capital_half"] == pytest.approx(ref["capital_half"], rel=1e-9)
        assert rep["capital_zero"] == pytest.approx(ref["capital_zero"], rel=1e-9)


def test_impact_coef_scales_sigma_to_the_window():
    """El mecanismo de la invariancia, aislado: el coeficiente crece con
    sqrt(ventana) porque la σ de la ventana crece con sqrt(ventana)."""
    liq = _liq()
    assert liq.impact_coef(1.0, 1) == pytest.approx(0.0035 * 1e4)
    assert liq.impact_coef(1.0, 4) == pytest.approx(2.0 * 0.0035 * 1e4)
    assert liq.impact_coef(2.0, 1) == pytest.approx(2.0 * liq.impact_coef(1.0, 1))


# ------------------------------------------------- V3: la invariante de salida

def test_assumed_liquidity_cannot_be_published():
    rep = capacity_curve(_rs(), avg_bar_notional=3e6, basis="neto")
    assert rep["liquidez"]["measured"] is False
    with pytest.raises(CapacityAssumedError):
        require_measured(rep)


def test_measured_liquidity_passes_the_gate():
    rep = capacity_curve(_rs(), liquidity=_liq(), basis="neto")
    assert rep["liquidez"]["measured"] is True
    assert rep["liquidez"]["source"].startswith("velas:")
    assert require_measured(rep) is rep


def test_gross_series_needs_the_ceiling_door():
    """La capacidad de un edge bruto describe un sistema que no existe: el coste
    fijo se lo comió antes de que el tamaño entrara. Se puede pedir, pero hay que
    nombrarlo TECHO al pedirlo."""
    rep = capacity_curve(_rs(), liquidity=_liq(), basis="bruto")
    with pytest.raises(CapacityAssumedError):
        require_measured(rep)
    assert require_measured(rep, allow_ceiling=True) is rep


def test_report_without_provenance_is_refused():
    with pytest.raises(CapacityAssumedError):
        require_measured({"capital_zero": 1e6})


def test_assumed_liquidity_is_marked():
    assert assumed_liquidity().measured is False
    assert _liq().measured is True


# ---------------------------------------------------- V3: lecturas del informe

def test_grid_floor_is_flagged_not_printed_as_a_number():
    """Con un edge diminuto el cruce cae en el primer punto de la rejilla. Eso no
    es "capacidad de $1k": es "por debajo de lo que esta rejilla mide", y hay que
    poder distinguirlo antes de citarlo."""
    rep = capacity_curve(_rs(mean_R=0.0005), liquidity=_liq(), basis="neto")
    assert rep["grid_floor"]["zero"] is True
    ancho = capacity_curve(_rs(mean_R=0.30), liquidity=_liq(), basis="bruto")
    assert ancho["grid_floor"]["zero"] is False


def test_tighter_stop_costs_more_capacity():
    """El hallazgo de V3 que conecta dos medidas viejas: el impacto entra en R
    dividido por la distancia al stop, así que el stop apretado —que este repo ya
    midió que ES el edge (Q1 +0.316R vs Q4 +0.147R, 2026-06-30)— es también lo
    que hace al sistema frágil al tamaño."""
    apretado = capacity_curve(_rs(), liquidity=_liq(stop_frac=0.0063), basis="bruto")
    ancho = capacity_curve(_rs(), liquidity=_liq(stop_frac=0.05), basis="bruto")
    assert ancho["capital_zero"] > apretado["capital_zero"]


def test_impact_at_matches_the_curve():
    """`impact_at` (¿cuánto me cuesta a MI tamaño?) y la curva (¿dónde muere?)
    tienen que ser la misma aritmética, o el informe se contradice consigo mismo."""
    liq = _liq()
    rep = capacity_curve(_rs(mean_R=0.20), liquidity=liq, fill_bars=1,
                         capitals=[1e5], basis="bruto")
    imp = impact_at(1e5, liq, fill_bars=1)
    assert rep["curve"]["participation"][0] == pytest.approx(imp["q"])
    assert rep["curve"]["edge_r"][0] == pytest.approx(
        rep["mean_R_gross"] - imp["slip_r"], rel=1e-9)


def test_frontier_is_where_impact_equals_the_fixed_cost():
    """La frontera entre los dos regímenes: por debajo manda el coste fijo, por
    encima el impacto. En el capital que devuelve, los dos valen lo mismo."""
    liq = _liq()
    c = capital_where_impact_equals(0.25, liq, fill_bars=1)
    assert impact_at(c, liq, fill_bars=1)["slip_r"] == pytest.approx(0.25, rel=1e-6)
    # coste fijo mayor -> hay que crecer más para que el impacto lo alcance
    assert capital_where_impact_equals(0.5, liq, fill_bars=1) > c
    assert capital_where_impact_equals(0.0, liq) is None


# ------------------------------------- V3: el camino VIP entero, sin red

pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")


@pytest.fixture
def mundo(tmp_path):
    """Un cube minimo + sus velas locales, con la misma forma que los reales."""
    cube_dir = tmp_path / "cubes"
    kl_dir = tmp_path / "klines"
    cube_dir.mkdir()
    kl_dir.mkdir()

    ts0 = pd.Timestamp("2024-01-01")
    for sym, precio, vol in (("BTC_USDT", 40000.0, 600.0), ("SOL_USDT", 100.0, 40000.0)):
        filas = []
        for i in range(80):
            d = 1 if i % 2 else -1
            gana = bool(i % 3)
            r = 0.8 if gana else -1.0     # bruto +0.2R: hay capacidad que medir
            # `bt_engine.simulate` recalcula el R de los PRECIOS, no del pnl_r:
            # sin `exit_price` coherente la celda sale vacia y el informe mide
            # un universo de cero senales sin quejarse.
            stop = precio * (1.0 - 0.005 * d)
            exit_px = precio * (1.0 + r * 0.005 * d)
            for tp in ("tp1", "tp4"):
                for h in (96, 288):
                    filas.append({
                        "entry_index": i,
                        "entry_ts": ts0 + pd.Timedelta(minutes=5 * 12 * i),
                        "entry_price": precio, "direction": d,
                        "bars_held": 6, "pnl_r": r,
                        "outcome": "win" if gana else "loss",
                        "stop_price": stop, "exit_price": exit_px,
                        "tp": tp, "horizon": h,
                        "mfe_r": 1.0, "mae_r": -0.5,
                    })
        pd.DataFrame(filas).to_parquet(cube_dir / ("tp_cube_%s.parquet" % sym))

        n = 4000
        rng = np.random.default_rng(7)
        closes = precio * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
        pd.DataFrame({
            "ts": (int(ts0.value // 1_000_000)
                   + np.arange(n) * 5 * 60 * 1000).astype("int64"),
            "open": closes, "high": closes, "low": closes, "close": closes,
            "volume": np.full(n, vol), "taker_buy_base": np.full(n, vol / 2),
        }).to_parquet(kl_dir / ("kl_hist_%sUSDT.parquet" % sym.split("_")[0]))
    return str(cube_dir), str(kl_dir)


def test_vip_capacity_mide_la_liquidez_de_cada_simbolo(mundo):
    """El informe no puede inventarse el mercado: cada simbolo trae su notional
    por barra, su sigma y su stop MEDIDOS, y la fuente dice de que archivo."""
    from tools.capacity_analysis import vip_capacity

    cube_dir, kl_dir = mundo
    rep = vip_capacity(cube_dir, kl_dir, tp="tp4", horizon=288,
                       universe=frozenset({"BTC", "SOL"}))
    assert {f["symbol"] for f in rep["filas"]} == {"BTC_USDT", "SOL_USDT"}
    for f in rep["filas"]:
        q = f["liq"]
        assert q.measured and q.source.startswith("velas:")
        assert q.stop_frac == pytest.approx(0.005, rel=1e-6)   # del cube, no default
        assert q.bar_notional > 0 and q.sigma_bar > 0
    # BTC mueve mas notional por barra -> aguanta mas capital que SOL
    btc, sol = sorted(rep["filas"], key=lambda f: -f["liq"].bar_notional)
    assert btc["liq"].bar_notional > sol["liq"].bar_notional
    assert (btc["curvas"][("bruto", 1.0)]["capital_zero"]
            > sol["curvas"][("bruto", 1.0)]["capital_zero"])


def test_vip_capacity_publica_toda_curva_con_procedencia(mundo):
    """Toda celda del informe pasa la guardia: liquidez medida, y el bruto solo
    por la puerta que lo llama TECHO."""
    from tools.capacity_analysis import vip_capacity

    cube_dir, kl_dir = mundo
    rep = vip_capacity(cube_dir, kl_dir, tp="tp4", horizon=288,
                       universe=frozenset({"BTC", "SOL"}))
    for f in rep["filas"]:
        for (base, _y), c in f["curvas"].items():
            require_measured(c, allow_ceiling=(base == "bruto"))
            if base == "bruto":
                with pytest.raises(CapacityAssumedError):
                    require_measured(c)


def test_vip_capacity_no_se_apoya_en_la_ventana_de_fill(mundo):
    """La invariancia, ya no en la formula sino en el informe entero."""
    from tools.capacity_analysis import vip_capacity

    cube_dir, kl_dir = mundo
    a = vip_capacity(cube_dir, kl_dir, tp="tp4", horizon=288, fill_bars=1,
                     universe=frozenset({"BTC", "SOL"}))
    b = vip_capacity(cube_dir, kl_dir, tp="tp4", horizon=288, fill_bars=24,
                     universe=frozenset({"BTC", "SOL"}))
    for fa, fb in zip(a["filas"], b["filas"]):
        assert (fa["curvas"][("bruto", 1.0)]["capital_zero"]
                == pytest.approx(fb["curvas"][("bruto", 1.0)]["capital_zero"],
                                 rel=1e-9))
        assert fa["c_coste_fijo"] == pytest.approx(fb["c_coste_fijo"], rel=1e-9)


def test_sin_velas_locales_no_hay_capacidad(mundo, tmp_path):
    """El modo de fallo que importa: sin velas, ANTES se contestaba igual con el
    default de catalogo. Ahora se para en seco y dice como conseguirlas."""
    from tools.capacity_analysis import vip_capacity

    cube_dir, _ = mundo
    vacio = tmp_path / "sin_velas"
    vacio.mkdir()
    with pytest.raises(FileNotFoundError, match="fetch_binance_vision_klines"):
        vip_capacity(cube_dir, str(vacio), tp="tp4", horizon=288,
                     universe=frozenset({"BTC", "SOL"}))
