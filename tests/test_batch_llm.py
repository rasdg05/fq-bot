# -*- coding: utf-8 -*-
"""
E5 — la mitad de coste para el trabajo que puede esperar, y NADA más.

La Batches API cuesta el 50% a cambio de una ventana de hasta 24 h. Es un
trueque excelente para lo que se genera con horas de antelación, e inaceptable
para lo que gatea una decisión.

La regla que fija este archivo: **una superficie se declara o no se batchea**, y
se falla CERRADO — una superficie desconocida se rechaza. Equivocarse hacia el
lado permisivo no cuesta dinero: cuesta un aviso que llega 24 h tarde.

El caso que más importa es el self-audit. Puede poner `_ledger_health.ok=False`
y suspender el track record; diferirlo un día significa publicar durante ese día
un número que el propio auditor ya no defiende. Es el fallo de julio otra vez,
ahora por ahorrar centavos.
"""
import pytest

import batch_llm as bl


# --- LA invariante: declarada o nada ----------------------------------------

def test_el_audit_no_se_puede_batchear():
    """Suspende el track record. Un lote de 24h publicaría un día entero un
    número que el auditor ya marcó como fallo de medición."""
    with pytest.raises(bl.NotBatchableError) as e:
        bl.assert_batchable("audit")
    assert "track record" in str(e.value)


@pytest.mark.parametrize("surface", sorted(bl.NEVER_BATCH))
def test_ninguna_superficie_critica_se_batchea(surface):
    with pytest.raises(bl.NotBatchableError):
        bl.assert_batchable(surface)


def test_una_superficie_desconocida_falla_cerrado():
    """El default es NO. Si alguien añade una superficie nueva y olvida
    declararla, no se difiere por accidente."""
    with pytest.raises(bl.NotBatchableError) as e:
        bl.assert_batchable("inventada_hoy")
    assert "no esta declarada" in str(e.value)


def test_lo_declarado_si_pasa():
    assert bl.assert_batchable("lectura") is True


def test_toda_superficie_declarada_lleva_su_motivo():
    """Un motivo vacío convierte la lista en decoración: el siguiente que la
    lea no sabrá si puede añadir la suya."""
    for motivo in list(BATCHABLE_VALUES()) + list(bl.NEVER_BATCH.values()):
        assert motivo and len(motivo) > 20


def BATCHABLE_VALUES():
    return bl.BATCHABLE.values()


def test_ninguna_superficie_esta_en_las_dos_listas():
    assert not (set(bl.BATCHABLE) & set(bl.NEVER_BATCH))


# --- dobles del SDK ---------------------------------------------------------

class _Msg:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [type("B", (), {"type": "text", "text": text})()]
        self.stop_reason = stop_reason


class _Res:
    def __init__(self, custom_id, tipo="succeeded", text="ok", stop_reason="end_turn"):
        self.custom_id = custom_id
        self.result = type("R", (), {
            "type": tipo,
            "message": _Msg(text, stop_reason) if tipo == "succeeded" else None,
        })()


class _Batches:
    def __init__(self, results=(), status="ended"):
        self._results = list(results)
        self._status = status
        self.created = None

    def create(self, requests):
        self.created = requests
        return type("B", (), {"id": "msgbatch_test"})()

    def retrieve(self, bid):
        return type("B", (), {
            "processing_status": self._status,
            "request_counts": type("C", (), {
                "succeeded": len(self._results), "errored": 0, "processing": 0})(),
        })()

    def results(self, bid):
        return iter(self._results)


class _Client:
    def __init__(self, batches):
        self.messages = type("M", (), {"batches": batches})()


# --- encolar ----------------------------------------------------------------

def test_submit_rechaza_una_superficie_critica():
    cl = _Client(_Batches())
    with pytest.raises(bl.NotBatchableError):
        bl.submit([("x", "hola")], surface="audit", model="m",
                  max_tokens=100, client=cl)


def test_submit_encola_una_peticion_por_trabajo():
    b = _Batches()
    bid = bl.submit([("a", "p1"), ("b", "p2")], surface="lectura",
                    model="m", max_tokens=100, client=_Client(b))
    assert bid == "msgbatch_test"
    assert len(b.created) == 2
    assert [r["custom_id"] for r in b.created] == ["a", "b"]


def test_el_system_va_cacheado_y_compartido():
    """El descuento de cache se apila sobre el 50% del batch: el system es
    idéntico en todas las peticiones del lote."""
    b = _Batches()
    bl.submit([("a", "p1"), ("b", "p2")], surface="lectura", model="m",
              max_tokens=100, system="SYS", client=_Client(b))
    for r in b.created:
        sys_block = r["params"]["system"][0]
        assert sys_block["cache_control"] == {"type": "ephemeral"}
        assert sys_block["text"] == "SYS"


def test_un_custom_id_duplicado_se_rechaza():
    """Dos trabajos distintos con la misma clave colapsan en uno al recogerlos:
    se perdería contenido en silencio."""
    with pytest.raises(ValueError) as e:
        bl.submit([("a", "p1"), ("a", "p2")], surface="lectura", model="m",
                  max_tokens=100, client=_Client(_Batches()))
    assert "duplicado" in str(e.value)


def test_un_lote_vacio_no_llama_a_la_api():
    b = _Batches()
    assert bl.submit([], surface="lectura", model="m", max_tokens=100,
                     client=_Client(b)) is None
    assert b.created is None


# --- recoger: por custom_id, JAMÁS por posición -----------------------------

def test_los_resultados_se_indexan_por_custom_id_no_por_posicion():
    """La API los devuelve en CUALQUIER orden. Emparejarlos por índice publica
    la lectura del martes el miércoles."""
    b = _Batches([_Res("dia-3", text="tres"),
                  _Res("dia-1", text="uno"),
                  _Res("dia-2", text="dos")])
    ok, fallidos = bl.collect("bid", client=_Client(b))
    assert ok == {"dia-1": "uno", "dia-2": "dos", "dia-3": "tres"}
    assert fallidos == []


@pytest.mark.parametrize("tipo", ["errored", "expired", "canceled"])
def test_un_trabajo_fallido_no_se_convierte_en_texto_vacio(tipo):
    """Un trabajo que expiró no es 'un texto vacío'. Confundirlos publicaría un
    hueco como si fuera contenido."""
    b = _Batches([_Res("a", tipo=tipo), _Res("b", text="bien")])
    ok, fallidos = bl.collect("bid", client=_Client(b))
    assert ok == {"b": "bien"}
    assert fallidos == [("a", tipo)]


def test_una_negativa_del_modelo_cuenta_como_fallo():
    b = _Batches([_Res("a", text="", stop_reason="refusal")])
    ok, fallidos = bl.collect("bid", client=_Client(b))
    assert ok == {} and fallidos == [("a", "refusal")]


def test_un_texto_vacio_cuenta_como_fallo():
    b = _Batches([_Res("a", text="   ")])
    ok, fallidos = bl.collect("bid", client=_Client(b))
    assert ok == {} and fallidos == [("a", "vacio")]


def test_status_devuelve_el_estado_y_los_conteos():
    estado, counts = bl.status("bid", client=_Client(_Batches([_Res("a")])))
    assert estado == "ended"
    assert counts["succeeded"] == 1


# --- dormido por defecto ----------------------------------------------------

def test_off_por_defecto(monkeypatch):
    monkeypatch.delenv("FQ_LLM_BATCH", raising=False)
    assert bl.enabled() is False


def test_el_flag_lo_enciende(monkeypatch):
    monkeypatch.setenv("FQ_LLM_BATCH", "1")
    assert bl.enabled() is True


# --- el alcance medido, no supuesto ----------------------------------------

def test_los_barridos_del_CI_no_llaman_a_la_api():
    """El brief daba por hecho que cross_asset_sweep / ablaciones / walkforward
    pagaban tarifa completa. No la pagan: son numpy/pandas puros. Si algún día
    una tool empieza a llamar a Anthropic, este test lo delata y hay que decidir
    conscientemente si va a batch o no."""
    import glob
    import os
    sospechosas = []
    for path in glob.glob(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "tools", "*.py")):
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        if "anthropic" in src or "claude_integration" in src:
            sospechosas.append(os.path.basename(path))
    assert sospechosas == [], (
        "estas tools ahora llaman a la API: %s. Decide si la superficie es "
        "diferible (BATCHABLE) o no (NEVER_BATCH)." % sospechosas)


# --- el consumidor real: las lecturas programadas ---------------------------

def test_las_lecturas_se_encolan_con_su_dia_como_clave():
    """La rotación de tema es determinista por día del año, así que el tema de
    pasado mañana ya se conoce hoy — eso es lo que la hace precomputable."""
    import public_content_generator as pcg
    b = _Batches()
    bid = pcg.generate_lecturas_batch(days_ahead=3, start_day=100,
                                      client=_Client(b))
    assert bid == "msgbatch_test"
    assert [r["custom_id"] for r in b.created] == [
        "lectura-doy-100", "lectura-doy-101", "lectura-doy-102"]


def test_cada_lectura_del_lote_lleva_su_propio_tema():
    import public_content_generator as pcg
    b = _Batches()
    pcg.generate_lecturas_batch(days_ahead=2, start_day=0, client=_Client(b))
    prompts = [r["params"]["messages"][0]["content"] for r in b.created]
    assert prompts[0] != prompts[1]


def test_recoger_devuelve_titulo_y_cuerpo_por_dia():
    import public_content_generator as pcg
    b = _Batches([_Res("lectura-doy-101", text="cuerpo B"),
                  _Res("lectura-doy-100", text="cuerpo A")])
    out = pcg.collect_lecturas_batch("bid", client=_Client(b))
    assert out[100][1] == "cuerpo A"
    assert out[101][1] == "cuerpo B"
    assert out[100][0] == pcg.pick_topic_for_day(100)["titulo"]


def test_una_lectura_fallida_simplemente_no_esta():
    """No se publica un hueco: el slot cae a la generación en línea, que es el
    comportamiento de siempre."""
    import public_content_generator as pcg
    b = _Batches([_Res("lectura-doy-100", tipo="expired"),
                  _Res("lectura-doy-101", text="ok")])
    out = pcg.collect_lecturas_batch("bid", client=_Client(b))
    assert 100 not in out and 101 in out
