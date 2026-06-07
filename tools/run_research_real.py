#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RUNNER REAL del harness de research — cablea el motor de PRODUCCION sobre el
histgrico y produce el reporte que un fondo mira: metricas OOS con costes,
modelo entrenado sobre walk-forward, e importancia/poda de modulos.

A diferencia de research_demo.py (sintetico), aqui se replica EXACTAMENTE lo que
ve el bot: mismas velas, mismo fusion_engine.evaluate_signal, mismos niveles.

REQUISITOS (corre en el entorno del bot: Railway/local, NO en el sandbox):
  - Datasets Parquet ya descargados con tools/build_dataset.py para los TFs que
    use el motor (15m primario + 1h/4h contexto + 1m sub, segun tu config).
  - Dependencias del bot: pandas-ta, lightgbm (opcional), etc.

Uso:
  # 1) descarga (una vez)
  python tools/build_dataset.py --symbol SOL/USDT --timeframe 15m --market swap --years 2 --exchanges binance
  python tools/build_dataset.py --symbol SOL/USDT --timeframe 1h  --market swap --years 2 --exchanges binance
  python tools/build_dataset.py --symbol SOL/USDT --timeframe 4h  --market swap --years 2 --exchanges binance
  python tools/build_dataset.py --symbol SOL/USDT --timeframe 1m  --market swap --years 2 --exchanges binance

  # 2) research
  python tools/run_research_real.py --exchange binance --symbol SOL/USDT \\
      --max-bars 96 --n-splits 8 --embargo 8
"""
import argparse
import importlib
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

import bt_data
import bt_features as bf
import bt_labeler as lb
import bt_walkforward as wf
import bt_engine as eng
import bt_metrics as met
import bt_train as tr
import bt_ablation as ab
import bt_retrieval as rt


def _load_tf(exchange, symbol, tf, data_dir):
    """Carga un Parquet OHLCV y le aplica los indicadores del motor."""
    import fq_market_data as md
    path = bt_data.dataset_path(data_dir, exchange, symbol, tf)
    if not os.path.exists(path):
        return None
    df = bt_data.load_parquet(path)
    return md.add_indicators(df)


def _build_config(monolith, tf_id="15m"):
    """Replica el config que el monolito pasa a evaluate_signal."""
    profile = monolith.TF_PROFILES.get(tf_id, {})
    return {
        "PHI": getattr(monolith, "PHI", 1.6180339887),
        "PMASTER_MIN": profile.get("PMASTER_MIN", monolith.PMASTER_MIN),
        "RR_MIN_TP_DIVINO": profile.get("RR_MIN_TP_DIVINO", 1.5),
        "TF_ID": tf_id,
        "TF_LABEL": profile.get("label", tf_id),
        "PULLBACK_VOL_MULT": profile.get("PULLBACK_VOL_MULT", 1.0),
        "BREAKOUT_VOL_MULT": profile.get("BREAKOUT_VOL_MULT", 1.0),
        "LAST_SIGNAL_TS": None,
        "PHASE_E_N_PATHS": profile.get("PHASE_E_N_PATHS"),
        "PHASE_E_COOLDOWN_MIN": profile.get("PHASE_E_COOLDOWN_MIN"),
    }


def _run_replay(tfs, env_overrides=None, **replay_kwargs):
    """Replay con (re)carga de fusion_engine bajo unos env overrides. Devuelve
    el DataFrame de eventos disparados por el motor.
    """
    if env_overrides:
        os.environ.update({k: str(v) for k, v in env_overrides.items()})
    # recarga modulos que leen env a nivel de import (toggles de modulo)
    import fusion_engine
    for mod_name in ("signal_scorer", "regime_detector", "session_bias",
                     "volume_quality", "emergent_time", "fusion_engine"):
        try:
            importlib.reload(importlib.import_module(mod_name))
        except Exception:
            pass
    fusion_engine = importlib.import_module("fusion_engine")

    import fq_bot_v3_2 as b
    config = _build_config(b)
    df15, df1h, df4h, df1m = tfs
    return bf.replay_events(
        df15, df1h, df4h, df1m,
        evaluate_fn=fusion_engine.evaluate_signal,
        detect_pspace_fn=b.detect_pspace,
        laplacian_check_fn=b.laplacian_check,
        calculate_levels_fn=b.calculate_levels,
        config=config,
        **replay_kwargs,
    )


def _init_ledger():
    """Crea el esquema del ledger (tabla 'signals' y demas) en FQ_LEDGER_PATH.

    Sin esto, evaluate_signal truena en cada vela al leer la memoria de buckets
    sobre una DB vacia ('no such table: signals') y NO dispara ninguna senal.
    init_db() corre el SCHEMA_SQL con IF NOT EXISTS; las migraciones son
    best-effort (idempotentes sobre una DB recien creada).
    """
    import entropy_cognition as ev
    ev.init_db()
    for mig in ("migrate_schema_v2", "migrate_schema_v3", "migrate_schema_v4"):
        fn = getattr(ev, mig, None)
        if fn:
            try:
                fn()
            except Exception:
                pass


def _label_and_fold(events, df15, max_bars, n_splits, embargo):
    labeled = lb.label_events(df15, events.to_dict("records"), max_bars=max_bars)
    folds, valid_index = wf.folds_from_labeled(
        labeled, n_splits=n_splits, embargo=embargo)
    return labeled, folds, valid_index


def _oos_metrics(labeled, folds, valid_index, sim_kwargs, ppy):
    pooled = ab.pooled_oos_trades(labeled, folds, valid_index=valid_index)
    res = eng.simulate(pooled, **sim_kwargs)
    return met.metrics_from_result(res, periods_per_year=ppy), len(pooled)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--exchange", default="binance")
    p.add_argument("--symbol", default="SOL/USDT")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--min-lookback", type=int, default=300)
    p.add_argument("--step", type=int, default=1)
    p.add_argument("--max-bars", type=int, default=96,
                   help="horizonte de la barrera vertical (velas de 15m)")
    p.add_argument("--n-splits", type=int, default=8)
    p.add_argument("--embargo", type=int, default=8)
    p.add_argument("--risk-frac", type=float, default=0.01)
    p.add_argument("--equity0", type=float, default=10_000)
    p.add_argument("--no-ablation", action="store_true")
    p.add_argument("--seed", type=int, default=42,
                   help="semilla global de reproducibilidad (retrieval/bootstrap)")
    # --- retrieval (capa k-NN de expectancy por analogia; read-only en F1) ---
    p.add_argument("--retrieval", action="store_true",
                   help="activa el diagnostico read-only de retrieval (no decide)")
    p.add_argument("--retrieval-backend", default="exact",
                   choices=["exact", "turbovec"])
    p.add_argument("--retrieval-k", type=int, default=50)
    p.add_argument("--retrieval-bit", type=int, default=4)
    p.add_argument("--retrieval-sim-floor", type=float, default=0.5)
    p.add_argument("--retrieval-nfloor", type=int, default=None,
                   help="minimo de vecinos en radio para no abstenerse (def: k/2)")
    p.add_argument("--retrieval-decay-bars", type=int, default=None,
                   help="half-life de recencia en velas (None=sin decaimiento)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("=" * 70)
    print("  HARNESS DE RESEARCH FQ — runner REAL (motor de produccion)")
    print("=" * 70)

    # --- datos ---
    df15 = _load_tf(args.exchange, args.symbol, "15m", args.data_dir)
    if df15 is None:
        sys.exit("falta el dataset 15m; corre tools/build_dataset.py primero")
    df1h = _load_tf(args.exchange, args.symbol, "1h", args.data_dir)
    df4h = _load_tf(args.exchange, args.symbol, "4h", args.data_dir)
    df1m = _load_tf(args.exchange, args.symbol, "1m", args.data_dir)
    tfs = (df15, df1h, df4h, df1m)
    print(f"\nvelas 15m: {len(df15)} | 1h: {_n(df1h)} | 4h: {_n(df4h)} | 1m: {_n(df1m)}")

    bar_minutes = 15.0
    cost = _cost_for_symbol(args.symbol)   # BTC mas fino que SOL
    sim_kwargs = {"equity0": args.equity0, "risk_frac": args.risk_frac,
                  "bar_minutes": bar_minutes, "cost": cost}
    print(f"  costos: taker_fee={cost.taker_fee} slippage_bps={cost.slippage_bps} "
          f"funding_8h={cost.funding_rate_8h}")

    # --- Inicializar el ledger (esquema) para que el motor lea memoria ---
    _init_ledger()

    # --- BASELINE: replay con todos los modulos ---
    print("\n[1/4] replay del motor (baseline, todos los modulos)...")
    events = _run_replay(
        tfs, env_overrides=None,
        min_lookback=args.min_lookback, step=args.step,
        progress_every=2000,
    )
    print(f"  senales disparadas: {len(events)}")
    if len(events) == 0:
        sys.exit("el motor no disparo ninguna senal en este rango; "
                 "baja min_lookback / sube el rango historico (--years)")

    # Etiqueta SIEMPRE lo que haya. Aunque sean 2 senales, este es el track
    # record crudo del motor (outcome + pnl_r por senal) y NO debe tirarse: es
    # el primer dato real del sistema, no un fallo.
    labeled = lb.label_events(
        df15, events.to_dict("records"), max_bars=args.max_bars)
    summ = lb.label_summary(labeled)
    if summ is not None:
        print(f"  etiquetadas: n={summ['n']} win_rate={summ['win_rate']:.3f} "
              f"expectancy_r={summ['expectancy_r']:.3f} "
              f"total_r={summ['total_r']:+.2f}")
    _print_track_record(labeled)

    # Guard de walk-forward: necesita una muestra minima para 8 folds. Con pocas
    # senales NO abortamos en rojo — ya mostramos el track record arriba; solo
    # omitimos las metricas OOS / modelo / poda por muestra insuficiente.
    min_for_wf = args.n_splits * 3
    if len(events) < min_for_wf:
        print(f"\n  [guard] {len(events)} senales < {min_for_wf} necesarias "
              f"para walk-forward de {args.n_splits} folds.")
        print("  Se omiten metricas OOS / modelo / poda (muestra insuficiente),")
        print("  pero el track record crudo de arriba es valido.")
        print("  Para subir el volumen: mas historia (build_dataset --years 2) "
              "y --step 1.")
        return

    folds, valid_index = wf.folds_from_labeled(
        labeled, n_splits=args.n_splits, embargo=args.embargo)

    ppy = _periods_per_year(labeled, bar_minutes)
    base_metrics, n_pool = _oos_metrics(labeled, folds, valid_index, sim_kwargs, ppy)
    print("\n[2/4] Metricas OOS (con fees+slippage+funding):")
    print(met.format_report(base_metrics))

    # --- modelo entrenado sobre walk-forward ---
    print("\n[3/4] Modelo (LightGBM si disponible) sobre walk-forward...")
    feat_cols = bf._numeric_feature_columns(labeled)
    valid = labeled.loc[valid_index]
    X = valid[feat_cols].reset_index(drop=True).fillna(0.0)
    y = (valid["outcome"] == lb.WIN).astype(int).to_numpy()
    try:
        est_factory = tr.make_lgbm_classifier
        est_factory()   # prueba que lightgbm exista
    except Exception:
        print("  (lightgbm no disponible; instala lightgbm para el modelo)")
        est_factory = None
    if est_factory is not None:
        trained = tr.train_walk_forward(X, y, folds, estimator_factory=est_factory)
        print(f"  AUC out-of-fold: {trained['oof_auc']}")
        if trained["importances"] is not None:
            print("  Top features:")
            print(trained["importances"].head(10).to_string())
        thr = tr.threshold_evaluation(
            trained["oof_scores"], trained["tested_mask"],
            valid["pnl_r"].to_numpy())
        print("  Expectancy por umbral del modelo:")
        print(thr.to_string(index=False))

    # --- retrieval (read-only, no decide) ---
    if args.retrieval:
        _run_retrieval_diagnostic(labeled, folds, valid_index, args)

    # --- ablacion de modulos por toggles de entorno ---
    if args.no_ablation:
        return
    print("\n[4/4] Poda de modulos (re-replay con cada modulo OFF)...")
    toggles = {
        "scorer":        {"FQ_USE_SCORER": "0"},
        "regime":        {"FQ_USE_REGIME": "0"},
        "session_bias":  {"FQ_SESSION_BIAS": "0"},
    }
    base_metric = base_metrics.get("expectancy_r")
    print(f"  baseline expectancy_r={_f(base_metric)} (n_oos={n_pool})")
    for name, env_off in toggles.items():
        try:
            ev2 = _run_replay(tfs, env_overrides=env_off,
                              min_lookback=args.min_lookback, step=args.step)
            lab2, fold2, vi2 = _label_and_fold(
                ev2, df15, args.max_bars, args.n_splits, args.embargo)
            m2, _ = _oos_metrics(lab2, fold2, vi2, sim_kwargs, ppy)
            without = m2.get("expectancy_r")
            delta = (base_metric - without) if (base_metric is not None and
                                                without is not None) else None
            verdict = "VIVE " if (delta is not None and delta > 0) else "MATAR"
            print(f"  [{verdict}] {name:<14} sin_el expectancy_r={_f(without)} "
                  f"delta={_f(delta)}  (n={len(ev2)})")
        except Exception as e:
            print(f"  [error] {name}: {e}")
        finally:
            # restaura el toggle para no contaminar el siguiente
            for k in env_off:
                os.environ[k] = "1"


def _cost_for_symbol(symbol):
    """Modelo de costos por simbolo. BTC es mas liquido (spread/slippage finos)
    que SOL; funding tipico similar en USDT-perp. Re-tunear con datos reales.
    """
    sym = (symbol or "").upper().replace("-", "/").split(":")[0]
    base = sym.split("/")[0]
    if base in ("BTC", "XBT"):
        return eng.CostModel(taker_fee=0.0005, slippage_bps=0.4,
                             funding_rate_8h=0.0001, apply_funding=True)
    # SOL y otros alts: slippage por defecto mas amplio.
    return eng.CostModel(taker_fee=0.0005, slippage_bps=1.0,
                         funding_rate_8h=0.0001, apply_funding=True)


def _run_retrieval_diagnostic(labeled, folds, valid_index, args):
    """[read-only] Expectancy por analogia (k-NN causal) + ablacion + leakage.

    NO altera ninguna decision: solo mide si condicionar por la expectancy del
    vecindario anade edge OOS, y corre la puerta de leakage (causal vs oracle vs
    placebo) sobre los eventos REALES del motor.
    """
    print("\n[5] Retrieval (k-NN causal, READ-ONLY) — expectancy por analogia")
    common = dict(backend=args.retrieval_backend, bit_width=args.retrieval_bit,
                  k=args.retrieval_k, sim_floor=args.retrieval_sim_floor,
                  n_floor=args.retrieval_nfloor, decay_bars=args.retrieval_decay_bars,
                  seed=args.seed)
    try:
        oos = rt.retrieval_oos(labeled, folds, valid_index, mode="causal", **common)
    except Exception as e:
        print(f"  (retrieval no disponible: {e})")
        return
    if len(oos) == 0:
        print("  (sin eventos OOS para retrieval)")
        return
    abl = rt.retrieval_ablation(oos, gate_threshold=0.0)
    print(f"  backend={args.retrieval_backend} k={args.retrieval_k} "
          f"sim_floor={args.retrieval_sim_floor} n_floor={common['n_floor'] or args.retrieval_k//2}")
    _print_ablation_table(abl)
    edge = abl.get("edge_vs_base_r")
    print(f"  >> EDGE retrieval (gate_pass - base) = {_f(edge)} R/trade")

    # Puerta de leakage: el edge causal debe sobrevivir, el placebo colapsar.
    try:
        oos_pl = rt.retrieval_oos(labeled, folds, valid_index, mode="placebo", **common)
        edge_pl = rt.retrieval_ablation(oos_pl)["edge_vs_base_r"]
        oos_or = rt.retrieval_oos(labeled, folds, valid_index, mode="oracle", **common)
        edge_or = rt.retrieval_ablation(oos_or)["edge_vs_base_r"]
        print(f"  [leakage] causal={_f(edge)}  placebo={_f(edge_pl)}  oracle={_f(edge_or)}")
        if edge is not None and not (isinstance(edge, float) and np.isnan(edge)):
            verdict = "OK" if (abs(edge_pl) < abs(edge) and edge > 0.02) else "REVISAR"
            print(f"  [leakage] veredicto={verdict} "
                  f"(placebo debe colapsar; causal no debe necesitar el oracle)")
    except Exception as e:
        print(f"  [leakage] no se pudo correr el barrido: {e}")


def _print_ablation_table(abl):
    cols = ["n", "expectancy_r", "wr", "pf", "total_r"]
    rows = ["base", "confident", "gate_pass", "gate_block", "abstained"]
    print(f"  {'subset':<12} {'n':>6} {'exp_r':>8} {'wr':>6} {'pf':>7} {'total_r':>9}")
    for r in rows:
        s = abl.get(r, {})
        print(f"  {r:<12} {s.get('n',0):>6} {_f(s.get('expectancy_r')):>8} "
              f"{_f(s.get('wr')):>6} {_f(s.get('pf')):>7} {_f(s.get('total_r')):>9}")


def _print_track_record(labeled):
    """Imprime cada senal etiquetada (su outcome y pnl_r) como track record crudo.

    Se llama SIEMPRE, aunque haya 2 senales: con muestra pequena el walk-forward
    no aplica, pero las senales individuales si son el primer dato real del motor.
    """
    if labeled is None or len(labeled) == 0:
        return
    dir_label = {1: "LONG", -1: "SHORT"}
    print("\n  Track record crudo (cada senal etiquetada):")
    header = (f"  {'#':>2}  {'entry_ts':<19}  {'dir':<5} {'entry':>10} "
              f"{'stop':>10} {'target':>10}  {'outcome':<8} {'pnl_r':>7} {'bars':>4}")
    print(header)
    print("  " + "-" * (len(header) - 2))
    for i, (_, r) in enumerate(labeled.iterrows(), start=1):
        ts = r.get("entry_ts")
        ts_s = "" if ts is None else str(pd.Timestamp(ts))[:19]
        d = dir_label.get(r.get("direction"), str(r.get("direction")))
        outcome = r.get("outcome")
        outcome_s = "-" if outcome is None else str(outcome)
        pnl = r.get("pnl_r")
        pnl_s = "n/a" if pnl is None or pd.isna(pnl) else f"{float(pnl):+.2f}"
        bars = r.get("bars_held")
        bars_s = "" if bars is None else str(int(bars))
        print(f"  {i:>2}  {ts_s:<19}  {d:<5} {_num(r.get('entry_price')):>10} "
              f"{_num(r.get('stop_price')):>10} {_num(r.get('target_price')):>10}  "
              f"{outcome_s:<8} {pnl_s:>7} {bars_s:>4}")


def _num(v):
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else f"{float(v):.4f}"


def _n(df):
    return 0 if df is None else len(df)


def _f(v):
    return "n/a" if v is None else f"{v:.4f}"


def _periods_per_year(labeled, bar_minutes):
    """Estima trades/ano a partir del span temporal de las entradas."""
    if "entry_ts" not in labeled.columns or len(labeled) < 2:
        return None
    ts = pd.to_datetime(labeled["entry_ts"])
    span_days = (ts.max() - ts.min()).total_seconds() / 86400.0
    if span_days <= 0:
        return None
    return len(labeled) * 365.0 / span_days


if __name__ == "__main__":
    main()
