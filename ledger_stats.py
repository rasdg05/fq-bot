# -*- coding: utf-8 -*-
"""
Estadistica pura del ledger. Sin I/O: recibe filas, devuelve numeros.

Compartido por el bot VIP (acceso directo) y el bot publico (read-only),
para que el track record sea identico desde ambos lados.
"""
from datetime import datetime, timezone, timedelta

WIN_OUTCOMES = ("tp1", "tp2", "tp3", "tp4")


def _pnl(r):
    return r["pnl_r"] if r["pnl_r"] is not None else None


def window_stats(rows):
    """Stats sobre una lista de filas cerradas. None si vacia."""
    if not rows:
        return None
    n = len(rows)
    wins = sum(1 for r in rows if r["outcome"] in WIN_OUTCOMES)
    pnls = [p for p in (_pnl(r) for r in rows) if p is not None]
    win_pnl  = sum(p for p in pnls if p > 0)
    loss_pnl = abs(sum(p for p in pnls if p < 0))
    return {
        "n":             n,
        "win_rate":      wins / n,
        "expectancy":    (sum(pnls) / len(pnls)) if pnls else 0.0,
        "profit_factor": (win_pnl / loss_pnl) if loss_pnl > 0 else float("inf"),
        "best_pnl":      max(pnls) if pnls else 0.0,
    }


def longest_win_streak(rows_sorted):
    """Racha ganadora mas larga sobre filas ordenadas por cierre ascendente."""
    best = cur = 0
    for r in rows_sorted:
        if r["outcome"] in WIN_OUTCOMES:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def summarize(all_rows_sorted, now=None):
    """
    all_rows_sorted: filas cerradas ordenadas por ts_closed ascendente.
    Cada fila debe exponer outcome, pnl_r y ts_closed (ISO).
    Devuelve dict con ventanas 30d / 90d / total + racha. None si vacia.
    """
    if not all_rows_sorted:
        return None
    now = now or datetime.now(timezone.utc)
    cutoff_30 = (now - timedelta(days=30)).isoformat()
    cutoff_90 = (now - timedelta(days=90)).isoformat()
    rows_30 = [r for r in all_rows_sorted if r["ts_closed"] and r["ts_closed"] >= cutoff_30]
    rows_90 = [r for r in all_rows_sorted if r["ts_closed"] and r["ts_closed"] >= cutoff_90]
    return {
        "w30":            window_stats(rows_30),
        "w90":            window_stats(rows_90),
        "total":          window_stats(all_rows_sorted),
        "longest_streak": longest_win_streak(all_rows_sorted),
    }
