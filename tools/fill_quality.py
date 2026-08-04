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

from bt_engine import CostModel, maker_entry_fill_mask, simulate   # noqa: E402
from cube_report import cell_events, load_pool                     # noqa: E402

BAR_MS = 300_000          # 5m
MIN_N = 30

# Acuerdo mínimo entre venues para que la medición sea legible. La correlación
# de la excursión es el juez: si Binance y OKX contaran historias distintas
# sobre lo que hizo el precio, el fill medido sobre Binance no describiría la
# señal de OKX.
VENUE_MIN_CORR = 0.95
VENUE_MAX_MED_ABS_DIFF_R = 0.25    # en R, mediana de |ΔMFE| y |ΔMAE|


def load_klines(klines_dir, symbol):
    """Velas 5m de un símbolo del cube ('SOL_USDT' -> kl_hist_SOLUSDT.parquet)."""
    sym = symbol.replace("_", "")
    path = os.path.join(klines_dir, "kl_hist_%s.parquet" % sym)
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path, columns=["ts", "high", "low", "close"])
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


def report(ev, lleno, espera, *, eps, ttl_bars):
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
    print("\n  Cota superior aún: el fill se juzga con la vela, y dentro de la")
    print("  vela no se conoce la cola de la orden. Lo realizable está por")
    print("  debajo de esto, nunca por encima.")


def run(cube_dir, klines_dir, *, tp="tp4", horizon=288, eps_bps=1.0, ttl_bars=6,
        cost=None, symbols=None):
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
    ev = simulate(ev.assign(direction=ev.direction.astype(int)),
                  equity0=1e9, risk_frac=1e-6, bar_minutes=5.0,
                  cost=maker, stop_on_ruin=False)["trades"]
    report(ev, ev["_lleno"].to_numpy(bool), ev["_espera"].to_numpy(int),
           eps=eps, ttl_bars=ttl_bars)
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
    a = ap.parse_args(argv)
    syms = a.symbols.split(",") if a.symbols else None
    print("=== GATE DE VENUE (los cubos son de OKX; las velas, de Binance) ===")
    out = run(a.cube, a.klines, tp=a.tp, horizon=a.horizon, eps_bps=a.eps_bps,
              ttl_bars=a.ttl_bars, symbols=syms)
    return 0 if out is not None else 1


if __name__ == "__main__":
    sys.exit(main())
