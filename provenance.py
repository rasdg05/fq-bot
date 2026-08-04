# -*- coding: utf-8 -*-
"""
================================================================================
  PROCEDENCIA — de qué filas y qué colectores cuelga cada número publicado
================================================================================

Hoy la auditabilidad es binaria: una fila cuenta o no cuenta. Pero un número
publicado no depende de filas — depende de MEDICIONES, que dependen de
COLECTORES. Cuando uno se rompe hay que acordarse de qué afirmaciones caen.

Y acordarse es exactamente lo que falló en julio: el repo SABÍA que la racha de
mayo era un espejismo (GHOST_MAP H1, escrito en julio) y siguió publicando
`WR 60% · E[R] +1.84R · PF 7.23` hasta agosto. El fallo no fue de conocimiento
sino de cableado.

Esto es el cableado. NO es un motor de grafos genérico: es el grafo CONCRETO de
este repo, doce líneas de declaración, con dos afirmaciones publicables y sus
fuentes. Si mañana hay una tercera se añade aquí; si esto crece a cuarenta nodos
es señal de que se está construyendo un framework en vez de cerrar un lazo.

Cómo funciona
-------------
Cada afirmación declara de qué NODOS cuelga. Romper un nodo (`break_node`)
invalida automáticamente todo lo que cuelgue de él, transitivamente. Preguntar
si algo se puede publicar (`is_publishable`) recorre el grafo hacia arriba.

La consecuencia de un nodo roto es CALLAR, no publicar con asterisco. Un track
record que no se puede defender no se publica — misma regla que ya aplica
`audit_signal_ledger`, ahora extendida a todo lo que cuelga del mismo sitio.
================================================================================
"""
import threading

# --- el grafo, declarado a mano (esto es una lista, no un framework) --------
#
#   colector.cvd ─────┐
#   tracker.outcomes ─┼─> ledger.signals ─┬─> track_record.publico
#   ledger.motor ─────┘                   └─> audit.veredicto
#
GRAPH = {
    # fuentes (no dependen de nada: son el mundo entrando al sistema)
    "colector.cvd":       (),
    "tracker.outcomes":   (),
    "ledger.motor":       (),
    # mediciones
    "ledger.signals":     ("tracker.outcomes",),
    # afirmaciones PUBLICABLES (lo que un humano llega a leer)
    "track_record.publico": ("ledger.signals",),
    "audit.veredicto":      ("ledger.signals", "ledger.motor"),
}

# Afirmaciones que salen de este sistema hacia un cliente. Son las únicas que
# hay que poder invalidar: lo demás es diagnóstico interno.
CLAIMS = ("track_record.publico", "audit.veredicto")

_lock = threading.Lock()
_broken = {}          # nodo -> motivo


class NodeUnknownError(KeyError):
    """Nodo que no está en el grafo. Romper algo que nadie declaró no invalida
    nada, así que fallar ruidosamente es mejor que un `break_node` inerte."""


def _check_node(name):
    if name not in GRAPH:
        raise NodeUnknownError(
            "'%s' no está en el grafo. Declaralo en GRAPH junto a lo que cuelga "
            "de él, o el corte no invalidaría nada." % name)


def break_node(name, reason):
    """Marca una fuente como rota. Todo lo que cuelgue deja de ser publicable."""
    _check_node(name)
    with _lock:
        _broken[name] = reason


def heal_node(name):
    """La fuente volvió. Se usa cuando el audit pasa de nuevo, no a mano."""
    _check_node(name)
    with _lock:
        _broken.pop(name, None)


def broken_nodes():
    with _lock:
        return dict(_broken)


def reset():
    """Solo para tests: el estado es global porque el proceso es uno."""
    with _lock:
        _broken.clear()


def ancestors(name):
    """Todos los nodos de los que `name` depende, transitivamente."""
    _check_node(name)
    vistos, pila = set(), list(GRAPH[name])
    while pila:
        n = pila.pop()
        if n in vistos:
            continue
        vistos.add(n)
        pila.extend(GRAPH.get(n, ()))
    return vistos


def is_publishable(claim):
    """(bool, [motivos]). Recorre el grafo hacia arriba: si CUALQUIER ancestro
    está roto, la afirmación no se sostiene aunque sus propias filas estén bien.
    """
    _check_node(claim)
    rotos = broken_nodes()
    culpables = [(n, rotos[n]) for n in sorted({claim} | ancestors(claim))
                 if n in rotos]
    if not culpables:
        return True, []
    return False, ["%s: %s" % (n, r) for n, r in culpables]


def require_publishable(claim):
    """Levanta si la afirmación cuelga de algo roto. El punto de estrangulamiento
    por el que pasa todo lo que sale hacia un cliente."""
    ok, motivos = is_publishable(claim)
    if not ok:
        raise NotPublishableError(
            "'%s' no se puede publicar: %s" % (claim, "; ".join(motivos)))


class NotPublishableError(RuntimeError):
    """Se intentó publicar una afirmación que cuelga de un nodo roto."""


# --- la procedencia de UN número concreto -----------------------------------

def trace(claim, *, rows_in=0, rows_out=0, filters=()):
    """La ficha de procedencia de un número: de cuántas filas salió, qué se le
    quitó y por qué, y de qué nodos cuelga.

    `filters` es una secuencia de (nombre, n_descartadas). Nombrar el filtro
    importa tanto como contar: "23 filas fuera" no explica nada, "23 fuera por
    vida > horizonte" explica el incidente entero.
    """
    _check_node(claim)
    ok, motivos = is_publishable(claim)
    return {
        "claim": claim,
        "rows_in": rows_in,
        "rows_out": rows_out,
        "filters": [{"nombre": n, "descartadas": k} for n, k in filters],
        "depends_on": sorted(ancestors(claim)),
        "publishable": ok,
        "broken": motivos,
    }


def explain(tr, indent="  "):
    """La procedencia en texto: de dónde salió este número, en una pantalla."""
    lineas = ["%sDe dónde sale «%s»:" % (indent, tr["claim"])]
    lineas.append("%s  %d filas leídas -> %d usadas" % (
        indent, tr["rows_in"], tr["rows_out"]))
    for f in tr["filters"]:
        if f["descartadas"]:
            lineas.append("%s  - %d fuera por %s" % (
                indent, f["descartadas"], f["nombre"]))
    lineas.append("%s  cuelga de: %s" % (indent, ", ".join(tr["depends_on"]) or "nada"))
    if not tr["publishable"]:
        lineas.append("%s  NO PUBLICABLE: %s" % (indent, "; ".join(tr["broken"])))
    return "\n".join(lineas)
