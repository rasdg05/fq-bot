# -*- coding: utf-8 -*-
"""
================================================================================
  magnet_multibt — backtest MULTI-SIMBOLO del motor de imanes (OKX 5m real)
  by RasDG_Sol + Claude
================================================================================
Prueba la tesis liquidez-seeking en varios pares para ver DONDE rinde/paga mejor.
Default = v3 (horas de volumen + bias macro + target macro del dia previo + ENTRAR EN
VALOR sobre VWAP). Incluye chequeo de ROBUSTEZ: expectancy en la 1a mitad (in-sample)
vs 2a mitad (out-of-sample) — si el edge solo vive en una mitad, es regime/overfit.

Uso:
    python tools/magnet_multibt.py --n 12000 --min-rr 2.0 --out research/magnet_multi_v3.md
    python tools/magnet_multibt.py --version v1     # baseline imanes micro
================================================================================
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import fetch_okx
import magnet_backtest as mb

BASKET = [
    "BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "XRP-USDT-SWAP",
    "DOGE-USDT-SWAP", "BNB-USDT-SWAP", "LTC-USDT-SWAP", "ADA-USDT-SWAP",
]


def _load(sym, bar, n, cache_dir):
    path = os.path.join(cache_dir, "%s_%s.parquet" % (sym, bar))
    if os.path.exists(path):
        df = pd.read_parquet(path)
        if len(df) >= n * 0.8:
            return df
    df = fetch_okx.fetch(sym, bar, n)
    if not df.empty:
        os.makedirs(cache_dir, exist_ok=True)
        df.to_parquet(path, index=False)
    return df


def run_basket(symbols, *, bar="5m", n=12000, step=1, min_rr=2.0, cache_dir="data/okx",
               version="v2", require_value=True, atr_mult=1.5):
    kw = dict(step=step, min_rr=min_rr, version=version)
    if version == "v2":
        kw.update(require_value=require_value, atr_mult=atr_mult)
    out = []
    for s in symbols:
        df = _load(s, bar, n, cache_dir)
        if df.empty or len(df) < 2000:
            print("[multi] %s: sin data suficiente, skip" % s)
            continue
        r = mb.run(df, **kw)
        h = len(df) // 2
        r["exp_is"] = mb.run(df.iloc[:h], **kw)["expectancy_r"]      # in-sample (1a mitad)
        r["exp_oos"] = mb.run(df.iloc[h:], **kw)["expectancy_r"]     # out-of-sample (2a)
        days = ((df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]) / 8.64e7
                if "timestamp" in df.columns else len(df) * 5 / 1440.0)
        r.update({"symbol": s, "bars": len(df), "days": days})
        out.append(r)
        robust = "OK " if (r["exp_is"] or -9) > 0 and (r["exp_oos"] or -9) > 0 else "-- "
        print("[multi] %-14s n=%-4d exp=%+.3fR (IS %+.3f / OOS %+.3f) %s DD=%3.0f%%" % (
            s, r["n_trades"], r["expectancy_r"] or 0, r["exp_is"] or 0,
            r["exp_oos"] or 0, robust, r["max_drawdown"] * 100))
    out.sort(key=lambda r: (r["expectancy_r"] if r["expectancy_r"] is not None else -9),
             reverse=True)
    return out


def to_markdown(results, *, bar, n, min_rr, version, require_value):
    tag = "v3 (macro + entrar en valor)" if (version == "v2" and require_value) \
        else ("v2 (macro)" if version == "v2" else "v1 (imanes micro)")
    lines = ["# Backtest multi-simbolo — Motor de Imanes [%s]\n" % tag]
    lines.append("OKX %s, ~%d velas/par, paso 1, min_rr=%.2f, trades NO solapados, "
                 "etiquetado pesimista (empate TP/SL -> SL), costes via bt_engine.\n"
                 % (bar, n, min_rr))
    lines.append("**Robustez:** IS = expectancy 1a mitad (in-sample), OOS = 2a mitad "
                 "(out-of-sample). OK = positivo en AMBAS (el edge persiste, no es una "
                 "racha de un solo regimen). Muestra corta (~6 semanas): tomar como "
                 "senal, no como verdad final.\n")
    lines.append("| Par | dias | trades | WR | exp (R) | IS | OOS | robusto | total (R) | maxDD |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|")
    for r in results:
        robust = "OK" if (r.get("exp_is") or -9) > 0 and (r.get("exp_oos") or -9) > 0 else "—"
        lines.append("| %s | %.0f | %d | %.0f%% | %+.3f | %+.3f | %+.3f | %s | %+.1f | %.0f%% |" % (
            r["symbol"], r["days"], r["n_trades"], (r["win_rate"] or 0) * 100,
            r["expectancy_r"] or 0, r.get("exp_is") or 0, r.get("exp_oos") or 0,
            robust, r["total_r"], r["max_drawdown"] * 100))
    pos = [r for r in results if (r["expectancy_r"] or 0) > 0]
    rob = [r for r in results if (r.get("exp_is") or -9) > 0 and (r.get("exp_oos") or -9) > 0]
    lines.append("\n**Resumen:** %d/%d pares positivos; %d/%d ROBUSTOS (IS y OOS +). "
                 "Mejores: %s.\n" % (len(pos), len(results), len(rob), len(results),
                 ", ".join(r["symbol"].split("-")[0] for r in rob[:4]) or "ninguno"))
    return "\n".join(lines) + "\n"


def main(argv):
    def opt(flag, default, cast=str):
        return cast(argv[argv.index(flag) + 1]) if flag in argv else default
    n = opt("--n", 12000, int)
    min_rr = opt("--min-rr", 2.0, float)
    version = opt("--version", "v2")
    require_value = "--no-value" not in argv
    out = opt("--out", "research/magnet_multi_v3.md")
    bar = opt("--bar", "5m")
    res = run_basket(BASKET, bar=bar, n=n, min_rr=min_rr, version=version,
                     require_value=require_value)
    if not res:
        print("[multi] sin resultados")
        return 1
    md = to_markdown(res, bar=bar, n=n, min_rr=min_rr, version=version,
                     require_value=require_value)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        f.write(md)
    with open(out.replace(".md", ".json"), "w") as f:
        json.dump(res, f, indent=2, default=float)
    print("\n" + md)
    print("[multi] reporte -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
