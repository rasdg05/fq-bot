# -*- coding: utf-8 -*-
"""
E8 — el bruto del cube no vuelve a salir solo.

El mismo motor da +0.224R bruto sobre 7 anos de cosecha y -0.510R vivo con fees.
El coste de ejecucion no muerde el edge: se lo come entero. Y sin embargo el
+0.224R circulo meses como si fuera "el edge", porque el cube etiqueta pre-coste
y nadie le ponia el neto al lado.

La invariante que fija este archivo: **ninguna cifra del cube se resume sin
net_pnl_r**. `cell_stats` levanta GrossWithoutNetError, y las tres secciones del
informe pasan por ella. Si alguien anade una cuarta que imprima `pnl_r` a pelo,
estos tests no la ven — por eso el guardian esta en el formateador comun y no en
cada seccion.
"""
import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

from bt_engine import CostModel
from tools import cube_report as cr


def _cube(n=60, stop_frac=0.005, symbol="SOL_USDT"):
    """Cubo minimo con la forma real: largo (evento x tp x horizonte)."""
    rows = []
    for i in range(n):
        entry = 100.0
        stop = entry * (1 - stop_frac)
        win = i % 3 == 0
        for tp in ("tp1", "tp4"):
            for h in (96, 288):
                rows.append({
                    "symbol": symbol,
                    "entry_index": i,
                    "entry_ts": pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i),
                    "entry_price": entry,
                    "stop_price": stop,
                    "exit_price": entry * (1 + 2 * stop_frac) if win else stop,
                    "direction": 1,
                    "bars_held": 10,
                    "outcome": "win" if win else "loss",
                    "pnl_r": 2.0 if win else -1.0,
                    "tp": tp, "horizon": h,
                    "p_master": 1.0 + (i % 5) * 0.5,
                    "field_killzone": "london_open_kz" if i % 2 else "asia_kz",
                    "mfe_r": 2.5, "mae_r": -1.0,
                })
    return pd.DataFrame(rows)


# --- el puente existe y va en la direccion correcta -------------------------

def test_apply_costs_anade_el_neto_y_es_peor_que_el_bruto():
    t = cr.apply_costs(cr.cell_events(_cube(), tp="tp4", horizon=288))
    assert "net_pnl_r" in t.columns
    assert t.net_pnl_r.mean() < t.pnl_r.mean()


def test_el_coste_en_R_escala_con_lo_estrecho_del_stop():
    """El mecanismo del hallazgo: el fee es sobre NOTIONAL y la R es la distancia
    al stop, asi que el coste en R ~ fee/(stop/precio). Doblar el stop parte el
    coste en R por dos. Es por esto que un motor de 5m con stops del 0.5% paga
    ~0.25R por trade y uno de swing no lo nota."""
    def coste(frac):
        t = cr.apply_costs(cr.cell_events(_cube(stop_frac=frac), tp="tp4", horizon=288))
        return t.pnl_r.mean() - t.net_pnl_r.mean()
    estrecho, ancho = coste(0.005), coste(0.010)
    assert estrecho > ancho > 0
    assert ancho == pytest.approx(estrecho / 2.0, rel=0.15)


def test_el_neto_por_trade_no_depende_del_capital():
    """net_pnl_r mide expectancy, no una curva: si cambiara con el equity, la
    tabla estaria leyendo compounding y no coste."""
    ev = cr.cell_events(_cube(), tp="tp4", horizon=288)
    import bt_engine
    a = bt_engine.simulate(ev.assign(direction=1), equity0=1e6, risk_frac=1e-6,
                           bar_minutes=5.0, cost=CostModel(), stop_on_ruin=False)
    b = bt_engine.simulate(ev.assign(direction=1), equity0=1e9, risk_frac=1e-6,
                           bar_minutes=5.0, cost=CostModel(), stop_on_ruin=False)
    assert a["trades"].net_pnl_r.mean() == pytest.approx(
        b["trades"].net_pnl_r.mean(), rel=1e-6)


def test_sin_costes_el_neto_iguala_al_bruto():
    """Control: con fees, slippage y funding en cero el puente es la identidad.
    Si esto fallara, el 'coste' medido incluiria un bug del adaptador."""
    free = CostModel(taker_fee=0.0, maker_fee=0.0, slippage_bps=0.0,
                     apply_funding=False)
    t = cr.apply_costs(cr.cell_events(_cube(), tp="tp4", horizon=288), cost=free)
    assert t.net_pnl_r.mean() == pytest.approx(t.pnl_r.mean(), abs=1e-9)


# --- LA invariante: el bruto no se imprime solo -----------------------------

def test_resumir_sin_costes_levanta():
    with pytest.raises(cr.GrossWithoutNetError):
        cr.cell_stats(cr.cell_events(_cube(), tp="tp4", horizon=288))


@pytest.mark.parametrize("seccion", ["fixed_cells", "veto_mine", "conviction"])
def test_ninguna_seccion_del_informe_imprime_bruto_a_pelo(seccion):
    """Es la regresion que importa: el +0.224R no puede volver a salir sin su
    neto al lado, por olvido de nadie."""
    with pytest.raises(cr.GrossWithoutNetError):
        getattr(cr, seccion)(_cube())


def test_con_costes_las_secciones_corren_y_muestran_los_dos(capsys):
    c = cr.apply_costs(_cube())
    cr.fixed_cells(c)
    out = capsys.readouterr().out
    assert "NET" in out and "exp=" in out


def test_el_formateador_comun_lleva_los_dos_numeros():
    c = cr.apply_costs(_cube())
    assert "NET" in cr._b(c)


# --- el subconjunto ganador es el maximo del ruido mientras no pase el gate --

def test_el_puente_declara_que_ningun_subconjunto_clarea(capsys):
    t = cr.apply_costs(cr.cell_events(_cube(n=120), tp="tp4", horizon=288))
    cr.net_bridge(t)
    out = capsys.readouterr().out
    assert "PUENTE BRUTO -> NETO" in out
    assert "NINGUN subconjunto clarea el gate" in out
    assert "COTA SUPERIOR" in out          # no es una simulacion, y lo dice


def test_el_puente_cuenta_los_cortes_como_n_trials(capsys):
    """Mirar 28 subconjuntos y quedarse con el mejor es justo lo que el DSR
    deflacta. Si el informe no publicara el conteo, el lector no sabria contra
    que vara se esta midiendo."""
    t = cr.apply_costs(cr.cell_events(_cube(n=120), tp="tp4", horizon=288))
    cr.net_bridge(t)
    assert "n_trials=" in capsys.readouterr().out


def test_el_puente_reporta_cuantas_sobreviven(capsys):
    t = cr.apply_costs(cr.cell_events(_cube(n=120), tp="tp4", horizon=288))
    cr.net_bridge(t)
    assert "sobreviven costes" in capsys.readouterr().out


# --- carga: una senal es una senal ------------------------------------------

def test_cell_events_deduplica_por_simbolo_y_ts(tmp_path):
    a, b = _cube(n=10, symbol="SOL_USDT"), _cube(n=10, symbol="BTC_USDT")
    a.to_parquet(tmp_path / "tp_cube_SOL_USDT.parquet")
    b.to_parquet(tmp_path / "tp_cube_BTC_USDT.parquet")
    c = cr.load_pool(str(tmp_path))
    assert len(cr.cell_events(c, tp="tp4", horizon=288)) == 20   # no 20x2x2
