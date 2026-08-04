# -*- coding: utf-8 -*-
"""
================================================================================
  FEATURE SNAPSHOT — sellar el vector COMPLETO en el OPEN, con version de esquema
================================================================================

MOTOR_OPEN_META sellaba ~10 campos elegidos a mano en 2026-07. Sirve para las
preguntas que alguien anticipo entonces; para cualquier otra, los trades de hoy
son incontestables dentro de tres meses. Eso es un log, no un dataset.

El vector que se sella aqui es el MISMO que produce `bt_features.extract_features`
-- o sea el mismo que llevan las 13.429 filas del cube. No es coincidencia: es el
punto. Una senal abierta hoy se puede comparar contra los 7 anos de cosecha
feature a feature, sin traducir nada.

La distincion que hoy NO se puede hacer
---------------------------------------
Con `cvd_confirmed` ausente de una fila vieja es imposible saber si la feature no
existia todavia o si existia y no se midio. Son cosas opuestas: la primera dice
"no preguntes"; la segunda es un dato (el colector estaba caido). Por eso la
ausencia de clave NO es la fuente de verdad aqui -- lo es el REGISTRO de esquemas:

    SCHEMA[v] = tupla de features que existian en la version v

Con eso, `read(row, name)` distingue tres estados y el consumidor nunca tiene que
adivinar:

    UNKNOWN_THEN : la feature no existia cuando se sello la fila -> no preguntes
    NULL         : existia y salio nula -> es un dato sobre el colector
    VALUE        : existia y se midio

Anadir una feature manana = anadir una version. Las filas viejas siguen siendo
legibles y siguen significando exactamente lo que significaban. El test
`test_las_versiones_son_append_only` impide quitar campos de una version publicada,
que es lo unico que romperia esa promesa.

Sobre-sellar tambien es un fallo
--------------------------------
`vp_basis` estuvo constante meses y el ledger lo guardaba fielmente sin que nadie
lo notara: una columna muerta ocupando sitio y aparentando medicion. `VarianceMonitor`
delata eso -- si una feature lleva N aperturas sin cambiar de valor, lo dice.

Dormido por defecto (Constitucion II.1): sin `FQ_FEATURE_SNAPSHOT=1` el ledger
queda byte-identico al historico, sin claves nuevas.
================================================================================
"""
import os

# --- estados de lectura -----------------------------------------------------
UNKNOWN_THEN = "unknown_then"   # la feature no existia en el esquema de la fila
NULL = "null"                   # existia y valia None (dato sobre el colector)
VALUE = "value"                 # existia y se midio


# --- registro de esquemas (APPEND-ONLY) -------------------------------------
# v1 = lo que MOTOR_OPEN_META sellaba a mano hasta 2026-07. Se declara aunque ya
# no se emita, porque las filas viejas del ledger la citan y hay que poder leerlas.
_V1 = (
    "tf", "killzone", "regime", "fill_type", "bars_waited",
    "cvd_confirmed", "cvd_imbalance", "cvd_staleness_min",
    "kl_low", "kl_irrev", "poc_dist", "vp_zone", "vp_basis",
    "funding_rate", "funding_pctl",
)

# v2 = v1 + el vector completo de bt_features.extract_features (el del cube).
_V2_NUEVAS = (
    "p_master", "p_master_raw", "p_master_pre_vol",
    "scorer_total", "scorer_volume", "scorer_structure", "scorer_liquidity",
    "scorer_concept_stack", "scorer_history",
    "regime_state", "regime_score",
    "qt_kappa_evo", "qt_alpha_hybrid", "qt_h_factor", "qt_f_confluence",
    "qt_f_ict", "qt_n_concepts", "qt_vol_score", "qt_session_bias_mult",
    "qt_sync_score", "qt_sigma_tau",
    "field_confluence_count", "field_pd_pct", "field_w_effective",
    "field_node_type", "field_killzone", "field_killzone_priority",
    "field_bias_4h", "field_bias_1h", "field_choch", "field_has_fuel",
)

SCHEMA = {
    1: _V1,
    2: _V1 + _V2_NUEVAS,
}

SCHEMA_VERSION = max(SCHEMA)
SCHEMA_KEY = "schema_version"
FEATURES_KEY = "features"


def enabled():
    """FQ_FEATURE_SNAPSHOT. OFF -> ledger byte-identico al historico."""
    return os.environ.get("FQ_FEATURE_SNAPSHOT", "0").strip() in ("1", "true", "yes")


def known_at(version):
    """Features que EXISTIAN en esa version del esquema.

    Una version desconocida (fila de un futuro que este codigo no conoce) se lee
    como el esquema mas alto que si conoce: mejor decir 'no se' de las features
    nuevas que inventar que no existian.
    """
    try:
        v = int(version)
    except (TypeError, ValueError):
        v = 1                        # fila sin version = pre-instrumentacion
    if v in SCHEMA:
        return frozenset(SCHEMA[v])
    known = [k for k in SCHEMA if k <= v]
    return frozenset(SCHEMA[max(known)]) if known else frozenset(SCHEMA[min(SCHEMA)])


def read(row, name):
    """(estado, valor) de una feature en una fila del ledger. NUNCA adivina.

    Es la unica forma correcta de leer el snapshot: preguntar `row.get(name)` y
    ver None mezcla "no existia" con "no se midio", que es justo el bug que este
    modulo existe para cerrar.
    """
    feats = row.get(FEATURES_KEY) if isinstance(row.get(FEATURES_KEY), dict) else row
    if name not in known_at(row.get(SCHEMA_KEY)):
        return UNKNOWN_THEN, None
    v = feats.get(name)
    return (NULL, None) if v is None else (VALUE, v)


def snapshot(field=None, report=None, *, extra=None, version=SCHEMA_VERSION):
    """Vector completo + `schema_version`, listo para sellar en el OPEN.

    Reutiliza `bt_features.extract_features` (el extractor del cube) para que la
    senal de hoy sea comparable con las 13.429 de la cosecha sin traducir. El
    import es LAZY y defensivo: bt_features arrastra pandas, y el motor no puede
    caerse porque falte una dependencia de research. Si no se puede extraer, las
    features del bloque quedan NULAS -- que en este esquema significa "existia y
    no se midio", y es exactamente lo que paso.
    """
    feats = {}
    if field is not None or report is not None:
        try:
            from bt_features import extract_features
            feats.update(extract_features(field, report or {}))
        except Exception:
            pass
    if extra:
        feats.update(extra)
    declared = known_at(version)
    # Solo lo declarado: un campo fuera del esquema no seria legible por `read`,
    # asi que sellarlo seria escribir a ciegas.
    feats = {k: v for k, v in feats.items() if k in declared}
    for k in declared:
        feats.setdefault(k, None)
    return {SCHEMA_KEY: int(version), FEATURES_KEY: feats}


class VarianceMonitor:
    """¿Alguna feature lleva N aperturas sin moverse?

    Una columna constante no es una medicion: es un cable suelto que el ledger
    guarda fielmente. Paso con `vp_basis` (constante 'developing') y con el CVD
    congelado de julio, y en los dos casos el snapshot los enterro en vez de
    delatarlos. Esto los delata.

    Las categoricas de baja cardinalidad (killzone, bias) tambien entran: si el
    killzone lleva 200 aperturas diciendo lo mismo, o el mercado es rarisimo o el
    campo esta cableado a una constante. Las dos merecen una mirada.
    """

    def __init__(self, min_runs=50):
        self.min_runs = int(min_runs)
        self._last = {}          # feature -> ultimo valor visto
        self._runs = {}          # feature -> aperturas consecutivas sin cambiar
        self.n_seen = 0

    def observe(self, features):
        """Registra una apertura. Devuelve las features recien marcadas rancias."""
        self.n_seen += 1
        nuevas = []
        for k, v in (features or {}).items():
            if k in self._last and self._last[k] == v:
                self._runs[k] = self._runs.get(k, 1) + 1
                if self._runs[k] == self.min_runs:
                    nuevas.append(k)
            else:
                self._runs[k] = 1
            self._last[k] = v
        return nuevas

    def stale(self):
        """Features constantes desde hace >= min_runs aperturas, con su racha."""
        return {k: n for k, n in sorted(self._runs.items()) if n >= self.min_runs}
