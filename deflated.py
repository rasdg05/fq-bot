# -*- coding: utf-8 -*-
"""
================================================================================
  DEFLATED SHARPE RATIO (DSR) + PROBABILITY OF BACKTEST OVERFITTING (PBO)
  by RasDG_Sol + Claude  --  el veredicto ANTI-SUERTE

  Cuando se prueban ~N configuraciones (anchos del sweep x selectores x simbolos)
  y una sale con edge positivo, ese edge podria ser SOLO la mas afortunada de N
  muestras: con suficientes intentos, el maximo Sharpe de N series de PURO RUIDO
  es positivo y "se ve bien". DSR y PBO cuantifican exactamente ese riesgo.

    * DSR (Bailey & Lopez de Prado, 2014, "The Deflated Sharpe Ratio: Correcting
      for Selection Bias, Backtest Overfitting and Non-Normality"): deshincha el
      Sharpe observado por (a) el numero de intentos N y la dispersion de sus
      Sharpes, y (b) la no-normalidad (skew/kurtosis) de los retornos. Devuelve la
      probabilidad de que el Sharpe VERDADERO supere el benchmark deshinchado SR0.
      Regla de embarque: DSR >= 0.95.

    * PBO (Bailey, Borwein, Lopez de Prado & Zhu, 2017, "The Probability of
      Backtest Overfitting", via CSCV -- Combinatorially Symmetric Cross
      Validation): de una matriz (tiempo x configuraciones), particiona el tiempo,
      elige IS/OOS por todas las combinaciones, y mide con que frecuencia la mejor
      config IN-SAMPLE queda por DEBAJO de la mediana OUT-OF-SAMPLE. PBO ~ 0 =
      robusto; PBO >= 0.5 = el ranking IS no predice el OOS (overfit puro).

  Modulo PURO: numpy (+ scipy.stats.norm si esta disponible). Si scipy no esta,
  se usa un fallback erf-based para Phi y una aproximacion racional (Acklam) para
  Phi^-1; ambos con error << 1e-7, suficiente para un veredicto de embarque.
  Sin red, sin estado, sin tocar el monolito.
================================================================================
"""
import math

import numpy as np

# Euler-Mascheroni y e, constantes del termino del MAXIMO ESPERADO de N normales.
_EULER_MASCHERONI = 0.5772156649015329
_E = math.e

# --- Phi / Phi^-1: scipy si esta, si no fallback puro (documentado) -----------
try:  # pragma: no cover - la rama depende del entorno
    from scipy.stats import norm as _norm

    def _Phi(x):
        """CDF normal estandar Phi(x) = P(Z <= x)."""
        return float(_norm.cdf(x))

    def _Phi_inv(p):
        """Cuantil normal estandar Phi^-1(p) (inversa de la CDF)."""
        return float(_norm.ppf(p))

    _HAVE_SCIPY = True
except Exception:  # scipy ausente -> fallback puro numpy/math
    _HAVE_SCIPY = False

    def _Phi(x):
        """CDF normal estandar via math.erf: Phi(x) = 0.5*(1 + erf(x/sqrt(2)))."""
        return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))

    # Aproximacion racional de Acklam para Phi^-1 (Peter Acklam, 2003). Error
    # relativo < 1.15e-9 en doble precision tras un paso de refinamiento Halley.
    # Coeficientes publicos; no requieren dependencias.
    _A = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
          1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    _B = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
          6.680131188771972e+01, -1.328068155288572e+01)
    _C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
          -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    _D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
          3.754408661907416e+00)
    _P_LOW = 0.02425
    _P_HIGH = 1.0 - _P_LOW

    def _Phi_inv(p):
        """Cuantil normal estandar via aproximacion racional de Acklam + 1 paso
        de Halley. p en (0,1); fuera de rango devuelve +/-inf como scipy.ppf."""
        p = float(p)
        if p <= 0.0:
            return -math.inf
        if p >= 1.0:
            return math.inf
        if p < _P_LOW:
            q = math.sqrt(-2.0 * math.log(p))
            x = (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / \
                ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
        elif p <= _P_HIGH:
            q = p - 0.5
            r = q * q
            x = (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q / \
                (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0)
        else:
            q = math.sqrt(-2.0 * math.log(1.0 - p))
            x = -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / \
                ((((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0)
        # refinamiento de Halley: una iteracion lleva el error a ~maquina
        e = _Phi(x) - p
        u = e * math.sqrt(2.0 * math.pi) * math.exp(x * x / 2.0)
        x = x - u / (1.0 + x * u / 2.0)
        return x


def _as_1d(returns):
    r = np.asarray(returns, dtype="float64").ravel()
    return r[np.isfinite(r)]


def _moments(r):
    """SR per-period, skew (g3) y kurtosis (g4, NO-excess: normal=3).

    Usa el estimador POBLACIONAL de momentos (divisor n) para g3/g4 -- la
    convencion de Bailey & Lopez de Prado para la varianza del estimador del
    Sharpe -- y std MUESTRAL (ddof=1) para el Sharpe en si, consistente con
    bt_metrics.sharpe (ddof=1). Devuelve (sr, g3, g4_nonexcess).
    """
    n = len(r)
    mean = float(r.mean())
    sd_sample = float(r.std(ddof=1))           # ddof=1: igual que bt_metrics.sharpe
    sr = mean / sd_sample if sd_sample > 0 else 0.0
    sd_pop = float(r.std(ddof=0))              # momentos centrales: divisor n
    if sd_pop > 0:
        z = (r - mean) / sd_pop
        g3 = float(np.mean(z ** 3))            # skewness (Fisher-Pearson poblacional)
        g4_nonexcess = float(np.mean(z ** 4))  # kurtosis NO-excess (normal -> 3.0)
    else:
        g3, g4_nonexcess = 0.0, 3.0
    return sr, g3, g4_nonexcess


def expected_max_sharpe(n_trials, trials_sr_var):
    """SR0 deshinchado = MAXIMO ESPERADO del Sharpe de N intentos de media-cero.

    Bailey & Lopez de Prado (2014), ec. del estadistico del maximo de N normales:

        SR0 = sqrt(V) * [ (1 - gamma) * Z^-1(1 - 1/N)
                          +     gamma  * Z^-1(1 - 1/(N*e)) ]

    con V = trials_sr_var (varianza de los Sharpes de los N intentos), gamma =
    Euler-Mascheroni (0.5772), e = exp(1), Z^-1 = Phi^-1 (cuantil normal). Es la
    barra que un Sharpe debe superar SOLO por haber probado N veces: crece con N
    (mas intentos => max por azar mas alto) y con la dispersion V de los intentos.
    """
    n = int(n_trials)
    v = float(trials_sr_var)
    if n <= 1 or v <= 0.0:
        return 0.0
    z1 = _Phi_inv(1.0 - 1.0 / n)
    z2 = _Phi_inv(1.0 - 1.0 / (n * _E))
    return math.sqrt(v) * ((1.0 - _EULER_MASCHERONI) * z1 + _EULER_MASCHERONI * z2)


# Default conservador de varianza de Sharpes cuando el caller NO la puede pasar
# (un solo intento medible). Es un PLACEHOLDER explicito, NO una medicion: asume
# que los Sharpes de los intentos tienen sd ~ 0.5 (var 0.25), un spread tipico
# pero arbitrario. Cuando se usa, el resultado lleva flag 'sr0_var_default'=True.
_DEFAULT_TRIALS_SR_VAR = 0.25


def deflated_sharpe_ratio(returns, n_trials, *, trials_sr_var=None,
                          sr_benchmark=0.0):
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).

    returns       : serie de retornos POR PERIODO (p.ej. net return por trade).
    n_trials      : N = numero de configuraciones probadas (sweep x selector x
                    simbolo). A mayor N, mas se deshincha (mas chances de suerte).
    trials_sr_var : V = varianza de los Sharpes de esos N intentos. Es la
                    DISPERSION del conjunto de intentos; sin ella no se puede
                    deshinchar por dispersion. Si es None y N>1, se cae a un
                    default conservador documentado (_DEFAULT_TRIALS_SR_VAR) y se
                    marca el flag 'sr0_var_default'=True para que el caller avise.
    sr_benchmark  : barra MINIMA adicional de Sharpe per-period (default 0). El
                    benchmark efectivo es max(sr_benchmark, SR0_deshinchado).

    Pasos:
      1) SR = mean/std(ddof=1); T = len(returns); g3 = skew; g4 = kurtosis
         NO-excess (normal=3). [g4 NO-excess para casar con la ec. de BLdP, que
         usa el termino (g4-1)/4; con g4=3 da el 0.5 gaussiano.]
      2) SR0 = expected_max_sharpe(N, V)  (= barra por multiples intentos).
      3) DSR = Phi( (SR - SR0_eff) * sqrt(T-1)
                    / sqrt(1 - g3*SR + ((g4-1)/4)*SR^2) ),  clip a [0,1],
         con SR0_eff = max(sr_benchmark, SR0).

    DSR = P(Sharpe verdadero > SR0_eff | N intentos, no-normalidad). Embarque si
    DSR >= 0.95. Devuelve dict {sr, T, skew, kurt, sr0, dsr[, sr0_var_default]}.
    """
    r = _as_1d(returns)
    T = int(len(r))
    if T < 2:
        return {"sr": None, "T": T, "skew": None, "kurt": None,
                "sr0": None, "dsr": None}

    sr, g3, g4 = _moments(r)                    # g4 NO-excess (normal -> 3.0)

    flag_default = False
    if trials_sr_var is None:
        if int(n_trials) <= 1:
            v = 0.0                             # 1 intento: nada que deshinchar
        else:
            v = _DEFAULT_TRIALS_SR_VAR          # fallback conservador, se FLAGea
            flag_default = True
    else:
        v = float(trials_sr_var)

    sr0 = expected_max_sharpe(n_trials, v)
    sr0_eff = max(float(sr_benchmark), sr0)

    # denominador = sd del estimador del Sharpe bajo no-normalidad (BLdP).
    denom_var = 1.0 - g3 * sr + ((g4 - 1.0) / 4.0) * (sr ** 2)
    denom_var = max(denom_var, 1e-12)           # guarda numerica (casi nunca <=0)
    z = (sr - sr0_eff) * math.sqrt(max(T - 1, 0)) / math.sqrt(denom_var)
    dsr = float(np.clip(_Phi(z), 0.0, 1.0))

    out = {"sr": float(sr), "T": T, "skew": float(g3), "kurt": float(g4),
           "sr0": float(sr0_eff), "dsr": dsr}
    if flag_default:
        out["sr0_var_default"] = True
    return out


def probability_backtest_overfitting(config_returns, n_splits=8,
                                     max_combos=2000, seed=0):
    """Probability of Backtest Overfitting via CSCV (Bailey et al., 2017).

    config_returns : matriz 2D (filas = buckets de tiempo/trade, cols = configs).
                     Cada columna es la serie de retornos de UNA configuracion
                     alineada en el tiempo. Necesita >= 2 columnas y >= n_splits
                     filas.
    n_splits       : S = numero de grupos en que se parte el tiempo (par; CSCV
                     toma la MITAD de los grupos como IS y la otra mitad como OOS).
    max_combos     : tope de combinaciones C(S, S/2) evaluadas. Si el total excede
                     el tope, se MUESTREA un subconjunto aleatorio reproducible
                     (seed) y se documenta en n_combos / sampled.

    Procedimiento (para cada particion IS/OOS):
      1) rank de configs por Sharpe IN-SAMPLE; se toma la MEJOR IS (n*).
      2) rank OOS de esa misma n*; se mapea a un logit
         lambda = ln( w / (1 - w) ), w = rank_relativo_OOS de n* en (0,1).
      3) la config esta OVERFIT en esta particion si su rank OOS cae por DEBAJO de
         la mediana (lambda <= 0, i.e. w <= 0.5).
    PBO = fraccion de particiones con la mejor-IS por debajo de la mediana OOS.
    PBO ~ 0 => el ganador IS sigue ganando OOS (robusto). PBO >= 0.5 => el ranking
    IS no informa el OOS (overfit). Devuelve {pbo, n_combos[, sampled, logits...]}.
    """
    import itertools

    M = np.asarray(config_returns, dtype="float64")
    if M.ndim != 2:
        raise ValueError("config_returns debe ser 2D (filas=tiempo, cols=configs)")
    n_rows, n_cfg = M.shape
    S = int(n_splits)
    if S % 2 != 0:
        S -= 1                                   # CSCV requiere S par (mitades)
    if n_cfg < 2 or S < 2 or n_rows < S:
        return {"pbo": None, "n_combos": 0,
                "note": "muestra insuficiente (cols<2 o filas<n_splits)"}

    # particion del TIEMPO en S grupos contiguos casi-iguales (orden cronologico).
    groups = np.array_split(np.arange(n_rows), S)

    def _sr_cols(rows_idx):
        """Sharpe per-period por columna sobre las filas dadas (ddof=1).
        Columnas con sd 0 o <2 muestras -> -inf (nunca pueden ser 'mejor IS')."""
        sub = M[rows_idx, :]
        if sub.shape[0] < 2:
            return np.full(n_cfg, -np.inf)
        mean = sub.mean(axis=0)
        sd = sub.std(axis=0, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            sr = np.where(sd > 0, mean / sd, -np.inf)
        return sr

    half = S // 2
    all_combos = list(itertools.combinations(range(S), half))
    sampled = False
    if len(all_combos) > int(max_combos):
        rng = np.random.default_rng(seed)
        pick = rng.choice(len(all_combos), size=int(max_combos), replace=False)
        combos = [all_combos[i] for i in pick]
        sampled = True
    else:
        combos = all_combos

    logits = []
    n_overfit = 0
    for is_groups in combos:
        is_set = set(is_groups)
        is_rows = np.concatenate([groups[g] for g in range(S) if g in is_set])
        oos_rows = np.concatenate([groups[g] for g in range(S) if g not in is_set])
        sr_is = _sr_cols(is_rows)
        sr_oos = _sr_cols(oos_rows)
        if not np.isfinite(sr_is).any() or not np.isfinite(sr_oos).any():
            continue
        best = int(np.argmax(sr_is))             # mejor config IN-SAMPLE
        # rank relativo OOS de la mejor-IS en (0,1): fraccion de configs que
        # rinden <= que ella OOS. method='average' reparte empates.
        order = sr_oos.argsort(kind="mergesort")
        ranks = np.empty(n_cfg, dtype="float64")
        ranks[order] = np.arange(1, n_cfg + 1)   # 1..n_cfg (peor..mejor)
        # promedia rangos en empates para estabilidad
        w = ranks[best] / (n_cfg + 1.0)          # en (0,1), evita 0 y 1 exactos
        lam = math.log(w / (1.0 - w))            # logit del rank OOS
        logits.append(lam)
        if w <= 0.5:                             # por debajo de la mediana OOS
            n_overfit += 1

    n_used = len(logits)
    if n_used == 0:
        return {"pbo": None, "n_combos": 0,
                "note": "sin particiones evaluables (todas degeneradas)"}
    pbo = float(n_overfit / n_used)
    out = {"pbo": pbo, "n_combos": int(n_used),
           "logit_mean": float(np.mean(logits))}
    if sampled:
        out["sampled"] = True
        out["n_combos_total"] = int(len(all_combos))
    return out
