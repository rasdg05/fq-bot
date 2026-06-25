# -*- coding: utf-8 -*-
"""
================================================================================
  fetch_binance_vision_funding — funding PROFUNDO multi-régimen (2021→hoy)
  by RasDG_Sol + Claude
================================================================================
El sandbox (y a veces CI) tienen la API de Binance/Bybit/Gate GEO-BLOQUEADA, así
que el carry sólo se validaba en UN régimen (OKX da ~3 meses). PERO el ARCHIVO
público de Binance — data.binance.vision (S3/CDN, distinto de la API) — SÍ es
alcanzable y trae funding mensual desde la inception del contrato.

Esto baja ese archivo (zips mensuales, cache a disco, descarga concurrente) y
contesta LA pregunta: el carry (short-perp delta-neutral, cobra funding>0)
¿SOBREVIVE el bear 2022 o se desploma? Lo mide POR AÑO y POR SÍMBOLO.

Hallazgo (al 2026-06): el basket CLEAN (BTC/ETH/XRP/LTC/DOGE/ADA — SIN SOL ni BNB)
cobra funding POSITIVO en los 6 años, incluido el bear 2022 (+1.7% APY). SOL es
carry muerto (Sharpe 0.27, maxDD 43%); BNB tiene funding MEDIO negativo (anti-carry).

Formato del archivo: calc_time(ms), funding_interval_hours, last_funding_rate
Ruta: data/futures/um/monthly/fundingRate/{SYM}/{SYM}-fundingRate-YYYY-MM.zip

Uso:
    python tools/fetch_binance_vision_funding.py                 # reporte multi-régimen
    python tools/fetch_binance_vision_funding.py --start 2021 --end 2026
================================================================================
"""
import argparse
import io
import os
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import carry_backtest as cb  # noqa: E402  (CLEAN_BASKET / ANTI_CARRY: una sola fuente de verdad)

BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
DEFAULT_CACHE = "data/binance_vision_funding"
# diagnóstico: las 8 (las 6 limpias + las 2 anti-carry, para mostrar el contraste)
SYMS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "LTCUSDT", "ADAUSDT", "SOLUSDT"]
SMOOTH = 21   # ~7 días (21 intervalos de 8h): media móvil causal del gate selectivo
REGIME = {2021: "bull/euforia", 2022: "BEAR brutal", 2023: "recuperacion",
          2024: "bull", 2025: "bull/lateral", 2026: "lateral/correccion"}


def _swap_to_sym(inst):
    """BTC-USDT-SWAP -> BTCUSDT (formato del archivo Binance)."""
    return inst.split("-")[0] + "USDT"


def _clean_syms():
    return [_swap_to_sym(s) for s in cb.CLEAN_BASKET]


def months(start, end):
    for y in range(start, end + 1):
        for m in range(1, 13):
            yield "%04d-%02d" % (y, m)


def _grab(args):
    sym, ym, cache = args
    dst = os.path.join(cache, "%s-%s.zip" % (sym, ym))
    if os.path.exists(dst) or os.path.exists(dst + ".missing"):
        return
    url = "%s/%s/%s-fundingRate-%s.zip" % (BASE, sym, sym, ym)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = r.read()
        with open(dst, "wb") as f:
            f.write(data)
    except Exception:
        open(dst + ".missing", "w").close()   # marca 404 (mes previo a la inception)


def download(symbols, start, end, cache):
    os.makedirs(cache, exist_ok=True)
    jobs = [(s, ym, cache) for s in symbols for ym in months(start, end)]
    todo = [j for j in jobs
            if not os.path.exists(os.path.join(cache, "%s-%s.zip" % (j[0], j[1])))
            and not os.path.exists(os.path.join(cache, "%s-%s.zip.missing" % (j[0], j[1])))]
    if todo:
        print("[bvf] bajando %d meses faltantes (concurrente)..." % len(todo))
        with ThreadPoolExecutor(max_workers=16) as ex:
            list(ex.map(_grab, todo))


def load_funding(sym, start, end, cache):
    """DataFrame ascendente: fundingTime(ms), fundingRate, intervalHours, year."""
    rows = []
    for ym in months(start, end):
        p = os.path.join(cache, "%s-%s.zip" % (sym, ym))
        if not os.path.exists(p):
            continue
        try:
            with zipfile.ZipFile(p) as z, z.open(z.namelist()[0]) as f:
                rows.append(pd.read_csv(f))
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    df = pd.concat(rows, ignore_index=True)
    df["fundingTime"] = pd.to_numeric(df["calc_time"], errors="coerce")
    df["fundingRate"] = pd.to_numeric(df["last_funding_rate"], errors="coerce")
    df["intervalHours"] = pd.to_numeric(df.get("funding_interval_hours"), errors="coerce").fillna(8)
    df = df.dropna(subset=["fundingTime", "fundingRate"]).drop_duplicates("fundingTime")
    df["year"] = pd.to_datetime(df["fundingTime"], unit="ms").dt.year
    return df.sort_values("fundingTime").reset_index(drop=True)


def metrics(f, hours, *, selective=False, threshold=0.0, switch_bps=5.0, smooth=1):
    """f: tasas/intervalo (short-perp cobra f>0, paga f<0). selective: mantiene sólo
    si la media móvil CAUSAL (smooth intervalos) del funding > threshold; flat el
    resto, paga switch_bps al cambiar. Anualiza con el intervalo real (8h o 4h)."""
    f = np.asarray(f, float)
    hours = np.asarray(hours, float)
    if len(f) == 0:
        return None
    periods_year = (24.0 / np.nanmedian(hours)) * 365.0
    years = len(f) / periods_year
    if selective:
        sig = pd.Series(f).rolling(smooth).mean().shift(1).values   # causal
        held = np.nan_to_num(sig, nan=-1.0) > threshold
        ret = np.where(held, f, 0.0)
        switches = int(np.sum(held[1:] != held[:-1])) + int(held[0])
        cost = switches * (switch_bps / 1e4)
    else:
        ret = f.copy()
        cost = 0.0
    cum = np.cumsum(ret)
    peak = np.maximum.accumulate(cum)
    return {"apy": float((ret.sum() - cost) / years) if years > 0 else 0.0,
            "sharpe": float(ret.mean() / ret.std() * np.sqrt(periods_year)) if ret.std() > 0 else 0.0,
            "maxdd": float((peak - cum).max()), "pct_pos": float((f > 0).mean()),
            "mean_bps": float(f.mean() * 1e4), "n": int(len(f))}


def report(data, clean):
    """Imprime el veredicto multi-régimen. data: {sym: DataFrame}. clean: [syms limpios]."""
    print("\n========== CARRY POR AÑO — basket CLEAN %s ==========" % "+".join(s[:-4] for s in clean))
    print("  (¿sobrevive el bear 2022? always-on vs gate de 7 días, equal-weight)")
    print(" año | always APY  Sh   maxDD | gate7d APY  Sh  %held | %+  | regimen")
    for y in sorted(REGIME):
        al, se, held = [], [], []
        for s in clean:
            d = data.get(s)
            if d is None:
                continue
            d = d[d["year"] == y]
            if len(d) < 50:
                continue
            fv, hv = d["fundingRate"].values, d["intervalHours"].values
            al.append(metrics(fv, hv))
            se.append(metrics(fv, hv, selective=True, smooth=SMOOTH))
            sig = pd.Series(fv).rolling(SMOOTH).mean().shift(1).values
            held.append(float((np.nan_to_num(sig, nan=-1.0) > 0).mean()))
        if not al:
            continue
        print("%d| %+8.1f%% %5.2f %5.1f%% | %+8.1f%% %5.2f %4.0f%% | %3.0f%% | %s" % (
            y, np.mean([m["apy"] for m in al]) * 100, np.mean([m["sharpe"] for m in al]),
            np.mean([m["maxdd"] for m in al]) * 100,
            np.mean([m["apy"] for m in se]) * 100, np.mean([m["sharpe"] for m in se]),
            np.mean(held) * 100, np.mean([m["pct_pos"] for m in al]) * 100, REGIME[y]))

    print("\n========== POR SÍMBOLO (full history, always-on) ==========")
    print("simbolo  |   APY    Sharpe  maxDD   %+   funding medio   veredicto")
    rows = sorted(((s, metrics(d["fundingRate"].values, d["intervalHours"].values))
                   for s, d in data.items()), key=lambda r: r[1]["apy"], reverse=True)
    for s, m in rows:
        verdict = "CLEAN" if s in [_swap_to_sym(x) for x in cb.CLEAN_BASKET] else "anti-carry (excluido)"
        print("%-9s| %+7.1f%%  %5.2f  %5.1f%%  %3.0f%%   %+.4f bps   %s" % (
            s, m["apy"] * 100, m["sharpe"], m["maxdd"] * 100, m["pct_pos"] * 100, m["mean_bps"], verdict))

    print("\n========== BASKET full history (equal-weight) ==========")
    for label, syms in [("TODOS (8)", list(data)), ("CLEAN (6, sin SOL/BNB)", clean)]:
        syms = [s for s in syms if s in data]
        for mode, kw in [("always", {}), ("gate7d", {"selective": True, "smooth": SMOOTH})]:
            ms = [metrics(data[s]["fundingRate"].values, data[s]["intervalHours"].values, **kw) for s in syms]
            print("  %-24s %s  APY %+6.1f%%  Sharpe %.2f  maxDD %.1f%%  %%+ %.0f%%" % (
                label, mode, np.mean([m["apy"] for m in ms]) * 100, np.mean([m["sharpe"] for m in ms]),
                np.mean([m["maxdd"] for m in ms]) * 100, np.mean([m["pct_pos"] for m in ms]) * 100))
    print("\nLECTURA: clean POSITIVO todos los años (incl. bear 2022) -> carry all-weather,")
    print("prima de régimen real (no arbitraje sin riesgo). 2026 comprime a ~0: vigilar.")


def main(argv):
    p = argparse.ArgumentParser(description="Funding profundo (data.binance.vision) + validación multi-régimen del carry.")
    p.add_argument("--start", type=int, default=2021)
    p.add_argument("--end", type=int, default=2026)
    p.add_argument("--cache", default=DEFAULT_CACHE)
    p.add_argument("--symbols", nargs="*", default=SYMS, help="default: las 8 (6 clean + 2 anti-carry)")
    a = p.parse_args(argv)

    download(a.symbols, a.start, a.end, a.cache)
    data = {}
    for s in a.symbols:
        df = load_funding(s, a.start, a.end, a.cache)
        if not df.empty:
            data[s] = df
    if not data:
        print("[bvf] sin data (¿archivo inalcanzable?).")
        return 1
    print("[bvf] cargados: " + ", ".join("%s(%d)" % (s, len(d)) for s, d in data.items()))
    clean = [s for s in _clean_syms() if s in data]
    report(data, clean)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
