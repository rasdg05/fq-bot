# -*- coding: utf-8 -*-
"""
Estadistica pura del ledger. Sin I/O: recibe filas, devuelve numeros.

Compartido por el bot VIP (acceso directo) y el bot publico (read-only),
para que el track record sea identico desde ambos lados.

=============================================================================
  FILTRO DE AUDITABILIDAD  (raiz del incidente del 10-jun-2026)
=============================================================================
Este modulo es el UNICO punto por el que sale el track record publico, asi
que es aqui donde se decide que fila cuenta y cual no.

Que paso: el tracker de outcomes recorria las velas posteriores a la emision
SIN TOPE y solo evaluaba el timeout si no habia tocado nada. Una senal que
debia morir por timeout a las 8h seguia viva indefinidamente. Cuando el
tracker volvio de un downtime largo, replayo un mes de velas y cerro 23
senales de mayo en 763 ms: los 16 shorts a TP4 y los 7 longs a SL, sin un
solo tp1/tp2/tp3/timeout. No era edge — era SOL cayendo un 21% y un barrido
sin horizonte. Ese bloque publicaba WR 60% / E[R] +1.84R / PF 7.23 mientras
el motor con fees del mismo periodo marcaba -0.51R.

La regla, como INVARIANTE y no como parche con fecha:

    una senal cuya vida REGISTRADA excede su propio horizonte de timeout
    no pudo ser producida por un tracker correcto -> no es auditable.

Es auto-verificable (no hay lista de ids ni ventana hardcodeada), captura el
bloque historico exactamente, y vuelve a saltar sola si el bug reaparece por
otra via. Las filas excluidas NO se borran: siguen en el ledger y se reportan
en `n_excluded` para que el numero publicado sea explicable, no solo correcto.

=============================================================================
  DESGLOSE OBLIGATORIO  (la vacuna estructural contra el espejismo de mayo)
=============================================================================
Un numero agregado esconde exactamente lo que hay que ver. GHOST_MAP H1 lo
midio: 2020-22 pagaba LONG (+0.36-0.46) y 2023-25 paga SHORT (+0.21-0.32) —
el lado ganador SE VOLTEA por epoca, y sobre 7 anos el agregado sale +0.224R
para los dos lados, un volado. El fantasma de mayo fue precisamente un
agregado sobre UN solo regimen presentado como ley.

De ahi la regla: **el agregado es el que lleva el asterisco, no el desglose.**
`window_stats` devuelve siempre `by_period`, y `format_expectancy` — el UNICO
renderizador sancionado de una expectancy agregada — LEVANTA si el desglose no
esta. Un periodo con n<%d sale MARCADO en vez de diluido en el promedio.

Que esto no se pueda evitar por descuido lo garantiza `tests/
test_desglose_obligatorio.py` (guarda AST, mismo patron que test_no_wallclock):
ninguna superficie de publicacion puede formatear una expectancy por su cuenta.

=============================================================================
  CRECIMIENTO OBLIGATORIO  (V4 — la media aritmetica no es la cuenta)
=============================================================================
Misma enfermedad, otro eje. E[R] es el promedio del ENSEMBLE; una cuenta vive UNA
trayectoria y compone, y las dos divergen con signo: sobre la celda que opera hoy
(tp1/h288 neto) E[R] = -0.069R y lo que el lector necesita saber es que **el 19%
de las trayectorias acaba por encima del capital inicial**. Sobre la mejor celda
medida (tp4 neto) la media del capital sube (x1.02) mientras la MEDIANA baja
(x0.97): el promedio lo levanta una cola que el suscriptor no va a vivir.

Y hay un parametro que ninguna metrica de este repo puede ver: la fraccion
arriesgada. E[R], IC95% y DSR son todos INVARIANTES a `f` por construccion, asi
que el sistema de medicion es estructuralmente incapaz de detectar sobre-apuesta.
Por eso `window_stats` adjunta siempre `growth` (g, f*, P(acabar arriba)) y
`format_expectancy` LEVANTA sin el.
"""
import os
from datetime import datetime, timezone, timedelta

# Import DURO a proposito (a diferencia de `provenance`, que es defensivo). Alli
# la degradacion correcta es "el numero sale sin traza"; aqui no hay degradacion
# correcta: una expectancy aritmetica sin su tasa de crecimiento describe algo
# distinto de lo que el lector entiende, y publicarla es el fallo, no el fallback.
import growth

WIN_OUTCOMES = ("tp1", "tp2", "tp3", "tp4")

# Por debajo de esto un periodo no concluye — ni a favor ni en contra. Mismo
# criterio que el resto del repo: con muestra chica, ordenar por resultado
# selecciona ruido.
PARTITION_MIN_N = 30


class AggregateWithoutBreakdownError(RuntimeError):
    """Se intento publicar una expectancy agregada sin su desglose al lado.

    No es cosmetica. El track record de mayo (WR 60%, +1.84R) era exacto como
    agregado y falso como afirmacion sobre el sistema, porque describia un mes
    de un solo regimen. Un desglose obligatorio lo habria delatado en el acto.
    """

# Outcomes que por definicion no miden nada: la ventana de velas no cubria la
# vida de la senal, asi que un TP/SL pudo tocarse en el hueco sin verse.
NON_AUDITABLE_OUTCOMES = ("stale",)

# Horizonte de vida de una senal (debe coincidir con
# entropy_cognition.OUTCOME_TIMEOUT_HOURS; se lee del mismo env para que no
# puedan divergir).
OUTCOME_TIMEOUT_HOURS = int(os.environ.get("FQ_OUTCOME_TIMEOUT_HOURS", "8"))

# Gracia sobre el horizonte para filas LEGACY. El tracker viejo media
# minutes_open contra datetime.now() en vez de contra la vela de salida, asi
# que los timeouts legitimos sobrepasan el horizonte por el granulado del ciclo
# de reconcile (observado: 485 min con horizonte de 480). El bloque corrupto
# empieza en 10.326 min, o sea tres ordenes de magnitud arriba: cualquier
# gracia razonable separa limpiamente ambas poblaciones.
AUDIT_GRACE_MINUTES = int(os.environ.get("FQ_LEDGER_AUDIT_GRACE_MIN", "120"))

MAX_AUDITABLE_MINUTES = OUTCOME_TIMEOUT_HOURS * 60 + AUDIT_GRACE_MINUTES


def _get(r, key, default=None):
    """Lector tolerante: acepta sqlite3.Row, dict o mapping. sqlite3.Row lanza
    IndexError si la columna no esta en el SELECT, asi que no basta con .get."""
    try:
        v = r[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if v is None else v


def _pnl(r):
    return _get(r, "pnl_r")


def is_auditable(r):
    """False si la fila no puede sostener una afirmacion sobre el sistema.

    Dos causas:
      1. outcome no auditable ('stale'): hueco de velas sin verificar.
      2. vida registrada > horizonte + gracia: imposible bajo un tracker
         correcto (ver cabecera). Filas sin minutes_open se aceptan: son
         anteriores al campo, no sospechosas por si mismas.
    """
    if _get(r, "outcome") in NON_AUDITABLE_OUTCOMES:
        return False
    mins = _get(r, "minutes_open")
    if mins is None:
        return True
    try:
        return float(mins) <= MAX_AUDITABLE_MINUTES
    except (TypeError, ValueError):
        return True


def filter_auditable(rows):
    """(auditables, n_excluidas). Punto unico de verdad del filtro."""
    rows = rows or []
    keep = [r for r in rows if is_auditable(r)]
    return keep, len(rows) - len(keep)


def period_of(r):
    """Etiqueta de particion de una fila: su regimen si lo trae, si no su ano.

    El ano es el proxy de regimen que SIEMPRE esta disponible en el ledger de
    senales, y es el corte con el que GHOST_MAP H1 midio que el lado ganador se
    voltea. Si alguna vez las filas traen `regime`, manda ese.
    """
    reg = _get(r, "regime")
    if reg:
        return str(reg)
    ts = _get(r, "ts_closed")
    return str(ts)[:4] if ts else "sin fecha"


def _core_stats(rows):
    """Los numeros de un lote YA filtrado. Sin desglose: uso interno."""
    n = len(rows)
    wins = sum(1 for r in rows if _get(r, "outcome") in WIN_OUTCOMES)
    pnls = [p for p in (_pnl(r) for r in rows) if p is not None]
    win_pnl = sum(p for p in pnls if p > 0)
    loss_pnl = abs(sum(p for p in pnls if p < 0))
    return {
        "n":             n,
        "win_rate":      wins / n,
        "expectancy":    (sum(pnls) / len(pnls)) if pnls else 0.0,
        "profit_factor": (win_pnl / loss_pnl) if loss_pnl > 0 else float("inf"),
        "best_pnl":      max(pnls) if pnls else 0.0,
    }


def partition_stats(rows, key=period_of):
    """{periodo: stats} sobre filas YA auditadas, con `thin` marcando n<30.

    `thin` no es decorativo: un periodo de 4 cierres mete su ruido entero en el
    agregado con el mismo peso que uno de 400, y el lector no tiene como saberlo
    si el desglose no se lo dice.
    """
    grupos = {}
    for r in rows:
        grupos.setdefault(key(r), []).append(r)
    out = {}
    for periodo, rs in grupos.items():
        st = _core_stats(rs)
        st["thin"] = st["n"] < PARTITION_MIN_N
        out[periodo] = st
    return dict(sorted(out.items()))


def window_stats(rows):
    """Stats sobre una lista de filas cerradas. None si no queda ninguna
    auditable. `n` cuenta SOLO filas auditables; `n_excluded` deja constancia
    de cuantas se descartaron para que el numero sea explicable.

    Trae SIEMPRE `by_period`: el agregado no viaja nunca sin su desglose, para
    que ninguna superficie pueda publicarlo suelto por descuido (ver cabecera).
    """
    n_in = len(rows or [])
    rows, n_excluded = filter_auditable(rows)
    if not rows:
        return None
    st = _core_stats(rows)
    st["n_excluded"] = n_excluded
    st["by_period"] = partition_stats(rows)
    # V4: la media aritmetica no es lo que le pasa a la cuenta. Viaja SIEMPRE con
    # su tasa de crecimiento, su f* y la probabilidad de acabar arriba — igual que
    # el agregado viaja con su desglose, y por la misma razon.
    st["growth"] = growth.growth_stats(
        [p for p in (_pnl(r) for r in rows) if p is not None])
    # V5: R es adimensional. El agregado viaja tambien con lo que vale en
    # DINERO a la capacidad MEDIDA — misma razon que el desglose y que `g`, y
    # el eje que faltaba: los otros dos corrigen que promedio se publica, este
    # corrige el TAMAÑO del premio, que es lo que decide si algo merece
    # trabajo.
    st["money"] = growth.money_stats(st["expectancy"], n=st["n"])
    # E4: el numero viaja con su procedencia — de cuantas filas salio, que se le
    # quito y de que colectores cuelga. Sin esto, cuando uno se rompe hay que
    # ACORDARSE de que afirmaciones caen, y acordarse es lo que fallo en julio.
    st["provenance"] = _provenance_trace(n_in, len(rows), n_excluded)
    return st


def _provenance_trace(n_in, n_out, n_excluded):
    """Ficha de procedencia del track record. Defensiva: si el modulo no esta
    disponible el numero sigue saliendo (con procedencia vacia), porque romper
    la publicacion por el trazador seria peor que no trazar."""
    try:
        import provenance
        return provenance.trace(
            "track_record.publico", rows_in=n_in, rows_out=n_out,
            filters=(("vida > horizonte / outcome no auditable", n_excluded),))
    except Exception:
        return None


def format_expectancy(stats, *, label="Expectancy", indent="  "):
    """UNICO renderizador sancionado de una expectancy agregada.

    Levanta si le falta el desglose. Ese `raise` es la invariante: hace
    IMPOSIBLE imprimir un E[R] agregado sin que salga al lado de que periodos
    sale — que es lo que el track record de mayo necesitaba y no tenia.
    """
    if not isinstance(stats, dict) or "expectancy" not in stats:
        raise AggregateWithoutBreakdownError("no es un stats con expectancy")
    by = stats.get("by_period")
    if not by:
        raise AggregateWithoutBreakdownError(
            "expectancy agregada sin by_period: un numero agrupado esconde que "
            "el lado ganador se voltea por epoca (GHOST_MAP H1). Usa "
            "window_stats(), que siempre lo adjunta.")
    if "growth" not in stats:
        raise growth.ArithmeticWithoutGrowthError(
            "expectancy aritmetica sin bloque de crecimiento: E[R] describe el "
            "promedio del ensemble, no lo que le pasa a UNA cuenta que compone. "
            "Usa window_stats(), que siempre lo adjunta.")
    # V5: y sin la cifra en DOLARES tampoco sale. R esconde el tamaño del
    # premio: el mismo +0.02R se lee igual siendo $50/mes que siendo $50.000.
    growth.require_money(stats, what="expectancy publicada")
    # E4: si el numero cuelga de un colector roto, no sale. Callar es la
    # consecuencia correcta: un track record que no se puede defender no se
    # publica (misma regla que ya aplicaba audit_signal_ledger).
    try:
        import provenance
        provenance.require_publishable("track_record.publico")
    except ImportError:
        pass
    thin = [p for p, s in by.items() if s["thin"]]
    lineas = ["%s%s %+.2fR  (n=%d, agregado%s)" % (
        indent, label, stats["expectancy"], stats["n"],
        "*" if thin else "")]
    for periodo, s in by.items():
        lineas.append("%s  %-10s %+.2fR  n=%-4d%s" % (
            indent, periodo, s["expectancy"], s["n"],
            "  <- n<%d, no concluye" % PARTITION_MIN_N if s["thin"] else ""))
    if thin:
        lineas.append("%s  * %d periodo(s) con muestra insuficiente entran en el"
                      % (indent, len(thin)))
        lineas.append("%s    agregado con el mismo peso que los demas." % indent)
    lineas.append(growth.format_growth(stats["growth"], indent=indent))
    lineas.append(growth.format_money(stats["money"], indent=indent))
    return "\n".join(lineas)


def longest_win_streak(rows_sorted):
    """Racha ganadora mas larga sobre filas ordenadas por cierre ascendente.
    Las filas no auditables no cuentan como win NI cortan la racha: se sacan
    de la secuencia antes de contar, igual que en window_stats. (Con el filtro
    puesto, la 'racha de 9' del track record publico eran 9 cierres del mismo
    barrido de 763 ms.)"""
    rows, _ = filter_auditable(rows_sorted)
    best = cur = 0
    for r in rows:
        if _get(r, "outcome") in WIN_OUTCOMES:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def summarize(all_rows_sorted, now=None):
    """
    all_rows_sorted: filas cerradas ordenadas por ts_closed ascendente.
    Cada fila debe exponer outcome, pnl_r y ts_closed (ISO). Si ademas expone
    minutes_open, se aplica el filtro de auditabilidad (recomendado: incluye
    minutes_open en el SELECT).
    Devuelve dict con ventanas 30d / 90d / total + racha. None si vacia.
    """
    if not all_rows_sorted:
        return None
    now = now or datetime.now(timezone.utc)
    cutoff_30 = (now - timedelta(days=30)).isoformat()
    cutoff_90 = (now - timedelta(days=90)).isoformat()
    rows_30 = [r for r in all_rows_sorted
               if _get(r, "ts_closed") and r["ts_closed"] >= cutoff_30]
    rows_90 = [r for r in all_rows_sorted
               if _get(r, "ts_closed") and r["ts_closed"] >= cutoff_90]
    return {
        "w30":            window_stats(rows_30),
        "w90":            window_stats(rows_90),
        "total":          window_stats(all_rows_sorted),
        "longest_streak": longest_win_streak(all_rows_sorted),
    }
