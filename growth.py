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

=============================================================================
  DINERO OBLIGATORIO  (V5 — R es adimensional; la cuenta vive en dólares)
=============================================================================
Misma familia, tercer eje. `g` corrigió *qué promedio* se publica; el desglose
corrigió *sobre qué régimen*. Lo que ninguno de los dos toca es **el tamaño del
premio**: un `+0.02R` se lee igual siendo $50/mes que siendo $50.000/mes, y este
repo estuvo cinco meses discutiendo palancas de R sin haber hecho nunca la
multiplicación. Cuando se hizo (2026-08-09), el mejor caso alcanzable sobre la
capacidad MEDIDA por V3 resultó ser **$2.079/año**.

    $/mes = capacidad × f × E[R] × señales/mes

`capacidad` no es "el dinero que uno quiera poner": es el techo al que el
impacto de mercado se come el edge, y sale MEDIDO (`tools/capacity_analysis.py`
con velas locales). Ponerlo a ojo aquí sería repetir el error del default de
catálogo de V3, que estaba 8x por debajo del BTC real — por eso los dos
parámetros se leen del entorno, con su fuente escrita al lado, y viajan dentro
del bloque para que se publiquen junto a la cifra que producen.

`format_expectancy` LEVANTA sin este bloque: que sea imposible enseñar un E[R]
sin ver al lado lo que son en dinero a la capacidad medida.

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

# --- V5: los dos parámetros que convierten R en dólares -------------------
# Ninguno se inventa aquí. Ambos son MEDIDOS y ambos son declarados, con la
# misma disciplina que `Y` en V3 y `queue_frac` en V2: se publican junto a la
# cifra que producen para que nadie cite el dinero sin ver de qué capacidad y
# de qué cadencia salió.
#
#   capacidad  = C0 NETO de ETH (tp4/h288, Y=1, risk 1%) medido por V3 sobre
#                velas locales — el único símbolo del VIP con neto > 0. Es un
#                TECHO del producto entero, no un objetivo de captación.
#   señales/mes= cadencia del universo VIP en el cube (~45), la misma que usa
#                `tools/frontier_report.py` para el volumen de 30 días.
CAPACITY_ENV = "FQ_CAPACITY_USD"
CAPACITY_DEFAULT = 22_000.0
SIGNALS_MONTH_ENV = "FQ_SIGNALS_PER_MONTH"
SIGNALS_MONTH_DEFAULT = 45.0
MONTHS_PER_YEAR = 12.0


class ArithmeticWithoutGrowthError(RuntimeError):
    """Se intentó publicar una expectancy aritmética sin su tasa de crecimiento.

    Hermana de `AggregateWithoutBreakdownError` (E9) y de la misma familia: un
    número exacto que describe algo distinto de lo que el lector cree. El
    agregado escondía el régimen; la media aritmética esconde el camino. Sobre
    la celda que opera hoy (tp1/h288 neto) el E[R] dice −0.069R y la lectura que
    importa es que **el 19% de las trayectorias acaba por encima del capital
    inicial**. Las dos salen del mismo dato; solo una se entiende.
    """


class RWithoutMoneyError(RuntimeError):
    """Se intentó publicar una afirmación de edge sin su cifra en dólares.

    Hermana de `AggregateWithoutBreakdownError` (E9) y de
    `ArithmeticWithoutGrowthError` (V4), y de la misma familia: un número
    exacto que el lector interpreta como algo que no es. El agregado escondía
    el régimen; la media aritmética escondía el camino; **R esconde el tamaño
    del premio**.

    La factura: cinco meses de palancas discutidas en R (comisiones, terciles,
    geometría, salida) sin que nadie multiplicara. Hecha la multiplicación, el
    mejor caso alcanzable sobre la capacidad MEDIDA son ~$2.079/año — o sea que
    la conversación entera cabía por debajo del coste de tenerla. Un `+0.02R`
    no puede volver a salir sin que se vea al lado que son ~$50/mes.
    """


def _env_float(key, default, env=None):
    src = os.environ if env is None else env
    try:
        return float(src.get(key, default))
    except (TypeError, ValueError):
        return default


def configured_risk_frac(env=None):
    """La `f` que arriesga la cuenta viva, de una sola fuente de verdad."""
    return _env_float(RISK_FRAC_ENV, RISK_FRAC_DEFAULT, env)


def configured_capacity_usd(env=None):
    """La capacidad MEDIDA sobre la que se traduce R a dólares (V3)."""
    return _env_float(CAPACITY_ENV, CAPACITY_DEFAULT, env)


def configured_signals_per_month(env=None):
    """La cadencia medida del universo que se publica."""
    return _env_float(SIGNALS_MONTH_ENV, SIGNALS_MONTH_DEFAULT, env)


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


def money_stats(mean_r, *, capital=None, risk_frac=None, signals_per_month=None,
                n=None, capital_source=None):
    """Lo que un E[R] vale en DINERO a la capacidad medida.

        $/trade = capacidad · f · E[R]
        $/mes   = $/trade · señales/mes
        APY     = $/año / capacidad

    Es aritmética de una línea, y ésa es exactamente la razón por la que nadie
    la hizo durante cinco meses: parecía obvia y por eso no parecía trabajo. El
    resultado no lo era — la capacidad manda ~20x más que el edge sobre el
    premio final, así que el orden en el que se atacan las palancas cambia
    entero al ver esta cifra.

    Devuelve None solo si `mean_r` no es un número: en todo lo demás la
    respuesta existe, incluso (sobre todo) cuando es ridícula.
    """
    try:
        mu = float(mean_r)
    except (TypeError, ValueError):
        return None
    if mu != mu or abs(mu) == float("inf"):
        return None
    cap = configured_capacity_usd() if capital is None else float(capital)
    f = configured_risk_frac() if risk_frac is None else float(risk_frac)
    spm = (configured_signals_per_month() if signals_per_month is None
           else float(signals_per_month))
    riesgo = cap * f
    por_trade = riesgo * mu
    por_mes = por_trade * spm
    por_ano = por_mes * MONTHS_PER_YEAR
    return {
        "n": n,
        "mean_r": mu,
        "capital": cap,
        "capital_source": capital_source or ("env:%s" % CAPACITY_ENV
                                             if os.environ.get(CAPACITY_ENV)
                                             else "V3 medido (C0 neto ETH)"),
        "risk_frac": f,
        "signals_per_month": spm,
        "risk_usd": riesgo,
        "usd_per_trade": por_trade,
        "usd_per_month": por_mes,
        "usd_per_year": por_ano,
        "apy": (por_ano / cap) if cap else float("nan"),
    }


def require_money(stats, *, what="afirmación de edge"):
    """Guardia: ninguna cifra de edge sale sin su traducción a dinero.

    Espejo exacto de `ledger_stats.format_expectancy` para el desglose y de
    `is_overbet` para la fracción: no prohíbe el número, obliga a que viaje con
    lo que significa. Que la respuesta sea deprimente no es motivo para
    omitirla — es el motivo por el que existe.
    """
    if not isinstance(stats, dict) or not stats.get("money"):
        raise RWithoutMoneyError(
            "%s sin bloque de dinero: R es adimensional y esconde el tamaño "
            "del premio. Adjunta money_stats(E[R]) — a la capacidad MEDIDA, no "
            "a la que a uno le gustaría tener." % what)
    return stats


def format_money(m, *, indent="  "):
    """Render del bloque de dinero. Va pegado al E[R], nunca aparte."""
    if not m:
        return "%s(sin cifra en dólares: nadie hizo la multiplicación)" % indent
    L = ["%sEn DINERO a la capacidad medida ($%s, %s)"
         % (indent, _miles(m["capital"]), m["capital_source"])]
    L.append("%s  $%s/mes  ·  $%s/año  ·  APY %.1f%%"
             % (indent, _miles(m["usd_per_month"]), _miles(m["usd_per_year"]),
                m["apy"] * 100))
    L.append("%s  = capacidad x f %.2f%% x E[R] %+.4f x %.0f señales/mes"
             % (indent, m["risk_frac"] * 100, m["mean_r"],
                m["signals_per_month"]))
    return "\n".join(L)


def _miles(x):
    """'1234567.8' -> '1.234.568'. Sin locale: el render no depende del host."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "?"
    signo = "-" if v < 0 else ""
    entero = "{:,.0f}".format(abs(v)).replace(",", ".")
    return signo + entero


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
