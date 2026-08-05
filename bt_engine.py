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


def maker_entry_fill_mask(trades, high, low, *, eps, ttl_bars):
    """¿Se habria LLENADO la entrada como limite pasiva, trade a trade? Version
    vectorizada (backtest) de la regla de gold_paper.process_maker_pending: una
    limite descansando en `entry_price` se llena SOLO si una de las `ttl_bars`
    velas SIGUIENTES PENETRA el nivel mas alla de `eps` (un touch NO llena -> peor
    caso de cola / adverse selection). LONG: low < entry*(1-eps); SHORT: high >
    entry*(1+eps). `high`/`low` = arrays posicionales (df_primary); cada trade trae
    `entry_index` (posicion de su vela de entrada), `entry_price` y `direction`
    (LONG/SHORT). Solo modela la pierna de ENTRADA (la que el techo asume gratis);
    stop/timeout siguen taker. Devuelve un bool ndarray alineado a `trades`.
    """
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    n = len(low)
    ei = trades["entry_index"].to_numpy()
    ent = trades["entry_price"].to_numpy(dtype=float)
    dirn = trades["direction"].to_numpy()
    out = np.zeros(len(trades), dtype=bool)
    for i in range(len(out)):
        a = int(ei[i]) + 1                        # la limite se evalua desde la vela SIGUIENTE
        b = min(int(ei[i]) + int(ttl_bars), n - 1)
        if a > b:
            continue                              # sin velas evaluables -> MISS (conservador)
        e = float(ent[i])
        out[i] = bool((low[a:b + 1] < e * (1.0 - eps)).any() if int(dirn[i]) > 0
                      else (high[a:b + 1] > e * (1.0 + eps)).any())
    return out


class MakerFillAssumedError(RuntimeError):
    """Se intentó publicar una cifra maker con el fill asumido al 100%.

    Es la invariante de V2, y tiene una factura detrás: en agosto el techo
    maker de E8 daba +0.060R IC95%[+0.024,+0.096] — con fill del 100% asumido —
    y el fill real lo dejó en −0.0350R. El supuesto era MÁS GRANDE que el
    margen entero. Una cifra maker sin modelo de fill no es optimista: es de
    otro mundo, y aquí no puede salir por la puerta.
    """


# Procedencia del fill que lleva pegada cada fila que sale de `simulate`. El
# número no viaja solo: viaja con cómo se decidió que la limite se llenaba.
FILL_TAKER = "taker"            # no hay pierna maker de entrada: no aplica
FILL_ASSUMED = "asumido_100"    # maker sin modelo -> TECHO, no publicable
FILL_MODELED = "modelado"       # maker con p_fill por señal


def maker_fill_probability(trades, high, low, *, eps, ttl_bars, queue_frac=None,
                           queue_bps=None, volume=None, taker_buy=None):
    """P(fill) de la entrada limite, condicionada al FLUJO que pasó por el nivel.

    `maker_entry_fill_mask` contesta *"¿el precio llegó?"*. Esa es la pregunta
    del backtest, no la del libro: una limite en el nivel no se llena porque el
    precio la toque, se llena cuando el volumen operado en ese nivel consume la
    COLA que tenía por delante. Dos señales con la misma penetración y flujo
    distinto no se llenan igual, y la binaria las cuenta iguales.

    Modelo (deliberadamente pequeño, y por eso declarable):

        p = clip(flujo_consumido / cola_por_delante, 0, 1)

    con dos formas de medir el flujo, en orden de fidelidad:

    1. **flujo firmado** (`volume` + `taker_buy`, `queue_frac`): lo que consume
       una BID descansando es el taker SELL que imprime en su nivel o por
       debajo — no el volumen total, del que la mitad son compras que se cruzan
       contra el ask. Simétrico para el SHORT. El reparto del volumen de la vela
       dentro de su rango es uniforme: es una aproximación, y de las gordas, pero
       es la que hay sin tick data y se equivoca en las dos direcciones, no en
       una.
    2. **profundidad** (`queue_bps`, sin volumen): el flujo se aproxima por los
       bps de penetración acumulados más allá del nivel. Para cuando no hay
       columna de volumen.

    `queue_frac` = cola por delante medida en múltiplos del volumen MEDIANO de
    barra del propio símbolo (unidad comparable entre BTC y SOL, que no comparten
    ni escala de precio ni de volumen). `queue_bps` = su equivalente en bps.

    Invariante de diseño, y está testeada: **p ≤ mask elementwise**. El flujo se
    cuenta solo más allá de `eps`, así que donde la binaria dice MISS esto dice 0
    y donde la binaria dice FILL esto dice como mucho 1. El refinamiento nunca es
    más optimista que la cota que ya se consideraba optimista — no hay forma de
    que este modelo INVENTE fills.

    Devuelve un ndarray float en [0,1] alineado a `trades`.
    """
    if (queue_frac is None) == (queue_bps is None):
        raise ValueError("declara exactamente una cola: queue_frac (flujo) o "
                         "queue_bps (profundidad)")
    if queue_frac is not None and volume is None:
        raise ValueError("queue_frac mide la cola en volumen de barra: pasa "
                         "`volume`, o usa queue_bps si no lo tienes")

    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    n = len(low)
    vol = None if volume is None else np.asarray(volume, dtype=float)
    tbuy = None if taker_buy is None else np.asarray(taker_buy, dtype=float)
    # La cola en unidades del propio símbolo. La mediana (no la media) porque el
    # volumen de barra tiene cola derecha larga y la media la fija un puñado de
    # velas de pánico que no describen la barra típica en la que descansa la orden.
    cola = (float(queue_frac) * float(np.median(vol[vol > 0])) if queue_frac is not None
            else float(queue_bps))
    if not cola > 0:
        raise ValueError("cola por delante <= 0: eso ES asumir fill del 100%")

    ei = trades["entry_index"].to_numpy()
    ent = trades["entry_price"].to_numpy(dtype=float)
    dirn = trades["direction"].to_numpy()
    out = np.zeros(len(trades), dtype=float)

    for i in range(len(out)):
        a = int(ei[i]) + 1
        b = min(int(ei[i]) + int(ttl_bars), n - 1)
        if a > b or int(ei[i]) < 0:
            continue                       # sin velas evaluables -> MISS
        d, e = int(dirn[i]), float(ent[i])
        # El nivel efectivo YA lleva el eps: contar flujo entre el nivel y el eps
        # haría que p > 0 donde la binaria dice MISS, y el refinamiento dejaría
        # de ser una cota inferior de ella.
        lvl = e * (1.0 - eps) if d > 0 else e * (1.0 + eps)
        hi_w, lo_w = high[a:b + 1], low[a:b + 1]
        rng = np.maximum(hi_w - lo_w, 1e-12)
        if d > 0:
            beyond = np.clip((np.minimum(hi_w, lvl) - lo_w) / rng, 0.0, 1.0)
            prof = np.maximum(lvl - lo_w, 0.0) / lvl * 10_000.0
        else:
            beyond = np.clip((hi_w - np.maximum(lo_w, lvl)) / rng, 0.0, 1.0)
            prof = np.maximum(hi_w - lvl, 0.0) / lvl * 10_000.0

        if queue_bps is not None:
            flujo = float(prof.sum())
        else:
            v = vol[a:b + 1]
            if tbuy is not None:
                # Firmado: una BID la consume el taker SELL; una ASK, el taker BUY.
                v = (v - tbuy[a:b + 1]) if d > 0 else tbuy[a:b + 1]
            flujo = float(np.sum(np.maximum(v, 0.0) * beyond))
        out[i] = min(1.0, flujo / cola)
    return out


def maker_expectancy(trades, *, col="net_pnl_r", p_col="fill_p",
                     model_col="fill_model", reps=2000, seed=7):
    """E[R | se llenó] bajo el modelo de fill, con su IC y su procedencia.

    La media simple de `net_pnl_r` sobre todas las señales responde a "¿cuánto
    habría rendido esto si TODAS las limites se llenaran?" — la pregunta cuya
    respuesta ya voló un resultado. Aquí cada señal pesa lo que se llena:

        E[R|fill] = Σ pᵢ rᵢ / Σ pᵢ

    y el IC95% se saca remuestreando señales **y sorteando el fill** Bernoulli(pᵢ)
    en cada réplica: la incertidumbre del fill es parte de la incertidumbre del
    número, no una nota al pie.

    Levanta `MakerFillAssumedError` si las filas vienen marcadas `asumido_100`.
    """
    if model_col not in trades.columns or p_col not in trades.columns:
        raise MakerFillAssumedError(
            "estas filas no traen procedencia de fill (%s/%s): sin saber cómo se "
            "decidió el fill, un E[R] maker no describe nada ejecutable"
            % (model_col, p_col))
    modelos = set(str(x) for x in trades[model_col].dropna().unique())
    if FILL_ASSUMED in modelos:
        raise MakerFillAssumedError(
            "hay filas con fill %r: el techo maker de E8 (+0.060R) era esto "
            "mismo y el fill real lo dejó en −0.0350R. Modela el fill "
            "(`maker_fill_probability`) o publícalo llamándolo TECHO."
            % FILL_ASSUMED)

    r = trades[col].to_numpy(float)
    p = np.clip(trades[p_col].to_numpy(float), 0.0, 1.0)
    ok = ~(np.isnan(r) | np.isnan(p))
    r, p = r[ok], p[ok]
    peso = p.sum()
    res = {"n": int(len(r)), "fill_rate": float(p.mean()) if len(p) else float("nan"),
           "n_esperada": float(peso), "fill_model": sorted(modelos),
           "expectancy": float(np.dot(p, r) / peso) if peso > 0 else float("nan")}
    if len(r) < 2 or peso <= 0:
        res.update(lo=float("nan"), hi=float("nan"), p_pos=float("nan"))
        return res
    rng = np.random.default_rng(seed)
    medias = np.empty(reps)
    for k in range(reps):
        idx = rng.integers(0, len(r), len(r))
        llena = rng.random(len(r)) < p[idx]
        medias[k] = r[idx][llena].mean() if llena.any() else np.nan
    medias = medias[~np.isnan(medias)]
    res.update(lo=float(np.percentile(medias, 2.5)),
               hi=float(np.percentile(medias, 97.5)),
               p_pos=float((medias > 0).mean()))
    return res


def require_fill_modeled(res):
    """Guardia de publicación: ninguna cifra maker sale con el fill asumido.

    Espejo de `vip_report.require_screened` (una celda no se nombra candidata
    sin cartera) y de `format_expectancy` (un E[R] no sale sin su desglose).
    Aquí lo que no puede faltar es CÓMO se llenó la orden.
    """
    if not isinstance(res, dict) or "fill_model" not in res:
        raise MakerFillAssumedError(
            "esto no pasó por maker_expectancy(): una cifra maker sin modelo de "
            "fill asume el 100% sin decirlo")
    if FILL_ASSUMED in set(res["fill_model"]):
        raise MakerFillAssumedError(
            "cifra maker con fill %r: no es publicable como resultado" % FILL_ASSUMED)
    return res


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

        # PROCEDENCIA DEL FILL (invariante V2). La fila sale marcada con cómo se
        # decidió que la limite se llenaba. Sin pierna maker no aplica; con
        # pierna maker y sin `fill_p`, esto es el TECHO — se ejecuta igual (el
        # techo es una medición legítima), pero queda marcado `asumido_100` y
        # `maker_expectancy` se niega a publicarlo como resultado.
        if not entry_maker:
            fill_model, fill_p = FILL_TAKER, 1.0
        elif "fill_p" in trades.columns and not pd.isna(t.get("fill_p")):
            fill_model, fill_p = FILL_MODELED, float(t["fill_p"])
        else:
            fill_model, fill_p = FILL_ASSUMED, 1.0

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
            "fill_model": fill_model,
            "fill_p": fill_p,
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
