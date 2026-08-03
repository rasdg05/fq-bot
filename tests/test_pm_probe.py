# -*- coding: utf-8 -*-
"""
Recolector de la Fase 0. Todo con cliente inyectado: sin red, sin claves y sin
depender de que py_clob_client_v2 este instalado (la suite del repo no lo trae).
"""
import json

import pytest

from pm import probe

USDC_E = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"


def _mercado(cid="0xabc", daily=50, neg_risk=False, tokens=2, abierto=True,
             max_spread=4.5, min_size=30):
    tks = [{"token_id": f"{cid}-yes", "outcome": "Yes"},
           {"token_id": f"{cid}-no", "outcome": "No"}][:tokens]
    return {
        "condition_id": cid, "market_slug": f"slug-{cid}", "question": "¿Sí o no?",
        "accepting_orders": abierto, "enable_order_book": True,
        "closed": False, "archived": False, "neg_risk": neg_risk,
        "tokens": tks, "minimum_order_size": 5, "minimum_tick_size": 0.01,
        "end_date_iso": "2027-01-01T00:00:00Z",
        "rewards": {"rates": [{"asset_address": USDC_E, "rewards_daily_rate": daily}],
                    "min_size": min_size, "max_spread": max_spread},
    }


class FakeClient:
    def __init__(self, markets):
        self._markets = markets
        self.batches = []

    def get_sampling_markets(self):
        return {"data": self._markets}

    def get_order_books(self, params):
        self.batches.append(len(params))
        return [{"asset_id": p.token_id, "bids": [], "asks": []} for p in params]


class FakeParams:
    def __init__(self, token_id):
        self.token_id = token_id


# ============================================================
# SELECCION
# ============================================================
def test_selecciona_y_ordena_por_pool_diario():
    cli = FakeClient([_mercado("a", daily=5), _mercado("b", daily=200),
                      _mercado("c", daily=50)])
    sel = probe.select_markets(cli, top_n=10)
    assert [m["condition_id"] for m in sel] == ["b", "c", "a"]
    assert sel[0]["yes_token_id"] == "b-yes" and sel[0]["no_token_id"] == "b-no"
    assert sel[0]["max_spread"] == 4.5 and sel[0]["min_size"] == 30


def test_descarta_neg_risk_cerrados_sin_pool_y_sin_max_spread():
    cli = FakeClient([
        _mercado("negrisk", neg_risk=True),
        _mercado("cerrado", abierto=False),
        _mercado("sinpool", daily=0),
        _mercado("sinspread", max_spread=0),
        _mercado("multi", tokens=1),
        _mercado("bueno", daily=10),
    ])
    assert [m["condition_id"] for m in probe.select_markets(cli)] == ["bueno"]


def test_respeta_el_tope_top_n():
    cli = FakeClient([_mercado(f"m{i}", daily=i + 1) for i in range(10)])
    assert len(probe.select_markets(cli, top_n=3)) == 3


def test_ignora_pools_en_otros_tokens():
    m = _mercado("x", daily=99)
    m["rewards"]["rates"] = [{"asset_address": "0xdead", "rewards_daily_rate": 99}]
    assert probe.select_markets(FakeClient([m])) == []


def test_mercado_corrupto_no_tumba_la_seleccion():
    cli = FakeClient([{"condition_id": "roto"}, _mercado("bueno")])
    assert [m["condition_id"] for m in probe.select_markets(cli)] == ["bueno"]


# ============================================================
# LIBROS
# ============================================================
def test_fetch_books_trocea_para_no_reventar_el_endpoint():
    """/books devuelve 400 'Payload exceeds the limit' con lotes grandes."""
    cli = FakeClient([])
    ids = [f"t{i}" for i in range(95)]
    books = probe.fetch_books(cli, ids, chunk=40, book_params=FakeParams)
    assert cli.batches == [40, 40, 15]
    assert len(books) == 95


def test_un_lote_fallido_no_pierde_los_demas():
    class Flaky(FakeClient):
        def get_order_books(self, params):
            self.batches.append(len(params))
            if len(self.batches) == 1:
                raise RuntimeError("502")
            return super().get_order_books(params)

    cli = Flaky([])
    books = probe.fetch_books(cli, [f"t{i}" for i in range(60)], chunk=40,
                              book_params=FakeParams)
    assert len(books) == 20          # se perdio el primer lote, no la muestra


# ============================================================
# SNAPSHOT
# ============================================================
def _libros(mid=0.50, tamano=100):
    """Libro simetrico a 1c del midpoint en los dos tokens."""
    return {
        "x-yes": {"bids": [{"price": mid - 0.01, "size": tamano}],
                  "asks": [{"price": mid + 0.01, "size": tamano}]},
        "x-no": {"bids": [{"price": 1 - mid - 0.01, "size": tamano}],
                 "asks": [{"price": 1 - mid + 0.01, "size": tamano}]},
    }


def test_snapshot_calcula_midpoint_y_puntaje_del_libro():
    m = probe.select_markets(FakeClient([_mercado("x", daily=100)]))
    recs = probe.snapshot(m, _libros(), ts="2026-08-03T00:00:00+00:00")
    assert len(recs) == 1
    r = recs[0]
    assert r["mid"] == pytest.approx(0.50)
    assert r["daily_pool"] == 100
    # Cada lado: bid YES + ask NO a 1c => S(4.5,1)*100 en cada Q.
    from pm import rewards
    esperado = rewards.score_order(4.5, 1.0) * 100 * 2
    assert r["q_one"] == pytest.approx(esperado, abs=0.01)
    assert r["book_q_min"] == pytest.approx(esperado, abs=0.01)


def test_snapshot_registra_el_vigilante_de_arb():
    m = probe.select_markets(FakeClient([_mercado("x")]))
    r = probe.snapshot(m, _libros())[0]
    assert r["ask_sum"] == pytest.approx(1.02)    # 0.51 + 0.51
    assert r["bid_sum"] == pytest.approx(0.98)    # 0.49 + 0.49


def test_snapshot_salta_mercados_sin_libro():
    m = probe.select_markets(FakeClient([_mercado("x")]))
    assert probe.snapshot(m, {}) == []


def test_snapshot_es_serializable():
    m = probe.select_markets(FakeClient([_mercado("x")]))
    linea = json.dumps(probe.snapshot(m, _libros())[0])
    assert json.loads(linea)["condition_id"] == "x"


def test_ordenes_bajo_el_corte_no_cuentan_como_profundidad():
    """min_size = 30: un libro de ordenes de 5 shares no compite por rewards."""
    m = probe.select_markets(FakeClient([_mercado("x", min_size=30)]))
    r = probe.snapshot(m, _libros(tamano=5))[0]
    assert r["book_q_min"] == 0.0
    assert r["qual_bid_shares"] == 0.0
    assert r["mid"] is None          # el midpoint ajustado tambien usa el corte


def test_trim_recorta_a_la_ventana_util():
    niveles = [(0.50, 10), (0.45, 10), (0.30, 10)]
    recortado = probe._trim(niveles, reference=0.50, max_spread_cents=4.5)
    assert recortado == [[0.45, 10.0], [0.5, 10.0]]      # 0.30 queda fuera
