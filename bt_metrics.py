# -*- coding: utf-8 -*-
"""
================================================================================
  BT METRICS - metricas de riesgo institucionales
  by RasDG_Sol + Claude

  Etapa 5 del harness de research. Convierte la salida del engine (serie de
  retornos + curva de equity) en las metricas que un fondo mira primero:

    - Sharpe, Sortino (riesgo-ajustado)
    - max drawdown + Calmar (retorno / dolor)
    - profit factor, expectancy en R, win rate
    - CAGR, retorno total

  Extiende la linea de ledger_stats.py (win_rate / expectancy / profit_factor)
  para que el track record real y el backtest hablen el mismo idioma.

  Pieza pura: arrays/Series in, numeros out. Sin I/O. Robusta a muestras chicas
  (devuelve None o 0.0 en vez de NaN/division por cero).

  Nota de anualizacion: el Sharpe sobre retornos POR TRADE se anualiza con
  sqrt(periods_per_year). Pasa periods_per_year ~ trades/ano esperados para una
  cifra comparable; sin el, el Sharpe es por-trade (sin anualizar).
================================================================================
"""
import logging

import numpy as np
import pandas as pd

log = logging.getLogger("bt_metrics")


def _as_array(x):
    return np.asarray(x, dtype="float64")


# ============================================================
# DRAWDOWN
# ============================================================
def drawdown_series(equity):
    """Serie de drawdown relativo al pico (<= 0). equity: array/Series."""
    eq = _as_array(equity)
    if len(eq) == 0:
        return np.array([])
    peak = np.maximum.accumulate(eq)
    return eq / peak - 1.0


def max_drawdown(equity):
    """Devuelve (max_dd, peak_idx, trough_idx). max_dd <= 0 (fraccion)."""
    eq = _as_array(equity)
    if len(eq) == 0:
        return 0.0, None, None
    dd = drawdown_series(eq)
    trough = int(np.argmin(dd))
    max_dd = float(dd[trough])
    peak = int(np.argmax(eq[:trough + 1])) if trough > 0 else 0
    return max_dd, peak, trough


# ============================================================
# RATIOS RIESGO-AJUSTADO
# ============================================================
def sharpe(returns, risk_free=0.0, periods_per_year=None):
    """Sharpe de una serie de retornos. Anualizado si periods_per_year.

    None si no hay suficiente muestra o desviacion nula.
    """
    r = _as_array(returns)
    if len(r) < 2:
        return None
    excess = r - risk_free
    sd = excess.std(ddof=1)
    if sd == 0:
        return None
    ratio = excess.mean() / sd
    if periods_per_year:
        ratio *= np.sqrt(periods_per_year)
    return float(ratio)


def sortino(returns, risk_free=0.0, periods_per_year=None, target=0.0):
    """Sortino: usa solo la desviacion a la baja (downside deviation)."""
    r = _as_array(returns)
    if len(r) < 2:
        return None
    excess = r - risk_free
    downside = np.minimum(excess - target, 0.0)
    dd = np.sqrt(np.mean(downside ** 2))
    if dd == 0:
        return None
    ratio = (excess.mean() - target) / dd
    if periods_per_year:
        ratio *= np.sqrt(periods_per_year)
    return float(ratio)


def cagr(equity, periods_per_year):
    """Tasa de crecimiento anual compuesta a partir de la curva de equity.

    Trata cada paso de la curva como un periodo. None si faltan datos.
    """
    eq = _as_array(equity)
    if len(eq) < 2 or eq[0] <= 0 or not periods_per_year:
        return None
    n_periods = len(eq) - 1
    total_growth = eq[-1] / eq[0]
    if total_growth <= 0:
        return -1.0
    return float(total_growth ** (periods_per_year / n_periods) - 1.0)


def calmar(equity, periods_per_year):
    """Calmar = CAGR / |max drawdown|. None si no computable."""
    c = cagr(equity, periods_per_year)
    mdd, _, _ = max_drawdown(equity)
    if c is None or mdd == 0:
        return None
    return float(c / abs(mdd))


# ============================================================
# RENTABILIDAD / CONSISTENCIA
# ============================================================
def profit_factor(pnls):
    """Suma de ganancias / |suma de perdidas|. inf si no hay perdidas."""
    p = _as_array(pnls)
    if len(p) == 0:
        return None
    gains = p[p > 0].sum()
    losses = abs(p[p < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def win_rate(pnls):
    p = _as_array(pnls)
    if len(p) == 0:
        return None
    return float((p > 0).mean())


# ============================================================
# REPORTE COMPLETO
# ============================================================
def compute_metrics(returns=None, equity_curve=None, pnl=None, pnl_r=None,
                    periods_per_year=None, risk_free=0.0):
    """Reune todas las metricas en un dict. Cualquier insumo ausente se omite.

    returns      : retornos por trade (para Sharpe/Sortino).
    equity_curve : curva de equity (para drawdown/CAGR/Calmar/retorno total).
    pnl          : pnl por trade en quote (para profit factor / win rate).
    pnl_r        : pnl por trade en R (para expectancy_r).
    periods_per_year: para anualizar Sharpe/Sortino y CAGR/Calmar.
    """
    out = {}

    if returns is not None:
        r = _as_array(returns)
        out["n_trades"] = int(len(r))
        out["mean_return"] = float(r.mean()) if len(r) else None
        out["std_return"] = float(r.std(ddof=1)) if len(r) > 1 else None
        out["sharpe"] = sharpe(r, risk_free, periods_per_year)
        out["sortino"] = sortino(r, risk_free, periods_per_year)
        if len(r):
            out["win_rate"] = float((r > 0).mean())

    if pnl is not None:
        p = _as_array(pnl)
        out["profit_factor"] = profit_factor(p)
        if "win_rate" not in out:
            out["win_rate"] = win_rate(p)
        wins = p[p > 0]
        losses = p[p < 0]
        out["avg_win"] = float(wins.mean()) if len(wins) else 0.0
        out["avg_loss"] = float(losses.mean()) if len(losses) else 0.0

    if pnl_r is not None:
        pr = _as_array(pnl_r)
        out["expectancy_r"] = float(pr.mean()) if len(pr) else None
        out["total_r"] = float(pr.sum()) if len(pr) else None

    if equity_curve is not None:
        eq = _as_array(equity_curve)
        if len(eq) >= 1:
            out["final_equity"] = float(eq[-1])
            if eq[0] > 0:
                out["total_return"] = float(eq[-1] / eq[0] - 1.0)
        mdd, peak_i, trough_i = max_drawdown(eq)
        out["max_drawdown"] = mdd
        out["max_dd_peak_idx"] = peak_i
        out["max_dd_trough_idx"] = trough_i
        if periods_per_year:
            out["cagr"] = cagr(eq, periods_per_year)
            out["calmar"] = calmar(eq, periods_per_year)

    return out


def metrics_from_result(result, periods_per_year=None, risk_free=0.0):
    """Conveniencia: toma el dict de bt_engine.simulate() y saca el reporte."""
    trades = result.get("trades")
    pnl = trades["net_pnl"] if trades is not None and "net_pnl" in trades else None
    pnl_r = trades["net_pnl_r"] if trades is not None and "net_pnl_r" in trades else None
    return compute_metrics(
        returns=result.get("returns"),
        equity_curve=result.get("equity_curve"),
        pnl=pnl,
        pnl_r=pnl_r,
        periods_per_year=periods_per_year,
        risk_free=risk_free,
    )


def format_report(metrics):
    """Render legible (una metrica por linea) para CLI/logs."""
    def fmt(v):
        if v is None:
            return "n/a"
        if isinstance(v, float):
            return f"{v:,.4f}"
        return str(v)
    order = [
        "n_trades", "win_rate", "expectancy_r", "total_r",
        "profit_factor", "avg_win", "avg_loss",
        "mean_return", "std_return", "sharpe", "sortino",
        "total_return", "cagr", "calmar", "max_drawdown", "final_equity",
    ]
    lines = []
    for k in order:
        if k in metrics:
            lines.append(f"  {k:<16} {fmt(metrics[k])}")
    return "\n".join(lines)
