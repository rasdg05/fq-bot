"""Tests del brain_indexer (MEMORY/ -> grafo). Cubre categorización por contexto,
referencias entre notas, menciones de símbolo con tier medido, y determinismo."""
import json
import os
import tempfile

import sys
sys.path.insert(0, "tools")
import brain_indexer as B


def _fixture():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "CEMENTERIO.md"), "w", encoding="utf-8") as f:
        f.write("# Cementerio\n## VALIDADO\n### CVD firmado\nBTC y SOL pasan el gate.\n"
                "## CEMENTERIO\n### POC-distance\nmurió (PBO 0.76). ver `DECISIONES.md`\n")
    with open(os.path.join(d, "DECISIONES.md"), "w", encoding="utf-8") as f:
        f.write("# Decisiones\n## 1. Measure-first\nnada sin gate. LINK no pasa. BNB forward.\n")
    return d


def test_self_test_pasa():
    assert B._self_test() == 0


def test_categoria_por_seccion():
    g = B.build_graph(_fixture())
    ids = {n["id"]: n for n in g["nodes"]}
    assert ids["file:CEMENTERIO.md#cvd-firmado"]["cat"] == "val"   # bajo ## VALIDADO
    assert ids["file:CEMENTERIO.md#poc-distance"]["cat"] == "cem"  # bajo ## CEMENTERIO


def test_simbolos_con_tier_medido():
    g = B.build_graph(_fixture())
    ids = {n["id"]: n for n in g["nodes"]}
    assert ids["sym:BTC"]["tier"] == "live"
    assert ids["sym:SOL"]["tier"] == "live"
    assert ids["sym:LINK"]["tier"] == "fail"     # GATE-F: LINK reprobado
    assert ids["sym:BNB"]["tier"] == "forward"


def test_referencias_entre_notas():
    g = B.build_graph(_fixture())
    assert any(e["kind"] == "ref" and e["b"] == "file:DECISIONES.md" for e in g["edges"])


def test_menciones_de_simbolo():
    g = B.build_graph(_fixture())
    assert any(e["kind"] == "mentions" and e["b"] == "sym:BTC" for e in g["edges"])


def test_determinista():
    d = _fixture()
    assert json.dumps(B.build_graph(d)) == json.dumps(B.build_graph(d))


def test_grado_calculado():
    g = B.build_graph(_fixture())
    assert all("deg" in n for n in g["nodes"])
    # el hub del archivo tiene grado > 0 (headings + refs cuelgan de él)
    ids = {n["id"]: n for n in g["nodes"]}
    assert ids["file:CEMENTERIO.md"]["deg"] > 0


def test_memory_real_si_existe():
    # si corre en el repo, indexa el MEMORY/ real sin romper
    if os.path.isdir("MEMORY"):
        g = B.build_graph("MEMORY")
        assert g["stats"]["nodes"] > 50
        assert g["stats"]["by_cat"].get("cem", 0) > 0   # hay cementerio real
        assert g["stats"]["by_cat"].get("val", 0) > 0   # hay validado real
