# -*- coding: utf-8 -*-
"""
Veredicto de la Fase 0. Lo que se protege aca es que el analisis NO se vuelva
optimista solo: el reparto tiene que respetar el min_size, el piso de pago de
$1/dia y marcar como dudoso lo que sale de dividir entre casi cero.
"""
import gzip
import json

import pytest

from pm import analyze


def _sm(cid="a", pool=100.0, book_q=1000.0, mid=0.5, min_size=30.0,
        max_spread=4.5, zero_frac=0.0, n=200):
    return {"condition_id": cid, "slug": f"slug-{cid}", "question": "", "n": n,
            "daily_pool": pool, "min_size": min_size, "max_spread": max_spread,
            "mid": mid, "book_q_min": book_q, "qual_usd": 0.0, "zero_frac": zero_frac,
            "ask_sum_min": 1.001, "bid_sum_max": 0.999}


# ============================================================
# COSTO DE ENTRADA: no hay media entrada
# ============================================================
def test_costo_de_entrada_es_el_min_size_a_dos_lados():
    """Con min_size 200 no se entra con $25: o entras con ~$200 o no puntuas."""
    assert analyze.entry_cost(_sm(min_size=200), 1.0) == pytest.approx(196.0)
    assert analyze.entry_cost(_sm(min_size=30), 1.0) == pytest.approx(29.4)


def test_reparto_entra_aunque_el_bloque_sea_menor_al_min_size():
    """Bug cazado en el smoke: con bloques de $25 y min_size 200 el reparto
    nunca entraba a ningun mercado y declaraba 'no viable' por construccion."""
    alloc = analyze.allocate([_sm(min_size=200, book_q=5000.0)], bankroll=500.0,
                             spread_cents=1.0)
    assert alloc, "el reparto tiene que poder entrar"
    assert alloc[0]["capital"] >= analyze.entry_cost(_sm(min_size=200), 1.0)
    assert alloc[0]["qualifies"]


def test_reparto_no_entra_si_el_capital_no_alcanza_el_minimo():
    alloc = analyze.allocate([_sm(min_size=1000)], bankroll=100.0, spread_cents=1.0)
    assert alloc == []


def test_reparto_no_excede_el_bankroll():
    mercados = [_sm(f"m{i}", pool=100.0, book_q=500.0) for i in range(5)]
    alloc = analyze.allocate(mercados, bankroll=300.0, spread_cents=1.0)
    assert sum(a["capital"] for a in alloc) <= 300.0


def test_reparto_prefiere_el_libro_mas_flaco():
    """Mismo pool: el mercado con menos competencia paga mas por dolar."""
    flaco = _sm("flaco", pool=100.0, book_q=200.0)
    gordo = _sm("gordo", pool=100.0, book_q=500_000.0)
    alloc = analyze.allocate([gordo, flaco], bankroll=500.0, spread_cents=1.0)
    assert alloc[0]["slug"] == "slug-flaco"
    por_id = {a["slug"]: a["capital"] for a in alloc}
    assert por_id["slug-flaco"] > por_id.get("slug-gordo", 0.0)


def test_reparto_diversifica_cuando_el_primero_satura():
    """Los rewards son concavos: al saturar el mejor mercado, el capital
    siguiente vale mas en el segundo."""
    mercados = [_sm("a", pool=20.0, book_q=100.0), _sm("b", pool=20.0, book_q=100.0)]
    alloc = analyze.allocate(mercados, bankroll=500.0, spread_cents=1.0)
    assert len(alloc) == 2
    caps = sorted(a["capital"] for a in alloc)
    assert caps[0] > 0


# ============================================================
# GUARDARRAILES
# ============================================================
def test_marca_dudoso_el_libro_vacio():
    """Un pool que nadie reclama daria ~100% del pool: eso no se cree."""
    alloc = analyze.allocate([_sm(book_q=0.0, zero_frac=1.0)], bankroll=500.0,
                             spread_cents=1.0)
    assert alloc[0]["suspect"] is True
    assert alloc[0]["est_daily"] == pytest.approx(alloc[0]["daily_pool"])


def test_libro_lleno_no_es_dudoso():
    alloc = analyze.allocate([_sm(book_q=5000.0, zero_frac=0.0)], bankroll=500.0,
                             spread_cents=1.0)
    assert alloc[0]["suspect"] is False


def test_piso_de_pago_de_un_dolar():
    """Debajo de $1/dia la plataforma no paga: el estimado no cuenta."""
    alloc = analyze.allocate([_sm(pool=10.0, book_q=5_000_000.0)], bankroll=500.0,
                             spread_cents=1.0)
    assert alloc[0]["est_daily"] < analyze.MIN_PAYOUT_USD
    assert alloc[0]["paid"] is False


def test_resumen_calcula_la_fraccion_de_muestras_vacias():
    recs = [{"mid": 0.5, "book_q_min": 0.0, "daily_pool": 10, "min_size": 30,
             "max_spread": 4.5, "qual_bid_usd": 0.0},
            {"mid": 0.5, "book_q_min": 100.0, "daily_pool": 10, "min_size": 30,
             "max_spread": 4.5, "qual_bid_usd": 50.0}]
    sm = analyze.summarize_market("a", {}, recs)
    assert sm["zero_frac"] == pytest.approx(0.5)
    assert sm["book_q_min"] == pytest.approx(50.0)      # mediana, no promedio


def test_resumen_usa_mediana_y_no_promedio():
    """Un mercado saturado que se vacia un minuto no es una oportunidad."""
    recs = [{"mid": 0.5, "book_q_min": q, "daily_pool": 10, "min_size": 30,
             "max_spread": 4.5, "qual_bid_usd": 0.0} for q in (1000, 1000, 1000, 1000, 1)]
    sm = analyze.summarize_market("a", {}, recs)
    assert sm["book_q_min"] == 1000.0                   # el promedio daria 800


def test_resumen_none_sin_datos_utiles():
    assert analyze.summarize_market("a", {}, [{"mid": None, "book_q_min": None}]) is None


# ============================================================
# CARGA
# ============================================================
def test_carga_jsonl_plano_y_comprimido(tmp_path):
    meta = {"_meta": "markets", "markets": [{"condition_id": "a", "slug": "s-a",
                                             "question": "q", "daily_pool": 10.0,
                                             "min_size": 30.0, "max_spread": 4.5}]}
    fila = {"ts": "2026-08-03T00:00:00+00:00", "condition_id": "a", "slug": "s-a",
            "daily_pool": 10.0, "min_size": 30.0, "max_spread": 4.5, "mid": 0.5,
            "book_q_min": 100.0, "qual_bid_usd": 50.0, "ask_sum": 1.001, "bid_sum": 0.999}

    plano = tmp_path / "probe_1.jsonl"
    plano.write_text(json.dumps(meta) + "\n" + json.dumps(fila) + "\n", encoding="utf-8")
    with gzip.open(tmp_path / "probe_2.jsonl.gz", "wt", encoding="utf-8") as fh:
        fh.write(json.dumps(fila) + "\n")

    cfg, samples = analyze.load(str(tmp_path / "*.jsonl*"))
    assert cfg["a"]["slug"] == "s-a"
    assert len(samples["a"]) == 2


def test_carga_ignora_lineas_corruptas(tmp_path):
    p = tmp_path / "probe.jsonl"
    p.write_text('{"condition_id": "a"}\n{roto\n\n', encoding="utf-8")
    _, samples = analyze.load(str(p))
    assert len(samples["a"]) == 1
