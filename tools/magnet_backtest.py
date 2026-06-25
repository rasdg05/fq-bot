# -*- coding: utf-8 -*-
"""
================================================================================
  magnet_backtest — backtest del MOTOR DE IMANES sobre 5m (alta densidad, paso 1)
  by RasDG_Sol + Claude
================================================================================
Mide el DRAWDOWN (y expectancy / win-rate / R total) de las senales del motor de
imanes (liquidity_magnet.best_target), recorriendo el historico vela a vela (paso 1)
y pasando cada trade por bt_engine (costes reales -> curva de equity neta).

Honestidad: NO reimplementa costes (bt_engine es la fuente). Mide la propia
estrategia (los imanes) tal cual dispara, con etiquetado pesimista (si una vela toca
TP y SL, gana el STOP) = misma convencion que el research.

Uso:
    python tools/magnet_backtest.py <ruta.csv|.parquet> [--step 1] [--min-rr 1.5]
    # el archivo debe traer columnas: open, high, low, close, volume (5m)

El motor usa solo VWAP/cloud de MAs/max-min previos cuando field=None (esta version);
los pools de ict_smc se inyectan con --field (refinamiento posterior).
================================================================================
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

import liquidity_magnet as lm
import bt_engine

WARMUP = 50          # velas de calentamiento (MAs / imanes)


def label_magnet_trades(df, *, step=1, min_rr=1.5, max_hold=200, field_fn=None):
    """Recorre el df (paso `step`) generando senales del motor y etiqueta el
    desenlace mirando ADELANTE (que toca primero, TP o STOP; empate -> STOP).
    Devuelve un DataFrame listo para bt_engine.simulate (entry_price, stop_price,
    exit_price, direction in {+1,-1}, bars_held) + columnas mode/outcome."""
    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    closes = df["close"].astype(float).to_numpy()
    n = len(df)
    rows = []
    i = WARMUP
    while i < n - 1:
        sub = df.iloc[:i + 1]
        field = field_fn(sub) if field_fn else None
        sig = lm.best_target(sub, field, closes[i], min_rr=min_rr)
        advanced = False
        if sig:
            d = 1 if sig["direction"] == "long" else -1
            entry, stop, tp = sig["entry"], sig["stop"], sig["tp"]
            exit_px = bars = outcome = None
            for j in range(i + 1, min(i + 1 + max_hold, n)):
                if d > 0:
                    hit_sl, hit_tp = lows[j] <= stop, highs[j] >= tp
                else:
                    hit_sl, hit_tp = highs[j] >= stop, lows[j] <= tp
                if hit_sl:                      # pesimista: el stop gana el empate
                    exit_px, bars, outcome = stop, j - i, "loss"
                    break
                if hit_tp:
                    exit_px, bars, outcome = tp, j - i, "win"
                    break
            if exit_px is not None:
                rows.append({"entry_price": entry, "stop_price": stop,
                             "exit_price": exit_px, "direction": d,
                             "bars_held": bars, "outcome": outcome, "mode": sig["mode"]})
                i += bars                       # NO solapado: saltar hasta el cierre
                advanced = True
        if not advanced:
            i += step
    return pd.DataFrame(rows)


def precompute(df, *, periods=(20, 50, 100, 200), prior_bars=96, vwap_win=288):
    """Vectoriza (O(n)) las entradas de los imanes por vela para backtest a escala:
    center del cloud (mediana de EMA/SMA por periodo + Hull9), vwma, below,
    divergence, vwap (anclado al dia UTC si hay timestamp; si no, rodante vwap_win),
    prior_high/low. Mismo criterio que ma_cloud/enumerate_magnets (NaN se ignora ->
    en velas tempranas equivale a usar menos periodos, igual que el camino lento)."""
    out = df.reset_index(drop=True).copy()
    close = out["close"].astype(float)
    vol = out["volume"].astype(float)
    cols = []
    for n in periods:
        if n <= len(out):
            cols.append(lm._ema(close, n))
            cols.append(lm._sma(close, n))
    cols.append(lm._hull(close, 9))
    out["center"] = pd.concat(cols, axis=1).median(axis=1)
    out["vwma"] = lm._vwma(close, vol, 20)
    below = close < out["center"]
    vwma_above = close > out["vwma"]
    out["below"] = below
    out["divergence"] = (below & vwma_above) | ((~below) & (~vwma_above))
    tp = (out["high"].astype(float) + out["low"].astype(float) + close) / 3.0
    if "timestamp" in out.columns:
        day = pd.to_datetime(out["timestamp"], unit="ms", utc=True,
                             errors="coerce").dt.floor("D")
        out["vwap"] = (tp * vol).groupby(day).cumsum() / vol.groupby(day).cumsum()
    else:
        out["vwap"] = ((tp * vol).rolling(vwap_win, min_periods=20).sum()
                       / vol.rolling(vwap_win, min_periods=20).sum())
    out["prior_high"] = out["high"].astype(float).rolling(prior_bars, min_periods=5).max().shift(1)
    out["prior_low"] = out["low"].astype(float).rolling(prior_bars, min_periods=5).min().shift(1)
    return out


def precompute_v2(df, *, macro_span=144, day_bars=288, atr_n=14, vol_q=0.5):
    """precompute + capas MACRO (feedback RasDG: no operar zonas micro):
      · macro_up/macro_dn : bias del HTF (EMA larga macro_span ~12h + pendiente) ->
        operar CON el rio, no con la microestructura 5m.
      · atr               : para un stop con AIRE (no micro-ajustado).
      · pday_high/low      : extremos del dia previo = TARGET MACRO (liquidez grande
        -> RR que vale la pena).
      · active            : 'horas de volumen' (perfil de volumen por hora UTC; solo
        las horas en el top (>= cuantil vol_q) = killzones). Asume perfil estable
        (leve supuesto estructural, no prediccion de precio)."""
    out = precompute(df)
    close = out["close"].astype(float)
    high = out["high"].astype(float)
    low = out["low"].astype(float)
    ema = lm._ema(close, macro_span)
    slope = ema.diff()
    out["macro_up"] = (close > ema) & (slope > 0)
    out["macro_dn"] = (close < ema) & (slope < 0)
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    out["atr"] = tr.rolling(atr_n).mean()
    out["pday_high"] = high.rolling(day_bars, min_periods=20).max().shift(1)
    out["pday_low"] = low.rolling(day_bars, min_periods=20).min().shift(1)
    if "timestamp" in out.columns:
        hour = pd.to_datetime(out["timestamp"], unit="ms", utc=True,
                              errors="coerce").dt.hour
        prof = out.assign(_h=hour).groupby("_h")["volume"].mean()
        active_hours = set(prof[prof >= prof.quantile(vol_q)].index.tolist())
        out["active"] = hour.isin(active_hours)
    else:
        out["active"] = True
    return out


def label_v2(df, *, step=1, min_rr=2.0, max_hold=288, warmup=300,
             atr_mult=1.5, macro_span=144, day_bars=288, vol_q=0.5,
             require_value=False):
    """Motor v2/v3: dispara solo en HORAS DE VOLUMEN, CON el bias macro, hacia el
    TARGET MACRO (extremo del dia previo) con stop por ATR -> RR que vale la pena.
    require_value=True (v3): exige ENTRAR EN VALOR (long solo en descuento, price<=VWAP;
    short en premium, price>=VWAP) -> no perseguir, mejor ubicacion -> mejor WR. Trades
    NO solapados, etiquetado pesimista. mode='macro'."""
    pc = precompute_v2(df, macro_span=macro_span, day_bars=day_bars, vol_q=vol_q)
    highs = pc["high"].to_numpy(float)
    lows = pc["low"].to_numpy(float)
    closes = pc["close"].to_numpy(float)
    vwap = pc["vwap"].to_numpy(float)
    atr = pc["atr"].to_numpy(float)
    pdh = pc["pday_high"].to_numpy(float)
    pdl = pc["pday_low"].to_numpy(float)
    up = pc["macro_up"].to_numpy(bool)
    dn = pc["macro_dn"].to_numpy(bool)
    active = pc["active"].to_numpy(bool)
    n = len(pc)
    rows = []
    i = max(warmup, macro_span + 5)
    while i < n - 1:
        advanced = False
        price = closes[i]
        a = atr[i]
        v = vwap[i]
        in_value_long = (not require_value) or (v == v and price <= v)
        in_value_short = (not require_value) or (v == v and price >= v)
        if active[i] and a == a and a > 0:
            direction = stop = tp = None
            if up[i] and in_value_long and pdh[i] == pdh[i] and pdh[i] > price:
                direction, tp, stop = 1, pdh[i], price - atr_mult * a
            elif dn[i] and in_value_short and pdl[i] == pdl[i] and pdl[i] < price:
                direction, tp, stop = -1, pdl[i], price + atr_mult * a
            if direction is not None:
                risk, reward = abs(price - stop), abs(tp - price)
                if risk > 0 and reward / risk >= min_rr:
                    exit_px = bars = outcome = None
                    for j in range(i + 1, min(i + 1 + max_hold, n)):
                        if direction > 0:
                            hit_sl, hit_tp = lows[j] <= stop, highs[j] >= tp
                        else:
                            hit_sl, hit_tp = highs[j] >= stop, lows[j] <= tp
                        if hit_sl:
                            exit_px, bars, outcome = stop, j - i, "loss"
                            break
                        if hit_tp:
                            exit_px, bars, outcome = tp, j - i, "win"
                            break
                    if exit_px is not None:
                        rows.append({"entry_price": price, "stop_price": stop,
                                     "exit_price": exit_px, "direction": direction,
                                     "bars_held": bars, "outcome": outcome, "mode": "macro"})
                        i += bars
                        advanced = True
        if not advanced:
            i += step
    return pd.DataFrame(rows)


def label_fast(df, *, step=1, min_rr=1.5, max_hold=200, warmup=WARMUP):
    """Igual que label_magnet_trades pero O(n): precomputa los imanes una vez y arma
    la senal por vela con lm.build_signal (mismo criterio). Para backtest a escala."""
    pc = precompute(df)
    highs = pc["high"].to_numpy(float)
    lows = pc["low"].to_numpy(float)
    closes = pc["close"].to_numpy(float)
    center = pc["center"].to_numpy(float)
    vwap = pc["vwap"].to_numpy(float)
    ph = pc["prior_high"].to_numpy(float)
    pl = pc["prior_low"].to_numpy(float)
    below = pc["below"].to_numpy()
    div = pc["divergence"].to_numpy()
    n = len(pc)
    rows = []
    i = warmup
    while i < n - 1:
        price = closes[i]
        advanced = False
        mode, direction = lm.context_mode({"below": bool(below[i]),
                                           "divergence": bool(div[i])})
        if direction is not None:
            mags = []
            for p, kind in ((vwap[i], "vwap"), (center[i], "ma_cloud"),
                            (ph[i], "prior_high"), (pl[i], "prior_low")):
                if p == p and p > 0:
                    mags.append(lm.Magnet(float(p), kind, "above" if p >= price else "below"))
            sig = lm.build_signal(price, mags, mode, direction, min_rr=min_rr)
            if sig:
                d = 1 if sig["direction"] == "long" else -1
                stop, tp = sig["stop"], sig["tp"]
                exit_px = bars = outcome = None
                for j in range(i + 1, min(i + 1 + max_hold, n)):
                    if d > 0:
                        hit_sl, hit_tp = lows[j] <= stop, highs[j] >= tp
                    else:
                        hit_sl, hit_tp = highs[j] >= stop, lows[j] <= tp
                    if hit_sl:
                        exit_px, bars, outcome = stop, j - i, "loss"
                        break
                    if hit_tp:
                        exit_px, bars, outcome = tp, j - i, "win"
                        break
                if exit_px is not None:
                    rows.append({"entry_price": price, "stop_price": stop,
                                 "exit_price": exit_px, "direction": d,
                                 "bars_held": bars, "outcome": outcome, "mode": sig["mode"]})
                    i += bars                      # NO solapado: saltar hasta el cierre
                    advanced = True
        if not advanced:
            i += step
    return pd.DataFrame(rows)


def _max_drawdown(equity):
    eq = np.asarray(equity, dtype=float)
    if len(eq) == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.where(peak > 0, peak, 1.0)
    return float(dd.max())


def _htf(df, rule, prior, span=50):
    """Niveles + bias de un timeframe MAYOR (rule '1h'/'4h'), CAUSAL: usa solo barras
    HTF COMPLETADAS (shift(1)) y reindexa con ffill a cada vela de 5m. Devuelve ph/pl
    (extremos previos del HTF = imanes pesados) y up/dn (bias del HTF)."""
    idx = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    g = pd.DataFrame({"high": df["high"].astype(float).values,
                      "low": df["low"].astype(float).values,
                      "close": df["close"].astype(float).values}, index=idx)
    o = g.resample(rule).agg({"high": "max", "low": "min", "close": "last"}).dropna()
    ema = o["close"].ewm(span=span, adjust=False).mean()
    feat = pd.DataFrame(index=o.index)
    feat["ph"] = o["high"].rolling(prior, min_periods=2).max().shift(1)
    feat["pl"] = o["low"].rolling(prior, min_periods=2).min().shift(1)
    feat["up"] = ((o["close"] > ema) & (ema.diff() > 0)).shift(1).fillna(False)
    feat["dn"] = ((o["close"] < ema) & (ema.diff() < 0)).shift(1).fillna(False)
    return feat.reindex(idx, method="ffill")


def precompute_v4(df, *, prior_1h=24, prior_4h=12, **kw):
    """precompute_v2 + RED MULTI-TF: niveles y bias de 1h y 4h (imanes pesados +
    confluencia de timeframes). Requiere timestamp (resample)."""
    out = precompute_v2(df, **kw)
    if "timestamp" not in out.columns:
        for tf in ("1h", "4h"):
            for c in ("ph", "pl"):
                out["%s_%s" % (c, tf)] = float("nan")
            for c in ("up", "dn"):
                out["%s_%s" % (c, tf)] = False
        return out
    for tf, prior in (("1h", prior_1h), ("4h", prior_4h)):
        h = _htf(df, tf, prior)
        out["ph_%s" % tf] = h["ph"].to_numpy()
        out["pl_%s" % tf] = h["pl"].to_numpy()
        out["up_%s" % tf] = h["up"].to_numpy()
        out["dn_%s" % tf] = h["dn"].to_numpy()
    return out


def label_v4(df, *, step=1, min_rr=2.0, max_hold=288, warmup=300, atr_mult=1.5,
             require_value=True, vol_q=0.5):
    """Motor v4 (gravedad + silencio): dispara SOLO si 1h Y 4h alinean (red multi-TF),
    en horas de volumen, entrando en valor (VWAP), hacia el IMAN PESADO de 4h (extremo
    previo del 4h). Si no hay confluencia/volumen/iman -> el bot CALLA. Stop por ATR."""
    pc = precompute_v4(df, vol_q=vol_q)
    highs = pc["high"].to_numpy(float)
    lows = pc["low"].to_numpy(float)
    closes = pc["close"].to_numpy(float)
    vwap = pc["vwap"].to_numpy(float)
    atr = pc["atr"].to_numpy(float)
    active = pc["active"].to_numpy(bool)
    up1 = pc["up_1h"].to_numpy(bool)
    dn1 = pc["dn_1h"].to_numpy(bool)
    up4 = pc["up_4h"].to_numpy(bool)
    dn4 = pc["dn_4h"].to_numpy(bool)
    ph4 = pc["ph_4h"].to_numpy(float)
    pl4 = pc["pl_4h"].to_numpy(float)
    n = len(pc)
    rows = []
    i = max(warmup, 300)
    while i < n - 1:
        advanced = False
        price = closes[i]
        a = atr[i]
        v = vwap[i]
        if active[i] and a == a and a > 0:
            direction = stop = tp = None
            val_long = (not require_value) or (v == v and price <= v)
            val_short = (not require_value) or (v == v and price >= v)
            if up1[i] and up4[i] and val_long and ph4[i] == ph4[i] and ph4[i] > price:
                direction, tp, stop = 1, ph4[i], price - atr_mult * a
            elif dn1[i] and dn4[i] and val_short and pl4[i] == pl4[i] and pl4[i] < price:
                direction, tp, stop = -1, pl4[i], price + atr_mult * a
            if direction is not None:
                risk, reward = abs(price - stop), abs(tp - price)
                if risk > 0 and reward / risk >= min_rr:
                    exit_px = bars = outcome = None
                    for j in range(i + 1, min(i + 1 + max_hold, n)):
                        if direction > 0:
                            hit_sl, hit_tp = lows[j] <= stop, highs[j] >= tp
                        else:
                            hit_sl, hit_tp = highs[j] >= stop, lows[j] <= tp
                        if hit_sl:
                            exit_px, bars, outcome = stop, j - i, "loss"
                            break
                        if hit_tp:
                            exit_px, bars, outcome = tp, j - i, "win"
                            break
                    if exit_px is not None:
                        rows.append({"entry_price": price, "stop_price": stop,
                                     "exit_price": exit_px, "direction": direction,
                                     "bars_held": bars, "outcome": outcome, "mode": "macro_mtf"})
                        i += bars
                        advanced = True
        if not advanced:
            i += step
    return pd.DataFrame(rows)


def run(df, *, step=1, min_rr=1.5, bar_minutes=5.0, cost=None, version="v1", **v2kw):
    """Backtest completo: etiqueta -> bt_engine -> metricas. version='v1' (imanes
    micro) o 'v2' (horas de volumen + bias macro + target macro). Devuelve dict con
    n_trades, win_rate, expectancy_r (gross), total_r, max_drawdown (neto),
    final_equity y desglose por modo."""
    if version == "v4":
        trades = label_v4(df, step=step, min_rr=min_rr, **v2kw)
    elif version == "v2":
        trades = label_v2(df, step=step, min_rr=min_rr, **v2kw)
    else:
        trades = label_fast(df, step=step, min_rr=min_rr)
    out = {"n_trades": int(len(trades))}
    if trades.empty:
        out.update({"win_rate": None, "expectancy_r": None, "total_r": 0.0,
                    "max_drawdown": 0.0, "final_equity": None, "by_mode": {}})
        return out
    # R gross por trade (precio puro, sin costes) para expectancy/WR
    d = trades["direction"].to_numpy(dtype=float)
    rdist = (trades["entry_price"] - trades["stop_price"]).abs().to_numpy()
    pnl_r = d * (trades["exit_price"].to_numpy() - trades["entry_price"].to_numpy()) / rdist
    trades = trades.assign(pnl_r=pnl_r)
    # equity NETA via bt_engine (costes reales) -> drawdown
    res = bt_engine.simulate(trades, bar_minutes=bar_minutes, cost=cost or bt_engine.CostModel())
    by_mode = {m: {"n": int((trades["mode"] == m).sum()),
                   "expectancy_r": float(trades.loc[trades["mode"] == m, "pnl_r"].mean())}
               for m in sorted(trades["mode"].unique())}
    out.update({
        "win_rate": float((trades["outcome"] == "win").mean()),
        "expectancy_r": float(pnl_r.mean()),
        "total_r": float(pnl_r.sum()),
        "max_drawdown": _max_drawdown(res["equity_curve"]),
        "final_equity": float(res["final_equity"]),
        "by_mode": by_mode,
    })
    return out


def _load(path):
    if path.endswith(".parquet"):
        return pd.read_parquet(path)
    return pd.read_csv(path)


def main(argv):
    if len(argv) < 2:
        print("uso: python tools/magnet_backtest.py <ruta.csv|.parquet> [--step N] [--min-rr R]")
        return 2
    path = argv[1]
    step = int(argv[argv.index("--step") + 1]) if "--step" in argv else 1
    min_rr = float(argv[argv.index("--min-rr") + 1]) if "--min-rr" in argv else 1.5
    if not os.path.exists(path):
        print("[magnet-bt] no existe: %s" % path)
        return 2
    df = _load(path)
    r = run(df, step=step, min_rr=min_rr)
    print("[magnet-bt] %s  velas=%d  step=%d  min_rr=%.2f" % (path, len(df), step, min_rr))
    if not r["n_trades"]:
        print("  sin trades (subi la densidad o baja --min-rr).")
        return 1
    print("  trades=%d  WR=%.1f%%  exp=%+.3fR  total=%+.1fR" % (
        r["n_trades"], r["win_rate"] * 100, r["expectancy_r"], r["total_r"]))
    print("  MAX DRAWDOWN (neto) = %.1f%%   equity_final=%.0f" % (
        r["max_drawdown"] * 100, r["final_equity"]))
    for m, s in r["by_mode"].items():
        print("    [%s] n=%d  exp=%+.3fR" % (m, s["n"], s["expectancy_r"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
