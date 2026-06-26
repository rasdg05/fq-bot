# -*- coding: utf-8 -*-
"""
================================================================================
  sizing — vol-targeting + Hierarchical Risk Parity (lever de sizing, evidenciado)
  by RasDG_Sol + Claude
================================================================================
El research (research/herramientas_quant_2026.md): el sizing es el lever sub-explorado.
Dos piezas evidenciadas, ambas FREE y pure-numpy (sin scipy):

  · VOL-TARGETING — escala la posición para que la vol realizada ≈ target. Su beneficio
    de Sharpe es ESPECÍFICO por clase de activo (equities sí; commodities/FX no) -> hay
    que VALIDARLO en crypto, no asumirlo. Pero su reducción de tail-risk / vol-of-vol es
    casi universal -> vale para control de drawdown. vol_target_series() lo aplica y
    compara Sharpe/tails IN vs OUT para decidir con datos.
  · HIERARCHICAL RISK PARITY (HRP, López de Prado) — asigna pesos sin invertir la
    covarianza (el paso más frágil cuando los activos están MUY correlacionados, como
    BTC/ETH/SOL ~0.8). Robustez, no máquina de Sharpe. Clustering aglomerativo manual
    (average-linkage) + quasi-diag + bisección recursiva.

Conecta con el historial MEXC del operador: el leverage/sizing fue lo que borró su
edge. Esto es la disciplina de sizing, cableada y validable.

Uso (librería): from sizing import vol_target_weight, vol_target_series, hrp_weights
Uso (CLI demo): python tools/sizing.py
================================================================================
"""
import sys

import numpy as np

ANN = np.sqrt(365 * 288)   # anualización aproximada para series 5m (referencia)


# ----------------------------- VOL-TARGETING -----------------------------
def vol_target_weight(returns, target_vol, lookback=20, max_leverage=3.0):
    """Peso (multiplicador de posición) para que la vol realizada ≈ target_vol.
    Usa SÓLO la ventana pasada (causal). Cap en max_leverage."""
    r = np.asarray(returns, float)
    r = r[~np.isnan(r)]
    if len(r) < 2:
        return 1.0
    rv = np.std(r[-lookback:], ddof=1) if len(r) >= lookback else np.std(r, ddof=1)
    if rv <= 0:
        return float(max_leverage)
    return float(min(max_leverage, target_vol / rv))


def vol_target_series(returns, target_vol=None, lookback=20, max_leverage=3.0):
    """Aplica vol-targeting CAUSAL a una serie y devuelve métricas IN (sin escalar) vs
    OUT (escalado) para DECIDIR si ayuda en crypto: sharpe, vol-of-vol, peor retorno.
    target_vol default = vol media de la serie (auto-escala a su propio nivel)."""
    r = np.asarray(returns, float)
    r = r[~np.isnan(r)]
    n = len(r)
    if n < lookback + 5:
        return None
    tv = target_vol if target_vol is not None else float(np.std(r, ddof=1))
    w = np.ones(n)
    for i in range(lookback, n):
        rv = np.std(r[i - lookback:i], ddof=1)
        w[i] = min(max_leverage, tv / rv) if rv > 0 else max_leverage
    scaled = r * w   # peso de la barra i usa SÓLO datos hasta i-1 (causal)

    def _m(x):
        x = x[lookback:]                      # comparar sobre el mismo tramo
        sd = x.std(ddof=1)
        sr = x.mean() / sd if sd > 0 else 0.0
        # vol-of-vol: std de la vol rodante (estabilidad)
        rollv = np.array([x[max(0, j - lookback):j].std(ddof=1) for j in range(lookback, len(x))])
        vov = float(rollv.std(ddof=1)) if len(rollv) > 2 else float("nan")
        return {"sharpe": float(sr), "vol_of_vol": vov, "worst": float(x.min())}

    return {"in": _m(r), "out": _m(scaled),
            "sharpe_uplift": _m(scaled)["sharpe"] - _m(r)["sharpe"]}


# ----------------------------- HIERARCHICAL RISK PARITY -----------------------------
def _quasi_diag_order(dist):
    """Orden de hojas por clustering aglomerativo average-linkage (sin scipy).
    Agrupa los activos correlacionados juntos -> la quasi-diagonal de López de Prado."""
    n = dist.shape[0]
    members = {i: [i] for i in range(n)}      # cluster id -> hojas
    active = set(range(n))
    nxt = n

    def _cdist(a, b):
        ma, mb = members[a], members[b]
        return np.mean([dist[i, j] for i in ma for j in mb])

    while len(active) > 1:
        al = sorted(active)
        best, bp = np.inf, None
        for ii in range(len(al)):
            for jj in range(ii + 1, len(al)):
                dd = _cdist(al[ii], al[jj])
                if dd < best:
                    best, bp = dd, (al[ii], al[jj])
        a, b = bp
        members[nxt] = members[a] + members[b]
        active.discard(a); active.discard(b); active.add(nxt)
        nxt += 1
    return members[next(iter(active))]


def _cluster_var(cov, idx):
    """Varianza de un cluster con pesos inverse-variance (López de Prado)."""
    sub = cov[np.ix_(idx, idx)]
    iv = 1.0 / np.diag(sub)
    w = iv / iv.sum()
    return float(w @ sub @ w)


def hrp_weights(returns_matrix):
    """Pesos HRP dado un (T x N) de retornos por activo (columnas). Devuelve array de N
    pesos que suman 1. SIN invertir la covarianza -> robusto con activos muy correlacionados."""
    R = np.asarray(returns_matrix, float)
    if R.ndim != 2 or R.shape[1] < 1:
        raise ValueError("returns_matrix debe ser (T x N)")
    n = R.shape[1]
    if n == 1:
        return np.array([1.0])
    cov = np.cov(R, rowvar=False)
    sd = np.sqrt(np.diag(cov))
    corr = cov / np.outer(sd, sd)
    corr = np.clip(corr, -1, 1)
    dist = np.sqrt(np.clip(0.5 * (1 - corr), 0, 1))
    order = _quasi_diag_order(dist)
    w = np.ones(n)
    clusters = [order]
    while clusters:
        nxt = []
        for c in clusters:
            if len(c) <= 1:
                continue
            half = len(c) // 2
            c0, c1 = c[:half], c[half:]
            v0, v1 = _cluster_var(cov, c0), _cluster_var(cov, c1)
            alpha = 1.0 - v0 / (v0 + v1) if (v0 + v1) > 0 else 0.5
            for i in c0:
                w[i] *= alpha
            for i in c1:
                w[i] *= (1.0 - alpha)
            nxt += [c0, c1]
        clusters = nxt
    return w / w.sum()


# ----------------------------- CLI demo -----------------------------
def _demo():
    print("=== sizing — sanity (determinista, sin red) ===")
    # vol-targeting sobre serie con vol cambiante
    t = np.arange(2000)
    r = 0.0003 + (0.005 + 0.004 * np.sin(t * 0.01)) * np.sin(t * 0.5)   # vol que respira
    vt = vol_target_series(r, lookback=30)
    if vt:
        print("vol-target: Sharpe %+.3f -> %+.3f (uplift %+.3f) | vol-of-vol %.2e -> %.2e"
              % (vt["in"]["sharpe"], vt["out"]["sharpe"], vt["sharpe_uplift"],
                 vt["in"]["vol_of_vol"], vt["out"]["vol_of_vol"]))
    # HRP sobre 3 activos: dos muy correlacionados + uno independiente
    base = np.sin(np.arange(1000) * 0.1)
    A = base + 0.05 * np.cos(np.arange(1000) * 0.3)
    B = base + 0.05 * np.cos(np.arange(1000) * 0.31)     # casi igual a A
    C = np.cos(np.arange(1000) * 0.07)                    # independiente
    w = hrp_weights(np.column_stack([A, B, C]))
    print("HRP 3 activos (A≈B correlacionados, C indep): pesos = %s (suman %.3f)"
          % (np.round(w, 3), w.sum()))
    print("  -> C (indep) debería pesar ~como el PAR A+B (diversifica), no 1/3 ciego")
    return 0


def main(argv):
    return _demo()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
