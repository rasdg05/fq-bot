# -*- coding: utf-8 -*-
"""I-7 y el embudo de copiabilidad, fijados como test (sin red).

Por qué existe: el screen de 2026-08-05 sobre el top-100 de Hyperliquid dejó 1
candidata de 100. Ese número solo significa algo si el filtro que lo produjo no
se ablanda por conveniencia más adelante. Estos tests fijan las tres decisiones
que podrían ablandarse en silencio:

  1. el PnL se cuenta NETO de fees (con el signo correcto: fee negativa = rebate),
  2. la frontera de I-7 está en el 50% y una cuenta que pierde NO es "evaluable",
  3. un lote capado produce una COTA INFERIOR de la tasa, nunca una tasa menor
     que la real (que es lo que dejaría pasar a un market maker como copiable).

Si alguno falla, el embudo ya no mide lo que decía medir.
"""
import pytest

from tools import copytrade_screen as cs


# --- 1. neto de fees --------------------------------------------------------

def test_pnl_es_neto_de_fees_con_signo():
    fills = [{"closedPnl": "100", "fee": "2"},     # fee normal -> resta
             {"closedPnl": "50", "fee": "-1"},     # rebate maker -> suma
             {"closedPnl": "0", "fee": "5"}]       # apertura -> no realiza
    assert cs.net_closed_pnls(fills) == [98.0, 51.0]


def test_fills_corruptos_no_tumban_el_screen():
    fills = [{"closedPnl": "no-es-un-numero"}, {"closedPnl": None},
             {"closedPnl": "10", "fee": None}, {}]
    assert cs.net_closed_pnls(fills) == [10.0]


# --- 2. frontera de I-7 -----------------------------------------------------

@pytest.mark.parametrize("pnls,esperado", [
    ([100.0, 5.0, 5.0], True),      # un volado domina -> n=1
    ([10.0, 10.0, 10.0], False),    # repartido -> hay metodo que copiar
    ([50.0, 50.0], False),          # resto exactamente 50% -> NO falla
    ([51.0, 49.0], True),           # resto 49% -> falla
])
def test_frontera_i7(pnls, esperado):
    assert cs.fails_i7(pnls) is esperado


@pytest.mark.parametrize("pnls", [[], [-5.0, 1.0], [-1.0]])
def test_cuenta_perdedora_no_es_evaluable_por_i7(pnls):
    """I-7 mide si el PnL positivo es un volado. Una cuenta que pierde se
    descarta antes, y marcarla como 'pasa I-7' seria un falso aprobado."""
    assert cs.fails_i7(pnls) is None


# --- 3. tasa capada = cota inferior ----------------------------------------

def test_lote_capado_da_cota_inferior_no_tasa_diluida():
    """2000 fills (el tope) en 12h dentro de una ventana de 30d. Dividir por la
    ventana daria ~67/dia y colaria un market maker como 'copiable'; la tasa
    correcta sale del span del propio lote: 4000/dia."""
    capped = [{"time": 0}, {"time": 43200000}] * 1000
    rate, lower_bound = cs.fills_per_day(capped, window_days=30)
    assert lower_bound is True
    assert rate == pytest.approx(4000.0)
    assert cs.classify(capped, 30)["verdict"] == "inalcanzable"


def test_lote_no_capado_se_promedia_sobre_la_ventana():
    rate, lower_bound = cs.fills_per_day([{"time": 0}] * 60, window_days=30)
    assert lower_bound is False
    assert rate == pytest.approx(2.0)


def test_sin_fills_no_inventa_actividad():
    assert cs.fills_per_day([], window_days=30) == (0.0, False)
    assert cs.classify([], 30)["verdict"] == "inactiva"


# --- el embudo entero -------------------------------------------------------

def test_embudo_ordena_los_descartes_por_coste():
    """Una cuenta inalcanzable se descarta por la TASA, sin llegar a mirar su
    PnL — aunque su PnL fuera glorioso. El orden de los filtros importa: el mas
    barato primero."""
    hft = [{"time": i * 100, "closedPnl": "1000", "fee": "0"} for i in range(2000)]
    rec = cs.classify(hft, 30)
    assert rec["verdict"] == "inalcanzable"
    assert "pnl_net" not in rec


def test_candidata_solo_si_pasa_los_tres_filtros():
    buena = [{"time": i, "closedPnl": "10", "fee": "0.1"} for i in range(30)]
    assert cs.classify(buena, 30)["verdict"] == "candidata"


def test_resumen_cuenta_supervivencia():
    s = cs.summarize([{"verdict": "inactiva"}, {"verdict": "inalcanzable"},
                      {"verdict": "falla_I7"}, {"verdict": "candidata"}])
    assert s["n"] == 4
    assert s["candidatas"] == 1
    assert s["tasa_supervivencia"] == pytest.approx(0.25)
