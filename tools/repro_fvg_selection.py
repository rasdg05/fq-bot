# -*- coding: utf-8 -*-
"""
================================================================================
  REPRO FVG SELECTION - diagnostico de "el FVG me lo dio muy abajo"
  by RasDG_Sol + Claude

  Corre CONTRA DATOS REALES de OKX (necesita red; usar en el entorno del bot,
  no en sesiones con egress bloqueado). Reproduce el panorama de FVGs en un
  momento dado y muestra:
    - todos los FVG abiertos detectados (bounds, ts, % relleno, distancia)
    - las zonas candidatas que arma battle_planner en la direccion pedida
    - cual gana por FRESCURA (ts reciente = ultimo displacement) vs cual ganaba
      por CERCANIA (mayor reach ~ menor distancia), que era el bug.

  Asi se valida sobre velas reales que el FVG correcto estaba mas arriba y que
  el fix de seleccion (FQ_ZONE_REACH_BIAS / frescura) lo elige.

  Uso:
    python tools/repro_fvg_selection.py                       # ahora, short
    python tools/repro_fvg_selection.py --at "2026-06-04 14:50" --dir short
    python tools/repro_fvg_selection.py --tf 5m --symbol SOL-USDT-SWAP

  --at se interpreta en hora CDMX (UTC-6). La vela "actual" es la cerrada en/antes
  de ese instante (mismo criterio que el radar: no usar la vela en formacion).
================================================================================
"""
import argparse
import sys
from datetime import datetime, timezone, timedelta

CDMX_TZ = timezone(timedelta(hours=-6))


def _parse_at(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=CDMX_TZ)
        except ValueError:
            continue
    raise SystemExit("--at no se pudo parsear: '{}'. Usa 'YYYY-MM-DD HH:MM' (CDMX).".format(s))


def _fetch_df(symbol, tf, at_cdmx):
    import ccxt
    import pandas as pd
    ex = ccxt.okx({"enableRateLimit": True, "timeout": 20000})
    if at_cdmx is None:
        ohlcv = ex.fetch_ohlcv(symbol, tf, limit=200)
    else:
        at_utc = at_cdmx.astimezone(timezone.utc)
        # traer una ventana amplia previa y cortar en 'at'
        since = int((at_utc - timedelta(hours=20)).timestamp() * 1000)
        ohlcv = ex.fetch_ohlcv(symbol, tf, since=since, limit=300)
        cut = int(at_utc.timestamp() * 1000)
        ohlcv = [c for c in ohlcv if c[0] <= cut]
    if not ohlcv:
        raise SystemExit("OKX no devolvio velas (revisa red / simbolo / fecha).")
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    return df


def _fmt_ts(ts):
    try:
        t = datetime.fromtimestamp(float(ts) / 1000.0, tz=timezone.utc).astimezone(CDMX_TZ)
        return t.strftime("%m-%d %H:%M CDMX")
    except Exception:
        return str(ts)


def main():
    ap = argparse.ArgumentParser(description="Diagnostico de seleccion de FVG sobre datos reales OKX")
    ap.add_argument("--symbol", default="SOL-USDT-SWAP")
    ap.add_argument("--tf", default="5m")
    ap.add_argument("--dir", default="short", choices=["short", "long"])
    ap.add_argument("--at", default=None, help="momento en hora CDMX, p.ej. '2026-06-04 14:50'")
    args = ap.parse_args()

    at_cdmx = _parse_at(args.at)
    df = _fetch_df(args.symbol, args.tf, at_cdmx)

    import ict_smc
    import battle_planner as bp

    price = float(df["close"].iloc[-1])
    last_ts = _fmt_ts(df["timestamp"].iloc[-1])
    print("=" * 70)
    print("Simbolo {}  TF {}  dir {}".format(args.symbol, args.tf, args.dir))
    print("Vela cerrada usada: {}  close={:.4f}".format(last_ts, price))
    print("FQ_ZONE_REACH_BIAS={}  FQ_ZONE_FRESH_TIEBREAK={}".format(
        bp.ZONE_REACH_BIAS, bp.ZONE_FRESH_TIEBREAK))
    print("=" * 70)

    fvgs = ict_smc.detect_fvgs(df)
    if not fvgs:
        print("Sin FVG abiertos en el lookback. Nada que diagnosticar.")
        return
    print("\nFVG abiertos detectados (mas reciente al final):")
    for f in fvgs:
        side = "arriba" if f.bottom > price else ("abajo" if f.top < price else "en precio")
        print("  {:8s} bottom={:.4f} top={:.4f}  relleno={:.0%}  ts={}  ({} de precio)".format(
            f.direction, f.bottom, f.top, f.filled_pct, _fmt_ts(f.ts), side))

    zones = bp.extract_candidate_zones(args.dir, price, {"fvgs": fvgs}, atr=price * 0.005)
    fvg_zones = [z for z in zones if z["kind"] == "FVG"]
    if not fvg_zones:
        print("\nNo hay zonas FVG candidatas en la direccion {} (todas del lado equivocado).".format(args.dir))
        return

    nearest = min(fvg_zones, key=lambda z: abs(z["ref"] - price))
    freshest = max(fvg_zones, key=lambda z: z.get("ts", 0.0))
    print("\nZonas FVG candidatas en direccion {}:".format(args.dir))
    for z in fvg_zones:
        tags = []
        if z is nearest:
            tags.append("MAS CERCANA (lo que elegia el bug)")
        if z is freshest:
            tags.append("MAS FRESCA (lo que elige el fix)")
        print("  {} ${:.4f}-${:.4f}  ref={:.4f}  ts={}  {}".format(
            z["label"], z["low"], z["high"], z["ref"], _fmt_ts(z["ts"]),
            "<- " + " / ".join(tags) if tags else ""))

    if nearest is freshest:
        print("\n=> La mas fresca coincide con la mas cercana: aqui no habria diferencia.")
    else:
        print("\n=> DIFERENCIA: el bug habria dado la zona en ${:.4f}-${:.4f} (cercana),".format(
            nearest["low"], nearest["high"]))
        print("   el fix prioriza la fresca en ${:.4f}-${:.4f} (ultimo displacement).".format(
            freshest["low"], freshest["high"]))
    print("\nNota: la decision final tambien pondera EV/P(SL) via Monte Carlo; este")
    print("diagnostico aisla el sesgo de cercania vs frescura sobre velas reales.")


if __name__ == "__main__":
    sys.path.insert(0, ".")
    main()
