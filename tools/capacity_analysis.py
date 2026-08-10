# -*- coding: utf-8 -*-
"""
================================================================================
  CAPACIDAD — un edge no se defiende con secreto, se defiende con capacidad
================================================================================

¿A qué tamaño se muere esto? Es lo primero que pregunta cualquiera que sepa, y
separa una estrategia de una anécdota. El edge se mide en R por-trade sobre
etiquetas que no saben cuánto capital hay detrás; al crecer el capital cada orden
pesa más sobre el libro → más impacto → cada R rinde menos. Este tool barre el
capital y dibuja la curva, marcando:
  - C½  : capital donde el edge cae a la MITAD.
  - C0  : capital donde el edge se anula (techo absoluto).

Modelo (ley raíz — el estándar de market impact):
  notional   = capital * risk_frac / stop_frac          (tamaño de posición)
  liquidez   = avg_bar_notional * fill_bars              (se reparte la orden)
  q          = notional / liquidez                       (participación)
  slip_bps   = impact_coef * q**impact_exp               (impact_exp=0.5)
  slip_R     = 2 * (slip_bps/1e4) / stop_frac            (entrada+salida)
  edge(C)    = mean_R - slip_R

V3 (2026-08-05) — lo que este tool NO tenía y por qué importaba
---------------------------------------------------------------
Escrito en N8.4, su propio docstring pedía "CALIBRARLOS con volumen real". Nadie
lo hizo, y el default `avg_bar_notional=3e6` resultó estar **8 veces por debajo**
del volumen real de BTC (2.56e7 USD por barra de 5m, medido). Un tool cuya
respuesta depende de dos parámetros inventados no contesta la pregunta: la
decora. Ahora:

1. **La liquidez se MIDE de las velas locales** (`measure_liquidity`): notional
   mediano por barra y volatilidad por barra, del propio símbolo y de la misma
   ventana temporal que las señales. Deja de ser un supuesto.
2. **El coeficiente de impacto se DERIVA de esa volatilidad**, no se inventa:
   la ley raíz es `impacto = Y · σ_ventana · sqrt(q)`, así que
   `impact_coef = Y · σ_barra · sqrt(fill_bars)`. Lo único declarado que queda es
   **Y** (adimensional, ~0.5–1.5 en la literatura) — y por eso se publica la
   CURVA sobre un rango de Y, nunca un punto. Mismo trato que `queue_frac` en V2.
3. **`fill_bars` deja de mover la respuesta.** Antes σ era por barra y la
   liquidez por ventana: el resultado escalaba con `sqrt(fill_bars)`, y elegir 24
   en vez de 1 multiplicaba la capacidad por 24 sin que nada lo delatara (medido:
   C0 pasaba de $12k a $282k). Con σ escalado a la misma ventana que el volumen,
   la ley raíz es **invariante** a esa elección — como debe ser, porque es un
   detalle de ejecución, no una propiedad del mercado. `test_capacity_analysis`
   lo fija.

La invariante que sale de aquí
------------------------------
`require_measured()` levanta ante una capacidad calculada con liquidez supuesta o
sobre una serie BRUTA. Es la misma enfermedad de julio —un supuesto viajando sin
etiqueta— y la misma cura que V2 le puso al fill maker: la cifra se puede
calcular, pero no puede salir por la puerta sin decir de dónde salió.

V5 (2026-08-10) — ¿el techo es del SISTEMA o de la GEOMETRÍA?
------------------------------------------------------------
V3 midió la capacidad sobre `tp4/h288`, la celda de stop más APRETADO (0.45–0.63%
del precio), que es la que el bot opera por accidente histórico. Despejando el
capital de la ley que este mismo módulo implementa:

    slip_R = 2·coef·(C·f/(sf·V))^½ / (1e4·sf)   →   C = B²·1e8·sf³·V / (4·coef²·f)

o sea **capacidad ∝ stop_frac³**: doblar el stop da 8x de capacidad y la celda
ancha del cementerio (kSL=5) daría 125x. Eso es una DERIVACIÓN. `--ancha` la
MIDE: toma la serie de R de la celda ancha con la salida dinámica puesta
(`geometry_sweep.relabel_exits`, pre-fijadas las dos por el cementerio) y barre
el capital sobre la rejilla pre-registrada en
`internal/BRIEF_CAPACIDAD_ANCHA_2026-08.md`.

Y la invariante que sale de V5 no es de capacidad, es de LECTURA: ninguna cifra
de edge se imprime aquí sin su traducción a dólares al lado
(`growth.money_stats`). R esconde el tamaño del premio.

Uso:
  python tools/capacity_analysis.py --vip            # V3: capacidad de tp4/h288
  python tools/capacity_analysis.py --ancha          # V5: la celda ANCHA
  python tools/capacity_analysis.py --cube cosecha_cubes/tp_cube_SOL_USDT.parquet \
      --tp tp4 --label-horizon 288 --avg-bar-notional 3e6 --out-png cap_SOL.png
================================================================================
"""
import argparse
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))           # raiz del repo
sys.path.insert(0, _HERE)                            # tools/

# Rango de Y de la literatura de impacto raíz. No es un intervalo de confianza:
# es el abanico de lo que otros midieron en otros mercados. Por eso se publica
# entero y lo que se cita es el umbral, no el punto.
Y_GRID = (0.5, 1.0, 1.5)
Y_REF = 1.0

# Tamaños de cuenta que la conversación de RasDG usa de verdad.
CAPITALES_REALES = (10e3, 50e3, 100e3, 500e3, 1e6)

MIN_BARS = 500          # por debajo de esto la mediana de volumen no describe nada
BAR_MINUTES = 5.0
MIN_N = 30

# --------------------------------------------------------------------------
#  V5 — PRE-REGISTRADO en internal/BRIEF_CAPACIDAD_ANCHA_2026-08.md
# --------------------------------------------------------------------------
# Nada de esto se busca. La geometría viene del CEMENTERIO (2026-08-04) y la
# salida de la medición del 2026-08-08: las dos con fecha y con resultado
# publicado ANTES de este experimento. Lo único que se barre es el capital.
CELDA_ANCHA = (5.0, 6.0, 1152)
SALIDA_ANCHA = ("A trail k=0.50", {"kind": "trail", "k": 0.50, "arm": 1.0})

# El eje único, declarado entero. ESTO es el n_trials.
CAPITAL_GRID = (22e3, 100e3, 250e3, 500e3, 1e6, 2e6)
N_TRIALS_V5 = len(CAPITAL_GRID)
# Divulgación paranoica obligatoria: 84 geometrías x 6 reglas de salida x 6
# capitales. No es el criterio; es la cota. Que se vea.
N_TRIALS_V5_PARANOICO = 84 * 6 * N_TRIALS_V5

# Los umbrales de las hipótesis, fijados antes de mirar.
#
# CORRECCIÓN ESCRITA DE LA PRE-REGISTRACIÓN (2026-08-10, obligatoria por §0 del
# brief: "se cambia por escrito y contando de nuevo, no en silencio").
# El brief escribe H1 como ">= $220k", que son 10x el $22k de V3. Pero ese $22k
# está medido a `risk_frac = 1%` (el default de `--vip`), y la cuenta viva
# arriesga 0.25%. La capacidad va como `1/f`, así que el MISMO sistema mide
# $88k a la `f` viva: el umbral absoluto no es una propiedad del sistema, es una
# propiedad de la convención con la que se escribió.
#
# Peor: correr el impacto a una `f` y juzgar la cartera a otra es exactamente lo
# que `growth.configured_risk_frac` (V4) existe para impedir — una sola `f`.
#
# Así que el experimento corre entero a la `f` VIVA y H1 se evalúa por su
# RATIO, que es lo que la hipótesis dice de verdad ("la capacidad de la celda
# ancha es >=10x la de tp4/h288"). El ratio es invariante a `f`; el absoluto no.
# `n_trials` NO cambia: sigue siendo 6, el eje sigue siendo uno.
H1_RATIO = 10.0
V3_RISK_FRAC = 0.01                             # la convención en que se publicó $22k
V3_TECHO_NETO_USD = 22e3
H1_UMBRAL_USD = H1_RATIO * V3_TECHO_NETO_USD    # >= $220k, en convención V3
H2_CAPITAL_USD = 250e3

# Presupuesto de impacto con el que el brief derivó la tabla de stop_frac³.
IMPACT_BUDGET_R = 0.02

# Símbolos del pool con cube cosechado. Por debajo de esto, cualquier resultado
# es una afirmación de SUBCONJUNTO (puerta 3 del brief).
POOL_SIMBOLOS = 13


class CapacityAssumedError(RuntimeError):
    """Se intentó publicar una capacidad que no describe nada medible.

    Dos formas de la misma enfermedad:

    - **Liquidez supuesta.** El default de este tool (3e6 USD/barra) resultó
      estar 8x por debajo del BTC real. Una capacidad calculada así no es una
      estimación conservadora: es un número inventado con unidades de dinero.
    - **Serie bruta.** La capacidad de un edge bruto es el techo de un sistema
      que no existe — el coste fijo ya se comió ese edge antes de que el tamaño
      entrara en la ecuación. Se puede calcular (dice cuánto aguantaría una
      ejecución perfecta), pero no puede salir sin la etiqueta TECHO.

    Espejo de `bt_engine.MakerFillAssumedError` (V2) y de
    `cube_report.GrossWithoutNetError` (E8).
    """


class Liquidity(object):
    """Lo que hace falta saber del mercado para preguntar por capacidad.

    `source` es el campo que decide si esto se puede publicar: sale de un
    parquet de velas o dice "supuesto". No hay tercera opción, y `require_measured`
    la comprueba.
    """

    __slots__ = ("symbol", "bar_notional", "sigma_bar", "stop_frac", "n_bars",
                 "desde", "hasta", "source")

    def __init__(self, symbol, bar_notional, sigma_bar, stop_frac, *,
                 n_bars=0, desde=None, hasta=None, source="supuesto"):
        self.symbol = symbol
        self.bar_notional = float(bar_notional)
        self.sigma_bar = float(sigma_bar)
        self.stop_frac = float(stop_frac)
        self.n_bars = int(n_bars)
        self.desde = desde
        self.hasta = hasta
        self.source = source

    @property
    def measured(self):
        return not str(self.source).startswith("supuesto")

    def impact_coef(self, y=Y_REF, fill_bars=1):
        """bps de impacto a participación q=1, derivados de la σ MEDIDA.

        `sqrt(fill_bars)` escala σ a la misma ventana que el volumen. Es lo que
        vuelve la curva invariante a `fill_bars`: repartir la orden en más barras
        divide la participación pero multiplica la volatilidad de la ventana por
        el mismo factor bajo la raíz. Sin ese término, elegir la ventana era
        elegir la respuesta.
        """
        return float(y) * self.sigma_bar * float(np.sqrt(max(fill_bars, 1e-12))) * 1e4

    def __repr__(self):
        return ("Liquidity(%s, %.3e USD/barra, sigma %.1f bps, stop %.2f%%, %s)"
                % (self.symbol, self.bar_notional, self.sigma_bar * 1e4,
                   self.stop_frac * 100, self.source))


def assumed_liquidity(symbol="?", bar_notional=3e6, sigma_bar=0.002,
                      stop_frac=0.012):
    """La liquidez de antes de V3: parámetros de catálogo. Marcada como tal."""
    return Liquidity(symbol, bar_notional, sigma_bar, stop_frac,
                     source="supuesto (parámetros de catálogo, sin velas)")


def measure_liquidity(klines_dir, symbol, *, stop_frac, desde=None, hasta=None,
                      min_bars=MIN_BARS):
    """Liquidez y volatilidad REALES del símbolo, de las velas locales.

    `desde`/`hasta` acotan a la ventana en la que hay señales: medir el volumen
    de BTC sobre 2019-2026 cuando las señales viven en 2021-2026 mezcla dos
    mercados distintos (el notional por barra de SOL creció ~100x en ese tramo).

    Mediana, no media: el volumen por barra tiene la cola derecha gordísima
    (media/mediana ≈ 2 en los tres símbolos VIP) y la media describe el día del
    crash, no la barra en la que se opera.
    """
    import pandas as pd

    path = _klines_path(klines_dir, symbol)
    if not os.path.exists(path):
        raise FileNotFoundError(
            "no hay velas locales para %s en %s. Bájalas con "
            "tools/fetch_binance_vision_klines.py — sin ellas la capacidad "
            "sale de parámetros inventados y no se puede publicar." % (symbol, path))
    k = pd.read_parquet(path, columns=["ts", "close", "volume"])
    k["dt"] = pd.to_datetime(k["ts"], unit="ms")
    if desde is not None:
        k = k[k["dt"] >= pd.to_datetime(desde)]
    if hasta is not None:
        k = k[k["dt"] <= pd.to_datetime(hasta)]
    if len(k) < min_bars:
        raise ValueError("solo %d barras de %s en la ventana: la mediana de "
                         "volumen no describe nada (mínimo %d)"
                         % (len(k), symbol, min_bars))
    notional = float((k["volume"] * k["close"]).median())
    sigma = float(np.log(k["close"].astype(float)).diff().std())
    return Liquidity(symbol, notional, sigma, stop_frac, n_bars=len(k),
                     desde=k["dt"].min(), hasta=k["dt"].max(),
                     source="velas:%s" % os.path.basename(path))


def _klines_path(klines_dir, symbol):
    """'BTC' / 'BTC_USDT' / 'BTCUSDT' -> <dir>/kl_hist_BTCUSDT.parquet."""
    s = str(symbol).upper().replace("/", "_").replace("_", "")
    if not s.endswith("USDT"):
        s += "USDT"
    return os.path.join(klines_dir, "kl_hist_%s.parquet" % s)


def require_measured(rep, *, allow_ceiling=False):
    """Guardia de publicación: nadie cita una capacidad sin decir de dónde sale.

    `allow_ceiling=True` es la puerta explícita para el bruto — la misma forma
    que `maker_expectancy(..., allow_assumed=True)` en V2: no prohíbe la cifra,
    obliga a nombrarla TECHO al pedirla.
    """
    if not isinstance(rep, dict) or "liquidez" not in rep:
        raise CapacityAssumedError(
            "esto no pasó por capacity_curve() con una Liquidity: una capacidad "
            "sin procedencia de liquidez no describe ningún mercado")
    liq = rep["liquidez"]
    if not liq.get("measured"):
        raise CapacityAssumedError(
            "capacidad calculada con liquidez %r. El default de catálogo estaba "
            "8x por debajo del BTC real: mide con velas locales "
            "(measure_liquidity) antes de publicar." % liq.get("source"))
    if rep.get("basis") != "neto" and not allow_ceiling:
        raise CapacityAssumedError(
            "capacidad sobre serie %r: el coste fijo se come el edge antes de "
            "que el tamaño importe, así que esto es un TECHO de ejecución "
            "perfecta. Pídelo con allow_ceiling=True y publícalo con esa "
            "etiqueta." % rep.get("basis"))
    return rep


def capacity_curve(r_series, *, capitals=None, risk_frac=0.01, stop_frac=0.012,
                   avg_bar_notional=3e6, fill_bars=24, impact_coef=45.0,
                   impact_exp=0.5, liquidity=None, y_impact=Y_REF, basis=None):
    """Curva de expectancy degradada vs capital + los puntos C½ y C0.

    r_series        : R por-trade (R-múltiplos, sin coste de impacto).
    capitals        : grilla de capital (USD). Default: log 1e3..1e8.
    risk_frac       : fracción de capital arriesgada por trade.
    stop_frac       : distancia del stop como fracción del precio.
    avg_bar_notional: notional (USD) negociado por barra (liquidez base).
    fill_bars       : barras en que se reparte la orden (ventana de fill).
    impact_coef     : slippage en bps a participación q=1 (a calibrar).
    impact_exp      : exponente del impacto (0.5 = raíz, el estándar).
    liquidity       : `Liquidity` MEDIDA. Si viene, manda sobre los tres
                      parámetros de arriba y `impact_coef` se deriva de su σ.
    y_impact        : Y de la ley raíz (adimensional). Lo único declarado.
    basis           : "neto" | "bruto" — qué serie es. `require_measured` lo mira.
    """
    rs = np.asarray([x for x in r_series if x is not None and np.isfinite(x)],
                    dtype=float)
    if rs.size < 2:
        raise ValueError("serie de R insuficiente (n<2)")
    mean_R = float(rs.mean())
    if liquidity is not None:
        stop_frac = liquidity.stop_frac
        avg_bar_notional = liquidity.bar_notional
        impact_coef = liquidity.impact_coef(y_impact, fill_bars)
    else:
        liquidity = assumed_liquidity(bar_notional=avg_bar_notional,
                                      stop_frac=stop_frac)
    if capitals is None:
        capitals = np.logspace(3, 8, 60)          # 1k .. 100M
    capitals = np.asarray(capitals, dtype=float)
    liq = avg_bar_notional * fill_bars
    notional = capitals * risk_frac / stop_frac
    q = notional / liq
    slip_bps = impact_coef * np.power(q, impact_exp)
    slip_R = 2.0 * (slip_bps / 1e4) / stop_frac
    edge = mean_R - slip_R

    def _cross(target):
        """Menor capital donde edge(C) <= target (interp lineal). None si nunca."""
        below = np.where(edge <= target)[0]
        if below.size == 0:
            return None
        i = below[0]
        if i == 0:
            return float(capitals[0])
        x0, x1 = capitals[i - 1], capitals[i]
        y0, y1 = edge[i - 1], edge[i]
        if y1 == y0:
            return float(x1)
        return float(x0 + (target - y0) * (x1 - x0) / (y1 - y0))

    ch, cz = _cross(mean_R * 0.5), _cross(0.0)
    return {
        "n_trades": int(rs.size),
        "mean_R_gross": mean_R,
        "basis": basis,
        # El cruce en el primer punto de la rejilla NO es "capacidad de $1k": es
        # "por debajo de lo que esta rejilla mide". Imprimirlo como cifra deja
        # leer un número donde lo que hay es un suelo.
        "grid_floor": {"half": bool(ch is not None and ch <= capitals[0]),
                       "zero": bool(cz is not None and cz <= capitals[0])},
        "y_impact": float(y_impact),
        "liquidez": {"symbol": liquidity.symbol, "source": liquidity.source,
                     "measured": liquidity.measured,
                     "bar_notional": liquidity.bar_notional,
                     "sigma_bar": liquidity.sigma_bar,
                     "n_bars": liquidity.n_bars},
        "params": {"risk_frac": risk_frac, "stop_frac": stop_frac,
                   "avg_bar_notional": avg_bar_notional, "fill_bars": fill_bars,
                   "impact_coef": impact_coef, "impact_exp": impact_exp},
        "capital_half": ch,                       # C½
        "capital_zero": cz,                       # C0
        "curve": {"capital": capitals.tolist(),
                  "participation": q.tolist(),
                  "slip_bps": slip_bps.tolist(),
                  "edge_r": edge.tolist()},
    }


def impact_at(capital, liquidity, *, risk_frac=0.01, y_impact=Y_REF,
              fill_bars=1, impact_exp=0.5):
    """Lo que un tamaño concreto cuesta: participación, bps y R de impacto.

    La curva contesta "¿dónde se muere?"; esto contesta "¿y a MI tamaño, cuánto
    me cuesta?", que es la pregunta que se responde antes de mandar el dinero.
    """
    notional = float(capital) * risk_frac / liquidity.stop_frac
    q = notional / (liquidity.bar_notional * max(fill_bars, 1e-12))
    slip_bps = liquidity.impact_coef(y_impact, fill_bars) * q ** impact_exp
    return {"capital": float(capital), "notional": notional, "q": float(q),
            "slip_bps": float(slip_bps),
            "slip_r": float(2.0 * (slip_bps / 1e4) / liquidity.stop_frac)}


def capital_where_impact_equals(cost_r, liquidity, *, risk_frac=0.01,
                                y_impact=Y_REF, fill_bars=1, impact_exp=0.5):
    """Capital al que el impacto (que ESCALA con el tamaño) iguala un coste fijo.

    Es la frontera entre dos regímenes, y decide qué palanca sirve. Por debajo,
    el tamaño es de segundo orden y lo que manda es el coste fijo por trade
    (fees + slippage de catálogo): crecer no empeora nada apreciable, y encoger
    tampoco arregla nada. Por encima, el impacto manda y la capacidad es el
    límite real.

    Este repo llevaba meses hablando de capacidad sin saber de qué lado estaba.
    """
    if cost_r <= 0:
        return None
    # slip_R(C) = 2·coef·(C·rf/(sf·V·N))^e /1e4/sf = cost_r  ->  despejar C.
    coef = liquidity.impact_coef(y_impact, fill_bars)
    sf, v = liquidity.stop_frac, liquidity.bar_notional * max(fill_bars, 1e-12)
    lhs = cost_r * sf * 1e4 / (2.0 * coef)          # = q**impact_exp
    if lhs <= 0:
        return None
    q = lhs ** (1.0 / impact_exp)
    return float(q * v * sf / risk_frac)


# --------------------------------------------------------------------------
#  V3 — la capacidad del producto que se publica (VIP), con velas locales
# --------------------------------------------------------------------------

def _fmt_usd(x, floor=False):
    if x is None:
        return "n/a"
    p = "<" if floor else ""
    if x >= 1e6:
        return "%s$%.1fM" % (p, x / 1e6)
    return "%s$%.0fk" % (p, x / 1e3)


def _c(rep, key):
    """C½/C0 formateado, marcando cuando cae en el suelo de la rejilla."""
    return _fmt_usd(rep[key], rep["grid_floor"]["half" if "half" in key else "zero"])


def symbol_liquidity(trades, klines_dir, *, symbol_col="symbol"):
    """Una `Liquidity` medida por símbolo, acotada a la ventana de sus señales.

    El `stop_frac` sale del propio cube (|entrada − stop| / entrada, mediano),
    no de un default: es lo que convierte bps de impacto en R, así que ponerlo a
    ojo desplaza toda la curva. Medido, el stop del motor está en 0.45–0.63% del
    precio — bastante más apretado que el 1.2% que este tool asumía, y eso
    AMPLIFICA el impacto en R (el mismo bps se divide por un stop menor).
    """
    out = {}
    for sym, g in trades.groupby(symbol_col):
        sf = float((np.abs(g["entry_price"] - g["stop_price"])
                    / g["entry_price"]).median())
        out[sym] = measure_liquidity(
            klines_dir, sym, stop_frac=sf,
            desde=g["entry_ts"].min(), hasta=g["entry_ts"].max())
    return out


def vip_capacity(cube_dir="cosecha_cubes/", klines_dir="data/binance", *,
                 tp="tp4", horizon=288, universe=None, y_grid=Y_GRID,
                 risk_frac=0.01, fill_bars=1, capitals=CAPITALES_REALES):
    """La curva de capacidad del universo que el bot difunde, símbolo a símbolo.

    Nunca un agregado: la capacidad de una cartera de tres símbolos no es la
    suma ni la media de las tres — el impacto se paga en el libro de CADA uno, y
    el que primero se satura marca el techo. Además E9 manda desglosar, y aquí
    el desglose es lo único que se puede accionar (la liquidez de SOL y la de
    BTC se llevan un orden de magnitud).
    """
    from cube_report import load_pool
    from vip_report import cell_trades, vip_universe

    u = universe if universe is not None else vip_universe()
    trades = cell_trades(load_pool(cube_dir), tp, horizon, symbols=u)
    if trades.empty:
        raise SystemExit("celda %s/h%d vacía sobre %s" % (tp, horizon, sorted(u)))
    liqs = symbol_liquidity(trades, klines_dir)

    filas = []
    for sym, g in sorted(trades.groupby("symbol")):
        liq = liqs[sym]
        bruto, neto = float(g["pnl_r"].mean()), float(g["net_r"].mean())
        curvas = {}
        for base, serie in (("bruto", g["pnl_r"]), ("neto", g["net_r"])):
            for y in y_grid:
                curvas[(base, y)] = capacity_curve(
                    serie, liquidity=liq, y_impact=y, fill_bars=fill_bars,
                    risk_frac=risk_frac, basis=base)
        filas.append({
            "symbol": sym, "n": len(g), "liq": liq, "bruto": bruto, "neto": neto,
            "coste_fijo": bruto - neto, "curvas": curvas,
            "impactos": [impact_at(c, liq, risk_frac=risk_frac, y_impact=Y_REF,
                                   fill_bars=fill_bars) for c in capitals],
            "c_coste_fijo": capital_where_impact_equals(
                bruto - neto, liq, risk_frac=risk_frac, y_impact=Y_REF,
                fill_bars=fill_bars),
            "trades": g,
        })
    return {"tp": tp, "horizon": horizon, "universo": sorted(u), "filas": filas,
            "risk_frac": risk_frac, "y_grid": tuple(y_grid),
            "capitales": tuple(capitals), "fill_bars": fill_bars}


def print_vip_capacity(rep):
    f = rep["filas"]
    print("=" * 78)
    print("  CAPACIDAD DEL VIP — %s · celda %s/h%d · risk %.2f%% por trade"
          % ("/".join(rep["universo"]), rep["tp"], rep["horizon"],
             rep["risk_frac"] * 100))
    print("=" * 78)

    print("\n=== 1) LA LIQUIDEZ, MEDIDA (no supuesta) ===")
    print("  %-11s %7s %14s %10s %9s  %s"
          % ("símbolo", "barras", "USD/barra 5m", "σ/barra", "stop med", "fuente"))
    for r in f:
        q = r["liq"]
        print("  %-11s %7d %14.3e %8.1fbps %8.2f%%  %s"
              % (r["symbol"], q.n_bars, q.bar_notional, q.sigma_bar * 1e4,
                 q.stop_frac * 100, q.source))
    print("  (mediana, no media: la cola derecha del volumen es gordísima y la")
    print("   media describe el día del crash, no la barra en la que se opera)")

    print("\n=== 2) LA CURVA — C½ y C0 por símbolo y por Y ===")
    print("  Y es el único parámetro declarado (ley raíz, ~0.5–1.5 en la")
    print("  literatura). Por eso va la curva entera y no un punto.")
    print("\n  %-11s %6s %26s %26s"
          % ("", "", "BRUTO (techo de ejecución)", "NETO (lo que hay hoy)"))
    print("  %-11s %6s %8s %8s %8s %8s %8s %8s"
          % ("símbolo", "Y", "edge", "C½", "C0", "edge", "C½", "C0"))
    for r in f:
        for y in rep["y_grid"]:
            b, n = r["curvas"][("bruto", y)], r["curvas"][("neto", y)]
            print("  %-11s %6.1f %+8.4f %8s %8s %+8.4f %8s %8s"
                  % (r["symbol"] if y == rep["y_grid"][0] else "", y,
                     b["mean_R_gross"], _c(b, "capital_half"),
                     _c(b, "capital_zero"), n["mean_R_gross"],
                     _c(n, "capital_half"), _c(n, "capital_zero")))

    print("\n=== 3) A LOS TAMAÑOS DE LA CONVERSACIÓN REAL (Y=%.1f) ===" % Y_REF)
    print("  Cuánto pesa la orden sobre una barra de 5m, y qué cuesta en R.")
    for r in f:
        print("  -- %s (coste FIJO ya aplicado: %.3fR por trade) --"
              % (r["symbol"], r["coste_fijo"]))
        print("     %9s %12s %9s %9s %11s"
              % ("capital", "notional/pos", "q(barra)", "impacto", "edge neto"))
        for imp in r["impactos"]:
            print("     %9s %12s %8.2f%% %7.1fbps %+10.4f"
                  % (_fmt_usd(imp["capital"]), _fmt_usd(imp["notional"]),
                     imp["q"] * 100, imp["slip_bps"], r["neto"] - imp["slip_r"]))

    print("\n=== 4) LA FRONTERA: ¿manda el tamaño o manda el coste fijo? ===")
    print("  Capital al que el impacto (escala con el tamaño) iguala al coste")
    print("  fijo por trade (fees+slippage de catálogo, NO escala).")
    for r in f:
        print("     %-11s coste fijo %.3fR  ->  el impacto lo iguala en %s"
              % (r["symbol"], r["coste_fijo"], _fmt_usd(r["c_coste_fijo"])))
    return rep


def print_capacity_por_ano(rep, klines_dir="data/binance"):
    """E9 sobre la capacidad: la liquidez de 2021 y la de 2026 no son la misma.

    Citar una capacidad de siete años promediados es el mismo error que citar
    una expectancy agregada. El notional por barra de SOL creció ~100x en el
    tramo del cube: una capacidad pooled describe un mercado que ya no existe.
    """
    import pandas as pd

    print("\n=== 5) POR AÑO — la capacidad de hace cinco años no es la de hoy ===")
    for r in rep["filas"]:
        g = r["trades"].copy()
        g["ano"] = pd.to_datetime(g["entry_ts"]).dt.year
        print("  -- %s --" % r["symbol"])
        print("     %6s %6s %14s %9s %9s %10s %10s"
              % ("año", "n", "USD/barra", "σ/barra", "bruto", "C½ bruto",
                 "C0 bruto"))
        for ano, gg in g.groupby("ano"):
            sf = float((np.abs(gg["entry_price"] - gg["stop_price"])
                        / gg["entry_price"]).median())
            try:
                liq = measure_liquidity(
                    klines_dir, r["symbol"], stop_frac=sf,
                    desde=pd.Timestamp(year=int(ano), month=1, day=1),
                    hasta=pd.Timestamp(year=int(ano), month=12, day=31,
                                       hour=23, minute=59))
            except (ValueError, FileNotFoundError):
                continue
            if len(gg) < 2:
                continue
            c = capacity_curve(gg["pnl_r"], liquidity=liq, y_impact=Y_REF,
                               fill_bars=rep["fill_bars"],
                               risk_frac=rep["risk_frac"], basis="bruto")
            flaco = "  <- n<30" if len(gg) < 30 else ""
            if c["mean_R_gross"] <= 0:
                flaco = "  <- bruto<=0: no hay capacidad que medir" + flaco
            print("     %6d %6d %14.3e %8.1fbps %+9.4f %10s %10s%s"
                  % (ano, len(gg), liq.bar_notional, liq.sigma_bar * 1e4,
                     c["mean_R_gross"], _c(c, "capital_half"),
                     _c(c, "capital_zero"), flaco))


def veredicto_capacidad(rep):
    """Lo que la curva significa para el producto, dicho sin adornos."""
    f = rep["filas"]
    print("\n" + "-" * 78)
    netos_vivos = [r for r in f if r["neto"] > 0]
    techo_neto = min(
        (r["curvas"][("neto", Y_REF)]["capital_zero"] for r in netos_vivos
         if r["curvas"][("neto", Y_REF)]["capital_zero"]), default=None)
    techo_bruto = min(
        (r["curvas"][("bruto", Y_REF)]["capital_zero"] for r in f
         if r["curvas"][("bruto", Y_REF)]["capital_zero"]), default=None)

    print("  >> DOS REGÍMENES, y la frontera entre ellos está MEDIDA:")
    for r in f:
        print("     %-11s coste fijo %.3fR · el impacto lo iguala en %s"
              % (r["symbol"], r["coste_fijo"], _fmt_usd(r["c_coste_fijo"])))
    print("     Por DEBAJO manda el coste fijo (fees + slippage de catálogo, no")
    print("     escala con el tamaño): encoger la cuenta no arregla nada. Por")
    print("     ENCIMA manda el impacto y la capacidad es el límite real. La")
    print("     conversación de RasDG ($10k–$500k) cruza esa frontera en SOL")
    print("     ($106k) y roza la de ETH ($434k): no es un rango donde el tamaño")
    print("     sea gratis, y hasta hoy nadie sabía de qué lado estaba.")

    if not netos_vivos:
        print("\n  >> Y la capacidad del edge NETO es CERO, por una razón que no")
        print("     es de liquidez: no hay edge neto que escalar. Ningún símbolo")
        print("     del universo tiene el neto por encima de cero en esta celda,")
        print("     así que C0 cae en el suelo de la rejilla para todos.")
    else:
        print("\n  >> Capacidad del edge NETO (el único que se puede cobrar):")
        for r in f:
            c = r["curvas"][("neto", Y_REF)]
            if r["neto"] <= 0:
                print("     %-11s neto %+.4fR -> no hay nada que escalar (el"
                      " capital solo empeora)" % (r["symbol"], r["neto"]))
                continue
            print("     %-11s neto %+.4fR -> C½ %s · C0 %s"
                  % (r["symbol"], r["neto"], _c(c, "capital_half"),
                     _c(c, "capital_zero")))
        piso = any(r["curvas"][("neto", Y_REF)]["grid_floor"]["zero"]
                   for r in netos_vivos)
        print("     Techo del conjunto = el símbolo que primero se satura: %s%s."
              % (_fmt_usd(techo_neto, piso),
                 " (en el suelo de la rejilla: el edge es tan fino que no hay "
                 "capital que lo aguante)" if piso else ""))
        print("     OJO: V1 midió que ninguna de estas celdas tiene el IC95% del")
        print("     neto entero sobre cero. Una capacidad sobre un edge que no")
        print("     está demostrado es una cota, no una promesa.")

    print("\n  >> TECHO de ejecución perfecta (serie BRUTA, sin coste alguno):")
    print("     %s — el símbolo que primero se satura marca el conjunto. Es lo"
          % _fmt_usd(techo_bruto))
    print("     que la LIQUIDEZ aguantaría si la ejecución fuera gratis. No es")
    print("     capital desplegable: es la distancia entre el problema que este")
    print("     repo tiene (ejecución) y el que NO tiene (tamaño).")

    print("\n  >> POR QUÉ la capacidad sale tan baja, que no es lo que parece:")
    print("     no es falta de libro — BTC mueve 2.6e7 USD por barra de 5m. Es")
    print("     que el stop del motor es APRETADO (0.45–0.63% del precio) y el")
    print("     impacto entra en R dividido por esa distancia: los mismos 7 bps")
    print("     valen 0.03R con un stop del 5% y 0.22R con uno del 0.63%. El")
    print("     repo ya midió (2026-06-30) que el stop apretado ES el edge")
    print("     (Q1 +0.316R vs Q4 +0.147R). Las dos cosas son la misma: lo que")
    print("     hace rentable a la señal es lo que la hace frágil al tamaño.")

    print("\n  >> La lectura de negocio, que era la pregunta de V3:")
    print("     esto es un SERVICIO DE SEÑALES, no un vehículo de capital. La")
    print("     escala a la que el impacto empieza a doler está en las decenas")
    print("     de miles, no en los millones, y llega ANTES de que el edge neto")
    print("     esté demostrado. La conversación de capital real tiene ya su")
    print("     cifra detrás: es de cinco dígitos, no de seis.")
    return {"techo_neto": techo_neto, "techo_bruto": techo_bruto}


def run_vip(cube_dir="cosecha_cubes/", klines_dir="data/binance", **kw):
    rep = vip_capacity(cube_dir, klines_dir, **kw)
    print_vip_capacity(rep)
    print_capacity_por_ano(rep, klines_dir)
    rep["veredicto"] = veredicto_capacidad(rep)
    return rep


# --------------------------------------------------------------------------
#  V5 — la capacidad de la geometría ANCHA (¿$22k o millones?)
# --------------------------------------------------------------------------

def with_stop_frac(liq, stop_frac):
    """La misma liquidez MEDIDA, otra geometría.

    La liquidez y la volatilidad son del MERCADO; el stop es de la ESTRATEGIA.
    Que `Liquidity` los llevara juntos es lo que hizo que V3 midiera la
    capacidad de la geometría más apretada creyendo que medía la del sistema.
    Separarlos aquí es todo el experimento: `source` viaja intacto, así que
    `require_measured` sigue viendo unas velas detrás.
    """
    return Liquidity(liq.symbol, liq.bar_notional, liq.sigma_bar, stop_frac,
                     n_bars=liq.n_bars, desde=liq.desde, hasta=liq.hasta,
                     source=liq.source)


def ancha_trades(cube_dir="cosecha_cubes/", klines_dir="data/binance", *,
                 celda=CELDA_ANCHA, salida=SALIDA_ANCHA, universe=None,
                 tp="tp4", horizon=288, cost=None, bar_minutes=BAR_MINUTES):
    """La serie de R de la celda ANCHA, con la salida dinámica ya aplicada.

    Reusa `geometry_sweep.relabel_exits` — la misma función que produjo el
    veredicto del 2026-08-08 — en vez de re-etiquetar aquí. Si alguien toca la
    convención intra-vela en un sitio, esto la hereda; una segunda
    implementación sería una segunda convención sin querer.

    Las señales son las MISMAS que las de tp4/h288 (el cube canónico): lo que
    cambia son las barreras y el cierre, nunca la entrada. Por eso `n` es
    comparable con todo lo publicado.
    """
    import pandas as pd

    from bt_engine import CostModel
    from cube_report import cell_events, load_pool
    from fill_quality import (align, load_klines, recompute_excursion,
                              validate_venue)
    from geometry_sweep import net_r_vectorized, relabel_exits
    from vip_report import base_ccy, vip_universe

    u = universe if universe is not None else vip_universe()
    ev_all = cell_events(load_pool(cube_dir), tp=tp, horizon=horizon)
    ev_all = ev_all[ev_all["symbol"].map(lambda s: base_ccy(s) in u)]
    if ev_all.empty:
        raise SystemExit("celda %s/h%d vacía sobre %s" % (tp, horizon, sorted(u)))

    trozos = []
    for sym, ev in ev_all.groupby("symbol"):
        kl = load_klines(klines_dir, sym)
        if kl is None or kl.empty:
            print("  [venue] %-10s sin velas locales -> fuera" % sym)
            continue
        ev = ev.reset_index(drop=True)
        pos = align(ev, kl)
        mfe_l, mae_l = recompute_excursion(ev, kl, pos, horizon)
        ok, rep = validate_venue(ev, mfe_l, mae_l)
        print("  [venue] %-10s %5d/%5d alineadas  corr MFE %.3f  %s"
              % (sym, rep.get("n_alineadas", 0), rep["n_total"],
                 rep.get("corr_mfe", float("nan")), "OK" if ok else "RECHAZADO"))
        if not ok:
            continue
        trozos.append(relabel_exits(ev, kl, pos, sym, celda=celda,
                                    exit_rules=(salida,)))
    if not trozos:
        raise SystemExit("ningún símbolo pasó el gate de venue: sin medición")

    t = pd.concat(trozos, ignore_index=True)
    t["net_r_sin_impacto"] = net_r_vectorized(
        t.direction, t.entry_price, t.exit_price, t.stop_price, t.bars_held,
        t.outcome, cost or CostModel(), bar_minutes)
    t["net_r"] = t["net_r_sin_impacto"]
    t["t0"] = pd.to_datetime(t["entry_ts"])
    t["t1"] = t["t0"] + pd.to_timedelta(
        t["bars_held"].astype(float) * bar_minutes, unit="m")
    return t.dropna(subset=["net_r_sin_impacto"]).reset_index(drop=True)


def _senales_mes(trades):
    """Cadencia MEDIDA del set, para que el dinero no salga de una cadencia
    inventada. Misma cuenta que `frontier_report.monthly_volume_usd`."""
    import pandas as pd
    ts = pd.to_datetime(trades["entry_ts"])
    meses = max((ts.max() - ts.min()).total_seconds() / 86400.0 / 30.44, 1e-9)
    return len(trades) / meses


def capital_sweep(trades, liqs, *, capitals=CAPITAL_GRID, risk_frac=None,
                  y_impact=Y_REF, fill_bars=1, senales_mes=None):
    """El eje único: qué le pasa al neto cuando el capital sube.

    El impacto se resta POR SÍMBOLO (cada libro se paga aparte, E9) y después
    se agrupa: un impacto promediado sobre tres libros de tamaño distinto no
    describe ninguna cuenta.

    Cada fila lleva su propia vara (`-IC_lo`), su cartera (`screen_cell`, sin
    cap), su bloque de crecimiento y **su cifra en dólares**. Sin ninguna de
    las cuatro no se publica.

    UNA SOLA `f`. `screen_cell` se evalúa a la MISMA fracción con la que se
    calculó el impacto, no sobre su rejilla de cuatro. Dejarle buscar la más
    tímida devolvía filas marcadas "cartera ok" cuyo DD salía de una `f` a la
    que el impacto de esa misma fila no corresponde — la enfermedad exacta que
    `growth.configured_risk_frac` (V4) cabló para que no volviera.
    """
    import growth
    from validation_gate import _sharpe, deflated_from_trials
    from vip_report import require_screened, screen_cell

    if risk_frac is None:
        risk_frac = growth.configured_risk_frac()
    if senales_mes is None:
        senales_mes = _senales_mes(trades)

    series = {}
    for c in capitals:
        t = trades.copy()
        slip = {s: impact_at(c, liq, risk_frac=risk_frac, y_impact=y_impact,
                             fill_bars=fill_bars)["slip_r"]
                for s, liq in liqs.items()}
        t["slip_r"] = t["symbol"].map(slip)
        t["net_r"] = t["net_r_sin_impacto"] - t["slip_r"]
        series[c] = t

    sharpes = {c: _sharpe(t["net_r"].to_numpy(float)) for c, t in series.items()}
    sharpe_std = float(np.std(list(sharpes.values()), ddof=1))
    filas = []
    for c in capitals:
        t = series[c]
        x = t["net_r"].to_numpy(float)
        lo, hi, _p = _boot(x)
        s = require_screened(screen_cell(t, label="$%.0fk" % (c / 1e3),
                                         risk_fracs=(risk_frac,)))
        m = growth.money_stats(float(x.mean()), capital=c, risk_frac=risk_frac,
                               signals_per_month=senales_mes, n=len(x),
                               capital_source="rejilla V5")
        filas.append({
            "capital": c, "n": len(x), "neto": float(x.mean()),
            "lo": lo, "hi": hi,
            "brecha": -lo,                       # la vara de SU n
            "slip_r": {s_: float(v) for s_, v in
                       t.groupby("symbol")["slip_r"].first().items()},
            "screen": s, "money": m,
            "dsr": deflated_from_trials(x, list(sharpes.values()))["dsr"],
            "dsr_paranoico": deflated_from_trials(
                x, list(sharpes.values()) * (84 * 6))["dsr"],
            "trades": t, "sharpe_std": sharpe_std,
        })
    return filas


def _boot(x, reps=2000, seed=7):
    """Espejo de `geometry_sweep._boot` / `cube_report._boot_ci`: misma semilla,
    mismas repeticiones, para que las cifras de los tres informes se comparen."""
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    m = np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(reps)])
    return (float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)),
            float((m > 0).mean()))


def ley_stop_frac(liq, *, k_mults=(1.0, 2.0, 5.0, 8.0), budget_r=IMPACT_BUDGET_R,
                  risk_frac=V3_RISK_FRAC, y_impact=Y_REF, fill_bars=1):
    """La DERIVACIÓN del brief, re-derivada aquí con la liquidez medida.

    Devuelve, por multiplicador de stop, el capital al que el impacto iguala
    `budget_r`. La ley es exacta y el test la fija: `C ∝ stop_frac³`, así que
    la columna `vs 1x` debe salir k³ hasta el error de coma flotante. Que salga
    exactamente k³ NO es una confirmación de nada empírico — es aritmética, y
    por eso la tabla se imprime marcada como derivación (puerta 1 del brief:
    reescalar stop y objetivo es invariante; lo único que puede mover el neto
    es que la resolución por barreras cambie de FORMA).
    """
    base = None
    filas = []
    for k in k_mults:
        lq = with_stop_frac(liq, liq.stop_frac * k)
        c = capital_where_impact_equals(budget_r, lq, risk_frac=risk_frac,
                                        y_impact=y_impact, fill_bars=fill_bars)
        base = c if base is None else base
        filas.append({"k": k, "stop_frac": lq.stop_frac, "capital": c,
                      "vs_1x": (c / base) if base else float("nan")})
    return filas


def print_ancha(rep):
    import growth

    liq_t, liq_a = rep["liq_apretada"], rep["liq_ancha"]
    print("\n" + "=" * 78)
    print("  V5 — LA CAPACIDAD DE LA GEOMETRÍA ANCHA")
    print("  celda PRE-FIJADA kSL=%.1f tpR=%.1f h=%d · salida %s"
          % (rep["celda"] + (rep["salida"],)))
    print("=" * 78)
    print("  n_trials = %d (los capitales; la geometría y la salida NO se"
          % N_TRIALS_V5)
    print("  buscan: vienen del cementerio con fecha). Divulgación paranoica")
    print("  obligatoria al lado: %d = 84 geometrías x 6 salidas x 6 capitales."
          % N_TRIALS_V5_PARANOICO)
    print("  risk_frac = %.2f%% — la `f` VIVA, la MISMA para el impacto y para"
          % (rep["risk_frac"] * 100))
    print("  la cartera (V4: una sola `f`). El $22k de V3 está publicado a")
    print("  f=%.2f%%, así que H1 se evalúa por RATIO, no por el absoluto."
          % (V3_RISK_FRAC * 100))

    print("\n=== 1) LA GEOMETRÍA, MEDIDA — no supuesta ===")
    print("  %-11s %10s %10s %8s %14s" % ("símbolo", "stop tp4", "stop ancho",
                                          "ratio", "USD/barra 5m"))
    for s in sorted(liq_a):
        print("  %-11s %9.2f%% %9.2f%% %8.2f %14.3e"
              % (s, liq_t[s].stop_frac * 100, liq_a[s].stop_frac * 100,
                 liq_a[s].stop_frac / liq_t[s].stop_frac, liq_a[s].bar_notional))
    print("  El stop ancho sale de las MISMAS señales re-etiquetadas (kSL=5),")
    print("  no de multiplicar el mediano por 5: la mediana de un producto no")
    print("  es el producto de las medianas y la diferencia entra al cubo.")

    print("\n=== 2) LA LEY, RE-DERIVADA CON LA LIQUIDEZ MEDIDA (no es medición) ===")
    print("  Capital al que el impacto iguala %.2fR, por multiplicador de stop."
          % IMPACT_BUDGET_R)
    for s in sorted(rep["ley"]):
        print("  -- %s --" % s)
        print("     %6s %10s %14s %8s" % ("kSL", "stop", "capital", "vs 1x"))
        for f in rep["ley"][s]:
            print("     %6.1f %9.2f%% %14s %7.1fx"
                  % (f["k"], f["stop_frac"] * 100, _fmt_usd(f["capital"]),
                     f["vs_1x"]))
    print("  El `vs 1x` es k³ EXACTO por construcción (C ∝ stop_frac³) — es")
    print("  aritmética de la ley, no evidencia. Lo que decide es la tabla 3.")

    print("\n=== 3) EL BARRIDO DE CAPITAL — el eje único pre-registrado ===")
    print("  El impacto se resta por símbolo y luego se agrupa. `brecha` es")
    print("  -IC_lo sobre la n de la fila; negativa = ya cruzó.")
    print("\n  %10s %6s %9s %20s %9s %8s %8s %9s %12s"
          % ("capital", "n", "NETO", "IC95% neto", "brecha", "DSR", "DSRp",
             "DD@f", "$/año"))
    for f in rep["filas"]:
        # `intentos` trae exactamente una fila: la `f` con la que se calculó el
        # impacto de esta misma fila. Una sola `f` (V4).
        viva = f["screen"]["intentos"][0] if f["screen"]["intentos"] else None
        print("  %10s %6d %+9.4f [%+8.4f,%+8.4f] %+9.4f %8.3f %8.3f %8s %12s%s"
              % (_fmt_usd(f["capital"]), f["n"], f["neto"], f["lo"], f["hi"],
                 f["brecha"], f["dsr"], f["dsr_paranoico"],
                 "%.1f%%" % (-viva["max_drawdown"] * 100) if viva else "  ---",
                 "$" + growth._miles(f["money"]["usd_per_year"]),
                 "" if f["screen"]["candidato"] else "   no"))

    print("\n  -- el impacto por símbolo, en R (lo que el tamaño cuesta) --")
    print("  %10s %s" % ("capital", "  ".join("%-11s" % s
                                              for s in sorted(liq_a))))
    for f in rep["filas"]:
        print("  %10s %s" % (_fmt_usd(f["capital"]),
                             "  ".join("%-11.4f" % f["slip_r"].get(s, float("nan"))
                                       for s in sorted(liq_a))))

    print("\n=== 4) LA CAPACIDAD NETA POR SÍMBOLO (comparable con el $22k de V3) ===")
    print("  %-11s %6s %9s %10s %10s   %s"
          % ("símbolo", "Y", "neto", "C½", "C0", "fuente de liquidez"))
    for s in sorted(rep["curvas"]):
        for y in rep["y_grid"]:
            c = rep["curvas"][s][y]
            print("  %-11s %6.1f %+9.4f %10s %10s   %s"
                  % (s if y == rep["y_grid"][0] else "", y, c["mean_R_gross"],
                     _c(c, "capital_half"), _c(c, "capital_zero"),
                     c["liquidez"]["source"] if y == rep["y_grid"][0] else ""))
    print("  Y se publica como CURVA (0.5–1.5): es lo único declarado que queda")
    print("  en la ley de impacto. Mismo trato que `queue_frac` en V2.")
    return rep


def veredicto_ancha(rep):
    """Las tres hipótesis, contestadas con el criterio fijado ANTES de mirar."""
    import growth

    filas = rep["filas"]
    ratios = rep["ratios_h1"]
    evaluables = [r for r in ratios if r["evaluable"]]
    # H1 por RATIO y símbolo a símbolo: es lo que la hipótesis dice, y lo único
    # invariante a `f`. Sin ningún símbolo evaluable, H1 NO se declara cumplida:
    # no saber no es pasar (misma regla que `require_reachable`, que falla
    # cerrado).
    h1 = bool(evaluables) and all(r["ratio"] >= H1_RATIO for r in evaluables)
    umbral = H1_RATIO * (min(r["c0_v3"] for r in evaluables) if evaluables
                         else V3_TECHO_NETO_USD * rep["risk_frac"] / V3_RISK_FRAC)
    f250 = min(filas, key=lambda f: abs(f["capital"] - H2_CAPITAL_USD))
    h2 = f250["neto"] > 0
    h3 = [f for f in filas
          if f["capital"] >= umbral and f["neto"] > 0
          and f["screen"]["candidato"] and f["dsr"] > 0.95]

    print("\n" + "-" * 78)
    print("  VEREDICTO — criterio pre-registrado (H3 exige las tres a la vez)")
    print("  H1  capacidad ancha >= %.0fx la de tp4/h288 .. %s"
          % (H1_RATIO, "SI" if h1 else "NO"))
    print("      Símbolo a símbolo (el brief prohíbe elegirlo), C0 NETO a Y=%.1f"
          % Y_REF)
    print("      y a la MISMA `f` (%.2f%%) en las dos celdas:"
          % (rep["risk_frac"] * 100))
    print("      %-11s %10s %10s %10s %10s %8s"
          % ("símbolo", "neto tp4", "C0 tp4", "neto ancha", "C0 ancha", "ratio"))
    for r in ratios:
        print("      %-11s %+10.4f %10s %+10.4f %10s %8s"
              % (r["symbol"], r["neto_v3"], _fmt_usd(r["c0_v3"]),
                 r["neto_ancha"], _fmt_usd(r["c0_ancha"]),
                 "%.0fx" % r["ratio"] if r["evaluable"]
                 else "n/e"))
    if len(evaluables) < len(ratios):
        print("      n/e = no evaluable: el neto de alguna de las dos celdas es")
        print("      ~0, y su C0 cae en el SUELO de la rejilla. Un ratio contra")
        print("      un suelo sale en cinco cifras y no describe capacidad.")
    print("  H2  neto > 0 con impacto a $%s ......... %s  (medido: %+.4fR)"
          % (growth._miles(f250["capital"]), "SI" if h2 else "NO", f250["neto"]))
    if h2 and f250["brecha"] > 0:
        print("      PERO su IC95%% [%+.4f, %+.4f] cruza cero: el punto es"
              % (f250["lo"], f250["hi"]))
        print("      positivo y el signo NO está determinado. H2 pasa por la")
        print("      LETRA ('sigue siendo positivo') y no por el fondo. Leerla")
        print("      como un sí es el error que mató a mayo.")
    print("  H3  las tres a la vez ...................... %s"
          % ("SI" if h3 else "NO"))
    print("      capital a capital (>= $%s):" % growth._miles(umbral))
    for f in filas:
        if f["capital"] < umbral:
            continue
        fallos = []
        if f["neto"] <= 0:
            fallos.append("neto %+.4f <= 0" % f["neto"])
        if not f["screen"]["candidato"]:
            fallos.append(f["screen"]["motivos"][0] if f["screen"]["motivos"]
                          else "cartera")
        if f["dsr"] <= 0.95:
            fallos.append("DSR %.3f <= 0.95" % f["dsr"])
        print("        %-10s %s" % (_fmt_usd(f["capital"]),
                                    " · ".join(fallos) or "PASA"))

    # El aviso que impide leer la columna DSR como un aprobado. Es la puerta 7
    # ("una métrica demasiado limpia es un bug") aplicada al propio gate.
    print("\n  >> EL DSR DE ESTA TABLA NO ES UN GATE, Y HAY QUE DECIRLO.")
    print("     Los 6 capitales no son 6 estrategias: son la MISMA serie con")
    print("     una constante restada, monótona en el capital. Sus Sharpes")
    print("     casi no se separan (std %.4f), y `deflated_from_trials`"
          % rep["sharpe_std"])
    print("     deflacta con esa dispersión -> el eje se auto-deflacta a ~nada")
    print("     y la columna sale en 1.000 por construcción, no por evidencia.")
    print("     El multiple-testing REAL de esta celda ocurrió aguas arriba (84")
    print("     geometrías x 6 salidas) y es justo lo que cuenta la cota")
    print("     paranoica. Las cifras con las que juzgar esta celda siguen")
    print("     siendo las publicadas: DSR 0.432 con n_trials=1 (cementerio")
    print("     2026-08-04) y 0.366 / 0.607 al contar los trials de verdad.")

    # Puerta 3 del brief: el confundido del subconjunto. Se cerró el
    # 2026-08-10 midiendo el pool entero, así que aquí ya no se avisa "esto no
    # se sabe" — se dice CUÁNTO cuesta mirar solo un subconjunto.
    n_sym = len(rep["universo"])
    if n_sym < POOL_SIMBOLOS:
        print("\n  " + "!" * 70)
        print("  PUERTA 3 — esto corre sobre %d símbolos, no sobre los %d del"
              % (n_sym, POOL_SIMBOLOS))
        print("  pool. NO es una incógnita: el 2026-08-10 se midió la misma")
        print("  celda y la misma salida sobre los 13, y el subconjunto MIENTE")
        print("  en la dirección optimista — el neto casi se dobla (+0.0950 vs")
        print("  +0.0501) y el drawdown se TERCIA (11.1% vs 34.2% a f viva).")
        print("  Cualquier cifra de riesgo de esta tabla es la del subconjunto.")
        print("  Corre `--ancha --pool` para verla sobre el universo entero.")
        print("  " + "!" * 70)

    # Puerta 6 del brief: máximo en la esquina.
    mejor = max(filas, key=lambda f: f["neto"])
    if mejor["capital"] == filas[-1]["capital"] and len(filas) > 2:
        print("\n  >> MÁXIMO EN LA ESQUINA: el mejor capital es el último de la")
        print("     rejilla. El rango se acabó y no hay óptimo demostrado.")

    # Puerta 2: capacidad sin edge no es buena noticia.
    if h1 and not h2:
        print("\n  >> H1 SIN H2. Hay capacidad y el edge muere al tamaño: la")
        print("     capacidad nunca fue el cuello de botella. Capacidad grande")
        print("     sin edge demostrado solo significa perder más rápido y en")
        print("     mayor cantidad.")

    # Puerta 4: el DSR ya se cayó una vez.
    fragiles = [f for f in filas if f["dsr"] > 0.95 and f["dsr_paranoico"] <= 0.95]
    if fragiles:
        print("\n  >> DSR FRÁGIL (el error que el brief prohíbe repetir): estas")
        print("     filas clarean a n_trials=%d y se caen a la cota paranoica"
              % N_TRIALS_V5)
        print("     de %d, que es la que cuenta la rejilla entera:"
              % N_TRIALS_V5_PARANOICO)
        for f in fragiles:
            print("        %-10s DSR %.3f -> %.3f"
                  % (_fmt_usd(f["capital"]), f["dsr"], f["dsr_paranoico"]))

    print("\n  -- LA CIFRA EN DÓLARES, que es la pregunta de negocio --")
    # El premio NO es monótono en el capital: $ = C·f·E[R]·cadencia y E[R] cae
    # como sqrt(C), así que hay un ÓPTIMO INTERIOR. Es la única cifra de esta
    # corrida que contesta "¿cuánto puede dar esto, como mucho?".
    mejor_usd = max(filas, key=lambda f: f["money"]["usd_per_year"])
    print("     Máximo del premio sobre la rejilla: %s de capital"
          % _fmt_usd(mejor_usd["capital"]))
    print(growth.format_money(mejor_usd["money"], indent="     "))
    dd = (mejor_usd["screen"]["intentos"][0]["max_drawdown"]
          if mejor_usd["screen"]["intentos"] else float("nan"))
    print("     Y lo que cuesta cobrarlo: DD %.1f%% a la `f` viva, IC95%%"
          % (-dd * 100))
    print("     [%+.4f, %+.4f] %s."
          % (mejor_usd["lo"], mejor_usd["hi"],
             "ENTERO sobre cero" if mejor_usd["brecha"] <= 0 else "CRUZANDO cero"))
    if mejor_usd["capital"] not in (filas[0]["capital"], filas[-1]["capital"]):
        print("     El máximo es INTERIOR (ni el primer capital ni el último):")
        print("     el premio sube con el tamaño hasta que el impacto se lo")
        print("     come. Esa es la forma que tiene un techo REAL de capacidad.")
    print("     (la columna $/año de la tabla 3 la da para toda la rejilla)")

    print("\n  COTA SUPERIOR por dos lados: el fill de la ENTRADA sigue sin")
    print("  modelar (V2 midió -1.039R de selección adversa) y el impacto se")
    print("  aplica sobre la serie neta de coste fijo, sin cola. Y COTA")
    print("  INFERIOR por uno: convención pesimista intra-vela.")
    return {"H1": h1, "H2": h2, "H3": bool(h3),
            "techo_neto": rep["techo_neto"], "ratios": ratios, "f250": f250}


def _techo_neto(curvas_por_simbolo):
    """El techo del conjunto = el símbolo que primero se satura.

    Solo cuentan los símbolos con neto > 0: donde no hay edge neto no hay
    capacidad que medir, y meterlos como "C0 en el suelo" convertiría la falta
    de edge en un techo bajo, que es un diagnóstico distinto.

    OJO: esta cifra NO es el "$22k de V3". Aquél es el C0 de **ETH**, el único
    símbolo del VIP con neto apreciable; el techo del CONJUNTO que V3 imprimió
    fue `<$1k`, porque BTC salía a +0.0027R y su C0 cae en el suelo de la
    rejilla. Confundirlos hace que un ratio salga en cinco cifras dividiendo
    por un suelo. Por eso H1 se evalúa SÍMBOLO A SÍMBOLO (`ratios_h1`).
    """
    techos = [c["capital_zero"] for c in curvas_por_simbolo
              if c["mean_R_gross"] > 0 and c["capital_zero"]]
    return min(techos) if techos else None


# Por debajo de este neto, el C0 cae en el suelo de la rejilla y el ratio que
# saldria de el no describe una capacidad: describe una division por casi cero.
# Es el mismo criterio con el que V3 dijo "BTC (+0.0027R) no tiene capacidad
# que medir".
NETO_MINIMO_PARA_RATIO = 0.01


def ratios_h1(curvas_ancha, curvas_v3, *, y=Y_REF):
    """H1 símbolo a símbolo: ¿la celda ancha da >=10x de capacidad?

    El brief manda reportar el símbolo por separado y no elegirlo. Y el ratio
    solo significa algo donde AMBAS celdas tienen neto apreciable: dividir por
    un C0 que está en el suelo de la rejilla produce un número enorme que no
    dice nada del sistema.
    """
    out = []
    for s in sorted(set(curvas_ancha) & set(curvas_v3)):
        a, b = curvas_ancha[s][y], curvas_v3[s]
        evaluable = (a["mean_R_gross"] > NETO_MINIMO_PARA_RATIO
                     and b["mean_R_gross"] > NETO_MINIMO_PARA_RATIO
                     and a["capital_zero"] and b["capital_zero"]
                     and not b["grid_floor"]["zero"])
        out.append({
            "symbol": s,
            "neto_ancha": a["mean_R_gross"], "neto_v3": b["mean_R_gross"],
            "c0_ancha": a["capital_zero"], "c0_v3": b["capital_zero"],
            "ratio": (a["capital_zero"] / b["capital_zero"]) if evaluable else None,
            "evaluable": bool(evaluable),
        })
    return out


def referencia_v3(cube_dir, klines_dir, *, universe=None, tp="tp4", horizon=288,
                  risk_frac, y_impact=Y_REF, fill_bars=1):
    """La capacidad de tp4/h288 medida AQUÍ, a la misma `f` y en la misma
    corrida. Es la mitad de H1: un ratio contra una cifra publicada en otra
    convención no es un ratio, es una comparación de peras con manzanas — y
    ése es justo el error que `require_own_bar` (V4→frontera) cabló para el
    IC. Aquí se cabla para la capacidad."""
    from cube_report import load_pool
    from vip_report import cell_trades, vip_universe

    u = universe if universe is not None else vip_universe()
    t = cell_trades(load_pool(cube_dir), tp, horizon, symbols=u)
    liqs = symbol_liquidity(t, klines_dir)
    curvas = {}
    for s, g in t.groupby("symbol"):
        curvas[s] = require_measured(capacity_curve(
            g["net_r"], liquidity=liqs[s], y_impact=y_impact,
            fill_bars=fill_bars, risk_frac=risk_frac, basis="neto"))
    return {"curvas": curvas, "n": len(t),
            "techo": _techo_neto(list(curvas.values()))}


def run_ancha(cube_dir="cosecha_cubes/", klines_dir="data/binance", *,
              celda=CELDA_ANCHA, salida=SALIDA_ANCHA, universe=None,
              capitals=CAPITAL_GRID, risk_frac=None, y_grid=Y_GRID,
              fill_bars=1, tp="tp4", horizon=288):
    import growth

    if risk_frac is None:
        risk_frac = growth.configured_risk_frac()
    print("=== GATE DE VENUE (cubos de OKX; velas de Binance) ===")
    t = ancha_trades(cube_dir, klines_dir, celda=celda, salida=salida,
                     universe=universe, tp=tp, horizon=horizon)

    # Liquidez MEDIDA una sola vez; la geometría se cambia encima de ella.
    liq_ancha = symbol_liquidity(t, klines_dir)
    liq_apretada = {s: with_stop_frac(liq_ancha[s], liq_ancha[s].stop_frac / celda[0])
                    for s in liq_ancha}

    filas = capital_sweep(t, liq_ancha, capitals=capitals, risk_frac=risk_frac,
                          fill_bars=fill_bars)

    curvas = {}
    for s, g in t.groupby("symbol"):
        curvas[s] = {y: require_measured(capacity_curve(
            g["net_r_sin_impacto"], liquidity=liq_ancha[s], y_impact=y,
            fill_bars=fill_bars, risk_frac=risk_frac, basis="neto"))
            for y in y_grid}

    rep = {"celda": celda, "salida": salida[0], "risk_frac": risk_frac,
           "y_grid": tuple(y_grid), "filas": filas, "curvas": curvas,
           "liq_ancha": liq_ancha, "liq_apretada": liq_apretada,
           "trades": t, "universo": sorted(t["symbol"].unique()),
           "techo_neto": _techo_neto([c[Y_REF] for c in curvas.values()]),
           "sharpe_std": filas[0]["sharpe_std"],
           "v3": referencia_v3(cube_dir, klines_dir, universe=universe, tp=tp,
                               horizon=horizon, risk_frac=risk_frac,
                               fill_bars=fill_bars),
           "ley": {s: ley_stop_frac(liq_apretada[s], risk_frac=risk_frac,
                                    fill_bars=fill_bars)
                   for s in sorted(liq_apretada)}}
    rep["ratios_h1"] = ratios_h1(rep["curvas"], rep["v3"]["curvas"])
    print_ancha(rep)
    rep["veredicto"] = veredicto_ancha(rep)
    return rep


def _load_r(args):
    if args.rfile:
        return list(np.loadtxt(args.rfile, dtype=float).ravel())
    if args.ledger:
        from execution import DurableHashLedger
        import reconciler as rc
        return rc.extract_closed_r(DurableHashLedger.load(args.ledger))
    if args.cube:
        import pandas as pd
        df = pd.read_parquet(args.cube)
        if args.tp and "tp" in df.columns:
            df = df[df["tp"].astype(str) == str(args.tp)]
        if args.label_horizon is not None and "horizon" in df.columns:
            df = df[df["horizon"].astype(int) == int(args.label_horizon)]
        if args.col not in df.columns:
            raise SystemExit("col %r no está en el cubo" % args.col)
        rs = df[args.col].dropna().astype(float)
        if rs.empty:
            raise SystemExit("0 filas tras filtrar (--tp / --label-horizon)")
        return list(rs)
    raise SystemExit("dá una fuente: --cube / --ledger / --rfile")


def lamina(rep, path, *, title="Capacidad: expectancy vs capital"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cap = np.asarray(rep["curve"]["capital"])
    edge = np.asarray(rep["curve"]["edge_r"])
    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(cap, edge, color="#2b6cb0", lw=2)
    ax.axhline(rep["mean_R_gross"], color="#999", ls=":", lw=1,
               label="edge bruto %.3fR" % rep["mean_R_gross"])
    ax.axhline(0.0, color="#d2453f", lw=1)
    for key, col, lab in (("capital_half", "#e0a93f", "C½"),
                          ("capital_zero", "#d2453f", "C0")):
        c = rep.get(key)
        if c:
            ax.axvline(c, color=col, ls="--", lw=1.4,
                       label="%s ≈ $%.0fk" % (lab, c / 1e3))
    ax.set_xscale("log")
    ax.set_xlabel("Capital desplegado (USD, log)")
    ax.set_ylabel("Expectancy por trade (R, neto de impacto)")
    ax.set_title(title)
    ax.legend(loc="lower left", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def _fmt(rep):
    ch = rep["capital_half"]
    cz = rep["capital_zero"]
    return "\n".join([
        "Capacidad — n=%d  edge bruto=%+.4fR" % (rep["n_trades"], rep["mean_R_gross"]),
        "  liquidez=%.1eUSD/bar × %d bars · impact=%.0fbps@q=1 (raíz)"
        % (rep["params"]["avg_bar_notional"], rep["params"]["fill_bars"],
           rep["params"]["impact_coef"]),
        "  C½ (edge a la mitad) ≈ %s" % ("$%.0fk" % (ch / 1e3) if ch else "n/a (no degrada en el rango)"),
        "  C0 (edge anulado)    ≈ %s" % ("$%.0fk" % (cz / 1e3) if cz else "n/a"),
    ])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Análisis de capacidad del edge")
    ap.add_argument("--vip", action="store_true",
                    help="V3: capacidad del universo que el bot difunde, con "
                         "la liquidez MEDIDA de las velas locales")
    ap.add_argument("--ancha", action="store_true",
                    help="V5: la capacidad de la geometría ANCHA (celda y "
                         "salida PRE-FIJADAS), barriendo el capital sobre la "
                         "rejilla pre-registrada del brief")
    ap.add_argument("--celda", default=None,
                    help="kSL,tpR,horizonte — por defecto la PRE-FIJADA del "
                         "cementerio. Cambiarla es OTRA pre-registración.")
    ap.add_argument("--pool", action="store_true",
                    help="PUERTA 3: correr sobre los 13 símbolos del pool en "
                         "vez del universo VIP (el control del subconjunto)")
    ap.add_argument("--cube-dir", default="cosecha_cubes/")
    ap.add_argument("--klines", default="data/binance")
    ap.add_argument("--horizon", type=int, default=288)
    ap.add_argument("--fill-bars-vip", type=int, default=1,
                    help="irrelevante por diseño: la ley raíz con σ escalada a "
                         "la ventana es invariante a esto (hay test)")
    ap.add_argument("--cube"); ap.add_argument("--col", default="pnl_r")
    ap.add_argument("--tp", default=None)
    ap.add_argument("--label-horizon", type=int, default=None)
    ap.add_argument("--ledger"); ap.add_argument("--rfile")
    # Sin valor: `--vip` usa la convención de V3 (1%) para no re-escribir sus
    # cifras publicadas, y `--ancha` usa la `f` VIVA (growth), que es la única
    # con la que la cartera y el impacto pueden juzgarse a la vez.
    ap.add_argument("--risk-frac", type=float, default=None)
    ap.add_argument("--stop-frac", type=float, default=0.012)
    ap.add_argument("--avg-bar-notional", type=float, default=3e6,
                    help="USD negociados por barra (CALIBRAR con volumen real)")
    ap.add_argument("--fill-bars", type=int, default=24)
    ap.add_argument("--impact-coef", type=float, default=45.0,
                    help="slippage bps a participación=1 (CALIBRAR)")
    ap.add_argument("--out-json"); ap.add_argument("--out-png")
    args = ap.parse_args(argv)
    if args.ancha:
        celda = CELDA_ANCHA
        if args.celda:
            k, t, h = args.celda.split(",")
            celda = (float(k), float(t), int(h))
        u = None
        if args.pool:
            from cube_report import load_pool
            from vip_report import base_ccy
            u = frozenset(base_ccy(s) for s in
                          load_pool(args.cube_dir)["symbol"].unique())
        run_ancha(args.cube_dir, args.klines, celda=celda, universe=u,
                  horizon=args.horizon, risk_frac=args.risk_frac,
                  fill_bars=args.fill_bars_vip)
        return 0
    if args.vip:
        run_vip(args.cube_dir, args.klines, tp=args.tp or "tp4",
                horizon=args.horizon,
                risk_frac=(V3_RISK_FRAC if args.risk_frac is None
                           else args.risk_frac),
                fill_bars=args.fill_bars_vip)
        return 0
    rs = _load_r(args)
    rep = capacity_curve(rs, risk_frac=(V3_RISK_FRAC if args.risk_frac is None
                                        else args.risk_frac), stop_frac=args.stop_frac,
                         avg_bar_notional=args.avg_bar_notional,
                         fill_bars=args.fill_bars, impact_coef=args.impact_coef)
    print(_fmt(rep))
    if args.out_json:
        with open(args.out_json, "w") as fh:
            json.dump(rep, fh, indent=2)
        print("→ %s" % args.out_json)
    if args.out_png:
        lamina(rep, args.out_png)
        print("→ %s" % args.out_png)
    return 0


if __name__ == "__main__":
    sys.exit(main())
