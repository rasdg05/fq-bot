#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  basis_residual — el gemelo TradFi del funding-percentil, para XAU / NQ
  by RasDG_Sol + Claude
================================================================================
NQ/oro en CME son futuros con VENCIMIENTO (dated), no perps -> NO hay funding rate.
Pero la funding de un perp ≈ la BASIS anualizada del dated equivalente: ambos
codifican cost-of-carry + posicionamiento. El análogo directo del edge de funding es
la BASIS del front-month, leída DIRECCIONAL-relativa-a-su-historia (tu percentil 90d).

Ojo measure-first (por qué esto puede NO pasar el gate tan limpio como el funding):
la basis de oro/NQ está ARBITRADA tensa contra la tasa libre de riesgo (r - q), casi
determinística. El raw-basis probablemente NO informa (sigue la tasa). Lo que puede
cargar posicionamiento es el RESIDUAL: basis observada - basis implícita por carry.
Este módulo computa ese residual y lo mapea a dirección con la MISMA semántica de
percentil que `motor_paper.funding_pctl_live` / `_funding_favorable` del bot.

Funciones PURAS (sin red, sin DB) -> testeables. El gate real (DSR/CPCV/PBO) vive en
tools/gate_basis_residual.py y consume estas features; los datos (curva CME) se jalan
de Databento (ver internal/EXPERIMENT_BASIS_RESIDUAL.md). NADA opera sin pasar el gate.

  Uso (librería):  from basis_residual import basis_residual, residual_pctl, directional_signal
  Uso (self-test): python tools/basis_residual.py --self-test
================================================================================
"""
import math

# Umbrales VALIDADOS del funding direccional (idénticos a FUNDING_LONG_PCTL /
# FUNDING_SHORT_PCTL del monolito). El gate puede barrerlos; estos son el punto de partida.
LONG_PCTL = 0.5    # pctl del residual <= 0.5 -> sesgo LONG  (futuro barato vs carry)
SHORT_PCTL = 0.7   # pctl del residual >= 0.7 -> sesgo SHORT (futuro rico = longs crowded)
MIN_HIST = 30      # mínimo de historia para un percentil honesto (== funding_pctl_live)


def basis_residual(front, spot, r_annual, q_annual, tau_years):
    """Residual de carry: la parte de la basis NO explicada por la tasa.

        b_obs   = ln(front / spot) / tau       (log-basis anualizada, observada)
        b_carry = r_annual - q_annual          (cost-of-carry teórico: tasa - yield)
        residual = b_obs - b_carry

    Interpretación (la HIPÓTESIS de dirección; el gate la confirma o la invierte):
      · residual ALTO  -> futuro RICO vs carry -> longs pagando premium -> crowded longs
        -> combustible del SHORT   (igual que funding CALIENTE).
      · residual BAJO/negativo -> futuro BARATO -> shorts crowded / longs baratos
        -> combustible del LONG    (igual que funding FRÍO).

    q_annual absorbe dividend yield (índices) o convenience/lease yield (oro). Defensivo:
    nan si algún input es inválido (jamás lanza). float(nan) es filtrable aguas abajo."""
    try:
        if front is None or spot is None or tau_years is None:
            return float("nan")
        front = float(front); spot = float(spot); tau = float(tau_years)
        if not (front > 0.0 and spot > 0.0 and tau > 0.0):
            return float("nan")
        b_obs = math.log(front / spot) / tau
        b_carry = float(r_annual) - float(q_annual)
        return b_obs - b_carry
    except (TypeError, ValueError):
        return float("nan")


def residual_pctl(hist, min_hist=MIN_HIST):
    """Percentil del ÚLTIMO residual dentro de su propia historia: fracción <= actual.
    MISMA semántica exacta que motor_paper.funding_pctl_live (relativo al venue). Ignora
    nan. Devuelve None si hay menos de `min_hist` puntos válidos (percentil no honesto)."""
    clean = [float(h) for h in hist if h is not None and h == h]  # h==h descarta nan
    if len(clean) < min_hist:
        return None
    cur = clean[-1]
    return sum(1 for h in clean if h <= cur) / len(clean)


def directional_signal(pctl, long_pctl=LONG_PCTL, short_pctl=SHORT_PCTL):
    """Percentil del residual -> dirección, IDÉNTICO a _funding_favorable del bot:
        pctl <= long_pctl  -> +1 (LONG)
        pctl >= short_pctl -> -1 (SHORT)
        en medio / None    ->  0 (neutro -> sin sesgo)."""
    if pctl is None:
        return 0
    if pctl <= long_pctl:
        return 1
    if pctl >= short_pctl:
        return -1
    return 0


def residual_series(fronts, spots, r_annuals, q_annuals, taus):
    """Vectoriza basis_residual sobre secuencias alineadas (una entrada por barra).
    Cualquier barra con input inválido queda como nan (no rompe la serie)."""
    n = len(fronts)
    out = []
    for i in range(n):
        out.append(basis_residual(fronts[i], spots[i], r_annuals[i], q_annuals[i], taus[i]))
    return out


def rolling_signal(residuals, i, n_hist=300, **thr):
    """Señal direccional CAUSAL en la barra i: percentil del residual[i] contra la ventana
    previa [i-n_hist, i] (sólo pasado -> samplable, sin fuga). 0 si historia insuficiente."""
    if i < 0 or i >= len(residuals):
        return 0
    lo = max(0, i - n_hist + 1)
    window = residuals[lo:i + 1]
    return directional_signal(residual_pctl(window), **{k: thr[k] for k in thr})


# ------------------------------------ self-test ------------------------------------
def _self_test():
    # 1) residual = 0 cuando la basis observada == carry teórico
    #    front = spot * exp((r-q)*tau) -> b_obs = r-q -> residual = 0
    r, q, tau = 0.05, 0.01, 0.25
    front_fair = 100.0 * math.exp((r - q) * tau)
    res0 = basis_residual(front_fair, 100.0, r, q, tau)
    assert abs(res0) < 1e-9, "residual debería ser ~0 en carry-fair-value: %r" % res0

    # 2) futuro por ENCIMA del fair -> residual POSITIVO (rico) -> SHORT en el extremo alto
    front_rich = front_fair * 1.01
    assert basis_residual(front_rich, 100.0, r, q, tau) > 0
    # futuro por DEBAJO -> residual NEGATIVO (barato) -> LONG en el extremo bajo
    front_cheap = front_fair * 0.99
    assert basis_residual(front_cheap, 100.0, r, q, tau) < 0

    # 3) percentil: mismo constructo que funding_pctl_live (fracción <= actual)
    hist_hi = list(range(100)) + [1000]        # último es el máximo -> pctl 1.0
    assert residual_pctl(hist_hi) == 1.0
    hist_lo = list(range(100)) + [-1000]       # último es el mínimo -> pctl ~ 1/101
    assert residual_pctl(hist_lo) <= 0.02
    assert residual_pctl([1, 2, 3]) is None    # < MIN_HIST -> None

    # 4) mapeo direccional idéntico a _funding_favorable (long<=0.5, short>=0.7)
    assert directional_signal(0.30) == 1       # residual bajo -> LONG
    assert directional_signal(0.85) == -1      # residual alto -> SHORT
    assert directional_signal(0.60) == 0       # zona neutra
    assert directional_signal(None) == 0       # sin dato -> neutro

    # 5) rolling causal: sólo mira el pasado, insuficiente -> 0
    res = [0.0] * 40 + [5.0]                    # salto al final
    assert rolling_signal(res, len(res) - 1, n_hist=300) == -1   # extremo alto -> SHORT
    assert rolling_signal(res, 5) == 0                            # historia < MIN_HIST -> 0

    # 6) defensivo: inputs basura -> nan, jamás lanza
    for bad in [(None, 1, 0, 0, 1), (1, 0, 0, 0, 1), (1, 1, 0, 0, 0), ("x", 1, 0, 0, 1)]:
        assert math.isnan(basis_residual(*bad))
    print("basis_residual self-test OK")
    return 0


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    print(__doc__)
