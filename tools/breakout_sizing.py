#!/usr/bin/env python3
"""breakout_sizing — la matemática de riesgo para PASAR el challenge de Breakout (prop firm,
perps cripto, liquidez Kraken). Convierte la estrategia de `rutas-capital-operativas-2026.md`
en código: el motor tiene WR BAJO (~28%) y edge chico, y el límite que MANDA es el **6% de
drawdown estático** → el sizing es todo.

Idea central (sin parámetros mágicos, falsable): si arriesgas `risk_pct` por trade, rompes el DD
con `floor(max_dd / risk_pct)` pérdidas-R seguidas. Eliges `risk_pct` para sobrevivir una racha
P99 dado tu win-rate. Default 0.4% → 15 pérdidas seguidas para reventar (P≈0.7% a WR 28%).

Reglas 1-Step (CONFIRMAR en checkout — fuente secundaria): objetivo +10%, DD máx 6% estático,
pérdida diaria 4%, sin límite de tiempo, leverage 5x BTC/ETH. Defaults abajo; se sobreescriben.

  python tools/breakout_sizing.py --demo --balance 5000 --win-rate 0.28
  # import: position_size(...), trade_allowed(...), plan(...)
"""
import argparse

# Defaults del challenge + la estrategia (todos overridables).
MAX_DD_PCT = 6.0          # drawdown máximo estático (piso fijo en 94% del balance inicial)
DAILY_LOSS_LIMIT = 4.0    # pérdida diaria máx del challenge
DAILY_STOP_PCT = 2.0      # stop diario AUTO-impuesto (mitad del límite legal)
PROFIT_TARGET = 10.0      # objetivo del challenge
RISK_PCT = 0.4            # riesgo por trade recomendado (sobrevive racha P99 a WR ~28%)


def position_size(balance, entry, stop, *, risk_pct=RISK_PCT):
    """Unidades a operar para que tocar el stop pierda exactamente `risk_pct`% del balance.
    Devuelve 0.0 si entry==stop (sin riesgo definido)."""
    per_unit = abs(float(entry) - float(stop))
    if per_unit <= 0:
        return 0.0
    return (float(balance) * (risk_pct / 100.0)) / per_unit


def streak_to_breach(risk_pct=RISK_PCT, *, max_dd_pct=MAX_DD_PCT):
    """Cuántas pérdidas-R SEGUIDAS rompen el DD (conservador: sin netear ganancias)."""
    if risk_pct <= 0:
        return float("inf")
    return int(max_dd_pct / risk_pct + 1e-9)   # +eps: 6.0//0.4 da 14 por flotantes; queremos 15


def streak_prob(win_rate, n_losses):
    """P(n pérdidas seguidas) = (1-WR)^n. El juez de si `risk_pct` es seguro."""
    return (1.0 - float(win_rate)) ** int(n_losses)


def risk_pct_for_survival(win_rate, *, max_dd_pct=MAX_DD_PCT, tail=0.01):
    """El MAYOR risk_pct (en pasos de 0.05) cuya racha-a-romper tiene P <= `tail` (P99 por
    default). Así el sizing se ata al win-rate real, no a un número arbitrario."""
    r = 0.05
    best = 0.05
    while r <= max_dd_pct:
        n = streak_to_breach(r, max_dd_pct=max_dd_pct)
        if streak_prob(win_rate, n) <= tail:
            best = r
        r = round(r + 0.05, 2)
    return best


def dd_remaining_pct(balance, initial_balance, *, max_dd_pct=MAX_DD_PCT):
    """% de balance que falta para tocar el piso estático (94% del inicial). <=0 => violado."""
    floor_ = float(initial_balance) * (1.0 - max_dd_pct / 100.0)
    return (float(balance) - floor_) / float(initial_balance) * 100.0


def trade_allowed(balance, initial_balance, day_pnl_pct, *,
                  max_dd_pct=MAX_DD_PCT, daily_stop_pct=DAILY_STOP_PCT):
    """¿Se permite ABRIR un trade nuevo? No si ya tocamos el stop diario o el DD."""
    if day_pnl_pct <= -abs(daily_stop_pct):
        return False
    if dd_remaining_pct(balance, initial_balance, max_dd_pct=max_dd_pct) <= 0:
        return False
    return True


def trades_to_target(expectancy_r, *, risk_pct=RISK_PCT, target=PROFIT_TARGET):
    """Estimación de trades para llegar al objetivo: cada trade gana (en %) expectancy_R*risk_pct.
    inf si la expectativa es <=0 (sin edge no se llega)."""
    gain_per_trade = float(expectancy_r) * risk_pct
    if gain_per_trade <= 0:
        return float("inf")
    return int(target / gain_per_trade + 0.999)


def plan(balance, *, win_rate=0.28, expectancy_r=0.20, risk_pct=RISK_PCT):
    """Devuelve un dict con el plan numérico concreto para un balance dado."""
    n_breach = streak_to_breach(risk_pct)
    rec = risk_pct_for_survival(win_rate)
    return {
        "balance": float(balance),
        "risk_pct": risk_pct,
        "risk_per_trade_$": round(balance * risk_pct / 100.0, 2),
        "daily_stop_$": round(balance * DAILY_STOP_PCT / 100.0, 2),
        "dd_floor_$": round(balance * (1 - MAX_DD_PCT / 100.0), 2),
        "losses_to_breach_dd": n_breach,
        "p_that_streak": round(streak_prob(win_rate, n_breach), 5),
        "risk_pct_recomendado_P99": rec,
        "trades_to_target_est": trades_to_target(expectancy_r, risk_pct=risk_pct),
    }


def _fmt(d):
    return "\n".join("  %-24s %s" % (k, v) for k, v in d.items())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--demo", action="store_true")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--balance", type=float, default=5000.0)
    p.add_argument("--win-rate", type=float, default=0.28)
    p.add_argument("--expectancy-r", type=float, default=0.20)
    p.add_argument("--risk-pct", type=float, default=RISK_PCT)
    a = p.parse_args(argv)
    if a.self_test:
        return _self_test()
    if a.demo:
        pl = plan(a.balance, win_rate=a.win_rate, expectancy_r=a.expectancy_r, risk_pct=a.risk_pct)
        print("Plan Breakout — balance $%.0f, WR %.0f%%, expectancy %.2fR:" %
              (a.balance, a.win_rate * 100, a.expectancy_r))
        print(_fmt(pl))
        print("  (size de ejemplo: entry 100, stop 98 -> %.4f unidades)" %
              position_size(a.balance, 100, 98, risk_pct=a.risk_pct))
        return 0
    print("usa --demo [--balance --win-rate --expectancy-r --risk-pct] o --self-test")
    return 0


def _self_test():
    # 0.4% riesgo -> 15 pérdidas para romper 6%; a WR 28% esa racha es P99-rara.
    assert streak_to_breach(0.4) == 15
    assert streak_prob(0.28, 15) < 0.01
    # 1% riesgo -> solo 6 pérdidas: peligroso.
    assert streak_to_breach(1.0) == 6
    # sizing: $5000, riesgo 0.4% = $20; stop a 2 de distancia -> 10 unidades.
    assert abs(position_size(5000, 100, 98, risk_pct=0.4) - 10.0) < 1e-9
    # gating: stop diario y DD.
    assert trade_allowed(5000, 5000, day_pnl_pct=-1.0) is True
    assert trade_allowed(5000, 5000, day_pnl_pct=-2.0) is False        # tocó stop diario
    assert trade_allowed(4699, 5000, day_pnl_pct=0.0) is False          # bajo el piso 4700
    assert dd_remaining_pct(5000, 5000) == 6.0
    # sin edge no se llega al objetivo.
    assert trades_to_target(0.0) == float("inf")
    assert trades_to_target(0.20, risk_pct=0.4) == 125                  # 10% / (0.2*0.4)
    print("self-test OK — plan $5000 WR28%:")
    print(_fmt(plan(5000)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
