# -*- coding: utf-8 -*-
"""
================================================================================
  carry_paper — colector FORWARD del FUNDING CARRY (0% real, ledger durable)
  by RasDG_Sol + Claude
================================================================================
SEGUNDO MOTOR, market-neutral. El motor del bot es direccional (Sharpe ~0.8); el
carry (short-perp delta-neutral, cobra funding>0) está VALIDADO multi-régimen sobre
el basket CLEAN — positivo los 6 años, incl. el bear 2022 (ver research/carry_regime.md).
Esto lo mide HACIA ADELANTE, 0% real, antes de arriesgar capital.

Espejo de fetch_okx_oi: cada poll baja el funding REALIZADO reciente (OKX history,
vía fetch_okx_funding) de cada símbolo del CLEAN_BASKET y lo appendea-dedupea a un
parquet durable en /data. Con eso calcula el carry del basket (always-on y gate de
7 días) y escribe un snapshot JSON. El span del parquet creciendo ES la prueba forward.

Por qué funding REALIZADO (history) y no el predicho (/funding-rate): el realizado
ya liquidó, viene con su fundingTime de settlement -> dedupe seguro, cero doble-conteo.
Cada poll trae las settlements recientes; el dedupe absorbe el solape.

MEDICIÓN, no ejecución: registra el stream de funding (el cash-flow que DEFINE el
carry; la pata de precio va hedgeada -> neutral). Costes de ejecución (fees 2 patas,
borrow) NO van aquí: restan ~2-4pp al APY al pasar a real. Esto es el techo medible.

Uso:
    python tools/carry_paper.py --once          # una pasada (todo el basket)
    python tools/carry_paper.py --loop          # loop (FQ_CARRY_INTERVAL seg, def 3600)
    python tools/carry_paper.py --report        # imprime el accrual del ledger
Salida: $FQ_CARRY_DIR/carry_funding.parquet + carry_paper_snapshot.json
        (FQ_CARRY_DIR def /data si existe, si no data/okx).

Pure stdlib + pandas/numpy. Hijo NO-crítico del launcher (FQ_CARRY_PAPER=1).
================================================================================
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carry_backtest as cb            # noqa: E402  CLEAN_BASKET (fuente de verdad)
import fetch_binance_vision_funding as bvf  # noqa: E402  metrics() con gate suavizado
import fetch_okx_funding               # noqa: E402  fetch realizado forward

OUT_DIR = os.environ.get("FQ_CARRY_DIR") or ("/data" if os.path.isdir("/data")
             else ("data/okx" if os.path.isdir("data/okx") else "data/mercado"))
LEDGER = os.path.join(OUT_DIR, "carry_funding.parquet")
SNAPSHOT = os.path.join(OUT_DIR, "carry_paper_snapshot.json")
BASKET = cb.CLEAN_BASKET
BACKFILL = int(os.environ.get("FQ_CARRY_BACKFILL", "200"))   # settlements/poll (~66d a 8h)
SMOOTH = bvf.SMOOTH                                          # gate de 7 días (21 intervalos)


def append_dedupe(path, new):
    """Espejo exacto de fetch_okx_oi.append_dedupe, dedupe por (fundingTime, symbol)."""
    if new.empty:
        return None
    if os.path.exists(path):
        try:
            new = pd.concat([pd.read_parquet(path), new], ignore_index=True)
        except Exception as e:
            print("[carry] read %s: %s (reescribo)" % (path, e))
    out = (new.drop_duplicates(["fundingTime", "symbol"])
              .sort_values(["symbol", "fundingTime"]).reset_index(drop=True))
    tmp = path + ".tmp"
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)   # atómico
    return out


def fetch_symbol(inst):
    """DataFrame [fundingTime, symbol, fundingRate] con las settlements recientes."""
    df = fetch_okx_funding.fetch(inst, n=BACKFILL)
    if df.empty:
        return df
    df = df[["fundingTime", "fundingRate"]].copy()
    df["symbol"] = inst
    return df[["fundingTime", "symbol", "fundingRate"]]


def _basket_carry(led):
    """Carry del basket equal-weight desde el ledger. always-on y gate7d.
    OKX paga c/8h -> hours=8. Reusa bvf.metrics (gate suavizado validado)."""
    per_sym, al, ga = {}, [], []
    for inst in BASKET:
        f = led.loc[led.symbol == inst, "fundingRate"].to_numpy(float)
        if len(f) < 5:
            continue
        hours = np.full(len(f), 8.0)
        ma = bvf.metrics(f, hours)
        mg = bvf.metrics(f, hours, selective=True, smooth=SMOOTH)
        per_sym[inst] = {"n": int(len(f)), "apy": ma["apy"], "pct_pos": ma["pct_pos"],
                         "mean_bps": ma["mean_bps"], "cum_funding": float(f.sum())}
        al.append(ma); ga.append(mg)
    if not al:
        return None
    return {
        "n_symbols": len(al),
        "always": {"apy": float(np.mean([m["apy"] for m in al])),
                   "sharpe": float(np.mean([m["sharpe"] for m in al])),
                   "maxdd": float(np.mean([m["maxdd"] for m in al])),
                   "pct_pos": float(np.mean([m["pct_pos"] for m in al]))},
        "gate7d": {"apy": float(np.mean([m["apy"] for m in ga])),
                   "sharpe": float(np.mean([m["sharpe"] for m in ga]))},
        "per_symbol": per_sym,
    }


def _span_days(led):
    if led.empty:
        return 0.0
    return float((led.fundingTime.max() - led.fundingTime.min()) / 8.64e7)


def write_snapshot(led):
    carry = _basket_carry(led)
    if carry is None:
        return None
    snap = {
        "ledger_intervals": int(len(led)),
        "span_days": round(_span_days(led), 1),
        "last_funding_ms": int(led.fundingTime.max()),
        "basket": [s.split("-")[0] for s in BASKET],
        "carry": carry,
    }
    tmp = SNAPSHOT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(snap, f, indent=2, default=float)
    os.replace(tmp, SNAPSHOT)
    return snap


def run_once():
    os.makedirs(OUT_DIR, exist_ok=True)
    frames = []
    for inst in BASKET:
        try:
            df = fetch_symbol(inst)
            if not df.empty:
                frames.append(df)
                print("[carry] %s: +%d settlements" % (inst, len(df)))
        except Exception as e:
            print("[carry] %s ERROR: %s" % (inst, str(e)[:100]))
        time.sleep(0.15)
    if not frames:
        print("[carry] sin data este poll")
        return
    led = append_dedupe(LEDGER, pd.concat(frames, ignore_index=True))
    snap = write_snapshot(led)
    if snap:
        c = snap["carry"]
        print("[carry] ledger %d intervalos (%.0f d, %d símbolos) | basket always APY "
              "%+.1f%% (Sh %.1f) | gate7d %+.1f%% | %s"
              % (snap["ledger_intervals"], snap["span_days"], c["n_symbols"],
                 c["always"]["apy"] * 100, c["always"]["sharpe"],
                 c["gate7d"]["apy"] * 100, LEDGER))


def report():
    if not os.path.exists(LEDGER):
        print("[carry] sin ledger en %s (corré --once primero)" % LEDGER)
        return 1
    led = pd.read_parquet(LEDGER)
    snap = write_snapshot(led)
    if not snap:
        print("[carry] ledger insuficiente")
        return 1
    c = snap["carry"]
    print("=== CARRY PAPER (forward, 0%% real) — %d intervalos, %.0f días ==="
          % (snap["ledger_intervals"], snap["span_days"]))
    print("basket CLEAN %s" % "+".join(snap["basket"]))
    print("  always-on: APY %+.1f%%  Sharpe %.1f  maxDD %.1f%%  %%+ %.0f%%"
          % (c["always"]["apy"] * 100, c["always"]["sharpe"],
             c["always"]["maxdd"] * 100, c["always"]["pct_pos"] * 100))
    print("  gate 7d:   APY %+.1f%%  Sharpe %.1f"
          % (c["gate7d"]["apy"] * 100, c["gate7d"]["sharpe"]))
    print("  por símbolo:")
    for inst, s in sorted(c["per_symbol"].items(), key=lambda kv: kv[1]["apy"], reverse=True):
        print("    %-14s n=%-4d APY %+6.1f%%  %%+ %3.0f%%  funding medio %+.4f bps"
              % (inst, s["n"], s["apy"] * 100, s["pct_pos"] * 100, s["mean_bps"]))
    print("(neto de costes de ejecución resta ~2-4pp; esto es el techo medible)")
    return 0


def main(argv):
    mode = argv[1] if len(argv) > 1 else "--once"
    if mode == "--report":
        return report()
    if mode == "--loop":
        interval = int(os.environ.get("FQ_CARRY_INTERVAL", "3600"))
        print("[carry] loop cada %ds -> %s (basket %s)"
              % (interval, OUT_DIR, "+".join(s.split("-")[0] for s in BASKET)))
        while True:
            run_once()
            time.sleep(interval)
    else:
        run_once()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
