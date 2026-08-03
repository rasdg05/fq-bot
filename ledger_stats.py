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
"""
import os
from datetime import datetime, timezone, timedelta

WIN_OUTCOMES = ("tp1", "tp2", "tp3", "tp4")

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


def window_stats(rows):
    """Stats sobre una lista de filas cerradas. None si no queda ninguna
    auditable. `n` cuenta SOLO filas auditables; `n_excluded` deja constancia
    de cuantas se descartaron para que el numero sea explicable."""
    rows, n_excluded = filter_auditable(rows)
    if not rows:
        return None
    n = len(rows)
    wins = sum(1 for r in rows if _get(r, "outcome") in WIN_OUTCOMES)
    pnls = [p for p in (_pnl(r) for r in rows) if p is not None]
    win_pnl  = sum(p for p in pnls if p > 0)
    loss_pnl = abs(sum(p for p in pnls if p < 0))
    return {
        "n":             n,
        "n_excluded":    n_excluded,
        "win_rate":      wins / n,
        "expectancy":    (sum(pnls) / len(pnls)) if pnls else 0.0,
        "profit_factor": (win_pnl / loss_pnl) if loss_pnl > 0 else float("inf"),
        "best_pnl":      max(pnls) if pnls else 0.0,
    }


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
