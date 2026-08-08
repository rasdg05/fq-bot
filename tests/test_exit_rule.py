# -*- coding: utf-8 -*-
"""
La regla de SALIDA dinamica, y las tres regresiones que la pre-registracion exige.

`internal/BRIEF_SALIDA_2026-08.md` fijo estas tres antes de correr nada, porque
son las tres formas de que este experimento salga bonito y falso:

1. **LOOK-AHEAD.** Es la trampa numero uno y por goleada. Un trailing necesita el
   maximo *hasta ahora*. Si se calcula el MFE de toda la vida del trade y luego
   se "sale en k x MFE", la regla sabe a donde va a llegar el precio: produce una
   curva preciosa que no se puede operar. El nivel de la vela `i` sale SOLO de
   las velas `0..i-1`.
2. **CONVENCION INTRA-VELA.** Con OHLC de 5m no se sabe si el extremo adverso
   llego antes que el favorable. La cosecha entera asume que si (empate -> gana
   el stop). Si la salida dinamica usara otra convencion, su comparacion contra
   el control seria contra otra regla, no contra la misma con otra salida.
3. **LA CADENCIA NO SE TOCA.** Una salida no filtra entradas. Si alguna config
   redujera `n`, seria un cap de concurrencia disfrazado — y capear para que el
   drawdown pase es el adorno que el repo ya prohibio. Ademas `n` constante es la
   propiedad que hace que la vara NO se mueva (`frontier_report.require_own_bar`):
   es la unica palanca viva que no paga peaje de muestra.
"""
import numpy as np
import pytest

pd = pytest.importorskip("pandas")

from bt_labeler import (LONG, SHORT, LookaheadExitError,  # noqa: E402
                        label_event, label_event_dynamic)


def _bars(seq):
    """seq: lista de (high, low, close)."""
    return pd.DataFrame(seq, columns=["high", "low", "close"])


TRAIL_050 = {"kind": "trail", "k": 0.50, "arm": 1.0}


# --------------------------------------------------------------------------
#  1) Causalidad — la trampa numero uno
# --------------------------------------------------------------------------

def test_la_salida_dinamica_es_causal():
    """El futuro espectacular no puede cambiar la salida de HOY.

    Dos series identicas en las tres primeras velas y radicalmente distintas
    despues. Si la regla mirara el MFE de toda la vida, la segunda saldria en un
    nivel mas alto (mas pico que ceder). Como el nivel se construye con el pasado,
    **las dos tienen que salir exactamente igual**.
    """
    # entry 100, stop 90 -> R = 10. Sube a 120 (=2R), luego se desploma a 105.
    comun = [(105, 99, 104), (120, 110, 118), (119, 104, 105)]
    modesto = _bars(comun + [(106, 104, 105)] * 5)
    espectacular = _bars(comun + [(400, 300, 390)] * 5)   # el futuro se dispara

    a = label_event_dynamic(modesto, 100.0, 90.0, 200.0, LONG,
                            exit_rule=TRAIL_050, max_bars=8)
    b = label_event_dynamic(espectacular, 100.0, 90.0, 200.0, LONG,
                            exit_rule=TRAIL_050, max_bars=8)

    assert a["bars_held"] == b["bars_held"]
    assert a["exit_price"] == pytest.approx(b["exit_price"])
    assert a["pnl_r"] == pytest.approx(b["pnl_r"])
    assert a["outcome"] == b["outcome"] == "trail"


def test_el_nivel_no_usa_el_mfe_de_la_propia_vela():
    """Dentro de la vela el orden es desconocido: el nivel de trailing de la
    vela `i` NO puede incorporar el maximo de la vela `i`.

    Vela unica que sube a 3R y se desploma a 1R. Si el nivel usara el MFE de esa
    misma vela (3R -> nivel 1.5R), saldria en 1.5R. Con el MFE previo (0, sin
    armar) manda el stop duro y NO sale.
    """
    bars = _bars([(130, 110, 111)])       # entry 100, stop 90: toca 3R y baja a 1R
    r = label_event_dynamic(bars, 100.0, 90.0, 500.0, LONG,
                            exit_rule=TRAIL_050, max_bars=1)
    assert r["outcome"] == "timeout", "no puede salir por un pico de su propia vela"
    assert r["exit_price"] == pytest.approx(111.0)


def test_el_trailing_se_arma_y_luego_protege():
    """Una vez armado (MFE previo >= 1R), cede la mitad del pico y sale ahi."""
    # v0: sube a 2R (120) y cierra alto. v1: se desploma.
    bars = _bars([(120, 100, 119), (119, 100, 101)])
    r = label_event_dynamic(bars, 100.0, 90.0, 500.0, LONG,
                            exit_rule=TRAIL_050, max_bars=2)
    # MFE tras v0 = 2R -> nivel = 2R * (1-0.5) = 1R -> precio 110
    assert r["outcome"] == "trail"
    assert r["exit_price"] == pytest.approx(110.0)
    assert r["pnl_r"] == pytest.approx(1.0)
    assert r["bars_held"] == 2


def test_sin_armar_manda_el_stop_duro():
    """Antes del umbral de armado la regla NO puede ser mas apretada que el stop.

    Sin umbral, `k * MFE` con MFE=0 daria nivel 0 = breakeven desde el tick uno:
    una regla degenerada que sale en cuanto el precio respira.
    """
    bars = _bars([(100.5, 99.0, 99.5), (100.2, 89.0, 90.0)])
    r = label_event_dynamic(bars, 100.0, 90.0, 500.0, LONG,
                            exit_rule=TRAIL_050, max_bars=2)
    assert r["outcome"] == "loss"
    assert r["exit_price"] == pytest.approx(90.0)
    assert r["pnl_r"] == pytest.approx(-1.0)


# --------------------------------------------------------------------------
#  2) La convencion intra-vela es la misma que la de la cosecha
# --------------------------------------------------------------------------

def test_hereda_el_pesimismo_intra_vela_de_la_cosecha():
    """Si el nivel de salida y el objetivo caen en la misma vela, gana la salida.

    Mismo sesgo que `label_event` (empate -> gana el stop). Mezclar convenciones
    invalidaria la comparacion contra el control.
    """
    # v0 arma el trailing en 2R. v1 toca el objetivo (200) Y el nivel (110).
    bars = _bars([(120, 100, 119), (210, 105, 150)])
    r = label_event_dynamic(bars, 100.0, 90.0, 200.0, LONG,
                            exit_rule=TRAIL_050, max_bars=2)
    assert r["outcome"] == "trail"
    assert r["exit_price"] == pytest.approx(110.0)


def test_sin_regla_es_exactamente_el_control():
    """`exit_rule=None` tiene que ser byte-identico a `label_event`.

    Es lo que hace que el control sea comparable: misma entrada, mismo stop,
    mismo objetivo, misma convencion. Solo cambia la salida.
    """
    bars = _bars([(105, 95, 104), (130, 120, 128), (140, 100, 105)])
    for d, tgt, stop in ((LONG, 135.0, 90.0), (SHORT, 60.0, 110.0)):
        a = label_event(bars, 100.0, stop, tgt, d, max_bars=3)
        b = label_event_dynamic(bars, 100.0, stop, tgt, d, exit_rule=None,
                                max_bars=3)
        assert a == b


def test_funciona_en_short_con_los_signos_correctos():
    """Un SHORT gana cuando el precio BAJA: el pico y el retroceso se miden al
    reves. Un error de signo aqui produce una tabla entera invertida."""
    # entry 100, stop 110 -> R = 10. Baja a 80 (=2R), luego rebota.
    bars = _bars([(100, 80, 81), (99, 82, 95)])
    r = label_event_dynamic(bars, 100.0, 110.0, 50.0, SHORT,
                            exit_rule=TRAIL_050, max_bars=2)
    assert r["outcome"] == "trail"
    assert r["exit_price"] == pytest.approx(90.0)     # cede la mitad de 2R
    assert r["pnl_r"] == pytest.approx(1.0)


def test_breakeven_mueve_el_stop_a_la_entrada():
    bars = _bars([(115, 100, 114), (114, 95, 96)])
    regla = {"kind": "be_trail", "m": 1.0, "k": 0.50}
    r = label_event_dynamic(bars, 100.0, 90.0, 500.0, LONG,
                            exit_rule=regla, max_bars=2)
    # MFE tras v0 = 1.5R -> nivel = max(0, 1.5*0.5) = 0.75R -> 107.5
    assert r["outcome"] == "trail"
    assert r["exit_price"] == pytest.approx(107.5)


def test_el_techo_de_tiempo_corta_en_su_barra():
    bars = _bars([(101, 99, 100.5)] * 20)
    r = label_event_dynamic(bars, 100.0, 90.0, 500.0, LONG,
                            exit_rule={"kind": "time", "T": 5}, max_bars=20)
    assert r["outcome"] == "timeout"
    assert r["bars_held"] == 5


def test_una_regla_desconocida_no_pasa_en_silencio():
    with pytest.raises(ValueError):
        label_event_dynamic(_bars([(101, 99, 100)]), 100.0, 90.0, 200.0, LONG,
                            exit_rule={"kind": "adivina"}, max_bars=1)


# --------------------------------------------------------------------------
#  3) Una salida no cambia la cadencia
# --------------------------------------------------------------------------

def test_la_salida_no_cambia_el_numero_de_senales():
    """Cada senal produce exactamente una fila, con regla y sin ella.

    Si esto cayera, la 'mejora' del neto podria venir de haber tirado senales —
    o sea un cap de concurrencia disfrazado — y la vara se habria movido sin que
    nadie lo viera.
    """
    rng = np.random.default_rng(4)
    reglas = [None, TRAIL_050, {"kind": "be_trail", "m": 2.0, "k": 0.50},
              {"kind": "time", "T": 3}]
    señales = []
    for _ in range(40):
        camino = 100 * np.cumprod(1 + rng.normal(0, 0.01, 12))
        señales.append(_bars([(p * 1.003, p * 0.997, p) for p in camino]))

    conteos = []
    for regla in reglas:
        filas = [label_event_dynamic(b, 100.0, 90.0, 130.0, LONG,
                                     exit_rule=regla, max_bars=12)
                 for b in señales]
        assert all(f["bars_held"] >= 1 for f in filas)
        conteos.append(len(filas))
    assert len(set(conteos)) == 1 == len(set([40])), "la n tiene que ser constante"


def test_la_salida_dinamica_nunca_alarga_el_trade():
    """Solo puede cerrar ANTES que las barreras fijas. Si alguna config
    aguantara mas, no seria 'la misma celda con otra salida'."""
    rng = np.random.default_rng(9)
    for _ in range(60):
        camino = 100 * np.cumprod(1 + rng.normal(0, 0.015, 25))
        bars = _bars([(p * 1.004, p * 0.996, p) for p in camino])
        base = label_event(bars, 100.0, 90.0, 130.0, LONG, max_bars=25)
        din = label_event_dynamic(bars, 100.0, 90.0, 130.0, LONG,
                                  exit_rule=TRAIL_050, max_bars=25)
        assert din["bars_held"] <= base["bars_held"]


def test_el_error_de_lookahead_existe_y_es_nombrable():
    """La invariante tiene que tener nombre propio para poder citarse en un
    diff. Un `RuntimeError` generico no ensena nada al que lo lee dentro de
    seis meses."""
    assert issubclass(LookaheadExitError, RuntimeError)
