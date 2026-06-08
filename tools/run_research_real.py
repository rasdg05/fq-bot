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
import random
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
import bt_optimize as opt
import bt_quality as ql


# Stack de TFs por TF primario: (primario, htf_mid, htf_high, sub). El motor
# trata arg1 de evaluate_signal como el TF de analisis y arg2/3/4 como
# contexto/sub, asi que cambiar de 15m a 5m es solo re-mapear el stack (no toca
# el motor). El config lleva TF_ID -> conmuta PMASTER_MIN/n_paths del perfil.
TF_STACK = {
    "5m":  ("5m", "15m", "1h", "1m"),
    "15m": ("15m", "1h", "4h", "1m"),
}
TF_MINUTES = {"1m": 1.0, "3m": 3.0, "5m": 5.0, "15m": 15.0, "1h": 60.0, "4h": 240.0}


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


def _run_replay(tfs, env_overrides=None, seed=42, tf_id="15m", dense=False,
                horizon_bars=288, **replay_kwargs):
    """Replay con (re)carga de fusion_engine bajo unos env overrides. Devuelve
    el DataFrame de eventos disparados por el motor.

    seed: el gate del motor usa Thompson sampling (random.betavariate sobre la
    memoria de buckets, ver entropy_cognition.compute_kappa_thompson). En vivo
    esa aleatoriedad es exploracion deliberada, pero en el replay hace que dos
    corridas del MISMO codigo disparen conjuntos de senales distintos. Sembramos
    random + numpy justo antes del replay para que la investigacion sea
    reproducible y la comparacion entre ramas no quede contaminada por el azar.
    Cada (re)replay reusa la misma semilla -> arranque identico para cada toggle.
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
    config = _build_config(b, tf_id=tf_id)
    df15, df1h, df4h, df1m = tfs
    # Determinismo del replay: fija el RNG que consume el Thompson sampling del
    # gate (stdlib random) y cualquier np.random global.
    random.seed(seed)
    np.random.seed(seed)

    # Reproducibilidad #2: inyectar la hora del BAR en los gates por reloj de
    # pared. volume_quality.is_dead_window()/volume_veto() vetan por hora CDMX
    # (14-16h, viernes tarde) via datetime.now(); en el replay eso juzga TODA la
    # historia contra la hora REAL de ejecucion (un run a las 15:xx CDMX = "ultima
    # hora NY" veta ~90% de las senales -> el conteo se volvia funcion de cuando
    # le diste "Run"). Sustituimos datetime.now por la hora del bar en curso para
    # que el veto se evalue al timestamp historico de cada vela: backtest = bot en
    # vivo, e independiente de la hora de ejecucion. Se reaplica tras cada reload.
    # Vale para AMBOS replays (denso y fires-only): replay_states tambien invoca
    # on_bar, asi el denso es igual de fiel.
    import volume_quality as _volq
    _replay_clock = {"ts": None}
    _RealDT = _volq.datetime

    class _BarClockDatetime(_RealDT):
        @classmethod
        def now(cls, tz=None):
            ts = _replay_clock["ts"]
            if ts is None:
                return _RealDT.now(tz)
            t = pd.Timestamp(ts)
            if t.tzinfo is None:
                t = t.tz_localize("UTC")
            d = t.to_pydatetime()
            return d.astimezone(tz) if tz is not None else d

    _volq.datetime = _BarClockDatetime

    def _on_bar(ts):
        _replay_clock["ts"] = ts

    common_fns = dict(
        evaluate_fn=fusion_engine.evaluate_signal,
        detect_pspace_fn=b.detect_pspace,
        laplacian_check_fn=b.laplacian_check,
        calculate_levels_fn=b.calculate_levels,
        config=config, on_bar=_on_bar,
    )
    if dense:
        # Replay DENSO (unificado): estado de CADA vela + label forward en ATR.
        # Las filas fired=True llevan dirccion/niveles reales del motor -> son el
        # track record de senales (frontera+modelo); todas las velas alimentan el
        # retrieval denso. UN replay -> dos salidas.
        return bf.replay_states(
            df15, df1h, df4h, df1m,
            horizon_bars=horizon_bars, **common_fns, **replay_kwargs,
        )
    return bf.replay_events(
        df15, df1h, df4h, df1m, **common_fns, **replay_kwargs,
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


def _exposure_fraction(pooled):
    """Fraccion de tiempo en mercado: velas en posicion / span temporal cubierto.

    Aproxima exposicion como sum(bars_held) / (span de entry_index cubierto). >1
    indicaria solape de posiciones (aqui se capa a 1.0). None si no computable.
    """
    if pooled is None or len(pooled) == 0:
        return None
    if "bars_held" not in pooled.columns or "entry_index" not in pooled.columns:
        return None
    bh = pd.to_numeric(pooled["bars_held"], errors="coerce")
    ei = pd.to_numeric(pooled["entry_index"], errors="coerce")
    span = float((ei + bh).max() - ei.min())
    held = float(bh.sum())
    if not np.isfinite(span) or span <= 0:
        return None
    return min(held / span, 1.0)


def _oos_metrics(labeled, folds, valid_index, sim_kwargs, ppy):
    """Metricas OOS sobre la cartera pooled. Devuelve (metrics, n_pool, equity).

    Emite ADEMAS la curva de equity (Series) para volcado/diagnostico de
    drawdown, y agrega exposicion + distribucion mfe_r/mae_r al dict de metricas.
    """
    pooled = ab.pooled_oos_trades(labeled, folds, valid_index=valid_index)
    res = eng.simulate(pooled, **sim_kwargs)
    exposure = _exposure_fraction(pooled)
    metrics = met.metrics_from_result(res, periods_per_year=ppy, exposure=exposure)
    return metrics, len(pooled), res.get("equity_curve")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--exchange", default="binance")
    p.add_argument("--symbol", default="SOL/USDT")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--tf-id", default="15m", choices=list(TF_STACK),
                   help="TF primario del motor (5m sube volumen de senales)")
    p.add_argument("--min-lookback", type=int, default=300)
    p.add_argument("--step", type=int, default=1)
    p.add_argument("--max-bars", type=int, default=96,
                   help="horizonte de la barrera vertical (velas del TF primario)")
    p.add_argument("--target-level", default="tp1",
                   choices=["tp1", "tp2", "tp3", "tp4"],
                   help="barrera de GANANCIA del triple-barrier (label de win que "
                        "ve el modelo Y el retrieval). tp1 (~1R) = definicion de "
                        "win del ledger, sin eventos descartados. OJO: tp3 == tp2 "
                        "en el motor (calculate_levels), asi que el unico target "
                        "LEJANO real es tp4 (entry+rng). tp4 puede descartar "
                        "eventos viejos sin px_tp4.")
    p.add_argument("--horizon-sweep", default="",
                   help="lista de horizontes (velas) separados por coma para la "
                        "frontera TP, p.ej. '96,288,576'. El horizonte es "
                        "post-replay: barrerlo NO re-replica. Vacio = solo "
                        "--max-bars")
    p.add_argument("--n-splits", type=int, default=8)
    p.add_argument("--embargo", type=int, default=8)
    p.add_argument("--risk-frac", type=float, default=0.01)
    p.add_argument("--equity0", type=float, default=10_000)
    p.add_argument("--ablation", action="store_true",
                   help="OPT-IN: corre la poda de modulos (3 replays fires-only "
                        "extra). Por defecto OFF -> el run rutinario hace UN solo "
                        "replay (frontera + modelo + retrieval denso)")
    p.add_argument("--seed", type=int, default=42,
                   help="semilla global: replay (Thompson sampling del gate) + "
                        "retrieval/bootstrap. Fija = reproducible; variala para "
                        "muestrear la distribucion de la politica estocastica")
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
    p.add_argument("--retrieval-json", default=None,
                   help="ruta para volcar resultados de retrieval en JSON (comparacion)")
    p.add_argument("--retrieval-query-step", type=int, default=1,
                   help="subsamplea queries de test del retrieval (denso: usa >1)")
    # --- replay DENSO unificado (default): UN replay alimenta senales + retrieval.
    # --dense se mantiene por compatibilidad con el workflow, pero ya es implicito.
    p.add_argument("--dense", action="store_true",
                   help="(implicito) el replay siempre es denso: un solo replay "
                        "alimenta el research de senales (subset fired) y el "
                        "retrieval denso (todas las velas)")
    p.add_argument("--dense-horizon", type=int, default=288,
                   help="velas forward para el label de retorno en ATR (denso)")
    # --- FASE D: riesgo/drawdown ---
    p.add_argument("--equity-json", default=None,
                   help="ruta para volcar la curva de equity OOS + drawdown (JSON)")
    # --- FASE C: grid post-replay de SL (xATR) x TP (tp1..tp4) ---
    p.add_argument("--tp-sl-grid", action="store_true",
                   help="re-etiqueta el MISMO conjunto fired variando ancho de SL "
                        "(multiplos de ATR) y nivel de TP -> tabla SL x TP con "
                        "expectancy/WR/Calmar (post-replay, cero replays extra)")
    p.add_argument("--sl-mults", default="0.5,1.0,1.5,2.0",
                   help="multiplos de ATR para el ancho de SL del grid (coma)")
    p.add_argument("--grid-tps", default="tp1,tp2,tp4",
                   help="niveles de TP del grid (coma). tp3 se omite (==tp2 en el motor)")
    # --- FASE B: gate de calidad 'VIP oro' (decil superior OOS) ---
    p.add_argument("--quality-gate", action="store_true",
                   help="aisla el decil/percentil superior del score del modelo y de "
                        "la expectancy del vecindario del retrieval (OOS) y reporta "
                        "WR/expectancy/total_r/max_dd del subset VIP vs el total")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("=" * 70)
    print("  HARNESS DE RESEARCH FQ — runner REAL (motor de produccion)")
    print("=" * 70)

    # --- datos ---
    prim_tf, mid_tf, high_tf, sub_tf = TF_STACK[args.tf_id]
    df_primary = _load_tf(args.exchange, args.symbol, prim_tf, args.data_dir)
    if df_primary is None:
        sys.exit(f"falta el dataset {prim_tf}; corre tools/build_dataset.py primero")
    df_mid = _load_tf(args.exchange, args.symbol, mid_tf, args.data_dir)
    df_high = _load_tf(args.exchange, args.symbol, high_tf, args.data_dir)
    df_sub = _load_tf(args.exchange, args.symbol, sub_tf, args.data_dir)
    tfs = (df_primary, df_mid, df_high, df_sub)
    print(f"\nTF primario={prim_tf} (mid={mid_tf} high={high_tf} sub={sub_tf})")
    print(f"velas {prim_tf}: {len(df_primary)} | {mid_tf}: {_n(df_mid)} | "
          f"{high_tf}: {_n(df_high)} | {sub_tf}: {_n(df_sub)}")
    print(f"seed={args.seed} (replay reproducible; el gate usa Thompson sampling)")
    print(f"target_level={args.target_level} (barrera de ganancia del "
          f"triple-barrier; tp3 = hard lock contra el target completo)")

    bar_minutes = TF_MINUTES.get(prim_tf, 15.0)
    cost = _cost_for_symbol(args.symbol)   # BTC mas fino que SOL
    sim_kwargs = {"equity0": args.equity0, "risk_frac": args.risk_frac,
                  "bar_minutes": bar_minutes, "cost": cost}
    print(f"  costos: taker_fee={cost.taker_fee} slippage_bps={cost.slippage_bps} "
          f"funding_8h={cost.funding_rate_8h}")

    # --- Inicializar el ledger (esquema) para que el motor lea memoria ---
    _init_ledger()

    # --- UNIFICADO: UN solo replay DENSO (estado de CADA vela) alimenta las DOS
    # salidas: las filas fired=True son el track record de senales (frontera +
    # modelo); TODAS las velas alimentan el retrieval denso. Antes eran dos replays
    # del mismo motor sobre las mismas velas (fires-only + denso); ahora es UNO. ---
    print("\n[1/4] replay DENSO del motor (estado de CADA vela; "
          "un replay -> senales + retrieval denso)...")
    states = _run_replay(
        tfs, env_overrides=None, seed=args.seed, tf_id=args.tf_id,
        dense=True, horizon_bars=args.dense_horizon,
        min_lookback=args.min_lookback, step=args.step,
        target_level=args.target_level, progress_every=5000,
    )
    n_states = len(states)
    if n_states == 0:
        sys.exit("el replay no produjo ningun estado; baja min_lookback / sube el "
                 "rango historico (--years) o revisa los datos")
    events = (states[states["fired"]].reset_index(drop=True)
              if "fired" in states.columns else states.iloc[0:0])
    print(f"  estados densos: {n_states} | senales disparadas (fired): {len(events)}")

    base_metric, n_pool, ppy = None, 0, None
    min_for_wf = args.n_splits * 3

    # ===== SALIDA A: research de SENALES (subset fired) =====
    if len(events) > 0:
        # Etiqueta SIEMPRE lo que haya: aunque sean pocas, es el track record crudo
        # del motor (outcome + pnl_r por senal) y no debe tirarse.
        labeled = lb.label_events(
            df_primary, events.to_dict("records"), max_bars=args.max_bars)
        summ = lb.label_summary(labeled)
        if summ is not None:
            print(f"  etiquetadas: n={summ['n']} win_rate={summ['win_rate']:.3f} "
                  f"expectancy_r={summ['expectancy_r']:.3f} "
                  f"total_r={summ['total_r']:+.2f}")
        _print_track_record(labeled)
        horizons = _parse_int_list(args.horizon_sweep) or [args.max_bars]
        _print_tp_frontier(df_primary, events, horizons)
        if args.tp_sl_grid:
            _print_tp_sl_grid(df_primary, events, args, sim_kwargs, bar_minutes)
    else:
        labeled = None
        print("  (el motor no disparo ninguna senal valida; se omite el research de "
              "senales, pero el retrieval denso sigue abajo)")

    if labeled is not None and len(events) >= min_for_wf:
        folds, valid_index = wf.folds_from_labeled(
            labeled, n_splits=args.n_splits, embargo=args.embargo)
        ppy = _periods_per_year(labeled, bar_minutes)
        base_metrics, n_pool, base_equity = _oos_metrics(
            labeled, folds, valid_index, sim_kwargs, ppy)
        base_metric = base_metrics.get("expectancy_r")
        print("\n[2/4] Metricas OOS de senales (con fees+slippage+funding):")
        print(met.format_report(base_metrics))
        _dump_equity_curve(base_equity, args)

        # --- modelo entrenado sobre walk-forward ---
        print("\n[3/4] Modelo (LightGBM si disponible) sobre walk-forward...")
        feat_cols = bf._numeric_feature_columns(labeled)
        valid = labeled.loc[valid_index]
        X = valid[feat_cols].reset_index(drop=True).fillna(0.0)
        y = (valid["outcome"] == lb.WIN).astype(int).to_numpy()
        est_factory = None
        try:
            import lightgbm  # noqa: F401
        except ImportError:
            print("  [skip] lightgbm no instalado; instala lightgbm para el modelo.")
        else:
            # lightgbm importa: el riesgo real es que el CLASSIFIER no construya.
            # LGBMClassifier vive en lightgbm.sklearn y REQUIERE scikit-learn; sin
            # el, construir truena con LightGBMError (NO ImportError) y un except
            # generico lo escondia tras "lightgbm no disponible". Aqui nombramos la
            # causa real para que un reporte sin AUC nunca sea un misterio.
            try:
                tr.make_lgbm_classifier()
                est_factory = tr.make_lgbm_classifier
            except Exception as e:
                print("  [WARN] lightgbm importa pero LGBMClassifier no construye:")
                print(f"         {type(e).__name__}: {e}")
                print("         Causa habitual: falta scikit-learn (o libgomp1).")
                print("         -> pip install scikit-learn. Modelo OMITIDO "
                      "(sin AUC / umbral / top-features).")
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

            # [FASE B] gate VIP por PERCENTIL del score OOS del modelo (robusto
            # aunque el AUC sea pobre: aisla el top relativo, no un umbral fijo).
            if args.quality_gate:
                tested = trained["tested_mask"]
                gate = ql.quality_gate(
                    trained["oof_scores"][tested],
                    valid["pnl_r"].to_numpy()[tested])
                print("\n  [VIP oro] subset por decil/percentil del SCORE DEL MODELO "
                      "(OOS):")
                print(ql.format_gate(gate, title="VIP modelo"))

        # retrieval sobre las SENALES fired (esparso; complementa al denso)
        if args.retrieval:
            print("\n  -- retrieval sobre senales fired (esparso) --")
            _run_retrieval_diagnostic(labeled, folds, valid_index, args)
    elif labeled is not None:
        print(f"\n  [guard] {len(events)} senales < {min_for_wf} para walk-forward "
              f"de {args.n_splits} folds: se omiten OOS/modelo de senales (el track "
              f"record de arriba es valido). Sube historia (--years) o baja --step.")

    # ===== SALIDA B: retrieval DENSO (TODAS las velas, no solo los fired) =====
    if args.retrieval:
        print("\n[denso] retrieval sobre TODOS los estados (no solo los fired)...")
        if n_states < min_for_wf:
            print(f"  (muestra densa insuficiente: {n_states}); se omite")
        else:
            if args.retrieval_backend == "exact" and args.retrieval_query_step <= 1:
                print("  (sugerencia: --retrieval-backend turbovec y "
                      "--retrieval-query-step>1 para 100k+ estados)")
            dfolds, dvalid = wf.folds_from_labeled(
                states, n_splits=args.n_splits, embargo=args.embargo)
            _run_retrieval_diagnostic(states, dfolds, dvalid, args)

    # --- ablacion de modulos (OPT-IN, --ablation): 3 replays fires-only extra ---
    # Es un diagnostico periodico de "que modulo paga su sitio", no de cada run;
    # por eso es opt-in (el run rutinario hace UN solo replay).
    if not args.ablation:
        return
    if base_metric is None:
        print("\n[ablacion] omitida: sin suficientes senales para una baseline OOS.")
        return
    print("\n[ablacion] Poda de modulos (re-replay fires-only con cada modulo OFF)...")
    toggles = {
        "scorer":        {"FQ_USE_SCORER": "0"},
        "regime":        {"FQ_USE_REGIME": "0"},
        "session_bias":  {"FQ_SESSION_BIAS": "0"},
    }
    print(f"  baseline expectancy_r={_f(base_metric)} (n_oos={n_pool})")
    for name, env_off in toggles.items():
        try:
            ev2 = _run_replay(tfs, env_overrides=env_off, seed=args.seed,
                              tf_id=args.tf_id, target_level=args.target_level,
                              min_lookback=args.min_lookback, step=args.step)
            lab2, fold2, vi2 = _label_and_fold(
                ev2, df_primary, args.max_bars, args.n_splits, args.embargo)
            m2, _, _ = _oos_metrics(lab2, fold2, vi2, sim_kwargs, ppy)
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
                  seed=args.seed, query_step=getattr(args, "retrieval_query_step", 1))
    try:
        oos = rt.retrieval_oos(labeled, folds, valid_index, mode="causal", **common)
    except Exception as e:
        print(f"  (retrieval no disponible: {e})")
        return None
    if len(oos) == 0:
        print("  (sin eventos OOS para retrieval)")
        return None
    abl = rt.retrieval_ablation(oos, gate_threshold=0.0)
    print(f"  backend={args.retrieval_backend} k={args.retrieval_k} "
          f"sim_floor={args.retrieval_sim_floor} n_floor={common['n_floor'] or args.retrieval_k//2}")
    _print_ablation_table(abl)
    edge = abl.get("edge_vs_base_r")
    print(f"  >> EDGE retrieval (gate_pass - base) = {_f(edge)} R/trade")

    # Puerta de leakage: el edge causal debe sobrevivir, el placebo colapsar.
    edge_pl = edge_or = None
    verdict = "n/a"
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

    if args.retrieval_json:
        import json
        payload = {
            "symbol": args.symbol, "exchange": args.exchange,
            "params": {"backend": args.retrieval_backend, "k": args.retrieval_k,
                       "bit_width": args.retrieval_bit, "sim_floor": args.retrieval_sim_floor,
                       "n_floor": common["n_floor"], "decay_bars": args.retrieval_decay_bars,
                       "seed": args.seed},
            "ablation": abl, "edge_causal_r": edge,
            "edge_placebo_r": edge_pl, "edge_oracle_r": edge_or,
            "leakage_verdict": verdict,
        }
        try:
            with open(args.retrieval_json, "w") as fh:
                json.dump(payload, fh, indent=2, default=_jsonable)
            print(f"  [json] resultados -> {args.retrieval_json}")
        except Exception as e:
            print(f"  [json] no se pudo escribir: {e}")

    # [FASE B] gate VIP por PERCENTIL de la expectancy del vecindario (OOS causal).
    # Aisla el decil superior por retr_expectancy_r y mide su pnl_r realizado.
    if getattr(args, "quality_gate", False):
        sub = oos[oos["pnl_r"].notna() & oos["retr_expectancy_r"].notna()]
        if len(sub) > 0:
            gate = ql.quality_gate(
                sub["retr_expectancy_r"].to_numpy(),
                sub["pnl_r"].to_numpy())
            print("\n  [VIP oro] subset por decil/percentil de la EXPECTANCY DEL "
                  "VECINDARIO (retrieval OOS):")
            print(ql.format_gate(gate, title="VIP retrieval"))
    return oos


def _dump_equity_curve(equity, args):
    """[FASE D] Vuelca la curva de equity OOS + su drawdown a JSON (si --equity-json).

    La curva es el insumo de drawdown/Calmar; emitirla permite graficarla fuera o
    auditar el peor tramo. No imprime la serie completa en el log (es larga).
    """
    if not getattr(args, "equity_json", None) or equity is None or len(equity) == 0:
        return
    import json
    eq = np.asarray(equity, dtype="float64")
    dd = met.drawdown_series(eq)
    mdd, peak_i, trough_i = met.max_drawdown(eq)
    payload = {
        "symbol": args.symbol, "exchange": args.exchange,
        "equity_curve": eq.tolist(),
        "drawdown_series": dd.tolist(),
        "max_drawdown": mdd, "peak_idx": peak_i, "trough_idx": trough_i,
        "final_equity": float(eq[-1]), "initial_equity": float(eq[0]),
    }
    try:
        with open(args.equity_json, "w") as fh:
            json.dump(payload, fh, default=_jsonable)
        print(f"  [equity] curva OOS ({len(eq)} puntos) + drawdown -> {args.equity_json}")
    except Exception as e:
        print(f"  [equity] no se pudo escribir: {e}")


def _jsonable(o):
    import numpy as _np
    if isinstance(o, (_np.floating, _np.integer)):
        return o.item()
    if isinstance(o, _np.ndarray):
        return o.tolist()
    return str(o)


def _print_ablation_table(abl):
    cols = ["n", "expectancy_r", "wr", "pf", "total_r"]
    rows = ["base", "confident", "gate_pass", "gate_block", "abstained"]
    print(f"  {'subset':<12} {'n':>6} {'exp_r':>8} {'wr':>6} {'pf':>7} {'total_r':>9}")
    for r in rows:
        s = abl.get(r, {})
        print(f"  {r:<12} {s.get('n',0):>6} {_f(s.get('expectancy_r')):>8} "
              f"{_f(s.get('wr')):>6} {_f(s.get('pf')):>7} {_f(s.get('total_r')):>9}")


def _parse_int_list(s):
    """'96,288,576' -> [96, 288, 576]. Vacio/None -> []."""
    if not s:
        return []
    return [int(x) for x in str(s).replace(" ", "").split(",") if x]


def _tp_frontier_rows(df_primary, recs, max_bars):
    """Reetiqueta los mismos eventos en tp1..tp4 a UN horizonte y resume.

    tp4 entra porque en el motor tp3 == tp2 (calculate_levels: tp3 = entry +
    rng*PHI_INV, identico a tp2), asi que la fila tp3 NO aporta un target mas
    lejano. tp4 (= entry + rng) es el unico target genuinamente distante para el
    test de alcance (avg_MFE vs rr). Eventos viejos sin px_tp4 caen por el guard
    de None de abajo (la fila tp4 sale vacia hasta el proximo replay).
    """
    rows = []
    for lvl in ("tp1", "tp2", "tp3", "tp4"):
        col = f"px_{lvl}"
        sub = [dict(r, target_price=r[col]) for r in recs
               if r.get(col) is not None and not pd.isna(r.get(col))]
        if not sub:
            continue
        lab = lb.label_events(df_primary, sub, max_bars=max_bars)
        s = lb.label_summary(lab)
        if s is None:
            continue
        rows.append({
            "TP": lvl, "n": s["n"], "WR": round(s["win_rate"], 3),
            "exp_R": round(s["expectancy_r"], 3), "total_R": round(s["total_r"], 1),
            "W/L/T": f"{s['wins']}/{s['losses']}/{s['timeouts']}",
            "avg_MFE": round(s["avg_mfe_r"], 2), "avg_MAE": round(s["avg_mae_r"], 2),
        })
    return rows


def _print_tp_frontier(df_primary, events, horizons):
    """Frontera TP x horizonte desde UN SOLO replay.

    El replay (recorrer el historico disparando el motor) es el ~99% del costo;
    TANTO el nivel de TP COMO el horizonte (barrera vertical) son post-replay y
    solo cambian el ETIQUETADO (barato). Asi medimos el trade-off WR<->R de los
    tres targets a varios horizontes sin re-replicar. In-sample es legitimo aqui:
    TP y horizonte son FIJOS por celda, no se ajusta ningun parametro -> no hay
    sobreajuste que validar (eso es para el modelo/umbral).
    """
    if events is None or len(events) == 0:
        return
    recs = events.to_dict("records")
    multi = len(horizons) > 1
    suffix = f"; horizontes {horizons} velas" if multi else ""
    print(f"\n[1.5/4] Frontera TP (mismo replay, reetiquetado tp1/tp2/tp3{suffix}):")
    any_rows = False
    for h in horizons:
        rows = _tp_frontier_rows(df_primary, recs, h)
        if not rows:
            continue
        any_rows = True
        if multi:
            print(f"\n  -- horizonte = {h} velas --")
        print(pd.DataFrame(rows).to_string(index=False))
    if any_rows:
        print("  WR baja y exp_R sube al alejar el TP: ese es el trade-off. "
              "avg_MFE = recorrido tipico en R (si << rr del TP, el TP no se "
              "alcanza). Horizonte mas largo da mas chance al TP lejano.")


def _parse_float_list(s):
    """'0.5,1.0,2.0' -> [0.5, 1.0, 2.0]. Vacio/None -> []."""
    if not s:
        return []
    return [float(x) for x in str(s).replace(" ", "").split(",") if x]


def _print_tp_sl_grid(df_primary, events, args, sim_kwargs, bar_minutes):
    """[FASE C] Grid post-replay SL(xATR) x TP -> tabla con exp_R/WR/Calmar OOS.

    Re-etiqueta el MISMO conjunto fired variando ancho de SL (multiplos de ATR) y
    nivel de TP, sin re-replicar el motor. Elige el optimo por Calmar (fallback
    expectancy). El horizonte es el primero del sweep (o --max-bars).
    """
    if events is None or len(events) == 0:
        return
    sl_mults = _parse_float_list(args.sl_mults)
    tp_levels = [t.strip() for t in str(args.grid_tps).split(",") if t.strip()]
    horizon = (_parse_int_list(args.horizon_sweep) or [args.max_bars])[0]
    print(f"\n[1.6/4] Grid SL(xATR) x TP (post-replay; horizonte={horizon} velas; "
          f"OOS si la muestra alcanza, si no in-sample):")
    grid = opt.tp_sl_grid(
        df_primary, events, sl_mults, tp_levels, horizon,
        sim_kwargs=sim_kwargs, n_splits=args.n_splits, embargo=args.embargo,
        bar_minutes=bar_minutes)
    if grid is None or len(grid) == 0:
        print("  (sin celdas evaluables: faltan px_tp o ATR en las senales)")
        return
    show = grid.copy()
    for c in ("exp_R", "WR", "total_R", "calmar", "max_dd"):
        show[c] = show[c].map(lambda v: round(v, 3) if v is not None and
                              not (isinstance(v, float) and pd.isna(v)) else None)
    print(show.to_string(index=False))
    best = opt.choose_optimum(grid, by="calmar")
    if best is not None:
        print(f"  >> OPTIMO (por Calmar): SL={best['SL_xATR']}xATR TP={best['TP']} "
              f"exp_R={_f(best['exp_R'])} WR={_f(best['WR'])} "
              f"calmar={_f(best['calmar'])} max_dd={_f(best['max_dd'])} "
              f"n={best['n']} ({'OOS' if best['oos'] else 'in-sample'})")
    print("  Nota: tp3 omitido (== tp2 en calculate_levels del motor; ver bt_optimize).")


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
