#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""brain_indexer — MEMORY/ (el cerebro obsidian) -> brain.json (grafo real).

Lee el vault de notas markdown y produce el grafo que el visualizador admin
renderiza: nodos = archivos + headings + símbolos; enlaces = jerarquía +
referencias entre notas (`X.md`) + menciones de símbolo. Categoriza por contexto
(VALIDADO / CEMENTERIO / DECISIONES / CONSTITUCION / ESTADO) para colorear el
grafo con la verdad medida. Pure-stdlib, determinista, testeable en aislado.

Uso:  python tools/brain_indexer.py --dir MEMORY --out brain.json
      python tools/brain_indexer.py --self-test
"""
import argparse
import json
import os
import re

SYMS = ["BTC", "SOL", "ETH", "BNB", "LINK", "BCH", "ADA", "AVAX", "DOGE", "DOT", "LTC", "TRX", "XRP"]
# Estatus MEDIDO del gate (GATE-F, 2026-07-05) — no marketing: lo que el gate dijo.
TIER = {"BTC": "live", "SOL": "live", "ETH": "live", "BNB": "forward", "LINK": "fail"}
_SYM_RE = re.compile(r"\b(" + "|".join(SYMS) + r")\b")
_REF_RE = re.compile(r"`([A-Za-z0-9_\-]+\.md)`|\]\(([^)]+\.md)\)|\[\[([^\]]+)\]\]")
_HEAD_RE = re.compile(r"^(#{1,3})\s+(.*?)\s*#*$")


def _slug(s):
    s = re.sub(r"[`*_>#\[\]]", "", s).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", s)[:48].strip("-") or "x"


def _cat_for(fname, section):
    """Categoría por archivo + sección H2 vigente (colorea la verdad)."""
    f = fname.upper()
    sec = (section or "").upper()
    if "VALIDADO" in sec:
        return "val"
    if "CEMENTERIO" in sec:
        return "cem"
    if "CEMENTERIO" in f:
        return "cem"      # nota del cementerio, sección no marcada aún
    if "DECISIONES" in f:
        return "dec"
    if "CONSTITUCION" in f:
        return "law"
    if "ESTADO" in f:
        return "state"
    if "INDICE" in f:
        return "root"
    return "section"


def build_graph(root_dir):
    """Escanea root_dir recursivamente por .md y arma {nodes, edges, stats}.
    Determinista (orden estable). Defensivo: un archivo ilegible se salta, no rompe."""
    nodes, edges, seen = [], [], {}
    files = []
    for dp, _, fns in os.walk(root_dir):
        for fn in sorted(fns):
            if fn.lower().endswith(".md"):
                files.append(os.path.join(dp, fn))
    files.sort()

    def add(nid, cat, label, **kw):
        if nid in seen:
            return seen[nid]
        n = {"id": nid, "cat": cat, "label": label, **kw}
        nodes.append(n); seen[nid] = n
        return n

    def link(a, b, kind):
        if a in seen and b in seen and a != b:
            edges.append({"a": a, "b": b, "kind": kind})

    add("MEMORY", "hub", "MEMORY/")
    fname_by_id = {}
    for path in files:
        base = os.path.basename(path)
        stem = os.path.splitext(base)[0]
        fid = "file:" + base
        add(fid, "hub", stem)
        fname_by_id[base] = fid
        link(fid, "MEMORY", "in")

    for path in files:
        base = os.path.basename(path)
        fid = "file:" + base
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except Exception:
            continue
        section = None           # H2 vigente (para categorizar H3)
        parents = {1: fid}       # último nodo por nivel -> jerarquía
        symset = set()
        for line in text.splitlines():
            m = _HEAD_RE.match(line)
            if m:
                lvl = len(m.group(1)); title = m.group(2).strip()
                if not title:
                    continue
                if lvl == 2:
                    section = title
                cat = _cat_for(base, section if lvl >= 3 else title if lvl == 2 else "")
                if lvl == 1:
                    continue     # el H1 es el archivo mismo
                hid = "%s#%s" % (fid, _slug(title))
                add(hid, cat, re.sub(r"\*\*|`", "", title)[:60])
                parent = parents.get(lvl - 1, fid)
                link(hid, parent, "sub")
                parents[lvl] = hid
                for k in list(parents):
                    if k > lvl:
                        parents.pop(k)
            for sm in _SYM_RE.findall(line):
                symset.add(sm)
        # referencias entre notas
        for r in _REF_RE.findall(text):
            ref = (r[0] or r[1] or r[2]).split("/")[-1]
            if not ref.endswith(".md"):
                ref += ".md"
            if ref in fname_by_id and fname_by_id[ref] != fid:
                edges.append({"a": fid, "b": fname_by_id[ref], "kind": "ref"})
        # menciones de símbolo
        for s in symset:
            sid = "sym:" + s
            add(sid, TIER.get(s, "harvest"), s, sym=True, tier=TIER.get(s, "harvest"))
            link(fid, sid, "mentions")

    # grado (para dimensionar nodos)
    deg = {}
    for e in edges:
        deg[e["a"]] = deg.get(e["a"], 0) + 1
        deg[e["b"]] = deg.get(e["b"], 0) + 1
    for n in nodes:
        n["deg"] = deg.get(n["id"], 0)

    cats = {}
    for n in nodes:
        cats[n["cat"]] = cats.get(n["cat"], 0) + 1
    return {"nodes": nodes, "edges": edges,
            "stats": {"files": len(files), "nodes": len(nodes), "edges": len(edges), "by_cat": cats}}


def _self_test():
    import tempfile
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "sub"), exist_ok=True)
    with open(os.path.join(d, "CEMENTERIO.md"), "w") as f:
        f.write("# Cementerio\n## VALIDADO\n### CVD firmado\nBTC y SOL pasan.\n"
                "## CEMENTERIO\n### POC-distance\nmurió. ver `DECISIONES.md`\n")
    with open(os.path.join(d, "DECISIONES.md"), "w") as f:
        f.write("# Decisiones\n## 1. Measure-first\nnada sin gate. LINK no pasa.\n")
    g = build_graph(d)
    ids = {n["id"]: n for n in g["nodes"]}
    assert "MEMORY" in ids and ids["MEMORY"]["cat"] == "hub"
    assert "file:CEMENTERIO.md" in ids, "archivo hub"
    cvd = ids.get("file:CEMENTERIO.md#cvd-firmado")
    assert cvd and cvd["cat"] == "val", "H3 bajo VALIDADO -> val (%s)" % (cvd and cvd["cat"])
    poc = ids.get("file:CEMENTERIO.md#poc-distance")
    assert poc and poc["cat"] == "cem", "H3 bajo CEMENTERIO -> cem"
    assert "sym:BTC" in ids and ids["sym:BTC"]["tier"] == "live", "símbolo BTC live"
    assert ids["sym:LINK"]["tier"] == "fail", "LINK fail (medido)"
    assert any(e["kind"] == "ref" and e["b"] == "file:DECISIONES.md" for e in g["edges"]), "ref entre notas"
    assert any(e["kind"] == "mentions" and e["b"] == "sym:BTC" for e in g["edges"]), "mención símbolo"
    # determinista
    g2 = build_graph(d)
    assert json.dumps(g) == json.dumps(g2), "determinista"
    print("brain_indexer self-test: OK (%d nodos, %d enlaces en el fixture)"
          % (g["stats"]["nodes"], g["stats"]["edges"]))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Indexa MEMORY/ -> brain.json (grafo del cerebro).")
    p.add_argument("--dir", default="MEMORY")
    p.add_argument("--out", default="brain.json")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)
    if a.self_test:
        return _self_test()
    g = build_graph(a.dir)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False)
    s = g["stats"]
    print("brain.json escrito: %d archivos · %d nodos · %d enlaces" % (s["files"], s["nodes"], s["edges"]))
    print("por categoría:", s["by_cat"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
