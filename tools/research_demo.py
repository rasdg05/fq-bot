#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEMO END-TO-END del harness de research (sin red, sin lightgbm obligatorio).

Cablea las 6 etapas sobre datos SINTETICOS para mostrar el pipeline completo y
servir de plantilla: sustituye la generacion sintetica por tus velas reales
(bt_data) y tus features reales (add_indicators + ict_smc) y el resto encaja.

    label (bt_labeler) -> folds purgados (bt_walkforward) -> backtest con costes
    (bt_engine) -> metricas (bt_metrics) -> modelo OOS (bt_train) -> poda de
    modulos (bt_ablation).

Uso:
    python tools/research_demo.py
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import bt_labeler as lb
import bt_walkforward as wf
import bt_engine as eng
import bt_metrics as met
import bt_train as tr
import bt_ablation as ab


# Modelo de respaldo: regresion logistica en numpy (si no hay lightgbm) para que
# el demo SIEMPRE corra. En produccion usarias tr.make_lgbm_classifier.
class _NumpyLogReg:
    def __init__(self, lr=0.1, epochs=300):
        self.lr, self.epochs = lr, epochs
        self.w = None
        self.b = 0.0
        self.cols = None

    def fit(self, X, y, **kw):
        self.cols = list(X.columns)
        Xs = (X.to_numpy() - X.to_numpy().mean(0)) / (X.to_numpy().std(0) + 1e-9)
        y = np.asarray(y, dtype="float64")
        n, d = Xs.shape
        self.w = np.zeros(d)
        for _ in range(self.epochs):
            z = Xs @ self.w + self.b
            p = 1 / (1 + np.exp(-z))
            g = p - y
            self.w -= self.lr * (Xs.T @ g) / n
            self.b -= self.lr * g.mean()
        self._mu = X.to_numpy().mean(0)
        self._sd = X.to_numpy().std(0) + 1e-9
        self.feature_importances_ = np.abs(self.w)
        return self

    def predict_proba(self, X):
        Xs = (X.to_numpy() - self._mu) / self._sd
        p = 1 / (1 + np.exp(-(Xs @ self.w + self.b)))
        return np.column_stack([1 - p, p])


def _make_estimator():
    try:
        return tr.make_lgbm_classifier()
    except Exception:
        return _NumpyLogReg()


def build_synthetic(n=600, seed=7):
    """Eventos sinteticos con features + flags de modulo de calidad conocida."""
    rng = np.random.default_rng(seed)
    # features
    f_struct = rng.normal(0, 1, n)        # util (correlaciona con ganar)
    f_vol = rng.normal(0, 1, n)           # util
    f_noise = rng.normal(0, 1, n)         # inutil
    regime_ok = rng.integers(0, 2, n).astype(bool)   # modulo util
    qte_ok = rng.integers(0, 2, n).astype(bool)      # modulo peso muerto

    logit = 0.9 * f_struct + 0.6 * f_vol + 1.1 * regime_ok - 0.7
    p_win = 1 / (1 + np.exp(-logit))
    win = rng.random(n) < p_win
    exit_price = np.where(win, 110.0, 95.0)

    return pd.DataFrame({
        "entry_index": np.arange(n),
        "entry_price": 100.0,
        "stop_price": 95.0,
        "target_price": 110.0,
        "direction": eng.LONG,
        "bars_held": 1,
        "exit_price": exit_price,
        "outcome": np.where(win, "win", "loss"),
        "pnl_r": np.where(win, 2.0, -1.0),
        "f_struct": f_struct, "f_vol": f_vol, "f_noise": f_noise,
        "regime_ok": regime_ok, "qte_ok": qte_ok,
    })


def main():
    print("=" * 70)
    print("  HARNESS DE RESEARCH FQ - demo end-to-end (datos sinteticos)")
    print("=" * 70)

    df = build_synthetic()

    # --- Etapa 3: folds walk-forward purgados ---
    folds, valid_index = wf.folds_from_labeled(df, n_splits=8, embargo=2)
    print(f"\nfolds walk-forward: {len(folds)} | eventos validos: {len(valid_index)}")

    # --- Etapa 4+5: backtest con costes + metricas (sobre OOS pooled) ---
    pooled = ab.pooled_oos_trades(df, folds, valid_index=valid_index)
    cost = eng.CostModel()   # costes realistas Binance-perp
    res = eng.simulate(pooled, equity0=10_000, risk_frac=0.01,
                       bar_minutes=15, cost=cost)
    metrics = met.metrics_from_result(res, periods_per_year=len(pooled))
    print("\n--- Metricas OOS (con fees+slippage+funding) ---")
    print(met.format_report(metrics))

    # --- Etapa 6: modelo entrenado sobre el walk-forward ---
    feat_cols = ["f_struct", "f_vol", "f_noise"]
    X = df.loc[valid_index, feat_cols].reset_index(drop=True)
    y = (df.loc[valid_index, "outcome"] == "win").astype(int).to_numpy()
    trained = tr.train_walk_forward(X, y, folds, estimator_factory=_make_estimator)
    print(f"\n--- Modelo OOS ---\nAUC out-of-fold: {trained['oof_auc']:.4f}")
    print("Importancia de features:")
    print(trained["importances"].to_string())

    thr = tr.threshold_evaluation(
        trained["oof_scores"], trained["tested_mask"],
        df.loc[valid_index, "pnl_r"].to_numpy())
    print("\nExpectancy por umbral del modelo (traduce AUC a R):")
    print(thr.to_string(index=False))

    # --- Poda de modulos por supervivencia OOS ---
    modules = {
        "regime": lambda d: d["regime_ok"].to_numpy(),
        "qte":    lambda d: d["qte_ok"].to_numpy(),
    }
    report = ab.run_ablation(df, folds, modules, valid_index=valid_index,
                             sim_kwargs={"cost": cost, "bar_minutes": 15},
                             margin=0.0)
    print("\n--- Poda de modulos (ablacion OOS) ---")
    print(ab.attribution_story(report))
    print("\n(demo sintetico: 'regime' aporta y vive; 'qte' es peso muerto y se mata)")


if __name__ == "__main__":
    main()
