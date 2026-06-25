#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COSECHA SHARDED — paraleliza el replay denso por RANGOS DE FECHA y mergea cubos.

El replay (recorrer el histórico disparando el motor) es single-thread y el ~99%
del costo. Shardearlo por fecha lo reparte en N procesos -> ~22h baja a ~22h/N
(en un VPS dedicado con N núcleos). Cada shard corre run_research_real con
--date-start/--date-end (recorta los dfs con buffer de lookback+horizonte y
filtra eventos a [start,end)); el merge los une por entry_ts. Correctitud POR
CONSTRUCCIÓN (cero solape entre shards) + modo --verify que la comprueba.

Uso (en el VPS dedicado; ver ops/SELF_HOSTED_RUNNER.md):
  # 1) VERIFICAR correctitud (rápido, ~minutos) ANTES de la cosecha grande:
  python tools/cosecha_shard.py --symbol SOL/USDT --verify
  # 2) cosecha completa (máxima data, paralela):
  python tools/cosecha_shard.py --symbol SOL/USDT --shards 8 --workers 8 \
      --step 1 --out tp_cube_SOL_USDT.parquet

El cubo resultante se analiza con bt_tp_selector (run / run_pooled --sweep).
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
import bt_data  # noqa: E402

CUBE_KEY = ["entry_ts", "tp", "horizon"]
_TS = "%Y-%m-%d %H:%M:%S"


def _data_range(exchange, symbol, tf, data_dir):
    path = bt_data.dataset_path(data_dir, exchange, symbol, tf)
    if not os.path.exists(path):
        sys.exit("falta el dataset %s; corre tools/build_dataset.py primero (%s)"
                 % (tf, path))
    ts = pd.to_datetime(bt_data.load_parquet(path)["timestamp"])
    return ts.min(), ts.max()


def chunks(start, end, n):
    """n rangos [a,b) contiguos que tilean [start, end]."""
    edges = pd.date_range(start, end, periods=n + 1)
    return [(edges[i], edges[i + 1]) for i in range(n)]


def merge_cubes(paths):
    """Une cubos parciales: concat + dedup por (entry_ts,tp,horizon) + sort.
    Función pura (testeable sin replay)."""
    frames = [pd.read_parquet(p) for p in paths
              if os.path.exists(p) and os.path.getsize(p)]
    if not frames:
        return None
    cube = pd.concat(frames, ignore_index=True)
    cube["entry_ts"] = pd.to_datetime(cube["entry_ts"])
    return (cube.drop_duplicates(CUBE_KEY)
            .sort_values(CUBE_KEY).reset_index(drop=True))


def _run_shard(args, a, b, out):
    cmd = [sys.executable, os.path.join(ROOT, "tools", "run_research_real.py"),
           "--exchange", args.exchange, "--symbol", args.symbol,
           "--tf-id", args.tf_id, "--step", str(args.step),
           "--max-bars", str(args.max_bars), "--n-splits", str(args.n_splits),
           "--embargo", str(args.embargo), "--seed", str(args.seed),
           "--min-lookback", str(args.min_lookback),
           "--horizon-sweep", args.horizon_sweep,
           "--date-start", a.strftime(_TS), "--date-end", b.strftime(_TS),
           "--tp-cube-out", out]
    # cube-only: SIN --retrieval/--tp-sl-grid -> más rápido. El gate ORO/leakage
    # se reconstruye UNA vez sobre el cubo merged si se quiere (run normal).
    with open(out + ".log", "w") as fh:
        rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                            cwd=ROOT).returncode
    return out, rc


def _replay_range(args, a, b, n_shards, tmp, tag):
    """Corre [a,b) en n_shards (paralelo) y devuelve el cubo merged."""
    cks = chunks(a, b, n_shards)
    outs = [os.path.join(tmp, "%s_%02d.parquet" % (tag, i)) for i in range(len(cks))]
    fails = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_run_shard, args, x, y, o): i
                for i, ((x, y), o) in enumerate(zip(cks, outs))}
        for f in cf.as_completed(futs):
            o, rc = f.result()
            i = futs[f]
            print("  [%s] shard %02d [%s..%s] rc=%d%s" % (
                tag, i, cks[i][0].date(), cks[i][1].date(), rc,
                "" if rc == 0 else "  FALLO -> " + o + ".log"))
            if rc != 0:
                fails.append(i)
    if fails:
        sys.exit("shards fallidos en %s: %s" % (tag, fails))
    return merge_cubes(outs)


def cosecha(args):
    s, e = _data_range(args.exchange, args.symbol, args.tf_id, args.data_dir)
    if args.date_start:
        s = max(s, pd.to_datetime(args.date_start))
    if args.date_end:
        e = min(e, pd.to_datetime(args.date_end))
    print("cosecha %s: data [%s .. %s] -> %d shards / %d en paralelo"
          % (args.symbol, s.date(), e.date(), args.shards, args.workers))
    tmp = tempfile.mkdtemp(prefix="cosecha_")
    cube = _replay_range(args, s, e, args.shards, tmp, "cosecha")
    if cube is None or len(cube) == 0:
        sys.exit("merge vacío: ningún shard produjo cubo")
    cube.to_parquet(args.out, index=False)
    print("\nLISTO: %d filas | %d eventos -> %s"
          % (len(cube), cube["entry_ts"].nunique(), args.out))


def verify(args):
    """Corre un rango chico (1) sin shardear y (2) en 2 shards; los cubos deben
    ser IDÉNTICOS. Es la garantía de que el sharding no corrompe la cosecha."""
    s, e = _data_range(args.exchange, args.symbol, args.tf_id, args.data_dir)
    vs = e - pd.Timedelta(days=args.verify_days)
    vs = max(vs, s)
    print("VERIFY %s: rango [%s .. %s] (1-shard vs 2-shards)"
          % (args.symbol, vs.date(), e.date()))
    tmp = tempfile.mkdtemp(prefix="verify_")
    one = _replay_range(args, vs, e, 1, tmp, "one")
    two = _replay_range(args, vs, e, 2, tmp, "two")
    if one is None or two is None:
        sys.exit("VERIFY sin datos: el rango no produjo eventos (sube --verify-days)")
    ok = one.shape == two.shape and len(one) == len(two)
    cols = [c for c in ("entry_ts", "tp", "horizon", "pnl_r", "outcome",
                        "mfe_r", "mae_r") if c in one.columns and c in two.columns]
    if ok:
        a = one[cols].reset_index(drop=True)
        b = two[cols].reset_index(drop=True)
        num = [c for c in ("pnl_r", "mfe_r", "mae_r") if c in cols]
        same = (a.drop(columns=num).equals(b.drop(columns=num))
                and all(float((a[c] - b[c]).abs().max() or 0) < 1e-9 for c in num))
        ok = bool(same)
    print("\n%s  1-shard: %d filas / %d eventos | 2-shards: %d / %d"
          % ("✅ IDÉNTICOS" if ok else "❌ DIFIEREN", len(one),
             one["entry_ts"].nunique(), len(two), two["entry_ts"].nunique()))
    if not ok:
        print("  El sharding NO reproduce el cubo sin shardear: NO usar para la "
              "cosecha grande hasta arreglar (revisa buffers lookback/horizonte).")
        sys.exit(1)
    print("  Sharding correcto: la cosecha grande es segura.")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", required=True)
    p.add_argument("--exchange", default="okx")
    p.add_argument("--tf-id", default="5m")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--shards", type=int, default=8)
    p.add_argument("--workers", type=int, default=8, help="procesos en paralelo")
    p.add_argument("--step", type=int, default=1)
    p.add_argument("--max-bars", type=int, default=288)
    p.add_argument("--n-splits", type=int, default=7)
    p.add_argument("--embargo", type=int, default=8)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--min-lookback", type=int, default=300)
    p.add_argument("--horizon-sweep", default="96,288,576")
    p.add_argument("--date-start", default=None)
    p.add_argument("--date-end", default=None)
    p.add_argument("--out", default=None, help="cubo parquet final (cosecha)")
    p.add_argument("--verify", action="store_true",
                   help="comprueba sharded==sin-shardear en un rango chico y sale")
    p.add_argument("--verify-days", type=int, default=120)
    args = p.parse_args(argv)
    if args.verify:
        return verify(args)
    if not args.out:
        sys.exit("--out requerido para la cosecha (o usa --verify)")
    return cosecha(args)


if __name__ == "__main__":
    main()
