# -*- coding: utf-8 -*-
"""Estadistica pura del ledger: correccion de ventanas, win rate, PF, racha."""
from datetime import datetime, timezone, timedelta

import ledger_stats


def _row(outcome, pnl, days_ago):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {"outcome": outcome, "pnl_r": pnl, "ts_closed": ts}


def test_window_stats_basic():
    rows = [_row("tp1", 1.0, 1), _row("sl", -1.0, 2), _row("tp2", 2.0, 3)]
    s = ledger_stats.window_stats(rows)
    assert s["n"] == 3
    assert abs(s["win_rate"] - 2 / 3) < 1e-9
    assert abs(s["expectancy"] - (1.0 - 1.0 + 2.0) / 3) < 1e-9
    # PF = ganancias / perdidas = 3.0 / 1.0
    assert abs(s["profit_factor"] - 3.0) < 1e-9
    assert s["best_pnl"] == 2.0


def test_window_stats_empty():
    assert ledger_stats.window_stats([]) is None


def test_profit_factor_no_losses_is_inf():
    rows = [_row("tp1", 1.0, 1), _row("tp2", 2.0, 2)]
    assert ledger_stats.window_stats(rows)["profit_factor"] == float("inf")


def test_longest_win_streak():
    rows = [_row("tp1", 1, 9), _row("tp1", 1, 8), _row("sl", -1, 7),
            _row("tp1", 1, 6), _row("tp2", 1, 5), _row("tp3", 1, 4), _row("sl", -1, 3)]
    assert ledger_stats.longest_win_streak(rows) == 3


def test_summarize_windows():
    rows = [_row("tp3", 1.8, 5), _row("tp1", 0.9, 10), _row("sl", -1.0, 20),
            _row("tp2", 1.4, 40), _row("tp4", 2.5, 70), _row("sl", -1.0, 120)]
    rows.sort(key=lambda r: r["ts_closed"])
    s = ledger_stats.summarize(rows)
    assert s["w30"]["n"] == 3      # 5,10,20 dias
    assert s["w90"]["n"] == 5      # + 40,70
    assert s["total"]["n"] == 6


def test_summarize_empty():
    assert ledger_stats.summarize([]) is None
