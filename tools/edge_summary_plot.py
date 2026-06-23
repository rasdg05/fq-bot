# -*- coding: utf-8 -*-
"""edge_summary_plot.py - El resumen visual del sprint: cada lever suma, pero el
stack llega a CERO, no a edge. Valores = expectancy OOS (R/trade) medidos en esta
sesion sobre 8 simbolos OKX 5m (salvo donde se indique). Honesto, no optimista."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

labels = [
    "Momentum naive\n(taker)",
    "Reversion naive\n(taker)",
    "MR + regimen\n(taker)",
    "MR + regimen\n(MAKER)",
    "Confluencia>=3\n(maker)",
]
exp = [-0.406, -0.316, -0.211, +0.010, +0.019]
colors = ["#b2182b" if e < -0.05 else ("#ef8a62" if e < 0 else "#4d9221") for e in exp]

fig, ax = plt.subplots(figsize=(10, 5.2))
bars = ax.barh(range(len(labels)), exp, color=colors)
ax.axvline(0, color="k", lw=1)
ax.set_yticks(range(len(labels))); ax.set_yticklabels(labels, fontsize=9)
ax.invert_yaxis()
for i, e in enumerate(exp):
    ax.text(e + (0.006 if e >= 0 else -0.006), i, f"{e:+.3f}R",
            va="center", ha="left" if e >= 0 else "right", fontsize=9, fontweight="bold")
ax.set_xlabel("Expectancy OOS por trade (R, neto de costos)")
ax.set_title("El edge se construye con LEVERS — pero el stack llega a CERO, no arriba\n"
             "(ejecucion > seleccion > regimen; ninguno solo es edge robusto)", fontsize=11)
ax.set_xlim(-0.46, 0.10)
fig.tight_layout()
fig.savefig("edge_summary.png", dpi=120)
print("PLOT -> edge_summary.png")
