# -*- coding: utf-8 -*-
"""
================================================================================
  BT LABELER - etiquetado triple-barrier (Lopez de Prado)
  by RasDG_Sol + Claude

  Etapa 2 del harness de research. Convierte cada senal candidata en un ejemplo
  etiquetado {win, loss, timeout} segun que barrera toca primero el precio:

    - barrera superior  -> take-profit (target)
    - barrera inferior  -> stop-loss
    - barrera vertical  -> horizonte temporal (timeout)

  Para un LONG: gana si high >= target, pierde si low <= stop.
  Para un SHORT: gana si low <= target, pierde si high >= stop.

  La etiqueta y el pnl_r (pnl en multiplos de R, donde R = |entry - stop|) son
  el ground-truth que:
    - entrena el GBM (bt_train),
    - construye la curva de equity y las metricas (bt_metrics),
    - se compara contra el ledger real para validar que el backtest no miente.

  Pieza pura: recibe DataFrames OHLCV, no toca red ni estado. Cuando target y
  stop caen en la MISMA vela (ambiguo, no sabemos el orden intra-vela), por
  defecto asumimos lo PESIMISTA (toco el stop primero) para no inflar resultados
  -- exactamente el sesgo que un fondo audita.
================================================================================
"""
import logging

import numpy as np
import pandas as pd

log = logging.getLogger("bt_labeler")

LONG = 1
SHORT = -1

WIN = "win"
LOSS = "loss"
TIMEOUT = "timeout"


def barriers_from_r(entry_price, direction, stop_r_pct=None, stop_price=None,
                    target_rr=2.0):
    """Deriva (stop_price, target_price) a partir de R.

    Modo A: das stop_price explicito (lo normal con tu motor, que ya calcula SL).
    Modo B: das stop_r_pct (riesgo como fraccion del precio, p.ej. 0.01 = 1%).
    target_rr: cuantas R de recorrido al target (2.0 = TP a 2R).
    """
    if stop_price is None:
        if stop_r_pct is None:
            raise ValueError("da stop_price o stop_r_pct")
        risk = entry_price * stop_r_pct
        stop_price = entry_price - direction * risk
    else:
        risk = abs(entry_price - stop_price)
    if risk <= 0:
        raise ValueError("riesgo no positivo (entry == stop)")
    target_price = entry_price + direction * risk * target_rr
    return stop_price, target_price


def label_event(bars, entry_price, stop_price, target_price, direction,
                max_bars=None, pessimistic=True):
    """Etiqueta UNA senal recorriendo las velas futuras (ya posteriores al entry).

    bars: DataFrame OHLCV cronologico DESPUES del entry (no incluye la vela de
          entrada). Columnas: high, low, close (timestamp opcional).
    direction: LONG (+1) o SHORT (-1).
    max_bars: barrera vertical en numero de velas. None => usa todas las dadas.
    pessimistic: si target y stop ocurren en la misma vela, asume stop primero.

    Devuelve dict:
      outcome   : 'win' | 'loss' | 'timeout'
      bars_held : velas hasta el cierre (1-indexado)
      exit_price: precio de salida (target/stop/close del horizonte)
      pnl_r     : pnl en multiplos de R (R = |entry - stop|), con signo
      mfe_r     : maxima excursion favorable vista (en R)
      mae_r     : maxima excursion adversa vista (en R, <= 0)
      hit_index : indice de vela donde se resolvio (None si timeout sin barrera)
    """
    if direction not in (LONG, SHORT):
        raise ValueError("direction debe ser LONG(+1) o SHORT(-1)")
    risk = abs(entry_price - stop_price)
    if risk <= 0:
        raise ValueError("riesgo no positivo (entry == stop)")

    horizon = len(bars) if max_bars is None else min(max_bars, len(bars))
    d = direction

    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    closes = bars["close"].to_numpy()

    mfe_r = 0.0
    mae_r = 0.0
    last_close = entry_price

    for i in range(horizon):
        hi, lo, cl = highs[i], lows[i], closes[i]
        last_close = cl

        # Excursiones favorable/adversa de esta vela, en R.
        fav_price = hi if d == LONG else lo
        adv_price = lo if d == LONG else hi
        fav_r = d * (fav_price - entry_price) / risk
        adv_r = d * (adv_price - entry_price) / risk
        mfe_r = max(mfe_r, fav_r)
        mae_r = min(mae_r, adv_r)

        if d == LONG:
            hit_target = hi >= target_price
            hit_stop = lo <= stop_price
        else:
            hit_target = lo <= target_price
            hit_stop = hi >= stop_price

        if hit_target and hit_stop:
            # Ambiguo dentro de la vela: por defecto, pesimista (stop primero).
            if pessimistic:
                return _result(LOSS, i + 1, stop_price, entry_price, stop_price,
                               d, risk, mfe_r, mae_r, i)
            return _result(WIN, i + 1, target_price, entry_price, stop_price,
                           d, risk, mfe_r, mae_r, i)
        if hit_stop:
            return _result(LOSS, i + 1, stop_price, entry_price, stop_price,
                           d, risk, mfe_r, mae_r, i)
        if hit_target:
            return _result(WIN, i + 1, target_price, entry_price, stop_price,
                           d, risk, mfe_r, mae_r, i)

    # Barrera vertical: cierre al horizonte (mark-to-market).
    pnl_r = d * (last_close - entry_price) / risk
    return {
        "outcome": TIMEOUT,
        "bars_held": horizon,
        "exit_price": last_close,
        "pnl_r": pnl_r,
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "hit_index": None,
    }


def _result(outcome, bars_held, exit_price, entry_price, stop_price,
            d, risk, mfe_r, mae_r, idx):
    pnl_r = d * (exit_price - entry_price) / risk
    return {
        "outcome": outcome,
        "bars_held": bars_held,
        "exit_price": exit_price,
        "pnl_r": pnl_r,
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "hit_index": idx,
    }


def label_events(df, events, max_bars=None, pessimistic=True):
    """Etiqueta un lote de senales sobre una serie OHLCV continua.

    df: DataFrame OHLCV cronologico (con columnas high/low/close), indice 0..n-1.
    events: iterable de dicts con al menos:
        entry_index  : indice de la vela de ENTRADA en df
        entry_price  : precio de entrada
        stop_price   : stop-loss
        target_price : take-profit
        direction    : LONG/SHORT
      (cualquier otra clave se preserva en la salida, p.ej. features del motor).

    Para cada evento usa las velas df[entry_index+1 :] como futuro. Devuelve un
    DataFrame: una fila por evento con las claves originales + las del label.
    """
    out = []
    n = len(df)
    for ev in events:
        ei = int(ev["entry_index"])
        future = df.iloc[ei + 1:]
        if len(future) == 0:
            row = dict(ev)
            row.update({"outcome": None, "bars_held": 0, "exit_price": None,
                        "pnl_r": None, "mfe_r": None, "mae_r": None,
                        "hit_index": None})
            out.append(row)
            continue
        label = label_event(
            future, ev["entry_price"], ev["stop_price"], ev["target_price"],
            ev["direction"], max_bars=max_bars, pessimistic=pessimistic,
        )
        row = dict(ev)
        row.update(label)
        out.append(row)
    return pd.DataFrame(out)


def label_summary(labeled):
    """Resumen rapido de un DataFrame etiquetado: conteos y expectancy en R.

    None si no hay filas resueltas.
    """
    resolved = labeled[labeled["outcome"].notna()]
    if len(resolved) == 0:
        return None
    n = len(resolved)
    pnls = resolved["pnl_r"].astype(float)
    counts = resolved["outcome"].value_counts().to_dict()
    wins = int(counts.get(WIN, 0))
    return {
        "n": n,
        "wins": wins,
        "losses": int(counts.get(LOSS, 0)),
        "timeouts": int(counts.get(TIMEOUT, 0)),
        "win_rate": wins / n,
        "expectancy_r": float(pnls.mean()),
        "total_r": float(pnls.sum()),
        "avg_mfe_r": float(resolved["mfe_r"].astype(float).mean()),
        "avg_mae_r": float(resolved["mae_r"].astype(float).mean()),
    }
