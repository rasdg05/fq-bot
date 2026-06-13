# -*- coding: utf-8 -*-
"""
================================================================================
  BT ENGINE - motor de backtest/replay con costes realistas
  by RasDG_Sol + Claude

  Etapa 4 del harness de research. Toma las senales ya resueltas por el labeler
  (entry/stop/exit/direction/bars_held) y las EJECUTA con costes de mercado
  reales, produciendo trades netos y la curva de equity en quote (USDT):

    - fees taker por lado (entrada y salida) sobre el notional,
    - slippage adverso por lado (llenas peor de lo que marca el precio),
    - funding del perpetuo prorrateado por el tiempo en posicion (en SOL el
      funding se come el edge en swing si no se modela),
    - sizing por riesgo fijo (% del equity al stop), con compounding.

  Es el 'artefacto unico': su salida es a la vez el backtest, la base out-of-
  sample (corriendolo por fold) y la serie de retornos de la que bt_metrics saca
  Sharpe/Sortino/Calmar/drawdown.

  Pieza pura: recibe un DataFrame de trades, devuelve trades enriquecidos +
  equity. No toca red ni estado.
================================================================================
"""
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

log = logging.getLogger("bt_engine")

LONG = 1
SHORT = -1


@dataclass
class CostModel:
    """Costes de ejecucion. Defaults ~ Binance USDT-perp (taker ambos lados).

    Piernas maker (jun-2026, frontera de ejecucion): el sistema entra cuando
    el precio LLEGA a un nivel y el TP es un precio conocido — ambos son
    territorio natural de orden LIMITE (fee maker, sin slippage). OJO: esto
    asume fill del 100% en el nivel, que es OPTIMISTA (adverse selection: las
    que se escapan sin llenar suelen ser ganadoras). Por eso estas flags miden
    el TECHO en research; la captura realista la mide el fill-model del paper
    (FQ_GOLD_MAKER_SIM). El STOP siempre es taker (cruza el book por diseno) y
    el timeout tambien (cierre a mercado).
    """
    taker_fee: float = 0.0005       # 5 bps por lado sobre notional
    slippage_bps: float = 1.0       # 1 bp adverso por lado, sobre precio
    funding_rate_8h: float = 0.0001  # tasa de funding por ventana de 8h
    apply_funding: bool = True
    maker_fee: float = 0.0002       # 2 bps OKX USDT-perp (tier regular)
    maker_entry: bool = False       # entrada como limite pasiva en el nivel
    maker_tp_exit: bool = False     # TP como limite descansando (solo outcome win)

    @property
    def slippage_frac(self):
        return self.slippage_bps / 10_000.0


def simulate(
    trades,
    equity0=10_000.0,
    risk_frac=0.01,
    bar_minutes=1.0,
    cost=None,
    max_leverage=None,
    stop_on_ruin=True,
):
    """Ejecuta una secuencia de trades y construye la curva de equity.

    trades: DataFrame con columnas (una fila por senal, en orden cronologico):
        entry_price, stop_price, exit_price, direction (LONG/SHORT), bars_held
      (acepta directamente la salida de bt_labeler.label_events; columnas extra
       se preservan). Las filas sin resolver (exit_price/bars_held nulos) se
       saltan.
    equity0: capital inicial (quote).
    risk_frac: fraccion del equity arriesgada al stop por trade (0.01 = 1%).
    bar_minutes: minutos por vela (para prorratear funding por bars_held).
    cost: CostModel; si None usa defaults.
    max_leverage: si se da, capa el notional a equity*max_leverage.
    stop_on_ruin: si el equity cae <= 0, detiene (bancarrota).

    Devuelve dict:
      trades       : DataFrame de entrada + columnas de ejecucion
      equity_curve : Series de equity tras cada trade (incluye el punto inicial)
      returns      : Series de retornos por trade (net_pnl / equity_previo)
      final_equity : equity final
      n_trades     : trades ejecutados
      total_fees, total_funding, total_slippage_cost : agregados (quote)
      ruin         : True si se detuvo por bancarrota
    """
    cost = cost or CostModel()
    rows = []
    equity = float(equity0)
    equity_points = [equity]
    returns = []
    tot_fees = tot_funding = tot_slip = 0.0
    ruin = False

    for _, t in trades.iterrows():
        if t.get("exit_price") is None or pd.isna(t.get("exit_price")):
            continue
        if pd.isna(t.get("bars_held")):
            continue

        d = int(t["direction"])
        entry = float(t["entry_price"])
        stop = float(t["stop_price"])
        exit_px = float(t["exit_price"])
        bars_held = float(t["bars_held"])

        stop_dist = abs(entry - stop)
        if stop_dist <= 0:
            continue

        risk_amount = equity * risk_frac
        qty = risk_amount / stop_dist            # unidades de base
        notional_entry = qty * entry
        if max_leverage is not None:
            cap = equity * max_leverage
            if notional_entry > cap:
                qty = cap / entry
                notional_entry = cap

        # Piernas maker: entrada (si esta activado) y TP (solo si el trade
        # SALIO por target, outcome 'win'); stop y timeout cruzan el book ->
        # siempre taker. Una pierna maker no paga slippage (el precio lo
        # pones tu); el fill 100% asumido es el TECHO (ver CostModel).
        entry_maker = bool(cost.maker_entry)
        exit_maker = bool(cost.maker_tp_exit) and str(t.get("outcome", "")) == "win"

        # Slippage adverso: compras mas caro / vendes mas barato segun lado.
        eff_entry = entry if entry_maker else entry * (1 + d * cost.slippage_frac)
        eff_exit = exit_px if exit_maker else exit_px * (1 - d * cost.slippage_frac)

        gross_pnl = d * (eff_exit - eff_entry) * qty

        notional_exit = qty * exit_px
        fees = ((cost.maker_fee if entry_maker else cost.taker_fee) * notional_entry
                + (cost.maker_fee if exit_maker else cost.taker_fee) * notional_exit)

        funding_cost = 0.0
        if cost.apply_funding:
            hours = bars_held * bar_minutes / 60.0
            periods = hours / 8.0
            notional_avg = qty * (entry + exit_px) / 2.0
            # Funding positivo: los LONG pagan, los SHORT cobran.
            funding_cost = d * cost.funding_rate_8h * periods * notional_avg

        # Coste de slippage explicito (para reporte): diferencia vs sin slippage.
        slip_cost = d * ((entry - eff_entry) + (eff_exit - exit_px)) * qty * -1.0
        slip_cost = abs(slip_cost)

        net_pnl = gross_pnl - fees - funding_cost
        equity_before = equity
        equity += net_pnl

        tot_fees += fees
        tot_funding += funding_cost
        tot_slip += slip_cost
        ret = net_pnl / equity_before if equity_before > 0 else 0.0
        returns.append(ret)
        equity_points.append(equity)

        row = dict(t)
        row.update({
            "qty": qty,
            "notional_entry": notional_entry,
            "gross_pnl": gross_pnl,
            "fees": fees,
            "funding_cost": funding_cost,
            "slippage_cost": slip_cost,
            "net_pnl": net_pnl,
            "net_pnl_r": net_pnl / risk_amount if risk_amount > 0 else 0.0,
            "return": ret,
            "equity_before": equity_before,
            "equity_after": equity,
        })
        rows.append(row)

        if stop_on_ruin and equity <= 0:
            ruin = True
            break

    trades_out = pd.DataFrame(rows)
    equity_curve = pd.Series(equity_points, name="equity")
    returns_s = pd.Series(returns, name="return")

    return {
        "trades": trades_out,
        "equity_curve": equity_curve,
        "returns": returns_s,
        "final_equity": equity,
        "n_trades": len(rows),
        "total_fees": tot_fees,
        "total_funding": tot_funding,
        "total_slippage_cost": tot_slip,
        "ruin": ruin,
    }


def simulate_folds(labeled, folds, valid_index=None, **kwargs):
    """Corre simulate() sobre el subconjunto de TEST de cada fold walk-forward.

    labeled: DataFrame etiquetado completo.
    folds: lista de (train_idx, test_idx) de bt_walkforward (indices posicionales
           sobre el subset valido).
    valid_index: el valid_index devuelto por folds_from_labeled; mapea posiciones
                 de fold a filas del DataFrame. Si None, se asume identidad.

    Devuelve lista de resultados de simulate(), uno por fold (solo test). Asi la
    curva de equity agregada es 100% out-of-sample.
    """
    results = []
    base = labeled.reset_index(drop=True)
    if valid_index is not None:
        base = labeled.loc[valid_index].reset_index(drop=True)
    for _train_idx, test_idx in folds:
        test_df = base.iloc[test_idx]
        results.append(simulate(test_df, **kwargs))
    return results
