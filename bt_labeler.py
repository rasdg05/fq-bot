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


TRAIL = "trail"


class LookaheadExitError(RuntimeError):
    """Una regla de salida miro el futuro.

    Es LA trampa de este experimento. Un trailing necesita el maximo *hasta
    ahora*; si se calcula el MFE de toda la vida del trade y luego se "sale en
    k x MFE", la regla sabe a donde va a llegar el precio y produce una curva
    preciosa y falsa. Aqui el nivel de trailing de la vela `i` se construye SOLO
    con las velas `0..i-1`, y `test_la_salida_dinamica_es_causal` lo comprueba
    alimentando una serie cuyo futuro es espectacular.
    """


def _trail_level_r(rule, mfe_r_prev, armed):
    """Nivel de salida en R, construido con el MFE **hasta la vela anterior**.

    Devuelve `(nivel_r, armed)`. `-1.0` significa "manda el stop duro" (en las
    unidades de R de esta geometria el stop duro es exactamente -1R por
    construccion, porque R = |entry - stop|).
    """
    kind = rule["kind"]
    if kind == "time":
        return -1.0, armed
    if kind == "trail":
        # Se ARMA al llegar a `arm` R. Sin umbral de armado la regla es
        # degenerada: con MFE=0 el nivel k*0 = 0 seria breakeven desde el tick
        # uno, mas apretado que el propio stop duro. `arm` NO se busca (queda
        # fijo en 1.0R) para no gastar n_trials en el.
        armed = armed or (mfe_r_prev >= rule["arm"])
        if not armed:
            return -1.0, armed
        return mfe_r_prev * (1.0 - rule["k"]), armed
    if kind == "be_trail":
        # Breakeven al llegar a `m` R, y a partir de ahi cede la mitad del pico.
        armed = armed or (mfe_r_prev >= rule["m"])
        if not armed:
            return -1.0, armed
        return max(0.0, mfe_r_prev * (1.0 - rule["k"])), armed
    raise ValueError("regla de salida desconocida: %r" % kind)


def label_event_dynamic(bars, entry_price, stop_price, target_price, direction,
                        exit_rule, max_bars=None, pessimistic=True):
    """Como `label_event`, pero con una salida DINAMICA encima de las barreras.

    El stop duro y el objetivo siguen ahi: la regla dinamica solo puede cerrar
    ANTES. Por eso el control (`exit_rule=None` -> `label_event`) es exactamente
    comparable, que es lo que exige la pre-registracion.

    Dos convenciones, y las dos son las de la casa:

    * **Causalidad.** El nivel de trailing de la vela `i` se calcula con el MFE
      de las velas `0..i-1`. Nunca con el de la vela en curso ni con el futuro.
    * **Pesimismo intra-vela.** Dentro de una vela no se sabe si el extremo
      adverso llego antes que el favorable, asi que se asume que si. El orden de
      comprobacion es: (1) nivel de salida/stop contra el extremo ADVERSO,
      (2) objetivo contra el favorable, (3) recien entonces se actualiza el MFE.
      Es el mismo sesgo que `label_event` (empate -> gana el stop), y por eso el
      resultado se publica como COTA INFERIOR.

    `outcome` gana un valor nuevo, `'trail'`, para que el desenlace por salida
    dinamica no se confunda con un stop ni con un timeout.
    """
    if direction not in (LONG, SHORT):
        raise ValueError("direction debe ser LONG(+1) o SHORT(-1)")
    risk = abs(entry_price - stop_price)
    if risk <= 0:
        raise ValueError("riesgo no positivo (entry == stop)")
    if exit_rule is None:
        return label_event(bars, entry_price, stop_price, target_price,
                           direction, max_bars=max_bars,
                           pessimistic=pessimistic)

    horizon = len(bars) if max_bars is None else min(max_bars, len(bars))
    if exit_rule["kind"] == "time":
        horizon = min(horizon, int(exit_rule["T"]))
    d = direction

    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    closes = bars["close"].to_numpy()

    mfe_r = 0.0          # MFE hasta la vela ANTERIOR (esto es la causalidad)
    mae_r = 0.0
    armed = False
    last_close = entry_price

    for i in range(horizon):
        hi, lo, cl = highs[i], lows[i], closes[i]
        last_close = cl

        nivel_r, armed = _trail_level_r(exit_rule, mfe_r, armed)
        # El nivel efectivo nunca es mas flojo que el stop duro.
        nivel_r = max(nivel_r, -1.0)
        nivel_px = entry_price + d * nivel_r * risk

        fav_price = hi if d == LONG else lo
        adv_price = lo if d == LONG else hi

        # (1) Extremo ADVERSO primero: pesimismo intra-vela.
        toca_salida = (adv_price <= nivel_px) if d == LONG else (adv_price >= nivel_px)
        # (2) Objetivo.
        toca_tp = (hi >= target_price) if d == LONG else (lo <= target_price)

        if toca_salida:
            # Un empate con el objetivo se resuelve a favor de la salida, igual
            # que `label_event` resuelve el empate a favor del stop.
            outcome = LOSS if nivel_r <= -1.0 else TRAIL
            res = _result(outcome, i + 1, nivel_px, entry_price, stop_price,
                          d, risk, mfe_r, mae_r, i)
            res["exit_kind"] = exit_rule["kind"]
            return res
        if toca_tp:
            res = _result(WIN, i + 1, target_price, entry_price, stop_price,
                          d, risk, mfe_r, mae_r, i)
            res["exit_kind"] = exit_rule["kind"]
            return res

        # (3) Recien AHORA entra esta vela en el MFE/MAE, para que el nivel de
        # la vela siguiente la use y el de esta no.
        mfe_r = max(mfe_r, d * (fav_price - entry_price) / risk)
        mae_r = min(mae_r, d * (adv_price - entry_price) / risk)

    pnl_r = d * (last_close - entry_price) / risk
    return {
        "outcome": TIMEOUT,
        "bars_held": horizon,
        "exit_price": last_close,
        "pnl_r": pnl_r,
        "mfe_r": mfe_r,
        "mae_r": mae_r,
        "hit_index": None,
        "exit_kind": exit_rule["kind"],
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


# ============================================================
# CUBO (TP x HORIZONTE) - una sola pasada, post-replay
# ============================================================
#
# El replay del motor es el ~99% del coste; re-etiquetar al variar el TARGET o el
# HORIZONTE es barato (solo cambia la barrera, no las velas). Este cubo resuelve,
# en UNA pasada por las velas de cada senal, TODAS las combinaciones (target x
# horizonte) con un STOP comun. Es la pieza que el plan de retrieval (F3,
# "selector de TP/horizonte") y el grid de bt_optimize consumen: la 'frontera'
# de desenlaces por estado. Coherente con label_event (misma R, mismo pesimismo,
# mismo pnl_r), de modo que una celda del cubo == llamar label_event con ese
# (target, max_bars).


def label_event_grid(bars, entry_price, stop_price, direction, targets,
                     horizons, pessimistic=True):
    """Etiqueta UNA senal contra una rejilla (target x horizonte) en una pasada.

    bars      : DataFrame OHLCV cronologico DESPUES del entry (igual que
                label_event), columnas high/low/close.
    targets   : dict {nombre: target_price}. (Una lista tambien vale; se nombran
                't0','t1',... por posicion.) El STOP es comun a todos.
    horizons  : iterable de barreras verticales (en numero de velas).
    pessimistic: si target y stop caen en la misma vela, asume stop primero.

    Devuelve dict:
      cells : {(target_name, horizon): {outcome, bars_held, exit_price, pnl_r}}
      mfe_r : {horizon: mfe_r}   # excursion favorable hasta ese horizonte (>=0)
      mae_r : {horizon: mae_r}   # excursion adversa hasta ese horizonte (<=0)
    """
    if direction not in (LONG, SHORT):
        raise ValueError("direction debe ser LONG(+1) o SHORT(-1)")
    risk = abs(entry_price - stop_price)
    if risk <= 0:
        raise ValueError("riesgo no positivo (entry == stop)")
    if not isinstance(targets, dict):
        targets = {f"t{i}": float(p) for i, p in enumerate(targets)}

    d = direction
    n = len(bars)
    horizons = [int(h) for h in horizons]
    # Solo necesitamos recorrer hasta el horizonte mayor (acotado por las velas).
    max_h = min(max(horizons), n) if (n > 0 and horizons) else 0

    highs = bars["high"].to_numpy()[:max_h]
    lows = bars["low"].to_numpy()[:max_h]
    closes = bars["close"].to_numpy()[:max_h]

    # Excursiones acumuladas en R: mfe_cum[k]/mae_cum[k] = mejor/peor sobre las
    # primeras k velas (k=0 => 0.0, como inicializa label_event).
    fav_price = highs if d == LONG else lows
    adv_price = lows if d == LONG else highs
    fav_r = d * (fav_price - entry_price) / risk
    adv_r = d * (adv_price - entry_price) / risk
    mfe_cum = np.concatenate([[0.0], np.maximum.accumulate(fav_r)]) if max_h \
        else np.array([0.0])
    mae_cum = np.concatenate([[0.0], np.minimum.accumulate(adv_r)]) if max_h \
        else np.array([0.0])
    mfe_cum = np.maximum(mfe_cum, 0.0)
    mae_cum = np.minimum(mae_cum, 0.0)

    # Primer toque del stop (comun) y de cada target, en [0, max_h).
    def _first(mask):
        idx = np.flatnonzero(mask)
        return int(idx[0]) if idx.size else None

    if max_h:
        stop_first = _first(lows <= stop_price) if d == LONG \
            else _first(highs >= stop_price)
        target_first = {
            name: (_first(highs >= px) if d == LONG else _first(lows <= px))
            for name, px in targets.items()
        }
    else:
        stop_first = None
        target_first = {name: None for name in targets}

    cells = {}
    mfe_by_h = {}
    mae_by_h = {}
    for h in horizons:
        hc = min(h, n)                       # horizonte efectivo (acotado)
        mfe_by_h[h] = float(mfe_cum[min(hc, max_h)])
        mae_by_h[h] = float(mae_cum[min(hc, max_h)])
        s = stop_first if (stop_first is not None and stop_first < hc) else None
        for name, px in targets.items():
            tf = target_first.get(name)
            t = tf if (tf is not None and tf < hc) else None
            if s is None and t is None:
                # barrera vertical: mark-to-market al cierre del horizonte.
                if hc <= 0:
                    outcome, bars_held, exit_price = TIMEOUT, 0, entry_price
                else:
                    exit_price = float(closes[hc - 1])
                    outcome, bars_held = TIMEOUT, hc
                pnl_r = d * (exit_price - entry_price) / risk
            elif t is not None and (s is None or t < s):
                # target primero (estrictamente): WIN. Empate (t == s) -> stop.
                outcome, bars_held, exit_price = WIN, t + 1, float(px)
                pnl_r = d * (px - entry_price) / risk
            else:
                # stop primero o empate pesimista: LOSS.
                outcome, bars_held, exit_price = LOSS, s + 1, float(stop_price)
                pnl_r = d * (stop_price - entry_price) / risk
            cells[(name, h)] = {
                "outcome": outcome,
                "bars_held": bars_held,
                "exit_price": exit_price,
                "pnl_r": float(pnl_r),
            }
    return {"cells": cells, "mfe_r": mfe_by_h, "mae_r": mae_by_h}


def label_events_grid(df, events, target_keys, horizons, pessimistic=True):
    """Cubo (TP x horizonte) por lote, formato LARGO (una fila por celda).

    df          : OHLCV continuo (indice 0..n-1), como label_events.
    events      : iterable de dicts con entry_index, entry_price, stop_price,
                  direction y los precios de target en `target_keys`.
    target_keys : claves de cada evento con el precio del target, p.ej.
                  ['px_tp1','px_tp2','px_tp4']. El nombre de TP en la salida es la
                  clave sin el prefijo 'px_'.
    horizons    : lista de barreras verticales (velas).

    Devuelve un DataFrame LARGO: una fila por (evento, tp, horizonte) con todas
    las claves del evento preservadas + tp, horizon, outcome, bars_held,
    exit_price, pnl_r, mfe_r, mae_r. El subconjunto de una celda (tp, horizon)
    tiene el MISMO esquema que label_events -> alimenta bt_engine/bt_metrics tal
    cual.
    """
    out = []
    n = len(df)
    for ev in events:
        ei = int(ev["entry_index"])
        future = df.iloc[ei + 1:]
        targets = {}
        for key in target_keys:
            px = ev.get(key)
            if px is None or (isinstance(px, float) and np.isnan(px)):
                continue
            name = key[3:] if key.startswith("px_") else key
            targets[name] = float(px)
        if len(future) == 0 or not targets:
            continue
        grid = label_event_grid(
            future, ev["entry_price"], ev["stop_price"], int(ev["direction"]),
            targets, horizons, pessimistic=pessimistic)
        for (name, h), cell in grid["cells"].items():
            row = dict(ev)
            row.update(cell)
            row["tp"] = name
            row["horizon"] = h
            row["mfe_r"] = grid["mfe_r"][h]
            row["mae_r"] = grid["mae_r"][h]
            out.append(row)
    return pd.DataFrame(out)


def grid_summary(long_df):
    """Tabla (TP x horizonte): expectancy_r / win_rate / total_r / n por celda,
    desde el DataFrame largo de label_events_grid. La 'frontera' que el selector
    F3 consume. Ordenada por expectancy_r descendente.
    """
    if long_df is None or len(long_df) == 0:
        return pd.DataFrame(
            columns=["tp", "horizon", "n", "win_rate", "expectancy_r", "total_r"])
    resolved = long_df[long_df["outcome"].notna()]
    rows = []
    for (tp, h), g in resolved.groupby(["tp", "horizon"], sort=False):
        pnls = g["pnl_r"].astype(float)
        n = len(g)
        wins = int((g["outcome"] == WIN).sum())
        rows.append({
            "tp": tp, "horizon": int(h), "n": n,
            "win_rate": wins / n if n else None,
            "expectancy_r": float(pnls.mean()) if n else None,
            "total_r": float(pnls.sum()),
        })
    res = pd.DataFrame(rows)
    return res.sort_values("expectancy_r", ascending=False).reset_index(drop=True)


def best_cell(long_df, by="expectancy_r"):
    """La mejor celda (tp, horizonte) del cubo segun `by`. None si vacio."""
    summ = grid_summary(long_df)
    summ = summ[summ[by].notna()]
    if len(summ) == 0:
        return None
    return summ.loc[summ[by].astype(float).idxmax()].to_dict()


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
