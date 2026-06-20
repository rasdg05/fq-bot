#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REGRADE OFFLINE GENERICO: mide un VETO/FILTRO sobre los eventos YA
persistidos de un run de research (tp_cube_<sym>.parquet) — CERO replays.

Es el paso 1 del protocolo F2.6 (RETRIEVAL_PLAN §6.8) y la herramienta N5
del ENGINEERING_PLAN: "¿que pasa con el OOS si vetamos X?" en segundos, con
los MISMOS labels y folds del run original (verificables contra los numeros
sellados del run).

Subsets que imprime (pool completo y OOS pooled):
  base      = todas las señales etiquetadas
  vetadas   = las que el veto ELIMINARIA (su expectancy es lo que dejariamos
              de operar: queremos que sea claramente <= 0 neto)
  restantes = la cartera con el veto puesto (la nueva "base")

Predicados disponibles (se combinan con OR: cae cualquiera => vetada):
  --veto-killzones london_open_kz[,asia_kz...]   (columna field_killzone)
  --veto-utc-blocks 00-04,04-08                  (bloque 4h del entry_ts UTC)
  --veto-weekdays lun[,dom...]                   (dia de semana del entry_ts)

Uso (veto primario F2.6 sobre el run #30):
  python tools/regrade_events.py --cube tp_cube_SOL_USDT.parquet \
      --veto-killzones london_open_kz --cost-burden-r 0.2334
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bt_ablation as ab          # noqa: E402
import bt_quality as ql           # noqa: E402
import bt_walkforward as wf       # noqa: E402
import bt_engine as eng           # noqa: E402
import bt_metrics as met          # noqa: E402
import segment_veto as sv         # noqa: E402


def _cost_for_symbol(symbol):
    """Mismo CostModel por simbolo que el runner (BTC mas fino que SOL)."""
    sym = (symbol or "").upper().replace("-", "/").split(":")[0]
    base = sym.split("/")[0]
    slip = 0.4 if base in ("BTC", "XBT") else 1.0
    return eng.CostModel(taker_fee=0.0005, slippage_bps=slip,
                         funding_rate_8h=0.0001, apply_funding=True)


def _exp_r(pool, cost):
    """expectancy_r OOS de una cartera bajo un CostModel (bt_engine real,
    no carga plana). bar_minutes=5 (cubo en 5m)."""
    if pool is None or len(pool) == 0:
        return float("nan"), 0
    res = eng.simulate(pool, bar_minutes=5.0, cost=cost)
    m = met.metrics_from_result(res, periods_per_year=None)
    return m.get("expectancy_r"), m.get("n_trades", 0)


def _maker_matrix(pooled, symbol):
    """Matriz {base, con-veto} x {taker, entrada maker, entrada+TP maker}:
    las DOS palancas de calidad juntas, con bt_engine real por pierna.
    El veto usa la columna _vetada ya marcada en `pooled`."""
    from dataclasses import replace
    base_cost = _cost_for_symbol(symbol)
    escen = [
        ("taker/taker", base_cost),
        ("entrada maker", replace(base_cost, maker_entry=True)),
        ("entrada+TP maker", replace(base_cost, maker_entry=True,
                                     maker_tp_exit=True)),
    ]
    restantes = pooled[~pooled["_vetada"]]
    rows = []
    for name, c in escen:
        eb, nb = _exp_r(pooled, c)
        er, nr = _exp_r(restantes, c)
        rows.append({"ejecucion": name, "base_expR": eb, "base_n": nb,
                     "+veto_expR": er, "+veto_n": nr})
    print(f"\n  -- MATRIZ maker x veto (OOS, bt_engine real; {symbol}) --")
    print("  " + pd.DataFrame(rows).to_string(
        index=False, float_format=lambda v: f"{v:8.4f}").replace("\n", "\n  "))
    print("  (base = toda la cartera OOS; +veto = sin las señales vetadas)")


def _veto_mask(df, args):
    """True = la señal cae al veto. Delega en `segment_veto` — el MISMO
    predicado que el replay integrado (run_research_real) y el loop vivo. Asi
    los numeros de este regrade offline REPRODUCEN lo que mide una corrida con
    el veto ON (cero divergencia offline / research / live)."""
    cfg = sv.parse(killzones=args.veto_killzones or "",
                   utc_blocks=args.veto_utc_blocks or "",
                   weekdays=args.veto_weekdays or "")
    return cfg.mask(df), cfg.describe()


def _print_table(tag, pool, burden):
    rows = []
    for klass, sub in (("base", pool),
                       ("vetadas", pool[pool["_vetada"]]),
                       ("restantes", pool[~pool["_vetada"]])):
        st = ql.subset_stats(sub["pnl_r"])
        neto = (st["expectancy_r"] - burden
                if burden is not None and st["n"] > 0 else float("nan"))
        rows.append({"subset": klass, "n": st["n"], "wr": st["wr"],
                     "exp_r_precoste": st["expectancy_r"],
                     "exp_r_neto~": neto, "total_r": st["total_r"],
                     "max_dd_r": st["max_dd_r"]})
    print(f"\n  -- {tag} --")
    print("  " + pd.DataFrame(rows).to_string(
        index=False, float_format=lambda v: f"{v:8.4f}").replace("\n", "\n  "))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cube", required=True, help="tp_cube_<sym>.parquet del run")
    p.add_argument("--tp", default="tp1")
    p.add_argument("--horizon", type=int, default=288)
    p.add_argument("--n-splits", type=int, default=7)
    p.add_argument("--embargo", type=int, default=8)
    p.add_argument("--veto-killzones", default=None)
    p.add_argument("--veto-utc-blocks", default=None)
    p.add_argument("--veto-weekdays", default=None)
    p.add_argument("--cost-burden-r", type=float, default=None,
                   help="carga media de costes del run en R (columna neta ~)")
    p.add_argument("--maker-matrix", default=None, metavar="SYMBOL",
                   help="imprime la matriz {base,veto}x{taker,maker} con "
                        "bt_engine real para el simbolo dado (p.ej. SOL/USDT)")
    args = p.parse_args()

    cube = pd.read_parquet(args.cube)
    labeled = cube[(cube["tp"] == args.tp)
                   & (cube["horizon"] == args.horizon)].copy()
    labeled = labeled.sort_values("entry_index").reset_index(drop=True)
    labeled["entry_ts"] = pd.to_datetime(labeled["entry_ts"])

    folds, valid_index = wf.folds_from_labeled(
        labeled, n_splits=args.n_splits, embargo=args.embargo)
    pooled_chk = ab.pooled_oos_trades(labeled, folds, valid_index=valid_index)
    st = ql.subset_stats(pooled_chk["pnl_r"])
    print(f"eventos {args.tp}/h{args.horizon}: {len(labeled)} | "
          f"[verificacion] OOS pooled n={st['n']} exp_r={st['expectancy_r']:.6f} "
          f"(contrastar con el [2.5/4] base del run)")

    mask, why = _veto_mask(labeled, args)
    labeled["_vetada"] = mask
    print(f"veto: {why} -> caen {int(mask.sum())}/{len(labeled)} señales")

    pooled = ab.pooled_oos_trades(labeled, folds, valid_index=valid_index)
    burden = args.cost_burden_r
    if burden is not None:
        print(f"(neta~ = pre-coste - {burden:.4f}R, carga media del run)")
    _print_table(f"TODAS las etiquetadas (n={len(labeled)})", labeled, burden)
    _print_table(f"OOS pooled (n={len(pooled)})", pooled, burden)
    if args.maker_matrix:
        _maker_matrix(pooled, args.maker_matrix)
    print("\n  NOTA: paso 1 del protocolo F2.6 (§6.8): esto DIMENSIONA el "
          "veto; la decision exige corrida de confirmacion + leakage_ok del "
          "ORO + paper forward. Radar, no prueba.")


if __name__ == "__main__":
    main()
