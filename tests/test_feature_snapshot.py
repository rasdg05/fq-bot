# -*- coding: utf-8 -*-
"""
E1 — el OPEN sella un DATASET, no un log.

MOTOR_OPEN_META llevaba ~10 campos elegidos a mano en 2026-07: sirve para las
preguntas que alguien anticipo entonces y para ninguna otra. Y peor, con una
clave ausente era imposible saber si la feature no existia o si existia y no se
midio -- que es literalmente lo que pasa hoy con `cvd_confirmed`, y son cosas
opuestas: una dice "no preguntes", la otra es un dato sobre el colector.

Las regresiones que este archivo fija:

1. Anadir una feature manana NO puede cambiar lo que significa una fila de ayer.
   Por eso el registro de esquemas es APPEND-ONLY y la ausencia de clave no es la
   fuente de verdad: lo es `SCHEMA[version]`.
2. Una feature constante se DELATA, no se entierra. `vp_basis` estuvo meses en
   'developing' y el ledger lo guardaba fielmente.
3. Con el flag off, el ledger es byte-identico al historico (Constitucion II.1).
"""
import pytest

import feature_snapshot as fs


# --- 1. las tres respuestas que hoy no se pueden distinguir ------------------

def test_feature_que_no_existia_no_se_confunde_con_nula():
    """LA razon de ser del modulo. Una fila v1 no sabe nada de p_master: eso NO
    es 'p_master fue None', es 'no preguntes a esta fila por p_master'."""
    fila_vieja = {fs.SCHEMA_KEY: 1, fs.FEATURES_KEY: {"tf": "5m"}}
    assert fs.read(fila_vieja, "p_master") == (fs.UNKNOWN_THEN, None)

    fila_nueva = {fs.SCHEMA_KEY: 2, fs.FEATURES_KEY: {"p_master": None}}
    assert fs.read(fila_nueva, "p_master") == (fs.NULL, None)

    medida = {fs.SCHEMA_KEY: 2, fs.FEATURES_KEY: {"p_master": 2.3}}
    assert fs.read(medida, "p_master") == (fs.VALUE, 2.3)


def test_el_caso_cvd_confirmed_concreto():
    """El ejemplo que cita el brief: 'confirmado=False' y 'no se midio' son
    diagnosticos distintos (uno es senal, el otro es un colector caido)."""
    sin_medicion = fs.snapshot(extra={})
    assert fs.read(sin_medicion, "cvd_confirmed")[0] == fs.NULL
    con_medicion = fs.snapshot(extra={"cvd_confirmed": False})
    assert fs.read(con_medicion, "cvd_confirmed") == (fs.VALUE, False)


def test_fila_sin_version_se_lee_como_v1():
    """El ledger historico no trae schema_version. No es un error: es v1."""
    assert fs.read({"tf": "5m"}, "p_master")[0] == fs.UNKNOWN_THEN
    assert fs.read({"tf": "5m"}, "tf") == (fs.VALUE, "5m")


def test_fila_de_una_version_futura_no_inventa():
    """Un ledger escrito por un deploy mas nuevo: de sus features nuevas este
    codigo no sabe nada, y decir 'no existia' seria mentir. Se lee con el esquema
    mas alto conocido."""
    fila = {fs.SCHEMA_KEY: 99, fs.FEATURES_KEY: {"p_master": 1.0}}
    assert fs.read(fila, "p_master") == (fs.VALUE, 1.0)


# --- 2. append-only: anadir no invalida lo viejo ----------------------------

def test_las_versiones_son_append_only():
    """LA invariante estructural. Si alguien quita un campo de una version ya
    publicada, todas las filas selladas con ella pasan a significar otra cosa y
    el dataset deja de ser un dataset. Este test lo impide."""
    versiones = sorted(fs.SCHEMA)
    for prev, cur in zip(versiones, versiones[1:]):
        faltan = set(fs.SCHEMA[prev]) - set(fs.SCHEMA[cur])
        assert not faltan, "v%d perdio campos de v%d: %s" % (cur, prev, sorted(faltan))


def test_una_version_no_repite_campos():
    for v, campos in fs.SCHEMA.items():
        assert len(campos) == len(set(campos)), "v%d tiene campos duplicados" % v


def test_el_snapshot_declara_todo_lo_que_promete_el_esquema():
    """Si el esquema declara una feature que snapshot() no emite nunca, `read`
    la reporta como NULL ('no se midio') cuando la verdad es 'nadie la cablea'.
    Eso es un esquema que miente."""
    snap = fs.snapshot(extra={})
    assert set(snap[fs.FEATURES_KEY]) == set(fs.SCHEMA[fs.SCHEMA_VERSION])


def test_no_se_sella_nada_fuera_del_esquema():
    """Un campo no declarado seria ilegible por `read` -> escribir a ciegas."""
    snap = fs.snapshot(extra={"inventado_ayer": 1})
    assert "inventado_ayer" not in snap[fs.FEATURES_KEY]


def test_el_vector_es_el_MISMO_del_cube():
    """El payoff de E1: una senal de hoy se compara contra las 13.429 de la
    cosecha sin traducir nada. Si bt_features cambia y esto no, se rompe."""
    pytest.importorskip("pandas")
    from bt_features import extract_features

    class _F:
        confluence_count = 3
    campos = set(extract_features(_F(), {}))
    declarados = set(fs.SCHEMA[fs.SCHEMA_VERSION])
    assert campos <= declarados, "el cube emite features que el snapshot no declara: %s" % (
        sorted(campos - declarados))


# --- 3. sobre-sellar tambien es un fallo: la varianza ------------------------

def test_delata_una_feature_constante():
    """El caso vp_basis: constante 'developing' durante meses, sellada fielmente,
    invisible. Una columna que no se mueve no esta midiendo."""
    m = fs.VarianceMonitor(min_runs=5)
    avisos = []
    for _ in range(6):
        avisos += m.observe({"vp_basis": "developing", "p_master": 1.0})
    assert "vp_basis" in avisos
    assert m.stale()["vp_basis"] >= 5


def test_una_feature_que_se_mueve_no_se_marca():
    m = fs.VarianceMonitor(min_runs=3)
    for i in range(10):
        avisos = m.observe({"p_master": float(i)})
        assert avisos == []
    assert "p_master" not in m.stale()


def test_avisa_una_sola_vez_por_feature():
    """Si avisara en cada apertura, el ledger se llenaria de ruido y el aviso
    dejaria de leerse -- que es como se pierden los avisos de verdad."""
    m = fs.VarianceMonitor(min_runs=3)
    n = sum(len(m.observe({"x": 1})) for _ in range(20))
    assert n == 1


def test_la_racha_se_reinicia_al_cambiar():
    m = fs.VarianceMonitor(min_runs=3)
    m.observe({"x": 1}); m.observe({"x": 1})
    m.observe({"x": 2})                       # cambio -> racha a 1
    assert m.observe({"x": 2}) == []          # aun no llega a 3
    assert m.stale() == {}


# --- 4. dormido por defecto (Constitucion II.1) -----------------------------

def test_off_por_defecto(monkeypatch):
    monkeypatch.delenv("FQ_FEATURE_SNAPSHOT", raising=False)
    assert fs.enabled() is False


def test_el_flag_lo_enciende(monkeypatch):
    monkeypatch.setenv("FQ_FEATURE_SNAPSHOT", "1")
    assert fs.enabled() is True


def test_con_el_flag_off_el_open_no_lleva_claves_nuevas(monkeypatch):
    """Byte-identico al historico: ni schema_version ni features."""
    import motor_paper
    monkeypatch.delenv("FQ_FEATURE_SNAPSHOT", raising=False)

    class _M:
        symbol = "X"
        _variance = fs.VarianceMonitor()
        broker = None
    assert motor_paper.MotorPaperRuntime._feature_meta(_M(), None, {}) == {}


def test_con_el_flag_on_el_open_lleva_version_y_vector(monkeypatch):
    import motor_paper
    monkeypatch.setenv("FQ_FEATURE_SNAPSHOT", "1")

    class _Ledger:
        def __init__(self):
            self.rows = []

        def append(self, r):
            self.rows.append(r)

    class _Broker:
        ledger = _Ledger()

    class _M:
        symbol = "X"
        _variance = fs.VarianceMonitor(min_runs=2)
        broker = _Broker()

    m = _M()
    meta = motor_paper.MotorPaperRuntime._feature_meta(m, None, {})
    assert meta[fs.SCHEMA_KEY] == fs.SCHEMA_VERSION
    assert "p_master" in meta[fs.FEATURES_KEY]


def test_el_motor_sella_el_aviso_de_feature_rancia(monkeypatch):
    """El aviso no se queda en un log que nadie lee: entra al ledger auditable."""
    import motor_paper
    monkeypatch.setenv("FQ_FEATURE_SNAPSHOT", "1")

    class _Ledger:
        def __init__(self):
            self.rows = []

        def append(self, r):
            self.rows.append(r)

    class _Broker:
        def __init__(self):
            self.ledger = _Ledger()

    class _M:
        symbol = "X"

        def __init__(self):
            self._variance = fs.VarianceMonitor(min_runs=2)
            self.broker = _Broker()

    m = _M()
    motor_paper.MotorPaperRuntime._feature_meta(m, None, {})
    motor_paper.MotorPaperRuntime._feature_meta(m, None, {})
    eventos = [r for r in m.broker.ledger.rows if r["event"] == "MOTOR_FEATURE_STALE"]
    assert eventos and eventos[0]["feature"] in fs.SCHEMA[fs.SCHEMA_VERSION]
