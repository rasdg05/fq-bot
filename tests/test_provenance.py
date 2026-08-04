# -*- coding: utf-8 -*-
"""
E4 — romper un colector invalida SOLO lo que cuelga de él, y lo hace solo.

Hoy la auditabilidad es binaria: una fila cuenta o no cuenta. Pero un número
publicado no depende de filas — depende de mediciones, que dependen de
colectores. Cuando uno se rompe hay que ACORDARSE de qué afirmaciones caen.

Y acordarse es exactamente lo que falló: el repo sabía en julio que la racha de
mayo era un espejismo (GHOST_MAP H1) y siguió publicando WR 60% / +1.84R / PF
7.23 hasta agosto. El fallo no fue de conocimiento sino de cableado.

Este archivo fija el cableado: el audit no solo escribe un flag, CORTA el nodo,
y el corte se propaga hacia abajo sin intervención humana.
"""
import pytest

import ledger_stats as ls
import provenance as pv


@pytest.fixture(autouse=True)
def _limpio():
    pv.reset()
    yield
    pv.reset()


def _rows(n, year="2024"):
    return [{"outcome": "tp1", "pnl_r": 1.0, "minutes_open": 60,
             "ts_closed": "%s-01-0%dT00:00:00" % (year, (i % 9) + 1)}
            for i in range(n)]


# --- el corte se propaga hacia abajo, no hacia los lados --------------------

def test_romper_una_fuente_invalida_lo_que_cuelga():
    assert pv.is_publishable("track_record.publico")[0] is True
    pv.break_node("tracker.outcomes", "cierres imposibles")
    ok, motivos = pv.is_publishable("track_record.publico")
    assert ok is False
    assert "tracker.outcomes" in motivos[0]


def test_el_corte_es_transitivo():
    """track_record cuelga de ledger.signals, que cuelga de tracker.outcomes.
    Romper la raíz tiene que llegar hasta abajo sin declararlo dos veces."""
    pv.break_node("tracker.outcomes", "roto")
    assert "tracker.outcomes" in pv.ancestors("track_record.publico")
    assert pv.is_publishable("track_record.publico")[0] is False


def test_romper_un_nodo_NO_invalida_lo_que_no_cuelga_de_el():
    """La otra mitad de la utilidad: si el corte tumbara todo, se apagaría a la
    primera y dejaría de proteger nada. El CVD caído no invalida el track record
    (el track record no lee CVD)."""
    pv.break_node("colector.cvd", "colector parado")
    assert pv.is_publishable("track_record.publico")[0] is True


def test_el_audit_cuelga_del_motor_y_de_las_senales():
    assert pv.ancestors("audit.veredicto") >= {"ledger.signals", "ledger.motor"}
    pv.break_node("ledger.motor", "hash-chain rota")
    assert pv.is_publishable("audit.veredicto")[0] is False
    assert pv.is_publishable("track_record.publico")[0] is True


def test_curar_el_nodo_devuelve_la_publicacion():
    pv.break_node("tracker.outcomes", "roto")
    pv.heal_node("tracker.outcomes")
    assert pv.is_publishable("track_record.publico")[0] is True


def test_romper_un_nodo_no_declarado_falla_ruidosamente():
    """Un break_node inerte sería peor que ninguno: daría sensación de
    protección sin invalidar nada."""
    with pytest.raises(pv.NodeUnknownError):
        pv.break_node("colector.inventado", "x")


# --- la consecuencia es CALLAR, no publicar con asterisco -------------------

def test_el_track_record_no_sale_si_su_fuente_esta_rota():
    st = ls.window_stats(_rows(40))
    ls.format_expectancy(st)                       # sano: sale
    pv.break_node("tracker.outcomes", "cierres imposibles")
    with pytest.raises(pv.NotPublishableError):
        ls.format_expectancy(st)


def test_el_numero_se_puede_seguir_calculando_aunque_no_se_publique():
    """Calcular no es publicar: el admin necesita ver el número roto para
    arreglarlo. Lo que se corta es la salida al cliente."""
    pv.break_node("tracker.outcomes", "roto")
    st = ls.window_stats(_rows(40))
    assert st["n"] == 40
    assert st["provenance"]["publishable"] is False


# --- cada número nombra las filas y los filtros de los que salió ------------

def test_el_track_record_nombra_sus_filas_y_sus_filtros():
    buenas = _rows(30)
    malas = [{"outcome": "tp4", "pnl_r": 3.0, "minutes_open": 10_326,
              "ts_closed": "2026-05-01T00:00:00"} for _ in range(23)]
    st = ls.window_stats(buenas + malas)
    tr = st["provenance"]
    assert tr["rows_in"] == 53 and tr["rows_out"] == 30
    assert tr["filters"][0]["descartadas"] == 23


def test_la_procedencia_nombra_el_filtro_no_solo_lo_cuenta():
    """'23 filas fuera' no explica nada; 'fuera por vida > horizonte' explica el
    incidente entero."""
    st = ls.window_stats(_rows(30))
    assert "horizonte" in st["provenance"]["filters"][0]["nombre"]


def test_la_procedencia_lista_de_que_cuelga():
    st = ls.window_stats(_rows(30))
    assert "tracker.outcomes" in st["provenance"]["depends_on"]


def test_explain_se_lee_de_un_vistazo():
    st = ls.window_stats(_rows(30) + [{"outcome": "tp4", "pnl_r": 3.0,
                                       "minutes_open": 99_999,
                                       "ts_closed": "2026-05-01T00:00:00"}])
    txt = pv.explain(st["provenance"])
    assert "31 filas leídas -> 30 usadas" in txt
    assert "1 fuera por" in txt


def test_explain_avisa_cuando_no_es_publicable():
    st = ls.window_stats(_rows(30))
    pv.break_node("tracker.outcomes", "cierres imposibles")
    txt = pv.explain(pv.trace("track_record.publico"))
    assert "NO PUBLICABLE" in txt


# --- el lazo entero: el audit corta solo ------------------------------------

def test_un_audit_fallido_corta_el_nodo_sin_intervencion(monkeypatch):
    """LA regresión de julio: el sistema sabía y seguía publicando. Ahora el
    audit que falla deja el track record no publicable por sí mismo."""
    import entropy_cognition as ec

    class _ViewRota:
        def verify(self):
            return False

    monkeypatch.setattr("reconciler.SignalLedgerView",
                        lambda **kw: _ViewRota(), raising=False)
    monkeypatch.setattr("reconciler.extract_closed_r", lambda v: [], raising=False)
    monkeypatch.setattr(ec, "get_closed_rows_for_audit", lambda symbol="SOL": [])

    ec.audit_signal_ledger()
    assert pv.is_publishable("track_record.publico")[0] is False


def test_un_audit_limpio_cura_el_nodo(monkeypatch):
    import entropy_cognition as ec

    class _ViewSana:
        def verify(self):
            return True

    pv.break_node("tracker.outcomes", "de antes")
    monkeypatch.setattr("reconciler.SignalLedgerView",
                        lambda **kw: _ViewSana(), raising=False)
    monkeypatch.setattr("reconciler.extract_closed_r", lambda v: [1.0], raising=False)
    monkeypatch.setattr(ec, "get_closed_rows_for_audit", lambda symbol="SOL": [])

    ec.audit_signal_ledger()
    assert pv.is_publishable("track_record.publico")[0] is True


# --- pequeño y útil, no un motor de grafos ---------------------------------

def test_el_grafo_es_chico_a_proposito():
    """Si esto crece a cuarenta nodos, se está construyendo un framework en vez
    de cerrar un lazo. El brief pedía explícitamente lo contrario."""
    assert len(pv.GRAPH) <= 12
    assert set(pv.CLAIMS) <= set(pv.GRAPH)


def test_toda_afirmacion_publicable_cuelga_de_algo():
    """Una afirmación sin ancestros no se puede invalidar nunca: sería un número
    que ningún fallo de colector puede tumbar, y eso no existe."""
    for claim in pv.CLAIMS:
        assert pv.ancestors(claim), "%s no cuelga de nada" % claim
