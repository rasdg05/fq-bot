# -*- coding: utf-8 -*-
"""
================================================================================
  BUILD RETRIEVAL INDEX (F2) - persiste el indice de produccion + umbral ORO
  by RasDG_Sol + Claude

  Construye el artefacto que el gate VIP oro consulta en vivo:
    retrieval/<exchange>/<symbol>/{scaler.pkl, index.pkl|index.turbo,
                                   outcomes.parquet, meta.json}

  Pipeline (reusa el MISMO replay denso que valido el edge en research):
    1) carga OHLCV (TF_STACK) y corre replay_states (estado de CADA vela + label
       forward en ATR), identico a tools/run_research_real.py.
    2) PUERTA DE LEAKAGE: pase causal vs placebo (bt_retrieval.retrieval_oos).
       Si el placebo no colapsa o el edge causal no supera el piso -> ABORTA
       (no se persiste un indice que no demostro edge limpio). --force lo salta.
    3) CALIBRA el umbral oro = percentil (1-top_pct) de retr_expectancy_r sobre
       estados confident (causal OOS). top_pct=0.05 por defecto (lo validado).
    4) construye el indice de produccion con TODOS los estados resueltos y
       persiste gate (indice + umbral + params) via GoldGate.save.

  OJO: corre en Railway/local/CI (necesita datos + el motor del monolito); este
  sandbox no llega a exchanges. Reusa run_research_real (_load_tf/_run_replay) y
  retrieval_gate/bt_retrieval. No toca fusion_engine ni la entrega de produccion.
================================================================================
"""
import os
import sys
import argparse
import logging

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bt_walkforward as wf
import bt_retrieval as btr
import retrieval_gate as rg
import tools.run_research_real as rr

log = logging.getLogger("build_retrieval_index")


def _leakage_gate(states, folds, valid_index, common, *, edge_floor=0.02):
    """Corre causal vs placebo y devuelve (ok, edge_causal, edge_placebo).
    ok = el placebo colapsa (|placebo| < |causal|) y el causal supera el piso."""
    oos_c = btr.retrieval_oos(states, folds, valid_index, mode="causal", **common)
    edge_c = btr.retrieval_ablation(oos_c).get("edge_vs_base_r")
    oos_p = btr.retrieval_oos(states, folds, valid_index, mode="placebo", **common)
    edge_p = btr.retrieval_ablation(oos_p).get("edge_vs_base_r")
    ok = (edge_c is not None and np.isfinite(edge_c) and edge_c > edge_floor
          and (edge_p is None or not np.isfinite(edge_p) or abs(edge_p) < abs(edge_c)))
    return ok, edge_c, edge_p, oos_c


def main():
    p = argparse.ArgumentParser(description="Construye el indice de retrieval (F2) + umbral oro")
    p.add_argument("--exchange", default="okx")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--tf-id", default="5m", choices=list(rr.TF_STACK.keys()))
    p.add_argument("--data-dir", default="data")
    p.add_argument("--dense-horizon", type=int, default=288,
                   help="velas forward del label de retorno en ATR (8h=96, 24h=288 en 5m)")
    p.add_argument("--step", type=int, default=2, help="submuestreo del replay denso")
    p.add_argument("--min-lookback", type=int, default=300)
    p.add_argument("--n-splits", type=int, default=7)
    p.add_argument("--embargo", type=int, default=8)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--backend", default="exact", choices=["exact", "turbovec"])
    p.add_argument("--bit-width", type=int, default=4)
    p.add_argument("--retrieval-k", type=int, default=50)
    p.add_argument("--sim-floor", type=float, default=0.5)
    p.add_argument("--n-floor", type=int, default=None)
    p.add_argument("--decay-bars", type=int, default=None)
    p.add_argument("--query-step", type=int, default=10,
                   help="submuestreo de queries en el pase de calibracion OOS")
    p.add_argument("--gold-top-pct", type=float, default=rg.GOLD_TOP_PCT)
    p.add_argument("--out-dir", default=None, help="default: retrieval/<ex>/<sym>")
    p.add_argument("--force", action="store_true",
                   help="persiste aunque la puerta de leakage no pase (NO recomendado)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # --- 1) datos + replay denso (identico al research) ---
    prim, mid, high, sub = rr.TF_STACK[args.tf_id]
    df_p = rr._load_tf(args.exchange, args.symbol, prim, args.data_dir)
    if df_p is None:
        sys.exit(f"falta el dataset {prim}; corre tools/build_dataset.py primero")
    tfs = (df_p,
           rr._load_tf(args.exchange, args.symbol, mid, args.data_dir),
           rr._load_tf(args.exchange, args.symbol, high, args.data_dir),
           rr._load_tf(args.exchange, args.symbol, sub, args.data_dir))
    print(f"[1/4] replay denso {args.symbol} {prim} (horizon={args.dense_horizon}, step={args.step})...")
    states = rr._run_replay(tfs, seed=args.seed, tf_id=args.tf_id, dense=True,
                            horizon_bars=args.dense_horizon, step=args.step,
                            min_lookback=args.min_lookback)
    states = states[states["pnl_r"].notna()].reset_index(drop=True)
    n = len(states)
    print(f"      estados densos resueltos: {n}")
    if n < args.n_splits * 3:
        sys.exit(f"muestra insuficiente ({n} < {args.n_splits*3}); sube historia o baja --step")

    # --- 2) puerta de leakage ---
    n_floor = (args.retrieval_k // 2) if args.n_floor is None else args.n_floor
    common = dict(backend=args.backend, bit_width=args.bit_width, k=args.retrieval_k,
                  sim_floor=args.sim_floor, n_floor=n_floor, decay_bars=args.decay_bars,
                  seed=args.seed, query_step=args.query_step)
    folds, valid_index = wf.folds_from_labeled(states, n_splits=args.n_splits,
                                               embargo=args.embargo)
    print("[2/4] puerta de leakage (causal vs placebo)...")
    ok, edge_c, edge_p, oos_c = _leakage_gate(states, folds, valid_index, common)
    print(f"      edge causal={edge_c}  placebo={edge_p}  -> {'OK' if ok else 'REVISAR'}")
    if not ok and not args.force:
        sys.exit("ABORTA: el edge causal no supera el piso o el placebo no colapsa "
                 "(usa --force para persistir igualmente, NO recomendado).")

    # --- 3) calibrar umbral oro sobre confident (causal OOS) ---
    print(f"[3/4] calibrando umbral oro (top {args.gold_top_pct:.0%})...")
    conf = oos_c[~oos_c["retr_abstain"].astype(bool)]
    threshold = rg.calibrate_gold_threshold(conf["retr_expectancy_r"].to_numpy(),
                                            top_pct=args.gold_top_pct)
    print(f"      n_confident={len(conf)}  umbral_oro(retr_expectancy_r)={threshold}")

    # --- 4) indice de produccion (todos los estados) + persistir ---
    print("[4/4] construyendo indice de produccion y persistiendo...")
    idx = rg.StateIndex.build(states, backend=args.backend, bit_width=args.bit_width)
    gate = rg.GoldGate(idx, threshold, k=args.retrieval_k, sim_floor=args.sim_floor,
                       n_floor=n_floor, decay_bars=args.decay_bars)
    out_dir = args.out_dir or os.path.join("retrieval", args.exchange,
                                           args.symbol.replace("/", "_"))
    gate.save(out_dir, backend=args.backend, meta_extra={
        "symbol": args.symbol, "exchange": args.exchange, "tf_id": args.tf_id,
        "dense_horizon": args.dense_horizon, "gold_top_pct": args.gold_top_pct,
        "bit_width": args.bit_width, "n_states": n, "n_confident": int(len(conf)),
        "edge_causal_r": edge_c, "edge_placebo_r": edge_p,
        "leakage_ok": bool(ok), "seed": args.seed,
    })
    print(f"      -> {out_dir} (scaler.pkl, index, outcomes.parquet, meta.json)")
    print("listo. Carga en vivo con retrieval_gate.GoldGate.from_dir(out_dir).")


if __name__ == "__main__":
    main()
