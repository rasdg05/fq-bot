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
import funding_oi as fo
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


# [P2] GATE DE SELECTIVIDAD — exclusion ESTRUCTURAL de killzones. Es un PRIOR de
# liquidez FIJO declarado A PRIORI (operar SOLO dentro de killzones definidas),
# NO un corte data-minado: "fuera" = ninguna killzone activa, "asia_open" = la
# ventana mas fina del dia. NO se elige mirando los resultados por segmento; va
# aqui como constante de modulo justamente para que sea auditable y no toqueteable
# por el run. La otra mitad de la regla (umbral de score) SI es data-driven pero
# leakage-clean (OOF para OOS; ventana BEFORE para forward). Ver _select_mask /
# _print_selectivity_gate y RETRIEVAL_PLAN (palanca P2: "operar solo el subset de
# alta expectancy").
SELECT_KILLZONE_EXCLUDE = {"fuera", "asia_open"}
SELECT_KZ_COL = "field_killzone"


def _select_mask(df, scores, score_thr, kz_col=SELECT_KZ_COL):
    """Mascara del gate de selectividad P2 (bool ndarray alineado a `df`/`scores`):

        seleccionado = (score >= score_thr) AND (killzone es liquida-activa)

    `scores` debe venir YA alineado posicionalmente a `df` (mismo orden de filas);
    el umbral `score_thr` se deriva FUERA (leakage-clean: OOF para OOS, ventana
    BEFORE para forward) y aqui solo se APLICA. La pierna de killzone excluye
    SELECT_KILLZONE_EXCLUDE (prior estructural). Si falta la columna de killzone,
    la seleccion degrada a SOLO-score (sin la pierna estructural) y el caller avisa.
    """
    s = np.asarray(scores, dtype="float64")
    keep = s >= float(score_thr)
    if kz_col in df.columns:
        kz = df[kz_col].astype("object")
        keep &= ~kz.isin(SELECT_KILLZONE_EXCLUDE).to_numpy()
    return keep


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


def _load_cross_ohlcv(exchange, symbol, tf, data_dir):
    """Carga el OHLCV CRUDO del activo cruzado (lider) al MISMO TF/exchange.

    Reusa bt_data.dataset_path (misma convencion que el primario), pero NO aplica
    add_indicators: cross_asset_features solo necesita OHLC + timestamp y calcula
    sus propias ventanas trailing. Si el Parquet NO existe, ERROR CLARO (sys.exit)
    -- nunca se omite en silencio: el cross-asset es una hipotesis que hay que
    poder medir o saber por que no se pudo.
    """
    path = bt_data.dataset_path(data_dir, exchange, symbol, tf)
    if not os.path.exists(path):
        sys.exit(
            f"--cross-asset {symbol}: falta el dataset {tf} en {path}. "
            f"Descargalo al MISMO TF/exchange que el primario:\n"
            f"  python tools/build_dataset.py --symbol {symbol} --timeframe {tf} "
            f"--market swap --years 2 --exchanges {exchange}")
    return bt_data.load_parquet(path)


def _load_funding_oi(exchange, symbol, data_dir):
    """Carga el cache de funding (obligatorio) y de OI (opcional) del simbolo.

    funding_oi.fetch_* cachean a Parquet; aqui SOLO leemos el cache (el harness no
    toca red). Si el cache de funding NO existe -> ERROR CLARO con el comando de
    descarga (igual que --cross-asset: el funding es una hipotesis medible, no se
    omite en silencio). El OI es OPCIONAL: si su cache falta o es mas corto que la
    ventana primaria, devolvemos (df_funding, None, rango) y el caller sigue
    FUNDING-ONLY (funding es la señal estructural mas larga/fuerte).

    Devuelve (df_funding, df_oi_or_None, oi_range_str).
    """
    import funding_oi as fo
    fpath = fo.funding_path(data_dir, exchange, symbol)
    if not os.path.exists(fpath):
        sys.exit(
            f"--funding-oi {symbol}: falta el cache de funding {fpath}. "
            f"Descargalo (cachea a Parquet) en el host CON red, p.ej.:\n"
            f"  python -c \"import funding_oi as fo, bt_data; "
            f"ex=bt_data.make_exchange('{exchange}', 'swap'); "
            f"fo.fetch_funding_history(ex, '{symbol}', data_dir='{data_dir}'); "
            f"fo.fetch_open_interest_history(ex, '{symbol}', data_dir='{data_dir}')\"")
    df_funding = bt_data.load_parquet(fpath)

    df_oi, oi_range = None, "no disponible"
    opath = fo.open_interest_path(data_dir, exchange, symbol)
    if os.path.exists(opath):
        df_oi_try = bt_data.load_parquet(opath)
        if df_oi_try is not None and len(df_oi_try):
            rng = fo._range_of(df_oi_try)
            df_oi = df_oi_try
            oi_range = f"{rng[0]} .. {rng[1]} (n={len(df_oi_try)})"
    return df_funding, df_oi, oi_range


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


def _print_execution_frontier(labeled, folds, valid_index, sim_kwargs, ppy,
                              df_primary=None):
    """[2.2/4] Frontera de ejecucion: las MISMAS senales OOS bajo escenarios de
    fees maker/taker (CostModel.maker_*). Gratis (re-simular, no re-replicar).

    DOS lecturas:
      - [techo]: maker con fill 100% asumido (adverse selection NO modelada).
      - [fill-sim] (si hay df_primary): descuenta por el FILL-RATE real simulando
        la limite de ENTRADA contra las velas con la MISMA regla penetracion>eps
        que el paper (gold_paper.process_maker_pending / FQ_GOLD_MAKER_SIM, §6.10)
        y regradua SOLO el subset que se HABRIA llenado; mas el chequeo de adverse
        selection (¿los FILLED rinden menos que los MISSED?). El stop SIEMPRE taker.
    El techo decide si vale la pena el fill-model; el [fill-sim] es el numero
    DEFENDIBLE OOS (la captura forward final la sella el paper).
    """
    from dataclasses import replace
    base_cost = sim_kwargs.get("cost") or eng.CostModel()
    pooled = ab.pooled_oos_trades(labeled, folds, valid_index=valid_index)
    mk = replace(base_cost, maker_entry=True)
    mktp = replace(base_cost, maker_entry=True, maker_tp_exit=True)
    nan = float("nan")

    def _exp(trades, cost):
        if trades is None or len(trades) == 0:
            return {}
        kw = dict(sim_kwargs)
        kw["cost"] = cost
        res = eng.simulate(trades, **kw)
        return met.metrics_from_result(res, periods_per_year=ppy,
                                       exposure=_exposure_fraction(trades))

    def _row(name, trades, cost, fill_pct):
        m = _exp(trades, cost)
        return {"escenario": name, "n": (0 if trades is None else len(trades)),
                "fill%": fill_pct, "exp_R": m.get("expectancy_r", nan),
                "PF": m.get("profit_factor", nan), "total_R": m.get("total_r", nan),
                "maxDD": m.get("max_drawdown", nan)}

    rows = [_row("taker/taker (actual)", pooled, base_cost, 100.0),
            _row("entrada maker [techo]", pooled, mk, 100.0),
            _row("entrada+TP maker [techo]", pooled, mktp, 100.0)]

    fr = None
    if df_primary is not None and len(pooled):
        eps = float(os.environ.get("FQ_GOLD_MAKER_EPS_BPS", "1.0")) / 10_000.0
        ttl = int(os.environ.get("FQ_GOLD_MAKER_TTL_BARS", "6"))
        mask = eng.maker_entry_fill_mask(
            pooled, df_primary["high"].to_numpy(), df_primary["low"].to_numpy(),
            eps=eps, ttl_bars=ttl)
        fr = float(mask.mean()) if len(mask) else 0.0
        filled = pooled[mask]
        rows.append(_row("entrada maker [fill-sim]", filled, mk, fr * 100.0))
        rows.append(_row("entrada+TP maker [fill-sim]", filled, mktp, fr * 100.0))

    print(f"\n[2.2/4] Frontera de ejecucion (maker_fee={base_cost.maker_fee}; "
          "[techo]=fill 100% asumido, [fill-sim]=descontado por fill-rate real):")
    print(pd.DataFrame(rows).to_string(
        index=False, float_format=lambda v: f"{v:8.4f}"))
    if fr is not None and "pnl_r" in pooled.columns and mask.any() and (~mask).any():
        rf = float(pooled.loc[mask, "pnl_r"].mean())
        rm = float(pooled.loc[~mask, "pnl_r"].mean())
        verdict = ("ADVERSE SELECTION: la limite se queda los flojos -> el "
                   "[fill-sim] aun es OPTIMISTA" if rf < rm
                   else "sin adverse selection evidente (alienta el maker)")
        print(f"  fill-rate={fr:.1%} (eps={eps * 1e4:.1f}bps, ttl={ttl} velas)  "
              f"R_fill={rf:+.4f} vs R_miss={rm:+.4f}  ->  {verdict}")
    print("  nota: stop/timeout SIEMPRE taker; el [fill-sim] regradua solo lo que "
          "la limite habria llenado. La captura forward real la mide el paper.")


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


def _print_selectivity_gate(labeled, folds, valid_index, trained, sim_kwargs,
                            ppy, df_primary, args):
    """[P2] GATE DE SELECTIVIDAD (OOS) — "operar SOLO el subset de alta expectancy".

    La tesis P2: el edge se concentra en el TOP del score del modelo Y dentro de
    las killzones liquidas, mientras la media de TODAS las senales es negativa.
    Aqui se mide ALL vs SELECTED sobre la MISMA cartera OOS pooled, con el umbral
    de score derivado de forma LEAKAGE-CLEAN:

      umbral = quantile(OOF scores en filas tested, 1 - select_top_pct)

    Los OOF scores (`trained["oof_scores"]`) ya son out-of-sample por construccion
    (cada fold predice su test con un modelo ajustado SOLO en su train), igual que
    el percentil de ql.quality_gate. NO se ajusta nada aqui; solo se rebana y mide.
    La pierna de killzone usa el prior estructural SELECT_KILLZONE_EXCLUDE.

    Para el subset SELECCIONADO ademas se reporta la expectancy maker [fill-sim]
    (P1) reusando eng.maker_entry_fill_mask EXACTAMENTE como la frontera [2.2/4]
    -> se ve P1xP2 apilados sobre el libro ya selectivo.
    """
    oof = np.asarray(trained.get("oof_scores"), dtype="float64")
    tested = np.asarray(trained.get("tested_mask"), dtype=bool)

    # ALINEACION score<->trade (critico): `oof`/`tested` viven en el espacio
    # POSICIONAL de valid = labeled.loc[valid_index].reset_index(drop=True) (0..N-1),
    # porque train_walk_forward hizo X = valid[...].reset_index(drop=True). La
    # cartera pooled es base.iloc[test_positions] ordenada por entry_index, con
    # base IDENTICO (labeled.loc[valid_index].reset_index(drop=True)). Reproducimos
    # pooled_oos_trades reteniendo la posicion base de cada fila para indexar `oof`
    # con el MISMO orden -> score y trade quedan emparejados fila a fila.
    base = labeled.loc[valid_index].reset_index(drop=True)
    test_positions = (np.unique(np.concatenate([te for _tr, te in folds]))
                      if folds else np.array([], dtype=int))
    pooled = base.iloc[test_positions].copy()
    pooled["_oof_pos"] = test_positions
    if "entry_index" in pooled.columns:
        pooled = pooled.sort_values("entry_index")
    pooled = pooled.reset_index(drop=True)
    pos = pooled["_oof_pos"].to_numpy()
    pooled = pooled.drop(columns=["_oof_pos"])
    scores = oof[pos]

    # Sanidad: las filas pooled deben ser exactamente las 'tested' (con score OOF).
    finite = np.isfinite(scores)
    if not finite.all():
        print(f"  [P2 aviso] {int((~finite).sum())}/{len(scores)} filas pooled sin "
              "score OOF (no tested); se excluyen de la seleccion")
    n_total = int(len(pooled))
    if n_total == 0:
        print("\n[P2] Gate de selectividad: sin filas OOS pooled; se omite.")
        return

    # Umbral leakage-clean: top `select_top_pct` del OOF en las filas tested.
    top_pct = float(getattr(args, "select_top_pct", 0.50))
    q = max(0.0, min(1.0, 1.0 - top_pct))
    valid_scores = scores[finite]
    score_thr = float(np.quantile(valid_scores, q)) if len(valid_scores) else float("nan")

    kz_present = SELECT_KZ_COL in pooled.columns
    sel = _select_mask(pooled, scores, score_thr) & finite
    selected = pooled[sel]
    n_sel = int(len(selected))

    def _exp(trades, cost):
        if trades is None or len(trades) == 0:
            return {}
        kw = dict(sim_kwargs)
        kw["cost"] = cost
        res = eng.simulate(trades, **kw)
        return met.metrics_from_result(res, periods_per_year=ppy,
                                       exposure=_exposure_fraction(trades))

    base_cost = sim_kwargs.get("cost") or eng.CostModel()
    nan = float("nan")
    m_all = _exp(pooled, base_cost)
    m_sel = _exp(selected, base_cost)
    rows = [
        {"subset": "ALL (todas OOS)", "n": n_total,
         "exp_R": m_all.get("expectancy_r", nan), "WR": m_all.get("win_rate", nan),
         "PF": m_all.get("profit_factor", nan), "total_R": m_all.get("total_r", nan)},
        {"subset": "SELECTED (P2)", "n": n_sel,
         "exp_R": m_sel.get("expectancy_r", nan), "WR": m_sel.get("win_rate", nan),
         "PF": m_sel.get("profit_factor", nan), "total_R": m_sel.get("total_r", nan)},
    ]

    print("\n[3.5/4] Gate de selectividad P2 (operar SOLO el subset de alta "
          "expectancy; OOS):")
    print("  regla A PRIORI: score >= umbral(top {:.0%} del OOF) Y killzone "
          "liquida (excluye {}).".format(top_pct, sorted(SELECT_KILLZONE_EXCLUDE)))
    if not kz_present:
        print(f"  [aviso] sin columna '{SELECT_KZ_COL}': seleccion = SOLO-score "
              "(sin la pierna estructural de killzone).")
    print(pd.DataFrame(rows).to_string(
        index=False, float_format=lambda v: f"{v:8.4f}"))

    # P1 x P2: expectancy maker [fill-sim] sobre el subset YA selectivo (misma
    # regla penetracion>eps que la frontera [2.2/4] y gold_paper; stop/timeout taker).
    if df_primary is not None and n_sel:
        eps = float(os.environ.get("FQ_GOLD_MAKER_EPS_BPS", "1.0")) / 10_000.0
        ttl = int(os.environ.get("FQ_GOLD_MAKER_TTL_BARS", "6"))
        mask = eng.maker_entry_fill_mask(
            selected, df_primary["high"].to_numpy(), df_primary["low"].to_numpy(),
            eps=eps, ttl_bars=ttl)
        fr = float(mask.mean()) if len(mask) else 0.0
        from dataclasses import replace
        mk = replace(base_cost, maker_entry=True)
        m_fill = _exp(selected[mask], mk)
        print(f"  [P1xP2 fill-sim] entrada maker sobre el SELECCIONADO: "
              f"fill-rate={fr:.1%} (eps={eps * 1e4:.1f}bps ttl={ttl}) "
              f"n_filled={int(mask.sum())} exp_R={_f(m_fill.get('expectancy_r'))} "
              f"PF={_f(m_fill.get('profit_factor'))} (stop/timeout taker)")

    rate = (n_sel / n_total) if n_total else 0.0
    edge = ((m_sel.get("expectancy_r") - m_all.get("expectancy_r"))
            if (m_sel.get("expectancy_r") is not None
                and m_all.get("expectancy_r") is not None) else None)
    print(f"  knobs: top_pct={top_pct:.2f} (umbral_OOF={_f(score_thr)}) "
          f"killzone_excluye={sorted(SELECT_KILLZONE_EXCLUDE) if kz_present else 'n/a'} "
          f"| seleccion={n_sel}/{n_total} ({rate:.1%}) | "
          f"edge_vs_all={_f(edge)} R/trade")
    print("  nota OOS limpia: el umbral sale del OOF (out-of-sample por "
          "construccion) y la killzone es prior estructural; el test SIN FUGA es "
          "el forward [seleccion] (--out-of-time).")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--exchange", default="binance")
    p.add_argument("--symbol", default="SOL/USDT")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--cross-asset", default=None,
                   help="simbolo LIDER cross-asset (p.ej. BTC/USDT) para features "
                        "lead-lag CAUSALES (xbtc_*) alineadas a cada vela del "
                        "primario via merge_asof backward (cross_ts<=t, shift 1 "
                        "vela = conservador). Las xbtc_ entran al modelo [3/4] Y al "
                        "vector de retrieval. Requiere el Parquet del lider al "
                        "MISMO TF/exchange (si falta, error claro; NO se omite en "
                        "silencio). Si == --symbol es no-op con aviso. Default None")
    p.add_argument("--funding-oi", action="store_true",
                   help="inyecta features ESTRUCTURALES de funding-rate (+ open "
                        "interest si disponible) CAUSALES (fund_/oi_) alineadas a "
                        "cada vela del primario via merge_asof backward (ts<=t, "
                        "shift 1 ventana = ultimo funding YA LIQUIDADO). Cosecha el "
                        "premio de reversion de extremos de funding y la "
                        "confirmacion/squeeze de OI; NO predice direccion. Requiere "
                        "el cache de funding (si falta, error claro con el comando "
                        "de descarga). El OI es opcional: si su historia no cubre la "
                        "ventana, sigue FUNDING-ONLY. Las fund_/oi_ entran al modelo "
                        "[3/4] Y al vector de retrieval. Default off")
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
    p.add_argument("--rolling-chunks", type=int, default=6,
                   help="nº de tramos del FORWARD [retrieval-rolling]: gate de "
                        "retrieval ONLINE con memoria EXPANSIVA (re-ingiere estados "
                        "resueltos al caminar AFTER; embargo == max_bars). Mide si la "
                        "adaptatividad recupera el edge que el gate estatico pierde "
                        "por drift de regimen. No es input del workflow (default 6)")
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
                        "WR/expectancy/total_r/max_dd del subset VIP vs el total. "
                        "Activa TAMBIEN el gate de selectividad P2 (OOS + forward)")
    p.add_argument("--select-top-pct", type=float, default=0.50,
                   help="[P2 gate de selectividad] fraccion SUPERIOR del score que se "
                        "OPERA (0.50 = top 50%% -> umbral = mediana). El umbral se "
                        "deriva leakage-clean: en OOS del OOF (walk-forward), en "
                        "forward de la ventana BEFORE; jamas del set evaluado. La "
                        "killzone se filtra ademas por SELECT_KILLZONE_EXCLUDE.")
    # --- F2: persiste el gate ORO (indice de retrieval + umbral) en una corrida ---
    p.add_argument("--build-index", action="store_true",
                   help="tras el retrieval denso, calibra el umbral oro (top_pct) y "
                        "persiste el gate (indice+scaler+outcomes+meta) para el live")
    p.add_argument("--index-out", default=None,
                   help="dir del artefacto del gate (default: retrieval/<ex>/<sym>)")
    p.add_argument("--gold-top-pct", type=float, default=0.05,
                   help="percentil que define ORO (0.05 = top 5%%, lo validado en F1)")
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

    # ===== CROSS-ASSET LEAD-LAG (BTC -> alt) — inyeccion CAUSAL =====
    # Punto unico DESPUES de que las 3 ramas (replay normal, --states-in,
    # --events-in) converjan en `states`/`events` y ANTES de que algo los consuma
    # (labeling [3-A], grids/cubo, modelo [3/4], retrieval denso [4/4], OOT,
    # selectividad). Anexa las columnas xbtc_* por entry_index a `events` y
    # `states`; `labeled` las HEREDA porque lb.label_events preserva toda clave del
    # evento (ver bt_labeler.label_events). Causal por construccion: attach ->
    # cross_asset_features solo lee el cruzado <= la vela de SU entry_index
    # (merge_asof backward + shift_cross=1); aqui NO se añade ningun merge
    # forward-looking. df_primary es el MISMO cuyas posiciones indexa entry_index
    # (mismo que lb.label_events de abajo y que re-deriva entry_index en las ramas
    # sharded), incluido el recorte por --date-start/--date-end.
    if args.cross_asset:
        if args.cross_asset == args.symbol:
            print(f"\n[cross-asset] --cross-asset == --symbol ({args.symbol}); "
                  "no-op (un activo no es su propio lider).")
        else:
            df_cross = _load_cross_ohlcv(
                args.exchange, args.cross_asset, prim_tf, args.data_dir)
            if events is not None and len(events):
                events = bf.attach_cross_asset_features(events, df_primary, df_cross)
            if states is not None and len(states):
                states = bf.attach_cross_asset_features(states, df_primary, df_cross)
            # cobertura = fraccion non-NaN de xbtc_ret_12 sobre los eventos fired
            # (la MISMA poblacion que se etiqueta -> labeled). NaN inicial = velas
            # sin ventana suficiente del cruzado / entry_index fuera de rango.
            _n_ev = len(events) if events is not None else 0
            if _n_ev and "xbtc_ret_12" in events.columns:
                _cov = float(events["xbtc_ret_12"].notna().mean()) * 100.0
            else:
                _cov = 0.0
            print(f"[cross-asset] {args.cross_asset} lider -> {_n_ev} eventos, "
                  f"xbtc_ cobertura {_cov:.1f}%")

    # ===== FUNDING / OPEN-INTEREST (estructural) — inyeccion CAUSAL =====
    # MISMO punto unico que cross-asset (3 ramas ya convergidas en states/events,
    # ANTES de labeling/grids/modelo/retrieval/OOT). Anexa fund_/oi_ por
    # entry_index; `labeled` las HEREDA (lb.label_events preserva toda clave del
    # evento). Causal por construccion: attach -> funding_oi_features solo lee
    # funding/OI <= la vela de SU entry_index (merge_asof backward + shift=1, ultimo
    # funding YA LIQUIDADO); aqui NO se añade ningun merge forward-looking. El OI es
    # opcional: si su cache no cubre la ventana, se sigue FUNDING-ONLY (oi_ ausentes
    # -> el vector las imputa a 0). df_primary es el MISMO que indexa entry_index.
    if args.funding_oi:
        df_funding, df_oi, oi_range = _load_funding_oi(
            args.exchange, args.symbol, args.data_dir)
        if events is not None and len(events):
            events = fo.attach_funding_oi_features(events, df_primary, df_funding, df_oi)
        if states is not None and len(states):
            states = fo.attach_funding_oi_features(states, df_primary, df_funding, df_oi)
        # cobertura = fraccion non-NaN de fund_rate sobre los eventos fired (misma
        # poblacion que se etiqueta). NaN = velas previas al primer funding o
        # entry_index fuera de rango.
        _n_ev = len(events) if events is not None else 0
        if _n_ev and "fund_rate" in events.columns:
            _cov = float(events["fund_rate"].notna().mean()) * 100.0
        else:
            _cov = 0.0
        print(f"[funding-oi] {_n_ev} eventos, fund_ cobertura {_cov:.1f}% | "
              f"oi: {oi_range}")

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
        _print_execution_frontier(labeled, folds, valid_index, sim_kwargs, ppy,
                                  df_primary=df_primary)
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

            # [P2] gate de selectividad OOS (score top-pct AND killzone liquida).
            # Default-on con --quality-gate (sin input de workflow nuevo).
            if trained is not None and args.quality_gate:
                _print_selectivity_gate(labeled, folds, valid_index, trained,
                                        sim_kwargs, ppy, df_primary, args)

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


# ----------------------------------------------------------------------------
# ROLLING / ONLINE forward retrieval — piezas PURAS (sin red, sin estado) que
# definen la MEMORIA causal de cada chunk. Extraidas como funciones puras para
# que la regla de embargo sea unit-testable (tests/test_rolling_forward.py).
# ----------------------------------------------------------------------------
def _rolling_chunk_bounds(after_entry_indexes, n_chunks):
    """Parte la ventana AFTER en `n_chunks` tramos CRONOLOGICOS (por entry_index)
    de tamano aproximadamente igual. Devuelve una lista de tuplas
    (chunk_start, idx_mask) donde:
      chunk_start : entry_index del PRIMER evento del chunk (frontera temporal;
                    define que memoria es admisible — todo lo resuelto antes).
      idx_mask    : mascara booleana (sobre after_entry_indexes) de los eventos
                    de ESE chunk.
    Los chunks son disjuntos y cubren todo AFTER en orden de entry_index. Pieza
    pura: arrays in -> lista de (float, np.ndarray[bool]) out.
    """
    ei = np.asarray(after_entry_indexes, dtype="float64")
    n = len(ei)
    if n == 0 or n_chunks < 1:
        return []
    order = np.argsort(ei, kind="stable")          # cronologico, estable
    n_chunks = int(min(n_chunks, n))               # no mas chunks que eventos
    parts = np.array_split(order, n_chunks)        # contiguos en el orden temporal
    bounds = []
    for part in parts:
        if len(part) == 0:
            continue
        mask = np.zeros(n, dtype=bool)
        mask[part] = True
        chunk_start = float(ei[part].min())        # frontera = primer evento del chunk
        bounds.append((chunk_start, mask))
    return bounds


def _rolling_memory_mask(memory_entry_indexes, max_bars, chunk_start):
    """MASCARA de la MEMORIA admisible para un chunk cuya frontera temporal es
    `chunk_start` (entry_index del primer evento del chunk).

    **Esta es la puerta de leakage del test rolling.** Un evento e SOLO entra en
    la memoria del chunk si su etiqueta ya estaba RESUELTA antes de que el chunk
    empiece, esto es:

        e.entry_index + max_bars  <  chunk_start

    `max_bars` es el horizonte de la barrera vertical (el MAXIMO de velas que una
    etiqueta puede tardar en resolverse). Sumarlo es la cota CONSERVADORA: aunque
    la etiqueta concreta cerrara antes (bars_held < max_bars), no asumimos saber
    su desenlace hasta `entry_index + max_bars`. Asi, un evento todavia ABIERTO
    en la frontera del chunk (cuyo pnl_r aun no se conocia) queda EXCLUIDO, y su
    desenlace no puede informar ni el indice ni el umbral del chunk.

    Pieza pura: array de entry_index in -> mascara booleana out.
    """
    ei = np.asarray(memory_entry_indexes, dtype="float64")
    return (ei + float(max_bars)) < float(chunk_start)


def _gold_threshold_from_memory(memory_res, *, k, sim_floor, n_floor, decay_bars,
                                backend, bit_width, gold_top_pct, n_splits,
                                embargo, seed, index=None):
    """UMBRAL ORO derivado SOLO de `memory_res` (estados ya resueltos). Camino
    principal = expectancy del vecindario de los folds walk-forward CAUSALES
    dentro de la memoria (rt.retrieval_oos: ningun fold ve el futuro de la
    memoria). Fallback (marcado) = percentil de las expectancies del vecindario
    in-sample de la memoria, consultando su propio indice.

    Es EXACTAMENTE la logica de umbral de _forward_retrieval_gate, extraida para
    que el gate estatico (BEFORE) y el rolling (MEMORIA por chunk) compartan el
    MISMO derivador leakage-clean. Devuelve (threshold, thr_source, n_confident).
    """
    threshold, thr_source, n_confident = None, "none", 0
    try:
        m_folds, m_valid = wf.folds_from_labeled(
            memory_res, n_splits=n_splits, embargo=embargo)
        if m_folds:
            m_oos = rt.retrieval_oos(
                memory_res, m_folds, m_valid, mode="causal", backend=backend,
                bit_width=bit_width, k=k, sim_floor=sim_floor, n_floor=n_floor,
                decay_bars=decay_bars, seed=seed)
            if len(m_oos):
                conf = m_oos[~m_oos["retr_abstain"].astype(bool)]
                n_confident = int(len(conf))
                threshold = rg.calibrate_gold_threshold(
                    conf["retr_expectancy_r"].to_numpy(), top_pct=gold_top_pct)
                if threshold is not None:
                    thr_source = "memory_oos"
    except Exception:
        threshold = None  # cae al fallback in-sample (sigue dentro de la memoria)

    if threshold is None:
        if index is None:
            index = rg.StateIndex.build(memory_res, backend=backend,
                                        bit_width=bit_width)
        exps = []
        for _, st in memory_res.iterrows():
            s = index.query(st, k=k, sim_floor=sim_floor, n_floor=n_floor,
                            decay_bars=decay_bars)
            if not s["abstain"] and np.isfinite(s["expectancy_r"]):
                exps.append(s["expectancy_r"])
        n_confident = len(exps)
        threshold = rg.calibrate_gold_threshold(exps, top_pct=gold_top_pct)
        thr_source = "memory_insample" if threshold is not None else "none"
    return threshold, thr_source, n_confident


def _forward_retrieval_gate(before, after, *, k=50, sim_floor=0.5, n_floor=None,
                            decay_bars=None, backend="exact", bit_width=4,
                            gold_top_pct=0.05, n_splits=8, embargo=8, seed=42):
    """Gate de RETRIEVAL leakage-clean por construccion (BEFORE -> AFTER).

    Esta es la version forward (out-of-time) del gate ORO de retrieval_gate (F2):
    el indice k-NN, el escalador y el UMBRAL oro se derivan EXCLUSIVAMENTE de la
    ventana BEFORE (pre-corte); cada evento de AFTER (post-corte, jamas visto) se
    clasifica consultando ESE indice de BEFORE. Los vecinos de un evento AFTER
    salen SIEMPRE del BEFORE (k-NN causal: nunca AFTER, nunca el futuro), y el
    desenlace (pnl_r) de AFTER NO informa ni el indice ni el umbral.

    Umbral oro (tambien BEFORE-only): se calibra con la expectancy del vecindario
    de los folds walk-forward CAUSALES *dentro de BEFORE* (rt.retrieval_oos sobre
    BEFORE). Si BEFORE no da para folds, cae al percentil de las expectancies del
    vecindario in-sample de BEFORE (sigue 100% dentro de BEFORE; se marca el
    origen en thr_source para la auditoria).

    Pieza PURA (DataFrames in -> DataFrame/numeros out): no toca red ni estado, y
    consulta UNICAMENTE el indice de BEFORE. Devuelve un dict:
      gate_pass      : sub-DataFrame de AFTER clasificado ORO (tier == GOLD)
      threshold      : umbral oro derivado de BEFORE (o None)
      thr_source     : "before_oos" | "before_insample" | "none"
      n_confident    : nº de estados confident usados para calibrar el umbral
      n_after_scored : nº de eventos AFTER clasificados (con pnl_r resuelto)
      tiers          : conteo {gold, base, abstain} sobre AFTER
    """
    # 1) INDICE + ESCALADOR: SOLO BEFORE (StateIndex.build ajusta el vectorizer y
    #    el indice con el pasado; exige pnl_r resuelto).
    before_res = before[before["pnl_r"].notna()].reset_index(drop=True)
    if len(before_res) == 0:
        raise ValueError("BEFORE sin estados resueltos (pnl_r)")
    index = rg.StateIndex.build(before_res, backend=backend, bit_width=bit_width)

    # 2) UMBRAL ORO: BEFORE-only. Camino principal = expectancy del vecindario de
    #    los folds walk-forward CAUSALES dentro de BEFORE (mismo primitivo vetado
    #    que el --build-index, pero restringido a BEFORE: ningun fold ve AFTER).
    #    Reusa el derivador puro compartido con el gate rolling (memoria==BEFORE);
    #    aqui la "memoria" es BEFORE, asi que renombramos el origen a before_*.
    threshold, thr_src_mem, n_confident = _gold_threshold_from_memory(
        before_res, k=k, sim_floor=sim_floor, n_floor=n_floor,
        decay_bars=decay_bars, backend=backend, bit_width=bit_width,
        gold_top_pct=gold_top_pct, n_splits=n_splits, embargo=embargo,
        seed=seed, index=index)
    thr_source = {"memory_oos": "before_oos",
                  "memory_insample": "before_insample",
                  "none": "none"}[thr_src_mem]

    # 3) GATE: clasifica cada evento AFTER contra el indice de BEFORE (causal).
    gate = rg.GoldGate(index, threshold, k=k, sim_floor=sim_floor,
                       n_floor=n_floor, decay_bars=decay_bars)
    after_res = after[after["pnl_r"].notna()].reset_index(drop=True)
    tiers = {rg.GOLD: 0, rg.BASE: 0, rg.ABSTAIN: 0}
    keep = np.zeros(len(after_res), dtype=bool)
    for i in range(len(after_res)):
        verdict = gate.classify(after_res.iloc[i])
        tiers[verdict["tier"]] = tiers.get(verdict["tier"], 0) + 1
        keep[i] = verdict["tier"] == rg.GOLD
    return {
        "gate_pass": after_res[keep].reset_index(drop=True),
        "threshold": threshold, "thr_source": thr_source,
        "n_confident": n_confident, "n_after_scored": int(len(after_res)),
        "tiers": tiers,
    }


def _run_rolling_forward_retrieval(before, after, *, max_bars, n_chunks=6, k=50,
                                   sim_floor=0.5, n_floor=None, decay_bars=None,
                                   backend="exact", bit_width=4, gold_top_pct=0.05,
                                   n_splits=8, embargo=8, seed=42):
    """Gate de RETRIEVAL ROLLING / ONLINE leakage-clean (memoria EXPANSIVA).

    Ataca el DRIFT DE REGIMEN: el gate estatico congela indice+umbral en BEFORE y
    los aplica a TODO AFTER, asi que con el tiempo la memoria queda anticuada (el
    forward se queda SILENCIOSO). Aqui caminamos AFTER cronologicamente en
    `n_chunks` tramos; para el chunk i la MEMORIA = todos los eventos cuya
    ETIQUETA se resolvio ANTES de que el chunk i empiece (BEFORE + chunks AFTER
    previos YA resueltos). La memoria CRECE conforme avanzamos: se mantiene al dia.

    **Puerta de leakage (embargo == max_bars).** Un evento e entra en la memoria
    del chunk i SOLO si `e.entry_index + max_bars < chunk_i_start` (ver
    _rolling_memory_mask). `max_bars` es el horizonte de la barrera vertical: la
    cota conservadora de cuando, COMO MUY TARDE, se conoce el desenlace (pnl_r).
    Asi un evento todavia ABIERTO en la frontera del chunk (pnl_r aun desconocido)
    queda EXCLUIDO: su desenlace jamas informa ni el indice ni el umbral ni el
    gate del chunk i. Cada evento de AFTER se clasifica con un indice construido
    SOLO con su pasado estricto resuelto (k-NN causal); su propio pnl_r nunca
    entra. El umbral oro sale de rt.retrieval_oos sobre ESA memoria (folds
    walk-forward causales) con el mismo fallback in-sample marcado que el estatico.

    Devuelve dict:
      gate_pass        : union (sobre chunks) de eventos AFTER clasificados ORO.
      n_after_scored   : nº de eventos AFTER gateados (con pnl_r resuelto).
      n_chunks_used    : nº de chunks realmente procesados (con memoria valida).
      n_chunks_skipped : nº de chunks saltados (memoria insuficiente para indice).
      thr_sources      : conteo {memory_oos, memory_insample, none} sobre chunks.
      mem_sizes        : tamano de la memoria por chunk procesado (crecimiento).
    """
    before_res = before[before["pnl_r"].notna()].reset_index(drop=True)
    after_res = after[after["pnl_r"].notna()].reset_index(drop=True)
    if "entry_index" not in after_res.columns:
        raise ValueError("AFTER sin columna entry_index (no se puede ordenar el rolling)")
    if len(after_res) == 0:
        raise ValueError("AFTER sin estados resueltos (pnl_r)")

    after_ei = after_res["entry_index"].to_numpy(dtype="float64")
    bounds = _rolling_chunk_bounds(after_ei, n_chunks)

    keep = np.zeros(len(after_res), dtype=bool)
    n_scored = 0
    thr_sources = {"memory_oos": 0, "memory_insample": 0, "none": 0}
    mem_sizes, n_used, n_skipped = [], 0, 0

    for chunk_start, chunk_mask in bounds:
        # MEMORIA del chunk = BEFORE (todo resuelto y anterior) U eventos de AFTER
        # de chunks previos cuya etiqueta YA cerro antes de la frontera del chunk.
        # La puerta de leakage es identica para ambos origenes: entry_index +
        # max_bars < chunk_start. (BEFORE casi siempre cumple por estar pre-corte,
        # pero lo filtramos por la MISMA regla — no asumimos nada gratis.)
        b_keep = _rolling_memory_mask(
            before_res["entry_index"].to_numpy(dtype="float64"), max_bars, chunk_start)
        a_keep = _rolling_memory_mask(after_ei, max_bars, chunk_start)
        memory = pd.concat(
            [before_res[b_keep], after_res[a_keep]], ignore_index=True)
        # exige al menos un punado de estados resueltos para un indice util
        if len(memory) < max(10, k // 2):
            n_skipped += 1
            continue
        try:
            index = rg.StateIndex.build(memory, backend=backend, bit_width=bit_width)
        except Exception:
            n_skipped += 1
            continue
        threshold, thr_src, _n_conf = _gold_threshold_from_memory(
            memory, k=k, sim_floor=sim_floor, n_floor=n_floor, decay_bars=decay_bars,
            backend=backend, bit_width=bit_width, gold_top_pct=gold_top_pct,
            n_splits=n_splits, embargo=embargo, seed=seed, index=index)
        thr_sources[thr_src] = thr_sources.get(thr_src, 0) + 1
        mem_sizes.append(int(len(memory)))
        n_used += 1

        # GATE de los eventos de ESTE chunk contra el indice de su memoria (causal).
        gate = rg.GoldGate(index, threshold, k=k, sim_floor=sim_floor,
                           n_floor=n_floor, decay_bars=decay_bars)
        pos = np.nonzero(chunk_mask)[0]
        n_scored += len(pos)
        for i in pos:
            verdict = gate.classify(after_res.iloc[i])
            keep[i] = verdict["tier"] == rg.GOLD

    return {
        "gate_pass": after_res[keep].reset_index(drop=True),
        "n_after_scored": int(n_scored),
        "n_chunks_used": int(n_used), "n_chunks_skipped": int(n_skipped),
        "thr_sources": thr_sources,
        "mem_sizes": mem_sizes,
    }


def _forward_net_returns(trades, sim_kwargs):
    """Retornos NET-de-costes por trade de un subset forward (mismos numeros que
    alimentan el Sharpe de forward_metrics: eng.simulate(...)['returns'] =
    net_pnl/equity_previo). Devuelve ndarray finito; vacio si no hay resueltos."""
    import bt_engine as eng
    if trades is None or len(trades) == 0:
        return np.array([], dtype="float64")
    t = trades[trades["outcome"].notna()] if "outcome" in trades.columns else trades
    if len(t) == 0:
        return np.array([], dtype="float64")
    res = eng.simulate(t, **(sim_kwargs or {}))
    r = np.asarray(res.get("returns"), dtype="float64").ravel()
    return r[np.isfinite(r)]


def _per_period_sharpe(returns):
    """Sharpe per-period (mean/std, ddof=1) -- mismo estimador que bt_metrics.sharpe
    SIN anualizar. None si <2 muestras o sd nula. Es la unidad de los 'trials' que
    arman N_trials/trials_sr_var del Deflated Sharpe."""
    r = np.asarray(returns, dtype="float64").ravel()
    r = r[np.isfinite(r)]
    if len(r) < 2:
        return None
    sd = float(r.std(ddof=1))
    if sd == 0.0:
        return None
    return float(r.mean() / sd)


def _print_deflated_verdict(fwd_configs, m, args, sim_kwargs):
    """[DEFLATED] Veredicto ANTI-SUERTE sobre los configs forward evaluados.

    `fwd_configs` = lista de (label, returns_net_por_trade, edge_vs_all) de TODOS
    los configs forward evaluados (sweep retrieval estatico + rolling + seleccion).
    Con ~10 intentos, un edge positivo podria ser el mas afortunado de N:

      * N_trials = numero de configs forward con Sharpe per-period medible.
      * trials_sr_var = VARIANZA de esos Sharpes per-period (su dispersion).
      Ambos se DERIVAN de los configs realmente evaluados aqui (auditable abajo).

    DSR del MEJOR config (max edge_vs_all con n>=10): P(Sharpe verdadero > barra
    del maximo-de-N | no-normalidad). Embarque si DSR>=0.95. Si >=3 configs tienen
    n>=10, ademas PBO (CSCV) sobre su matriz de retornos por trade bucketizada.
    """
    import deflated as dfl

    MIN_TRADES = 10
    # trials = configs con Sharpe per-period medible (n>=2). El conjunto de
    # intentos para N y su varianza sale de TODOS los configs forward, no solo
    # los de n>=10 (probar un ancho que salio starved TAMBIEN es un intento).
    trial_srs = []
    for _lbl, _ret, _edge in fwd_configs:
        s = _per_period_sharpe(_ret)
        if s is not None:
            trial_srs.append(s)
    n_trials = len(trial_srs)
    trials_sr_var = float(np.var(trial_srs, ddof=1)) if n_trials >= 2 else None

    # MEJOR config: el de mayor edge_vs_all con muestra suficiente (n>=10).
    eligible = [(lbl, ret, edge) for (lbl, ret, edge) in fwd_configs
                if len(ret) >= MIN_TRADES and edge is not None
                and np.isfinite(edge)]
    if not eligible:
        print("\n  [DEFLATED] sin config forward con n>=%d y edge medible "
              "(nada que deshinchar)." % MIN_TRADES)
        return
    best_lbl, best_ret, best_edge = max(eligible, key=lambda x: x[2])

    res = dfl.deflated_sharpe_ratio(best_ret, n_trials=max(n_trials, 1),
                                    trials_sr_var=trials_sr_var)
    dsr = res["dsr"]
    verdict = "OK" if (dsr is not None and dsr >= 0.95) else "SOSPECHA"
    flag = "  [var_default: dispersion no medible, default conservador]" \
        if res.get("sr0_var_default") else ""
    var_note = (f"{trials_sr_var:.4f}" if trials_sr_var is not None
                else "n/a(default)")
    print(f"\n  [DEFLATED] mejor forward = '{best_lbl}' "
          f"(edge_vs_all={_f(best_edge)} R/trade, n={len(best_ret)})")
    print(f"    N_trials={n_trials} (configs forward evaluados) "
          f"trials_sr_var={var_note} (var de sus Sharpes per-period)")
    print(f"    DSR={_f(dsr)} (P(edge real | N={n_trials} configs, no-normalidad)) "
          f"| SR={_f(res['sr'])} T={res['T']} skew={_f(res['skew'])} "
          f"kurt={_f(res['kurt'])} sr0={_f(res['sr0'])}  -> {verdict} "
          f"(DSR{'>=' if verdict == 'OK' else '<'}0.95){flag}")

    # PBO: necesita >=3 configs con n>=10. Se ALINEA por bucket de trade en
    # n_splits bins cuantilicos de la ventana forward (las longitudes difieren
    # entre configs: cada uno opera un subset distinto del after).
    pbo_pool = [(lbl, ret) for (lbl, ret, _e) in fwd_configs
                if len(ret) >= MIN_TRADES]
    if len(pbo_pool) >= 3:
        try:
            n_splits = int(getattr(args, "n_splits", 8))
            M = _bucketize_configs([r for _l, r in pbo_pool], n_splits=n_splits)
            if M is not None and M.shape[1] >= 3 and M.shape[0] >= n_splits:
                pres = dfl.probability_backtest_overfitting(M, n_splits=n_splits)
                pbo = pres.get("pbo")
                samp = " (muestreado)" if pres.get("sampled") else ""
                print(f"    PBO={_f(pbo)} (prob. de overfit del ranking IS->OOS; "
                      f"bajo=robusto, >=0.5=overfit) "
                      f"sobre {M.shape[1]} configs, {pres.get('n_combos')} combos{samp}")
            else:
                print("    PBO: matriz insuficiente tras bucketizar "
                      f"(configs={0 if M is None else M.shape[1]}, "
                      f"buckets={0 if M is None else M.shape[0]}, n_splits={n_splits})")
        except Exception as e:
            print(f"    PBO: no se pudo computar ({e})")
    else:
        print(f"    PBO: solo {len(pbo_pool)} config(s) con n>={MIN_TRADES} "
              f"(se requieren >=3 para CSCV)")


def _bucketize_configs(returns_list, n_splits):
    """Alinea configs de DISTINTA longitud en una matriz (n_splits filas x configs)
    para CSCV/PBO: cada serie de retornos por trade se reparte en n_splits bins
    contiguos (cuantiles de su propio orden temporal) y se promedia dentro del bin.
    Asi cada columna queda en la MISMA rejilla de n_splits 'tramos' de la ventana
    forward aunque cada config opere un numero distinto de trades. Devuelve la
    matriz o None si algun config no llena los bins."""
    cols = []
    for r in returns_list:
        r = np.asarray(r, dtype="float64").ravel()
        r = r[np.isfinite(r)]
        if len(r) < n_splits:
            return None                              # no llena los bins -> aborta
        # bins contiguos casi-iguales en el orden cronologico del config
        parts = np.array_split(r, n_splits)
        col = np.array([float(p.mean()) for p in parts], dtype="float64")
        cols.append(col)
    return np.column_stack(cols) if cols else None


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
        scored, model = fw.freeze_predict(before, after, feat_cols, fac)
    except Exception as e:
        print(f"  (no se pudo congelar el modelo: {e})")
        return
    m = fw.forward_metrics(after, sim_kwargs=sim_kwargs, bar_minutes=bar_minutes)
    if m is not None:
        print("  Métricas FORWARD (net de costes, ventana posterior):")
        print(met.format_report(m))

    # [DEFLATED] conjunto de INTENTOS forward para el veredicto anti-suerte. Cada
    # config evaluado abajo (seleccion P2 + sweep retrieval estatico + rolling) se
    # apila aqui como (label, retornos_net_por_trade, edge_vs_all). Con ~10 intentos
    # un edge positivo puede ser el mas afortunado de N; DSR/PBO lo cuantifican al
    # final del bloque forward. e_all es la expectancy de TODO el after (baseline).
    fwd_configs = []
    e_all = m.get("expectancy_r") if m else None

    # [P2] FORWARD del subset SELECCIONADO — el test SIN FUGA del gate de
    # selectividad. El umbral de score se deriva EXCLUSIVAMENTE de la ventana
    # BEFORE (congelada): se puntua BEFORE con el MISMO modelo frozen y se toma el
    # quantile top-pct de ESOS scores; jamas se mira el 'after'. Ese umbral fijo se
    # APLICA al 'after' (columna fwd_score, nunca vista) y se cruza con el prior
    # estructural de killzone. forward_metrics mide el subset resultante.
    if getattr(args, "quality_gate", False):
        try:
            top_pct = float(getattr(args, "select_top_pct", 0.50))
            q = max(0.0, min(1.0, 1.0 - top_pct))
            Xb = before[feat_cols].reset_index(drop=True).fillna(0.0)
            before_scores = fw._predict_scores(model, Xb)   # umbral SOLO del BEFORE
            bs = np.asarray(before_scores, dtype="float64")
            bs = bs[np.isfinite(bs)]
            if len(bs) == 0:
                raise ValueError("sin scores finitos en la ventana BEFORE")
            score_thr = float(np.quantile(bs, q))
            fwd_scores = scored["fwd_score"].to_numpy()
            kz_present = SELECT_KZ_COL in scored.columns
            sel = _select_mask(scored, fwd_scores, score_thr)
            sel_after = scored[sel]
            n_sel, n_after = int(len(sel_after)), int(len(scored))
            ms = fw.forward_metrics(sel_after, sim_kwargs=sim_kwargs,
                                    bar_minutes=bar_minutes)
            print("\n  FORWARD [selección] P2 (umbral del BEFORE aplicado al after "
                  "jamás visto + killzone líquida):")
            print(f"    umbral_score(top {top_pct:.0%} del BEFORE)={_f(score_thr)} "
                  f"killzone_excluye="
                  f"{sorted(SELECT_KILLZONE_EXCLUDE) if kz_present else 'n/a (solo-score)'} "
                  f"| seleccion={n_sel}/{n_after} "
                  f"({(n_sel / n_after if n_after else 0.0):.1%})")
            if ms is not None:
                print(f"    n={ms.get('n_trades')} "
                      f"expectancy_r={_f(ms.get('expectancy_r'))} "
                      f"total_return={_f(ms.get('total_return'))} "
                      f"sharpe={_f(ms.get('sharpe'))} "
                      f"profit_factor={_f(ms.get('profit_factor'))}")
                e_sel = ms.get("expectancy_r")
                edge = (e_sel - e_all) if (e_all is not None and e_sel is not None) else None
                print(f"    >> edge_vs_all_forward={_f(edge)} R/trade  "
                      "(¿la selección SOBREVIVE out-of-time? este es EL test)")
                # intento forward para el veredicto anti-suerte (DSR/PBO)
                fwd_configs.append(
                    ("seleccion_P2", _forward_net_returns(sel_after, sim_kwargs), edge))
            else:
                print("    (subset forward vacío tras la selección; baja "
                      "--select-top-pct o mueve el corte)")
        except Exception as e:
            print(f"  FORWARD [selección]: no se pudo computar ({e})")

    # [RETRIEVAL] FORWARD del gate de RETRIEVAL — el test SIN FUGA de la PUERTA
    # densa de analogia (k-NN). A diferencia de [selección] (score del modelo, que
    # NO sobrevivio forward en #60), aqui el indice k-NN, el escalador y el umbral
    # ORO se construyen EXCLUSIVAMENTE con la ventana BEFORE; cada evento AFTER
    # (jamas visto) se clasifica consultando ESE indice de BEFORE. Los vecinos de
    # un evento AFTER salen SIEMPRE del BEFORE (causal), y el desenlace de AFTER NO
    # informa ni el indice ni el umbral. Es la pregunta abierta decisiva: ¿la
    # PUERTA DE RETRIEVAL sobrevive out-of-time donde el score del modelo no?
    if getattr(args, "quality_gate", False):
        try:
            # SWEEP del ancho del gate: el umbral ORO se calibra del BEFORE a varios
            # percentiles (top 5/10/25/50%) y se aplica al AFTER jamas visto. A top
            # 5% el gate puede quedar STARVED forward (1-2 trades, ruido); ensanchar
            # da una lectura OOT con suficientes gold para JUZGAR si el edge OOS (que
            # cross-asset subio fuerte en el decil alto) sobrevive out-of-time. CADA
            # percentil sigue siendo BEFORE-only (leakage-clean); solo cambia el corte.
            print("\n  FORWARD [retrieval] (indice + umbral ORO del BEFORE; gate del "
                  "AFTER jamas visto por k-NN causal; SWEEP de ancho del gate):")
            e_all = m.get("expectancy_r") if m else None
            static_exp = {}   # top_pct -> exp_R estatico (baseline del delta rolling)
            _hdr = False
            for _tp in (0.05, 0.10, 0.25, 0.50):
                gr = _forward_retrieval_gate(
                    before, after, k=args.retrieval_k,
                    sim_floor=args.retrieval_sim_floor, n_floor=args.retrieval_nfloor,
                    decay_bars=args.retrieval_decay_bars,
                    backend=args.retrieval_backend, bit_width=args.retrieval_bit,
                    gold_top_pct=_tp, n_splits=args.n_splits,
                    embargo=args.embargo, seed=args.seed)
                gp = gr["gate_pass"]
                if not _hdr:
                    src_note = {"before_oos": "OOS walk-forward de BEFORE",
                                "before_insample": "in-sample de BEFORE (fallback)",
                                "none": "n/a"}.get(gr["thr_source"], gr["thr_source"])
                    print(f"    umbral <- {src_note} | AFTER={gr['n_after_scored']} "
                          f"n_confident_BEFORE={gr['n_confident']} k={args.retrieval_k}")
                    if gr["thr_source"] == "before_insample":
                        print("    [aviso] umbral del fallback in-sample de BEFORE "
                              "(limpio vs AFTER; optimismo in-sample en BEFORE).")
                    _hdr = True
                mg = fw.forward_metrics(gp, sim_kwargs=sim_kwargs,
                                        bar_minutes=bar_minutes) if len(gp) else None
                if mg is not None:
                    e_g = mg.get("expectancy_r")
                    static_exp[_tp] = e_g
                    edge = (e_g - e_all) if (e_all is not None and e_g is not None) else None
                    print(f"    top {_tp:>5.0%}: thr={_f(gr['threshold'])} "
                          f"gold={len(gp):>4} exp_R={_f(e_g)} "
                          f"edge_vs_all={_f(edge)} PF={_f(mg.get('profit_factor'))}")
                    # intento forward (sweep estatico) para el veredicto anti-suerte
                    fwd_configs.append(
                        (f"retr_static_top{_tp:.0%}",
                         _forward_net_returns(gp, sim_kwargs), edge))
                else:
                    static_exp[_tp] = None
                    print(f"    top {_tp:>5.0%}: thr={_f(gr['threshold'])} "
                          f"gold={len(gp):>4} (subset forward vacio)")
            print("    >> ¿sobrevive OOT al ensanchar el gate? BEFORE-only (AFTER no "
                  "puede filtrarse); mas gold = lectura mas fiable del edge forward.")
        except Exception as e:
            static_exp = {}
            print(f"  FORWARD [retrieval]: no se pudo computar ({e})")

    # [RETRIEVAL-ROLLING] FORWARD del gate de RETRIEVAL ONLINE — ataca el DRIFT DE
    # REGIMEN, causa comun de que el gate ESTATICO se quede silencioso forward (SOL
    # #61/#62 pasaron 1-2/141 gold). En produccion el bot ACTUALIZA su memoria de
    # continuo; esto lo mide: caminamos AFTER en K tramos y para cada uno
    # reconstruimos indice + umbral con la MEMORIA EXPANSIVA = todo lo cuya etiqueta
    # ya se resolvio antes de la frontera del tramo (BEFORE + tramos AFTER previos
    # YA cerrados). Embargo == max_bars: un evento abierto en la frontera NUNCA
    # entra (su pnl_r aun no se sabia). Si el rolling RECUPERA edge que el estatico
    # pierde, el drift es el asesino y la adaptatividad es el arreglo.
    if getattr(args, "quality_gate", False):
        try:
            K = int(getattr(args, "rolling_chunks", 6))
            e_all = m.get("expectancy_r") if m else None
            print(f"\n  FORWARD [retrieval-rolling] (memoria ONLINE/expansiva, K={K} "
                  f"tramos cronologicos; embargo=max_bars={args.max_bars}; cada tramo "
                  f"reconstruye indice+umbral con SOLO lo resuelto antes de su "
                  f"frontera; SWEEP de ancho del gate):")
            _hdr = False
            for _tp in (0.05, 0.10, 0.25):
                rfr = _run_rolling_forward_retrieval(
                    before, after, max_bars=args.max_bars, n_chunks=K,
                    k=args.retrieval_k, sim_floor=args.retrieval_sim_floor,
                    n_floor=args.retrieval_nfloor, decay_bars=args.retrieval_decay_bars,
                    backend=args.retrieval_backend, bit_width=args.retrieval_bit,
                    gold_top_pct=_tp, n_splits=args.n_splits,
                    embargo=args.embargo, seed=args.seed)
                gp = rfr["gate_pass"]
                if not _hdr:
                    mn = min(rfr["mem_sizes"]) if rfr["mem_sizes"] else 0
                    mx = max(rfr["mem_sizes"]) if rfr["mem_sizes"] else 0
                    print(f"    AFTER_gateado={rfr['n_after_scored']} "
                          f"chunks_usados={rfr['n_chunks_used']} "
                          f"(saltados={rfr['n_chunks_skipped']}) "
                          f"memoria {mn}->{mx} (crece) k={args.retrieval_k}")
                    print(f"    umbral por tramo <- {dict(rfr['thr_sources'])} "
                          f"(memory_oos = OOS walk-forward de la memoria del tramo)")
                    _hdr = True
                mg = fw.forward_metrics(gp, sim_kwargs=sim_kwargs,
                                        bar_minutes=bar_minutes) if len(gp) else None
                e_st = static_exp.get(_tp)
                if mg is not None:
                    e_g = mg.get("expectancy_r")
                    edge = (e_g - e_all) if (e_all is not None and e_g is not None) else None
                    d_static = (e_g - e_st) if (e_st is not None and e_g is not None) else None
                    print(f"    top {_tp:>5.0%}: gold={len(gp):>4} exp_R={_f(e_g)} "
                          f"total_ret={_f(mg.get('total_return'))} "
                          f"edge_vs_all={_f(edge)} PF={_f(mg.get('profit_factor'))} "
                          f"| delta_vs_static={_f(d_static)} (static_exp={_f(e_st)})")
                    # intento forward (sweep rolling) para el veredicto anti-suerte
                    fwd_configs.append(
                        (f"retr_rolling_top{_tp:.0%}",
                         _forward_net_returns(gp, sim_kwargs), edge))
                else:
                    print(f"    top {_tp:>5.0%}: gold={len(gp):>4} (subset forward "
                          f"vacio) | static_exp={_f(e_st)}")
            print("    >> ¿la MEMORIA AL DIA recupera edge que el gate congelado "
                  "pierde? delta_vs_static>0 = el drift es el asesino y la "
                  "adaptatividad lo arregla. Leakage-clean: embargo=max_bars.")
        except Exception as e:
            print(f"  FORWARD [retrieval-rolling]: no se pudo computar ({e})")

    # [DEFLATED] VEREDICTO ANTI-SUERTE — Deflated Sharpe Ratio (Bailey & Lopez de
    # Prado 2014) + Probability of Backtest Overfitting (CSCV, Bailey et al. 2017).
    # Se probaron ~10 configs forward (sweep estatico+rolling + seleccion P2); el
    # mejor edge podria ser el mas afortunado de N. DSR deshincha el Sharpe del
    # mejor config por N intentos + dispersion + no-normalidad; PBO mide si el
    # ranking IS->OOS aguanta. N_trials y trials_sr_var salen de los configs
    # apilados en fwd_configs (auditable en la propia linea impresa).
    if getattr(args, "quality_gate", False):
        try:
            _print_deflated_verdict(fwd_configs, m, args, sim_kwargs)
        except Exception as e:
            print(f"  [DEFLATED] no se pudo computar ({e})")

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
