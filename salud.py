# -*- coding: utf-8 -*-
"""
================================================================================
  SALUD — ¿me puedo fiar de lo que este sistema publica, ahora mismo?
================================================================================

`_ledger_health`, `n_excluded`, `MOTOR_FILL_REJECTED`, `cvd_staleness_min`,
`bars_held`: todo escrito, nada visible. Cinco arreglos invisibles no son
producto — son cinco cosas que hay que acordarse de ir a mirar, y acordarse es
exactamente lo que fallo en julio.

Esto las junta en una respuesta que se entiende a las 3 de la manana, medio
dormido, desde el telefono. De ahi las tres reglas de escritura:

  1. El VEREDICTO va primero y en una linea. Si todo esta bien no hay que leer
     nada mas.
  2. Cada chequeo dice que significa PARA LO QUE SE PUBLICA, no que variable
     interna esta en que valor. "El track record esta suspendido" es util;
     "_ledger_health.ok = False" no lo es a esa hora.
  3. Lo que esta mal trae QUE HACER. Un diagnostico sin siguiente paso obliga a
     reconstruir el contexto entero justo cuando menos cabeza hay.

El modulo es PURO: recibe hechos ya leidos y devuelve texto. El I/O (que puede
fallar, y a las 3am falla) vive en `gather()`, que atrapa todo y convierte cada
fallo en un chequeo DESCONOCIDO en vez de tumbar el comando. Un panel de salud
que se cae con el sistema no sirve de nada.
================================================================================
"""
OK = "ok"
WARN = "revisar"
BROKEN = "roto"
UNKNOWN = "?"

# Orden de gravedad: el veredicto global es el peor de los chequeos.
_SEVERIDAD = {OK: 0, UNKNOWN: 1, WARN: 2, BROKEN: 3}

_GLIFO = {OK: "✅", WARN: "⚠️", BROKEN: "🛑", UNKNOWN: "❔"}

# Un colector con mas de esto sin escribir no esta midiendo, esta contestando.
CVD_STALE_MIN = 60.0
# Por encima de esta fraccion de filas excluidas, el numero publicado describe
# mas lo que se tiro que lo que se midio.
EXCLUIDAS_WARN = 0.10


def _check(clave, estado, titulo, detalle="", accion=""):
    return {"clave": clave, "estado": estado, "titulo": titulo,
            "detalle": detalle, "accion": accion}


def check_track_record(health):
    """¿El track record es fiable? Es LA pregunta: si no, lo demas da igual."""
    if not health:
        return _check("track_record", UNKNOWN, "Track record: sin auditar aun",
                      accion="Corre /audit para que haya veredicto.")
    if not health.get("ok", True):
        razones = "; ".join(health.get("reasons") or []) or "sin detalle"
        return _check("track_record", BROKEN,
                      "Track record SUSPENDIDO — no se esta publicando",
                      detalle=razones,
                      accion="El tracker de outcomes esta produciendo cierres "
                             "imposibles. NO publiques numeros hasta arreglarlo.")
    if health.get("reasons"):
        return _check("track_record", WARN, "Track record fiable, con avisos",
                      detalle="; ".join(health["reasons"]),
                      accion="Integridad OK; el aviso es de deriva, no de datos.")
    return _check("track_record", OK, "Track record fiable",
                  detalle="n=%s cerradas auditadas" % health.get("n"))


def check_exclusiones(n_total, n_excluded):
    """¿Cuantas filas se excluyen y por que?

    Las excluidas no se borran nunca: son la prueba de que el numero publicado
    es explicable y no solo correcto. Que sean MUCHAS es en si mismo la senal.
    """
    if not n_total:
        return _check("exclusiones", UNKNOWN, "Exclusiones: sin cierres todavia")
    frac = n_excluded / float(n_total)
    detalle = ("%d de %d filas fuera (%.0f%%) — vida registrada > horizonte, o "
               "outcome 'stale'" % (n_excluded, n_total, frac * 100))
    if frac >= EXCLUIDAS_WARN:
        return _check("exclusiones", WARN, "Se esta excluyendo mucho", detalle,
                      accion="Con esa fraccion fuera, el numero describe mas lo "
                             "que se tiro que lo que se midio. Mira el tracker.")
    return _check("exclusiones", OK, "Exclusiones normales", detalle)


def check_cvd(staleness_min, activo=True):
    """¿El CVD esta fresco? Un colector parado contesta como si midiera."""
    if not activo:
        return _check("cvd", OK, "CVD apagado (no se usa)",
                      detalle="Sin FQ_CVD_FILTER no hay nada que envejecer.")
    if staleness_min is None:
        return _check("cvd", WARN, "CVD sin datos utilizables",
                      detalle="El colector no devuelve ventana valida.",
                      accion="Revisa FQ_CVD_COLLECT y el parquet en /data.")
    if staleness_min > CVD_STALE_MIN:
        return _check("cvd", BROKEN, "CVD RANCIO — %.0f min sin escribir" % staleness_min,
                      detalle="Un colector parado da confirmaciones constantes "
                              "indistinguibles de una medicion viva (paso en jul-2026).",
                      accion="Reinicia el colector. Las confirmaciones de este "
                             "rato no valen como medicion.")
    return _check("cvd", OK, "CVD fresco (%.0f min)" % staleness_min)


def check_fills(n_rejected, n_opened):
    """¿Cuantos fills se rechazaron? Es el gate donde vive el 80% de la perdida."""
    total = (n_rejected or 0) + (n_opened or 0)
    if not total:
        return _check("fills", UNKNOWN, "Fills: sin actividad todavia")
    frac = (n_rejected or 0) / float(total)
    detalle = "%d rechazados de %d intentos (%.0f%%) por fill demasiado rapido" % (
        n_rejected or 0, total, frac * 100)
    if frac >= 0.5:
        return _check("fills", WARN, "Se rechaza mas de la mitad de los fills",
                      detalle,
                      accion="El gate esta protegiendo de seleccion adversa, pero "
                             "a este ritmo la cadencia se muere. Mira si "
                             "FQ_MOTOR_MIN_FILL_BARS esta de mas.")
    return _check("fills", OK, "Rechazo de fills normal", detalle)


def check_audit(health, ahora_iso=None):
    """¿Cuando corrio el ultimo audit y con que veredicto?

    Un audit viejo es un audit que no protege: si lleva dias sin correr, su
    'ok' describe un sistema que ya no existe.
    """
    if not health or not health.get("ts"):
        return _check("audit", WARN, "El audit no ha corrido nunca",
                      accion="Corre /audit. Sin el, 'fiable' es una suposicion.")
    ts = str(health["ts"])
    veredicto = "sin hallazgos" if health.get("ok", True) else "CON HALLAZGOS"
    detalle = "ultimo: %s — %s" % (ts[:16].replace("T", " "), veredicto)
    if ahora_iso and ts[:10] < str(ahora_iso)[:10]:
        return _check("audit", WARN, "El audit no corre desde ayer o antes",
                      detalle,
                      accion="Un audit viejo describe un sistema que ya no existe.")
    return _check("audit", OK, "Audit al dia", detalle)


def check_procedencia(rotos=None, claims=None):
    """E4: ¿hay algún nodo roto, y qué se cae con él?

    Es la pregunta que en julio nadie hizo. No basta con "el colector está
    caído": hay que saber qué afirmaciones dejan de sostenerse por eso, y que la
    respuesta salga sola en vez de reconstruirse de memoria.
    """
    if not rotos:
        return _check("procedencia", OK, "Ninguna fuente rota")
    caidas = [c for c in (claims or ()) if not c[1]]
    detalle = "; ".join("%s (%s)" % (n, r) for n, r in sorted(rotos.items()))
    return _check("procedencia", BROKEN,
                  "Fuentes rotas: %d" % len(rotos), detalle,
                  accion="Se cae: %s. No se publica hasta que la fuente vuelva."
                         % (", ".join(n for n, _ in caidas) or "nada publicable"))


def veredicto(checks):
    """El peor estado manda. Un solo chequeo roto rompe el conjunto."""
    if not checks:
        return UNKNOWN
    return max((c["estado"] for c in checks), key=lambda e: _SEVERIDAD[e])


_TITULAR = {
    OK: "TODO EN ORDEN — lo que se publica se sostiene.",
    WARN: "HAY QUE MIRAR ALGO — nada roto, pero no lo dejes correr.",
    BROKEN: "ALGO ESTA ROTO — no publiques numeros hasta resolverlo.",
    UNKNOWN: "SIN DATOS SUFICIENTES para decir nada.",
}


def render(checks, titulo="Salud del sistema"):
    """Texto para Telegram. Veredicto arriba; el detalle solo si hace falta."""
    v = veredicto(checks)
    lineas = ["<b>%s %s</b>" % (_GLIFO[v], titulo), "", _TITULAR[v], ""]
    for c in checks:
        lineas.append("%s %s" % (_GLIFO[c["estado"]], c["titulo"]))
        if c.get("detalle"):
            lineas.append("    %s" % c["detalle"])
        # La accion solo cuando hay algo que hacer: en verde, ruido.
        if c.get("accion") and c["estado"] != OK:
            lineas.append("    → %s" % c["accion"])
    return "\n".join(lineas)


def gather(*, health=None, n_total=None, n_excluded=None, cvd_staleness_min=None,
           cvd_activo=True, n_rejected=None, n_opened=None, ahora_iso=None,
           rotos=None, claims=None):
    """Los chequeos, en orden de lo que mas importa a las 3am."""
    return [
        check_track_record(health),
        check_audit(health, ahora_iso),
        check_procedencia(rotos, claims),
        check_exclusiones(n_total, n_excluded),
        check_cvd(cvd_staleness_min, activo=cvd_activo),
        check_fills(n_rejected, n_opened),
    ]


def _safe(fn, default=None):
    """Cada lectura por separado: un colector caido no puede tumbar el panel."""
    try:
        return fn()
    except Exception:
        return default


def gather_live(*, ahora_iso=None):
    """Igual que `gather` pero leyendo el sistema vivo. Nunca lanza."""
    import os

    health = _safe(lambda: __import__("entropy_cognition").get_ledger_health(), {})

    def _rows():
        import entropy_cognition as ec
        import ledger_stats as ls
        rows = ec.get_closed_rows_for_audit()
        keep, excl = ls.filter_auditable(rows)
        return len(rows), excl

    n_total, n_excluded = _safe(_rows, (None, None))

    def _fills():
        import motor_paper
        rep = motor_paper.ledger_report(
            os.environ.get("FQ_MOTOR_PAPER_LEDGER_PATH",
                           "/data/motor_paper_SOL_USDT.jsonl")) or {}
        return rep.get("n_fill_rejected"), rep.get("n_open_meta")

    n_rejected, n_opened = _safe(_fills, (None, None))

    cvd_activo = os.environ.get("FQ_CVD_FILTER", "0").strip() in ("1", "true", "yes")
    staleness = _safe(lambda: _cvd_staleness(), None) if cvd_activo else None

    def _proc():
        import provenance
        return (provenance.broken_nodes(),
                [(c, provenance.is_publishable(c)[0]) for c in provenance.CLAIMS])

    rotos, claims = _safe(_proc, ({}, []))

    return gather(health=health, n_total=n_total, n_excluded=n_excluded,
                  cvd_staleness_min=staleness, cvd_activo=cvd_activo,
                  n_rejected=n_rejected, n_opened=n_opened, ahora_iso=ahora_iso,
                  rotos=rotos, claims=claims)


def _cvd_staleness():
    """Minutos desde la ultima barra del colector CVD. None si no se puede saber."""
    import os
    import time
    path = os.environ.get("FQ_CVD_COLLECT")
    if not path or not os.path.exists(path):
        return None
    import pandas as pd
    df = pd.read_parquet(path, columns=["ts"])
    if df.empty:
        return None
    return round((time.time() * 1000.0 - float(df["ts"].max())) / 60_000.0, 1)
