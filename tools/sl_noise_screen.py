#!/usr/bin/env python3
"""sl_noise_screen — ¿el stop del motor vive DENTRO del ruido? Diagnóstico cross-símbolo.

Detonante (2026-06-30): una señal de BCH tocó SL casi al instante. Su stop (0.249%) era más
chico que una vela mediana de 5m (0.265%) → estaba en el ruido. Pregunta de RasDG: ¿los demás
símbolos están igual? Esto lo MIDE, conclusivo (no depende de timing):

  ratio = stop%_mediano / rango_mediano_vela_5m
    ratio < 1  -> el stop típico es más chico que UNA vela: vive en el ruido (MALO)
    ratio > 1  -> el stop típico está fuera del ruido de una sola vela

Hallazgo: en cripto el ratio MEDIANO es ~1.7-2.8 en todos (stop típico OK), pero el **p10**
del stop (~0.24-0.31%) roza el ruido en TODOS -> en baja vol cualquier símbolo emite un stop
de cola dentro del ruido. El fix (piso de stop SL>=k*ATR) protege esa cola global. OJO: ratio>1
NO significa "nunca lo toca el ruido" (una vela p75 o una corrida de 2-3 barras sí) -> es
"¿el stop es patológicamente chico (dentro de UNA vela mediana)?".

  python tools/sl_noise_screen.py --self-test
  python tools/sl_noise_screen.py --cubes 'cosecha_cubes/tp_cube_*_USDT.parquet' --klines-dir data/okx
"""
import argparse
import glob
import os
import re

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bt_data as btd            # noqa: E402
import bt_labeler as lb          # noqa: E402


def bar_noise_pct(kl):
    """Rango mediano de vela (high-low)/close, en %."""
    h = kl["high"].astype(float); l = kl["low"].astype(float); c = kl["close"].astype(float)
    return float(np.median((h - l) / c) * 100)


def stop_stats(cube):
    """Distribución de la distancia del stop (|entry-stop|/entry, %) sobre los fires únicos."""
    f = cube[cube["fired"] == True].drop_duplicates("entry_index")  # noqa: E712
    s = (np.abs(f["entry_price"] - f["stop_price"]) / f["entry_price"] * 100)
    return {"stop_med": float(s.median()), "stop_p10": float(s.quantile(0.10)), "n": int(len(f))}


def right_but_stopped_pct(cube, *, tp="tp4", horizon=288, thr=1.0):
    """% de PÉRDIDAS que llegaron a >=thr·R a favor ANTES DE MORIR.

    "Antes de morir" es literal: exige la excursión EN VIDA. Con la de ventana
    (cubos de esquema 1) este número medía el tape posterior al stop y crecía
    solo con alargar el horizonte — 58% a h96, 83% a h576 sobre las mismas
    señales. Por eso la guarda: sin ella el screen sale limpio y equivocado.
    """
    lb.require_life_scoped(cube, who="right_but_stopped_pct")
    d = cube[(cube["fired"] == True) & (cube["tp"] == tp) & (cube["horizon"] == horizon)]  # noqa: E712
    los = d[d["outcome"] == "loss"]
    return float((los["mfe_r"] >= thr).mean() * 100) if len(los) else float("nan")


def screen_one(cube_path, klines_path=None):
    cube = pd.read_parquet(cube_path)
    sym = re.search(r"tp_cube_(.+)\.parquet", os.path.basename(cube_path)).group(1)
    st = stop_stats(cube)
    noise = float("nan")
    if klines_path and os.path.exists(klines_path):
        kl = pd.read_parquet(klines_path)
        # El ratio compara el stop del CUBO contra la vela de estas klines. Si
        # no son el mismo tape, el cociente no significa nada -- y el directorio
        # por defecto se llamo `data/okx/` mientras guardaba velas de Binance.
        btd.require_same_venue(cube, kl, who="el screen de ruido del stop",
                               nombres=("el cubo", "las velas"))
        noise = bar_noise_pct(kl)
    ratio = st["stop_med"] / noise if noise == noise else float("nan")  # noqa: PLR0124
    return {"sym": sym.replace("_USDT", ""), **st, "vela5m": noise, "ratio": ratio,
            "rbs_pct": right_but_stopped_pct(cube)}


def screen(cube_glob, klines_dir):
    rows = []
    for cp in sorted(glob.glob(cube_glob)):
        sym = re.search(r"tp_cube_(.+)\.parquet", os.path.basename(cp)).group(1)
        kp = os.path.join(klines_dir, "kl_hist_%s.parquet" % sym.replace("_", "")) if klines_dir else None
        rows.append(screen_one(cp, kp))
    df = pd.DataFrame(rows).sort_values("ratio", na_position="last")
    return df


def _self_test():
    import tempfile
    d = tempfile.mkdtemp()
    rng = np.random.default_rng(0)
    n = 500
    ts = 1_700_000_000_000 + np.arange(n) * 300000
    c = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    pd.DataFrame({"ts": ts, "open": c, "high": c * 1.004, "low": c * 0.996, "close": c,
                  "volume": rng.uniform(1e3, 1e4, n)}).to_parquet(os.path.join(d, "kl_hist_TKUSDT.parquet"), index=False)
    ep = 100.0 + rng.normal(0, 1, n)
    cube = pd.DataFrame({
        "entry_index": np.arange(n), "fired": True, "entry_price": ep,
        "stop_price": ep * 1.005, "direction": -1, "tp": "tp4", "horizon": 288,
        "outcome": rng.choice(["win", "loss"], n),
        # esquema 2: la de VIDA es la que juzga el trade; la de ventana la
        # acota por arriba (aqui, el doble) y solo describe el tape.
        "mfe_r": rng.uniform(0, 4, n), "mae_r": -rng.uniform(0, 2, n),
        "mfe_horizon_r": rng.uniform(4, 8, n), "mae_horizon_r": -rng.uniform(2, 6, n)})
    cube.to_parquet(os.path.join(d, "tp_cube_TK_USDT.parquet"), index=False)
    df = screen(os.path.join(d, "tp_cube_*_USDT.parquet"), d)
    assert set(["sym", "stop_med", "stop_p10", "vela5m", "ratio", "rbs_pct", "n"]).issubset(df.columns)
    assert len(df) == 1 and df.iloc[0]["sym"] == "TK"
    assert np.isfinite(df.iloc[0]["ratio"]) and df.iloc[0]["ratio"] > 0
    print("self-test OK:\n" + df.to_string(index=False, float_format=lambda x: "%.3f" % x))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--cubes", default="cosecha_cubes/tp_cube_*_USDT.parquet")
    p.add_argument("--klines-dir", default="data/okx")
    a = p.parse_args(argv)
    if a.self_test:
        return _self_test()
    df = screen(a.cubes, a.klines_dir)
    print("ratio<1 => stop dentro del ruido (MALO). p10 bajo => cola de stops apretados.")
    print(df.to_string(index=False, float_format=lambda x: "%.3f" % x))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
