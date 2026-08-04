# -*- coding: utf-8 -*-
"""
E9 — GUARDA DEL DESGLOSE: nunca mas un E[R] agregado suelto.

El fantasma de mayo fue un agregado sobre UN solo regimen presentado como ley:
WR 60% / +1.84R / PF 7.23, exacto como aritmetica y falso como afirmacion sobre
el sistema. Y no fue mala suerte — GHOST_MAP H1 ya habia medido que el lado
ganador SE VOLTEA por epoca (2020-22 pago LONG, 2023-25 paga SHORT), asi que
cualquier promedio largo es un volado y cualquier promedio corto es un regimen.

La regla que sale de ahi: **el agregado lleva el asterisco, no el desglose.**

Dos capas la sostienen, porque una sola no basta:
  1. RUNTIME: `format_expectancy` levanta si le falta `by_period`.
  2. ESTRUCTURAL (este archivo): una guarda AST cuenta las superficies de
     publicacion que formatean una expectancy POR SU CUENTA. Baseline = 0.
     Sin esta capa, la regla se cumple hasta que alguien escriba un `.format()`
     nuevo — que es exactamente como se perdio la primera vez: no por falta de
     conocimiento, por falta de cableado.

Si este test te falla: no formatees el numero a mano. Pasa el stats por
`ledger_stats.format_expectancy`, que ya trae el desglose y marca los periodos
con n<30.
"""
import ast
import os

import pytest

import ledger_stats as ls

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Superficies que publican track record de cara a un humano. Los modulos de
# research (bt_*, tools/) NO van aqui: sus tablas ya son desgloses.
SURFACES_BASELINE = {
    "public_format.py": 0,
    "vip_format.py": 0,
    "public_content_generator.py": 0,
    "public_outcome_announcer.py": 0,
}

SANCTIONED = "format_expectancy"


def _touches_expectancy(node):
    """¿Este subarbol saca 'expectancy' de un stats? (`s["expectancy"]` / .get)"""
    for n in ast.walk(node):
        if (isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)
                and n.slice.value == "expectancy"):
            return True
        if (isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "get"
                and n.args and isinstance(n.args[0], ast.Constant)
                and n.args[0].value == "expectancy"):
            return True
    return False


def _is_format_context(node):
    """Nodos que RENDERIZAN texto: f-string, .format(...) y '%' sobre literal.

    Se cuenta el renderizado, no el fontaneo. Pasar `stats["expectancy"]` de un
    dict a otro es legitimo -- de hecho es necesario -- siempre que `by_period`
    viaje pegado; de eso ya se encarga el guardia en tiempo de ejecucion, que
    levanta cuando el desglose no llega. Lo que no puede pasar es que alguien
    imprima el numero suelto.
    """
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "format":
        return True
    return (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)
            and isinstance(node.left, ast.Constant)
            and isinstance(node.left.value, str))


def _manual_expectancy_formats(path):
    """Sitios donde se RENDERIZA una expectancy sin pasar por el formateador."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)

    sancionados = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and
                getattr(node.func, "id", getattr(node.func, "attr", None)) == SANCTIONED):
            for sub in ast.walk(node):
                sancionados.add(id(sub))

    hits = []
    for node in ast.walk(tree):
        if id(node) in sancionados or not _is_format_context(node):
            continue
        if _touches_expectancy(node):
            hits.append(node.lineno)
    return sorted(set(hits))


@pytest.mark.parametrize("modulo,baseline", sorted(SURFACES_BASELINE.items()))
def test_ninguna_superficie_formatea_la_expectancy_a_mano(modulo, baseline):
    path = os.path.join(ROOT, modulo)
    if not os.path.exists(path):
        pytest.skip("%s no existe" % modulo)
    hits = _manual_expectancy_formats(path)
    assert len(hits) <= baseline, (
        "%s toca 'expectancy' fuera de %s en las lineas %s. Un agregado sin su "
        "desglose es exactamente el espejismo de mayo." % (modulo, SANCTIONED, hits))


@pytest.mark.parametrize("codigo", [
    'def f(s):\n    return "%.2f" % s["expectancy"]\n',           # % sobre literal
    'def f(s):\n    return "{:+.2f}".format(s["expectancy"])\n',  # .format
    'def f(s):\n    return f"{s[\'expectancy\']:+.2f}"\n',        # f-string
    'def f(s):\n    return "{e}".format(e=s.get("expectancy", 0))\n',
])
def test_la_guarda_detecta_cada_forma_de_renderizar(tmp_path, codigo):
    """La guarda tiene que servir para algo: si no cazara un renderizado manual,
    pasar el test no significaria nada. Se prueban las tres sintaxis con las que
    Python formatea, porque cerrar solo una deja la puerta abierta."""
    p = tmp_path / "malo.py"
    p.write_text(codigo)
    assert _manual_expectancy_formats(str(p)) == [2]


def test_la_guarda_no_castiga_el_uso_sancionado(tmp_path):
    p = tmp_path / "bueno.py"
    p.write_text("from ledger_stats import format_expectancy\n"
                 "def f(s):\n    return '{}'.format(format_expectancy(s))\n")
    assert _manual_expectancy_formats(str(p)) == []


def test_la_guarda_no_castiga_el_fontaneo(tmp_path):
    """Pasar la expectancy de un dict a otro es legitimo y necesario; lo que no
    puede es imprimirse suelta. Si la guarda castigara esto, se desactivaria a
    la primera y dejaria de proteger nada."""
    p = tmp_path / "plumbing.py"
    p.write_text('def f(s):\n    return {"expectancy": s["expectancy"],\n'
                 '            "by_period": s["by_period"]}\n')
    assert _manual_expectancy_formats(str(p)) == []


# --- capa 1: el guardia en tiempo de ejecucion ------------------------------

def _rows(n, year="2024", pnl=1.0):
    return [{"outcome": "tp1" if pnl > 0 else "sl", "pnl_r": pnl,
             "ts_closed": "%s-01-0%dT00:00:00" % (year, (i % 9) + 1),
             "minutes_open": 60} for i in range(n)]


def test_publicar_un_agregado_sin_desglose_levanta():
    with pytest.raises(ls.AggregateWithoutBreakdownError):
        ls.format_expectancy({"expectancy": 1.84, "n": 35})


def test_window_stats_siempre_adjunta_el_desglose():
    st = ls.window_stats(_rows(10))
    assert st["by_period"]
    ls.format_expectancy(st)          # no levanta


def test_el_desglose_separa_por_ano():
    st = ls.window_stats(_rows(5, "2023") + _rows(5, "2024"))
    assert set(st["by_period"]) == {"2023", "2024"}


def test_el_regimen_manda_sobre_el_ano_si_esta():
    rows = _rows(4, "2024")
    for r in rows:
        r["regime"] = "deriva"
    assert set(ls.window_stats(rows)["by_period"]) == {"deriva"}


def test_un_periodo_flaco_sale_marcado_no_diluido():
    """El criterio de aceptacion del brief: si un regimen tiene n<30 aparece
    marcado en vez de diluido en el promedio."""
    st = ls.window_stats(_rows(40, "2023") + _rows(3, "2024"))
    assert st["by_period"]["2024"]["thin"] is True
    assert st["by_period"]["2023"]["thin"] is False
    salida = ls.format_expectancy(st)
    assert "no concluye" in salida
    assert "agregado*" in salida       # el agregado es el que lleva el asterisco


def test_el_desglose_delata_un_voltear_de_signo():
    """El caso H1: dos epocas de signo opuesto que el agregado esconde."""
    st = ls.window_stats(_rows(30, "2021", pnl=+1.0) + _rows(30, "2024", pnl=-1.0))
    salida = ls.format_expectancy(st)
    assert "+1.00R" in salida and "-1.00R" in salida
    assert abs(st["expectancy"]) < 0.01          # el agregado dice "nada pasa"


def test_el_track_record_publico_sale_con_desglose():
    """Punta a punta por la superficie real."""
    import public_format
    st = ls.window_stats(_rows(30, "2023") + _rows(4, "2024"))
    salida = public_format._fmt_window("Historico total", st)
    assert "2023" in salida and "2024" in salida
    assert "no concluye" in salida
