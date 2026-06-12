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

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bt_ablation as ab          # noqa: E402
import bt_quality as ql           # noqa: E402
import bt_walkforward as wf       # noqa: E402

_DIAS = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]


def _veto_mask(df, args):
    """True = la señal cae al veto. OR de los predicados pedidos."""
    ts = pd.to_datetime(df["entry_ts"])
    mask = np.zeros(len(df), dtype=bool)
    why = []
    if args.veto_killzones:
        kzs = [k.strip() for k in args.veto_killzones.split(",") if k.strip()]
        mask |= df["field_killzone"].astype(str).isin(kzs).to_numpy()
        why.append(f"killzone in {kzs}")
    if args.veto_utc_blocks:
        blocks = set()
        for b in args.veto_utc_blocks.split(","):
            b = b.strip()
            if b:
                blocks.add(int(b.split("-")[0]))
        mask |= ts.dt.hour.floordiv(4).mul(4).isin(blocks).to_numpy()
        why.append(f"bloque_utc in {sorted(blocks)}")
    if args.veto_weekdays:
        dias = [d.strip() for d in args.veto_weekdays.split(",") if d.strip()]
        idx = [_DIAS.index(d) for d in dias]
        mask |= ts.dt.dayofweek.isin(idx).to_numpy()
        why.append(f"dia in {dias}")
    return mask, " OR ".join(why) if why else "(sin veto)"


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
    print("\n  NOTA: paso 1 del protocolo F2.6 (§6.8): esto DIMENSIONA el "
          "veto; la decision exige corrida de confirmacion + leakage_ok del "
          "ORO + paper forward. Radar, no prueba.")


if __name__ == "__main__":
    main()
