# -*- coding: utf-8 -*-
"""
================================================================================
  BT FORWARD - prueba forward / out-of-time (proof of work) + calibración
  by RasDG_Sol + Claude

  Más allá del walk-forward OOS: el escalón siguiente de rigor antes de tocar
  capital. Tres piezas, todas puras (arrays/DataFrames in, números out):

    1) out_of_time_split: congela en una FECHA de corte. Todo lo que se ajusta
       (modelo, scaler, índice de retrieval) usa SOLO eventos anteriores; se
       evalúa SOLO en la ventana posterior, jamás vista. Es el split sin folds
       entrelazados: imposible de contaminar por construcción.
    2) calibration_table: ¿lo PREDICHO coincide con lo REALIZADO? Por bin de
       score predicho, la tasa/expectancy realizada. La diagonal = calibrado.
       Un modelo con AUC alta pero mal calibrado miente sobre la magnitud.
    3) reconcile: ¿la expectancy VIVA cae dentro del IC bootstrap del backtest?
       Si no, alarma de DRIFT (cambio de régimen / decay del edge). Cierra el
       lazo backtest <-> producción.

  freeze_predict ajusta UN estimador sobre el 'antes' y predice el 'después'
  (estimador inyectable para test sin lightgbm). Sin red, sin tocar el monolito.
================================================================================
"""
import logging

import numpy as np
import pandas as pd

log = logging.getLogger("bt_forward")

WIN = "win"


def out_of_time_split(labeled, cutoff, ts_col="entry_ts"):
    """Divide por TIEMPO: before = eventos con ts < cutoff (para CONGELAR el
    ajuste), after = eventos con ts >= cutoff (jamás vistos, para evaluar).

    labeled : DataFrame etiquetado (debe traer ts_col, p.ej. 'entry_ts').
    cutoff  : fecha de corte (str/Timestamp).
    Devuelve (before, after) reindexados 0..n-1.
    """
    if ts_col not in labeled.columns:
        raise ValueError(f"falta la columna temporal '{ts_col}'")
    ts = pd.to_datetime(labeled[ts_col])
    cut = pd.Timestamp(cutoff)
    if cut.tzinfo is not None and ts.dt.tz is None:
        cut = cut.tz_localize(None)
    before = labeled[ts < cut].reset_index(drop=True)
    after = labeled[ts >= cut].reset_index(drop=True)
    return before, after


def _predict_scores(model, X):
    """proba de la clase positiva si existe; si no, predict crudo."""
    if hasattr(model, "predict_proba"):
        p = np.asarray(model.predict_proba(X))
        if p.ndim == 2 and p.shape[1] >= 2:
            return p[:, 1]
        return p.ravel()
    return np.asarray(model.predict(X)).ravel()


def freeze_predict(before, after, feature_cols, estimator_factory,
                   label_col="outcome", win_value=WIN, score_col="fwd_score"):
    """Congela UN estimador sobre 'before' y puntúa 'after' (sin re-ver el test).

    El núcleo del out-of-time: el ajuste NUNCA ve la ventana posterior. Devuelve
    una copia de 'after' con la columna score_col (prob de ganar predicha).
    estimator_factory: callable() -> estimador con .fit(X,y) y predict[_proba].
    """
    Xb = before[feature_cols].reset_index(drop=True).fillna(0.0)
    yb = (before[label_col] == win_value).astype(int).to_numpy()
    if len(np.unique(yb)) < 2:
        raise ValueError("el 'before' tiene una sola clase; no se puede ajustar")
    model = estimator_factory()
    model.fit(Xb, yb)
    Xa = after[feature_cols].reset_index(drop=True).fillna(0.0)
    out = after.copy().reset_index(drop=True)
    out[score_col] = _predict_scores(model, Xa)
    return out, model


def _periods_per_year(labeled, bar_minutes):
    if "entry_ts" not in labeled.columns or len(labeled) < 2:
        return None
    ts = pd.to_datetime(labeled["entry_ts"])
    span_days = (ts.max() - ts.min()).total_seconds() / 86400.0
    if span_days <= 0:
        return None
    return len(labeled) * 365.0 / span_days


def forward_metrics(after, sim_kwargs=None, bar_minutes=5.0):
    """Métricas net-de-costes sobre la ventana posterior (reusa bt_engine +
    bt_metrics). Devuelve el dict de métricas o None si no hay trades resueltos.
    """
    import bt_engine as eng
    import bt_metrics as met
    sim_kwargs = sim_kwargs or {}
    trades = after[after["outcome"].notna()] if "outcome" in after.columns else after
    if len(trades) == 0:
        return None
    ppy = _periods_per_year(after, bar_minutes)
    res = eng.simulate(trades, **sim_kwargs)
    return met.metrics_from_result(res, periods_per_year=ppy)


def calibration_table(predicted, realized, n_bins=5):
    """Calibración: por bin de cuantil del score PREDICHO, el promedio predicho
    vs el promedio REALIZADO (tasa de acierto si realized es 0/1, o expectancy si
    es pnl_r). La diagonal (predicho ~ realizado) = bien calibrado.

    Devuelve (DataFrame[bin, n, pred_mean, real_mean, gap], cal_error) donde
    cal_error = MAE ponderado por n entre predicho y realizado.
    """
    p = np.asarray(predicted, dtype="float64")
    r = np.asarray(realized, dtype="float64")
    m = np.isfinite(p) & np.isfinite(r)
    p, r = p[m], r[m]
    if len(p) == 0:
        return pd.DataFrame(columns=["bin", "n", "pred_mean", "real_mean", "gap"]), None
    # bins por cuantil (rangos de score), robustos a empates
    ranks = pd.Series(p).rank(method="first")
    bins = np.clip(((ranks - 1) / len(p) * n_bins).astype(int), 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        sel = bins == b
        if not sel.any():
            continue
        pm, rm = float(p[sel].mean()), float(r[sel].mean())
        rows.append({"bin": b, "n": int(sel.sum()), "pred_mean": pm,
                     "real_mean": rm, "gap": rm - pm})
    df = pd.DataFrame(rows)
    if len(df) == 0:
        return df, None
    cal_error = float((df["gap"].abs() * df["n"]).sum() / df["n"].sum())
    return df, cal_error


def reconcile(backtest_expectancy_r, live_pnls_r, n_boot=2000, seed=42, ci=0.90):
    """¿La expectancy del BACKTEST es consistente con la VIVA? Bootstrapea la
    media de los pnl_r vivos y comprueba si la expectancy del backtest cae dentro
    del IC. Fuera del IC = DRIFT (régimen/decay) -> revisar antes de subir tamaño.

    Devuelve dict: live_expectancy_r, ic_low, ic_high, backtest_expectancy_r,
    within (bool), verdict.
    """
    x = np.asarray(live_pnls_r, dtype="float64")
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return {"live_expectancy_r": None, "within": None, "verdict": "muestra insuficiente"}
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    lo = float(np.quantile(means, (1 - ci) / 2))
    hi = float(np.quantile(means, 1 - (1 - ci) / 2))
    bt = float(backtest_expectancy_r) if backtest_expectancy_r is not None else None
    within = (bt is not None) and (lo <= bt <= hi)
    if bt is None:
        verdict = "sin baseline de backtest"
    elif within:
        verdict = "CONSISTENTE (sin drift detectable)"
    elif float(x.mean()) < bt:
        verdict = "DRIFT a la baja: la viva rinde menos que el backtest -> NO subir tamaño"
    else:
        verdict = "la viva supera al backtest (favorable; verifica que no sea suerte)"
    return {
        "live_expectancy_r": float(x.mean()),
        "ic_low": lo, "ic_high": hi,
        "backtest_expectancy_r": bt,
        "within": within, "n": int(len(x)),
        "verdict": verdict,
    }
