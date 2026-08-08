# -*- coding: utf-8 -*-
"""
================================================================================
  GEOMETRY SWEEP — ¿un stop más ancho diluye el coste fijo lo bastante?
================================================================================

La hipótesis: el coste en R es `(2·fee + 2·slip) / (stop/precio)`, así que
ensanchar el stop lo divide. Con el stop mediano de esta cosecha (0.525% del
precio) el peaje son 0.229R; con un stop 3× serían 0.076R.

El contra-argumento, y por qué esto NO es libre
-----------------------------------------------
Si se ensancha el stop **y el objetivo con él** (misma geometría en R), la
asimetría de recorrido disponible se divide por el mismo factor: E7 midió
+1.011R sobre el stop actual, que son 0.531% del precio. En R nuevo, con k=3,
son 0.337R contra un coste de 0.076R. El ratio asimetría/coste es **4.42× para
cualquier k**. Un reescalado puro es exactamente eso: invariante.

Pero la invarianza solo aplica al RECORRIDO, que es un estadístico de camino.
La **resolución por barreras no es lineal**: un trade que hoy muere en el stop y
luego se recupera se convierte en ganador con un stop más ancho, y uno que hoy
cobra el TP se queda en timeout si el objetivo se aleja. La distribución de R
realizada cambia de FORMA, no solo de escala — y eso es lo único que puede mover
el neto. Es lo que esto mide.

Qué se hace, exactamente
------------------------
Se re-etiqueta cada señal del cube con triple barrera sobre las velas reales,
reusando `bt_labeler.label_event_grid` (misma convención de empate pesimista que
la cosecha original: si TP y SL caen en la misma vela, gana el stop), sobre una
rejilla de (multiplicador de stop × objetivo en R × horizonte). Después se
aplica el modelo de costes y se busca si ALGUNA celda tiene el IC95% del neto
por encima de cero.

Y se cuenta la rejilla como `n_trials` en el DSR: mirar 50 geometrías y quedarse
con la mejor es exactamente lo que el gate deflacta. Sin eso, la mejor celda de
una rejilla siempre parece un hallazgo.

Uso:
    python tools/geometry_sweep.py --klines data/binance
================================================================================
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

from bt_engine import CostModel                                   # noqa: E402
from bt_labeler import label_event_dynamic, label_event_grid      # noqa: E402
from cube_report import cell_events, load_pool                    # noqa: E402
from fill_quality import align, load_klines, recompute_excursion, validate_venue  # noqa: E402
from validation_gate import _sharpe, deflated_from_trials         # noqa: E402
from vip_report import require_screened, screen_cell, vip_universe  # noqa: E402

MIN_N = 30
# La rejilla llega hasta kSL=12 a proposito: con (1..5) el maximo caia en la
# ESQUINA, que es la señal clasica de que el optimo esta fuera del rango probado
# y de que se esta extrapolando. Extendida, el gradiente GIRA (kSL 5 -> 8 -> 12
# empeora), o sea que hay optimo interior y no una deriva hacia comprar-y-esperar.
SL_MULTS = (1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 12.0)
TP_RS = (1.0, 2.0, 3.0, 4.0, 6.0, 10.0)
HORIZONS = (576, 1152)

# --------------------------------------------------------------------------
#  EJE DE SALIDA — pre-registrado en internal/BRIEF_SALIDA_2026-08.md
# --------------------------------------------------------------------------
# La geometria NO se busca: viene PRE-FIJADA por el resultado publicado del
# cementerio (2026-08-04), que es un resultado con fecha y no una busqueda nueva.
CELDA_PRIMARIA = (5.0, 6.0, 1152)      # la de +0.0608R
CELDA_REPLICA = (5.0, 10.0, 1152)      # la de CPCV 13/15, replica declarada

# Estas 7 SON el `n_trials`. Declaradas enteras antes de correr; el brief
# prohibe expresamente cruzarlas con nada. `arm=1.0` en la familia A queda FIJO
# (no se busca) porque sin umbral de armado la regla es degenerada.
EXIT_RULES = (
    ("control (barreras fijas)", None),
    ("A trail k=0.33", {"kind": "trail", "k": 0.33, "arm": 1.0}),
    ("A trail k=0.50", {"kind": "trail", "k": 0.50, "arm": 1.0}),
    ("A trail k=0.67", {"kind": "trail", "k": 0.67, "arm": 1.0}),
    # OJO — DEGENERACION DE LA PRE-REGISTRACION, encontrada al correr (2026-08-08).
    # `be_trail(m=1.0, k=0.50)` es MATEMATICAMENTE IDENTICO a `trail(k=0.50,
    # arm=1.0)`: al armarse con mfe>=1.0, el `max(0, mfe*0.5)` del breakeven
    # nunca muerde porque mfe*0.5 >= 0.5 > 0. Las dos reglas producen la MISMA
    # columna hasta el ultimo decimal. Se deja en la tabla marcada como duplicado
    # en vez de borrarla: la rejilla se declaro antes de correr y borrarla a
    # posteriori seria reescribir la pre-registracion. Pero NO cuenta como
    # evidencia independiente ni como trial.
    ("B breakeven m=1.0 (= A k=0.50)", {"kind": "be_trail", "m": 1.0, "k": 0.50}),
    ("B breakeven m=2.0", {"kind": "be_trail", "m": 2.0, "k": 0.50}),
    ("C techo T=96", {"kind": "time", "T": 96}),
    ("C techo T=288", {"kind": "time", "T": 288}),
)
# El control no es un trial, y el duplicado tampoco: son 6 reglas DISTINTAS.
DUPLICADA = "(= A k=0.50)"
N_TRIALS_SALIDA = len([n for n, r in EXIT_RULES
                       if r is not None and DUPLICADA not in n])
N_TRIALS_PARANOICO = 84 * N_TRIALS_SALIDA      # divulgacion obligatoria

# La `f` que gobierna la cuenta viva. El drawdown se reporta AQUI, no en la
# risk_frac mas conservadora de la rejilla: informar el DD minimo entre cuatro
# fracciones es informar el de la mas timida (0.1%), que no es la que se opera y
# hace parecer segura una celda que a 0.25% lleva el doble de DD.
F_VIVA = 0.0025


def net_r_vectorized(direction, entry, exit_price, stop, bars_held, outcome,
                     cost, bar_minutes=5.0):
    """R NETA por trade, vectorizada. Espejo exacto de `bt_engine.simulate`.

    Existe por velocidad: la rejilla son ~650k filas y el bucle de `simulate`
    tardaría diez minutos por barrido. Que sea un ESPEJO y no una segunda
    implementación lo garantiza `test_el_neto_vectorizado_coincide_con_simulate`,
    que la compara contra bt_engine fila a fila. Si alguien toca el modelo de
    costes en un sitio y no en el otro, ese test cae — que es justo el fallo que
    este repo ya vivió con la regla de fill viviendo dos veces.
    """
    d = np.asarray(direction, float)
    entry = np.asarray(entry, float)
    exit_price = np.asarray(exit_price, float)
    stop_dist = np.abs(entry - np.asarray(stop, float))
    slip = cost.slippage_frac

    entry_maker = bool(cost.maker_entry)
    exit_maker = bool(cost.maker_tp_exit) & (np.asarray(outcome) == "win")

    eff_entry = entry if entry_maker else entry * (1 + d * slip)
    eff_exit = np.where(exit_maker, exit_price, exit_price * (1 - d * slip))

    gross = d * (eff_exit - eff_entry)
    fee_in = (cost.maker_fee if entry_maker else cost.taker_fee) * entry
    fee_out = np.where(exit_maker, cost.maker_fee, cost.taker_fee) * exit_price
    funding = 0.0
    if cost.apply_funding:
        periods = np.asarray(bars_held, float) * bar_minutes / 60.0 / 8.0
        funding = d * cost.funding_rate_8h * periods * (entry + exit_price) / 2.0
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(stop_dist > 0,
                        (gross - fee_in - fee_out - funding) / stop_dist, np.nan)


def relabel(events, kl, pos, *, sl_mults=SL_MULTS, tp_rs=TP_RS, horizons=HORIZONS):
    """Re-etiqueta cada señal bajo cada geometría. Devuelve un frame largo.

    Reusa `bt_labeler.label_event_grid` — la misma función que produjo el cube —
    para que el empate intra-vela se resuelva igual aquí que allí. Reimplementar
    la triple barrera sería introducir una segunda convención sin querer.
    """
    max_h = max(horizons)
    hi, lo, cl = (kl["high"].to_numpy(float), kl["low"].to_numpy(float),
                  kl["close"].to_numpy(float))
    n = len(kl)
    entry = events["entry_price"].to_numpy(float)
    stop0 = events["stop_price"].to_numpy(float)
    d = events["direction"].to_numpy(int)
    ts = events["entry_ts"].to_numpy()
    risk0 = np.abs(entry - stop0)

    filas = []
    for i in range(len(events)):
        p = pos[i]
        if p < 0 or risk0[i] <= 0:
            continue
        a, b = p + 1, min(p + 1 + max_h, n)
        if b - a < 2:
            continue
        bars = pd.DataFrame({"high": hi[a:b], "low": lo[a:b], "close": cl[a:b]})
        for k in sl_mults:
            riesgo = risk0[i] * k
            stop = entry[i] - d[i] * riesgo
            targets = {"R%g" % t: entry[i] + d[i] * t * riesgo for t in tp_rs}
            g = label_event_grid(bars, entry[i], stop, int(d[i]), targets,
                                 horizons, pessimistic=True)
            for (name, h), cell in g["cells"].items():
                filas.append((ts[i], int(d[i]), entry[i], stop, riesgo, k,
                              float(name[1:]), h, cell["outcome"],
                              cell["bars_held"], cell["exit_price"],
                              cell["pnl_r"]))
    return pd.DataFrame(filas, columns=[
        "entry_ts", "direction", "entry_price", "stop_price", "risk", "k_sl",
        "tp_r", "horizon", "outcome", "bars_held", "exit_price", "pnl_r"])


def _boot(x, reps=2000, seed=7):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    m = np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(reps)])
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)), float((m > 0).mean())


def report(long, cost, *, bar_minutes=5.0):
    long = long.copy()
    long["net_pnl_r"] = net_r_vectorized(
        long.direction, long.entry_price, long.exit_price, long.stop_price,
        long.bars_held, long.outcome, cost, bar_minutes)

    celdas = {}
    for (k, t, h), g in long.groupby(["k_sl", "tp_r", "horizon"]):
        celdas[(k, t, h)] = g["net_pnl_r"].to_numpy(float)

    print("\n" + "=" * 78)
    print("  BARRIDO DE GEOMETRIA — %d señales x %d celdas" % (
        long.entry_ts.nunique(), len(celdas)))
    print("=" * 78)
    print("  Recordatorio: reescalar stop Y objetivo a la vez es INVARIANTE en el")
    print("  ratio asimetria/coste (4.42x para cualquier k). Lo unico que puede")
    print("  mover el neto es que la resolucion por barreras cambie de forma.")

    for h in sorted(long.horizon.unique()):
        print("\n=== NETO por celda · horizonte %d velas (%.0f h) ===" % (h, h * 5 / 60))
        print("  %-8s" % "kSL\\tpR" + "".join("%10.1f" % t for t in sorted(long.tp_r.unique())))
        for k in sorted(long.k_sl.unique()):
            fila = "  %-8.1f" % k
            for t in sorted(long.tp_r.unique()):
                x = celdas.get((k, t, h))
                fila += "%10.4f" % (np.nanmean(x) if x is not None and len(x) else np.nan)
            print(fila)

    # El gate: n_trials = celdas miradas. Quedarse con la mejor de 50 es
    # exactamente lo que el DSR deflacta.
    sharpes = {c: _sharpe(v[~np.isnan(v)]) for c, v in celdas.items() if len(v) >= MIN_N}
    orden = sorted(sharpes, key=lambda c: -sharpes[c])
    print("\n=== LAS 6 MEJORES, CON EL GATE ENCIMA (n_trials=%d) ===" % len(sharpes))
    print("  %-22s %6s %9s %9s %22s %8s" % (
        "celda", "n", "bruto", "NETO", "IC95% neto", "DSR"))
    alguna = False
    for c in orden[:6]:
        k, t, h = c
        g = long[(long.k_sl == k) & (long.tp_r == t) & (long.horizon == h)]
        x = celdas[c][~np.isnan(celdas[c])]
        lo_, hi_, _ = _boot(x)
        dsr = deflated_from_trials(x, list(sharpes.values()))
        pasa = dsr["significant"] and lo_ > 0
        alguna = alguna or pasa
        print("  kSL=%.1f tpR=%.1f h=%-5d %6d %+9.4f %+9.4f  [%+8.4f,%+8.4f] %8.3f%s"
              % (k, t, h, len(x), g.pnl_r.mean(), x.mean(), lo_, hi_, dsr["dsr"],
                 "" if pasa else "  NO"))
    # E9 aplicado a esto: la celda ganadora NO se lee agregada. Un neto positivo
    # promediado sobre siete anos puede ser dos anos buenos tapando dos malos —
    # que es exactamente la forma del fantasma.
    mejor = orden[0]
    g = long[(long.k_sl == mejor[0]) & (long.tp_r == mejor[1])
             & (long.horizon == mejor[2])].copy()
    g["ano"] = pd.to_datetime(g.entry_ts).dt.year
    print("\n=== LA MEJOR CELDA, POR ANO (kSL=%.1f tpR=%.1f h=%d) ==="
          % mejor)
    print("  desenlaces: %s" % ", ".join(
        "%s %.0f%%" % (a, b * 100)
        for a, b in g.outcome.value_counts(normalize=True).items()))
    print("  stop = %.2f%% del precio (mediana)"
          % (100 * (g.risk / g.entry_price).median()))
    negativos, anos = 0, 0
    for y, gy in g.groupby("ano"):
        x = gy["net_pnl_r"].to_numpy(float)
        lo_, hi_, _ = _boot(x)
        flaco = "   <- n<%d, no concluye" % MIN_N if len(x) < MIN_N else ""
        print("  %s n=%5d  NETO %+.4f  IC95%%[%+.4f, %+.4f]%s"
              % (y, len(x), np.nanmean(x), lo_, hi_, flaco))
        if len(x) >= MIN_N:
            anos += 1
            negativos += int(np.nanmean(x) < 0)

    print("\n" + "-" * 78)
    if not alguna:
        print("  >> NINGUNA geometria clarea el gate (DSR>0.95 + IC95%>0).")
        print("     La mejor celda es la ganadora de un concurso de %d, elegida" % len(sharpes))
        print("     despues de ver los resultados.")
    else:
        print("  >> Hay al menos una geometria que clarea el DSR. Confirmala con")
        print("     CPCV/PBO antes de creerla.")
    if anos and negativos:
        print("  >> Y REPARTE MAL: %d de %d anos con n suficiente salen NEGATIVOS."
              % (negativos, anos))
        print("     Un neto agregado sobre anos que van de un signo al otro no es")
        print("     un edge estable: es la forma exacta del espejismo de mayo. El")
        print("     juez correcto aqui NO es el IC del pool — es CPCV con folds")
        print("     temporales, que es lo que mide si sobrevive fuera de muestra.")
    print("\n  Sigue siendo COTA SUPERIOR: sin modelo de fill. Y el fill ya se")
    print("  midio (-1.039R de seleccion adversa en la entrada maker).")
    return long


def relabel_exits(events, kl, pos, symbol, *, celda, exit_rules=EXIT_RULES):
    """Re-etiqueta cada senal bajo cada REGLA DE SALIDA, con la geometria fija.

    La geometria (kSL, tpR, horizonte) no se mueve: viene pre-fijada. Lo unico
    que varia es cuando se cierra. Por eso el control (`exit_rule=None`) es
    exactamente comparable — misma entrada, mismo stop, mismo objetivo.
    """
    k_sl, tp_r, horizon = celda
    hi, lo, cl = (kl["high"].to_numpy(float), kl["low"].to_numpy(float),
                  kl["close"].to_numpy(float))
    n = len(kl)
    entry = events["entry_price"].to_numpy(float)
    stop0 = events["stop_price"].to_numpy(float)
    d = events["direction"].to_numpy(int)
    ts = events["entry_ts"].to_numpy()
    risk0 = np.abs(entry - stop0)

    filas = []
    for i in range(len(events)):
        p = pos[i]
        if p < 0 or risk0[i] <= 0:
            continue
        a, b = p + 1, min(p + 1 + horizon, n)
        if b - a < 2:
            continue
        bars = pd.DataFrame({"high": hi[a:b], "low": lo[a:b], "close": cl[a:b]})
        riesgo = risk0[i] * k_sl
        stop = entry[i] - d[i] * riesgo
        target = entry[i] + d[i] * tp_r * riesgo
        for nombre, regla in exit_rules:
            r = label_event_dynamic(bars, entry[i], stop, target, int(d[i]),
                                    exit_rule=regla, max_bars=horizon,
                                    pessimistic=True)
            filas.append((symbol, ts[i], int(d[i]), entry[i], stop, riesgo,
                          nombre, r["outcome"], r["bars_held"],
                          r["exit_price"], r["pnl_r"]))
    return pd.DataFrame(filas, columns=[
        "symbol", "entry_ts", "direction", "entry_price", "stop_price", "risk",
        "salida", "outcome", "bars_held", "exit_price", "pnl_r"])


def report_exits(long, cost, *, celda, bar_minutes=5.0, etiqueta="PRIMARIA",
                 n_trials=N_TRIALS_SALIDA):
    """El veredicto del eje de salida, con las tres puertas de la casa puestas:
    vara propia por fila, cartera antes que candidata, y DSR deflactado."""
    long = long.copy()
    long["net_pnl_r"] = net_r_vectorized(
        long.direction, long.entry_price, long.exit_price, long.stop_price,
        long.bars_held, long.outcome, cost, bar_minutes)
    long["t0"] = pd.to_datetime(long["entry_ts"])
    long["t1"] = long["t0"] + pd.to_timedelta(
        long["bars_held"].astype(float) * bar_minutes, unit="m")
    long["net_r"] = long["net_pnl_r"]

    k_sl, tp_r, horizon = celda
    print("\n" + "=" * 78)
    print("  EJE DE SALIDA · celda %s PRE-FIJADA kSL=%.1f tpR=%.1f h=%d"
          % (etiqueta, k_sl, tp_r, horizon))
    print("=" * 78)
    print("  n_trials = %d (las reglas; el control no cuenta)." % n_trials)
    print("  Divulgacion paranoica: la celda salio de una rejilla de 84, asi")
    print("  que la cota superior de trials es %d. Se imprime al lado."
          % N_TRIALS_PARANOICO)

    grupos = {nombre: g for nombre, g in long.groupby("salida")}
    sharpes = {nombre: _sharpe(g["net_r"].to_numpy(float)[
        ~np.isnan(g["net_r"].to_numpy(float))])
        for nombre, g in grupos.items() if len(g) >= MIN_N}

    print("\n  %-26s %6s %8s %9s %9s %10s %8s %8s"
          % ("salida", "n", "hold_d", "bruto", "NETO", "brecha", "DSR", "DSRp"))
    filas = []
    orden = [nombre for nombre, _ in EXIT_RULES if nombre in grupos]
    for nombre in orden:
        g = grupos[nombre]
        x = g["net_r"].to_numpy(float)
        x = x[~np.isnan(x)]
        if len(x) < MIN_N:
            continue
        lo_, hi_, _ = _boot(x)
        brecha = -lo_                      # la vara de SU n (frontier_report)
        dsr = deflated_from_trials(x, list(sharpes.values()))
        dsr_p = deflated_from_trials(x, list(sharpes.values()) * 84)
        hold_d = float(g["bars_held"].mean()) * bar_minutes / 60.0 / 24.0
        s = require_screened(screen_cell(g, label=nombre))
        filas.append({"salida": nombre, "n": len(x), "neto": float(x.mean()),
                      "brecha": brecha, "hold_d": hold_d, "dsr": dsr["dsr"],
                      "dsr_paranoico": dsr_p["dsr"], "screen": s,
                      "lo": lo_, "hi": hi_})
        print("  %-26s %6d %8.2f %+9.4f %+9.4f %+10.4f %8.3f %8.3f%s"
              % (nombre, len(x), hold_d, g.pnl_r.mean(), x.mean(), brecha,
                 dsr["dsr"], dsr_p["dsr"], "" if s["candidato"] else "   no"))

    ctrl = next((f for f in filas if f["salida"].startswith("control")), None)
    print("\n  -- H1 (concurrencia) y H2 (perfil), contra el control --")
    print("  El DD es el de la `f` VIVA (%.2f%%), NO el minimo de la rejilla de"
          % (F_VIVA * 100))
    print("  fracciones: reportar el minimo es reportar el de la mas timida.")
    print("  %-30s %8s %9s %9s %8s %9s"
          % ("salida", "d_hold", "DD@f_viva", "equity", "skew", "Sharpe/tr"))
    for f in filas:
        g = grupos[f["salida"]]
        x = g["net_r"].to_numpy(float)
        x = x[~np.isnan(x)]
        viva = next((r for r in f["screen"]["intentos"]
                     if abs(r["risk_frac"] - F_VIVA) < 1e-12), None)
        f["dd_viva"] = -viva["max_drawdown"] if viva else float("nan")
        f["equity_viva"] = viva["equity_final"] if viva else float("nan")
        f["skew"] = float(pd.Series(x).skew())
        f["sharpe"] = _sharpe(x)
        print("  %-30s %+8.2f %8.1f%% %9.3f %+8.2f %9.4f"
              % (f["salida"], f["hold_d"] - (ctrl["hold_d"] if ctrl else 0.0),
                 f["dd_viva"] * 100, f["equity_viva"], f["skew"], f["sharpe"]))
    return filas, ctrl


def veredicto_exits(filas, ctrl):
    """Las tres hipotesis, contestadas con el criterio fijado ANTES."""
    print("\n" + "-" * 78)
    print("  VEREDICTO — criterio pre-registrado (H3 exige las cuatro cosas)")
    candidatos = [f for f in filas if f["brecha"] <= 0 and f["screen"]["candidato"]
                  and f["dsr"] > 0.95]
    for f in filas:
        if f["salida"].startswith("control"):
            continue
        fallos = []
        if f["brecha"] > 0:
            fallos.append("IC95%% no cruza (falta %+.4fR)" % f["brecha"])
        if not f["screen"]["candidato"]:
            fallos.append(f["screen"]["motivos"][0] if f["screen"]["motivos"]
                          else "cartera")
        if f["dsr"] <= 0.95:
            fallos.append("DSR %.3f <= 0.95" % f["dsr"])
        print("  %-26s %s" % (f["salida"], "PASA" if not fallos
                              else " · ".join(fallos)))
    print()
    if candidatos:
        print("  >> Hay reglas que clarean el criterio literal. NO las llames")
        print("     candidatas todavia: lee los dos avisos de abajo primero.")
    else:
        print("  >> NINGUNA regla de salida clarea el criterio. Al CEMENTERIO")
        print("     con su n, su rejilla y su n_trials.")

    if ctrl:
        mejor = min((f for f in filas if not f["salida"].startswith("control")),
                    key=lambda f: f["brecha"], default=None)
        if mejor:
            print("\n  Mejor regla: %s · brecha %+.4f vs control %+.4f (%s%+.4f)"
                  % (mejor["salida"], mejor["brecha"], ctrl["brecha"],
                     "cierra " if mejor["brecha"] < ctrl["brecha"] else "abre ",
                     ctrl["brecha"] - mejor["brecha"]))
            print("  n IGUAL que el control (%d vs %d) -> la vara NO se movio y"
                  % (mejor["n"], ctrl["n"]))
            print("  toda la diferencia es real. Es lo unico limpio de la tabla.")

        # AVISO 1 — el confundido que se come el titular.
        if ctrl["brecha"] <= 0:
            print("\n  " + "!" * 70)
            print("  AVISO 1 — EL CONTROL YA CRUZA. La regla de salida NO es lo")
            print("  que hace pasar esto. El control (barreras FIJAS) ya tiene")
            print("  brecha %+.4f y DD@f_viva %.1f%%. Lo que cambio frente al"
                  % (ctrl["brecha"], ctrl.get("dd_viva", float("nan")) * 100))
            print("  cementerio NO es la salida: es el UNIVERSO (3 simbolos con")
            print("  velas en vez de los 13 del pool). La concurrencia escala con")
            print("  el numero de simbolos, asi que restringir el universo baja el")
            print("  DD por aritmetica, no por hallazgo.")
            print("  Eso es una afirmacion de SUBCONJUNTO y arrastra su propia")
            print("  carga de multiple-testing (13 simbolos -> 3), ademas de")
            print("  chocar con el CEMENTERIO: 'concentrar en los mejores")
            print("  simbolos - el liderazgo rota; los rezagados ganan OOS'.")
            print("  " + "!" * 70)

        # AVISO 2 — el DSR se cae en cuanto se cuenta de verdad.
        fragiles = [f for f in filas if f["dsr"] > 0.95 and f["dsr_paranoico"] <= 0.95]
        if fragiles:
            print("\n  AVISO 2 — DSR FRAGIL. Estas clarean a n_trials=%d y se caen"
                  % N_TRIALS_SALIDA)
            print("  a la cota paranoica (%d), que es la que cuenta la rejilla de"
                  % N_TRIALS_PARANOICO)
            print("  84 de la que salio la celda:")
            for f in fragiles:
                print("     %-30s DSR %.3f -> %.3f"
                      % (f["salida"], f["dsr"], f["dsr_paranoico"]))
            print("  Ninguna sobrevive a contar los trials de verdad.")
    print("\n  COTA INFERIOR: convencion pesimista intra-vela (el extremo adverso")
    print("  se asume primero). Y sigue sin modelo de fill en la ENTRADA.")
    return candidatos


def run_exits(cube_dir, klines_dir, *, tp="tp4", horizon=288, cost=None,
              symbols=None, celda=CELDA_PRIMARIA, etiqueta="PRIMARIA",
              n_trials=N_TRIALS_SALIDA):
    cube = load_pool(cube_dir)
    ev_all = cell_events(cube, tp=tp, horizon=horizon)
    if symbols:
        ev_all = ev_all[ev_all.symbol.isin(symbols)]
    trozos = []
    for sym, ev in ev_all.groupby("symbol"):
        kl = load_klines(klines_dir, sym)
        if kl is None or kl.empty:
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
        trozos.append(relabel_exits(ev, kl, pos, sym, celda=celda))
    if not trozos:
        print("\n  Ningun simbolo paso el gate de venue. Sin medicion.")
        return None
    filas, ctrl = report_exits(pd.concat(trozos, ignore_index=True),
                               cost or CostModel(), celda=celda,
                               etiqueta=etiqueta, n_trials=n_trials)
    return veredicto_exits(filas, ctrl), filas


def run(cube_dir, klines_dir, *, tp="tp4", horizon=288, cost=None, symbols=None,
        sl_mults=SL_MULTS, tp_rs=TP_RS, horizons=HORIZONS):
    cube = load_pool(cube_dir)
    ev_all = cell_events(cube, tp=tp, horizon=horizon)
    if symbols:
        ev_all = ev_all[ev_all.symbol.isin(symbols)]
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
        trozos.append(relabel(ev, kl, pos, sl_mults=sl_mults, tp_rs=tp_rs,
                              horizons=horizons))
    if not trozos:
        print("\n  Ningun simbolo paso el gate de venue. Sin medicion.")
        return None
    return report(pd.concat(trozos, ignore_index=True), cost or CostModel())


def main(argv=None):
    ap = argparse.ArgumentParser(description="¿Un stop mas ancho salva el neto?")
    ap.add_argument("--cube", default="cosecha_cubes/")
    ap.add_argument("--klines", default="data/binance")
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--exits", action="store_true",
                    help="barrer el EJE DE SALIDA sobre la celda pre-fijada "
                         "(internal/BRIEF_SALIDA_2026-08.md)")
    ap.add_argument("--vip", action="store_true",
                    help="restringir al universo que difunde el bot")
    ap.add_argument("--replica", action="store_true",
                    help="ademas, la celda replica declarada (n_trials x2)")
    a = ap.parse_args(argv)

    syms = a.symbols.split(",") if a.symbols else None
    if a.vip and not syms:
        syms = ["%s_USDT" % s for s in sorted(vip_universe())]

    print("=== GATE DE VENUE (cubos de OKX; velas de Binance) ===")
    if a.exits:
        out = run_exits(a.cube, a.klines, symbols=syms)
        if out is not None and a.replica:
            print("\n\n" + "#" * 78)
            print("  REPLICA DECLARADA — n_trials sube a %d, y se dice"
                  % (2 * N_TRIALS_SALIDA))
            print("#" * 78)
            run_exits(a.cube, a.klines, symbols=syms, celda=CELDA_REPLICA,
                      etiqueta="REPLICA", n_trials=2 * N_TRIALS_SALIDA)
        return 0 if out is not None else 1
    out = run(a.cube, a.klines, symbols=syms)
    return 0 if out is not None else 1


if __name__ == "__main__":
    sys.exit(main())
