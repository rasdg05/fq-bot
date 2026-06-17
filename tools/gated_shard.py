#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GATEADO SHARDED — paraleliza el replay DENSO por RANGOS DE FECHA y corre el
analisis gateado (retrieval + quality_gate + grids) + out-of-time UNA vez sobre
los estados mergeados.

El replay denso (estado de CADA vela disparando el motor) es single-thread y el
~99% del costo. Este orquestador shardea ese replay por fecha (reusando el
mecanismo VERIFICADO de tools/cosecha_shard.py: chunks sin solape + rango de
datos), mergea los ESTADOS DENSOS por entry_ts y corre el research gateado con la
MISMA ruta de codigo que el run normal (run_research_real --states-in) -> numeros
IDENTICOS al run sin shardear, solo que el replay va en paralelo sobre N cores.
A diferencia de la poda (ablation_shard, fires-only, N variantes), aqui es UNA
sola config y los estados son DENSOS (todas las velas, para el retrieval denso).

Flujo:
  1) shard [s,e) en N rangos; cada shard corre run_research_real --states-out
     (replay DENSO, filtra al rango) -> estados densos del rango.
  2) merge por entry_ts (cero solape entre shards -> ni duplica ni pierde).
  3) run_research_real --states-in re-deriva entry_index global y corre el
     analisis IDENTICO al run normal (OOS/modelo/retrieval denso/quality_gate/
     OOT/grids). Su stdout ES el reporte gateado+OOT.

Correctitud: --verify corre un rango chico 1-shard vs 2-shards (replay denso con
--states-out) y exige estados IDENTICOS por entry_ts (igual que cosecha_shard /
ablation_shard --verify). Correrlo ANTES de la corrida grande.

Uso (self-hosted; ver ops/SELF_HOSTED_RUNNER.md):
  python tools/gated_shard.py --symbol SOL/USDT --verify
  python tools/gated_shard.py --symbol SOL/USDT --shards 8 --workers 8 \
      --out research_out/research_real.txt
"""
import argparse
import concurrent.futures as cf
import os
import subprocess
import sys
import tempfile

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import cosecha_shard as cs  # noqa: E402  (reusa _data_range, chunks)

_TS = "%Y-%m-%d %H:%M:%S"
RRR = os.path.join(ROOT, "tools", "run_research_real.py")


def _merge_states(paths):
    """Une los estados densos de los shards: concat + dedup por entry_ts + sort.
    Funcion pura (testeable sin replay)."""
    frames = []
    for p in paths:
        if p and os.path.exists(p) and os.path.getsize(p):
            try:
                df = pd.read_parquet(p)
            except Exception:
                continue
            if len(df):
                frames.append(df)
    if not frames:
        return None
    st = pd.concat(frames, ignore_index=True)
    st["entry_ts"] = pd.to_datetime(st["entry_ts"])
    return (st.drop_duplicates("entry_ts").sort_values("entry_ts")
            .reset_index(drop=True))


def _shard_cmd(args, a, b, out):
    return [sys.executable, RRR,
            "--exchange", args.exchange, "--symbol", args.symbol,
            "--tf-id", args.tf_id, "--step", str(args.step),
            "--max-bars", str(args.max_bars), "--n-splits", str(args.n_splits),
            "--embargo", str(args.embargo), "--seed", str(args.seed),
            "--min-lookback", str(args.min_lookback),
            "--target-level", args.target_level,
            "--horizon-sweep", args.horizon_sweep,
            "--dense-horizon", str(args.dense_horizon),
            "--date-start", a.strftime(_TS), "--date-end", b.strftime(_TS),
            "--states-out", out]


def _run_one(cmd, env, logpath):
    with open(logpath, "w") as fh:
        return subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                              cwd=ROOT, env=env).returncode


def _replay_dense(args, s, e, n_shards, tmp, tag):
    """Shardea [s,e) en n_shards (replay DENSO en paralelo) y devuelve los estados
    densos mergeados."""
    cks = cs.chunks(s, e, n_shards)
    outs = [os.path.join(tmp, "%s_%02d.parquet" % (tag, i)) for i in range(len(cks))]
    env = {**os.environ, "FQ_USE_THOMPSON": "0"}
    fails = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_run_one, _shard_cmd(args, x, y, o), env, o + ".log"): i
                for i, ((x, y), o) in enumerate(zip(cks, outs))}
        for f in cf.as_completed(futs):
            rc = f.result()
            i = futs[f]
            print("  [%s] shard %02d [%s..%s] rc=%d%s" % (
                tag, i, cks[i][0].date(), cks[i][1].date(), rc,
                "" if rc == 0 else "  FALLO -> " + outs[i] + ".log"))
            if rc != 0:
                fails.append(i)
    if fails:
        sys.exit("shards fallidos en %s: %s" % (tag, fails))
    return _merge_states(outs)


def _gated_cmd(args, states_path):
    """run_research_real --states-in sobre el merge denso: corre el analisis
    gateado completo (retrieval denso + quality_gate + grids + vector_ablation) y,
    si hay corte, la prueba out-of-time. Su stdout ES el reporte gateado+OOT."""
    cmd = [sys.executable, RRR,
           "--exchange", args.exchange, "--symbol", args.symbol,
           "--tf-id", args.tf_id, "--max-bars", str(args.max_bars),
           "--n-splits", str(args.n_splits), "--embargo", str(args.embargo),
           "--seed", str(args.seed), "--target-level", args.target_level,
           "--horizon-sweep", args.horizon_sweep,
           "--dense-horizon", str(args.dense_horizon),
           "--states-in", states_path,
           "--retrieval", "--retrieval-backend", "turbovec",
           "--tp-sl-grid", "--quality-gate", "--vector-ablation"]
    if args.out_of_time:
        cmd += ["--out-of-time", args.out_of_time]
    # CROSS-ASSET: el lider (p.ej. BTC/USDT) se inyecta SOLO en el analisis sobre
    # el merge (--states-in). run_research_real anexa las xbtc_* DESPUES de cargar
    # los estados; los shards (--states-out) retornan ANTES de esa inyeccion, por
    # eso NO lo lleva _shard_cmd (los estados densos se replayean crudos y el
    # cross-asset entra una sola vez aqui, sobre el merge global).
    if args.cross_asset:
        cmd += ["--cross-asset", args.cross_asset]
    return cmd


def gated(args):
    s, e = cs._data_range(args.exchange, args.symbol, args.tf_id, args.data_dir)
    if args.date_start:
        s = max(s, pd.to_datetime(args.date_start))
    if args.date_end:
        e = min(e, pd.to_datetime(args.date_end))
    print("GATEADO SHARDED %s: data [%s .. %s] | step=%d | %d shards / %d en paralelo"
          % (args.symbol, s.date(), e.date(), args.step, args.shards, args.workers))
    tmp = tempfile.mkdtemp(prefix="gated_")
    st = _replay_dense(args, s, e, args.shards, tmp, "gated")
    if st is None or len(st) == 0:
        sys.exit("merge vacio: ningun shard produjo estados")
    stp = os.path.join(tmp, "gated_merged.parquet")
    st.to_parquet(stp, index=False)
    print("\nmerge: %d estados | %d eventos (fired) -> %s"
          % (len(st), int(st["fired"].sum()) if "fired" in st.columns else 0, stp))

    # Analisis gateado + OOT UNA vez sobre el merge (stdout = reporte).
    print("\n== analisis gateado + retrieval + out-of-time (sobre el merge) ==")
    cmd = _gated_cmd(args, stp)
    env = {**os.environ, "FQ_USE_THOMPSON": "0"}
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          cwd=ROOT, env=env)
    txt = proc.stdout.decode("utf-8", errors="replace")
    print(txt)
    if proc.returncode != 0:
        sys.exit("el analisis gateado fallo (rc=%d); ver salida arriba"
                 % proc.returncode)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as fh:
            fh.write(txt)
        print("\n-> %s" % args.out)


def verify(args):
    """1-shard vs 2-shards en un rango chico: los estados densos deben ser
    IDENTICOS por entry_ts (mismo n y misma serie). Garantia de que shardear el
    replay denso no corrompe el gateado. Igual que cosecha_shard/ablation_shard
    --verify. Correrlo ANTES de la corrida grande."""
    s, e = cs._data_range(args.exchange, args.symbol, args.tf_id, args.data_dir)
    vs = max(e - pd.Timedelta(days=args.verify_days), s)
    print("VERIFY %s: rango [%s .. %s] (1-shard vs 2-shards, replay denso)"
          % (args.symbol, vs.date(), e.date()))
    tmp = tempfile.mkdtemp(prefix="gatedverify_")
    one = _replay_dense(args, vs, e, 1, tmp, "one")
    two = _replay_dense(args, vs, e, 2, tmp, "two")
    if one is None or two is None:
        sys.exit("VERIFY sin datos: el rango no produjo estados (sube --verify-days)")
    n1, n2 = len(one), len(two)
    same = (n1 == n2) and one["entry_ts"].reset_index(drop=True).equals(
        two["entry_ts"].reset_index(drop=True))
    print("\n%s  1-shard: %d estados | 2-shards: %d"
          % ("IDENTICOS" if same else "DIFIEREN", n1, n2))
    if not same:
        print("  El sharding NO reproduce los estados sin shardear: NO usar para la "
              "corrida grande hasta arreglar (revisa buffers lookback/horizonte).")
        sys.exit(1)
    print("  Sharding correcto: el replay denso sharded reproduce el gateado exacto.")


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", required=True)
    p.add_argument("--exchange", default="okx")
    p.add_argument("--tf-id", default="5m")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--shards", type=int, default=8)
    p.add_argument("--workers", type=int, default=8, help="procesos en paralelo")
    p.add_argument("--step", type=int, default=1,
                   help="densidad del replay (1 = maxima)")
    p.add_argument("--max-bars", type=int, default=288)
    p.add_argument("--n-splits", type=int, default=7)
    p.add_argument("--embargo", type=int, default=8)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--min-lookback", type=int, default=300)
    p.add_argument("--target-level", default="tp1")
    p.add_argument("--horizon-sweep", default="96,288,576")
    p.add_argument("--dense-horizon", type=int, default=288,
                   help="velas forward para el label de retorno en ATR (denso)")
    p.add_argument("--out-of-time", default=None,
                   help="fecha de corte (p.ej. 2025-06-01) para la prueba forward")
    p.add_argument("--cross-asset", default=None,
                   help="simbolo LIDER cross-asset (p.ej. BTC/USDT) -> features "
                        "lead-lag CAUSALES (xbtc_*). Se pasa SOLO al analisis "
                        "--states-in (run_research_real inyecta tras cargar el "
                        "merge); los shards --states-out van crudos.")
    p.add_argument("--date-start", default=None)
    p.add_argument("--date-end", default=None)
    p.add_argument("--out", default="research_out/research_real.txt",
                   help="ruta del reporte gateado+OOT (stdout del run --states-in)")
    p.add_argument("--verify", action="store_true",
                   help="comprueba sharded==sin-shardear en un rango chico y sale")
    p.add_argument("--verify-days", type=int, default=90)
    args = p.parse_args(argv)
    if args.verify:
        return verify(args)
    return gated(args)


if __name__ == "__main__":
    main()
