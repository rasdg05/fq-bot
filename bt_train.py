# -*- coding: utf-8 -*-
"""
================================================================================
  BT TRAIN - entrenamiento del modelo sobre walk-forward purgado
  by RasDG_Sol + Claude

  Etapa 6 del harness de research. Entrena un clasificador (LightGBM por
  defecto) que predice la probabilidad de que una senal GANE, usando SOLO los
  folds walk-forward purgados de bt_walkforward. Eso convierte el "ensemble ML"
  aspiracional en un modelo REALMENTE aprendido de datos, con validacion honesta
  out-of-sample (sin fuga).

  Salida clave: predicciones out-of-fold (OOF) -> con ellas se mide AUC y, al
  umbralizar la probabilidad, la expectancy_r OOS de la sub-cartera filtrada por
  el modelo. Asi sabes si el modelo aporta edge real, no in-sample.

  Diseno mockeable: el estimador entra por factoria (cualquier objeto con
  .fit(X,y) y .predict_proba/.predict). make_lgbm_classifier() crea LightGBM con
  import perezoso, de modo que el modulo se importa y se testea sin lightgbm.
  AUC se calcula por rangos (Mann-Whitney) para no depender de sklearn.
================================================================================
"""
import logging

import numpy as np
import pandas as pd

log = logging.getLogger("bt_train")


# ============================================================
# METRICA: AUC por rangos (sin sklearn)
# ============================================================
def roc_auc(y_true, scores):
    """AUC ROC via el estadistico de Mann-Whitney. None si hay una sola clase."""
    y = np.asarray(y_true).astype(int)
    s = np.asarray(scores, dtype="float64")
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), dtype="float64")
    ranks[order] = np.arange(1, len(s) + 1)
    # promedia rangos en empates
    _assign_tied_ranks(s, ranks)
    sum_pos = ranks[y == 1].sum()
    return float((sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _assign_tied_ranks(s, ranks):
    order = np.argsort(s, kind="mergesort")
    s_sorted = s[order]
    i = 0
    n = len(s)
    while i < n:
        j = i
        while j + 1 < n and s_sorted[j + 1] == s_sorted[i]:
            j += 1
        if j > i:
            avg = (i + 1 + j + 1) / 2.0   # rangos 1-indexados
            ranks[order[i:j + 1]] = avg
        i = j + 1


# ============================================================
# FACTORIA LIGHTGBM (import perezoso)
# ============================================================
def make_lgbm_classifier(**overrides):
    """Crea un LGBMClassifier con defaults sensatos. Import perezoso para que el
    modulo se importe y se testee sin lightgbm instalado.
    """
    import lightgbm as lgb  # perezoso a proposito

    params = {
        "n_estimators": 300,
        "learning_rate": 0.03,
        "num_leaves": 31,
        "max_depth": -1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_samples": 30,
        "reg_lambda": 1.0,
        "random_state": 42,
        "n_jobs": -1,
        "verbose": -1,
    }
    params.update(overrides)
    return lgb.LGBMClassifier(**params)


# ============================================================
# PREDICCION ROBUSTA (predict_proba o predict)
# ============================================================
def _predict_scores(model, X):
    if hasattr(model, "predict_proba"):
        proba = np.asarray(model.predict_proba(X))
        if proba.ndim == 2 and proba.shape[1] >= 2:
            return proba[:, 1]
        return proba.ravel()
    return np.asarray(model.predict(X)).ravel()


# ============================================================
# ENTRENAMIENTO WALK-FORWARD
# ============================================================
def train_walk_forward(X, y, folds, estimator_factory=None,
                       sample_weight=None):
    """Entrena un modelo por fold (train) y predice su test (OOS).

    X: DataFrame de features (indices posicionales 0..N-1 alineados a los folds).
    y: array binario (1 = la senal gano).
    folds: lista de (train_idx, test_idx) de bt_walkforward.
    estimator_factory: callable() -> estimador (.fit/.predict[_proba]).
                       Default: make_lgbm_classifier.
    sample_weight: opcional, peso por muestra (p.ej. unicidad LdP).

    Devuelve dict:
      oof_scores : array (N,) con la prob OOS por evento (NaN si nunca fue test)
      tested_mask: bool (N,) True donde hay prediccion OOS
      fold_metrics: lista de dicts por fold (n_train, n_test, auc)
      models     : lista de modelos entrenados (uno por fold)
      importances: Series de importancia media de features (si el modelo expone
                   feature_importances_), si no None
      oof_auc    : AUC global sobre todas las predicciones OOS
    """
    if estimator_factory is None:
        estimator_factory = make_lgbm_classifier
    X = X.reset_index(drop=True)
    y = np.asarray(y).astype(int)
    n = len(X)

    oof = np.full(n, np.nan, dtype="float64")
    tested = np.zeros(n, dtype=bool)
    fold_metrics = []
    models = []
    importance_acc = None
    importance_count = 0

    for fi, (train_idx, test_idx) in enumerate(folds):
        X_tr, y_tr = X.iloc[train_idx], y[train_idx]
        X_te, y_te = X.iloc[test_idx], y[test_idx]
        model = estimator_factory()
        fit_kwargs = {}
        if sample_weight is not None:
            fit_kwargs["sample_weight"] = np.asarray(sample_weight)[train_idx]
        model.fit(X_tr, y_tr, **fit_kwargs)

        scores = _predict_scores(model, X_te)
        oof[test_idx] = scores
        tested[test_idx] = True
        models.append(model)

        fold_metrics.append({
            "fold": fi,
            "n_train": len(train_idx),
            "n_test": len(test_idx),
            "auc": roc_auc(y_te, scores),
        })

        if hasattr(model, "feature_importances_"):
            imp = np.asarray(model.feature_importances_, dtype="float64")
            importance_acc = imp if importance_acc is None else importance_acc + imp
            importance_count += 1

    importances = None
    if importance_acc is not None and importance_count > 0:
        importances = pd.Series(importance_acc / importance_count,
                                index=X.columns).sort_values(ascending=False)

    oof_auc = roc_auc(y[tested], oof[tested]) if tested.any() else None

    return {
        "oof_scores": oof,
        "tested_mask": tested,
        "fold_metrics": fold_metrics,
        "models": models,
        "importances": importances,
        "oof_auc": oof_auc,
    }


# ============================================================
# EVALUACION ECONOMICA DEL MODELO (umbral -> expectancy OOS)
# ============================================================
def threshold_evaluation(oof_scores, tested_mask, pnl_r, thresholds=None):
    """Para cada umbral de probabilidad, selecciona las senales OOS con score >=
    umbral y mide cuantas son, su win_rate aproximado y su expectancy_r.

    Asi traduces el AUC a dinero: 'tomando solo el top X% del modelo, la
    expectancy sube de A a B'. Devuelve un DataFrame ordenado por umbral.
    """
    if thresholds is None:
        thresholds = [round(x, 2) for x in np.arange(0.50, 0.91, 0.05)]
    pnl_r = np.asarray(pnl_r, dtype="float64")
    scores = np.asarray(oof_scores, dtype="float64")
    mask = np.asarray(tested_mask, dtype=bool)

    rows = []
    base_idx = np.where(mask)[0]
    for thr in thresholds:
        sel = base_idx[scores[base_idx] >= thr]
        if len(sel) == 0:
            rows.append({"threshold": thr, "n": 0, "win_rate": None,
                         "expectancy_r": None, "total_r": 0.0})
            continue
        p = pnl_r[sel]
        rows.append({
            "threshold": thr,
            "n": int(len(sel)),
            "win_rate": float((p > 0).mean()),
            "expectancy_r": float(p.mean()),
            "total_r": float(p.sum()),
        })
    return pd.DataFrame(rows)
