# -*- coding: utf-8 -*-
"""
bt_train (etapa 6): entrenamiento walk-forward. Se testea con un estimador
inyectado trivial (sin lightgbm/sklearn) y AUC por rangos.
"""
import numpy as np
import pandas as pd
import pytest

import bt_train as tr
import bt_walkforward as wf


# Estimador de juguete: "predice" usando una sola feature (umbral aprendido = su
# media en el train). Sirve para validar el cableado de train/predict/OOS.
class _FeatureThreshold:
    def __init__(self, col="signal"):
        self.col = col
        self.mid = 0.0
        self.feature_importances_ = None

    def fit(self, X, y, **kw):
        self.mid = float(X[self.col].mean())
        self.feature_importances_ = np.array(
            [1.0 if c == self.col else 0.0 for c in X.columns])
        return self

    def predict_proba(self, X):
        # prob monotona en la feature: sigmoide centrada en mid
        z = (X[self.col].to_numpy() - self.mid)
        p = 1.0 / (1.0 + np.exp(-z))
        return np.column_stack([1 - p, p])


# --------------------------------------------------------------------------
# make_lgbm_classifier — contrato de construccion
# --------------------------------------------------------------------------
def test_make_lgbm_classifier_builds_when_available():
    """Con lightgbm + scikit-learn instalados (entorno de research), el
    classifier DEBE construirse. Atrapa el "install verde pero modelo degradado
    en silencio": `import lightgbm` pasa pero LGBMClassifier (en lightgbm.sklearn)
    truena por falta de scikit-learn. En CI normal (sin deps) se omite; en el CI
    de research, que instala ambas, se ejecuta de verdad.
    """
    pytest.importorskip("lightgbm")
    pytest.importorskip("sklearn")
    clf = tr.make_lgbm_classifier()
    assert type(clf).__name__ == "LGBMClassifier"
    assert clf.get_params()["n_estimators"] == 300


# --------------------------------------------------------------------------
# roc_auc
# --------------------------------------------------------------------------
def test_auc_perfect_separation():
    y = [0, 0, 1, 1]
    s = [0.1, 0.2, 0.8, 0.9]
    assert tr.roc_auc(y, s) == pytest.approx(1.0)


def test_auc_random_is_half_with_ties():
    y = [0, 1, 0, 1]
    s = [0.5, 0.5, 0.5, 0.5]      # todo empatado -> 0.5
    assert tr.roc_auc(y, s) == pytest.approx(0.5)


def test_auc_inverted_is_zero():
    y = [0, 0, 1, 1]
    s = [0.9, 0.8, 0.2, 0.1]
    assert tr.roc_auc(y, s) == pytest.approx(0.0)


def test_auc_none_single_class():
    assert tr.roc_auc([1, 1, 1], [0.2, 0.5, 0.7]) is None


# --------------------------------------------------------------------------
# train_walk_forward
# --------------------------------------------------------------------------
def _make_dataset(n=120, signal_strength=3.0, seed=0):
    rng = np.random.default_rng(seed)
    # feature 'signal' correlacionada con la etiqueta; 'noise' no.
    y = rng.integers(0, 2, size=n)
    signal = y * signal_strength + rng.normal(0, 1, size=n)
    noise = rng.normal(0, 1, size=n)
    X = pd.DataFrame({"signal": signal, "noise": noise})
    return X, y


def test_train_walk_forward_produces_oos_predictions():
    X, y = _make_dataset(n=120)
    t0 = np.arange(120, dtype=float)
    t1 = t0 + 1
    folds = wf.purged_walk_forward_splits(t0, t1, n_splits=5)
    res = tr.train_walk_forward(X, y, folds,
                                estimator_factory=lambda: _FeatureThreshold())
    # cubrio los bloques de test (todos menos el primero)
    assert res["tested_mask"].sum() > 0
    # con senal fuerte, el AUC OOS debe superar claramente el azar
    assert res["oof_auc"] is not None and res["oof_auc"] > 0.7
    # importancia: 'signal' domina a 'noise'
    assert res["importances"]["signal"] > res["importances"]["noise"]
    assert len(res["models"]) == len(folds)


def test_train_handles_estimator_without_proba():
    class _HardPredictor:
        def fit(self, X, y, **kw):
            self.mid = float(X["signal"].mean())
            return self
        def predict(self, X):
            return (X["signal"].to_numpy() > self.mid).astype(int)
    X, y = _make_dataset(n=80)
    t0 = np.arange(80, dtype=float)
    folds = wf.purged_walk_forward_splits(t0, t0 + 1, n_splits=4)
    res = tr.train_walk_forward(X, y, folds,
                                estimator_factory=lambda: _HardPredictor())
    assert res["tested_mask"].sum() > 0
    assert res["importances"] is None      # no expone feature_importances_


def test_sample_weight_is_passed_through():
    captured = {}
    class _WeightSpy:
        def fit(self, X, y, sample_weight=None):
            captured["w_len"] = None if sample_weight is None else len(sample_weight)
            return self
        def predict(self, X):
            return np.zeros(len(X))
    X, y = _make_dataset(n=60)
    t0 = np.arange(60, dtype=float)
    folds = wf.purged_walk_forward_splits(t0, t0 + 1, n_splits=3)
    w = np.ones(60)
    tr.train_walk_forward(X, y, folds,
                          estimator_factory=lambda: _WeightSpy(),
                          sample_weight=w)
    # el peso del train llega con la longitud del fold de train
    assert captured["w_len"] is not None and captured["w_len"] > 0


# --------------------------------------------------------------------------
# threshold_evaluation
# --------------------------------------------------------------------------
def test_threshold_evaluation_filters_by_score():
    # 5 senales OOS; score alto coincide con pnl_r positivo.
    oof = np.array([np.nan, 0.9, 0.4, 0.8, 0.2])
    tested = np.array([False, True, True, True, True])
    pnl_r = np.array([0.0, 2.0, -1.0, 1.5, -1.0])
    df = tr.threshold_evaluation(oof, tested, pnl_r, thresholds=[0.5, 0.85])
    row50 = df[df["threshold"] == 0.5].iloc[0]
    row85 = df[df["threshold"] == 0.85].iloc[0]
    assert row50["n"] == 2                  # scores 0.9 y 0.8
    assert row85["n"] == 1                  # solo 0.9
    assert row85["expectancy_r"] == pytest.approx(2.0)
    # subir el umbral mejora la expectancy (se queda con lo mejor)
    assert row85["expectancy_r"] >= row50["expectancy_r"]
