#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  FUNDING RESEARCH — backtest DEFLACTADO de la REVERSION de funding (edge
  ESTRUCTURAL), por el MISMO juez forward+anti-suerte que el resto del harness.
  by RasDG_Sol + Claude

  El pivote post-§6.14: la PREDICCION direccional resulto suerte (DSR 0.41). Esta
  herramienta mide la alternativa ESTRUCTURAL — los EXTREMOS de funding revierten
  (longs que sobrepagan -> el precio revierte abajo, y viceversa) — sin pasar por
  el modelo [3/4] ni el gate de retrieval. La senal es funding_strategy.
  funding_reversion_signal sobre el fund_zscore CAUSAL de funding_oi.

  Flujo (todo CAUSAL; no introduce ventana hacia el futuro):
    1) carga el OHLCV primario (cache parquet) + el funding del exchange MAS
       PROFUNDO (Part C: funding_oi.fetch_funding_history_best / cache por
       exchange). Sin red en el harness: solo lee caches que el probe escribio.
    2) funding_oi.funding_oi_features -> fund_zscore por barra (settled funding,
       shift=1, merge_asof backward, z trailing). Ya causal.
    3) funding_strategy.funding_reversion_signal(fund_zscore, z_enter, z_exit)
       -> posicion {-1,0,+1} por barra -> positions_to_trades -> eventos
       (entry_index/dir/precio + stop/target en R).
    4) bt_labeler.label_events (triple-barrier) -> folds walk-forward purgados ->
       OOS pooled (mismas metricas net-de-costes que el run real).
    5) FORWARD out-of-time (--out-of-time): congela en una fecha y mide SOLO el
       'after' jamas visto. Reusa el patron de bt_forward.
    6) [DEFLATED] DSR (Bailey & Lopez de Prado) + PBO (CSCV): el SWEEP de z_enter
       es el conjunto de INTENTOS (probar 8 umbrales es probar 8 configs); el
       mejor edge se deshincha por N + dispersion + no-normalidad, y PBO mide si
       el ranking IS->OOS aguanta. Es el read inmediato de si el edge de funding
       es real o el mas afortunado del sweep, sobre la profundidad que exista.

  REUSA tal cual las piezas del runner real (bt_labeler / bt_walkforward /
  bt_engine / bt_metrics / bt_forward / deflated y los helpers _forward_net_returns
  / _per_period_sharpe / _bucketize_configs / _cost_for_symbol de
  run_research_real) -> misma ruta de medicion, mismo veredicto, cero metrica
  nueva que auditar.

  Uso (corre en el host del bot CON el cache ya bajado; el harness no toca red):
    # 1) (en Hetzner, una vez) bajar el funding mas profundo a cache:
    python -c "import funding_oi as fo; \
        print(fo.format_depth_table(fo.probe_funding_depth('BTC', data_dir='data')))"
    # 2) backtest deflactado de la reversion:
    python tools/funding_research.py --exchange okx --symbol BTC/USDT \
        --funding-base BTC --tf-id 15m --max-bars 96 --n-splits 8 --embargo 8 \
        --out-of-time 2025-04-01
================================================================================
"""
import argparse
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bt_data
import bt_labeler as lb
import bt_walkforward as wf
import bt_engine as eng
import bt_metrics as met
import bt_ablation as ab
import bt_forward as fw
import funding_oi as fo
import funding_strategy as fs
import deflated as dfl

# Reusa los helpers EXACTOS del runner real (misma metrica/veredicto).
import tools.run_research_real as rr


# z_enter del SWEEP = el conjunto de INTENTOS para el veredicto anti-suerte. Cada
# umbral es una configuracion distinta del MISMO edge estructural; probar N de
# ellos y quedarse con el mejor es justo lo que DSR/PBO deshinchan. El z_exit se
# escala con cada z_enter (histeresis proporcional) para no introducir un segundo
# grado de libertad por intento.
DEFAULT_Z_ENTER_SWEEP = (1.5, 1.75, 2.0, 2.25, 2.5, 3.0)


def _parse_float_list(s):
    """'1.5,2.0,2.5' -> [1.5, 2.0, 2.5]. Vacio/None -> []."""
    if not s:
        return []
    return [float(x) for x in str(s).replace(" ", "").split(",") if x]


def _load_primary(exchange, symbol, tf, data_dir):
    """Carga el OHLCV primario (cache parquet) con indicadores. La senal de
    funding solo necesita timestamp+close, pero reusamos el loader del runner real
    para que entry_price/entry_ts salgan IDENTICOS a un run normal."""
    path = bt_data.dataset_path(data_dir, exchange, symbol, tf)
    if not os.path.exists(path):
        sys.exit(
            f"falta el dataset {tf} en {path}. Descargalo con tools/build_dataset.py:\n"
            f"  python tools/build_dataset.py --symbol {symbol} --timeframe {tf} "
            f"--market swap --years 2 --exchanges {exchange}")
    return bt_data.load_parquet(path)


def _load_funding_best(funding_base, data_dir, *, exchange_hint=None):
    """Carga el funding del exchange MAS PROFUNDO desde el cache (Part C).

    Estrategia SIN RED (el harness nunca toca red): se RECORREN los caches por
    exchange (funding_oi.funding_path) de los candidatos y se elige el de mayor
    profundidad ya en disco. Esto reusa lo que el probe (probe_funding_depth /
    fetch_funding_history_best, corrido en Hetzner) escribio. Si ninguno existe
    -> error claro con el comando del probe.

    Devuelve (df_funding, source_exchange, depth_rows) donde depth_rows es la mini
    tabla de profundidad de los caches encontrados (para reportar in situ).
    """
    candidates = ([exchange_hint] if exchange_hint else []) + \
        [e for e in fo.FUNDING_EXCHANGE_CANDIDATES if e != exchange_hint]
    found = []
    for ex_id in candidates:
        symbol = fo.perp_symbol_for(ex_id, funding_base)
        path = fo.funding_path(data_dir, ex_id, symbol)
        if not os.path.exists(path):
            continue
        df = bt_data.load_parquet(path)
        if df is None or len(df) == 0:
            continue
        rng = fo._range_of(df)
        found.append({
            "exchange": ex_id, "symbol": symbol, "n_rows": int(len(df)),
            "start": rng[0], "end": rng[1],
            "months": fo._months_between(rng[0], rng[1]),
            "source": path, "ok": True, "error": None, "_df": df,
        })
    if not found:
        sys.exit(
            f"--funding-base {funding_base}: NO hay cache de funding en {data_dir} "
            f"para ningun exchange {list(fo.FUNDING_EXCHANGE_CANDIDATES)}.\n"
            f"Corre el probe (cachea por exchange) en el host CON red (Hetzner):\n"
            f"  python -c \"import funding_oi as fo; fo.probe_funding_depth("
            f"'{funding_base}', data_dir='{data_dir}')\"")
    found.sort(key=lambda r: r["months"], reverse=True)
    best = found[0]
    df = best.pop("_df")
    for r in found:
        r.pop("_df", None)
    return df, best, found


def _events_for_z(fund_zscore, df_primary, z_enter, z_exit, *,
                  stop_r_pct, target_rr):
    """Senal de reversion para un z_enter -> eventos (sin labelar todavia)."""
    pos = fs.funding_reversion_signal(fund_zscore, z_enter=z_enter, z_exit=z_exit)
    trades = fs.positions_to_trades(
        pos, df_primary, stop_r_pct=stop_r_pct, target_rr=target_rr)
    return pos, trades


def _label_and_oos(events, df_primary, sim_kwargs, ppy, *, max_bars,
                   n_splits, embargo):
    """label triple-barrier -> folds -> metricas OOS pooled. Devuelve
    (labeled, folds, valid_index, metrics, n_pool)."""
    if events is None or len(events) == 0:
        return None, [], np.array([], dtype=int), {}, 0
    labeled = lb.label_events(df_primary, events.to_dict("records"),
                              max_bars=max_bars)
    folds, valid_index = wf.folds_from_labeled(
        labeled, n_splits=n_splits, embargo=embargo)
    pooled = ab.pooled_oos_trades(labeled, folds, valid_index=valid_index)
    if pooled is None or len(pooled) == 0:
        return labeled, folds, valid_index, {}, 0
    res = eng.simulate(pooled, **sim_kwargs)
    metrics = met.metrics_from_result(res, periods_per_year=ppy)
    return labeled, folds, valid_index, metrics, len(pooled)


def main():
    p = argparse.ArgumentParser(
        description="Backtest DEFLACTADO de la reversion de funding (estructural).")
    p.add_argument("--exchange", default="okx",
                   help="exchange del OHLCV primario (cache). Default okx")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--funding-base", default=None,
                   help="base del perp de funding (BTC/SOL/ETH). Default: base de "
                        "--symbol. El cache de funding se busca por exchange (Part C).")
    p.add_argument("--funding-exchange", default=None,
                   help="forzar el exchange del cache de funding (si no, se elige el "
                        "MAS PROFUNDO en disco entre los candidatos)")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--tf-id", default="15m", choices=list(rr.TF_STACK),
                   help="TF primario (define entry_price/entry_ts)")
    p.add_argument("--max-bars", type=int, default=96,
                   help="barrera vertical del triple-barrier (velas del primario)")
    p.add_argument("--n-splits", type=int, default=8)
    p.add_argument("--embargo", type=int, default=8)
    p.add_argument("--risk-frac", type=float, default=0.01)
    p.add_argument("--equity0", type=float, default=10_000)
    p.add_argument("--stop-r-pct", type=float, default=0.01,
                   help="ancho del stop como fraccion del precio de entrada "
                        "(0.01 = 1%%). R = entry*stop_r_pct")
    p.add_argument("--target-rr", type=float, default=1.0,
                   help="multiplo de R hasta el TP (1.0 = +1R)")
    p.add_argument("--z-enter", type=float, default=2.0,
                   help="umbral de ENTRADA del fade |z|>=z_enter (config principal)")
    p.add_argument("--z-exit", type=float, default=0.5,
                   help="umbral de SALIDA |z|<=z_exit (histeresis; < z_enter)")
    p.add_argument("--z-win", type=int, default=96,
                   help="ventana del z-score de funding (en ventanas de funding ~8h)")
    p.add_argument("--z-sweep", default="",
                   help="lista de z_enter (coma) que arma el conjunto de INTENTOS del "
                        "veredicto DEFLATED. Vacio = sweep por defecto "
                        f"{','.join(str(z) for z in DEFAULT_Z_ENTER_SWEEP)}")
    p.add_argument("--out-of-time", default=None,
                   help="fecha de corte (YYYY-MM-DD): forward sin fuga. before "
                        "congela, after (jamas visto) se mide. El veredicto "
                        "DEFLATED se computa sobre el sweep en el AFTER.")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    base = args.funding_base or args.symbol.upper().replace("-", "/").split(":")[0].split("/")[0]

    print("=" * 72)
    print("  FUNDING RESEARCH — reversion de funding (ESTRUCTURAL), DEFLACTADO")
    print("=" * 72)

    # --- datos: primario + funding mas profundo del cache ---
    prim_tf = rr.TF_STACK[args.tf_id][0]
    df_primary = _load_primary(args.exchange, args.symbol, prim_tf, args.data_dir)
    df_funding, best, depth = _load_funding_best(
        base, args.data_dir, exchange_hint=args.funding_exchange)

    bar_minutes = rr.TF_MINUTES.get(prim_tf, 15.0)
    cost = rr._cost_for_symbol(args.symbol)
    sim_kwargs = {"equity0": args.equity0, "risk_frac": args.risk_frac,
                  "bar_minutes": bar_minutes, "cost": cost}

    print(f"\nprimario={args.exchange} {args.symbol} {prim_tf}: {len(df_primary)} velas "
          f"[{df_primary['timestamp'].iloc[0]} .. {df_primary['timestamp'].iloc[-1]}]")
    print(f"funding base={base} (Part C: cache mas profundo en disco):")
    for r in depth:
        mark = "  <- ELEGIDO" if r["exchange"] == best["exchange"] else ""
        print(f"    {r['exchange']:<12} {r['months']:>6.2f} meses  n={r['n_rows']:>5}  "
              f"[{r['start']} .. {r['end']}]{mark}")
    print(f"  >> fuente funding = {best['exchange']} ({best['months']:.2f} meses, "
          f"{best['n_rows']} filas). El backtest es tan profundo como esto.")
    print(f"  costos: taker={cost.taker_fee} slip_bps={cost.slippage_bps} "
          f"funding_8h={cost.funding_rate_8h}")

    # --- fund_zscore CAUSAL por barra del primario ---
    ff = fo.funding_oi_features(df_primary, df_funding, df_oi=None,
                                z_win=args.z_win)
    fund_z = ff["fund_zscore"].to_numpy()
    n_finite = int(np.isfinite(fund_z).sum())
    print(f"\nfund_zscore: {n_finite}/{len(fund_z)} barras con lectura "
          f"(z_win={args.z_win} ventanas de funding; el resto es warmup -> FLAT)")
    if n_finite < 50:
        print("  [AVISO] muy pocas barras con z (funding poco profundo): el read "
              "sera ruidoso. Es exactamente lo que decide forward-only vs backtest.")

    # --- senal principal (z_enter del usuario) -> eventos -> OOS ---
    ppy_all = rr._periods_per_year
    pos, trades = _events_for_z(
        fund_z, df_primary, args.z_enter, args.z_exit,
        stop_r_pct=args.stop_r_pct, target_rr=args.target_rr)
    n_long = int((pos == fs.LONG).sum())
    n_short = int((pos == fs.SHORT).sum())
    print(f"\n[1/3] senal de reversion (z_enter={args.z_enter} z_exit={args.z_exit}): "
          f"barras LONG={n_long} SHORT={n_short} FLAT={len(pos) - n_long - n_short} "
          f"-> {len(trades)} eventos (flancos de entrada/volteo)")
    if len(trades) == 0:
        print("  sin eventos (el funding nunca cruzo el umbral en esta ventana). "
              "Baja --z-enter o consigue funding mas profundo. Fin.")
        return

    labeled, folds, valid_index, metrics, n_pool = _label_and_oos(
        trades, df_primary, sim_kwargs,
        rr._periods_per_year(
            lb.label_events(df_primary, trades.to_dict("records"),
                            max_bars=args.max_bars), bar_minutes),
        max_bars=args.max_bars, n_splits=args.n_splits, embargo=args.embargo)
    print(f"\n[2/3] OOS pooled (walk-forward purgado, n_splits={args.n_splits} "
          f"embargo={args.embargo}): n={n_pool}")
    if metrics:
        print(met.format_report(metrics))
    else:
        print("  (sin trades OOS resueltos; sube historia / baja --z-enter / "
              "--n-splits)")

    # --- FORWARD out-of-time + [DEFLATED] sobre el SWEEP de z_enter ---
    z_sweep = _parse_float_list(args.z_sweep) if args.z_sweep else list(
        DEFAULT_Z_ENTER_SWEEP)
    print(f"\n[3/3] FORWARD + [DEFLATED] — sweep de z_enter (conjunto de intentos) = "
          f"{z_sweep}")
    if args.out_of_time:
        _funding_out_of_time(
            df_primary, fund_z, args, sim_kwargs, bar_minutes, z_sweep)
    else:
        # sin corte forward: el sweep DEFLATED se corre sobre el OOS pooled (in-sample
        # del backtest completo; menos riguroso que el forward, pero da un read).
        _funding_deflated_oos(
            df_primary, fund_z, args, sim_kwargs, bar_minutes, z_sweep)


def _funding_out_of_time(df_primary, fund_z, args, sim_kwargs, bar_minutes,
                         z_sweep):
    """FORWARD sin fuga: congela en --out-of-time y mide el sweep de z_enter SOLO
    en el AFTER jamas visto. Cada z_enter es un intento; DSR/PBO deshinchan el
    mejor. El z_enter NO se calibra mirando el after (es un grado de libertad
    declarado a priori), asi que el sweep entero es leakage-clean: se aplica el
    umbral al after y se mide. Reusa _print_deflated_verdict del runner real."""
    cut = pd.Timestamp(args.out_of_time)
    ts = pd.to_datetime(df_primary["timestamp"])
    if cut.tzinfo is not None and ts.dt.tz is None:
        cut = cut.tz_localize(None)
    after_mask = (ts >= cut).to_numpy()
    n_after = int(after_mask.sum())
    n_before = int((~after_mask).sum())
    print(f"  OUT-OF-TIME corte={args.out_of_time}: before={n_before} after={n_after} "
          f"barras (el after es jamas visto; el umbral z es a-priori, no calibrado)")
    if n_after < 50:
        print("  (after muy corto; mueve el corte o consigue mas historia)")
        return

    # baseline e_all del AFTER = la senal con el z_enter PRINCIPAL del usuario.
    _, base_trades = _events_for_z(
        fund_z, df_primary, args.z_enter, args.z_exit,
        stop_r_pct=args.stop_r_pct, target_rr=args.target_rr)
    m_all = _forward_metrics_after(
        base_trades, df_primary, after_mask, sim_kwargs, bar_minutes,
        max_bars=args.max_bars)
    e_all = m_all.get("expectancy_r") if m_all else None
    if m_all:
        print("  FORWARD (after) con z_enter principal = baseline e_all:")
        print(f"    n={m_all.get('n_trades')} exp_R={rr._f(m_all.get('expectancy_r'))} "
              f"total_ret={rr._f(m_all.get('total_return'))} "
              f"sharpe={rr._f(m_all.get('sharpe'))} PF={rr._f(m_all.get('profit_factor'))}")

    fwd_configs = []
    print("\n  sweep z_enter en el AFTER (cada uno es un intento; leakage-clean):")
    for z in z_sweep:
        z_exit = min(args.z_exit, 0.5 * z)         # histeresis proporcional
        _, tr = _events_for_z(fund_z, df_primary, z, z_exit,
                              stop_r_pct=args.stop_r_pct, target_rr=args.target_rr)
        ms = _forward_metrics_after(
            tr, df_primary, after_mask, sim_kwargs, bar_minutes,
            max_bars=args.max_bars)
        if ms is None:
            print(f"    z_enter={z:>4}: (sin trades forward)")
            continue
        e_z = ms.get("expectancy_r")
        edge = (e_z - e_all) if (e_all is not None and e_z is not None) else None
        ret = _forward_net_returns_after(
            tr, df_primary, after_mask, sim_kwargs, max_bars=args.max_bars)
        print(f"    z_enter={z:>4}: n={ms.get('n_trades'):>4} exp_R={rr._f(e_z)} "
              f"edge_vs_principal={rr._f(edge)} PF={rr._f(ms.get('profit_factor'))}")
        fwd_configs.append((f"z_enter={z}", ret, edge))

    print()
    try:
        rr._print_deflated_verdict(fwd_configs, m_all, args, sim_kwargs)
    except Exception as e:
        print(f"  [DEFLATED] no se pudo computar ({e})")


def _funding_deflated_oos(df_primary, fund_z, args, sim_kwargs, bar_minutes,
                          z_sweep):
    """Sin corte forward: corre el sweep de z_enter sobre el OOS pooled del
    backtest completo y deshincha el mejor (DSR/PBO). Read menos riguroso que el
    forward (es in-sample del backtest), pero util cuando no hay historia para un
    corte. Reusa _print_deflated_verdict."""
    print("  (sin --out-of-time: sweep sobre el OOS pooled del backtest completo; "
          "menos riguroso que el forward, pero da un read deflactado)")
    # Conjunto de intentos (un z_enter por intento). La baseline 'all' = expectancy
    # del z_enter MAS PERMISIVO (el que mas opera ~ la senal sin afinar el umbral);
    # edge_vs_all = cuanto mejora cada config respecto a esa base. DSR/PBO se
    # computan sobre los RETORNOS reales de cada config (correcto sea cual sea la
    # base; la base solo decide que config se rotula 'mejor' para el display).
    fwd_configs = []          # (label, returns, expectancy_oos)
    for z in z_sweep:
        z_exit = min(args.z_exit, 0.5 * z)
        _, tr = _events_for_z(fund_z, df_primary, z, z_exit,
                              stop_r_pct=args.stop_r_pct, target_rr=args.target_rr)
        labeled, folds, valid_index, metrics, n_pool = _label_and_oos(
            tr, df_primary, sim_kwargs,
            rr._periods_per_year(
                lb.label_events(df_primary, tr.to_dict("records"),
                                max_bars=args.max_bars), bar_minutes)
            if len(tr) else None,
            max_bars=args.max_bars, n_splits=args.n_splits, embargo=args.embargo)
        if not metrics or n_pool == 0:
            print(f"    z_enter={z:>4}: (sin OOS)")
            continue
        pooled = ab.pooled_oos_trades(labeled, folds, valid_index=valid_index)
        ret = rr._forward_net_returns(pooled, sim_kwargs)
        e_z = metrics.get("expectancy_r")
        print(f"    z_enter={z:>4}: n={n_pool:>4} exp_R={rr._f(e_z)} "
              f"PF={rr._f(metrics.get('profit_factor'))}")
        fwd_configs.append((f"z_enter={z}", ret, e_z))
    # baseline 'all' = el z_enter mas bajo evaluado (el que mas opera).
    e_all = fwd_configs[0][2] if fwd_configs else None
    deflated_configs = [
        (lbl, ret, (e_z - e_all if (e_all is not None and e_z is not None) else None))
        for (lbl, ret, e_z) in fwd_configs]
    print()
    try:
        rr._print_deflated_verdict(deflated_configs, {"expectancy_r": e_all},
                                   args, sim_kwargs)
    except Exception as e:
        print(f"  [DEFLATED] no se pudo computar ({e})")


def _forward_metrics_after(trades, df_primary, after_mask, sim_kwargs,
                           bar_minutes, *, max_bars):
    """Labela los eventos y mide SOLO los que ENTRAN en el after (entry_index en
    la zona after). El labeling usa velas posteriores de TODO df_primary (el after
    puede cerrar despues del corte, eso es fisico). Devuelve metrics o None."""
    if trades is None or len(trades) == 0:
        return None
    labeled = lb.label_events(df_primary, trades.to_dict("records"),
                              max_bars=max_bars)
    after_idx = np.flatnonzero(after_mask)
    if len(after_idx) == 0:
        return None
    keep = labeled["entry_index"].isin(set(after_idx.tolist()))
    sub = labeled[keep & labeled["outcome"].notna()]
    if len(sub) == 0:
        return None
    ppy = rr._periods_per_year(sub, bar_minutes)
    res = eng.simulate(sub, **sim_kwargs)
    return met.metrics_from_result(res, periods_per_year=ppy)


def _forward_net_returns_after(trades, df_primary, after_mask, sim_kwargs, *,
                               max_bars):
    """Retornos net-de-costes por trade del subset que entra en el after (mismas
    unidades que _forward_net_returns: eng.simulate(...)['returns'])."""
    if trades is None or len(trades) == 0:
        return np.array([], dtype="float64")
    labeled = lb.label_events(df_primary, trades.to_dict("records"),
                              max_bars=max_bars)
    after_idx = set(np.flatnonzero(after_mask).tolist())
    sub = labeled[labeled["entry_index"].isin(after_idx)]
    return rr._forward_net_returns(sub, sim_kwargs)


if __name__ == "__main__":
    main()
