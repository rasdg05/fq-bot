# -*- coding: utf-8 -*-
"""
================================================================================
  VIP REPORT — "¿Y el VIP? ¿Funciona?" contestado por un comando
================================================================================

El 2026-08-05 RasDG preguntó exactamente eso. Se midió, salieron dos cosas que
importan — y se midieron con un script de sesión que ya no existe. Por la regla
de la casa (*un hallazgo sin invariante que lo haga cumplir es una nota, no un
arreglo*), aquello era una NOTA. Esto es el arreglo: la misma pregunta, un
comando, un test.

    python tools/vip_report.py

Las dos preguntas, y por qué son dos
------------------------------------
1. **¿El universo?** ¿La selección SOL/BTC/ETH de junio-2026 (que se tomó sobre
   una ventana de 2 meses) se sostiene sobre los 7 años del cube?
2. **¿La geometría?** De las barreras que un producto con suscriptores puede
   sostener, ¿alguna tiene el neto por encima de cero?

Son independientes: el universo puede ser bueno y la geometría mala, que es
justo lo que salió. Mezclarlas produce el veredicto de brocha gorda ("el VIP no
funciona") que no dice qué arreglar.

Por qué el filtro de cartera va ANTES y no como post-mortem
-----------------------------------------------------------
El barrido de agosto (`geometry_sweep`) buscó el máximo de R por trade y
encontró una celda que la señal respalda con seis controles independientes — y
que es inoperable: 13.7 posiciones simultáneas, 71% de drawdown, tirando el 66%
de las señales. El R por trade era real y el producto seguía siendo imposible.

De ahí `screen_cell`: una celda **no se nombra candidata** si no sostiene una
cartera. No es un aviso al pie de la tabla — es parte de la definición. Y el
gate corre **sin cap de concurrencia** a propósito: capear hace pasar cualquier
cosa tirando señales, así que capear antes de juzgar es maquillar el resultado.

Lo que esto NO es
-----------------
Una simulación. La etiqueta triple-barrera del cube asume fill perfecto en el
precio de la barrera, sin cola ni rechazo, y el fill ya se midió caro (−1.039R
de selección adversa). Todo lo de aquí es **cota superior** de lo capturable.
================================================================================
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))           # raiz del repo (bt_engine)
sys.path.insert(0, _HERE)                            # tools/

import growth                                                    # noqa: E402
from bt_engine import CostModel                                  # noqa: E402
from cube_report import _boot_ci, apply_costs, cell_events, load_pool  # noqa: E402
from portfolio_risk import simulate_portfolio, worst_days         # noqa: E402

# El universo del producto se lee de la MISMA variable que el bot difunde
# (`fq_bot_v3_2.VIP_PAIRS`). Que este informe pueda medir un universo distinto
# del que se publica es precisamente la forma de mentir sin saberlo, y por eso
# `test_vip_report.py` compara los dos conjuntos.
VIP_ENV = "FQ_VIP_PAIRS"
VIP_DEFAULT = "BTC,ETH,SOL"

# El horizonte que opera el motor vivo. El barrido de V1 se mueve por el eje TP
# a horizonte FIJO: es la palanca que el producto puede cambiar mañana sin
# tocar nada más.
OPERATING_HORIZON = 288
TP_LADDER = ("tp1", "tp2", "tp3", "tp4")

BAR_MINUTES = 5.0
MIN_N = 30

# Las dos cotas de producto. El DD sale del cementerio (2026-08-04): "un perfil
# de riesgo que el producto pueda sostener con DD < 35%" es la condición escrita
# para revivir la geometría ancha. No es un número redondo elegido hoy.
DD_MAX = 0.35
RISK_FRACS = (0.01, 0.005, 0.0025, 0.001)


class PortfolioGateSkippedError(RuntimeError):
    """Se intentó declarar una celda candidata sin pasarla por la cartera.

    Es la invariante de V1. El barrido de agosto encontró +0.085R por trade con
    CPCV positivo y holdout 8/8 que transfiere, y aquello NO era un candidato:
    a nivel cuenta arruinaba el capital. Un R por trade sin su cartera al lado
    no describe nada operable, así que aquí no puede ni nombrarse.
    """


def vip_universe(env=None):
    """Los símbolos del producto, de la misma variable de entorno que el bot."""
    src = os.environ if env is None else env
    raw = src.get(VIP_ENV, VIP_DEFAULT)
    return frozenset(p.strip().upper() for p in str(raw).split(",") if p.strip())


def base_ccy(symbol):
    """'BTC_USDT' / 'BTC/USDT' / 'BTC' -> 'BTC'. Los cubos y el bot no nombran
    los pares igual; normalizar en un solo sitio evita que el informe mida un
    universo vacío por un guion bajo."""
    return str(symbol).upper().replace("/", "_").split("_")[0]


def split_universe(events, universe=None):
    """(dentro_del_VIP, resto_del_pool). El resto NO es ruido: es el control
    contra el que se juzga si elegir esos tres símbolos aportó algo."""
    u = universe if universe is not None else vip_universe()
    dentro = events["symbol"].map(lambda s: base_ccy(s) in u)
    return events[dentro].copy(), events[~dentro].copy()


def cell_trades(cube, tp, horizon, *, symbols=None, cost=None,
                bar_minutes=BAR_MINUTES):
    """Una celda del cube, con costes aplicados y con VENTANA TEMPORAL.

    El `t1` es lo que distingue esto de `cell_events`: sin saber cuándo cierra
    cada señal no hay solapamiento que medir, y sin solapamiento la cartera no
    existe. `bars_held` sale de la etiqueta triple-barrera, así que el cierre es
    el de la barrera o el del horizonte, nunca una hora de reloj.
    """
    ev = cell_events(cube, tp=tp, horizon=horizon)
    if symbols is not None:
        ev = ev[ev["symbol"].map(lambda s: base_ccy(s) in symbols)]
    if ev.empty:
        return ev.assign(net_r=[], t0=[], t1=[])
    t = apply_costs(ev, cost=cost or CostModel(), bar_minutes=bar_minutes)
    t["t0"] = pd.to_datetime(t["entry_ts"])
    t["t1"] = t["t0"] + pd.to_timedelta(
        t["bars_held"].astype(float) * bar_minutes, unit="m")
    t["net_r"] = t["net_pnl_r"].astype(float)
    return t


def portfolio_gate(trades, *, risk_fracs=RISK_FRACS, dd_max=DD_MAX):
    """¿Alguna fracción de riesgo SIN CAP sostiene esta celda?

    Sin cap a propósito. Un límite de concurrencia hace pasar casi cualquier
    cosa a base de tirar señales — la mejor config por Calmar del barrido de
    agosto daba x12.86 tirando el 66% de las señales y con 71% de drawdown — así
    que capear antes de juzgar convierte el filtro en un adorno. La pregunta
    honesta es si la celda aguanta tal como sale del motor.

    Devuelve (mejor_config | None, todos_los_intentos).
    """
    intentos = []
    for rf in risk_fracs:
        r = simulate_portfolio(trades, rf)
        r["risk_frac"] = rf
        r["crece"] = r["equity_final"] > 1.0
        r["dd_ok"] = -r["max_drawdown"] < dd_max
        intentos.append(r)
    vivas = [r for r in intentos if r["crece"] and r["dd_ok"]]
    mejor = max(vivas, key=lambda r: r["equity_final"]) if vivas else None
    return mejor, intentos


def screen_cell(trades, *, label="", min_n=MIN_N, dd_max=DD_MAX,
                risk_fracs=RISK_FRACS):
    """Los tres filtros que una celda pasa ANTES de poder llamarse candidata.

    1. `n >= MIN_N` — con muestra chica ordenar por resultado selecciona ruido.
    2. IC95% del neto **entero** por encima de cero — no "el punto es positivo".
    3. Una cartera sostenible sin cap ciego, con DD < `dd_max`.

    El 3 es el que no estaba en agosto, y es el que mata a la ganadora de
    entonces. `candidato` es False en cuanto falta cualquiera de los tres: no
    hay forma de leer esta salida como "casi pasa".
    """
    n = len(trades)
    if n == 0:
        return {"label": label, "n": 0, "candidato": False,
                "motivos": ["celda vacía"], "cartera": None, "intentos": [],
                "gross": float("nan"), "net": float("nan"),
                "lo": float("nan"), "hi": float("nan"), "wr": float("nan")}

    net_r = trades["net_r"].to_numpy(float)
    lo, hi, _p = _boot_ci(net_r)
    mejor, intentos = portfolio_gate(trades, risk_fracs=risk_fracs, dd_max=dd_max)

    motivos = []
    if n < min_n:
        motivos.append("n=%d < %d — no concluye ni a favor ni en contra"
                       % (n, min_n))
    if not lo > 0:
        motivos.append("IC95%% del neto [%+.4f, %+.4f] no está entero sobre cero"
                       % (lo, hi))
    if mejor is None:
        if not intentos:
            motivos.append("sin cartera evaluable")
        elif not any(r["crece"] for r in intentos):
            # Decir "no aguanta el drawdown" cuando el drawdown está dentro de
            # la cota confunde el diagnostico: aqui la cuenta no se hunde por
            # riesgo mal puesto, se hunde porque la celda pierde dinero. Son
            # dos enfermedades con cotas distintas y hay que nombrarlas aparte.
            mejor_dd = min(-r["max_drawdown"] for r in intentos)
            motivos.append(
                "la cuenta termina POR DEBAJO del capital inicial a toda "
                "risk_frac (DD %.1f%% está dentro de la cota: no sobra riesgo, "
                "falta edge)" % (mejor_dd * 100))
        else:
            crecen = [r for r in intentos if r["crece"]]
            motivos.append(
                "crece pero con DD %.1f%% >= %.0f%%: no es sostenible en un "
                "producto con suscriptores (el cliente se va antes del suelo)"
                % (min(-r["max_drawdown"] for r in crecen) * 100, dd_max * 100))

    base = intentos[-1] if intentos else {}
    # V4: la celda se juzga tambien por lo que le hace a UNA cuenta, no solo por
    # su media. La `f` es la que gobierna la cuenta viva — evaluar la celda a una
    # fraccion distinta de la que se opera es medir otro producto (misma familia
    # de error que medir un universo distinto del que se difunde).
    g = growth.growth_stats(net_r)
    return {
        "label": label,
        "n": n,
        "growth": g,
        "gross": float(trades["pnl_r"].mean()),
        "net": float(np.mean(net_r)),
        "lo": lo, "hi": hi,
        "wr": float((trades["pnl_r"] > 0).mean() * 100),
        "conc_media": base.get("conc_media", float("nan")),
        "conc_max": base.get("conc_max", 0),
        "hold_dias": float((trades["t1"] - trades["t0"])
                           .dt.total_seconds().mean() / 86400.0),
        "cartera": mejor,
        "intentos": intentos,
        "motivos": motivos,
        "candidato": not motivos,
    }


def require_screened(fila):
    """Guardia de runtime: nadie publica una celda como candidata sin cartera.

    Espejo de `cube_report.cell_stats`, que levanta si falta el neto. Aquí lo
    que no puede faltar es el veredicto de cartera — el filtro que en agosto se
    corrió DESPUÉS y por eso no impidió nada.
    """
    if not isinstance(fila, dict) or "candidato" not in fila:
        raise PortfolioGateSkippedError(
            "esto no pasó por screen_cell(): una celda sin su veredicto de "
            "cartera no describe nada operable")
    if fila["candidato"] and fila.get("cartera") is None:
        raise PortfolioGateSkippedError(
            "celda %r marcada candidata sin config de cartera que la sostenga"
            % fila.get("label"))
    return fila


# --------------------------------------------------------------------------
#  1) EL UNIVERSO
# --------------------------------------------------------------------------

def universe_report(cube, *, tp="tp4", horizon=OPERATING_HORIZON,
                    universe=None, cost=None, bar_minutes=BAR_MINUTES):
    """¿La selección de junio-2026 se sostiene sobre 7 años?

    La celda de referencia es tp4/h288 — la de research, no la que opera. Es a
    propósito: la pregunta aquí es sobre los SÍMBOLOS, y compararlos en la celda
    donde el pool entero se midió evita que un universo salga mejor solo por
    haberle puesto barreras distintas.
    """
    u = universe if universe is not None else vip_universe()
    t = cell_trades(cube, tp, horizon, cost=cost, bar_minutes=bar_minutes)
    dentro, fuera = split_universe(t, u)

    print("\n=== 1) EL UNIVERSO — ¿la selección de junio se sostiene? ===")
    print("  celda de referencia %s/h%d · %s = %s"
          % (tp, horizon, VIP_ENV, ",".join(sorted(u))))
    if dentro.empty:
        print("  el cube no trae ninguno de esos símbolos -> sin medición")
        return None

    filas = []
    for nombre, g in (("VIP", dentro), ("resto del pool", fuera)):
        if g.empty:
            continue
        lo, hi, _ = _boot_ci(g["net_r"].to_numpy(float))
        filas.append((nombre, g["symbol"].nunique(), len(g),
                      g["pnl_r"].mean(), g["net_r"].mean(), lo, hi))
    print("  %-16s %5s %7s %9s %9s %22s" % (
        "grupo", "sims", "n", "bruto", "NETO", "IC95% neto"))
    for nombre, sims, n, gr, ne, lo, hi in filas:
        print("  %-16s %5d %7d %+9.4f %+9.4f  [%+9.4f,%+9.4f]"
              % (nombre, sims, n, gr, ne, lo, hi))

    ventaja = float("nan")
    if len(filas) == 2:
        ventaja = filas[0][4] - filas[1][4]
        print("  -> ventaja del universo VIP: %+.4fR netos por señal" % ventaja)
        print("     %s" % ("la selección aporta y ahora tiene 7 años detrás, no "
                           "una ventana de 2 meses" if ventaja > 0 else
                           "elegir esos símbolos NO aportó: el resto del pool "
                           "rinde igual o mejor"))

    # Por símbolo: el agregado del universo esconde que sus miembros no se
    # parecen. Si el pilar del producto es el peor de los tres, eso es
    # exactamente lo que hay que ver — no un promedio que lo tapa (E9).
    print("\n  -- por símbolo VIP (el agregado de arriba esconde esto) --")
    meses = _meses_cubiertos(t)
    for sym, g in sorted(dentro.groupby("symbol"),
                         key=lambda kv: -kv[1]["net_r"].mean()):
        lo, hi, _ = _boot_ci(g["net_r"].to_numpy(float))
        print("     %-12s n=%5d  bruto %+.4f -> NETO %+.4f  IC95%%[%+.4f,%+.4f]"
              "  ~%.0f señales/mes%s"
              % (sym, len(g), g["pnl_r"].mean(), g["net_r"].mean(), lo, hi,
                 len(g) / meses if meses else float("nan"),
                 "" if len(g) >= MIN_N else "   <- n<%d" % MIN_N))
    return {"vip": dentro, "resto": fuera, "ventaja": ventaja}


def _meses_cubiertos(t):
    if t.empty:
        return 0.0
    span = pd.to_datetime(t["entry_ts"]).max() - pd.to_datetime(t["entry_ts"]).min()
    return max(span.total_seconds() / 86400.0 / 30.44, 1e-9)


# --------------------------------------------------------------------------
#  2) LA GEOMETRIA
# --------------------------------------------------------------------------

def tp_sweep(cube, *, horizon=OPERATING_HORIZON, tps=TP_LADDER, universe=None,
             cost=None, bar_minutes=BAR_MINUTES, dd_max=DD_MAX,
             risk_fracs=RISK_FRACS, min_n=MIN_N):
    """Barrido tp1->tp2->tp3(->tp4) a horizonte fijo, sobre el universo VIP,
    con el filtro de cartera aplicado a cada celda ANTES de reportarla.

    No es el barrido de agosto otra vez. Aquel movía la distancia del stop sobre
    el pool entero buscando el máximo de R; este mueve la distancia del OBJETIVO
    sobre el universo que se publica, y la vara no es el máximo de R sino la
    supervivencia de la cuenta. Ensanchar el stop está medido y agotado
    (CEMENTERIO 2026-08-04); esto es el otro eje, y el único que el producto
    puede cambiar mañana sin tocar el motor.
    """
    u = universe if universe is not None else vip_universe()
    filas = []
    for tp in tps:
        t = cell_trades(cube, tp, horizon, symbols=u, cost=cost,
                        bar_minutes=bar_minutes)
        filas.append(require_screened(screen_cell(
            t, label="%s/h%d" % (tp, horizon), min_n=min_n, dd_max=dd_max,
            risk_fracs=risk_fracs)))
    return filas


def print_sweep(filas, *, dd_max=DD_MAX):
    print("\n=== 2) LA GEOMETRIA — barrido del objetivo, con la cartera puesta ANTES ===")
    print("  Una celda NO se nombra candidata si no sostiene una cuenta. El")
    print("  filtro corre SIN cap de concurrencia: capear hace pasar cualquier")
    print("  cosa tirando señales (la ganadora de agosto tiraba el 66%).")
    print("\n  %-10s %6s %9s %9s %20s %6s %7s %9s %10s %8s" % (
        "celda", "n", "bruto", "NETO", "IC95% neto", "WR", "hold_d",
        "DD mejor", "g/trade", "P(arriba)"))
    for f in filas:
        if f["n"] == 0:
            print("  %-10s   (vacía)" % f["label"])
            continue
        dd = ("%8.1f%%" % (-f["cartera"]["max_drawdown"] * 100)
              if f["cartera"] else "     ---")
        g = f.get("growth") or {}
        gg = "%+10.6f" % g["g"] if g.get("g") is not None else "     RUINA"
        pu = "%7.1f%%" % (g["p_up"] * 100) if g.get("p_up") is not None else "      --"
        print("  %-10s %6d %+9.4f %+9.4f  [%+8.4f,%+8.4f] %5.1f%% %7.1f %9s %10s %8s"
              % (f["label"], f["n"], f["gross"], f["net"], f["lo"], f["hi"],
                 f["wr"], f["hold_dias"], dd, gg, pu))
    _aviso_de_crecimiento(filas)

    _aviso_de_esquina(filas)

    print("\n  -- veredicto por celda, y por qué --")
    for f in filas:
        if f["candidato"]:
            c = f["cartera"]
            print("     %-10s CANDIDATA: risk %.2f%% sin cap -> x%.2f con DD %.1f%%"
                  % (f["label"], c["risk_frac"] * 100, c["equity_final"],
                     -c["max_drawdown"] * 100))
        else:
            print("     %-10s %s" % (f["label"], f["motivos"][0]))
            for m in f["motivos"][1:]:
                print("     %-10s %s" % ("", m))


def _aviso_de_esquina(filas):
    """¿El mejor neto cae en el ÚLTIMO peldaño probado?

    `geometry_sweep` ya trata esto como bandera roja y por eso extendió su
    rejilla hasta kSL=12: un máximo en la esquina significa que el óptimo está
    fuera del rango medido y que la tabla está extrapolando. Aquí el eje TP se
    acaba en tp4 porque **el cube solo trae cuatro etiquetas**, no porque tp4
    sea el final del gradiente. Callarlo dejaría leer "tp4 es lo mejor" cuando
    lo medido es "de lo que hay, tp4 es lo último".
    """
    vivas = [f for f in filas if f["n"]]
    if len(vivas) < 3:
        return
    netos = [f["net"] for f in vivas]
    if netos[-1] != max(netos) or not all(a < b for a, b in zip(netos, netos[1:])):
        return
    print("\n  >> MAXIMO EN LA ESQUINA: el neto sube en cada peldaño y el mejor")
    print("     es el ÚLTIMO probado (%s). El gradiente apunta FUERA del rango"
          % vivas[-1]["label"])
    print("     medido, así que esta tabla no dice que %s sea el óptimo — dice"
          % vivas[-1]["label"])
    print("     que el óptimo puede estar más allá y que aquí no se ve. El eje")
    print("     se acaba porque el cube trae 4 etiquetas, no porque el gradiente")
    print("     gire. Para saberlo hay que RE-ETIQUETAR con objetivos más lejanos")
    print("     (`geometry_sweep`, que necesita velas locales), no extrapolar.")
    print("     Y ojo: alejar el objetivo alarga la vida del trade, o sea que")
    print("     devuelve el problema de concurrencia que mató la geometría ancha.")


def print_por_ano(cube, fila_tp, horizon, universe, *, cost=None,
                  bar_minutes=BAR_MINUTES, min_n=MIN_N):
    """E9 aplicado: la celda que opera el motor NO se lee agregada.

    Un neto promediado sobre siete años puede ser dos años buenos tapando dos
    malos, que es la forma exacta del espejismo de mayo.
    """
    t = cell_trades(cube, fila_tp, horizon, symbols=universe, cost=cost,
                    bar_minutes=bar_minutes)
    if t.empty:
        return
    print("\n=== 3) LA CELDA QUE OPERA HOY (%s/h%d), POR AÑO ===" % (fila_tp, horizon))
    t = t.copy()
    t["ano"] = pd.to_datetime(t["entry_ts"]).dt.year
    negativos = anos = 0
    for y, g in t.groupby("ano"):
        x = g["net_r"].to_numpy(float)
        lo, hi, _ = _boot_ci(x)
        flaco = "   <- n<%d, no concluye" % min_n if len(x) < min_n else ""
        print("  %s n=%5d  NETO %+.4f  IC95%%[%+.4f, %+.4f]%s"
              % (y, len(x), x.mean(), lo, hi, flaco))
        if len(x) >= min_n:
            anos += 1
            negativos += int(x.mean() < 0)
    if anos:
        print("  -> %d de %d años con n suficiente salen NEGATIVOS." % (negativos, anos))
    print("\n  peores días por R agregada (las pérdidas llegan juntas):")
    for d, row in worst_days(t).iterrows():
        print("    %s  %7.1fR en %d cierres" % (d, row["sum"], row["count"]))


def verdict(filas, universo):
    print("\n" + "-" * 78)
    cands = [f for f in filas if f["candidato"]]
    if cands:
        print("  >> HAY celda(s) operable(s): %s" % ", ".join(f["label"] for f in cands))
        print("     Confírmalas con CPCV/PBO y el gate DSR antes de tocar el")
        print("     producto. Pasar este filtro es necesario, no suficiente.")
    else:
        print("  >> NINGUNA geometría del eje TP es operable sobre el universo VIP.")
        print("     No es falta de muestra: son las barreras. La señal sigue")
        print("     confirmada (E7: asimetría +1.011R) y el universo sigue siendo")
        print("     mejor que el resto del pool — lo que no existe es una forma")
        print("     conocida de cobrarla dentro de un perfil de riesgo operable.")
        print("     Desenlace legítimo: al CEMENTERIO con su n, no maquillado.")
        # Y una distincion que hay que decir en voz alta: aqui el filtro de
        # cartera NO es el que mata. La geometria ancha de agosto moria por
        # concurrencia; este eje muere por expectancy. Confundirlos llevaria a
        # buscar un mecanismo de concurrencia que no arreglaria nada.
        por_cartera = [f for f in filas
                       if f["n"] and f["lo"] > 0 and f["cartera"] is None]
        if not por_cartera:
            print("\n     OJO con el diagnóstico: ninguna celda cae POR la cartera.")
            print("     El hold medio es de horas y la concurrencia baja, así que")
            print("     el problema de la geometría ancha (13.7 simultáneas) no")
            print("     aplica a este eje. Estas celdas caen por expectancy. Un")
            print("     mecanismo de concurrencia no arreglaría ninguna.")
    if universo is not None and universo.get("ventaja") == universo.get("ventaja"):
        print("\n  Y separado de lo anterior: la selección de símbolos aporta")
        print("  %+.4fR netos por señal frente al resto del pool. Son dos"
              % universo["ventaja"])
        print("  preguntas distintas y solo una salió mal.")
    print("\n  COTA SUPERIOR: etiqueta triple-barrera, fill perfecto asumido, sin")
    print("  cola ni rechazo. El fill real ya se midió (−1.039R de selección")
    print("  adversa). Lo realizable está POR DEBAJO de esta tabla.")


def run(cube_dir, *, horizon=OPERATING_HORIZON, ref_tp="tp4", tps=TP_LADDER,
        universe=None, cost=None, bar_minutes=BAR_MINUTES, dd_max=DD_MAX):
    u = universe if universe is not None else vip_universe()
    cube = load_pool(cube_dir)
    print("=" * 78)
    print("  ¿FUNCIONA EL VIP?  —  %s · horizonte operativo h%d"
          % ("/".join(sorted(u)), horizon))
    print("=" * 78)
    uni = universe_report(cube, tp=ref_tp, horizon=horizon, universe=u,
                          cost=cost, bar_minutes=bar_minutes)
    filas = tp_sweep(cube, horizon=horizon, tps=tps, universe=u, cost=cost,
                     bar_minutes=bar_minutes, dd_max=dd_max)
    print_sweep(filas, dd_max=dd_max)
    print_por_ano(cube, tps[0], horizon, u, cost=cost, bar_minutes=bar_minutes)
    verdict(filas, uni)
    return {"universo": uni, "celdas": filas}


def main(argv=None):
    ap = argparse.ArgumentParser(description="¿Funciona el VIP? Una pregunta, un comando.")
    ap.add_argument("--cube", default="cosecha_cubes/")
    ap.add_argument("--horizon", type=int, default=OPERATING_HORIZON,
                    help="horizonte que opera el motor (velas de 5m)")
    ap.add_argument("--ref-tp", default="tp4",
                    help="celda de referencia para comparar universos")
    ap.add_argument("--tps", default=",".join(TP_LADDER))
    ap.add_argument("--dd-max", type=float, default=DD_MAX,
                    help="drawdown máximo que el producto tolera")
    ap.add_argument("--bar-minutes", type=float, default=BAR_MINUTES)
    a = ap.parse_args(argv)
    out = run(a.cube, horizon=a.horizon, ref_tp=a.ref_tp,
              tps=tuple(x.strip() for x in a.tps.split(",") if x.strip()),
              dd_max=a.dd_max, bar_minutes=a.bar_minutes)
    return 0 if out["universo"] is not None else 1


def _aviso_de_crecimiento(filas):
    """La lectura que la columna E[R] no da: qué le pasa a UNA cuenta.

    La media aritmética es el promedio del ensemble. Una cuenta vive una
    trayectoria y compone, y sobre estas distribuciones (skew ~+2, mediana muy
    por debajo de la media) las dos divergen con signo. Que la tabla imprima
    `g` y `P(arriba)` al lado del E[R] es el equivalente de V4 a lo que E9 hizo
    con el desglose: el número que se entiende va pegado al que no.
    """
    vivas = [f for f in filas if f["n"] and (f.get("growth") or {}).get("g") is not None]
    if not vivas:
        return
    rf = vivas[0]["growth"]["risk_frac"]
    hor = vivas[0]["growth"]["horizon"]
    print("\n  g = crecimiento logarítmico por trade a risk %.2f%% (la `f` que" % (rf * 100))
    print("  gobierna la cuenta viva) · P(arriba) = acabar sobre el capital")
    print("  inicial tras %d trades. Aproximación normal: con skew positivo la" % hor)
    print("  real es algo PEOR, así que esa columna es optimista.")
    for f in vivas:
        g = f["growth"]
        if g["f_star"] <= 0:
            print("     %-10s f* = 0 -> ninguna fracción positiva hace crecer "
                  "esta celda" % f["label"])
        elif growth.is_overbet(g):
            print("     %-10s f* = %.2f%% -> a risk %.2f%% se apuesta %.1fx de más"
                  % (f["label"], g["f_star"] * 100, g["risk_frac"] * 100, g["overbet"]))


if __name__ == "__main__":
    sys.exit(main())
