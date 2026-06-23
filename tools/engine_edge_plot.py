# -*- coding: utf-8 -*-
"""engine_edge_plot.py - Donde vive el edge del motor real: expectancy OOS (neto
maker) por killzone. Excluir las rojas = el gate de selectividad P2."""
import pandas as pd, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = pd.concat([pd.read_parquet(f"cosecha_cubes/tp_cube_{s}_USDT.parquet").assign(symbol=s)
                for s in ["SOL", "BTC"]])
f = df[(df.fired == True) & df.pnl_r.notna()].copy()
f.entry_ts = pd.to_datetime(f.entry_ts)
risk = (f.entry_price - f.stop_price).abs()
f["net"] = f.pnl_r - (0.0004 * f.entry_price / risk.replace(0, np.nan)).clip(0, 2)
sp = f.groupby("symbol").entry_ts.transform(lambda x: x.quantile(0.7))
oos = f[f.entry_ts >= sp]
g = oos.groupby("field_killzone").net.agg(["mean", "count"])
g = g[g["count"] >= 80].sort_values("mean")
colors = ["#b2182b" if m < 0 else "#4d9221" for m in g["mean"]]
fig, ax = plt.subplots(figsize=(10, 5.6))
ax.barh(range(len(g)), g["mean"], color=colors)
ax.axvline(0, color="k", lw=1)
ax.set_yticks(range(len(g)))
ax.set_yticklabels([f"{k}  (n={int(c)})" for k, c in zip(g.index, g["count"])], fontsize=8)
for i, m in enumerate(g["mean"]):
    ax.text(m + (0.012 if m >= 0 else -0.012), i, f"{m:+.2f}R", va="center",
            ha="left" if m >= 0 else "right", fontsize=8, fontweight="bold")
ax.set_xlabel("Expectancy OOS por trade (R, neto maker)")
ax.set_title("Motor REAL: el edge vive en sesiones especificas (killzones)\n"
             "verde = operar / rojo = excluir (el gate de selectividad P2)")
fig.tight_layout()
fig.savefig("engine_killzone.png", dpi=120)
print("PLOT -> engine_killzone.png")
