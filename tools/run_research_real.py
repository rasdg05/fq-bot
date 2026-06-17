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
import json
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
import retrieval_gate as rg
import segment_veto as sv


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
    import killzones_pd as _kzpd
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
    # MISMA inyeccion para killzones_pd (descubierto jun-2026, run #26 vs #28):
    # current_killzone() y get_legacy_session() leian datetime.now(CDMX) ->
    # TODA la historia heredaba la killzone/sesion de la hora en que corria el
    # CI, y eso alimenta Fase D (w_killzone / w_clock_legacy -> w_effective ->
    # p_master). Un run en horario NY (run #26: silver_bullet w=1.40 para cada
    # vela de 24 meses) disparo 629 senales de SOL; el mismo codigo+datos+seed
    # de madrugada CDMX (run #28: pesos asia 0.50) disparo 226. Con el bar-clock
    # cada vela se juzga en SU killzone historica: backtest = bot en vivo e
    # independiente de la hora del click. is_weekend_closed (UTC) se deja
    # intacto a proposito: WEEKEND_ADMIN_ONLY ya lo neutraliza en research.
    _kzpd.datetime = _BarClockDatetime

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


def _print_execution_frontier(labeled, folds, valid_index, sim_kwargs, ppy):
    """[2.2/4] Frontera de ejecucion: las MISMAS senales OOS bajo escenarios
    de fees maker/taker (CostModel.maker_*). Gratis (re-simular, no re-replicar).

    Es el TECHO: asume fill 100% en la limite (adverse selection no modelada).
    La captura realista la mide el paper con FQ_GOLD_MAKER_SIM (RETRIEVAL_PLAN
    §6.10). El stop SIEMPRE taker. Sirve para decidir si vale la pena pagar el
    fill-model forward, no para declarar victoria.
    """
    from dataclasses import replace
    base_cost = sim_kwargs.get("cost") or eng.CostModel()
    escenarios = [
        ("taker/taker (actual)", base_cost),
        ("entrada maker", replace(base_cost, maker_entry=True)),
        ("entrada+TP maker", replace(base_cost, maker_entry=True,
                                     maker_tp_exit=True)),
    ]
    print("\n[2.2/4] Frontera de ejecucion (techo maker; fill 100% asumido, "
          f"maker_fee={base_cost.maker_fee}):")
    rows = []
    for name, c in escenarios:
        kw = dict(sim_kwargs)
        kw["cost"] = c
        m, n, _eq = _oos_metrics(labeled, folds, valid_index, kw, ppy)
        rows.append({"escenario": name, "n": n,
                     "exp_R": m.get("expectancy_r"),
                     "PF": m.get("profit_factor"),
                     "total_R": m.get("total_r"),
                     "maxDD": m.get("max_drawdown")})
    print(pd.DataFrame(rows).to_string(
        index=False, float_format=lambda v: f"{v:8.4f}"))


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
    # --- Eje A: ablacion del vector (base vs +bloque quantum/tiempo emergente) ---
    p.add_argument("--vector-ablation", action="store_true",
                   help="[Eje A] mide el LIFT del bloque quantum (kappa/sigma_tau/sync/"
                        "campo) en el edge de retrieval, sobre las senales fired (barato)")
    p.add_argument("--emergent-time", action="store_true",
                   help="corre el replay con FQ_EMERGENT_TIME_ENABLED=1 (Phase E): "
                        "sync_score/sigma_tau pasan a estar VIVOS. OJO: cambia el set de "
                        "senales (el motor veta por sync), asi que es un experimento aparte")
    # --- prueba FORWARD / out-of-time (proof of work; escalón antes de capital) ---
    p.add_argument("--out-of-time", default=None,
                   help="fecha de corte (p.ej. 2025-06-01): congela el modelo con "
                        "lo ANTERIOR y evalua SOLO la ventana posterior + calibracion "
                        "predicho-vs-realizado. El test sin fuga por construccion")
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
    # --- F2.5: edge por segmento (fractales legibles) ---
    p.add_argument("--segments-out", default=None,
                   help="ruta csv para la tabla completa de edge por segmento "
                        "(killzone / bloque horario / dia / node_type / "
                        "direccion / bias). Radar de fractales explotables; "
                        "post-replay, cero coste")
    # --- F3 (datos): cubo (TP x horizonte) POR EVENTO, persistido ---
    p.add_argument("--tp-cube-out", default=None,
                   help="ruta parquet/csv para el cubo por evento (bt_labeler."
                        "label_events_grid, formato largo: evento x TP x "
                        "horizonte + features). Es la tabla que entrena el "
                        "selector F3 (TP/horizonte por vecindario); se acumula "
                        "run a run como artefacto. Re-etiquetado post-replay: "
                        "cero replays extra")
    # --- SHARDING por fecha (cosecha paralela; ver tools/cosecha_shard.py) ---
    p.add_argument("--date-start", default=None,
                   help="ISO (YYYY-MM-DD): solo eventos con entry_ts >= esto. El "
                        "replay recorta los dfs a [date_start-lookback, date_end+"
                        "horizonte] (indicadores ya computados -> seguro). Permite "
                        "shardear el replay por fecha y mergear los cubos.")
    p.add_argument("--date-end", default=None,
                   help="ISO: solo eventos con entry_ts < esto (rango del shard).")
    # --- PODA SHARDED (ver tools/ablation_shard.py): emite/consume eventos crudos
    # para paralelizar la ablacion por fecha SIN reescribir la metrica. ---
    p.add_argument("--events-out", default=None,
                   help="ruta parquet: corre SOLO el replay fires-only (rapido, con "
                        "los toggles de modulo que vengan por env), filtra al rango "
                        "del shard y vuelca los eventos crudos. NO etiqueta/modela. "
                        "Es el emisor por-shard de la poda sharded.")
    p.add_argument("--events-in", default=None,
                   help="ruta parquet: SALTA el replay y carga eventos ya mergeados; "
                        "corre el MISMO label+fold+OOS de siempre sobre ellos. Para "
                        "computar la metrica de una variante sobre el cubo de eventos "
                        "sharded-mergeado (correctitud: misma ruta que el run normal).")
    p.add_argument("--metric-out", default=None,
                   help="ruta json: con --events-in, vuelca {expectancy_r, n_fired, "
                        "n_oos} de la variante y termina (sin modelo/retrieval).")
    # --- GATEADO SHARDED (ver tools/gated_shard.py): emite/consume ESTADOS DENSOS
    # (todas las velas, no solo fired) para paralelizar el replay denso por fecha y
    # correr el analisis gateado+retrieval+OOT UNA vez sobre el merge. Analogo denso
    # de --events-out/--events-in (que son fires-only para la poda). ---
    p.add_argument("--states-out", default=None,
                   help="ruta parquet: corre SOLO el replay DENSO (estado de CADA "
                        "vela), filtra los estados al rango del shard por entry_ts y "
                        "vuelca TODO el DataFrame de estados. NO etiqueta/modela. Es "
                        "el emisor por-shard del gateado sharded (replay denso).")
    p.add_argument("--states-in", default=None,
                   help="ruta parquet: SALTA el replay y carga los estados densos ya "
                        "mergeados; re-deriva entry_index global y corre el MISMO "
                        "analisis de siempre (OOS/modelo/retrieval/quality_gate/OOT/"
                        "grids) sobre el merge. Misma ruta que el run normal.")
    # --- FASE C: grid post-replay de SL (xATR) x TP (tp1..tp4) ---
    p.add_argument("--tp-sl-grid", action="store_true",
                   help="re-etiqueta el MISMO conjunto fired variando ancho de SL "
                        "(multiplos de ATR) y nivel de TP -> tabla SL x TP con "
                        "expectancy/WR/Calmar (post-replay, cero replays extra)")
    p.add_argument("--sl-mults", default="0.5,1.0,1.5,2.0",
                   help="multiplos de ATR para el ancho de SL del grid (coma)")
    p.add_argument("--grid-tps", default="tp1,tp2,tp3,tp4",
                   help="niveles de TP del grid (coma). tp3 ya es distinto de tp2 "
                        "(fix jun-2026): cuatro peldanos reales")
    # --- FASE B: gate de calidad 'VIP oro' (decil superior OOS) ---
    p.add_argument("--quality-gate", action="store_true",
                   help="aisla el decil/percentil superior del score del modelo y de "
                        "la expectancy del vecindario del retrieval (OOS) y reporta "
                        "WR/expectancy/total_r/max_dd del subset VIP vs el total")
    # --- F2: persiste el gate ORO (indice de retrieval + umbral) en una corrida ---
    p.add_argument("--build-index", action="store_true",
                   help="tras el retrieval denso, calibra el umbral oro (top_pct) y "
                        "persiste el gate (indice+scaler+outcomes+meta) para el live")
    p.add_argument("--index-out", default=None,
                   help="dir del artefacto del gate (default: retrieval/<ex>/<sym>)")
    p.add_argument("--gold-top-pct", type=float, default=0.05,
                   help="percentil que define ORO (0.05 = top 5%, lo validado en F1)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("=" * 70)
    print("  HARNESS DE RESEARCH FQ — runner REAL (motor de produccion)")
    print("=" * 70)

    # Eje A: para que sync_score/sigma_tau (tiempo emergente) esten VIVOS en el
    # vector, el replay debe correr con Phase E ON. Se fija ANTES del replay; el
    # reload de modulos en _run_replay lo recoge. Cambia el set de senales.
    if getattr(args, "emergent_time", False):
        os.environ["FQ_EMERGENT_TIME_ENABLED"] = "1"
        print("\n[Eje A] FQ_EMERGENT_TIME_ENABLED=1 (Phase E ON; sync/sigma_tau vivos; "
              "el set de senales cambia)")

    # --- datos ---
    prim_tf, mid_tf, high_tf, sub_tf = TF_STACK[args.tf_id]
    df_primary = _load_tf(args.exchange, args.symbol, prim_tf, args.data_dir)
    if df_primary is None:
        sys.exit(f"falta el dataset {prim_tf}; corre tools/build_dataset.py primero")
    df_mid = _load_tf(args.exchange, args.symbol, mid_tf, args.data_dir)
    df_high = _load_tf(args.exchange, args.symbol, high_tf, args.data_dir)
    df_sub = _load_tf(args.exchange, args.symbol, sub_tf, args.data_dir)
    tfs = (df_primary, df_mid, df_high, df_sub)

    # SHARDING por fecha: recorta los dfs a [date_start-lookback, date_end+horizonte]
    # (indicadores ya computados en _load_tf sobre el df COMPLETO -> recortar es
    # seguro). El warmup del replay (min_lookback) consume el buffer-izq y los
    # eventos arrancan en ~date_start; el buffer-der da la ventana de labeling.
    # Mas abajo se filtran los eventos a [date_start, date_end). Cero solape entre
    # shards adyacentes. Ver tools/cosecha_shard.py.
    _date_start = pd.to_datetime(args.date_start) if args.date_start else None
    _date_end = pd.to_datetime(args.date_end) if args.date_end else None
    if _date_start is not None or _date_end is not None:
        _bm = TF_MINUTES.get(prim_tf, 15.0)
        _maxh = max([args.dense_horizon, args.max_bars]
                    + (_parse_int_list(args.horizon_sweep) or []))
        _lo = (_date_start - pd.Timedelta(minutes=_bm * args.min_lookback)
               if _date_start is not None else None)
        _hi = (_date_end + pd.Timedelta(minutes=_bm * _maxh)
               if _date_end is not None else None)

        def _slice_win(df):
            if df is None:
                return None
            ts = pd.to_datetime(df["timestamp"])
            keep = pd.Series(True, index=df.index)
            if _lo is not None:
                keep &= ts >= _lo
            if _hi is not None:
                keep &= ts <= _hi
            return df[keep.to_numpy()].reset_index(drop=True)
        df_primary, df_mid, df_high, df_sub = (_slice_win(d) for d in tfs)
        tfs = (df_primary, df_mid, df_high, df_sub)
        print(f"[shard] eventos [{args.date_start}..{args.date_end}); ventana "
              f"{prim_tf}: {len(df_primary)} velas (buffer lookback+horizonte)")

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

    # PODA SHARDED — EMISOR por-shard (--events-out): SOLO replay fires-only
    # (rapido), filtra al rango del shard y vuelca eventos crudos. Sin labeling/
    # modelo/retrieval. Los toggles de modulo (FQ_USE_SCORER/REGIME, FQ_SESSION_BIAS)
    # llegan por env del subproceso -> _run_replay recarga modulos y los recoge.
    # Ver tools/ablation_shard.py.
    if args.events_out:
        print("\n[poda-shard] replay fires-only del motor (emisor de eventos)...")
        ev = _run_replay(
            tfs, env_overrides=None, seed=args.seed, tf_id=args.tf_id,
            min_lookback=args.min_lookback, step=args.step,
            target_level=args.target_level,
        )
        if (_date_start is not None or _date_end is not None) and len(ev):
            _ets = pd.to_datetime(ev["entry_ts"])
            _km = pd.Series(True, index=ev.index)
            if _date_start is not None:
                _km &= _ets >= _date_start
            if _date_end is not None:
                _km &= _ets < _date_end
            ev = ev[_km.to_numpy()].reset_index(drop=True)
        ev.to_parquet(args.events_out, index=False)
        print(f"[events-out] {len(ev)} eventos -> {args.events_out}")
        return

    # GATEADO SHARDED — EMISOR por-shard (--states-out): replay DENSO (estado de
    # CADA vela, igual que la rama 'else' normal), filtra los estados al rango del
    # shard por entry_ts y vuelca TODO el DataFrame (no solo los fired). El analisis
    # gateado+retrieval+OOT corre UNA vez sobre el merge via --states-in. Ver
    # tools/gated_shard.py.
    if args.states_out:
        print("\n[gated-shard] replay DENSO del motor (emisor de estados)...")
        states = _run_replay(
            tfs, env_overrides=None, seed=args.seed, tf_id=args.tf_id,
            dense=True, horizon_bars=args.dense_horizon,
            min_lookback=args.min_lookback, step=args.step,
            target_level=args.target_level, progress_every=5000,
        )
        # SHARD: quedarse SOLO con los estados del rango [date_start, date_end) (los
        # del warmup-izq y el buffer-der pertenecen a shards vecinos). entry_ts es
        # global -> el merge por entry_ts no duplica ni pierde. MISMO filtro que los
        # eventos, pero sobre TODOS los estados (no solo fired).
        if (_date_start is not None or _date_end is not None) and len(states):
            _ets = pd.to_datetime(states["entry_ts"])
            _km = pd.Series(True, index=states.index)
            if _date_start is not None:
                _km &= _ets >= _date_start
            if _date_end is not None:
                _km &= _ets < _date_end
            states = states[_km.to_numpy()].reset_index(drop=True)
        states.to_parquet(args.states_out, index=False)
        print(f"[states-out] {len(states)} estados -> {args.states_out}")
        return

    if args.events_in:
        # PODA SHARDED — CONSUMIDOR (--events-in): SALTA el replay y carga los
        # eventos ya mergeados (cubo sharded de UNA variante). Todo lo de abajo
        # (label+fold+OOS) corre IDENTICO al run normal -> la metrica de la variante
        # es la misma que sin shardear (correctitud por reuso de la ruta).
        print(f"\n[poda-shard] eventos mergeados (sin replay) <- {args.events_in}")
        states = None
        events = pd.read_parquet(args.events_in)
        events["entry_ts"] = pd.to_datetime(events["entry_ts"])
        # entry_index viene LOCAL al slice de cada shard; label_events lo usa como
        # df.iloc[entry_index+1:] y folds_from_labeled ORDENA por el -> hay que
        # RE-DERIVARLO global: entry_ts -> posicion en el df_primary COMPLETO. Asi
        # label/fold/OOS reproducen EXACTO el run sin shardear (entry_price/stop/
        # target del evento son precios -> sobreviven el merge sin tocar).
        _idx = pd.Series(range(len(df_primary)),
                         index=pd.to_datetime(df_primary["timestamp"]).to_numpy())
        events["entry_index"] = events["entry_ts"].map(_idx)
        _miss = int(events["entry_index"].isna().sum())
        if _miss:
            print(f"  [aviso] {_miss} eventos sin match de entry_ts en df_primary "
                  "(descartados)")
            events = events[events["entry_index"].notna()]
        events["entry_index"] = events["entry_index"].astype(int)
        events = events.sort_values("entry_index").reset_index(drop=True)
        n_states = len(events)
    elif args.states_in:
        # GATEADO SHARDED — CONSUMIDOR (--states-in): SALTA el replay y carga los
        # ESTADOS DENSOS ya mergeados (cubo sharded de todas las velas). Re-deriva el
        # entry_index global desde entry_ts (igual que --events-in: el index venia
        # LOCAL al slice de cada shard, y label_events/folds_from_labeled lo usan) y
        # deja que el resto de main() corra IDENTICO al run normal (OOS/modelo/
        # retrieval denso/quality_gate/OOT/grids usan `states` y `events`). Es la
        # MISMA rama que el `else` de abajo pero sin replay. Ver tools/gated_shard.py.
        print(f"\n[gated-shard] estados densos mergeados (sin replay) <- {args.states_in}")
        states = pd.read_parquet(args.states_in)
        states["entry_ts"] = pd.to_datetime(states["entry_ts"])
        _idx = pd.Series(range(len(df_primary)),
                         index=pd.to_datetime(df_primary["timestamp"]).to_numpy())
        states["entry_index"] = states["entry_ts"].map(_idx)
        _miss = int(states["entry_index"].isna().sum())
        if _miss:
            print(f"  [aviso] {_miss} estados sin match de entry_ts en df_primary "
                  "(descartados)")
            states = states[states["entry_index"].notna()]
        states["entry_index"] = states["entry_index"].astype(int)
        states = states.sort_values("entry_index").reset_index(drop=True)
        n_states = len(states)
        if n_states == 0:
            sys.exit("el merge de estados vino vacio; revisa los shards / el rango")
        events = (states[states["fired"]].reset_index(drop=True)
                  if "fired" in states.columns else states.iloc[0:0])
        print(f"  estados densos: {n_states} | senales disparadas (fired): {len(events)}")
    else:
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
        # SHARD: quedarse SOLO con los eventos del rango [date_start, date_end) de este
        # shard (los del warmup-izq y el buffer-der de labeling pertenecen a shards
        # vecinos). entry_ts es global -> el merge por entry_ts no duplica ni pierde.
        if (_date_start is not None or _date_end is not None) and len(events):
            _ets = pd.to_datetime(events["entry_ts"])
            _km = pd.Series(True, index=events.index)
            if _date_start is not None:
                _km &= _ets >= _date_start
            if _date_end is not None:
                _km &= _ets < _date_end
            events = events[_km.to_numpy()].reset_index(drop=True)
            print(f"  [shard] eventos en rango: {len(events)}")
        print(f"  estados densos: {n_states} | senales disparadas (fired): {len(events)}")
    if states is not None:
        _print_decision_funnel(states, args)

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
        if args.tp_cube_out:
            _dump_tp_cube(df_primary, events, horizons, args)
        if args.tp_sl_grid:
            _print_tp_sl_grid(df_primary, events, args, sim_kwargs, bar_minutes)
            _print_tp_horizon_grid(df_primary, events, args, sim_kwargs,
                                   bar_minutes, horizons)
    else:
        labeled = None
        print("  (el motor no disparo ninguna senal valida; se omite el research de "
              "senales, pero el retrieval denso sigue abajo)")

    # F2.6 (§6.8) — VETO DE SESION integrado. Default OFF (FQ_SEGMENT_VETO_*="").
    # Filtra la poblacion ETIQUETADA por killzone / bloque-UTC / dia de la VELA:
    # TODO lo de abajo (OOS [2/4], frontera maker [2.2/4], segmentos [2.5/4],
    # modelo, retrieval/leakage) mide la cartera CON el veto. El cubo (events) NO
    # se toca -> queda integro para el regrade offline de cualquier otro corte.
    # Mismo predicado (segment_veto) que tools/regrade_events.py y el loop vivo.
    if labeled is not None and len(labeled):
        _veto = sv.from_env()
        if _veto.active:
            _vmask = _veto.mask(labeled)
            print("\n  [veto sesion §6.8] %s -> caen %d/%d; la poblacion "
                  "restante alimenta OOS/frontera/segmentos/retrieval"
                  % (_veto.describe(), int(_vmask.sum()), len(labeled)))
            labeled = labeled[~_vmask].reset_index(drop=True)

    if labeled is not None and len(labeled) >= min_for_wf:
        folds, valid_index = wf.folds_from_labeled(
            labeled, n_splits=args.n_splits, embargo=args.embargo)
        ppy = _periods_per_year(labeled, bar_minutes)
        base_metrics, n_pool, base_equity = _oos_metrics(
            labeled, folds, valid_index, sim_kwargs, ppy)
        base_metric = base_metrics.get("expectancy_r")
        print("\n[2/4] Metricas OOS de senales (con fees+slippage+funding):")
        print(met.format_report(base_metrics))
        # PODA SHARDED — con --metric-out volca la metrica de ESTA variante y
        # termina (sin modelo/retrieval: no hacen falta para el veredicto de poda).
        # Ver tools/ablation_shard.py.
        if args.metric_out:
            with open(args.metric_out, "w") as _fh:
                json.dump({"expectancy_r": (None if base_metric is None
                                            else float(base_metric)),
                           "n_fired": int(len(events)), "n_oos": int(n_pool)}, _fh)
            print(f"[metric-out] expectancy_r={base_metric} n_fired={len(events)} "
                  f"n_oos={n_pool} -> {args.metric_out}")
            return
        _dump_equity_curve(base_equity, args)
        _print_execution_frontier(labeled, folds, valid_index, sim_kwargs, ppy)
        _print_segments(labeled, folds, valid_index, args)

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
            if getattr(args, "vector_ablation", False):
                _print_vector_ablation(labeled, folds, valid_index, args)
        # prueba FORWARD / out-of-time (proof of work)
        if getattr(args, "out_of_time", None):
            _run_out_of_time(labeled, args, sim_kwargs, bar_minutes)
    elif labeled is not None:
        print(f"\n  [guard] {len(events)} senales < {min_for_wf} para walk-forward "
              f"de {args.n_splits} folds: se omiten OOS/modelo de senales (el track "
              f"record de arriba es valido). Sube historia (--years) o baja --step.")
        _print_segments(labeled, None, None, args)

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
            idx_out = None
            if args.build_index:
                idx_out = args.index_out or os.path.join(
                    "retrieval", args.exchange, args.symbol.replace("/", "_"))
            _run_retrieval_diagnostic(states, dfolds, dvalid, args,
                                      build_index_dir=idx_out)

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
    # NOTA: la poda GitHub-hosted está sizeada para 3 toggles (="triplica el coste")
    # bajo el techo de 350min. volume_quality (FQ_VOL_GATE_ENABLED) e ICT
    # (FQ_ENABLE_ICT) son candidatos a pesar, pero un 4º replay NO cabe ahí → se
    # miden en una corrida con headroom (self-hosted, sin tope). emergent_time NO
    # entra nunca: acoplado al gate ORO (qt_sync_score/qt_sigma_tau), sin off limpio.
    # Modulos cuyas features alimentan el VECTOR del gate ORO (DEFAULT_NUMERIC
    # en bt_retrieval): apagarlos en prod desalinea la query del indice aunque
    # su delta de motor sea 0 -> NO son "peso muerto removible" (§6.6). Avisar.
    gate_coupled = {"scorer", "regime"}
    n_base = len(events)
    print(f"  baseline expectancy_r={_f(base_metric)} (n_oos={n_pool}, "
          f"n_fired={n_base})")
    print("  regla §6.6: MATAR solo si delta<=0 Y la cadencia sube >=20% "
          "(quitarlo no daña Y compra señales); si no, el modulo se queda.")
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
            dn = (len(ev2) - n_base) / n_base if n_base else 0.0
            # Veredicto fiel a la regla §6.6, no el binario delta>0.
            if delta is None:
                verdict = "?    "
            elif delta > 0:
                verdict = "VIVE "                      # quitarlo EMPEORA -> aporta
            elif dn >= 0.20:
                verdict = "MATAR"                      # no daña Y compra cadencia
            else:
                verdict = "QUEDA"                      # inerte: no daña pero no paga cadencia
            flag = "  [acoplado al gate ORO: NO apagar en prod]" \
                if name in gate_coupled else ""
            print(f"  [{verdict}] {name:<14} sin_el expectancy_r={_f(without)} "
                  f"delta={_f(delta)}  (n={len(ev2)}, dn={dn:+.0%}){flag}")
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


def _print_vector_ablation(labeled, folds, valid_index, args):
    """[Eje A] Ablación del vector: base vs base+BLOQUE QUANTUM (tiempo emergente /
    excitación de campo / convicción adaptativa). Mide si esas coordenadas suben el
    EDGE de retrieval (gate_pass − base) OOS. Read-only, sobre las señales fired
    (esparso = barato). Si qt_sync/qt_sigma salen planas, re-corre con
    --emergent-time (FQ_EMERGENT_TIME_ENABLED=1) para que el tiempo emergente viva.
    """
    print("\n  -- [Eje A] ablación de vector: base vs +quantum (tiempo emergente) --")
    common = dict(backend=args.retrieval_backend, bit_width=args.retrieval_bit,
                  k=args.retrieval_k, sim_floor=args.retrieval_sim_floor,
                  n_floor=args.retrieval_nfloor, decay_bars=args.retrieval_decay_bars,
                  seed=args.seed, query_step=getattr(args, "retrieval_query_step", 1))
    edges = {}
    for name, vec in rt.vector_variants().items():
        try:
            oos = rt.retrieval_oos(labeled, folds, valid_index, mode="causal",
                                   vectorizer=vec, **common)
            e = rt.retrieval_ablation(oos, gate_threshold=0.0).get("edge_vs_base_r")
        except Exception as ex:
            print(f"  ({name}: no disponible: {ex})")
            e = None
        edges[name] = e
        print(f"  vector={name:<8} dim={getattr(vec, 'dim', '?')} "
              f"edge_retrieval={_f(e)} R/trade")
    b, q = edges.get("base"), edges.get("quantum")
    if b is not None and q is not None and not (isinstance(b, float) and np.isnan(b)):
        lift = q - b
        verdict = "SUMA" if lift > 0 else "NO SUMA"
        print(f"  >> LIFT del bloque quantum = {_f(lift)} R/trade  [{verdict}]")
        print("     (positivo y robusto a leakage = el tiempo emergente / "
              "excitación de campo aporta edge medible)")
    # DECOUPLING (§6.6): edge del gate SIN scorer/regime (solo si FQ_RETRIEVAL_DECOUPLE
    # las pidió). Si el edge NO cae vs base, esas features no cargan el gate -> el
    # módulo es REMOVIBLE del motor (cortar motor + reconstruir índice sin desalinear).
    if b is not None and not (isinstance(b, float) and np.isnan(b)):
        for g in ("scorer", "regime"):
            de = edges.get("no_%s" % g)
            if de is None or (isinstance(de, float) and np.isnan(de)):
                continue
            drop = b - de   # cuánto CAE el edge del gate al sacar la feature
            print(f"  >> gate SIN {g}: edge={_f(de)} vs base={_f(b)} (cae {_f(drop)}) "
                  f"-> {'el GATE la NECESITA (no decouplear)' if drop > 0 else 'DECOUPLEABLE (no aporta al gate)'}")


def _resolve_lgbm_factory():
    """Factory del modelo (tr.make_lgbm_classifier) para la prueba forward: la
    devuelve si lightgbm importa Y el classifier construye (requiere scikit-learn /
    libgomp1); si no, nombra la causa real y devuelve None (el forward se omite sin
    romper, no crashea). Misma comprobacion que el modelo del walk-forward [3/4]."""
    try:
        import lightgbm  # noqa: F401
    except ImportError:
        print("  [skip] lightgbm no instalado; omito el modelo forward.")
        return None
    try:
        tr.make_lgbm_classifier()
    except Exception as e:
        print("  [WARN] lightgbm importa pero LGBMClassifier no construye:")
        print(f"         {type(e).__name__}: {e}")
        print("         Causa habitual: falta scikit-learn (o libgomp1). Forward OMITIDO.")
        return None
    return tr.make_lgbm_classifier


def _run_out_of_time(labeled, args, sim_kwargs, bar_minutes):
    """[forward] Prueba out-of-time: congela el modelo con lo ANTERIOR al corte y
    evalúa SOLO la ventana posterior (jamás vista) + calibración predicho-vs-
    realizado. Es el escalón de rigor previo a capital: sin fuga por construcción.
    """
    import bt_forward as fw
    try:
        before, after = fw.out_of_time_split(labeled, args.out_of_time)
    except Exception as e:
        print(f"\n[forward] out-of-time: no se pudo dividir ({e})")
        return
    print(f"\n[forward] OUT-OF-TIME corte={args.out_of_time}: "
          f"before={len(before)} after={len(after)} (la ventana 'after' es jamás vista)")
    if len(before) < 30 or len(after) < 10:
        print("  (muestra insuficiente a un lado del corte; mueve el corte o sube historia)")
        return
    fac = _resolve_lgbm_factory()
    if fac is None:
        return
    feat_cols = bf._numeric_feature_columns(labeled)
    try:
        scored, _ = fw.freeze_predict(before, after, feat_cols, fac)
    except Exception as e:
        print(f"  (no se pudo congelar el modelo: {e})")
        return
    m = fw.forward_metrics(after, sim_kwargs=sim_kwargs, bar_minutes=bar_minutes)
    if m is not None:
        print("  Métricas FORWARD (net de costes, ventana posterior):")
        print(met.format_report(m))
    sc = scored["fwd_score"].to_numpy()
    win = (scored["outcome"] == lb.WIN).astype(float).to_numpy()
    tab, err = fw.calibration_table(sc, win, n_bins=5)
    if len(tab):
        print("  Calibración (score predicho vs WR realizada, por bin):")
        print(tab.to_string(index=False))
        print(f"  >> error de calibración (MAE ponderado) = {_f(err)} "
              f"(0 = perfecto; alto = el modelo miente sobre la magnitud)")
    exp_tab, _e = fw.calibration_table(sc, scored["pnl_r"].to_numpy(), n_bins=5)
    if len(exp_tab):
        print("  Expectancy realizada (R) por bin de score predicho:")
        print(exp_tab.rename(columns={"real_mean": "exp_R"}).to_string(index=False))
    print("  Próximo escalón: reconcile() compara la expectancy VIVA del ledger "
          "contra el IC del backtest (alarma de drift).")


def _run_retrieval_diagnostic(labeled, folds, valid_index, args, build_index_dir=None):
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

    # [F2] persiste el gate ORO desde ESTE mismo replay (un solo replay):
    # calibra el umbral con la expectancy del vecindario (confident, causal) e
    # indexa TODOS los estados resueltos. NO persiste si el leakage no paso.
    if build_index_dir:
        if verdict != "OK":
            print(f"  [index] NO se persiste: leakage={verdict} "
                  f"(causal={_f(edge)} placebo={_f(edge_pl)}); el edge no es limpio.")
        else:
            try:
                conf = oos[~oos["retr_abstain"].astype(bool)]
                top_pct = getattr(args, "gold_top_pct", 0.05)
                thr = rg.calibrate_gold_threshold(
                    conf["retr_expectancy_r"].to_numpy(), top_pct=top_pct)
                idx = rg.StateIndex.build(labeled, backend=args.retrieval_backend,
                                          bit_width=args.retrieval_bit)
                gate = rg.GoldGate(idx, thr, k=args.retrieval_k,
                                   sim_floor=args.retrieval_sim_floor,
                                   n_floor=common["n_floor"],
                                   decay_bars=args.retrieval_decay_bars)
                gate.save(build_index_dir, backend=args.retrieval_backend, meta_extra={
                    "symbol": args.symbol, "exchange": args.exchange,
                    "tf_id": args.tf_id, "dense_horizon": args.dense_horizon,
                    "gold_top_pct": top_pct, "bit_width": args.retrieval_bit,
                    "n_states": int(len(labeled)), "n_confident": int(len(conf)),
                    "edge_causal_r": edge, "edge_placebo_r": edge_pl,
                    "leakage_ok": True, "seed": args.seed})
                print(f"  [index] gate ORO persistido -> {build_index_dir} "
                      f"(umbral retr_expectancy_r={_f(thr)}, n_confident={len(conf)})")
            except Exception as e:
                print(f"  [index] no se pudo construir/persistir: {e}")

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


def _print_decision_funnel(states, args):
    """[1.4/4] FUNNEL de cadencia: donde mueren las velas candidatas.

    El replay denso YA evaluo el motor en cada vela; agrupar (decision,
    failed_at) es gratis y es el diagnostico previo a la poda: dice QUE gate
    mata candidatos (la poda OOS dice si ese gate paga su sitio antes de
    relajarlo). Ver RETRIEVAL_PLAN §6.6 (F2.5 cadencia).
    """
    funnel = bf.decision_funnel(states)
    if len(funnel) == 0:
        return
    print("\n[1.4/4] Funnel del motor (en que decision/gate muere cada vela):")
    print("  " + funnel.to_string(index=False).replace("\n", "\n  "))
    # near-miss del gate de conviccion: cuanta cadencia hay a un paso del
    # umbral (si p90 esta pegado a PMASTER_MIN, el headroom es real; si esta
    # lejos, relajar el umbral no compra cadencia util).
    near = states[states["decision"] == "math_below_threshold"]
    if len(near) and "p_master" in near.columns:
        pm = pd.to_numeric(near["p_master"], errors="coerce").dropna()
        if len(pm):
            thr = None
            try:
                import fq_bot_v3_2 as _b
                thr = _build_config(_b, tf_id=args.tf_id).get("PMASTER_MIN")
            except Exception:
                pass
            q = pm.quantile([0.5, 0.75, 0.9])
            print(f"  near-miss p_master (n={len(pm)}): mediana={q[0.5]:.3f} "
                  f"p75={q[0.75]:.3f} p90={q[0.9]:.3f} max={pm.max():.3f}"
                  + (f"  (gate PMASTER_MIN={thr})" if thr is not None else ""))


_SEGMENT_COLS = ("field_killzone", "hora_utc_4h", "dia_semana",
                 "field_node_type", "direction", "field_bias_4h")


def _print_segments(labeled, folds, valid_index, args):
    """[2.5/4] Edge por SEGMENTO (fractales legibles): expectancy condicional
    por killzone / bloque horario UTC / dia / tipo de nodo / direccion / bias.

    Sobre la cartera OOS pooled cuando hay folds (honesto); si no, in-sample
    ETIQUETADO como tal. Es un RADAR de candidatos: con tantos cortes siempre
    hay un grupo bueno por azar -> un segmento se explota SOLO tras
    confirmarlo OOS/forward (mismo estandar que la poda; RETRIEVAL_PLAN §6.6).
    """
    try:
        if folds:
            pool = ab.pooled_oos_trades(labeled, folds, valid_index=valid_index)
            scope = "OOS (folds pooled)"
        else:
            pool, scope = labeled, "IN-SAMPLE (sin folds: solo indicativo)"
        if "pnl_r" in pool.columns:
            pool = pool[pd.to_numeric(pool["pnl_r"], errors="coerce").notna()].copy()
        if pool is None or len(pool) == 0:
            return
        if "entry_ts" in pool.columns:
            ts = pd.to_datetime(pool["entry_ts"])
            pool["hora_utc_4h"] = (ts.dt.hour // 4 * 4).map(
                lambda h: "%02d-%02dutc" % (h, h + 4))
            pool["dia_semana"] = ts.dt.dayofweek.map(dict(enumerate(
                ["lun", "mar", "mie", "jue", "vie", "sab", "dom"])))
        print(f"\n[2.5/4] Edge por segmento ({scope}; n={len(pool)}; min_n=10):")
        frames = []
        for c in (c for c in _SEGMENT_COLS if c in pool.columns):
            t = ql.segment_expectancy(pool, c)
            if len(t) == 0:
                continue
            frames.append(t.assign(segmento=c).rename(columns={c: "valor"}))
            show = t[t["ok_n"]] if bool(t["ok_n"].any()) else t.head(4)
            print(f"\n  -- {c} --")
            print("  " + show.to_string(index=False).replace("\n", "\n  "))
        print("\n  NOTA: radar de candidatos, no prueba. Un segmento se explota "
              "solo tras confirmarse OOS/forward (multiples cortes => siempre "
              "hay un 'bueno' por azar).")
        if getattr(args, "segments_out", None) and frames:
            out = args.segments_out
            d = os.path.dirname(out)
            if d:
                os.makedirs(d, exist_ok=True)
            pd.concat(frames, ignore_index=True).to_csv(out, index=False)
            print(f"  [segmentos] tabla completa -> {out}")
    except Exception as e:
        print(f"  [segmentos] error no fatal: {e}")


def _dump_tp_cube(df_primary, events, horizons, args):
    """Persiste el cubo (TP x horizonte) POR EVENTO -- la side-table §3.2 que
    entrena el selector F3 (TP/horizonte por vecindario). El replay es el
    costo; esto es re-etiquetado (label_events_grid) + I/O, cero replays."""
    recs = events.to_dict("records")
    cube = lb.label_events_grid(
        df_primary, recs, ["px_tp1", "px_tp2", "px_tp3", "px_tp4"], horizons)
    if cube is None or len(cube) == 0:
        print("  [cube] sin filas etiquetables; no se persiste")
        return
    out = args.tp_cube_out
    d = os.path.dirname(out)
    if d:
        os.makedirs(d, exist_ok=True)
    try:
        cube.to_parquet(out, index=False)
    except Exception as e:
        out = os.path.splitext(out)[0] + ".csv"   # sin pyarrow -> csv
        cube.to_csv(out, index=False)
        print(f"  [cube] parquet no disponible ({type(e).__name__}); fallback csv")
    print(f"  [cube] {len(cube)} filas (evento x TP x horizonte, con features) "
          f"-> {out}")


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
    print("  Nota: tp3 ya es un peldano distinto (fix jun-2026); el grid lo incluye.")


def _print_tp_horizon_grid(df_primary, events, args, sim_kwargs, bar_minutes,
                           horizons):
    """[FASE C+] Frontera TP x HORIZONTE con costes y OOS (gratis post-replay).

    Complementa a _print_tp_frontier (in-sample, sin costes) y a _print_tp_sl_grid
    (SL x TP a un horizonte fijo): aqui barremos NIVEL de TP x HORIZONTE vertical
    con el stop del motor, net de costes y OOS, via el cubo de una pasada
    bt_labeler.label_events_grid (re-etiquetar todas las celdas no re-replica el
    motor). Es la 'frontera' que el selector F3 del retrieval consume.
    """
    if events is None or len(events) == 0:
        return
    tp_levels = [t.strip() for t in str(args.grid_tps).split(",") if t.strip()]
    print(f"\n[1.7/4] Frontera TP x horizonte con costes/OOS "
          f"(post-replay; horizontes={horizons} velas):")
    grid = opt.tp_horizon_grid(
        df_primary, events, tp_levels, horizons,
        sim_kwargs=sim_kwargs, n_splits=args.n_splits, embargo=args.embargo,
        bar_minutes=bar_minutes)
    if grid is None or len(grid) == 0:
        print("  (sin celdas evaluables: faltan px_tp o stop en las senales)")
        return
    show = grid.copy()
    for c in ("exp_R", "WR", "total_R", "calmar", "max_dd"):
        if c in show.columns:
            show[c] = show[c].map(lambda v: round(v, 3) if v is not None and
                                  not (isinstance(v, float) and pd.isna(v)) else None)
    print(show.to_string(index=False))
    best = opt.choose_optimum(grid, by="exp_R")
    if best is not None:
        print(f"  >> OPTIMO (por exp_R): TP={best['TP']} horizonte={best['horizon']} "
              f"exp_R={_f(best['exp_R'])} WR={_f(best['WR'])} "
              f"total_R={_f(best['total_R'])} n={best['n']} "
              f"({'OOS' if best['oos'] else 'in-sample'})")


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
