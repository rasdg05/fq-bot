# -*- coding: utf-8 -*-
"""
V1 — "¿Y el VIP? ¿Funciona?" deja de contestarse con una sesión.

El 2026-08-05 se midió el universo exacto del producto sobre el cube y salieron
dos cosas: la selección SOL/BTC/ETH se sostiene sobre 7 años, y la geometría
tp1 que el motor vivo publica tiene el IC95% del neto **entero por debajo de
cero**. Se midió con un script ad-hoc que no quedó en el repo — sin tool, sin
test, sin invariante. Por la regla de la casa eso era una NOTA.

Las regresiones que fija este archivo:

1. **El universo medido es el universo publicado.** Si el informe leyera una
   lista distinta de la que difunde el bot, mediría un producto que no existe —
   y nadie se enteraría, porque los dos números serían correctos por separado.
2. **Una celda no se nombra candidata sin pasar por la cartera.** Es la
   invariante de V1. El barrido de agosto encontró +0.085R por trade con CPCV
   positivo y holdout 8/8 que transfiere, y aquello arruinaba la cuenta: 13.7
   posiciones simultáneas y 71% de drawdown. El R por trade era real y el
   producto imposible. Aquí eso no puede ni imprimirse como hallazgo.
3. **El filtro de cartera corre SIN cap de concurrencia.** Un cap hace pasar
   casi cualquier cosa tirando señales (la ganadora de agosto tiraba el 66%).
   Capear antes de juzgar convierte el filtro en un adorno.
4. **Un IC que cruza cero no es un candidato**, aunque el punto sea positivo.
5. **"No aguanta el drawdown" y "no tiene edge" son diagnósticos distintos** y
   el informe no los confunde: llevan a arreglos opuestos.
"""
import numpy as np
import pytest

pd = pytest.importorskip("pandas")

from tools.vip_report import (                                    # noqa: E402
    DD_MAX, MIN_N, PortfolioGateSkippedError, base_ccy, portfolio_gate,
    require_screened, screen_cell, split_universe, tp_sweep, vip_universe)

T0 = pd.Timestamp("2020-01-01")


def _trades(specs, symbol="BTC_USDT"):
    """specs: lista de (offset_horas, horas_de_vida, net_r)."""
    return pd.DataFrame({
        "symbol": [symbol] * len(specs),
        "entry_ts": [T0 + pd.Timedelta(hours=a) for a, _, _ in specs],
        "t0": [T0 + pd.Timedelta(hours=a) for a, _, _ in specs],
        "t1": [T0 + pd.Timedelta(hours=a + v) for a, v, _ in specs],
        "net_r": [r for _, _, r in specs],
        "pnl_r": [r for _, _, r in specs],
    })


# --- 1. el universo medido es el publicado ---------------------------------

def test_el_universo_sale_de_la_misma_variable_que_el_bot():
    """La regresión que esto impide es silenciosa: dos números correctos por
    separado que describen productos distintos."""
    import fq_bot_v3_2 as bot
    assert {base_ccy(p) for p in bot.VIP_PAIRS} == set(vip_universe())


def test_el_universo_respeta_la_variable_de_entorno():
    assert vip_universe({"FQ_VIP_PAIRS": "BTC, sol ,ETH"}) == {"BTC", "SOL", "ETH"}


def test_el_universo_por_defecto_son_los_tres_del_gate():
    assert vip_universe({}) == {"BTC", "ETH", "SOL"}


@pytest.mark.parametrize("crudo,esperado", [
    ("BTC_USDT", "BTC"), ("BTC/USDT", "BTC"), ("btc", "BTC"), ("SOL_USDT", "SOL")])
def test_los_dos_alfabetos_de_simbolo_normalizan_igual(crudo, esperado):
    """El cube nombra `BTC_USDT` y el bot `BTC/USDT`. Sin normalizar en un solo
    sitio el informe mide un universo vacío por un guion bajo."""
    assert base_ccy(crudo) == esperado


def test_la_particion_deja_el_resto_del_pool_como_control():
    ev = pd.concat([_trades([(0, 1, 1.0)], "BTC_USDT"),
                    _trades([(0, 1, 1.0)], "ADA_USDT")], ignore_index=True)
    dentro, fuera = split_universe(ev, {"BTC"})
    assert list(dentro.symbol) == ["BTC_USDT"]
    assert list(fuera.symbol) == ["ADA_USDT"]


# --- 2. la invariante: sin cartera no hay candidata -------------------------

def _ganadora_de_agosto():
    """Una celda con R por trade excelente y cartera ruinosa.

    Reproduce el MECANISMO, no unos números: 4.000 ganadores pequeños que
    entran y salen de uno en uno (el R por trade sale claramente positivo y su
    IC95% no toca el cero), y 500 posiciones que abren todas a la vez y pierden
    todas a la vez. Es lo que midió el barrido de agosto — "peores días: −26.0R
    en 24 cierres el mismo día" — y lo que un promedio de R por trade no puede
    ver: aislada, cada operación es buena; juntas, se llevan la cuenta.

    Cae en TODA la escalera de riesgo, que es lo que la hace inoperable: a
    riesgo alto arruina, y a riesgo bajo el drawdown sigue por encima de la
    cota porque las 500 pérdidas se suman en el mismo instante.
    """
    ganadores = [(i * 2, 1, +0.2) for i in range(4000)]
    simultaneos = [(8000, 24, -1.0) for _ in range(500)]
    return _trades(ganadores + simultaneos)


def test_un_R_por_trade_excelente_con_cartera_ruinosa_NO_es_candidato():
    """LA regresión de V1, en un caso.

    Si esto saliera como candidato, el filtro de cartera sería decorativo y V1
    no habría arreglado nada: es exactamente la lectura que en agosto dejó
    pasar una celda con CPCV positivo y holdout 8/8 que arruinaba la cuenta.
    """
    f = screen_cell(_ganadora_de_agosto(), label="ganadora-de-agosto")

    assert f["net"] > 0                      # el R por trade es bueno
    assert f["lo"] > 0                       # y su IC95% no toca el cero
    assert f["cartera"] is None              # ...y la cuenta no lo sostiene
    assert f["candidato"] is False           # -> NO se nombra candidata
    assert any("DD" in m or "capital" in m for m in f["motivos"])


def test_una_celda_sana_si_pasa_los_tres_filtros():
    """El test anterior no vale si nada pasa nunca: entonces la invariante sería
    'devuelve siempre False' y no estaría midiendo el filtro."""
    rng = np.random.default_rng(3)
    specs = [(i * 48, 6, float(rng.normal(0.5, 0.5))) for i in range(300)]
    f = screen_cell(_trades(specs), label="sana")
    assert f["candidato"] is True
    assert f["cartera"] is not None
    assert f["motivos"] == []


def test_publicar_una_candidata_sin_cartera_levanta():
    """Capa de runtime, espejo de `cube_report.cell_stats`: el guardia no
    depende de que el que imprime se acuerde de mirar el campo."""
    with pytest.raises(PortfolioGateSkippedError):
        require_screened({"label": "x", "candidato": True, "cartera": None})


def test_lo_que_no_paso_por_el_filtro_no_se_puede_publicar():
    with pytest.raises(PortfolioGateSkippedError):
        require_screened({"label": "x", "net": 0.5})


def test_require_screened_deja_pasar_una_fila_legitima():
    fila = {"label": "x", "candidato": True, "cartera": {"equity_final": 2.0}}
    assert require_screened(fila) is fila


# --- 3. el filtro corre sin cap ciego ---------------------------------------

def test_el_gate_de_cartera_no_usa_cap_de_concurrencia():
    """Con cap, una celda inoperable pasa tirando señales. El gate tiene que
    juzgar la celda tal como sale del motor, no una versión recortada de ella.
    """
    mejor, intentos = portfolio_gate(_ganadora_de_agosto())
    assert mejor is None
    assert all(r["saltadas"] == 0 for r in intentos), (
        "el gate saltó señales -> está capeando la concurrencia")


# --- 4. un IC que cruza cero no concluye ------------------------------------

def test_un_IC_que_cruza_cero_no_es_candidato_aunque_el_punto_sea_positivo():
    rng = np.random.default_rng(9)
    specs = [(i * 48, 6, float(rng.normal(0.02, 1.0))) for i in range(200)]
    f = screen_cell(_trades(specs), label="ruido")
    assert f["candidato"] is False
    assert any("IC95%" in m for m in f["motivos"])


def test_muestra_chica_no_concluye_ni_a_favor():
    f = screen_cell(_trades([(i * 48, 6, 1.0) for i in range(MIN_N - 1)]),
                    label="flaca")
    assert f["candidato"] is False
    assert any("no concluye" in m for m in f["motivos"])


def test_una_celda_vacia_no_revienta_ni_pasa():
    f = screen_cell(_trades([]), label="vacía")
    assert f["n"] == 0 and f["candidato"] is False


# --- 5. falta de edge y exceso de riesgo son diagnósticos distintos ---------

def test_perder_dinero_no_se_reporta_como_problema_de_drawdown():
    """Llevan a arreglos opuestos: uno se arregla bajando el riesgo, el otro no
    se arregla con riesgo. Confundirlos manda el trabajo al sitio equivocado —
    a buscar un mecanismo de concurrencia para una celda que solo pierde."""
    specs = [(i * 48, 6, -0.05) for i in range(300)]
    f = screen_cell(_trades(specs), label="sin-edge")
    motivo = " ".join(f["motivos"])
    assert "falta edge" in motivo
    assert -f["intentos"][-1]["max_drawdown"] < DD_MAX   # el DD estaba DENTRO


def test_un_drawdown_inoperable_se_nombra_por_su_nombre():
    rng = np.random.default_rng(4)
    specs = [(i * 3, 240, float(rng.normal(0.35, 4.0))) for i in range(500)]
    f = screen_cell(_trades(specs), label="dd-alto", risk_fracs=(0.02,))
    if f["intentos"][0]["crece"]:
        assert "no es sostenible" in " ".join(f["motivos"])


# --- 6. el barrido entero, punta a punta -----------------------------------

def _cube_sintetico(net_por_tp):
    """Cube mínimo con las columnas que `cell_events` + `simulate` necesitan."""
    filas = []
    for tp, net in net_por_tp.items():
        for i in range(120):
            entry, stop = 100.0, 99.0
            filas.append({
                "symbol": "BTC_USDT",
                "entry_ts": T0 + pd.Timedelta(hours=i * 48),
                "entry_price": entry, "stop_price": stop,
                "exit_price": entry + net, "direction": 1,
                "bars_held": 12, "pnl_r": net, "outcome": "win",
                "tp": tp, "horizon": 288,
            })
    return pd.DataFrame(filas)


def test_el_barrido_recorre_el_eje_TP_a_horizonte_fijo():
    filas = tp_sweep(_cube_sintetico({"tp1": 0.5, "tp2": 1.0, "tp3": 2.0}),
                     horizon=288, tps=("tp1", "tp2", "tp3"), universe={"BTC"})
    assert [f["label"] for f in filas] == ["tp1/h288", "tp2/h288", "tp3/h288"]
    assert all("candidato" in f for f in filas)


def test_el_barrido_pasa_cada_celda_por_require_screened():
    """`tp_sweep` no puede devolver una fila que no haya pasado el guardia: si
    alguien añade una celda por otra vía, el guardia la para."""
    filas = tp_sweep(_cube_sintetico({"tp1": 1.0}), horizon=288, tps=("tp1",),
                     universe={"BTC"})
    assert require_screened(filas[0]) is filas[0]


def test_el_barrido_ignora_los_simbolos_de_fuera_del_VIP():
    cube = _cube_sintetico({"tp1": 1.0})
    cube.loc[cube.index[:60], "symbol"] = "ADA_USDT"
    filas = tp_sweep(cube, horizon=288, tps=("tp1",), universe={"BTC"})
    assert filas[0]["n"] == 60


# --- 7. un máximo en la esquina se dice, no se lee como óptimo --------------

def test_avisa_si_el_mejor_neto_es_el_ULTIMO_peldaño_probado(capsys):
    """El repo ya trata esto como bandera roja (`geometry_sweep` extendió su
    rejilla hasta kSL=12 justo por esto). Sin el aviso, la tabla se lee como
    "tp4 es el óptimo" cuando lo medido es "tp4 es lo último que hay"."""
    from tools.vip_report import print_sweep
    filas = [{"label": "tp%d/h288" % i, "n": 100, "gross": 0.2, "net": 0.1 * i,
              "lo": -0.1, "hi": 0.3, "wr": 30.0, "conc_media": 1.0,
              "hold_dias": 0.1, "cartera": None, "motivos": ["x"],
              "candidato": False} for i in (1, 2, 3, 4)]
    print_sweep(filas)
    assert "MAXIMO EN LA ESQUINA" in capsys.readouterr().out


def test_no_avisa_de_esquina_si_el_gradiente_gira(capsys):
    from tools.vip_report import print_sweep
    netos = [0.1, 0.3, 0.2, 0.05]
    filas = [{"label": "tp%d/h288" % (i + 1), "n": 100, "gross": 0.2,
              "net": v, "lo": -0.1, "hi": 0.3, "wr": 30.0, "conc_media": 1.0,
              "hold_dias": 0.1, "cartera": None, "motivos": ["x"],
              "candidato": False} for i, v in enumerate(netos)]
    print_sweep(filas)
    assert "MAXIMO EN LA ESQUINA" not in capsys.readouterr().out
