#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cube_net_expectancy — E8 paso 1: el cube CON costes, para que backtest y forward
hablen en las mismas unidades.

LA BRECHA. El cube dice +0,224R bruto. El motor paper con fees dice −0,510R. Ese
hueco es la pregunta abierta 6 del GHOST_MAP. Aquí se aplica el MISMO
`bt_engine.CostModel` que usa el resto del repo a las etiquetas del cube y se
mira cuánto del bruto sobrevive.

ALCANCE — leer antes de citar cualquier número de aquí:

  1. **Es una COTA SUPERIOR, no una simulación.** El cube etiqueta con triple
     barrera y sin modelo de fill: asume que el stop se llena EXACTO en
     `stop_price`. Medido sobre 49.808 pérdidas, la vela que dispara el stop se
     pasa +0,388R de media. Lo que sobreviva aquí es el techo de lo capturable,
     no "lo que se habría ganado". El paso 2 (`--fill-overshoot`) mete ese
     sobrepaso y enseña los dos números por separado.
  2. **Cruce de venue.** El cube se cosechó sobre velas de OKX SPOT (verificado:
     el entry_price coincide exacto) y el CostModel por defecto modela un
     USDT-perp con funding. Es una mezcla heredada del repo, no una decisión de
     este tool; `--no-funding` la quita para ver cuánto pesa.
  3. Requiere cubos de esquema 2 (`cosecha_cubes_v2`, de
     tools/cube_regrade_excursion.py).

Uso:
  python tools/cube_net_expectancy.py
  python tools/cube_net_expectancy.py --tp tp4 --horizon 288 --por-simbolo
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bt_engine as eng          # noqa: E402
import bt_labeler as lb          # noqa: E402

CUBE_DIR = "cosecha_cubes_v2"
MIN_N = 30
N_BOOT = 2000


def cost_for_symbol(symbol, no_funding=False):
    """Mismo CostModel por simbolo que el runner (BTC mas fino que el resto)."""
    base = (symbol or "").upper().split("_")[0]
    slip = 0.4 if base in ("BTC", "XBT") else 1.0
    return eng.CostModel(taker_fee=0.0005, slippage_bps=slip,
                         funding_rate_8h=0.0001, apply_funding=not no_funding)


def aplicar_sobrepaso(pool, frac):
    """PASO 2: el stop no se llena en `stop_price`, se llena mas alla.

    La vela que dispara el stop se pasa de largo (medido: +0.388R de media, p90
    +0.902R). Una orden stop es MARKET: se llena en algun punto entre el nivel y
    el extremo de la vela, y ese punto no esta en el dato. Asi que esto NO es una
    estimacion, es un BARRIDO: frac=0 es el nivel exacto (lo que asume el cube),
    frac=1 el extremo de la vela (el peor caso posible). El numero real esta
    dentro, y donde exactamente depende de la microestructura, no del backtest.

    Solo toca las salidas por stop. El TP es orden LIMITE: se llena a tu precio y
    su sobrepaso (+0.485R medido) no te lo llevas ni te lo comen.
    """
    if not frac:
        return pool
    q = pool.copy()
    perd = q["outcome"].to_numpy() == lb.LOSS
    if not perd.any():
        return q
    e = q["entry_price"].to_numpy(dtype=float)
    st = q["stop_price"].to_numpy(dtype=float)
    d = q["direction"].to_numpy(dtype=float)
    risk = np.abs(e - st)
    extremo = e + d * q["mae_r"].to_numpy(dtype=float) * risk
    nuevo = st + frac * (extremo - st)
    px = q["exit_price"].to_numpy(dtype=float).copy()
    px[perd] = nuevo[perd]
    q["exit_price"] = px
    return q


def neto(pool, symbol, no_funding=False, fill_frac=0.0):
    """E[R] bruta y neta de un pool, con la contabilidad de bt_engine."""
    lb.require_life_scoped(pool, who="cube_net_expectancy")
    pool = aplicar_sobrepaso(pool, fill_frac)
    r = eng.simulate(pool, bar_minutes=5.0, cost=cost_for_symbol(symbol, no_funding))
    t = r["trades"]
    if len(t) == 0:
        return None
    riesgo = t["qty"].to_numpy() * (t["entry_price"] - t["stop_price"]).abs().to_numpy()
    return pd.DataFrame({
        "bruto_r": t["pnl_r"].astype(float).to_numpy(),
        "neto_r": t["net_pnl_r"].astype(float).to_numpy(),
        "fees_r": t["fees"].to_numpy() / riesgo,
        "funding_r": t["funding_cost"].to_numpy() / riesgo,
        "slip_r": t["slippage_cost"].to_numpy() / riesgo,
        "gana_neto": t["net_pnl_r"].astype(float).to_numpy() > 0,
    })


def ci(x, n_boot=N_BOOT, seed=0):
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float)
    m = np.array([x[i].mean() for i in
                  (rng.integers(0, len(x), len(x)) for _ in range(n_boot))])
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)), float(np.mean(m <= 0))


def cargar(cube_dir, tp, horizon, symbols=None, no_funding=False, fill_frac=0.0):
    partes = []
    for f in sorted(glob.glob(os.path.join(cube_dir, "tp_cube_*.parquet"))):
        sym = os.path.basename(f).replace("tp_cube_", "").replace(".parquet", "")
        if symbols and sym not in symbols:
            continue
        d = pd.read_parquet(f)
        pool = d[(d["tp"] == tp) & (d["horizon"] == horizon)].copy()
        if len(pool) == 0:
            continue
        n = neto(pool, sym, no_funding, fill_frac)
        if n is None:
            continue
        n["symbol"] = sym
        partes.append(n)
    return pd.concat(partes, ignore_index=True) if partes else None


def linea(nombre, d):
    lo, hi, p0 = ci(d["neto_r"].to_numpy())
    nota = "" if len(d) >= MIN_N else "  <- n<%d" % MIN_N
    return ("%-11s %6d %8.3f %8.3f  [%+.3f,%+.3f] %6.3f %8.3f %8.3f %8.3f %6.1f%%%s"
            % (nombre, len(d), d["bruto_r"].mean(), d["neto_r"].mean(), lo, hi, p0,
               -d["fees_r"].mean(), -d["funding_r"].mean(), -d["slip_r"].mean(),
               100 * d["gana_neto"].mean(), nota))


def cabecera():
    print("%-11s %6s %8s %8s  %-17s %6s %8s %8s %8s %6s"
          % ("", "n", "bruto", "NETO", "IC95%", "P<=0", "fees", "fund", "slip", "WR"))


def main(argv=None):
    p = argparse.ArgumentParser(description="E8 paso 1: el cube con costes")
    p.add_argument("--cube-dir", default=CUBE_DIR)
    p.add_argument("--tp", default="tp4")
    p.add_argument("--horizon", type=int, default=288)
    p.add_argument("--symbols", nargs="*", default=None)
    p.add_argument("--no-funding", action="store_true")
    p.add_argument("--por-simbolo", action="store_true")
    p.add_argument("--rejilla", action="store_true", help="todas las celdas tp x horizonte")
    p.add_argument("--fill-overshoot", action="store_true",
                   help="paso 2: barrido del fill del stop entre el nivel y el extremo")
    a = p.parse_args(argv)

    if a.rejilla:
        print("REJILLA tp x horizonte — E[R] NETA (bruta entre parentesis)\n")
        print("%-6s %s" % ("tp", "".join("%22s" % ("h%d" % h) for h in (96, 288, 576))))
        for tp in ("tp1", "tp2", "tp3", "tp4"):
            fila = "%-6s" % tp
            for h in (96, 288, 576):
                d = cargar(a.cube_dir, tp, h, a.symbols, a.no_funding)
                if d is None:
                    fila += "%22s" % "-"
                    continue
                lo, hi, _ = ci(d["neto_r"].to_numpy())
                fila += "%22s" % ("%+.3f (%+.3f)" % (d["neto_r"].mean(), d["bruto_r"].mean()))
            print(fila)
        print("\n  Ninguna celda es 'la estrategia': elegir la mejor de 12 sobre el")
        print("  MISMO set es seleccion, y su expectancy no sobrevive al gate.")
        return 0

    if a.fill_overshoot:
        print("E8 PASO 2 — donde se llena el stop (%s / h%d)" % (a.tp, a.horizon))
        print("Una orden stop es MARKET: se llena entre el nivel y el extremo de la")
        print("vela, y ese punto NO esta en el dato. Esto es un barrido, no una")
        print("estimacion: el numero real esta dentro del rango.\n")
        print("%-28s %6s %9s  %-17s %6s %6s"
              % ("fill del stop", "n", "NETO", "IC95%", "P<=0", "WR"))
        for frac, nom in ((0.0, "0%  nivel exacto (el cube)"),
                          (0.25, "25% del sobrepaso"),
                          (0.50, "50% del sobrepaso"),
                          (1.00, "100% extremo de la vela")):
            d = cargar(a.cube_dir, a.tp, a.horizon, a.symbols, a.no_funding, frac)
            if d is None:
                continue
            lo, hi, p0 = ci(d["neto_r"].to_numpy())
            print("%-28s %6d %9.3f  [%+.3f,%+.3f] %6.3f %5.1f%%"
                  % (nom, len(d), d["neto_r"].mean(), lo, hi, p0,
                     100 * d["gana_neto"].mean()))
        print("\n  El TP no entra en el barrido: es orden LIMITE, se llena a tu")
        print("  precio. Su sobrepaso (+0.485R medido) ni se cobra ni se paga.")
        print("  La asimetria es de un solo lado, y es en contra.")
        return 0

    d = cargar(a.cube_dir, a.tp, a.horizon, a.symbols, a.no_funding)
    if d is None:
        print("sin pool; corre tools/cube_regrade_excursion.py")
        return 1
    print("E8 PASO 1 — el cube con costes (%s / h%d)%s"
          % (a.tp, a.horizon, "  [sin funding]" if a.no_funding else ""))
    print("COTA SUPERIOR: el cube asume fill EXACTO en stop_price. Medido, la vela")
    print("que dispara el stop se pasa +0.388R de media. Ver --fill-overshoot (paso 2).\n")
    cabecera()
    print(linea("POOL", d))
    if a.por_simbolo:
        print()
        for s, g in d.groupby("symbol"):
            print(linea(s, g))
    print("\n  fees/fund/slip en R, con signo de COSTE (positivo = resta).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
