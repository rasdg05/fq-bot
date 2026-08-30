#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cube_regrade_excursion — re-etiqueta un cubo de esquema 1 sobre las velas REALES
para sellar la excursión EN VIDA (mfe_r/mae_r acotados a bars_held) más el orden
de barras. CERO replays: la geometría (entry/stop/px_tp*) ya está en el cubo, y
el etiquetado nunca dependió del replay.

POR QUÉ. Los cubos cosechados antes de ago-2026 traen `mfe_r`/`mae_r` medidos
sobre la ventana ENTERA del horizonte (ver bt_labeler.CUBE_SCHEMA). Leerlos como
recorrido del trade acredita movimiento posterior a su muerte.

EL VENUE IMPORTA, Y ES OKX SPOT. Los cubos se cosecharon con
`cosecha_shard --exchange okx` (el default). Verificado: el `entry_price` de las
señales coincide EXACTO con el close de OKX spot y con nada de Binance. Con velas
de otro venue el bar en que salta la barrera se mueve, y con él la vida del trade
— que es justo lo que la excursión en vida recorta. No es "un poco de ruido".
  (Cuidado: `fetch_binance_vision_klines` escribe por defecto en `data/okx/`,
   un nombre heredado que guarda velas de BINANCE. Este tool lee `data/okx_real`.)

VELAS RALAS. `fetch_okx_life_windows` baja solo la ventana que cada señal vivió,
no el histórico continuo (15k peticiones en vez de 74k). Así que el re-etiquetado
recorta por señal y EXIGE contigüidad: una ventana con un hueco se descarta y se
cuenta. Un hueco silencioso adelantaría el toque de barrera.

LA VALIDACIÓN ES PARTE DEL PRODUCTO. Antes de creerse una sola excursión nueva,
el tool reproduce lo que el cubo YA afirmaba (outcome, bars_held, pnl_r) y
reporta la coincidencia. Un cubo que no reproduce su propio pasado no gana
credibilidad por traer una columna más.

Uso:
  python tools/cube_regrade_excursion.py                     # todos los cubos
  python tools/cube_regrade_excursion.py --symbols SOL_USDT --dry-run
Salida: <out-dir>/tp_cube_<sym>.parquet  (esquema 2)
"""
import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bt_data as btd            # noqa: E402
import bt_labeler as lb          # noqa: E402

CUBE_DIR = "cosecha_cubes"
KL_DIR = os.environ.get("FQ_OKX_DIR", "data/okx_real")
HORIZONS = [96, 288, 576]
TARGET_KEYS = ["px_tp1", "px_tp2", "px_tp3", "px_tp4"]
BAR_MS = 300_000
EV_KEYS = ["entry_ts", "entry_price", "stop_price", "direction"] + TARGET_KEYS


def load_life_candles(sym, kl_dir=KL_DIR):
    """kl_life_<SYM>.parquet -> Series de (high, low, close) indexada por ts(ms)."""
    path = os.path.join(kl_dir, "kl_life_%s.parquet" % sym)
    if not os.path.exists(path):
        return None
    kl = pd.read_parquet(path).drop_duplicates("ts").sort_values("ts")
    cols = ["high", "low", "close"]
    if btd.VENUE_COL in kl.columns:
        cols.append(btd.VENUE_COL)
    return kl.set_index(kl["ts"].astype("int64"))[cols]


def regrade(cube, kl):
    """Cubo de esquema 2 sobre las mismas señales.

    Devuelve (df, diagnostico). El diagnostico cuenta por qué se cayó cada señal
    descartada: sin velas suficientes, o con hueco en la ventana.
    """
    ev = cube.drop_duplicates(EV_KEYS)[EV_KEYS].copy()
    vida = (cube.groupby(["entry_ts", "direction"])["bars_held"].max() + 2)
    filas, diag = [], {"sin_velas": 0, "hueco": 0, "ok": 0}
    idx = kl.index.to_numpy()
    pos = pd.Series(np.arange(len(idx)), index=idx)

    for row in ev.to_dict("records"):
        ts = pd.Timestamp(row["entry_ts"])
        ms = int(ts.value // 10**6)
        need = int(vida.get((row["entry_ts"], row["direction"]), 0))
        quiero = np.arange(ms + BAR_MS, ms + (need + 1) * BAR_MS, BAR_MS)
        if len(quiero) == 0:
            diag["sin_velas"] += 1
            continue
        p = pos.reindex(quiero)
        if p.isna().any():                      # ventana incompleta -> fuera
            diag["hueco" if p.notna().any() else "sin_velas"] += 1
            continue
        bars = kl.iloc[p.astype(int).to_numpy()].reset_index(drop=True)
        targets = {k[3:]: float(row[k]) for k in TARGET_KEYS
                   if row.get(k) is not None and not pd.isna(row[k])}
        if not targets:
            diag["sin_velas"] += 1
            continue
        g = lb.label_event_grid(bars, float(row["entry_price"]),
                                float(row["stop_price"]), int(row["direction"]),
                                targets, HORIZONS)
        venue = btd.venue_of(kl)
        for (name, h), cell in g["cells"].items():
            r = dict(row)
            r.update(cell)
            r["tp"] = name
            r["horizon"] = h
            r["mfe_horizon_r"] = g["mfe_horizon_r"][h]
            r["mae_horizon_r"] = g["mae_horizon_r"][h]
            if venue:
                r[btd.VENUE_COL] = venue      # el cubo hereda de que tape salio
            filas.append(r)
        diag["ok"] += 1
    return (pd.DataFrame(filas) if filas else None), diag


def validate(viejo, nuevo):
    """Coincidencia de lo que el cubo YA afirmaba, celda a celda."""
    key = ["entry_ts", "direction", "tp", "horizon"]
    a = viejo.drop_duplicates(key).set_index(key)
    b = nuevo.drop_duplicates(key).set_index(key)
    comun = a.index.intersection(b.index)
    if len(comun) == 0:
        return {"n": 0}
    a, b = a.loc[comun], b.loc[comun]
    pa = a["pnl_r"].astype(float).to_numpy()
    pb = b["pnl_r"].astype(float).to_numpy()
    return {
        "n": len(comun),
        "outcome": float((a["outcome"].to_numpy() == b["outcome"].to_numpy()).mean()),
        "bars_held": float((a["bars_held"].astype(int).to_numpy()
                            == b["bars_held"].astype(int).to_numpy()).mean()),
        "pnl_r": float(np.isclose(pa, pb, atol=1e-6).mean()),
        "pnl_bias": float(np.mean(pb - pa)),
    }


def run_one(path, out_dir, kl_dir=KL_DIR, dry_run=False, min_match=0.98):
    sym = os.path.basename(path).replace("tp_cube_", "").replace(".parquet", "")
    cube = pd.read_parquet(path)
    kl = load_life_candles(sym, kl_dir)
    if kl is None:
        print("  %-10s SIN VELAS (falta %s/kl_life_%s.parquet)" % (sym, kl_dir, sym))
        return None
    nuevo, diag = regrade(cube, kl)
    if nuevo is None:
        print("  %-10s ninguna señal con ventana completa %s" % (sym, diag))
        return None
    v = validate(cube, nuevo)
    ok = v["n"] and min(v["outcome"], v["bars_held"], v["pnl_r"]) >= min_match
    print("  %-10s señales %d/%d (hueco %d)  outcome %.4f  bars_held %.4f  "
          "pnl_r %.4f  sesgo %+.4f  %s"
          % (sym, diag["ok"], diag["ok"] + diag["hueco"] + diag["sin_velas"],
             diag["hueco"], v.get("outcome", 0), v.get("bars_held", 0),
             v.get("pnl_r", 0), v.get("pnl_bias", 0),
             "OK" if ok else "<-- NO REPRODUCE"))
    if not ok:
        return None
    if not dry_run:
        os.makedirs(out_dir, exist_ok=True)
        nuevo.to_parquet(os.path.join(out_dir, "tp_cube_%s.parquet" % sym), index=False)
    return nuevo


def main(argv=None):
    p = argparse.ArgumentParser(description="Re-etiqueta cubos con excursión en vida")
    p.add_argument("--cube-dir", default=CUBE_DIR)
    p.add_argument("--kl-dir", default=KL_DIR)
    p.add_argument("--out-dir", default="cosecha_cubes_v2")
    p.add_argument("--symbols", nargs="*", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--min-match", type=float, default=0.98)
    a = p.parse_args(argv)

    paths = sorted(glob.glob(os.path.join(a.cube_dir, "tp_cube_*.parquet")))
    if a.symbols:
        paths = [q for q in paths
                 if os.path.basename(q).replace("tp_cube_", "").replace(".parquet", "")
                 in a.symbols]
    print("REGRADE DE EXCURSION — %d cubos (velas: %s)" % (len(paths), a.kl_dir))
    print("  coincidencia con lo que el cubo ya afirmaba; <%.2f = no se escribe"
          % a.min_match)
    hechos = 0
    for q in paths:
        if run_one(q, a.out_dir, a.kl_dir, a.dry_run, a.min_match) is not None:
            hechos += 1
    print("\n%d/%d cubos %s" % (hechos, len(paths),
                                "validados" if a.dry_run else "reescritos en " + a.out_dir))
    return 0 if hechos == len(paths) else 1


if __name__ == "__main__":
    sys.exit(main())
