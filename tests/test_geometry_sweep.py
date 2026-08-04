# -*- coding: utf-8 -*-
"""
BARRIDO DE GEOMETRÍA — ¿un stop más ancho diluye el coste fijo lo bastante?

La hipótesis es aritmética: coste_R = (2·fee+2·slip)/(stop/precio), así que
ensanchar el stop lo divide. El contra-argumento también: si se ensancha el
objetivo con él, la asimetría de recorrido se divide por lo mismo, y el ratio
asimetría/coste queda invariante (4.42× para cualquier k).

Lo único que puede romper esa invarianza es que la **resolución por barreras**
no es lineal: un trade que muere en el stop y luego se recupera pasa a ganador
con un stop más ancho. Eso cambia la FORMA de la distribución, no solo su
escala. Este archivo fija que la medición de eso sea fiel.

La regresión que más importa: el neto vectorizado es un ATAJO por velocidad
(~650k filas), y un atajo que se desvíe del modelo de costes real convierte todo
el barrido en ficción. `test_el_neto_vectorizado_coincide_con_simulate` lo ancla
a `bt_engine` fila a fila. Este repo ya vivió el fallo de una regla viviendo en
dos sitios.
"""
import numpy as np
import pytest

pd = pytest.importorskip("pandas")

from bt_engine import CostModel, simulate
from tools import geometry_sweep as gs


def _trades(n=40, seed=3):
    rng = np.random.default_rng(seed)
    entry = 100.0 + rng.normal(0, 5, n)
    d = rng.choice([1, -1], n)
    risk = np.abs(rng.normal(0.6, 0.15, n)) + 0.2
    stop = entry - d * risk
    win = rng.random(n) < 0.4
    exit_px = np.where(win, entry + d * risk * 2.5, stop)
    return pd.DataFrame({
        "direction": d, "entry_price": entry, "stop_price": stop,
        "exit_price": exit_px, "bars_held": rng.integers(1, 400, n),
        "outcome": np.where(win, "win", "loss"),
    })


# --- LA regresión: el atajo no puede divergir del modelo real ---------------

@pytest.mark.parametrize("cost", [
    CostModel(),
    CostModel(maker_entry=True),
    CostModel(maker_entry=True, maker_tp_exit=True),
    CostModel(apply_funding=False),
    CostModel(taker_fee=0.0, maker_fee=0.0, slippage_bps=0.0, apply_funding=False),
])
def test_el_neto_vectorizado_coincide_con_simulate(cost):
    """El barrido usa una versión vectorizada por velocidad. Si se desvía del
    modelo de costes de bt_engine, todo el barrido es ficción."""
    t = _trades()
    ref = simulate(t, equity0=1e9, risk_frac=1e-6, bar_minutes=5.0,
                   cost=cost, stop_on_ruin=False)["trades"]
    mine = gs.net_r_vectorized(t.direction, t.entry_price, t.exit_price,
                               t.stop_price, t.bars_held, t.outcome,
                               cost, bar_minutes=5.0)
    np.testing.assert_allclose(mine, ref["net_pnl_r"].to_numpy(), rtol=1e-9, atol=1e-12)


def test_el_neto_vectorizado_respeta_el_tp_maker_solo_en_ganadores():
    """maker_tp_exit solo aplica al que SALIÓ por objetivo. Aplicarlo a los
    stops regalaría fee maker en la pierna que siempre cruza el book."""
    t = _trades(n=20)
    cost = CostModel(maker_entry=True, maker_tp_exit=True)
    ref = simulate(t, equity0=1e9, risk_frac=1e-6, bar_minutes=5.0,
                   cost=cost, stop_on_ruin=False)["trades"]
    mine = gs.net_r_vectorized(t.direction, t.entry_price, t.exit_price,
                               t.stop_price, t.bars_held, t.outcome, cost)
    np.testing.assert_allclose(mine, ref["net_pnl_r"].to_numpy(), rtol=1e-9)
    assert (t.outcome == "win").any() and (t.outcome == "loss").any()


def test_riesgo_cero_no_produce_un_neto_infinito():
    out = gs.net_r_vectorized([1], [100.0], [101.0], [100.0], [10], ["win"],
                              CostModel())
    assert np.isnan(out[0])


# --- el re-etiquetado usa la MISMA convención que la cosecha ---------------

def _klines(n=100, base=100.0, ts0=1_600_000_000_000):
    return pd.DataFrame({
        "ts": ts0 + np.arange(n) * 300_000,
        "high": np.full(n, base), "low": np.full(n, base),
        "close": np.full(n, base),
    })


def _ev(ts, entry=100.0, stop=99.0, direction=1):
    return pd.DataFrame({
        "entry_ts": pd.to_datetime(pd.Series([ts], dtype="int64"),
                                   unit="ms").astype("datetime64[ms]"),
        "entry_price": [entry], "stop_price": [stop], "direction": [direction],
        "pnl_r": [0.0], "mfe_r": [0.0], "mae_r": [0.0],
    })


def test_un_stop_mas_ancho_salva_al_que_se_recuperaba():
    """EL mecanismo que puede romper la invarianza: con el stop original el
    trade muere; con el doble sobrevive y llega al objetivo."""
    # riesgo original 1.0 -> con k=2 el stop baja a 98.0 y el objetivo a 2R
    # sube a 104.0. Las velas tienen que cubrir el objetivo ANCHO, no el
    # estrecho, o el test mediria un timeout en vez del rescate.
    kl = _klines()
    kl.loc[6, "low"] = 98.5          # perfora el stop original (99.0), no el 98.0
    kl.loc[7:12, "high"] = 105.0     # luego se va mas alla del objetivo ancho
    ev = _ev(int(kl["ts"].iloc[5]))
    pos = gs.align(ev, kl)
    long = gs.relabel(ev, kl, pos, sl_mults=(1.0, 2.0), tp_rs=(2.0,),
                      horizons=(20,))
    estrecho = long[(long.k_sl == 1.0)].iloc[0]
    ancho = long[(long.k_sl == 2.0)].iloc[0]
    assert estrecho["outcome"] == "loss"
    assert ancho["outcome"] == "win"


def test_el_empate_intra_vela_sigue_siendo_pesimista():
    """Misma convención que la cosecha original: si TP y SL caen en la misma
    vela gana el stop. Cambiarla aquí haría el barrido incomparable con el cube."""
    kl = _klines()
    kl.loc[6, "high"] = 103.0
    kl.loc[6, "low"] = 98.0          # ambos en la MISMA vela
    ev = _ev(int(kl["ts"].iloc[5]))
    pos = gs.align(ev, kl)
    long = gs.relabel(ev, kl, pos, sl_mults=(1.0,), tp_rs=(2.0,), horizons=(20,))
    assert long.iloc[0]["outcome"] == "loss"


def test_la_rejilla_emite_una_fila_por_celda():
    kl = _klines()
    kl.loc[6:12, "high"] = 101.0
    ev = _ev(int(kl["ts"].iloc[5]))
    pos = gs.align(ev, kl)
    long = gs.relabel(ev, kl, pos, sl_mults=(1.0, 2.0), tp_rs=(1.0, 3.0),
                      horizons=(20, 40))
    assert len(long) == 2 * 2 * 2
    assert set(long.k_sl) == {1.0, 2.0}


def test_el_riesgo_escala_con_el_multiplicador():
    kl = _klines()
    ev = _ev(int(kl["ts"].iloc[5]), entry=100.0, stop=99.0)
    pos = gs.align(ev, kl)
    long = gs.relabel(ev, kl, pos, sl_mults=(1.0, 3.0), tp_rs=(2.0,), horizons=(20,))
    r = dict(zip(long.k_sl, long.risk))
    assert r[1.0] == pytest.approx(1.0)
    assert r[3.0] == pytest.approx(3.0)


def test_una_senal_sin_velas_suficientes_se_salta():
    kl = _klines(n=8)
    ev = _ev(int(kl["ts"].iloc[7]))       # no quedan barras despues
    pos = gs.align(ev, kl)
    assert len(gs.relabel(ev, kl, pos, sl_mults=(1.0,), tp_rs=(2.0,),
                          horizons=(20,))) == 0


# --- el informe cuenta la rejilla como n_trials ----------------------------

def test_el_informe_deflacta_por_el_tamano_de_la_rejilla(capsys):
    """Mirar 50 geometrías y quedarse con la mejor es lo que el DSR deflacta.
    Sin publicar n_trials, la mejor celda siempre parece un hallazgo."""
    rng = np.random.default_rng(1)
    filas = []
    for k in (1.0, 2.0):
        for t in (1.0, 2.0):
            for i in range(200):
                filas.append((pd.Timestamp("2024-01-01") + pd.Timedelta(minutes=5 * i),
                              1, 100.0, 99.0 - (k - 1), k, k, t, 576,
                              "win" if rng.random() < 0.4 else "loss",
                              50, 100.0 + rng.normal(0, 1), 0.0))
    long = pd.DataFrame(filas, columns=[
        "entry_ts", "direction", "entry_price", "stop_price", "risk", "k_sl",
        "tp_r", "horizon", "outcome", "bars_held", "exit_price", "pnl_r"])
    gs.report(long, CostModel())
    out = capsys.readouterr().out
    assert "n_trials=4" in out
    assert "NINGUNA geometria clarea el gate" in out


# --- E9 aplicado: la celda ganadora no se lee agregada ----------------------

def _grid_frame(net_por_ano, k=2.0, t=3.0, h=576, n_por_ano=200):
    filas = []
    for ano, media in net_por_ano.items():
        for i in range(n_por_ano):
            # exit_price fabricado para que el neto salga cerca de `media`
            filas.append((pd.Timestamp("%d-06-01" % ano) + pd.Timedelta(minutes=5 * i),
                          1, 100.0, 100.0 - k, k, k, t, h, "win", 10,
                          100.0 + media * k + 0.0121, 0.0))
    return pd.DataFrame(filas, columns=[
        "entry_ts", "direction", "entry_price", "stop_price", "risk", "k_sl",
        "tp_r", "horizon", "outcome", "bars_held", "exit_price", "pnl_r"])


def test_el_informe_delata_una_celda_que_reparte_mal(capsys):
    """El neto agregado positivo puede ser dos años buenos tapando dos malos —
    la forma exacta del fantasma. E9 obliga al desglose; aquí decide."""
    long = _grid_frame({2021: 0.30, 2022: 0.30, 2023: -0.25, 2024: -0.20})
    gs.report(long, CostModel())
    out = capsys.readouterr().out
    assert "POR ANO" in out
    assert "REPARTE MAL" in out
    assert "CPCV" in out


def test_el_informe_no_grita_si_todos_los_anos_van_igual(capsys):
    long = _grid_frame({2021: 0.20, 2022: 0.22, 2023: 0.19, 2024: 0.21})
    gs.report(long, CostModel())
    assert "REPARTE MAL" not in capsys.readouterr().out


def test_el_desglose_marca_los_anos_con_muestra_chica(capsys):
    long = pd.concat([_grid_frame({2021: 0.2}, n_por_ano=200),
                      _grid_frame({2022: 0.2}, n_por_ano=5)], ignore_index=True)
    gs.report(long, CostModel())
    assert "no concluye" in capsys.readouterr().out
