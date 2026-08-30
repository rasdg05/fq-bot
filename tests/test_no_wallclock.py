# -*- coding: utf-8 -*-
"""GUARDA ANTI-RELOJ (lección RETRIEVAL_PLAN §6.7, codificada como test).

El bug de reloj ocurrió DOS veces (volume_quality, killzones_pd): un módulo
del path del motor leía `datetime.now()` y el replay de research heredaba la
hora del click — backtests de regímenes ficticios. El harness inyecta
`_BarClockDatetime` (tools/run_research_real.py) en los módulos conocidos;
esta guarda evita que un reloj NUEVO entre sin pasar por esa decisión.

Cómo funciona: cuenta por AST los call-sites de reloj de pared
(datetime.now / datetime.utcnow / date.today / Timestamp.now) en los módulos
del path del motor y los compara contra el BASELINE auditado (jun-2026).

Si este test te falla:
  1. ¿Puedes recibir el timestamp de la VELA por parámetro? Hazlo (preferido).
  2. Si el reloj es legítimo (solo producción, p.ej. sellos de ledger),
     añade el módulo a la inyección del harness si el replay lo toca, y
     actualiza el baseline AQUÍ en el mismo PR, explicando por qué.
Bajar un conteo es bienvenido: actualiza el baseline a la baja.
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Módulos que participan en la decisión del motor (replay de research los
# ejecuta vela a vela). Los bots/ops/presentación NO van aquí: su reloj de
# pared es legítimo.
ENGINE_PATH_BASELINE = {
    # módulo            call-sites de reloj auditados (jun-2026)
    "fusion_engine.py":     2,   # cooldown + sello ts del report
    "killzones_pd.py":      4,   # INYECTADO por _BarClockDatetime en replay
    "volume_quality.py":    2,   # INYECTADO por _BarClockDatetime en replay
    "ict_smc.py":           1,   # sello ts del field
    "signal_scorer.py":     1,   # sello ts
    "signal_engine_v2.py":  6,   # cooldowns + sellos
    "regime_detector.py":   1,   # sello ts
    # +1 (ago-2026): audit_signal_ledger sella la hora del ultimo audit en
    # _ledger_health. Es un reloj de MONITORIZACION, no del path de decision:
    # no entra en ningun outcome ni en el replay, solo registra cuando se
    # ejecuto la comprobacion. Subida consciente del baseline.
    "entropy_cognition.py": 11,  # sellos de ledger/outcomes + sello del audit
    "market_context.py":    0,
    "session_bias.py":      0,
    "segment_veto.py":      0,   # F2.6 §6.8: juzga el ts de la VELA, nunca now()
    "battle_planner.py":    0,
    "emergent_time.py":     0,
    "quantum_timelines.py": 0,
}

_CLOCK_ATTRS = {
    ("datetime", "now"), ("datetime", "utcnow"),
    ("date", "today"), ("Timestamp", "now"),
}


def _wallclock_callsites(path):
    """Lista (lineno, expresión) de llamadas de reloj de pared en el archivo."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    hits = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)):
            continue
        attr = node.func.attr
        base = node.func.value
        # cubre `datetime.now(...)`, `datetime.datetime.now(...)`,
        # `pd.Timestamp.now(...)`: nos quedamos con el último nombre de la
        # cadena antes del atributo llamado.
        if isinstance(base, ast.Name):
            base_name = base.id
        elif isinstance(base, ast.Attribute):
            base_name = base.attr
        else:
            continue
        if (base_name, attr) in _CLOCK_ATTRS:
            hits.append((node.lineno, f"{base_name}.{attr}()"))
    return hits


def test_sin_relojes_nuevos_en_el_path_del_motor():
    problemas = []
    for fname, max_sites in ENGINE_PATH_BASELINE.items():
        path = os.path.join(ROOT, fname)
        assert os.path.exists(path), (
            f"{fname} no existe: si el módulo se renombró/eliminó, actualiza "
            "ENGINE_PATH_BASELINE en este test (es el inventario del motor).")
        hits = _wallclock_callsites(path)
        if len(hits) > max_sites:
            detalle = ", ".join(f"L{ln}:{expr}" for ln, expr in hits)
            problemas.append(
                f"{fname}: {len(hits)} relojes de pared (baseline {max_sites})"
                f" -> {detalle}")
    assert not problemas, (
        "RELOJ DE PARED NUEVO en el path del motor (lección §6.7 del "
        "RETRIEVAL_PLAN: el replay heredaría la hora del click). Pasa el ts "
        "de la vela por parámetro o inyecta _BarClockDatetime en el harness "
        "y actualiza el baseline conscientemente.\n" + "\n".join(problemas))


def test_baseline_no_esta_inflado():
    """El baseline debe reflejar la realidad: si alguien LIMPIA relojes, hay
    que bajar el número (si no, la guarda pierde sensibilidad)."""
    inflados = []
    for fname, max_sites in ENGINE_PATH_BASELINE.items():
        path = os.path.join(ROOT, fname)
        if not os.path.exists(path):
            continue
        n = len(_wallclock_callsites(path))
        if n < max_sites:
            inflados.append(f"{fname}: baseline {max_sites} pero hay {n} — "
                            f"baja el baseline a {n}")
    assert not inflados, "\n".join(inflados)


# ---------------------------------------------------------------------------
# LA SUITE TAMPOCO PUEDE LEER EL RELOJ (ago-2026)
# ---------------------------------------------------------------------------
# La guarda de arriba cubre el path del MOTOR. No cubria los tests, y ahi habia
# el mismo bug: seis tests de test_tactical_alert.py llamaban a
# `volume_quality.is_dead_window()` -- que lee `datetime.now()` -- y hacian
# pytest.skip si daba True. Entre las 14:00 y las 16:00 CDMX, y los viernes por
# la tarde, esos seis desaparecian y el resumen seguia diciendo "passed".
#
# Un test que se salta segun la hora no es flaky: es una guarda que deja de
# guardar en silencio, que es exactamente el fallo que este fichero persigue.
# Se arreglo fijando el instante (fixture `reloj_fijo`), no mockeando el
# veredicto: la logica real corre entera, a una hora conocida.

# Motivos legitimos para saltar un test: que falte una dependencia OPCIONAL, o
# que el entorno tenga una flag puesta. Nunca la hora, la fecha ni el dia.
SKIPS_LEGITIMOS = {
    "test_bt_selectivity.py": "run_research_real no importable (deps opcionales)",
    "test_html_safety.py": "skipif por dependencia del bot",
    "test_signal_policy.py": "skipif por FQ_RADAR_ENABLED en el entorno",
}

_RELOJ = {"now", "utcnow", "today", "is_dead_window", "dead_window_label",
          "is_weekend_closed", "time"}


def _lee_reloj(nodo):
    """¿Este subarbol llama a algo que lee el reloj de pared SIN pasarle la hora?"""
    for n in ast.walk(nodo):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        if nombre in _RELOJ and not n.args and not n.keywords:
            return nombre
    return None


def test_ningun_test_se_salta_segun_la_hora():
    tests_dir = os.path.join(ROOT, "tests")
    malos = []
    for name in sorted(os.listdir(tests_dir)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        if name in SKIPS_LEGITIMOS:
            continue
        src = open(os.path.join(tests_dir, name), encoding="utf-8").read()
        if "skip" not in src:
            continue
        arbol = ast.parse(src)
        for n in ast.walk(arbol):
            # `if <algo que lee el reloj>: pytest.skip(...)`
            if not isinstance(n, ast.If):
                continue
            reloj = _lee_reloj(n.test)
            if reloj and "skip" in ast.dump(ast.Module(body=n.body, type_ignores=[])):
                malos.append("tests/%s (salta segun %s())" % (name, reloj))
    assert not malos, (
        "estos tests se saltan segun el reloj de pared, asi que desaparecen a "
        "ciertas horas sin que nadie lo note: %s. Fija el instante con una "
        "fixture (ver `reloj_fijo` en test_tactical_alert.py) en vez de saltar; "
        "si el motivo es una dependencia opcional, declaralo en "
        "SKIPS_LEGITIMOS." % ", ".join(malos))
