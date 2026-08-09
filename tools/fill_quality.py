# -*- coding: utf-8 -*-
"""
================================================================================
  FILL QUALITY — la pregunta que decide si esto es viable
================================================================================

E8 midió que el edge bruto del cube (+0.2305R) no sobrevive a los costes taker
(neto −0.0258R). Y midió que con entrada MAKER el signo se voltea: +0.060R,
IC95% [+0.024, +0.096], P(>0)=0.998.

Pero ese escenario asume **fill del 100%** en el nivel, y este repo ya midió que
esa suposición es falsa en la dirección optimista: los maker rápidos pierden el
80% del R (selección adversa — tu orden se llena porque el precio la está
atravesando). El error de la suposición es MÁS GRANDE que todo el margen.

Así que toda la diferencia entre rentable y no rentable está en una sola
pregunta, y es empírica:

    de las órdenes límite que el backtest asume llenas,
    ¿cuántas se llenan de verdad, y son las buenas o las malas?

Esto la contesta sobre las 13.429 señales, no sobre las 53 del ledger vivo.

Cómo
----
`bt_engine.maker_entry_fill_mask` ya define la regla de fill (una límite en el
nivel se llena solo si una vela POSTERIOR lo PENETRA más allá de `eps`; un toque
no llena). Aquí se aplica esa misma función a cada señal del cube contra las
velas reales, y se mide:

  1. FILL RATE — qué fracción se llena dentro del TTL.
  2. SELECCIÓN ADVERSA — E[R] de las llenadas vs las que se escaparon. Es EL
     número: si las que se llenan son sistemáticamente las perdedoras, el
     +0.060R teórico de E8 no existe.
  3. R POR BARRAS DE ESPERA — la versión con n grande del hallazgo de agosto
     (fills ≤2 barras: n=53, WR 11%, 80% de la pérdida).
  4. NETO — el CostModel maker aplicado SOLO al subconjunto que se llena.

El problema del venue, y por qué no se ignora
---------------------------------------------
Los cubos se cosecharon de **OKX**; OKX bloquea desde datacenter (403), así que
las velas vienen de **Binance Vision**. Un desajuste de precio entre venues cae
justo en la escala que esto mide (eps = 1 bp), y una medición de fill hecha
sobre velas del venue equivocado no vale nada.

Por eso `validate_venue()` corre PRIMERO y es un gate, no una nota: recomputa
MFE/MAE desde las velas de Binance sobre el mismo horizonte y las compara con
las que el cube trae de OKX. Si las dos series no concuerdan, la medición se
declara inválida y no se imprime ningún fill rate. Un número de fill sobre datos
que no casan sería peor que no medir: parecería una respuesta.

Uso:
    python tools/fill_quality.py --klines data/binance --cube cosecha_cubes/
================================================================================
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

from bt_engine import (CostModel, MakerFillAssumedError,       # noqa: E402
                       maker_entry_fill_mask, maker_expectancy,
                       maker_fill_probability, require_fill_modeled, simulate)
from cube_report import cell_events, load_pool                     # noqa: E402

BAR_MS = 300_000          # 5m
MIN_N = 30

# La rejilla de cola (V2). `queue_frac` = cuánta cola tiene por delante la orden,
# medida en múltiplos del volumen MEDIANO de barra del propio símbolo.
#
# El 0.0 no es relleno: es la binaria. Con cola cero, cualquier flujo más allá de
# eps llena con p=1 y el modelo COLAPSA exactamente en `maker_entry_fill_mask`.
# O sea que la regla que este repo usó hasta hoy es la ESQUINA MÁS OPTIMISTA de
# esta curva — la de estar siempre el primero de la cola. Verlo en la misma tabla
# es medio hallazgo.
QUEUE_GRID = (0.0, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0)
# El punto que se cita cuando hay que citar uno. No sale de una medición de libro
# (este repo no tiene L2): sale de elegir el centro de la rejilla y decirlo. Por
# eso el informe imprime la CURVA entera y el veredicto se lee de la curva.
DEFAULT_QUEUE_FRAC = 0.25

# Acuerdo mínimo entre venues para que la medición sea legible. La correlación
# de la excursión es el juez: si Binance y OKX contaran historias distintas
# sobre lo que hizo el precio, el fill medido sobre Binance no describiría la
# señal de OKX.
VENUE_MIN_CORR = 0.95
VENUE_MAX_MED_ABS_DIFF_R = 0.25    # en R, mediana de |ΔMFE| y |ΔMAE|


def load_klines(klines_dir, symbol, interval="5m"):
    """Velas de un símbolo del cube ('SOL_USDT' -> kl_hist_SOLUSDT.parquet).

    `volume` y `taker_buy_base` son OPCIONALES en disco y obligatorios para el
    modelo de cola: sin ellos no hay flujo que medir y la P(fill) cae al modo
    profundidad. Se piden aparte para que un parquet viejo (solo OHLC) siga
    sirviendo para la binaria en vez de romper el informe entero.

    `interval` distinto de 5m lee el parquet con sufijo. El 5m conserva el
    nombre historico a proposito: cualquier otra cosa invalidaria en silencio
    todas las cifras ya publicadas del repo.
    """
    sym = symbol.replace("_", "")
    nombre = ("kl_hist_%s.parquet" % sym if interval == "5m"
              else "kl_hist_%s_%s.parquet" % (sym, interval))
    path = os.path.join(klines_dir, nombre)
    if not os.path.exists(path):
        return None
    cols = ["ts", "high", "low", "close"]
    try:
        df = pd.read_parquet(path, columns=cols + ["volume", "taker_buy_base"])
    except Exception:
        df = pd.read_parquet(path, columns=cols)
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


def align(events, kl):
    """Posición de cada señal en las velas, por TIMESTAMP (no por índice).

    El `entry_index` del cube es posicional sobre el dataframe de OKX con el que
    se cosechó; sobre otro dataframe no significa nada. El `entry_ts` sí es
    absoluto. Devuelve el índice de la vela cuya apertura coincide, o -1.
    """
    # OJO con la unidad: el cube trae `entry_ts` como datetime64[ms], y sobre
    # esa dtype `.astype("int64")` YA devuelve milisegundos. Normalizar a ns
    # primero es lo que hace la conversión independiente de la unidad de origen
    # -- sin esto la alineación da 0 coincidencias en silencio.
    ts = (pd.to_datetime(events["entry_ts"]).astype("datetime64[ns]")
          .astype("int64") // 10**6)
    pos = kl["ts"].searchsorted(ts.to_numpy(), side="left")
    pos = np.clip(pos, 0, len(kl) - 1)
    ok = kl["ts"].to_numpy()[pos] == ts.to_numpy()
    return np.where(ok, pos, -1)


def recompute_excursion(events, kl, pos, horizon):
    """MFE/MAE en R desde las velas locales, sobre el mismo horizonte del cube.

    Es la piedra de toque del venue: el cube trae estos mismos números medidos
    en OKX. Si concuerdan, las dos series describen el mismo mercado.
    """
    hi, lo = kl["high"].to_numpy(), kl["low"].to_numpy()
    n = len(kl)
    entry = events["entry_price"].to_numpy(float)
    stop = events["stop_price"].to_numpy(float)
    d = events["direction"].to_numpy(int)
    risk = np.abs(entry - stop)
    mfe = np.full(len(events), np.nan)
    mae = np.full(len(events), np.nan)
    for i in range(len(events)):
        p = pos[i]
        if p < 0 or risk[i] <= 0:
            continue
        a, b = p + 1, min(p + 1 + horizon, n)
        if a >= b:
            continue
        fav = hi[a:b] if d[i] > 0 else lo[a:b]
        adv = lo[a:b] if d[i] > 0 else hi[a:b]
        mfe[i] = max(0.0, d[i] * ((fav.max() if d[i] > 0 else fav.min()) - entry[i]) / risk[i])
        mae[i] = min(0.0, d[i] * ((adv.min() if d[i] > 0 else adv.max()) - entry[i]) / risk[i])
    return mfe, mae


def validate_venue(events, mfe_local, mae_local):
    """GATE: ¿las velas locales cuentan la misma historia que el cube?

    Devuelve (ok, informe). Si no pasa, el llamador NO debe imprimir fill rates:
    un número de fill sobre datos que no casan parecería una respuesta.
    """
    m = ~np.isnan(mfe_local)
    rep = {"n_alineadas": int(m.sum()), "n_total": len(events)}
    if m.sum() < MIN_N:
        rep["motivo"] = "solo %d señales alineadas por timestamp" % m.sum()
        return False, rep
    a_mfe, b_mfe = events["mfe_r"].to_numpy(float)[m], mfe_local[m]
    a_mae, b_mae = events["mae_r"].to_numpy(float)[m], mae_local[m]
    # Una serie sin varianza hace la correlacion indefinida (NaN). NaN >= umbral
    # es False, o sea que el gate ya fallaria cerrado — pero enseñando un NaN en
    # vez del motivo. Se declara explicito: sin dispersion no hay nada que
    # correlacionar y la comparacion de venues no significa nada.
    if min(np.std(a_mfe), np.std(b_mfe), np.std(a_mae), np.std(b_mae)) < 1e-9:
        rep["motivo"] = ("la excursion no tiene dispersion (serie constante): no "
                         "hay nada que correlacionar entre venues")
        return False, rep
    rep["corr_mfe"] = float(np.corrcoef(a_mfe, b_mfe)[0, 1])
    rep["corr_mae"] = float(np.corrcoef(a_mae, b_mae)[0, 1])
    rep["med_abs_dif_mfe"] = float(np.median(np.abs(a_mfe - b_mfe)))
    rep["med_abs_dif_mae"] = float(np.median(np.abs(a_mae - b_mae)))
    rep["cobertura"] = float(m.sum()) / len(events)
    ok = (rep["corr_mfe"] >= VENUE_MIN_CORR and rep["corr_mae"] >= VENUE_MIN_CORR
          and rep["med_abs_dif_mfe"] <= VENUE_MAX_MED_ABS_DIFF_R
          and rep["med_abs_dif_mae"] <= VENUE_MAX_MED_ABS_DIFF_R)
    if not ok:
        rep["motivo"] = ("las velas locales no reproducen la excursión del cube "
                         "(corr MFE %.3f / MAE %.3f, |Δ| mediana %.2fR / %.2fR)"
                         % (rep["corr_mfe"], rep["corr_mae"],
                            rep["med_abs_dif_mfe"], rep["med_abs_dif_mae"]))
    return ok, rep


def measure_fills(events, kl, pos, *, eps, ttl_bars):
    """(lleno, barras_esperadas) por señal, con la MISMA regla que el backtest.

    Reutiliza `bt_engine.maker_entry_fill_mask` para el veredicto de fill: si la
    regla viviera dos veces, forward y backtest podrían divergir sin que nadie
    lo notara. Aquí solo se añade CUÁNDO se llenó, que es lo que permite el
    corte por barras de espera.
    """
    hi, lo = kl["high"].to_numpy(float), kl["low"].to_numpy(float)
    ev = events.copy()
    ev["entry_index"] = pos
    lleno = maker_entry_fill_mask(ev, hi, lo, eps=eps, ttl_bars=ttl_bars)
    lleno = np.asarray(lleno) & (pos >= 0)

    entry = ev["entry_price"].to_numpy(float)
    d = ev["direction"].to_numpy(int)
    espera = np.full(len(ev), -1)
    for i in np.flatnonzero(lleno):
        a, b = pos[i] + 1, min(pos[i] + ttl_bars, len(kl) - 1)
        for k in range(a, b + 1):
            cruza = (lo[k] < entry[i] * (1 - eps)) if d[i] > 0 \
                else (hi[k] > entry[i] * (1 + eps))
            if cruza:
                espera[i] = k - pos[i]
                break
    return lleno, espera


def queue_probabilities(events, kl, pos, *, eps, ttl_bars, grid=QUEUE_GRID):
    """P(fill) por señal para cada cola de la rejilla. dict {queue_frac: ndarray}.

    El elemento `0.0` se calcula con `maker_entry_fill_mask`, no con el modelo:
    con cola cero el modelo colapsa en la binaria por construcción, y hacerlo
    con la función de verdad convierte esa afirmación en algo que el informe
    COMPRUEBA cada vez que corre, en vez de algo que dice el docstring.
    """
    ev = events.copy()
    ev["entry_index"] = pos
    hi, lo = kl["high"].to_numpy(float), kl["low"].to_numpy(float)
    vol = kl["volume"].to_numpy(float) if "volume" in kl.columns else None
    tb = kl["taker_buy_base"].to_numpy(float) if "taker_buy_base" in kl.columns else None
    out = {}
    for q in grid:
        if q <= 0:
            out[q] = maker_entry_fill_mask(ev, hi, lo, eps=eps,
                                           ttl_bars=ttl_bars).astype(float)
        elif vol is None:
            # Sin volumen no hay flujo: la cola se mide en bps de penetración
            # acumulada. Peor modelo, y por eso el informe lo dice al imprimir.
            out[q] = maker_fill_probability(ev, hi, lo, eps=eps, ttl_bars=ttl_bars,
                                            queue_bps=q)
        else:
            out[q] = maker_fill_probability(ev, hi, lo, eps=eps, ttl_bars=ttl_bars,
                                            queue_frac=q, volume=vol, taker_buy=tb)
        out[q] = np.where(pos >= 0, out[q], 0.0)
    return out


def _agg(x):
    x = np.asarray(x, float)
    if not len(x):
        return "n=0"
    return "n=%5d  E[R]=%+.3f  WR=%4.1f%%" % (
        len(x), x.mean(), (x > 0).mean() * 100)


def _boot(x, reps=2000, seed=7):
    x = np.asarray(x, float)
    if len(x) < 2:
        return (float("nan"),) * 3
    rng = np.random.default_rng(seed)
    m = np.array([x[rng.integers(0, len(x), len(x))].mean() for _ in range(reps)])
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)), float((m > 0).mean())


def report_cola(ev, probs, *, col="net_pnl_r"):
    """V2 — la curva de la cola: ¿cuánto del maker sobrevive a NO ser el primero?

    La binaria contesta "¿el precio llegó?". Esta tabla contesta "¿y dónde estaba
    mi orden cuando llegó?", que es la pregunta que separa un backtest de una
    ejecución. Se lee de arriba abajo: la fila `0.00` es la regla que este repo
    usó hasta hoy — la esquina de estar SIEMPRE el primero de la cola.

    El mecanismo que hay que ver, y que la binaria no puede ver: una cola por
    delante no filtra al azar. Filtra por PENETRACIÓN — te quedas con las señales
    en las que el precio te atravesó del todo, que son justo las que la selección
    adversa ya señaló como perdedoras (−1.039R medido en agosto). Más cola no es
    "menos muestra": es muestra sesgada hacia lo peor.
    """
    if not probs:
        return None
    print("\n=== 6. POSICIÓN EN COLA (V2) — el fill deja de ser binario ===")
    print("  queue_frac = cola por delante en múltiplos del volumen MEDIANO de")
    print("  barra del símbolo, consumida por el flujo FIRMADO que imprimió en el")
    print("  nivel o más allá (a una BID la consume el taker SELL, no el volumen")
    print("  total). Reparto uniforme dentro de la vela: aproximación declarada.")
    print("\n  %-10s %9s %9s %11s %22s %8s" % (
        "queue_frac", "fill", "n_esperada", "E[R] neto", "IC95%", "P(>0)"))
    filas = []
    for q in sorted(probs):
        res = maker_expectancy(ev.assign(fill_p=probs[q]), col=col)
        require_fill_modeled(res)
        res["queue_frac"] = q
        filas.append(res)
        flaco = "  <- n<%d" % MIN_N if res["n_esperada"] < MIN_N else ""
        print("  %-10.2f %8.1f%% %10.0f %+11.4f  [%+8.4f,%+8.4f] %7.3f%s"
              % (q, res["fill_rate"] * 100, res["n_esperada"], res["expectancy"],
                 res["lo"], res["hi"], res["p_pos"], flaco))
    print("  (la fila 0.00 ES `maker_entry_fill_mask`: cola cero = siempre el")
    print("   primero. Todo lo de debajo es lo que cuesta no serlo.)")

    utiles = [f for f in filas if f["n_esperada"] >= MIN_N]
    if len(utiles) >= 2:
        base, peor = utiles[0], utiles[-1]
        delta = peor["expectancy"] - base["expectancy"]
        print("\n  -- lo que cuesta la cola --")
        print("  de queue_frac %.2f a %.2f: %+.4fR -> %+.4fR  (%+.4fR)"
              % (base["queue_frac"], peor["queue_frac"], base["expectancy"],
                 peor["expectancy"], delta))
        if delta < -0.01:
            print("  >> LA COLA COBRA. El E[R] baja al retrasar la orden: no es")
            print("     ruido de muestra, es el mecanismo de la selección adversa")
            print("     — cuanto más atrás estás, más te llenas SOLO cuando el")
            print("     precio te atraviesa. El fill binario cobraba de más.")
        elif delta > 0.01:
            print("  >> LA COLA NO COBRA en esta muestra: retrasar la orden no")
            print("     empeora el E[R]. Míralo dos veces antes de creerlo — es")
            print("     lo contrario de lo que dice la selección adversa medida.")
        else:
            print("  >> NEUTRA: la cola no mueve el E[R] de forma legible.")

    _gradiente_de_fill(ev, probs, col=col)

    vivos = [f for f in utiles if f["lo"] > 0]
    print("\n  -- veredicto --")
    if vivos:
        print("  Colas con el IC95%% ENTERO sobre cero: %s"
              % ", ".join("%.2f" % f["queue_frac"] for f in vivos))
        print("  Necesario, no suficiente: pásalo por el gate (DSR/CPCV/PBO).")
    else:
        print("  NINGUNA cola tiene el IC95% entero sobre cero — tampoco la 0.00,")
        print("  que es el mejor caso imaginable. El maker no se salva por")
        print("  ejecución: no hay dónde ponerse en la cola que lo arregle.")
    return filas


def _gradiente_de_fill(ev, probs, *, col="net_pnl_r", q=None):
    """¿La P(fill) PREDICE el resultado? Es la prueba del mecanismo, no del número.

    Una curva que baja al meter cola podría ser puro encogimiento de muestra. Lo
    que la convierte en un mecanismo es esto: ordenar las señales por su
    probabilidad de llenarse y ver el neto caer. Si las que se llenan seguro son
    las peores, entonces "estar más atrás en la cola" no te quita señales al
    azar — te deja EXACTAMENTE las que no querías.
    """
    if q is None:
        candidatas = [k for k in probs if k > 0]
        if not candidatas:
            return None
        q = sorted(candidatas)[len(candidatas) // 2]
    p, r = np.asarray(probs[q], float), ev[col].to_numpy(float)
    vivo = (np.asarray(probs[min(probs)], float) > 0) & ~np.isnan(r)
    if vivo.sum() < MIN_N:
        return None
    p, r = p[vivo], r[vivo]
    print("\n  -- el mecanismo: ¿la P(fill) predice el resultado? (queue_frac %.2f) --" % q)
    print("     sobre las %d que la binaria da por llenas" % vivo.sum())
    cortes = ((0.0, 0.25), (0.25, 0.50), (0.50, 0.75), (0.75, 1.0), (1.0, 1.01))
    for lo_b, hi_b in cortes:
        m = (p >= lo_b) & (p < hi_b)
        if m.sum() < MIN_N:
            print("     p %.2f-%.2f  n=%5d   <- n<%d" % (lo_b, min(hi_b, 1.0), m.sum(), MIN_N))
            continue
        print("     p %.2f-%.2f  n=%5d  NETO %+.4f" % (lo_b, min(hi_b, 1.0),
                                                       m.sum(), r[m].mean()))
    corr = float(np.corrcoef(p, r)[0, 1]) if np.std(p) > 1e-12 else float("nan")
    print("     corr(P(fill), R neto) = %+.4f" % corr)
    if corr < -0.05:
        print("     >> La orden que MÁS seguro se llena es la que PEOR sale. La")
        print("        cola no te quita señales al azar: te deja las que el")
        print("        precio atravesó. Selección adversa, medida por el fill.")
    return corr


def techo_asumido(ev, *, col="net_pnl_r"):
    """El número de E8 (+0.060R) reconstruido, y marcado como lo que es.

    Se imprime a propósito, y a propósito NO pasa por `maker_expectancy`: esa
    función levanta ante `asumido_100`. Aquí se calcula a mano y se etiqueta
    TECHO para que quede al lado de la curva y se vea la distancia. Un techo
    sirve de cota; lo que no puede es viajar sin la etiqueta.
    """
    x = ev[col].to_numpy(float)
    x = x[~np.isnan(x)]
    if len(x) < MIN_N:
        return None
    print("\n  -- el techo, etiquetado --")
    print("  fill 100%% asumido: n=%d  E[R] %+.4f   <- TECHO, NO publicable como"
          % (len(x), x.mean()))
    print("     resultado (bt_engine.MakerFillAssumedError lo impide). Es la")
    print("     cifra que en agosto dijo +0.060R y el fill real dejó en −0.0350R.")
    return float(x.mean())


def report(ev, lleno, espera, *, eps, ttl_bars, probs=None):
    r = ev["pnl_r"].to_numpy(float)
    neto = ev["net_pnl_r"].to_numpy(float) if "net_pnl_r" in ev.columns else None
    n = len(ev)
    print("\n" + "=" * 72)
    print("  CALIDAD DE FILL — %d señales · eps=%.1f bps · TTL=%d barras" % (
        n, eps * 10_000, ttl_bars))
    print("=" * 72)

    print("\n=== 1. ¿CUÁNTAS SE LLENAN? ===")
    print("  llenadas %d de %d = %.1f%%" % (lleno.sum(), n, 100.0 * lleno.mean()))
    print("  El backtest maker de E8 asumía el 100%. Todo lo que falte de ahí")
    print("  es edge que el papel cobra y la orden real no.")

    print("\n=== 2. SELECCIÓN ADVERSA — el número que decide ===")
    print("  llenadas   %s" % _agg(r[lleno]))
    print("  escapadas  %s" % _agg(r[~lleno]))
    if lleno.sum() >= MIN_N and (~lleno).sum() >= MIN_N:
        dif = r[lleno].mean() - r[~lleno].mean()
        lo_, hi_, p = _boot(r[lleno])
        print("  diferencia %+.3fR  (llenadas − escapadas)" % dif)
        print("  IC95%% del bruto de las llenadas [%+.3f, %+.3f]  P(>0)=%.3f"
              % (lo_, hi_, p))
        if dif < -0.05:
            print("  >> SELECCIÓN ADVERSA CONFIRMADA: la límite se llena en las")
            print("     PEORES. El precio te atraviesa porque va en tu contra.")
        elif dif > 0.05:
            print("  >> A FAVOR: las que se llenan son mejores que las que se")
            print("     escapan. Poco común; míralo dos veces antes de creerlo.")
        else:
            print("  >> NEUTRA: llenarse no predice el desenlace. El fill no")
            print("     regala edge, pero tampoco lo roba.")

    print("\n=== 3. R POR BARRAS DE ESPERA (n grande del hallazgo de agosto) ===")
    print("  el ledger vivo vio: fills ≤2 barras n=53, WR 11%, 80% de la pérdida")
    for lo_b, hi_b, lab in ((1, 1, "1 barra"), (2, 2, "2 barras"),
                            (3, 4, "3-4 barras"), (5, 999, "5+ barras")):
        m = lleno & (espera >= lo_b) & (espera <= hi_b)
        nota = "" if m.sum() >= MIN_N else "   <- n<%d" % MIN_N
        print("    %-12s %s%s" % (lab, _agg(r[m]), nota))

    if neto is not None:
        print("\n=== 4. NETO POR BARRAS DE ESPERA — el juez de FQ_MOTOR_MIN_FILL_BARS ===")
        print("  El gate de produccion (default 2) DESCARTA los fills de 1 barra,")
        print("  por el hallazgo de agosto sobre n=53. Esto lo remide sobre n grande.")
        for lo_b, hi_b, lab in ((1, 1, "1 barra"), (2, 2, "2 barras"),
                                (3, 4, "3-4 barras"), (5, 999, "5+ barras")):
            m = lleno & (espera >= lo_b) & (espera <= hi_b)
            if m.sum() < MIN_N:
                print("    %-12s n=%d  <- n<%d" % (lab, m.sum(), MIN_N))
                continue
            lo_c, hi_c, _ = _boot(neto[m])
            print("    %-12s n=%5d  NETO %+.4f  IC95%%[%+.4f, %+.4f]"
                  % (lab, m.sum(), neto[m].mean(), lo_c, hi_c))
        con_gate = lleno & (espera >= 2)
        if con_gate.sum() >= MIN_N and lleno.sum() >= MIN_N:
            print("  -- el gate, aplicado --")
            for lab, m in (("sin gate (todo lo que llena)", lleno),
                           ("con gate >=2 barras", con_gate)):
                lo_c, hi_c, _ = _boot(neto[m])
                print("    %-30s n=%5d  NETO %+.4f  IC95%%[%+.4f, %+.4f]"
                      % (lab, m.sum(), neto[m].mean(), lo_c, hi_c))
            if neto[con_gate].mean() < neto[lleno].mean():
                print("  >> El gate EMPEORA el neto en esta muestra: descarta el bucket")
                print("     menos malo y se queda con los peores. El hallazgo de n=53")
                print("     no replica. NO es orden de apagarlo — es orden de remedirlo")
                print("     antes de seguir confiando en el (geometria distinta: el cube")
                print("     es tp4/h288, el motor vivo tp1 con TTL).")

        print("\n=== 5. NETO MAKER, SOLO SOBRE LO QUE SE LLENA ===")
        x = neto[lleno]
        if len(x) >= MIN_N:
            lo_, hi_, p = _boot(x)
            print("  %s" % _agg(x))
            print("  neto medio %+.4fR  IC95%%[%+.4f, %+.4f]  P(E[R]>0)=%.3f"
                  % (x.mean(), lo_, hi_, p))
            print("  (E8 con fill 100%% asumido daba +0.0601R IC95%%[+0.0235,+0.0958])")
            if lo_ > 0:
                print("\n  >> SOBREVIVE. Es la primera configuración medida de este")
                print("     repo con el IC95%% por encima de cero. Verifícala con el")
                print("     gate (DSR/CPCV/PBO) antes de creerla del todo.")
            else:
                print("\n  >> NO SOBREVIVE. El IC95%% cruza cero: el margen teórico")
                print("     de E8 se lo come el fill real.")

    if neto is not None and probs:
        report_cola(ev, probs)
        techo_asumido(ev)

    print("\n  Cota superior aún: el fill se juzga con la vela, y dentro de la")
    print("  vela no se conoce la cola de la orden%s. Lo realizable está por"
          % (" al tick" if probs else ""))
    print("  debajo de esto, nunca por encima.")


def _pcol(q):
    return "_p_%.4f" % q


def run(cube_dir, klines_dir, *, tp="tp4", horizon=288, eps_bps=1.0, ttl_bars=6,
        cost=None, symbols=None, queue_grid=QUEUE_GRID,
        queue_frac=DEFAULT_QUEUE_FRAC):
    cube = load_pool(cube_dir)
    ev_all = cell_events(cube, tp=tp, horizon=horizon)
    if symbols:
        ev_all = ev_all[ev_all.symbol.isin(symbols)]
    eps = eps_bps / 10_000.0

    trozos, rechazados = [], []
    for sym, ev in ev_all.groupby("symbol"):
        kl = load_klines(klines_dir, sym)
        if kl is None or kl.empty:
            rechazados.append((sym, "sin velas locales"))
            continue
        ev = ev.reset_index(drop=True)
        pos = align(ev, kl)
        mfe_l, mae_l = recompute_excursion(ev, kl, pos, horizon)
        ok, rep = validate_venue(ev, mfe_l, mae_l)
        print("  [venue] %-10s alineadas %5d/%5d (%.0f%%)  corr MFE %.3f MAE %.3f  %s"
              % (sym, rep.get("n_alineadas", 0), rep["n_total"],
                 100 * rep.get("cobertura", 0), rep.get("corr_mfe", float("nan")),
                 rep.get("corr_mae", float("nan")), "OK" if ok else "RECHAZADO"))
        if not ok:
            rechazados.append((sym, rep.get("motivo", "?")))
            continue
        m = pos >= 0
        ev, pos = ev[m].reset_index(drop=True), pos[m]
        lleno, espera = measure_fills(ev, kl, pos, eps=eps, ttl_bars=ttl_bars)
        ev = ev.assign(_lleno=lleno, _espera=espera)
        # El modelo de cola se calibra POR SÍMBOLO (el volumen mediano de barra
        # de BTC y el de SOL no son el mismo número ni de lejos); por eso la
        # rejilla se evalúa aquí dentro y no sobre el concatenado.
        pq = queue_probabilities(ev, kl, pos, eps=eps, ttl_bars=ttl_bars,
                                 grid=queue_grid)
        ev = ev.assign(**{_pcol(q): v for q, v in pq.items()})
        trozos.append(ev)

    if rechazados:
        print("\n  Fuera de la medición: %s" % ", ".join(
            "%s (%s)" % (s, m) for s, m in rechazados))
    if not trozos:
        print("\n  Ningún símbolo pasó el gate de venue. Sin medición.")
        return None

    ev = pd.concat(trozos, ignore_index=True)
    # Neto MAKER: entrada límite (sin slippage, fee maker) + TP maker.
    maker = cost or CostModel(maker_entry=True, maker_tp_exit=True)
    # `fill_p` viaja HASTA simulate a propósito: es lo que hace que las filas
    # salgan marcadas `modelado` en vez de `asumido_100`. Sin esa columna, el
    # mismo cálculo sale marcado como techo y `maker_expectancy` se niega a
    # publicarlo — que es exactamente la invariante que V2 tenía que dejar.
    ev = ev.assign(direction=ev.direction.astype(int))
    if _pcol(queue_frac) in ev.columns:
        ev = ev.assign(fill_p=ev[_pcol(queue_frac)])
    ev = simulate(ev, equity0=1e9, risk_frac=1e-6, bar_minutes=5.0,
                  cost=maker, stop_on_ruin=False)["trades"]
    probs = {q: ev[_pcol(q)].to_numpy(float) for q in queue_grid
             if _pcol(q) in ev.columns}
    report(ev, ev["_lleno"].to_numpy(bool), ev["_espera"].to_numpy(int),
           eps=eps, ttl_bars=ttl_bars, probs=probs)
    return ev


def main(argv=None):
    ap = argparse.ArgumentParser(description="¿Se llenan de verdad las límites?")
    ap.add_argument("--cube", default="cosecha_cubes/")
    ap.add_argument("--klines", default="data/binance")
    ap.add_argument("--tp", default="tp4")
    ap.add_argument("--horizon", type=int, default=288)
    ap.add_argument("--eps-bps", type=float, default=1.0)
    ap.add_argument("--ttl-bars", type=int, default=6)
    ap.add_argument("--symbols", default=None, help="coma-separados, p.ej. SOL_USDT,BTC_USDT")
    ap.add_argument("--queue-frac", type=float, default=DEFAULT_QUEUE_FRAC,
                    help="cola por delante (múltiplos del volumen mediano de barra)")
    ap.add_argument("--queue-grid", default=",".join("%g" % q for q in QUEUE_GRID),
                    help="rejilla de colas a barrer; 0 = la binaria de siempre")
    a = ap.parse_args(argv)
    syms = a.symbols.split(",") if a.symbols else None
    grid = tuple(sorted(float(x) for x in a.queue_grid.split(",") if x.strip()))
    print("=== GATE DE VENUE (los cubos son de OKX; las velas, de Binance) ===")
    out = run(a.cube, a.klines, tp=a.tp, horizon=a.horizon, eps_bps=a.eps_bps,
              ttl_bars=a.ttl_bars, symbols=syms, queue_grid=grid,
              queue_frac=a.queue_frac)
    return 0 if out is not None else 1


if __name__ == "__main__":
    sys.exit(main())
