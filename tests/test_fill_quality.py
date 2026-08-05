# -*- coding: utf-8 -*-
"""
CALIDAD DE FILL — la medición que decide si esto es viable, y sus dos trampas.

E8 midió que con entrada maker el signo se voltea (+0.060R, IC95% por encima de
cero) bajo un supuesto que el repo ya sabe falso: fill del 100%. Esta medición
sustituye el supuesto por el dato.

Dos regresiones, las dos vividas al construirla:

1. LA UNIDAD DEL TIMESTAMP. El cube trae `entry_ts` como datetime64[ms], y sobre
   esa dtype `.astype("int64")` YA devuelve milisegundos. Dividir otra vez por
   1e6 alineó CERO señales — y el fallo es silencioso: no lanza, solo devuelve
   un dataset vacío que parece "no hay datos".

2. EL VENUE. Los cubos son de OKX; OKX bloquea desde datacenter, así que las
   velas vienen de Binance. Un desajuste entre venues cae justo en la escala que
   esto mide (eps = 1 bp). El gate de venue tiene que RECHAZAR velas que no
   reproduzcan la excursión del cube, no seguir adelante con una nota al pie: un
   fill rate calculado sobre datos que no casan parecería una respuesta.
"""
import numpy as np
import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

from tools import fill_quality as fq


def _klines(n=200, base=100.0, ts0=1_600_000_000_000):
    """Velas 5m planas, para inyectar el movimiento que cada test necesita."""
    return pd.DataFrame({
        "ts": ts0 + np.arange(n) * fq.BAR_MS,
        "high": np.full(n, base),
        "low": np.full(n, base),
        "close": np.full(n, base),
    })


def _events(ts_list, entry=100.0, stop=99.0, direction=1, pnl=1.0,
            mfe=2.0, mae=-0.5):
    return pd.DataFrame({
        "entry_ts": pd.to_datetime(pd.Series(ts_list, dtype="int64"),
                                   unit="ms").astype("datetime64[ms]"),
        "entry_price": entry, "stop_price": stop, "direction": direction,
        "pnl_r": pnl, "mfe_r": mfe, "mae_r": mae,
        "exit_price": entry, "bars_held": 10, "outcome": "win",
    })


# --- 1. la unidad del timestamp --------------------------------------------

def test_alinea_un_cube_en_milisegundos():
    """LA regresión: con datetime64[ms], astype('int64') ya da ms. Dividir por
    1e6 alineaba 0 señales y el informe decía 'sin datos' en vez de 'bug'."""
    kl = _klines()
    ts = kl["ts"].iloc[10]
    pos = fq.align(_events([ts]), kl)
    assert pos.tolist() == [10]


def test_alinea_igual_si_el_cube_viene_en_nanosegundos():
    """La conversión no puede depender de la unidad con la que se guardó el
    parquet — otro harness puede escribirlo en ns."""
    kl = _klines()
    ts = int(kl["ts"].iloc[7])
    ev = _events([ts])
    ev["entry_ts"] = ev["entry_ts"].astype("datetime64[ns]")
    assert fq.align(ev, kl).tolist() == [7]


def test_una_senal_sin_vela_se_marca_menos_uno():
    """Ausente no es 'la vela 0'. Un fallback silencioso mediría el fill de otro
    momento del mercado."""
    kl = _klines()
    fuera = int(kl["ts"].iloc[-1]) + 7 * fq.BAR_MS
    assert fq.align(_events([fuera]), kl).tolist() == [-1]


# --- 2. el gate de venue ----------------------------------------------------

def _venue_case(n=60, ruido=0.0):
    """n señales en velas distintas, cada una con su propia excursión.

    La dispersión es el punto: sin ella no hay nada que correlacionar. `ruido`
    desplaza las velas locales respecto a lo que dice el cube, para simular un
    venue que cuenta otra historia.
    """
    kl = _klines(n=6 * n + 40)
    ts, mfes, maes = [], [], []
    for i in range(n):
        p = 5 + 6 * i
        alto = 1.0 + (i % 7) * 0.5                 # +1.0R .. +4.0R
        bajo = 0.2 + (i % 5) * 0.3                 # -0.2R .. -1.4R
        kl.loc[p + 1:p + 4, "high"] = 100.0 + alto
        kl.loc[p + 1:p + 4, "low"] = 100.0 - bajo
        ts.append(int(kl["ts"].iloc[p]))
        mfes.append(alto + ruido)
        maes.append(-bajo - ruido)
    ev = _events(ts)
    ev["mfe_r"], ev["mae_r"] = mfes, maes
    return kl, ev


def test_el_gate_acepta_velas_que_reproducen_la_excursion():
    kl, ev = _venue_case()
    pos = fq.align(ev, kl)
    mfe, mae = fq.recompute_excursion(ev, kl, pos, horizon=6)
    ok, rep = fq.validate_venue(ev, mfe, mae)
    assert ok, rep
    assert rep["corr_mfe"] > 0.99
    assert rep["med_abs_dif_mfe"] < 0.1


def test_el_gate_rechaza_una_serie_sin_dispersion():
    """corr sobre una constante es NaN. El gate ya fallaría cerrado por la
    comparación, pero tiene que decir el motivo en vez de enseñar un NaN."""
    kl = _klines()
    kl.loc[6:12, "high"] = 102.0
    kl.loc[6:12, "low"] = 99.5
    ev = _events([int(kl["ts"].iloc[5])] * 40, mfe=2.0, mae=-0.5)
    pos = fq.align(ev, kl)
    mfe, mae = fq.recompute_excursion(ev, kl, pos, horizon=12)
    ok, rep = fq.validate_venue(ev, mfe, mae)
    assert not ok and "dispersion" in rep["motivo"]


def test_el_gate_RECHAZA_velas_de_otro_mercado():
    """Si las velas locales cuentan otra historia, no se mide: un fill rate
    sobre datos que no casan parecería una respuesta."""
    # Hay dispersión (si no, saltaría el otro guardia): lo que falla es que las
    # velas locales dicen sistemáticamente otra cosa que el cube.
    kl, ev = _venue_case(ruido=3.0)
    pos = fq.align(ev, kl)
    mfe, mae = fq.recompute_excursion(ev, kl, pos, horizon=6)
    ok, rep = fq.validate_venue(ev, mfe, mae)
    assert not ok
    assert "no reproducen" in rep["motivo"]


def test_el_gate_rechaza_una_muestra_alineada_ridicula():
    kl = _klines()
    ev = _events([int(kl["ts"].iloc[3])] * 5)
    pos = fq.align(ev, kl)
    mfe, mae = fq.recompute_excursion(ev, kl, pos, horizon=12)
    ok, rep = fq.validate_venue(ev, mfe, mae)
    assert not ok and "alineadas" in rep["motivo"]


def test_la_excursion_recomputada_respeta_el_lado():
    """En un short, 'favorable' es que BAJE. Invertir el signo aquí haría pasar
    el gate justo cuando los datos son incomparables."""
    kl = _klines()
    kl.loc[6:12, "low"] = 98.0            # short: +2R a favor sobre riesgo 1.0
    kl.loc[6:12, "high"] = 100.5          # -0.5R en contra
    ev = _events([int(kl["ts"].iloc[5])], entry=100.0, stop=101.0, direction=-1)
    pos = fq.align(ev, kl)
    mfe, mae = fq.recompute_excursion(ev, kl, pos, horizon=12)
    assert mfe[0] == pytest.approx(2.0, abs=0.01)
    assert mae[0] == pytest.approx(-0.5, abs=0.01)


# --- 3. la regla de fill: penetrar, no tocar --------------------------------

def test_un_toque_exacto_NO_llena():
    """La orden en la cola no se llena porque el precio bese el nivel. Aceptar
    el toque infla el fill rate justo donde vive la selección adversa."""
    kl = _klines()
    kl.loc[6, "low"] = 100.0              # toca exacto, no penetra
    ev = _events([int(kl["ts"].iloc[5])])
    pos = fq.align(ev, kl)
    lleno, _ = fq.measure_fills(ev, kl, pos, eps=1e-4, ttl_bars=6)
    assert not lleno[0]


def test_penetrar_mas_alla_de_eps_si_llena():
    kl = _klines()
    kl.loc[6, "low"] = 99.5
    ev = _events([int(kl["ts"].iloc[5])])
    pos = fq.align(ev, kl)
    lleno, espera = fq.measure_fills(ev, kl, pos, eps=1e-4, ttl_bars=6)
    assert lleno[0] and espera[0] == 1


def test_fuera_del_TTL_no_llena():
    kl = _klines()
    kl.loc[20, "low"] = 99.0              # penetra, pero mucho después
    ev = _events([int(kl["ts"].iloc[5])])
    pos = fq.align(ev, kl)
    lleno, _ = fq.measure_fills(ev, kl, pos, eps=1e-4, ttl_bars=6)
    assert not lleno[0]


def test_las_barras_de_espera_cuentan_desde_la_vela_siguiente():
    """Una límite no se llena en su propia vela. Contar desde 0 movería todo el
    corte por barras de espera una posición."""
    kl = _klines()
    kl.loc[8, "low"] = 99.0
    ev = _events([int(kl["ts"].iloc[5])])
    pos = fq.align(ev, kl)
    lleno, espera = fq.measure_fills(ev, kl, pos, eps=1e-4, ttl_bars=6)
    assert lleno[0] and espera[0] == 3


def test_el_short_se_llena_por_arriba():
    kl = _klines()
    kl.loc[6, "high"] = 100.5
    ev = _events([int(kl["ts"].iloc[5])], entry=100.0, stop=101.0, direction=-1)
    pos = fq.align(ev, kl)
    lleno, espera = fq.measure_fills(ev, kl, pos, eps=1e-4, ttl_bars=6)
    assert lleno[0] and espera[0] == 1


def test_la_regla_de_fill_es_la_MISMA_del_backtest():
    """Si la regla viviera dos veces, forward y backtest podrían divergir sin
    que nadie lo notara. measure_fills delega en bt_engine."""
    import inspect
    src = inspect.getsource(fq.measure_fills)
    assert "maker_entry_fill_mask" in src


# --- 4. el informe no concluye con muestra chica ----------------------------

def test_el_informe_marca_los_buckets_flacos(capsys):
    n = 10
    ev = _events([1_600_000_000_000] * n)
    ev = ev.assign(net_pnl_r=0.1)
    fq.report(ev, np.ones(n, bool), np.ones(n, int), eps=1e-4, ttl_bars=6)
    assert "n<%d" % fq.MIN_N in capsys.readouterr().out


def test_el_informe_declara_la_seleccion_adversa(capsys):
    """Llenadas peores que escapadas -> tiene que decirlo con esas palabras."""
    n = 200
    ev = _events([1_600_000_000_000] * n)
    ev["pnl_r"] = np.r_[np.full(n // 2, -1.0), np.full(n // 2, 2.0)]
    lleno = np.r_[np.ones(n // 2, bool), np.zeros(n // 2, bool)]
    fq.report(ev.assign(net_pnl_r=ev.pnl_r), lleno, np.ones(n, int),
              eps=1e-4, ttl_bars=6)
    assert "SELECCION ADVERSA CONFIRMADA" in capsys.readouterr().out.replace("Ó", "O")


# --- 5. el juez del gate de produccion --------------------------------------

def test_el_informe_avisa_si_el_gate_empeora_el_neto():
    """FQ_MOTOR_MIN_FILL_BARS=2 está ON en producción y descarta los fills de 1
    barra por un hallazgo de n=53. Si sobre n grande el gate empeora el neto, el
    informe tiene que decirlo — y decir que es orden de REMEDIR, no de apagar."""
    import io, contextlib
    n = 400
    ev = _events([1_600_000_000_000] * n)
    espera = np.r_[np.ones(n // 2, int), np.full(n - n // 2, 3)]
    ev["net_pnl_r"] = np.r_[np.full(n // 2, 0.10), np.full(n - n // 2, -0.30)]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fq.report(ev, np.ones(n, bool), espera, eps=1e-4, ttl_bars=6)
    out = buf.getvalue()
    assert "El gate EMPEORA el neto" in out
    assert "remedirlo" in out


def test_el_informe_no_avisa_si_el_gate_ayuda():
    import io, contextlib
    n = 400
    ev = _events([1_600_000_000_000] * n)
    espera = np.r_[np.ones(n // 2, int), np.full(n - n // 2, 3)]
    ev["net_pnl_r"] = np.r_[np.full(n // 2, -0.30), np.full(n - n // 2, 0.10)]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fq.report(ev, np.ones(n, bool), espera, eps=1e-4, ttl_bars=6)
    assert "El gate EMPEORA el neto" not in buf.getvalue()


# --- 6. la cola (V2) --------------------------------------------------------

def _con_procedencia(ev, p):
    """Filas como salen de `simulate` con la pierna maker MODELADA."""
    import bt_engine as eng
    return ev.assign(fill_p=p, fill_model=eng.FILL_MODELED)


def test_la_rejilla_de_cola_empieza_en_la_binaria():
    """queue_frac=0 no es un caso raro: es `maker_entry_fill_mask` exacta. Si
    dejara de serlo, la tabla del informe compararía dos modelos distintos en
    la misma columna sin avisar."""
    kl = _klines()
    kl["volume"] = 1_000.0
    kl["taker_buy_base"] = 500.0
    kl.loc[7, "low"] = 99.0
    ev = _events([int(kl["ts"].iloc[5])])
    pos = fq.align(ev, kl)
    probs = fq.queue_probabilities(ev, kl, pos, eps=1e-4, ttl_bars=6,
                                   grid=(0.0, 1.0))
    lleno, _ = fq.measure_fills(ev, kl, pos, eps=1e-4, ttl_bars=6)
    assert probs[0.0].tolist() == lleno.astype(float).tolist()
    assert 0.0 <= probs[1.0][0] <= probs[0.0][0]


def test_una_senal_sin_velas_no_tiene_probabilidad():
    """pos < 0 (no alineada) -> p=0, no un número inventado."""
    kl = _klines()
    kl["volume"] = 1_000.0
    ev = _events([1])                      # timestamp fuera de las velas
    pos = fq.align(ev, kl)
    probs = fq.queue_probabilities(ev, kl, pos, eps=1e-4, ttl_bars=6, grid=(1.0,))
    assert probs[1.0].tolist() == [0.0]


def test_el_informe_de_cola_dice_cuando_la_cola_cobra(capsys):
    """El mecanismo, no solo el número: al retrasar la orden te quedas con las
    señales en las que el precio te ATRAVESÓ, que son las peores. El informe
    tiene que nombrarlo."""
    n = 400
    ev = _events([1_600_000_000_000] * n)
    ev = ev.assign(net_pnl_r=np.r_[np.full(n // 2, 0.5), np.full(n // 2, -0.5)])
    ev = _con_procedencia(ev, 1.0)
    # las perdedoras llenan siempre; las ganadoras, casi nunca -> más cola, peor
    probs = {0.0: np.r_[np.ones(n // 2), np.ones(n // 2)],
             1.0: np.r_[np.full(n // 2, 0.05), np.ones(n // 2)]}
    filas = fq.report_cola(ev, probs)
    out = capsys.readouterr().out
    assert "LA COLA COBRA" in out
    assert filas[0]["expectancy"] > filas[-1]["expectancy"]


def test_el_informe_de_cola_no_publica_un_fill_asumido():
    """LA invariante de V2 en el sitio donde se publica: si las filas vienen del
    techo (fill 100% asumido), la tabla no se imprime — levanta."""
    import bt_engine as eng
    n = 60
    ev = _events([1_600_000_000_000] * n).assign(
        net_pnl_r=0.1, fill_p=1.0, fill_model=eng.FILL_ASSUMED)
    with pytest.raises(eng.MakerFillAssumedError):
        fq.report_cola(ev, {0.0: np.ones(n)})


def test_el_techo_sale_etiquetado_como_techo(capsys):
    """El techo se puede imprimir — es una cota legítima — pero nunca sin decir
    que lo es. La cifra de agosto viajó sin etiqueta y volteó un signo."""
    n = 60
    ev = _events([1_600_000_000_000] * n).assign(net_pnl_r=0.1)
    fq.techo_asumido(ev)
    out = capsys.readouterr().out
    assert "TECHO" in out and "NO publicable" in out


def test_el_informe_prueba_el_mecanismo_no_solo_el_numero(capsys):
    """Una curva que baja podría ser encogimiento de muestra. Lo que la hace un
    mecanismo es que la P(fill) PREDIGA el resultado — y el informe lo mide."""
    n = 400
    ev = _events([1_600_000_000_000] * n)
    ev = ev.assign(net_pnl_r=np.r_[np.full(n // 2, 0.5), np.full(n // 2, -0.5)])
    ev = _con_procedencia(ev, 1.0)
    probs = {0.0: np.ones(n),
             1.0: np.r_[np.full(n // 2, 0.10), np.full(n // 2, 0.95)]}
    corr = fq._gradiente_de_fill(ev, probs)
    out = capsys.readouterr().out
    assert corr < -0.05
    assert "PEOR sale" in out
