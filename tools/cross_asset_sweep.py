#!/usr/bin/env python3
"""cross_asset_sweep — la TESIS DEL PREMIO en una tabla.

¿La fuerza del edge de persistencia (F2, order-splitting Bouchaud-Farmer-Lillo)
ESCALA con la institucional-idad del activo? Anclas medidas: BTC (institucional)
F2 apiló; SOL (retail) NO. Aquí lo barremos sobre TODOS los cubos disponibles.

Por símbolo, en la ventana común con CVD (2024-06..2026-06):
  - ac1_flow  = autocorrelación lag-1 del flujo firmado por barra (la HUELLA de
                order-splitting: alto = institucional/persistente, ~0 = retail/aleatorio)
  - edges por tier (base / calidad-KL / cvd / persist / premium) vía measure_tiers
  - uplift F2 = meanR(persist) − meanR(base)   (¿la memoria del flujo paga?)

Ordena por ac1_flow (medido, no asumido) y deja ver si el uplift lo sigue.

  python tools/cross_asset_sweep.py --out scratchpad/cross_asset.json
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "tools")
import measure_tiers as mt  # noqa: E402

# prior cualitativo institucional -> retail (solo para etiqueta; el orden REAL lo da ac1)
SPECTRUM = {
    "BTC": "institucional", "ETH": "institucional/large", "LTC": "institucional/lento",
    "BCH": "institucional/lento", "SOL": "retail-rápido", "XRP": "retail-rápido",
    "DOGE": "retail puro", "TRX": "retail",
}


def global_ac1(cvd_path):
    """Autocorrelación lag-1 del imbalance de flujo firmado por barra 5m.
    imbalance = (buy−sell)/(buy+sell) ∈ [−1,1]; ac1 = <x_t x_{t-1}> / <x^2>."""
    d = pd.read_parquet(cvd_path)
    tot = (d.buy_vol + d.sell_vol).to_numpy(float)
    x = np.where(tot > 0, (d.buy_vol - d.sell_vol).to_numpy(float) / np.maximum(tot, 1e-9), 0.0)
    x = x - x.mean()
    den = float((x * x).sum())
    ac1 = float((x[1:] * x[:-1]).sum() / den) if den > 0 else 0.0
    # también el ac1 del SIGNO (Lillo clásico)
    s = np.sign((d.buy_vol - d.sell_vol).to_numpy(float))
    s = s - s.mean()
    dens = float((s * s).sum())
    ac1_sign = float((s[1:] * s[:-1]).sum() / dens) if dens > 0 else 0.0
    return ac1, ac1_sign


def klines_path(sym):
    for p in ("data/kl_hist_%sUSDT.parquet" % sym,
              "data/mercado/kl_hist_%sUSDT.parquet" % sym,
              "data/okx/kl_hist_%sUSDT.parquet" % sym):   # okx/: nombre heredado
        if os.path.exists(p):
            return p
    return None


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="BTC,ETH,LTC,BCH,SOL,XRP")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)

    rows = []
    for sym in [s.strip() for s in a.symbols.split(",") if s.strip()]:
        cube = "cosecha_cubes/tp_cube_%s_USDT.parquet" % sym
        cvd = "data/cvd_hist_%sUSDT.parquet" % sym
        kl = klines_path(sym)
        if not (os.path.exists(cube) and os.path.exists(cvd) and kl):
            print("  [skip %s] falta cube/cvd/klines (cvd=%s kl=%s)" % (
                sym, os.path.exists(cvd), kl))
            continue
        res = mt.measure(cube, kl, cvd, kl_thr=0.34, imb_min=0.50)
        t = res["tiers"]
        ac1, ac1_sign = global_ac1(cvd)
        base = t["base"]["meanR"]
        per = t.get("persist", {})
        row = {
            "sym": sym, "spectrum": SPECTRUM.get(sym, "?"),
            "ac1_flow": round(ac1, 4), "ac1_sign": round(ac1_sign, 4),
            "n_base": t["base"]["n"], "base_R": round(base, 3),
            "calidad_R": round(t["calidad"]["meanR"], 3) if t["calidad"]["n"] else None,
            "cvd_R": round(t["cvd"]["meanR"], 3) if t.get("cvd", {}).get("n") else None,
            "persist_R": round(per["meanR"], 3) if per.get("n") else None,
            "persist_n": per.get("n"),
            "premium_R": round(t["premium"]["meanR"], 3) if t.get("premium", {}).get("n") else None,
            "f2_uplift": round(per["meanR"] - base, 3) if per.get("n") else None,
        }
        rows.append(row)
        print("  %-4s ac1_flow=%+.3f  base=%+.3f  persist=%s  F2_uplift=%s" % (
            sym, ac1, base,
            ("%+.3f" % row["persist_R"]) if row["persist_R"] is not None else "—",
            ("%+.3f" % row["f2_uplift"]) if row["f2_uplift"] is not None else "—"))

    rows.sort(key=lambda r: -(r["ac1_flow"] if r["ac1_flow"] is not None else -9))
    print("\n=== CROSS-ASSET (orden por ac1_flow = order-splitting medido) ===")
    print("%-4s %-18s %8s %8s %8s %8s %8s" % (
        "sym", "espectro", "ac1_flow", "base_R", "calidad", "persist", "F2_upl"))
    for r in rows:
        print("%-4s %-18s %+8.3f %+8.3f %8s %8s %8s" % (
            r["sym"], r["spectrum"], r["ac1_flow"], r["base_R"],
            ("%+.3f" % r["calidad_R"]) if r["calidad_R"] is not None else "—",
            ("%+.3f" % r["persist_R"]) if r["persist_R"] is not None else "—",
            ("%+.3f" % r["f2_uplift"]) if r["f2_uplift"] is not None else "—"))

    # correlación ac1 vs uplift (la tesis)
    pts = [(r["ac1_flow"], r["f2_uplift"]) for r in rows if r["f2_uplift"] is not None]
    if len(pts) >= 3:
        xs, ys = zip(*pts)
        cc = float(np.corrcoef(xs, ys)[0, 1])
        print("\n  corr(ac1_flow, F2_uplift) = %+.3f  (n=%d símbolos)" % (cc, len(pts)))
        print("  tesis: si >0, la persistencia paga MÁS donde el flujo es más persistente (institucional).")

    if a.out:
        json.dump(rows, open(a.out, "w"), indent=2)
        print("\n  -> %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
