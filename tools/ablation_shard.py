#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PODA SHARDED — paraleliza la ablacion de modulos por RANGOS DE FECHA.

La poda son 4 replays (baseline + scorer/regime/session_bias OFF). Cada replay es
single-thread y el ~99% del costo. Este orquestador shardea CADA variante por fecha
(reusando el mecanismo VERIFICADO de tools/cosecha_shard.py: chunks sin solape +
rango de datos), mergea los eventos crudos y computa la metrica OOS con la MISMA
ruta de codigo que el run normal (run_research_real --events-in) -> numeros
IDENTICOS a la poda sin shardear, solo que en paralelo sobre N cores. Permite subir
la densidad (step1) sin que el tiempo se dispare.

Flujo por variante:
  1) shard [s,e) en N rangos; cada shard corre run_research_real --events-out con el
     toggle del modulo por ENV (fires-only, rapido) -> eventos crudos del rango.
  2) merge por entry_ts (cero solape entre shards -> ni duplica ni pierde).
  3) run_research_real --events-in re-deriva entry_index global y corre
     label+fold+OOS IDENTICO al run normal -> expectancy_r + cadencia (n_fired).
Veredicto §6.6: MATAR solo si delta<=0 Y la cadencia sube >=20% (quitarlo no daña Y
compra senales); si delta>0 el modulo VIVE; si no, QUEDA (inerte, no paga cadencia).

Correctitud: --verify corre un rango chico 1-shard vs 2-shards y exige eventos
IDENTICOS (igual que cosecha_shard --verify). Correrlo ANTES de la poda grande.

Uso (self-hosted; ver ops/SELF_HOSTED_RUNNER.md):
  python tools/ablation_shard.py --symbol SOL/USDT --verify
  python tools/ablation_shard.py --symbol SOL/USDT --shards 8 --workers 8 --step 1 \
      --out research_out/research_real.txt
"""
import argparse
import concurrent.futures as cf
import json
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

# variante -> env toggle (modulo OFF). baseline = sin toggle.
VARIANTS = [
    ("baseline",     {}),
    ("scorer",       {"FQ_USE_SCORER": "0"}),
    ("regime",       {"FQ_USE_REGIME": "0"}),
    ("session_bias", {"FQ_SESSION_BIAS": "0"}),
]
# §6.6: sus features alimentan el VECTOR del gate ORO (bt_retrieval) -> apagarlos en
# prod desalinea la query del indice aunque el delta de motor sea 0. NO removibles.
GATE_COUPLED = {"scorer", "regime"}


def _merge_events(paths):
    """Une los eventos crudos de los shards: concat + dedup por entry_ts + sort."""
    frames = []
    for p in paths:
        if p and os.path.exists(p):
            try:
                df = pd.read_parquet(p)
            except Exception:
                continue
            if len(df):
                frames.append(df)
    if not frames:
        return None
    ev = pd.concat(frames, ignore_index=True)
    ev["entry_ts"] = pd.to_datetime(ev["entry_ts"])
    return (ev.drop_duplicates("entry_ts").sort_values("entry_ts")
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
            "--date-start", a.strftime(_TS), "--date-end", b.strftime(_TS),
            "--events-out", out]


def _run_one(cmd, env, logpath):
    with open(logpath, "w") as fh:
        return subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                              cwd=ROOT, env=env).returncode


def _replay_variant(args, s, e, n_shards, env_toggle, tmp, tag):
    """Shardea [s,e) para UNA variante (su toggle por env) y devuelve los eventos
    crudos mergeados."""
    cks = cs.chunks(s, e, n_shards)
    outs = [os.path.join(tmp, "%s_%02d.parquet" % (tag, i)) for i in range(len(cks))]
    env = {**os.environ, **env_toggle, "FQ_USE_THOMPSON": "0"}
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
    return _merge_events(outs)


def _metric_of(args, events_path):
    """run_research_real --events-in --metric-out sobre el cubo mergeado de una
    variante. La metrica corre por la MISMA ruta que el run normal."""
    mout = events_path + ".metric.json"
    cmd = [sys.executable, RRR,
           "--exchange", args.exchange, "--symbol", args.symbol,
           "--tf-id", args.tf_id, "--max-bars", str(args.max_bars),
           "--n-splits", str(args.n_splits), "--embargo", str(args.embargo),
           "--target-level", args.target_level, "--horizon-sweep", args.horizon_sweep,
           "--events-in", events_path, "--metric-out", mout]
    env = {**os.environ, "FQ_USE_THOMPSON": "0"}
    rc = _run_one(cmd, env, events_path + ".metric.log")
    if rc != 0 or not os.path.exists(mout):
        sys.exit("fallo computando metrica de %s (ver %s.metric.log)"
                 % (events_path, events_path))
    with open(mout) as fh:
        return json.load(fh)


def poda(args):
    s, e = cs._data_range(args.exchange, args.symbol, args.tf_id, args.data_dir)
    if args.date_start:
        s = max(s, pd.to_datetime(args.date_start))
    if args.date_end:
        e = min(e, pd.to_datetime(args.date_end))
    print("PODA SHARDED %s: data [%s .. %s] | step=%d | %d shards / %d en paralelo"
          % (args.symbol, s.date(), e.date(), args.step, args.shards, args.workers))
    tmp = tempfile.mkdtemp(prefix="poda_")
    results = {}
    for name, toggle in VARIANTS:
        print("\n== variante %s %s ==" % (name, toggle or "(baseline)"))
        ev = _replay_variant(args, s, e, args.shards, toggle, tmp, name)
        if ev is None or len(ev) == 0:
            print("  (sin eventos)")
            results[name] = {"expectancy_r": None, "n_fired": 0, "n_oos": 0}
            continue
        evp = os.path.join(tmp, "%s_merged.parquet" % name)
        ev.to_parquet(evp, index=False)
        m = _metric_of(args, evp)
        results[name] = m
        print("  -> expectancy_r=%s  n_fired=%s  n_oos=%s"
              % (m.get("expectancy_r"), m.get("n_fired"), m.get("n_oos")))
    _report(args, results)


def _report(args, results):
    base = results.get("baseline", {})
    bexp = base.get("expectancy_r")
    bn = base.get("n_fired") or 0
    out = []
    out.append("=" * 70)
    out.append("  PODA SHARDED — %s  (step=%d, %d shards, densidad alta)"
               % (args.symbol, args.step, args.shards))
    out.append("=" * 70)
    out.append("baseline expectancy_r=%s (n_fired=%s, n_oos=%s)"
               % (_f(bexp), bn, base.get("n_oos")))
    out.append("regla §6.6: MATAR solo si delta<=0 Y la cadencia sube >=20%; "
               "delta>0 -> VIVE; si no -> QUEDA (inerte).")
    for name, _ in VARIANTS:
        if name == "baseline":
            continue
        r = results.get(name, {})
        wexp = r.get("expectancy_r")
        wn = r.get("n_fired") or 0
        delta = (bexp - wexp) if (bexp is not None and wexp is not None) else None
        dn = ((wn - bn) / bn) if bn else 0.0
        verdict = _verdict(delta, dn)
        flag = "  [acoplado al gate ORO: NO apagar en prod]" \
            if name in GATE_COUPLED else ""
        out.append("[%s] %-14s sin_el expectancy_r=%s delta=%s (n=%s, dn=%+.0f%%)%s"
                   % (verdict, name, _f(wexp), _f(delta), wn, dn * 100.0, flag))
    txt = "\n".join(out)
    print("\n" + txt)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as fh:
            fh.write(txt + "\n")
        print("\n-> %s" % args.out)


def verify(args):
    """1-shard vs 2-shards en un rango chico: los eventos crudos deben ser
    IDENTICOS. Garantia de que shardear no corrompe la poda. Por defecto chequea
    baseline (la correctitud del sharding es independiente del toggle); --verify-all
    lo prueba con cada modulo OFF tambien."""
    s, e = cs._data_range(args.exchange, args.symbol, args.tf_id, args.data_dir)
    vs = max(e - pd.Timedelta(days=args.verify_days), s)
    print("VERIFY %s: rango [%s .. %s] (1-shard vs 2-shards)"
          % (args.symbol, vs.date(), e.date()))
    tmp = tempfile.mkdtemp(prefix="podaverify_")
    variants = VARIANTS if args.verify_all else VARIANTS[:1]
    bad = []
    for name, toggle in variants:
        one = _replay_variant(args, vs, e, 1, toggle, tmp, name + "_1")
        two = _replay_variant(args, vs, e, 2, toggle, tmp, name + "_2")
        n1 = 0 if one is None else len(one)
        n2 = 0 if two is None else len(two)
        same = (n1 == n2) and (n1 == 0 or one["entry_ts"].reset_index(drop=True)
                               .equals(two["entry_ts"].reset_index(drop=True)))
        print("  %-14s 1-shard: %d eventos | 2-shards: %d -> %s"
              % (name, n1, n2, "OK" if same else "DIFIERE"))
        if not same:
            bad.append(name)
    if bad:
        sys.exit("VERIFY FALLO: el sharding NO reproduce los eventos en %s "
                 "-> NO usar para la poda." % bad)
    print("\nVERIFY OK: el sharding reproduce la poda exacta. Seguro para la grande.")


def _verdict(delta, dn):
    """Regla §6.6. delta = expectancy baseline - sin_modulo; dn = cambio de cadencia.
    VIVE (delta>0: quitarlo empeora -> aporta) > MATAR (delta<=0 Y dn>=20%: no dana
    Y compra senales) > QUEDA (inerte: no dana pero no paga cadencia)."""
    if delta is None:
        return "?    "
    if delta > 0:
        return "VIVE "
    if dn >= 0.20:
        return "MATAR"
    return "QUEDA"


def _f(v):
    try:
        return "%.4f" % float(v)
    except (TypeError, ValueError):
        return "n/a"


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", required=True)
    p.add_argument("--exchange", default="okx")
    p.add_argument("--tf-id", default="5m")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--shards", type=int, default=8)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--step", type=int, default=1,
                   help="densidad del replay (1 = maxima; la poda vieja usaba 3)")
    p.add_argument("--max-bars", type=int, default=288)
    p.add_argument("--n-splits", type=int, default=7)
    p.add_argument("--embargo", type=int, default=8)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--min-lookback", type=int, default=300)
    p.add_argument("--target-level", default="tp1")
    p.add_argument("--horizon-sweep", default="96,288,576")
    p.add_argument("--date-start", default=None)
    p.add_argument("--date-end", default=None)
    p.add_argument("--out", default=None, help="ruta del reporte de texto")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--verify-all", action="store_true",
                   help="con --verify, prueba cada variante (no solo baseline)")
    p.add_argument("--verify-days", type=int, default=90)
    args = p.parse_args(argv)
    if args.verify:
        verify(args)
    else:
        poda(args)


if __name__ == "__main__":
    main()
