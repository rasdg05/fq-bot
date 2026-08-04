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
from bt_labeler import label_event_grid                           # noqa: E402
from cube_report import cell_events, load_pool                    # noqa: E402
from fill_quality import align, load_klines, recompute_excursion, validate_venue  # noqa: E402
from validation_gate import _sharpe, deflated_from_trials         # noqa: E402

MIN_N = 30
# La rejilla llega hasta kSL=12 a proposito: con (1..5) el maximo caia en la
# ESQUINA, que es la señal clasica de que el optimo esta fuera del rango probado
# y de que se esta extrapolando. Extendida, el gradiente GIRA (kSL 5 -> 8 -> 12
# empeora), o sea que hay optimo interior y no una deriva hacia comprar-y-esperar.
SL_MULTS = (1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 12.0)
TP_RS = (1.0, 2.0, 3.0, 4.0, 6.0, 10.0)
HORIZONS = (576, 1152)


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
    a = ap.parse_args(argv)
    print("=== GATE DE VENUE (cubos de OKX; velas de Binance) ===")
    out = run(a.cube, a.klines,
              symbols=a.symbols.split(",") if a.symbols else None)
    return 0 if out is not None else 1


if __name__ == "__main__":
    sys.exit(main())
