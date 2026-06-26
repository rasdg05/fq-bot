# -*- coding: utf-8 -*-
"""
================================================================================
  validation_gate — Deflated Sharpe Ratio + PBO + CPCV (Bailey & López de Prado)
  by RasDG_Sol + Claude
================================================================================
El lever de MAYOR evidencia del research (research/herramientas_quant_2026.md) NO
es data nueva — es VALIDACIÓN rigurosa. El multiple-testing hace casi inevitable un
Sharpe espurio alto: ~20 configs probadas ya dan un "5% significativo" falso. Este
módulo es el GO/NO-GO honesto:

  · probabilistic_sharpe_ratio (PSR)  — ¿el Sharpe supera un benchmark, dado T,
    skew y kurtosis (no asume normalidad)?
  · expected_max_sharpe               — el Sharpe que esperarías por PURO AZAR tras
    N trials (la vara que hay que batir).
  · deflated_sharpe_ratio (DSR)       — PSR contra esa vara -> deflacta el Sharpe por
    cuántas cosas probaste. DSR > 0.95 = significativo tras corregir overfitting.
  · cpcv_paths / pbo                   — Combinatorial Purged CV + Probability of
    Backtest Overfitting (¿el mejor in-sample queda bajo la mediana out-of-sample?).

Pure stdlib (math) + numpy. SIN scipy (no está en el sandbox): el normal CDF usa
math.erf y el inverso usa la aproximación de Acklam. Testeado contra valores conocidos.

Uso (librería):  from validation_gate import deflated_sharpe_ratio, pbo, cpcv_paths
Uso (CLI demo):  python tools/validation_gate.py
================================================================================
"""
import math
import sys
from itertools import combinations

import numpy as np

EULER_MASCHERONI = 0.5772156649015329


# ----------------------------- normal CDF / PPF (sin scipy) -----------------------------
def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p):
    """Inverso del normal estándar (Acklam). Precisión ~1e-9 en (0,1)."""
    if not (0.0 < p < 1.0):
        if p <= 0.0:
            return -math.inf
        if p >= 1.0:
            return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= phigh:
        q = p - 0.5
        r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


# ----------------------------- momentos -----------------------------
def _sharpe(r):
    r = np.asarray(r, float)
    r = r[~np.isnan(r)]
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 0 else 0.0


def _skew_kurt(r):
    """Skew y kurtosis (Pearson, kurt normal=3) — sin scipy."""
    r = np.asarray(r, float)
    r = r[~np.isnan(r)]
    n = len(r)
    if n < 3:
        return 0.0, 3.0
    m = r.mean()
    s = r.std(ddof=0)
    if s == 0:
        return 0.0, 3.0
    z = (r - m) / s
    return float((z**3).mean()), float((z**4).mean())


# ----------------------------- PSR / DSR -----------------------------
def probabilistic_sharpe_ratio(sr, sr_benchmark, n, skew=0.0, kurt=3.0):
    """P(SR_verdadero > sr_benchmark) dado SR observado (por-período), n obs, skew y
    kurtosis. No asume normalidad. sr y sr_benchmark en la MISMA frecuencia."""
    if n < 2:
        return float("nan")
    denom = math.sqrt(max(1e-12, 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr))
    return norm_cdf((sr - sr_benchmark) * math.sqrt(n - 1) / denom)


def expected_max_sharpe(n_trials, sr_std):
    """Sharpe (por-período) esperado del MEJOR de n_trials estrategias SIN skill, dada
    la dispersión (std) de los Sharpes entre trials. La vara que el azar ya regala."""
    if n_trials < 1 or sr_std <= 0:
        return 0.0
    n = max(2, int(n_trials))
    z1 = norm_ppf(1.0 - 1.0 / n)
    z2 = norm_ppf(1.0 - 1.0 / (n * math.e))
    return sr_std * ((1.0 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)


def deflated_sharpe_ratio(returns, n_trials, sr_trials_std):
    """DSR: significancia del Sharpe DEFLACTADA por multiple-testing.
    returns: serie de retornos de la MEJOR estrategia (por-período).
    n_trials: cuántas configs/estrategias se probaron (el conteo de selección).
    sr_trials_std: desviación de los Sharpes (por-período) ENTRE esos trials.
    Devuelve dict: sr, sr0 (vara), dsr (prob), significant (dsr>0.95)."""
    r = np.asarray(returns, float)
    r = r[~np.isnan(r)]
    n = len(r)
    sr = _sharpe(r)
    sk, ku = _skew_kurt(r)
    sr0 = expected_max_sharpe(n_trials, sr_trials_std)
    dsr = probabilistic_sharpe_ratio(sr, sr0, n, sk, ku)
    return {"sr": sr, "sr0": sr0, "dsr": float(dsr),
            "significant": bool(dsr > 0.95), "n": int(n),
            "n_trials": int(n_trials), "skew": sk, "kurt": ku}


def deflated_from_trials(returns_best, all_trial_sharpes):
    """Conveniencia: deriva n_trials y sr_trials_std del set de Sharpes probados."""
    s = np.asarray(all_trial_sharpes, float)
    s = s[~np.isnan(s)]
    return deflated_sharpe_ratio(returns_best, len(s), float(s.std(ddof=1)) if len(s) > 1 else 0.0)


# ----------------------------- CPCV + PBO -----------------------------
def cpcv_paths(n_samples, n_groups=6, n_test_groups=2, embargo_frac=0.01):
    """Combinatorial Purged CV: parte [0,n) en n_groups bloques contiguos; por cada
    combinación de n_test_groups bloques como TEST, el resto es TRAIN, PURGADO (se
    quita el train dentro de embargo del borde de cada test). Devuelve lista de
    (train_idx, test_idx). C(n_groups, n_test_groups) caminos."""
    idx = np.arange(n_samples)
    bounds = np.linspace(0, n_samples, n_groups + 1).astype(int)
    blocks = [idx[bounds[i]:bounds[i + 1]] for i in range(n_groups)]
    emb = max(1, int(embargo_frac * n_samples))
    out = []
    for test_combo in combinations(range(n_groups), n_test_groups):
        test_idx = np.concatenate([blocks[g] for g in test_combo])
        test_set = set(test_idx.tolist())
        # purga+embargo: saco del train lo que cae dentro de `emb` de cualquier test
        purged = []
        for g in range(n_groups):
            if g in test_combo:
                continue
            for i in blocks[g]:
                lo, hi = i - emb, i + emb
                if any((j in test_set) for j in range(lo, hi + 1)):
                    continue
                purged.append(i)
        out.append((np.array(sorted(purged)), np.sort(test_idx)))
    return out


def pbo(perf_matrix, n_splits=10):
    """Probability of Backtest Overfitting (CSCV, Bailey et al.). perf_matrix: (T x N)
    de performance por período (filas) y estrategia (columnas, N configs). Parte T en
    n_splits; por cada combinación de la mitad como IS (resto OOS): elige la mejor IS,
    mira su rango OOS; PBO = fracción de combos donde la mejor IS queda BAJO la mediana
    OOS (logit<0). PBO alto -> selección sobre-ajustada."""
    M = np.asarray(perf_matrix, float)
    T, N = M.shape
    if N < 2 or T < n_splits:
        return float("nan")
    bnd = np.linspace(0, T, n_splits + 1).astype(int)
    parts = [np.arange(bnd[i], bnd[i + 1]) for i in range(n_splits)]
    logits = []
    for is_combo in combinations(range(n_splits), n_splits // 2):
        is_rows = np.concatenate([parts[i] for i in is_combo])
        oos_rows = np.concatenate([parts[i] for i in range(n_splits) if i not in is_combo])
        is_perf = M[is_rows].mean(axis=0)
        oos_perf = M[oos_rows].mean(axis=0)
        best = int(np.argmax(is_perf))
        # rango relativo OOS del mejor IS (1=mejor OOS, 0=peor)
        rank = (oos_perf < oos_perf[best]).sum() / (N - 1)
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(math.log(rank / (1 - rank)))
    logits = np.asarray(logits)
    return float((logits < 0).mean())


# ----------------------------- CLI demo / autotest -----------------------------
def _demo():
    rng_like = np.cos(np.arange(2000) * 0.1) * 0.0 + 0.0  # placeholder determinista
    print("=== validation_gate — sanity (sin red, determinista) ===")
    # PSR de una serie con Sharpe modesto
    t = np.linspace(0, 1, 1000)
    good = 0.001 + 0.01 * np.sin(t * 50)        # media>0
    d = deflated_sharpe_ratio(good, n_trials=20, sr_trials_std=0.02)
    print("DSR ejemplo: SR=%.4f vara(sr0)=%.4f DSR=%.3f significativo=%s"
          % (d["sr"], d["sr0"], d["dsr"], d["significant"]))
    print("norm_ppf(0.975)=%.4f (esperado ~1.95996)" % norm_ppf(0.975))
    print("expected_max_sharpe(20, 0.02)=%.4f (>0, la vara que el azar regala)"
          % expected_max_sharpe(20, 0.02))
    # CPCV
    paths = cpcv_paths(600, n_groups=6, n_test_groups=2)
    print("CPCV: %d caminos (C(6,2)=15); 1er test n=%d train n=%d"
          % (len(paths), len(paths[0][1]), len(paths[0][0])))
    return 0


def main(argv):
    return _demo()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
