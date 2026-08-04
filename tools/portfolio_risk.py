# -*- coding: utf-8 -*-
"""
================================================================================
  PORTFOLIO RISK — el R por trade NO describe el riesgo de la cartera
================================================================================

Todo lo que este repo mide está en R por trade: expectancy, IC95%, DSR. Eso
describe una operación **aislada**. Una cartera no opera aisladamente: si hay 14
posiciones abiertas a la vez sobre activos correlacionados, las pérdidas llegan
JUNTAS, y el drawdown no se parece a la suma de trades independientes.

El caso que motivó esto: la geometría ancha del barrido daba +0.085R por trade
con CPCV positivo y holdout por símbolo que transfiere (8/8). A nivel cartera, a
`risk_frac=1%` sin límite de concurrencia, **arruina la cuenta** — porque el
hold medio son 2 días y eso deja 13.7 posiciones abiertas de media, 54 en el
pico. El edge por trade era real y el producto seguía siendo inviable.

Un número que no pasa por aquí no describe nada operable.

Contabilidad
------------
El capital se compromete en la APERTURA y el PnL se realiza en el CIERRE. Es la
diferencia que importa: una curva de equity que compone trade a trade en orden
de entrada asume que el capital estaba libre, y con solapamiento no lo está —
sobrestima el retorno y subestima el drawdown a la vez.

`max_concurrent` modela el límite real de una cuenta: si ya hay N abiertas, la
siguiente señal **se salta** (no se encola). Saltarlas es una decisión de
producto con coste medible — el informe reporta cuántas se tiran.

Lo que esto NO modela
---------------------
Correlación explícita entre posiciones. No hace falta para el veredicto: la
concurrencia ya la incorpora por la vía que importa (las pérdidas coinciden en
el tiempo, y el informe lista los peores días agregados). Pero significa que el
drawdown de aquí sigue siendo una COTA INFERIOR del real.

Uso (como librería):
    from tools.portfolio_risk import simulate_portfolio, report
    report(trades, risk_fracs=(0.01, 0.0025), caps=(None, 5))
================================================================================
"""
import numpy as np
import pandas as pd

MIN_N = 30


def simulate_portfolio(trades, risk_frac, max_concurrent=None):
    """Curva de equity con solapamiento real.

    `trades`: DataFrame con t0 (apertura), t1 (cierre) y net_r. El orden de las
    filas da igual — se reordena por evento.

    Devuelve dict con equity final, drawdown maximo, curva, concurrencia y
    cuantas señales se saltaron por el limite.
    """
    t0 = pd.to_datetime(trades["t0"]).to_numpy()
    t1 = pd.to_datetime(trades["t1"]).to_numpy()
    net = trades["net_r"].to_numpy(float)

    # Un cierre en el mismo instante que una apertura libera capital ANTES de
    # comprometerlo: si no, el limite de concurrencia rechaza señales que en la
    # practica si cabrian.
    eventos = sorted(
        [(t0[i], 1, i) for i in range(len(net))] +
        [(t1[i], 0, i) for i in range(len(net))],
        key=lambda e: (e[0], e[1]))

    eq = 1.0
    abiertas = 0
    pico_conc = 0
    riesgo = {}
    saltadas = 0
    curva_t, curva_e, conc_t, conc_n = [], [], [], []

    for t, tipo, i in eventos:
        if tipo == 1:
            if max_concurrent is not None and abiertas >= max_concurrent:
                saltadas += 1
                riesgo[i] = None
                continue
            riesgo[i] = eq * risk_frac       # capital comprometido AL ABRIR
            abiertas += 1
            pico_conc = max(pico_conc, abiertas)
        else:
            r = riesgo.get(i)
            if r is None:
                continue
            eq += r * net[i]                 # PnL realizado AL CERRAR
            abiertas -= 1
            curva_t.append(t)
            curva_e.append(eq)
        conc_t.append(t)
        conc_n.append(abiertas)

    c = pd.Series(curva_e, index=pd.to_datetime(curva_t))
    dd = ((c - c.cummax()) / c.cummax()).min() if len(c) else 0.0
    conc = pd.Series(conc_n, index=pd.to_datetime(conc_t))
    return {
        "equity_final": eq,
        "max_drawdown": float(dd),
        "curva": c,
        "conc_media": float(conc.mean()) if len(conc) else 0.0,
        "conc_p95": float(np.percentile(conc, 95)) if len(conc) else 0.0,
        "conc_max": int(pico_conc),
        "saltadas": saltadas,
        "n": len(net),
    }


def worst_days(trades, k=5):
    """Los peores dias por R agregada — la prueba de que llegan juntas."""
    t = trades.copy()
    t["dia"] = pd.to_datetime(t["t1"]).dt.date
    g = t.groupby("dia")["net_r"].agg(["sum", "count"])
    return g.nsmallest(k, "sum")


def report(trades, *, risk_fracs=(0.01, 0.005, 0.0025, 0.001),
           caps=(None, 10, 5, 3), cap_risk_frac=0.01):
    """Tabla de supervivencia. Devuelve la mejor config por Calmar."""
    n = len(trades)
    base = simulate_portfolio(trades, 0.001)
    print("\n" + "=" * 74)
    print("  RIESGO DE CARTERA — %d trades" % n)
    print("=" * 74)
    print("  hold medio %.1f dias | simultaneas: media %.1f, p95 %.0f, max %d"
          % ((pd.to_datetime(trades.t1) - pd.to_datetime(trades.t0))
             .dt.total_seconds().mean() / 86400.0,
             base["conc_media"], base["conc_p95"], base["conc_max"]))
    print("  E[R] por trade %+.4f  <- esto es lo que TODO el repo reporta"
          % trades["net_r"].mean())
    print("  ...y lo de abajo es lo que esa cifra NO dice.")

    filas = []
    print("\n  %-34s %10s %9s %8s" % ("config", "x final", "DD max", "saltadas"))
    for rf in risk_fracs:
        r = simulate_portfolio(trades, rf)
        filas.append(("risk=%.3f%% sin cap" % (rf * 100), rf, None, r))
        print("  risk_frac=%-6.3f%% sin cap           %10.2f %8.1f%% %8d"
              % (rf * 100, r["equity_final"], -r["max_drawdown"] * 100, r["saltadas"]))
    for cap in caps:
        if cap is None:
            continue
        r = simulate_portfolio(trades, cap_risk_frac, max_concurrent=cap)
        filas.append(("risk=%.2f%% cap %d" % (cap_risk_frac * 100, cap),
                      cap_risk_frac, cap, r))
        print("  risk_frac=%-5.2f%%  cap %-2d simultaneas %10.2f %8.1f%% %8d"
              % (cap_risk_frac * 100, cap, r["equity_final"],
                 -r["max_drawdown"] * 100, r["saltadas"]))

    print("\n  peores dias por R agregada (la prueba de que llegan juntas):")
    for d, row in worst_days(trades).iterrows():
        print("    %s  %7.1fR en %d cierres" % (d, row["sum"], row["count"]))

    vivas = [f for f in filas if f[3]["equity_final"] > 1.0]
    if not vivas:
        print("\n  >> NINGUNA configuracion termina por encima del capital inicial.")
        return None
    mejor = max(vivas, key=lambda f: f[3]["equity_final"] / max(-f[3]["max_drawdown"], 1e-9))
    r = mejor[3]
    print("\n  >> Mejor por Calmar: %s -> x%.2f con DD %.1f%%"
          % (mejor[0], r["equity_final"], -r["max_drawdown"] * 100))
    if -r["max_drawdown"] > 0.35:
        print("     Un drawdown de %.0f%% no es operable en un producto con"
              % (-r["max_drawdown"] * 100))
        print("     suscriptores: el cliente se va mucho antes del suelo.")
    if r["saltadas"] > 0.5 * r["n"]:
        print("     Y descarta el %.0f%% de las señales por el limite de"
              % (100.0 * r["saltadas"] / r["n"]))
        print("     concurrencia: la cadencia del producto se desploma.")
    print("\n  COTA INFERIOR del drawdown: no se modela correlacion explicita")
    print("  entre posiciones abiertas. El real es PEOR, no mejor.")
    return mejor
