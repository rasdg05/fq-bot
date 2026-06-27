# -*- coding: utf-8 -*-
"""
build_flow_clock — F3: reloj de VOLUMEN/FLUJO en vez de wall-clock ("emergent time"
hecho rigor). NO tiempo imaginario; es event-time vs physical-time (arXiv:2606.16269) +
volume clocks / VPIN (Easley-Lopez de Prado).

La idea de RasDG: en vez de barras de tiempo fijo (5m), muestrear barras de VOLUMEN
FIRMADO constante — el reloj se ACELERA en los estallidos (donde vive la ventaja) y se
DUERME en el grindeo institucional. Cada barra lleva ~la misma "información" (flujo).

`to_flow_bars(df, n_bars)` parte una ventana de barras 5m [ts, buy_vol, sell_vol] en
n_bars cubetas de |flujo firmado| ACUMULADO ~igual (no de tiempo igual), agregando
buy/sell por cubeta. Puro, causal (solo usa las barras de la ventana). Reusado por
validate_flow_clock para la prueba PAREADA (mismo nº de barras, reloj de flujo vs de pared).
"""
import numpy as np
import pandas as pd


def to_flow_bars(df, n_bars):
    """Re-muestrea [ts, buy_vol, sell_vol] (5m) en n_bars cubetas de |buy-sell| acumulado
    ~igual. Devuelve DataFrame [ts, buy_vol, sell_vol] de n_bars filas, o None si no hay
    suficiente flujo/barras. El ts de cada cubeta = el de su última barra 5m (causal)."""
    d = df.sort_values("ts")
    buy = pd.to_numeric(d["buy_vol"], errors="coerce").to_numpy(float)
    sell = pd.to_numeric(d["sell_vol"], errors="coerce").to_numpy(float)
    ts = d["ts"].to_numpy()
    m = np.isfinite(buy) & np.isfinite(sell)
    buy, sell, ts = buy[m], sell[m], ts[m]
    n = len(buy)
    nb = int(n_bars)
    if n < nb or nb < 2:
        return None
    mag = np.abs(buy - sell)
    total = float(mag.sum())
    if total <= 0:
        return None
    cum = np.cumsum(mag)
    edges = np.linspace(0.0, total, nb + 1)[1:]      # umbrales de volumen acumulado
    rows = []
    start = 0
    for e in edges:
        end = int(np.searchsorted(cum, e, side="left")) + 1
        end = min(max(end, start + 1), n)
        rows.append((ts[end - 1], float(buy[start:end].sum()), float(sell[start:end].sum())))
        start = end
        if start >= n:
            break
    if len(rows) < 2:
        return None
    return pd.DataFrame(rows, columns=["ts", "buy_vol", "sell_vol"])
