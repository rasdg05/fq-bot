# -*- coding: utf-8 -*-
"""
=============================================================================
  GROWTH — la media aritmética no es lo que le pasa a la cuenta
=============================================================================

Todo lo que este repo publica está en E[R] **aritmética**: expectancy, IC95%,
DSR. Eso describe el promedio del *ensemble* — lo que ganarías si pudieras vivir
las 13.429 señales en universos paralelos y promediarlos. Una cuenta no vive eso:
vive **una** trayectoria, y compone. Las dos cosas no coinciden, y la diferencia
tiene signo.

Con `f` = fracción de capital arriesgada por trade, el capital se multiplica por
`1 + f·R` en cada operación, así que lo que crece la cuenta es

    g = E[ln(1 + f·R)]  ≈  f·μ − f²·σ²/2

El segundo término es el **arrastre de volatilidad**. No son comisiones ni
slippage: es geometría. Y decide dos cosas que la media aritmética no ve:

1. **Existe una `f` óptima** (`f* ≈ μ/σ²`, Kelly). Por debajo creces despacio;
   por encima creces MENOS, y pasado `2·f*` creces NEGATIVO aunque μ sea
   positivo. Apostar de más no se parece a apostar de menos: no es simétrico.
2. **La mediana y la media divergen.** Medido sobre el propio cube (VIP tp4/h288
   neto, n=3.774): μ = +0.0099R con σ = 2.19R y skew +1.96. A f=1% la media del
   capital tras 200 trades es **x1.02** y la **mediana x0.97** — el promedio sube
   y el camino típico baja. La media la levanta una cola delgada de trayectorias
   que no vas a vivir tú.

Por qué el repo era ciego a esto
--------------------------------
Es estructural, no descuido. `cube_report.apply_costs` lo dice en su docstring:
*"la R neta por trade sale invariante al capital (esto mide expectancy, no una
curva)"*. Correcto para medir señal — y significa que **ninguna métrica del repo
cambia si arriesgas 0.25% o 5%**. El sistema de medición entero es invariante a
`f`, o sea incapaz por construcción de detectar sobre-apuesta.

Lo que este módulo NO hace
--------------------------
No crea edge. Si μ ≤ 0 ninguna `f` lo arregla: `f*` sale ~0 y lo único que el
sizing elige es a qué velocidad se pierde. Esto es disciplina de riesgo, no de
alfa — convierte un edge en crecimiento, no la falta de edge en edge.

Stdlib puro a propósito: lo consume `ledger_stats` (producción) además de
`tools/` (research), y la superficie de publicación no debe crecer dependencias.
=============================================================================
"""
import math
import os

# Horizonte por defecto de P(acabar arriba). ~48 señales/mes en el VIP (3
# símbolos x ~16), así que 200 trades son unos cuatro meses: el plazo en el que
# un suscriptor decide si sigue pagando.
DEFAULT_HORIZON = 200

# Por debajo de esto la varianza está peor estimada que la media y `f*` es
# ruido. Mismo criterio que el resto del repo.
GROWTH_MIN_N = 30

# Fracción de Kelly recomendada. Kelly pleno maximiza el crecimiento asintótico
# y es intolerable en el camino (drawdowns del 50% son rutina) — y además `f*`
# se estima con error, así que apuntar al pico es apuntar a pasarse. La mitad es
# el estándar: ~75% del crecimiento con la mitad de la volatilidad.
KELLY_SAFETY = 0.5

# El riesgo por trade que gobierna la cuenta viva. Se lee del MISMO sitio que
# `execution.GovernorConfig.max_risk_frac`: que este módulo pudiera juzgar una
# `f` distinta de la que opera es exactamente la forma de no enterarse.
RISK_FRAC_ENV = "FQ_MAX_RISK_FRAC"
RISK_FRAC_DEFAULT = 0.0025


class ArithmeticWithoutGrowthError(RuntimeError):
    """Se intentó publicar una expectancy aritmética sin su tasa de crecimiento.

    Hermana de `AggregateWithoutBreakdownError` (E9) y de la misma familia: un
    número exacto que describe algo distinto de lo que el lector cree. El
    agregado escondía el régimen; la media aritmética esconde el camino. Sobre
    la celda que opera hoy (tp1/h288 neto) el E[R] dice −0.069R y la lectura que
    importa es que **el 19% de las trayectorias acaba por encima del capital
    inicial**. Las dos salen del mismo dato; solo una se entiende.
    """


def configured_risk_frac(env=None):
    """La `f` que arriesga la cuenta viva, de una sola fuente de verdad."""
    src = os.environ if env is None else env
    try:
        return float(src.get(RISK_FRAC_ENV, RISK_FRAC_DEFAULT))
    except (TypeError, ValueError):
        return RISK_FRAC_DEFAULT


def _clean(rs):
    # `if rs` no vale: aqui entran ndarrays y Series ademas de listas, y su
    # verdad es ambigua. Explicito contra None y a iterar.
    if rs is None:
        return []
    out = []
    for x in rs:
        try:
            v = float(x)
        except (TypeError, ValueError):
            continue
        if v == v and abs(v) != float("inf"):
            out.append(v)
    return out


def _moments(rs):
    n = len(rs)
    mu = sum(rs) / n
    var = sum((x - mu) ** 2 for x in rs) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    skew = 0.0
    if sd > 0 and n > 2:
        skew = sum(((x - mu) / sd) ** 3 for x in rs) / n
    return mu, sd, skew


def _median(rs):
    s = sorted(rs)
    n = len(s)
    if not n:
        return float("nan")
    m = n // 2
    return s[m] if n % 2 else (s[m - 1] + s[m]) / 2.0


def growth_rate(rs, f):
    """`g = E[ln(1 + f·R)]` — lo que la cuenta crece por trade, en log.

    Devuelve None si alguna R ruina la cuenta a esa `f` (`1 + f·R <= 0`): no es
    "crecimiento muy negativo", es que esa fracción no es apostable. Distinguirlo
    importa — un promedio finito sobre una ruina la esconde.
    """
    rs = _clean(rs)
    if len(rs) < 2:
        return None
    tot = 0.0
    for x in rs:
        m = 1.0 + f * x
        if m <= 0.0:
            return None
        tot += math.log(m)
    return tot / len(rs)


def kelly_fraction(rs, *, fmax=0.5, steps=2000):
    """`f*` que maximiza `g`, por búsqueda directa sobre la distribución REAL.

    No usa la forma cerrada `μ/σ²` porque esa supone retornos pequeños y
    simétricos, y esta distribución no lo es (skew ~+2, mediana −1.18R con media
    +0.01R). La forma cerrada se devuelve aparte como referencia: cuando las dos
    difieren mucho, la que miente es la cerrada.
    """
    rs = _clean(rs)
    if len(rs) < 2:
        return None
    mejor_f, mejor_g = 0.0, 0.0          # f=0 -> g=0: no apostar es el suelo
    for i in range(1, steps + 1):
        f = fmax * i / steps
        g = growth_rate(rs, f)
        if g is not None and g > mejor_g:
            mejor_f, mejor_g = f, g
    return {"f_star": mejor_f, "g_star": mejor_g}


def prob_above_start(g, sigma_log, horizon=DEFAULT_HORIZON):
    """P(la cuenta acabe por encima del capital inicial tras `horizon` trades).

    Normal sobre el log-capital acumulado (CLT). Con skew positivo la real es
    algo PEOR que ésta —la cola gorda está arriba, no abajo, así que la masa se
    corre hacia el lado malo de la mediana—: medido, 46.6% analítico contra 45.4%
    simulado. O sea que esta cifra es **optimista**, y se publica sabiéndolo.
    """
    if sigma_log is None or sigma_log <= 0 or g is None:
        return None
    z = g * math.sqrt(horizon) / sigma_log
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def growth_stats(rs, f=None, *, horizon=DEFAULT_HORIZON, safety=KELLY_SAFETY):
    """El bloque completo: media aritmética, `g`, `f*` y P(acabar arriba).

    `f=None` -> la fracción que gobierna la cuenta viva (`configured_risk_frac`).
    """
    rs = _clean(rs)
    n = len(rs)
    if n < 2:
        return None
    f = configured_risk_frac() if f is None else float(f)
    mu, sd, skew = _moments(rs)
    g = growth_rate(rs, f)
    k = kelly_fraction(rs) or {"f_star": 0.0, "g_star": 0.0}
    # sigma del log-multiplicador a la f evaluada (no de R): es la que gobierna
    # la dispersion de la TRAYECTORIA, que es lo que se esta describiendo.
    logs = [math.log(1.0 + f * x) for x in rs] if g is not None else []
    sigma_log = math.sqrt(sum((y - g) ** 2 for y in logs) / (len(logs) - 1)) \
        if len(logs) > 1 else None
    f_star = k["f_star"]
    return {
        "n": n,
        "thin": n < GROWTH_MIN_N,
        "risk_frac": f,
        "mean_r": mu,                  # lo que el repo publica hoy
        "median_r": _median(rs),       # lo que le pasa al trade tipico
        "sigma_r": sd,
        "skew_r": skew,
        "g": g,                        # crecimiento por trade (log)
        "g_star": k["g_star"],
        "f_star": f_star,
        "f_star_closed": (mu / (sd * sd)) if sd > 0 else None,
        "overbet": (f / f_star) if f_star > 0 else (float("inf") if f > 0 else 0.0),
        "horizon": horizon,
        "median_x": math.exp(g * horizon) if g is not None else 0.0,
        "mean_x": (1.0 + f * mu) ** horizon,
        "p_up": prob_above_start(g, sigma_log, horizon),
        "recommended_risk_frac": f_star * safety,
        "safety": safety,
    }


def is_overbet(stats, *, tol=1.0):
    """¿La `f` que opera está por encima de la que maximiza el crecimiento?

    `tol=1.0` compara contra `f*` pleno. Pasado `2·f*` el crecimiento es negativo
    aunque μ sea positivo, así que ahí ya no es "subóptimo": es destructivo.
    """
    if not stats or stats.get("f_star") is None:
        return False
    fs = stats["f_star"]
    return fs <= 0 or stats["risk_frac"] > tol * fs


def format_growth(stats, *, indent="  "):
    """Render del bloque de crecimiento. `ledger_stats.format_expectancy` lo
    pega al lado de la media aritmética para que no se pueda leer una sin la
    otra."""
    if not stats:
        return "%s(sin muestra para estimar crecimiento)" % indent
    g, p = stats["g"], stats["p_up"]
    L = ["%sCrecimiento a risk %.2f%%/trade  (lo que la media aritmetica no dice)"
         % (indent, stats["risk_frac"] * 100)]
    if g is None:
        L.append("%s  RUINA: a esa fraccion una sola perdida borra la cuenta."
                 % indent)
        return "\n".join(L)
    L.append("%s  g = %+.6f por trade  ->  mediana x%.2f en %d trades%s"
             % (indent, g, stats["median_x"], stats["horizon"],
                "   (media x%.2f)" % stats["mean_x"]))
    if p is not None:
        L.append("%s  P(acabar por encima del capital inicial) = %.1f%%"
                 % (indent, p * 100))
    L.append("%s  f* = %.2f%%  ->  recomendado %.2f%% (%.0f%% de Kelly)"
             % (indent, stats["f_star"] * 100,
                stats["recommended_risk_frac"] * 100, stats["safety"] * 100))
    if stats["f_star"] <= 0:
        L.append("%s  >> f* = 0: la apuesta optima es NO apostar. Ninguna"
                 % indent)
        L.append("%s     fraccion positiva hace crecer esta distribucion."
                 % indent)
    elif is_overbet(stats):
        L.append("%s  >> SOBRE-APUESTA %.1fx sobre f*. Apostar de mas NO es"
                 % (indent, stats["overbet"]))
        L.append("%s     simetrico a apostar de menos: pasado 2xf* el" % indent)
        L.append("%s     crecimiento es NEGATIVO aunque la media sea positiva."
                 % indent)
    if stats["thin"]:
        L.append("%s  <- n=%d < %d: la varianza esta peor estimada que la media,"
                 % (indent, stats["n"], GROWTH_MIN_N))
        L.append("%s     asi que f* aqui es orientativo, no una recomendacion."
                 % indent)
    return "\n".join(L)
