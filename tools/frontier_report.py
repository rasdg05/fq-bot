# -*- coding: utf-8 -*-
"""
================================================================================
  FRONTIER REPORT — ¿cuánto falta para la frontera, y por qué camino?
================================================================================

`internal/BRIEF_FRONTERA_2026-08.md` dejó tres preguntas abiertas y dijo que
cabían en una corrida. Esto es esa corrida:

    python tools/frontier_report.py

  1. ¿Cuánto neto compra cada escalón de comisiones, y **qué tier es
     ALCANZABLE**? (el brief lo dejó explícitamente sin cerrar).
  2. ¿Qué dan las palancas apiladas, medidas netas y con la cartera puesta?
  3. ¿Qué distancia hay de aquí a la frontera por cada camino?

La corrección que obliga a que esto exista
------------------------------------------
El brief escribió la frontera como **una constante** (+0.07R). No lo es. La
frontera es el punto donde el IC95% del neto queda entero sobre cero, y ese
punto depende de la **n de la configuración que lo pretende cruzar**. Toda
palanca que FILTRA señales (convicción, régimen, gates) sube la media y a la vez
**aleja la vara**, porque con menos muestra el IC se ensancha.

Comparar el neto de una config filtrada contra la vara de la config sin filtrar
es la forma limpia de creerse un avance que no existe. Aquí la vara se recalcula
para cada fila, y la identidad que lo hace barato es exacta:

    brecha_a_la_frontera  ==  -IC_lo

(si `lo = media - h`, hace falta `media > h`, o sea `media - lo > media`, o sea
que falta `-lo`). Cuando `-lo` es negativo, la config YA cruzó.

La otra corrección: un tier de comisiones no es aritmética
-----------------------------------------------------------
`coste_R = (2·fee + 2·slip)/stop_frac` sí es aritmética. **Que la cuenta
alcance ese tier no lo es**, y esa parte el brief la contó como palanca #1 "que
no depende de que ningún research salga bien". Depende de una cosa: del volumen
que la propia estrategia genera, que es `n_señales x 2 x (equity·f)/stop_frac`.

Por eso `require_reachable` levanta si alguien reporta la ganancia de un tier
sin comprobar su requisito de volumen contra el throughput de la cuenta. Es la
misma familia que `MakerFillAssumedError` (V2) y `CapacityAssumedError` (V3):
tres veces el repo publicó una cifra apoyada en un supuesto más grande que el
margen entero.

Lo que esto NO es
-----------------
Una simulación, y menos una promesa. Corre sobre la etiqueta triple-barrera del
cube: fill perfecto en el precio de la barrera, sin cola ni rechazo. V2 midió
que el fill real cuesta −1.039R de selección adversa. **Todo lo de aquí es cota
superior.** Y bajar de tier no es un resultado medido: es una ACCIÓN (cambiar de
venue, stakear, usar referral) cuyo efecto se estima aquí.
================================================================================
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))           # raiz del repo
sys.path.insert(0, _HERE)                            # tools/

import growth                                                      # noqa: E402
from bt_engine import CostModel                                    # noqa: E402
from cube_report import _boot_ci, load_pool                        # noqa: E402
from vip_report import (BAR_MINUTES, MIN_N, OPERATING_HORIZON,     # noqa: E402
                        TP_LADDER, cell_trades, require_screened,
                        screen_cell, vip_universe)

# El slippage NO se toca en el barrido de fees a propósito: es la parte del
# coste que no depende del tier, y moverlo a la vez haría imposible atribuir la
# mejora. Es el mismo valor que usa todo el repo (bt_engine.CostModel).
SLIP_BPS = 1.0

# La `f` de la cuenta viva. Sale de growth (V4) para que el volumen que se
# calcula aquí sea el de la cuenta que de verdad existe, no el de una hipotética.
DEFAULT_EQUITIES = (10_000, 22_000, 100_000, 434_000, 1_200_000)


class FeeTierUnreachableError(RuntimeError):
    """Se contó la ganancia de un tier de comisiones sin comprobar que la
    cuenta lo alcanza.

    Tiene factura detrás. El brief de agosto listó "bajar comisiones" como la
    palanca #1, "+0.06 a +0.09R", y "del tamaño de la frontera entera". El
    escalón que da esa cifra en Binance es VIP1 o mejor, y VIP1 pide **$15M de
    volumen en 30 días**. La estrategia genera ~45 señales/mes en el universo
    VIP; a la capacidad NETA que midió V3 ($22k) eso son ~$0.97M/mes. La cuenta
    no puede ser lo bastante grande para ganarse el tier que haría demostrable
    el edge, porque el edge no sostiene una cuenta tan grande. V3 y la palanca
    #1 son la MISMA pared vista por los dos lados.
    """


class FrontierBarMovedError(RuntimeError):
    """Se comparó una configuración contra una vara que no es la suya.

    La frontera no es +0.07R para todo el mundo: es `-IC_lo`, y el IC depende de
    la n. Una palanca que tira un tercio de las señales sube la media Y sube la
    vara. Medir la primera sin la segunda es exactamente el espejismo que este
    repo lleva un año aprendiendo a no creerse.
    """


# --------------------------------------------------------------------------
#  Los tiers, DECLARADOS con su requisito (no medidos aquí)
# --------------------------------------------------------------------------
# Mismo trato que `queue_frac` en V2 y que `Y` en V3: es un supuesto declarado,
# con fuente y fecha, y por eso se publica la CURVA y no un punto. `volume_30d`
# es el requisito de volumen en USD; None = no depende del volumen (depende de
# capital inmovilizado o de un código, que es otra clase de puerta).
#
# Fuentes (consultadas 2026-08-08):
#   binance.com/en/fee/futureFee — USDT-M VIP0 taker 0.0500%, VIP9 0.0170%;
#     VIP1 pide 15.000.000 USD de volumen de futuros en 30 días; pagar con BNB
#     descuenta hasta un 10% y apila con el tier.
#   Hyperliquid — perp taker base 0.045% / maker 0.015%; los tramos de volumen
#     bajan hasta 0.024% por encima de $7.000M en 14 días; el descuento por
#     stakear HYPE va del 5% (>10 HYPE) al 40% (>500.000 HYPE); el referral
#     descuenta un 4% del taker en los primeros $25M.
#
# Cada tier declara su PUERTA, y las puertas no son de la misma clase:
#   ("ninguna", 0)      — un código o un saldo trivial. Se alcanza hoy.
#   ("volumen", USD)    — throughput de 30d. Se compara con lo que la
#                         estrategia genera de verdad.
#   ("capital", HYPE)   — token inmovilizado. NO se evalúa sin precio: sin
#                         `--hype-price` la fila sale `??` (falla cerrado).
#   ("desconocida", -)  — requisito no verificado. También `??`.
TIERS = (
    # (etiqueta, taker_bps, (clase_de_puerta, magnitud), nota)
    ("Binance VIP0 (base del repo)", 5.00, ("ninguna", 0.0),
     "es el coste con el que están medidos TODOS los números del repo"),
    ("Binance VIP0 + BNB (-10%)", 4.50, ("ninguna", 0.0),
     "no pide volumen: pide saldo de BNB para pagar fees"),
    ("Hyperliquid base", 4.50, ("ninguna", 0.0),
     "venue distinto, sin requisito de volumen"),
    ("Hyperliquid + referral (-4%)", 4.32, ("ninguna", 0.0),
     "un código; vale para los primeros $25M de volumen"),
    ("HL + referral + stake Wood (-5%)", 4.10, ("capital", 10.0),
     ">10 HYPE inmovilizados"),
    ("Binance VIP1", 4.00, ("volumen", 15_000_000.0),
     "el primer escalón que SÍ pide volumen"),
    ("Binance VIP4-ish", 3.00, ("desconocida", 0.0),
     "varios escalones más arriba; el requisito exacto no está verificado"),
    ("HL Diamond (-40%)", 2.70, ("capital", 500_000.0),
     ">500.000 HYPE inmovilizados"),
    ("Binance VIP9 (el suelo de la tabla)", 1.70, ("desconocida", 0.0),
     "el mínimo publicado; requisito de volumen no verificado"),
)

# Qué fracción del capital se acepta inmovilizada en un token para comprar un
# descuento de fees. No es una constante de mercado: es una decisión de riesgo,
# y va aquí para que se vea. Inmovilizar HYPE es tomar exposición DIRECCIONAL a
# un token para subvencionar una estrategia cuyo edge no está demostrado — la
# varianza de esa posición es órdenes de magnitud mayor que los +0.04R que
# compra. Por eso el default es bajo y por eso la fila lo dice en voz alta.
MAX_CAPITAL_LOCK_FRAC = 0.10


# --------------------------------------------------------------------------
#  La vara, recalculada donde toque
# --------------------------------------------------------------------------

def frontier_gap(net_r, *, seed=7):
    """Cuánto R por trade le falta a ESTA configuración para que su IC95% del
    neto quede entero sobre cero. Negativo = ya cruzó.

    Es `-IC_lo` por identidad, no por aproximación: si `lo = media - h`, cruzar
    pide `media > h`, o sea que falta `h - media = -lo`. Se calcula sobre la n
    de la propia configuración, que es el punto entero de esta función.
    """
    x = np.asarray(net_r, dtype=float)
    if len(x) == 0:
        return float("nan"), float("nan"), 0
    lo, hi, _p = _boot_ci(x, seed=seed)
    return -float(lo), float(x.mean()), len(x)


def require_own_bar(fila):
    """Guardia: una fila de esta tabla no se publica sin la vara de su propia n.

    Sin esto, la tabla vuelve a ser "cuánto sube la media" — que es la mitad de
    la pregunta y justo la mitad que engaña.
    """
    if not isinstance(fila, dict) or "brecha" not in fila or "n" not in fila:
        raise FrontierBarMovedError(
            "fila sin `brecha` calculada sobre su propia n: comparar contra la "
            "vara de otra configuración es el espejismo que esto existe para "
            "impedir")
    return fila


# --------------------------------------------------------------------------
#  El volumen que la estrategia genera (lo que decide qué tier alcanza)
# --------------------------------------------------------------------------

def monthly_volume_usd(trades, *, equity, risk_frac=None, bar_minutes=BAR_MINUTES):
    """Volumen de 30 días que genera la estrategia con esa cuenta.

    `notional = risk_amount / stop_frac`, y cada trade cruza el book DOS veces
    (entrada y salida). El `stop_frac` sale de las propias señales, no de un
    catálogo — es la lección de V3, donde el default de liquidez estaba 8x fuera.
    """
    if len(trades) == 0:
        return 0.0, 0.0, float("nan")
    f = growth.configured_risk_frac() if risk_frac is None else float(risk_frac)
    sf = (trades["stop_price"] - trades["entry_price"]).abs() / trades["entry_price"]
    stop_frac = float(sf.median())
    ts = pd.to_datetime(trades["entry_ts"])
    meses = max((ts.max() - ts.min()).total_seconds() / 86400.0 / 30.44, 1e-9)
    por_mes = len(trades) / meses
    notional = (equity * f) / stop_frac
    return por_mes * 2.0 * notional, por_mes, stop_frac


def require_reachable(tier, volume_30d, *, equity=None, hype_price=None,
                      max_lock=MAX_CAPITAL_LOCK_FRAC):
    """¿Puede ESTA cuenta contar la ganancia de este tier?

    Devuelve `(alcanzable, motivo)` y levanta `FeeTierUnreachableError` cuando
    la puerta no se puede ni evaluar. No saber si se alcanza NO es alcanzarlo:
    la versión anterior de esta función trataba "puerta de capital" como
    "sin requisito" y por eso marcaba ALCANZABLE un tier que pide 500.000 HYPE
    inmovilizados. Ése es exactamente el espejismo que el módulo existe para
    impedir, cometido dentro del módulo.
    """
    lbl, _bps, (clase, magnitud), nota = tier
    if clase == "ninguna":
        return True, nota
    if clase == "desconocida":
        raise FeeTierUnreachableError(
            "tier %r sin requisito verificado: no se cuenta una ganancia cuya "
            "puerta nadie miró (%s)" % (lbl, nota))
    if clase == "volumen":
        if volume_30d is None:
            raise FeeTierUnreachableError(
                "tier %r evaluado sin el volumen que genera la cuenta: el "
                "requisito es $%s/30d y no hay con qué compararlo"
                % (lbl, f"{magnitud:,.0f}"))
        if volume_30d < magnitud:
            return False, ("pide $%s/30d y la cuenta genera $%s"
                           % (f"{magnitud:,.0f}", f"{volume_30d:,.0f}"))
        return True, nota
    if clase == "capital":
        if hype_price is None or equity is None:
            raise FeeTierUnreachableError(
                "tier %r es puerta de CAPITAL (%s) y no hay precio con que "
                "valorarla: pasa --hype-price para evaluarla. Sin precio no se "
                "cuenta como ganada" % (lbl, nota))
        coste = magnitud * float(hype_price)
        tope = float(equity) * max_lock
        if coste > tope:
            return False, ("pide $%s inmovilizados (%s) y el tope es $%s "
                           "(%.0f%% de la cuenta)"
                           % (f"{coste:,.0f}", nota, f"{tope:,.0f}",
                              max_lock * 100))
        return True, ("%s = $%s inmovilizados, exposición DIRECCIONAL ajena a "
                      "la estrategia" % (nota, f"{coste:,.0f}"))
    raise FeeTierUnreachableError("clase de puerta desconocida: %r" % clase)


# --------------------------------------------------------------------------
#  1) La escalera de comisiones
# --------------------------------------------------------------------------

def fee_ladder(cube, *, tp="tp4", horizon=OPERATING_HORIZON, universe=None,
               equity=22_000, bar_minutes=BAR_MINUTES, tiers=TIERS,
               hype_price=None):
    """Neto y brecha a la frontera en cada escalón, con el tier marcado
    ALCANZABLE o no contra el volumen que la propia cuenta genera."""
    u = universe if universe is not None else vip_universe()
    base = cell_trades(cube, tp, horizon, symbols=u, cost=CostModel(),
                       bar_minutes=bar_minutes)
    vol, por_mes, stop_frac = monthly_volume_usd(base, equity=equity)

    print("\n=== 1) LA ESCALERA DE COMISIONES — y qué escalón alcanza la cuenta ===")
    print("  celda %s/h%d · universo %s · n=%d" % (tp, horizon, ",".join(sorted(u)), len(base)))
    print("  cuenta de referencia: equity $%s a f=%.2f%% -> notional/trade $%s"
          % (f"{equity:,}", growth.configured_risk_frac() * 100,
             f"{(equity * growth.configured_risk_frac()) / stop_frac:,.0f}"))
    print("  la estrategia emite ~%.0f señales/mes (stop mediano %.2f%%)"
          " -> VOLUMEN 30d = $%s" % (por_mes, stop_frac * 100, f"{vol:,.0f}"))
    print()
    print("  %-44s %6s %9s %11s %10s  %s"
          % ("escalón", "taker", "NETO", "brecha", "n", "¿alcanzable?"))

    filas = []
    for tier in tiers:
        lbl, bps, puerta, nota = tier
        t = cell_trades(cube, tp, horizon, symbols=u,
                        cost=CostModel(taker_fee=bps / 1e4, slippage_bps=SLIP_BPS),
                        bar_minutes=bar_minutes)
        brecha, media, n = frontier_gap(t["net_r"].to_numpy(float))
        try:
            ok, motivo = require_reachable(tier, vol, equity=equity,
                                           hype_price=hype_price)
        except FeeTierUnreachableError as e:
            ok, motivo = None, str(e).split(":")[-1].strip()
        fila = require_own_bar({
            "tier": lbl, "taker_bps": bps, "neto": media, "brecha": brecha,
            "n": n, "alcanzable": ok, "motivo": motivo, "puerta": puerta})
        filas.append(fila)
        marca = {True: "SI", False: "NO", None: "??"}[ok]
        print("  %-44s %5.2f %+9.4f %+11.4f %8d  %-3s %s"
              % (lbl, bps, media, brecha, n, marca,
                 "" if ok and puerta[0] == "ninguna" else motivo))

    print()
    print("  brecha = cuánto R por trade falta para que el IC95% quede entero")
    print("  sobre cero, calculada sobre la n de ESA fila. Negativa = ya cruzó.")
    print("  `??` = la puerta no se pudo ni evaluar. No saberlo NO es alcanzarlo.")

    alc = [f for f in filas if f["alcanzable"]]
    cruzan = [f for f in filas if f["brecha"] <= 0]
    if alc:
        mejor = min(alc, key=lambda f: f["brecha"])
        print("\n  >> MEJOR ESCALÓN ALCANZABLE: %s (%.2f bps)"
              % (mejor["tier"], mejor["taker_bps"]))
        print("     neto %+.4f · le sigue faltando %+.4fR"
              % (mejor["neto"], mejor["brecha"]))
    if cruzan:
        cruce = max(cruzan, key=lambda f: f["taker_bps"])   # el más caro que cruza
        print("\n  >> EL PRIMER ESCALÓN QUE CRUZA es %s (%.2f bps)."
              % (cruce["tier"], cruce["taker_bps"]))
        # `NO alcanzable` y `puerta sin evaluar` son dos diagnósticos distintos.
        # Fundirlos es la misma clase de error que decir "no aguanta el
        # drawdown" cuando lo que falta es edge: suena igual y se arregla
        # distinto.
        if cruce["alcanzable"] is False:
            print("     Y ESTÁ MEDIDO QUE NO SE ALCANZA: %s" % cruce["motivo"])
        else:
            print("     Y SU PUERTA NI SIQUIERA SE PUDO EVALUAR: %s"
                  % cruce["motivo"])
            print("     Eso no lo hace alcanzable: lo hace desconocido.")
        print("     En ambos casos se cierra el lazo con V3: los escalones que")
        print("     cruzan piden volumen (VIP1 ya pide $15M/30d) y la cuenta")
        print("     genera $%s a la capacidad NETA que V3 midió." % f"{vol:,.0f}")
        print("     **El edge no sostiene la cuenta que haría falta para")
        print("     abaratar el edge.**")
        print("     Es una pared estructural, no una tarea pendiente.")
    else:
        print("\n  >> NINGÚN escalón de la tabla cruza la frontera en esta celda.")
    return filas


# --------------------------------------------------------------------------
#  2) Las palancas apiladas, con la cartera puesta
# --------------------------------------------------------------------------

def conviction_cut(trades, *, drop="bajo", terciles=3):
    """Corta el tercil BAJO de `p_master`. Hipótesis PRE-REGISTRADA: GATE-C ya
    la validó en bruto (PBO 0.008); lo que se mide aquí es si sobrevive NETA.
    No es un barrido — es un umbral fijado de antemano, y por eso no infla
    `n_trials` más allá de 1."""
    if drop is None:
        return trades
    q = trades["p_master"].quantile(1.0 / terciles)
    return trades[trades["p_master"] > q]


def stacked_report(cube, *, tps=TP_LADDER, horizon=OPERATING_HORIZON,
                   universe=None, reachable_bps=4.10, bar_minutes=BAR_MINUTES,
                   min_n=MIN_N):
    """Coste base vs coste alcanzable, x con/sin corte de convicción, sobre el
    eje TP entero. Cada fila pasa por `screen_cell` (cartera antes que
    candidata) y lleva su propia vara."""
    u = universe if universe is not None else vip_universe()
    costes = (("base 5.00bps", CostModel()),
              ("alcanzable %.2fbps" % reachable_bps,
               CostModel(taker_fee=reachable_bps / 1e4, slippage_bps=SLIP_BPS)))

    print("\n=== 2) LAS PALANCAS APILADAS — netas y con la cartera puesta ===")
    print("  palanca #1 = bajar al mejor tier ALCANZABLE (%.2f bps)" % reachable_bps)
    print("  palanca #2 = cortar el tercil bajo de convicción (GATE-C, pre-registrada)")
    print("  n_trials de esta tabla: %d celdas x %d cortes = %d"
          % (len(tps), 2, len(tps) * 2))
    print()
    print("  %-5s %-20s %-16s %6s %9s %+11s %9s  %s"
          % ("celda", "coste", "convicción", "n", "NETO", "brecha", "cartera",
             "CANDIDATO"))

    filas = []
    for tp in tps:
        for lbl_c, cost in costes:
            t = cell_trades(cube, tp, horizon, symbols=u, cost=cost,
                            bar_minutes=bar_minutes)
            for lbl_v, d in (("todas", t), ("sin tercil bajo", conviction_cut(t))):
                s = require_screened(screen_cell(
                    d, label="%s|%s|%s" % (tp, lbl_c, lbl_v), min_n=min_n))
                brecha, media, n = frontier_gap(d["net_r"].to_numpy(float))
                fila = require_own_bar({
                    "celda": tp, "coste": lbl_c, "conviccion": lbl_v,
                    "n": n, "neto": media, "brecha": brecha,
                    "cartera": s["cartera"] is not None,
                    "candidato": s["candidato"], "motivos": s["motivos"]})
                filas.append(fila)
                print("  %-5s %-20s %-16s %6d %+9.4f %+11.4f %9s  %s"
                      % (tp, lbl_c, lbl_v, n, media, brecha,
                         "ok" if fila["cartera"] else "NO",
                         "SI" if fila["candidato"] else "no"))

    mejor = min(filas, key=lambda f: f["brecha"])
    print("\n  >> MEJOR CONFIGURACIÓN ALCANZABLE HOY: %s · %s · %s"
          % (mejor["celda"], mejor["coste"], mejor["conviccion"]))
    print("     neto %+.4f con n=%d · le falta %+.4fR para ser demostrable"
          % (mejor["neto"], mejor["n"], mejor["brecha"]))
    if mejor["brecha"] > 0:
        print("     SIGUE SIN SER CANDIDATA. %s" % (mejor["motivos"][0] if mejor["motivos"] else ""))
    return filas


# --------------------------------------------------------------------------
#  3) La vara se mueve: cuánto de la brecha cierra cada palanca
# --------------------------------------------------------------------------

def gap_attribution(filas, *, celda="tp4"):
    """Descomposición honesta: cuánto cerró cada palanca de la brecha inicial,
    y cuánto de eso se lo comió el ensanchamiento del IC por perder muestra."""
    sel = {(f["coste"].startswith("base"), f["conviccion"] == "todas"): f
           for f in filas if f["celda"] == celda}
    base = sel.get((True, True))
    solo_fee = sel.get((False, True))
    solo_conv = sel.get((True, False))
    ambas = sel.get((False, False))
    if not all((base, solo_fee, solo_conv, ambas)):
        return None

    print("\n=== 3) ATRIBUCIÓN DE LA BRECHA (celda %s) ===" % celda)
    print("  De dónde sale el avance, y qué parte se lo come la muestra perdida.")
    print()
    print("  %-26s %9s %9s %11s %8s" % ("configuración", "NETO", "Δ media", "brecha", "n"))
    for lbl, f in (("punto de partida", base), ("+ solo comisiones", solo_fee),
                   ("+ solo convicción", solo_conv), ("+ las dos", ambas)):
        print("  %-26s %+9.4f %+9.4f %+11.4f %8d"
              % (lbl, f["neto"], f["neto"] - base["neto"], f["brecha"], f["n"]))

    print()
    cerrado = base["brecha"] - ambas["brecha"]
    print("  la brecha pasó de %+.4f a %+.4f -> se cerró el %.0f%%"
          % (base["brecha"], ambas["brecha"], 100.0 * cerrado / base["brecha"]))
    subida = ambas["neto"] - base["neto"]
    peaje = subida - cerrado
    print("  la media subió %+.4f pero la brecha solo bajó %+.4f:" % (subida, cerrado))
    print("  **%+.4fR se los comió la vara al moverse** (n %d -> %d)."
          % (peaje, base["n"], ambas["n"]))
    print("  Ése es el peaje de toda palanca que filtra, y es la razón por la")
    print("  que la frontera NO es una constante. Contarlo aparte no es")
    print("  pesimismo: es lo que distingue avance de espejismo.")
    return {"cerrado": cerrado, "subida": subida, "peaje": peaje,
            "base": base, "ambas": ambas}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("cubes", nargs="?", default="cosecha_cubes/")
    ap.add_argument("--tp", default="tp4", help="celda de la escalera de fees")
    ap.add_argument("--horizon", type=int, default=OPERATING_HORIZON)
    ap.add_argument("--equity", type=float, default=22_000,
                    help="capital de referencia (default = la capacidad NETA de V3)")
    ap.add_argument("--reachable-bps", type=float, default=4.32,
                    help="mejor tier alcanzable SIN inmovilizar capital")
    ap.add_argument("--hype-price", type=float, default=None,
                    help="precio de HYPE para evaluar las puertas de CAPITAL; "
                         "sin él esas filas salen '??' (falla cerrado)")
    a = ap.parse_args(argv)

    cube = load_pool(a.cubes)
    print("=" * 78)
    print("  FRONTERA — ¿cuánto falta, y por qué camino?")
    print("=" * 78)
    print("  COTA SUPERIOR: etiqueta triple-barrera, fill perfecto asumido.")
    print("  V2 midió el fill real en -1.039R de selección adversa. Lo")
    print("  realizable está POR DEBAJO de todo lo que sigue.")

    fee_ladder(cube, tp=a.tp, horizon=a.horizon, equity=a.equity,
               hype_price=a.hype_price)
    filas = stacked_report(cube, horizon=a.horizon,
                           reachable_bps=a.reachable_bps)
    gap_attribution(filas, celda=a.tp)

    print("\n" + "-" * 78)
    print("  Recordatorio de alcance: bajar de tier es una ACCIÓN (cambiar de")
    print("  venue, stakear, referral), no un resultado medido. Y el corte de")
    print("  convicción está pre-registrado (GATE-C) pero nunca se ha medido")
    print("  FORWARD. Nada de esto es todavía un edge demostrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
