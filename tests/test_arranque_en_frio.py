# -*- coding: utf-8 -*-
"""GUARDA DEL ARRANQUE EN FRIO: los puntos de entrada no pueden contradecirse.

El 2026-08-30 `internal/BRIEF_INSTRUMENTO_2026-08.md` tenia DOS instrucciones de
rama incompatibles: el bloque nuevo mandaba sacar de `claude/instrumento-2026-08`
y la seccion vieja "Como entregar", al final, seguia mandando sacar de
`claude/polymarket-trading-tools-grx05x`. Una sesion que leyera el final en vez
del principio se llevaba el cementerio de Polymarket pero perdia E7, E8 y las
invariantes de excursion -- y volvia a leer el recorrido del cube como si fuera
el del trade.

Es el mismo fallo que persigue todo este repo: no falto conocimiento, falto
CABLEADO. La rama correcta estaba escrita; tambien lo estaba la incorrecta.

Lo que se fija: la rama que `CLAUDE.md` declara como "contexto mas fresco" es la
UNICA que los puntos de entrada mandan sacar.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Los ficheros que una sesion nueva lee antes de tocar nada (ver CLAUDE.md).
# `marea/` queda fuera a proposito: es otra linea de trabajo con su propia rama.
PUNTOS_DE_ENTRADA = [
    "CLAUDE.md",
    "MEMORY/00-INDICE.md",
    "MEMORY/ESTADO.md",
    "internal/BRIEF_INSTRUMENTO_2026-08.md",
]

_CHECKOUT = re.compile(r"git checkout -b \S+ origin/(\S+)")
_FRESCA = re.compile(r"contexto m[aá]s fresco[^`]*`([^`]+)`")


def _leer(rel):
    p = os.path.join(ROOT, rel)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def rama_declarada():
    """La rama que CLAUDE.md declara como la del contexto mas fresco."""
    m = _FRESCA.search(_leer("CLAUDE.md"))
    assert m, ("CLAUDE.md ya no declara cual es la rama con el contexto mas "
               "fresco. Es lo primero que lee una sesion nueva: sin eso, "
               "arranca desde main y re-propone lo ya muerto.")
    return m.group(1)


def test_claude_md_declara_una_rama():
    assert rama_declarada().startswith("claude/")


def test_ningun_punto_de_entrada_manda_sacar_otra_rama():
    esperada = rama_declarada()
    malos = []
    for rel in PUNTOS_DE_ENTRADA:
        for encontrada in _CHECKOUT.findall(_leer(rel)):
            if encontrada != esperada:
                malos.append("%s manda sacar de %s" % (rel, encontrada))
    assert not malos, (
        "los puntos de entrada se contradicen: CLAUDE.md declara %s pero %s. "
        "Una sesion nueva que lea el fichero equivocado arranca sin el trabajo "
        "de la rama buena. Si una instruccion quedo obsoleta, marcala como "
        "historica en prosa en vez de dejar el comando vivo."
        % (esperada, "; ".join(malos)))


def test_el_indice_apunta_a_la_misma_rama():
    esperada = rama_declarada()
    txt = _leer("MEMORY/00-INDICE.md")
    m = re.search(r"[Rr]ama con el contexto m[aá]s fresco:\**\s*`([^`]+)`", txt)
    assert m, "MEMORY/00-INDICE.md dejo de nombrar la rama fresca"
    assert m.group(1) == esperada, (
        "el indice apunta a %s y CLAUDE.md a %s" % (m.group(1), esperada))


def test_el_brief_dice_como_comprobar_que_no_esta_mergeada():
    """Sin la comprobacion, la instruccion caduca en silencio el dia que se
    mergee: seguiria mandando sacar de una rama que ya es main."""
    txt = _leer("CLAUDE.md") + _leer("internal/BRIEF_INSTRUMENTO_2026-08.md")
    assert "git log origin/main" in txt and "grep -i" in txt
