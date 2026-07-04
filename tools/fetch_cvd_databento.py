#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  fetch_cvd_databento — trades de CME (Databento GLBX.MDP3) -> schema CVD del bot
  by RasDG_Sol + Claude
================================================================================
NO reinventa el gate de order-flow: lo ALIMENTA. `validate_cvd_signed_flow.py` ya corre
el DSR sobre el CVD firmado; sólo consume un parquet [ts, buy_vol, sell_vol] por barra 5m
(mismo que produce fetch_cvd para cripto). Este adaptador traduce los trades de CME a ESE
schema -> tu gate probado corre sin tocar una línea, ahora sobre MNQ/MGC.

Databento 'trades' trae por trade: ts_event (ns epoch), size, side. `side` mapea el CME
MDP 3.0 Tag 5797-AggressorSide (verificado): 'B'=buy-aggressor (levantó el offer),
'A'=sell-aggressor (pegó al bid), 'N'=sin agresor. Agregado por barra 5m:
    buy_vol  = Σ size con side == 'B'
    sell_vol = Σ size con side == 'A'
    (los 'N' no entran al delta — no adivinamos el agresor)
-> CVD = cumsum(buy - sell), idéntico a cripto.

⚠️ CORRECTNESS: verifica el encoding de `side` contra una MUESTRA real (imprime unas filas).
Si el CVD sale invertido vs el precio, tienes buy/sell cruzados -> usa --buy A --sell B.
Es el ÚNICO punto que puede invertir el signo; todo lo demás es aritmética.

Pipeline completo:
  1) jala trades de Databento (tu crédito; query exacta en internal/EXPERIMENT_ORDER_FLOW.md)
  2) python tools/fetch_cvd_databento.py --in mnq_trades.parquet --out data/cme/cvd_MNQ.parquet
  3) python tools/validate_cvd_signed_flow.py --cube <cube_MNQ>.parquet --cvd data/cme/cvd_MNQ.parquet

  Self-test: python tools/fetch_cvd_databento.py --self-test
================================================================================
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

BAR_MS = 300_000   # 5m, el bar del gate (fetch_cvd/validate_cvd_signed_flow)


def _to_ms(ts, unit="auto"):
    """Serie de epoch -> ms (int64). Databento ts_event es NANOsegundos. 'auto' detecta por
    magnitud (ns ~1e18, us ~1e15, ms ~1e12 en 2026); explícito ('ns'/'us'/'ms') si prefieres.
    Acepta también datetime64 / strings de fecha (to_df(pretty_ts=True)) -> ns."""
    ts = pd.Series(ts).reset_index(drop=True)
    # datetime64 o strings de fecha -> ns epoch (int64), luego cae en la rama 'ns'/'auto'
    if ts.dtype.kind == "M" or (ts.dtype == object and not pd.api.types.is_numeric_dtype(ts)):
        # utc=True -> tz-aware UTC; tz_localize(None) -> naive UTC; astype int64 -> ns epoch.
        # (Series.view murió en pandas 3.x; esta ruta es estable en 2.x y 3.x.)
        dt = pd.to_datetime(ts, utc=True, errors="coerce").dt.tz_localize(None)
        ts = dt.astype("int64")         # NaT -> iNaT (negativo grande) -> se filtra por ms>0
        unit = "ns" if unit == "auto" else unit
    ts = pd.to_numeric(ts, errors="coerce")
    if unit == "ms":
        return ts.astype("int64")
    if unit == "us":
        return (ts // 1_000).astype("int64")
    if unit == "ns":
        return (ts // 1_000_000).astype("int64")
    # auto: > 1e16 -> ns ; > 1e13 -> us ; si no -> ya es ms
    out = np.where(ts > 1e16, ts // 1_000_000,
                   np.where(ts > 1e13, ts // 1_000, ts))
    return pd.Series(out, index=getattr(ts, "index", None)).astype("int64")


def signed_bars(df, bar_ms=BAR_MS, ts_col="ts_event", size_col="size", side_col="side",
                buy_code="B", sell_code="A", ts_unit="auto", notional=False, price_col="price"):
    """Trades de Databento -> DataFrame [ts, buy_vol, sell_vol] por barra `bar_ms` (ms epoch,
    floor a la barra). PURA: sin red, sin archivo. Robusta a `side` como 'B'/'Bid'/'b' (toma la
    1ª letra en mayúscula), a `ts_event` como columna O como índice (Databento .to_df() suele
    ponerlo de índice) y a ns/us/ms/datetime. Los trades sin agresor ('N') no suman a nada."""
    # ts_event puede venir como columna o como índice (DatetimeIndex de to_df).
    if ts_col in df.columns:
        ts_raw = df[ts_col]
    elif df.index.name == ts_col or df.index.dtype.kind == "M":
        ts_raw = df.index
    else:
        raise KeyError("no encuentro '%s' ni como columna ni como índice" % ts_col)
    # Peso del trade: contratos (size) o notional (size*price). Notional = comparable entre
    # instrumentos (MGC/GC/MNQ) y consistente con el CVD de cripto (que ya era notional).
    size = pd.to_numeric(pd.Series(df[size_col]).reset_index(drop=True),
                         errors="coerce").fillna(0.0).astype(float).to_numpy()
    if notional:
        if price_col not in df.columns:
            raise KeyError("--notional pide la columna de precio '%s' (no está en el export)" % price_col)
        px = pd.to_numeric(pd.Series(df[price_col]).reset_index(drop=True),
                           errors="coerce").fillna(0.0).astype(float).to_numpy()
        weight = size * px
    else:
        weight = size
    # Construir POSICIONAL (.values) para no depender de índices alineados entre columnas.
    d = pd.DataFrame({
        "ms": _to_ms(ts_raw, ts_unit).to_numpy(),
        "w": weight,
        "side": pd.Series(df[side_col]).reset_index(drop=True).astype(str)
                  .str.strip().str.upper().str[:1].to_numpy(),
    })
    d = d[d["ms"] > 0]
    d["ts"] = (d["ms"] // bar_ms) * bar_ms
    d["buy_vol"] = np.where(d["side"] == buy_code, d["w"], 0.0)
    d["sell_vol"] = np.where(d["side"] == sell_code, d["w"], 0.0)
    g = (d.groupby("ts", as_index=False)[["buy_vol", "sell_vol"]].sum()
         .sort_values("ts").reset_index(drop=True))
    return g


def _load(path):
    """Lee el export de Databento: .parquet o .csv (columnas trades: ts_event,size,side)."""
    if path.endswith(".parquet"):
        return pd.read_parquet(path)
    return pd.read_csv(path)


def main(argv=None):
    p = argparse.ArgumentParser(description="Trades CME (Databento) -> parquet CVD del gate.")
    p.add_argument("--in", dest="inp", required=True, help="trades.parquet|csv de Databento")
    p.add_argument("--out", required=True, help="salida [ts,buy_vol,sell_vol] (parquet)")
    p.add_argument("--ts-col", default="ts_event")
    p.add_argument("--size-col", default="size")
    p.add_argument("--side-col", default="side")
    p.add_argument("--buy", default="B", help="código de buy-aggressor (default Databento 'B')")
    p.add_argument("--sell", default="A", help="código de sell-aggressor (default 'A')")
    p.add_argument("--ts-unit", default="auto", choices=["auto", "ns", "us", "ms"])
    p.add_argument("--notional", action="store_true",
                   help="CVD en notional (size*price) en vez de contratos — recomendado en TradFi")
    p.add_argument("--price-col", default="price")
    a = p.parse_args(argv)

    raw = _load(a.inp)
    bars = signed_bars(raw, ts_col=a.ts_col, size_col=a.size_col, side_col=a.side_col,
                       buy_code=a.buy.upper()[:1], sell_code=a.sell.upper()[:1], ts_unit=a.ts_unit,
                       notional=a.notional, price_col=a.price_col)
    if bars.empty:
        print("⚠️  0 barras — revisa columnas/side-encoding del export.", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bars.to_parquet(a.out, index=False)
    tot_b, tot_s = bars.buy_vol.sum(), bars.sell_vol.sum()
    print("✓ %d barras 5m -> %s" % (len(bars), a.out))
    print("  buy_vol=%.0f sell_vol=%.0f  imbalance global=%.3f  (0.5=neutro)"
          % (tot_b, tot_s, tot_b / (tot_b + tot_s) if (tot_b + tot_s) else 0.5))
    print("  OJO: si el CVD sale invertido vs precio, corre con --buy A --sell B.")
    return 0


# ------------------------------------ self-test ------------------------------------
def _self_test():
    # 3 trades en la barra 0, 2 en la barra 1 (5m = 300000 ms). ts en NANOsegundos (Databento).
    # base ALINEADA a la barra de 5m (múltiplo de BAR_MS) para que min0/1/2 caigan en bar0.
    base_ns = 1_699_999_800_000 * 1_000_000            # = 5666666*300000 ms, bar-aligned, en ns
    step_ns = 60 * 1_000_000_000                       # 1 min en ns
    rows = [
        {"ts_event": base_ns + 0 * step_ns, "size": 10, "side": "B"},   # bar0 buy 10
        {"ts_event": base_ns + 1 * step_ns, "size": 4,  "side": "A"},   # bar0 sell 4
        {"ts_event": base_ns + 2 * step_ns, "size": 3,  "side": "N"},   # bar0 sin agresor -> nada
        {"ts_event": base_ns + 6 * step_ns, "size": 7,  "side": "B"},   # bar1 (min6) buy 7
        {"ts_event": base_ns + 7 * step_ns, "size": 2,  "side": "A"},   # bar1 sell 2
    ]
    g = signed_bars(pd.DataFrame(rows))
    assert len(g) == 2, g
    assert g.iloc[0]["buy_vol"] == 10 and g.iloc[0]["sell_vol"] == 4     # 'N' no sumó
    assert g.iloc[1]["buy_vol"] == 7 and g.iloc[1]["sell_vol"] == 2
    # ts floored a la barra de 5m y en MS
    assert g.iloc[0]["ts"] % BAR_MS == 0
    assert g.iloc[1]["ts"] - g.iloc[0]["ts"] == BAR_MS

    # DROP-IN: el output alimenta fetch_cvd.cvd_features SIN cambios -> CVD = cumsum(buy-sell)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import fetch_cvd
    f = fetch_cvd.cvd_features(g, win=24)
    assert abs(f["cvd"] - ((10 - 4) + (7 - 2))) < 1e-9, f     # 6 + 5 = 11
    assert f["imbalance"] > 0.5                                # domina la compra

    # side flexible ('Bid'/'ask') + inversión por flags
    rows2 = [{"ts_event": base_ns, "size": 5, "side": "Bid"},
             {"ts_event": base_ns, "size": 8, "side": "Ask"}]
    g2 = signed_bars(pd.DataFrame(rows2))
    assert g2.iloc[0]["buy_vol"] == 5 and g2.iloc[0]["sell_vol"] == 8
    g2i = signed_bars(pd.DataFrame(rows2), buy_code="A", sell_code="B")  # invertido
    assert g2i.iloc[0]["buy_vol"] == 8 and g2i.iloc[0]["sell_vol"] == 5

    # ts en ms (no ns) también funciona con ts_unit explícito
    g3 = signed_bars(pd.DataFrame([{"ts_event": 1_700_000_000_000, "size": 1, "side": "B"}]),
                     ts_unit="ms")
    assert g3.iloc[0]["ts"] == (1_700_000_000_000 // BAR_MS) * BAR_MS
    print("fetch_cvd_databento self-test OK")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    raise SystemExit(main())
