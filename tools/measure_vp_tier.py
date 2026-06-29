#!/usr/bin/env python3
"""measure_vp_tier — ¿el Volume Profile del día PREVIO mejora el edge del cube?

Para cada evento del cube (tp4/h576), calcula el perfil de volumen del día UTC
ANTERIOR (causal: conocido al abrir) sobre las klines y clasifica la entrada:
  premium   = entry_price > VAH(prev)     (caro, sobre el value area)
  discount  = entry_price < VAL(prev)      (barato, bajo el value area)
  value     = dentro del value area
  + cercanía al POC (|entry-POC| / mitad-ancho-VA).

Mide meanR/WR/n por zona, y la tesis Market-Profile/ICT condicionada a dirección:
  rev-aligned  = long&discount o short&premium  (reversión a value)
  rev-against  = long&premium  o short&discount
GROSS (pnl_r del cube es pre-coste): radar, no veredicto neto.

  python tools/measure_vp_tier.py \
    --cube cosecha_cubes/tp_cube_BTC_USDT.parquet \
    --klines data/kl_hist_BTCUSDT.parquet --label BTC
"""
import argparse
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import volume_profile as vpm  # noqa: E402


def _stats(r):
    r = np.asarray(r, float)
    if r.size == 0:
        return dict(n=0, meanR=float("nan"), WR=float("nan"))
    return dict(n=int(r.size), meanR=float(r.mean()), WR=float((r > 0).mean()))


def tag_events(cube_path, kl_path, *, tp="tp4", horizon=576, n_bins=50, va_pct=0.70):
    c = pd.read_parquet(cube_path)
    c["tp"] = c["tp"].astype(str)
    c["horizon"] = c["horizon"].astype(int)
    e = c[(c.tp == tp) & (c.horizon == horizon)].drop_duplicates("entry_index").copy()
    e["ts"] = pd.to_datetime(e["entry_ts"])
    e["day"] = e["ts"].dt.normalize()

    k = pd.read_parquet(kl_path).sort_values("ts").reset_index(drop=True)
    k["dt"] = pd.to_datetime(k["ts"], unit="ms", utc=True).dt.tz_localize(None)
    k["day"] = k["dt"].dt.normalize()

    # perfil por día UTC, y mapa día -> perfil del día ANTERIOR (causal)
    profiles, order = {}, []
    for day, g in k.groupby("day"):
        p = vpm.volume_profile(g, n_bins=n_bins, va_pct=va_pct)
        if p is not None:
            profiles[day] = p
            order.append(day)
    prior = {d: (profiles[order[i - 1]] if i > 0 else None) for i, d in enumerate(order)}

    def _zone(row):
        p = prior.get(row["day"])
        if p is None:
            return pd.Series([np.nan, np.nan], index=["vp_zone", "poc_dist"])
        z = vpm.vp_position(row["entry_price"], p)
        half = max((p.vah - p.val) / 2.0, 1e-9)
        d = abs(row["entry_price"] - p.poc) / half          # 0=en POC, 1=borde VA
        return pd.Series([z, d], index=["vp_zone", "poc_dist"])

    e[["vp_zone", "poc_dist"]] = e.apply(_zone, axis=1)
    return e[e.vp_zone.notna()].copy()


def report(e, label):
    base = _stats(e.pnl_r)
    print("\n===== %s  (eventos con perfil previo: n=%d) =====" % (label, base["n"]))
    print("  BASE                       n=%4d  meanR=%+.3f  WR=%4.1f%%"
          % (base["n"], base["meanR"], base["WR"] * 100))
    print("  -- por ZONA de la entrada (vs VA del día previo) --")
    for z in ("discount", "value", "premium"):
        s = _stats(e[e.vp_zone == z].pnl_r)
        if s["n"]:
            print("  %-9s                  n=%4d  meanR=%+.3f  WR=%4.1f%%  (Δ %+0.3f)"
                  % (z, s["n"], s["meanR"], s["WR"] * 100, s["meanR"] - base["meanR"]))
    # tesis reversión-a-value condicionada a dirección
    d = e.direction.astype(int)
    rev_al = e[((d == 1) & (e.vp_zone == "discount")) | ((d == -1) & (e.vp_zone == "premium"))]
    rev_ag = e[((d == 1) & (e.vp_zone == "premium")) | ((d == -1) & (e.vp_zone == "discount"))]
    print("  -- tesis Market-Profile (reversión a value, condicionada a dirección) --")
    for name, sub in (("rev-ALIGNED (long@disc/short@prem)", rev_al),
                      ("rev-AGAINST (long@prem/short@disc)", rev_ag)):
        s = _stats(sub.pnl_r)
        if s["n"]:
            print("  %-36s n=%4d  meanR=%+.3f  WR=%4.1f%%  (Δ %+0.3f)"
                  % (name, s["n"], s["meanR"], s["WR"] * 100, s["meanR"] - base["meanR"]))
    # cercanía al POC (cuartil más cercano vs más lejano)
    if e.poc_dist.notna().sum() > 20:
        near = e[e.poc_dist <= e.poc_dist.quantile(0.25)]
        far = e[e.poc_dist >= e.poc_dist.quantile(0.75)]
        sn, sf = _stats(near.pnl_r), _stats(far.pnl_r)
        print("  -- cercanía al POC del día previo --")
        print("  cerca del POC (q25)        n=%4d  meanR=%+.3f  WR=%4.1f%%" % (sn["n"], sn["meanR"], sn["WR"] * 100))
        print("  lejos del POC (q75)        n=%4d  meanR=%+.3f  WR=%4.1f%%" % (sf["n"], sf["meanR"], sf["WR"] * 100))
    return base


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--cube", required=True)
    p.add_argument("--klines", required=True)
    p.add_argument("--label", default="?")
    p.add_argument("--n-bins", type=int, default=50)
    p.add_argument("--va-pct", type=float, default=0.70)
    a = p.parse_args(argv)
    e = tag_events(a.cube, a.klines, n_bins=a.n_bins, va_pct=a.va_pct)
    report(e, a.label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
