# -*- coding: utf-8 -*-
"""
Reporte de PROGRESO FQ — para inversionista (interno/confidencial).
Profesional, sin solapes (reusa el sistema de layout de build_deck: draw_lines
con espaciado exacto). Datos REALES del desarrollo (jun-2026): curva de
expectancy en desarrollo, las dos palancas medidas, validacion anti-espejismo,
plan de ingenieria actualizado, diagrama de arquitectura/modelo de pensamiento.

Salida: FQ_Reporte_Progreso.pdf
    python tools/build_progress_report.py [salida.pdf]
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyArrowPatch, Circle, Rectangle, Patch

import build_deck as d   # reusa paleta + helpers profesionales (mismo dir)

BG, INK, INK2, LINE = d.BG, d.INK, d.INK2, d.LINE
GOLD, GOLDL, TEAL, BLUE, VIOLET = d.GOLD, d.GOLDL, d.TEAL, d.BLUE, d.VIOLET
RED, GREEN, TXT, SUB = d.RED, d.GREEN, d.TXT, d.SUB
W, H = d.W, d.H
panel, draw_lines, header, footer, chip, wrap = (
    d.panel, d.draw_lines, d.header, d.footer, d.chip, d.wrap)
TOTAL = 11

# ---------------- datos REALES (jun-2026) ----------------
# expectancy OOS por palanca acumulada (R/trade, neto de costes); §6.10.1 + #33
STAGES = ["Motor\nbase", "+ veto\nsesión", "+ entrada\nmaker", "+ entrada+TP\nmaker"]
SOL_R = [-0.095, 0.012, 0.086, 0.1245]
BTC_R = [-0.068, -0.027, 0.0585, 0.1046]
TARGET_R = 0.133


def chart_ax(fig, x, y, w, h):
    """Inset axes en coordenadas del deck (0..16 x 0..9), estilo dark."""
    ax = fig.add_axes([x / W, y / H, w / W, h / H])
    ax.set_facecolor(INK)
    for s in ax.spines.values():
        s.set_color(LINE)
    ax.tick_params(colors=SUB, labelsize=8.5, length=3)
    ax.grid(True, color=LINE, lw=0.6, alpha=0.5)
    ax.set_axisbelow(True)
    return ax


def metric(ax, x, y, w, big, label, color=GOLD, sub=None):
    """Tarjeta de métrica grande (número + etiqueta), sin solape."""
    h = 1.55
    panel(ax, x, y, w, h, fc=INK, ec=LINE, r=0.06)
    ax.text(x + 0.32, y + h - 0.42, big, fontsize=25, color=color,
            fontweight="bold", va="center")
    ax.text(x + 0.32, y + 0.62, label, fontsize=10, color=TXT, va="center")
    if sub:
        ax.text(x + 0.32, y + 0.30, sub, fontsize=8.2, color=SUB, va="center")


def arrow(ax, x0, y0, x1, y1, color=GOLD, lw=2.0):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>",
                 mutation_scale=14, color=color, lw=lw, shrinkA=2, shrinkB=2))


# ============================================================
# 1 — PORTADA
# ============================================================
def p_cover(pdf):
    fig, ax = d.new_page()
    # textura fractal sutil de fondo (señal financiera)
    t = np.linspace(0, 1, 1400)
    for k, c in enumerate([GOLD, TEAL, BLUE]):
        y = d.fbm(1400, seed=3 + k)
        ax.plot(0.7 + t * 14.6, 6.6 + 0.55 * k + 0.5 * y, color=c, lw=1.0, alpha=0.13)
    ax.add_patch(Rectangle((0, 0), W, 0.16, fc=GOLD, ec="none"))
    ax.text(0.7, 8.05, "FQ QUANTITATIVE SIGNALS ENGINE", fontsize=13,
            color=GOLD, fontweight="bold")
    ax.add_patch(Rectangle((0.7, 7.78), 1.1, 0.035, fc=GOLD, ec="none"))
    ax.text(0.7, 7.25, "Reporte de progreso", fontsize=34, color=TXT,
            fontweight="bold", va="top")
    ax.text(0.7, 6.05, "del sistema y sus actualizaciones", fontsize=34,
            color=GOLDL, fontweight="bold", va="top")
    draw_lines(ax, 0.7, 4.55, [
        "Primera configuración con expectancy out-of-sample POSITIVA,",
        "replicada en los dos símbolos (SOL y BTC). El motor base, un veto",
        "de sesión legible y la ejecución maker — las tres palancas medidas.",
    ], fs=13, ls=1.6, color=SUB)
    # chips de estado
    cx = 0.7
    for txt, col in [("+0.12R OOS · SOL", GREEN), ("+0.10R OOS · BTC", GREEN),
                     ("validado cross-símbolo", TEAL), ("0% real · paper-first", GOLD)]:
        cx += chip(ax, cx, 3.05, txt, color=col, fs=9.5) + 0.25
    ax.text(0.7, 1.45, "Documento interno · confidencial",
            fontsize=10.5, color=SUB)
    ax.text(0.7, 1.05, "15-jun-2026 · validación forward en curso · cosecha a máxima data corrida",
            fontsize=9.5, color=SUB)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 2 — RESUMEN EJECUTIVO
# ============================================================
def p_exec(pdf):
    fig, ax = d.new_page()
    header(ax, "Resumen ejecutivo", "Dónde está el sistema hoy")
    # 4 métricas headline
    metric(ax, 0.7, 5.05, 3.45, "+0.1245R", "expectancy OOS (SOL)",
           color=GREEN, sub="motor+veto+maker · PF 1.21")
    metric(ax, 4.35, 5.05, 3.45, "+0.1046R", "expectancy OOS (BTC)",
           color=GREEN, sub="integrado, replica cross-símbolo")
    metric(ax, 8.0, 5.05, 3.45, "54.3%", "win-rate (SOL, post-veto)",
           color=TEAL, sub="sube desde 50.0% base")
    metric(ax, 11.65, 5.05, 3.65, "≥ 0.133R", "objetivo forward",
           color=GOLD, sub="faltan ~+0.01R (F3)")
    # narrativa
    panel(ax, 0.7, 0.95, 14.6, 3.75, fc=INK, ec=LINE, r=0.05)
    draw_lines(ax, 1.05, 4.35, [
        "FQ es un motor de señales intradía (ICT/SMC + capa cuántica/ML) sobre SOL y BTC perpetuos.",
        "Durante junio se hizo una auditoría honesta: se corrigió un bug de reloj que inflaba los",
        "backtests, y al re-medir, el motor solo NO tenía edge neto out-of-sample (los costes se comían",
        "el bruto). El hallazgo clave: la ventaja no estaba en más señales, sino en DOS palancas legibles.",
    ], fs=11.5, ls=1.62, color=TXT)
    draw_lines(ax, 1.05, 2.30, [
        "1.  VETO DE SESIÓN — no operar la franja 'london open', tóxica y replicada en ambos símbolos.",
        "2.  EJECUCIÓN MAKER — entrar y salir con órdenes límite (2 bps vs 5 bps, sin slippage).",
    ], fs=11.5, ls=1.7, color=GOLDL, weight="bold")
    draw_lines(ax, 1.05, 1.55, [
        "Juntas llevan la expectancy OOS de −0.095R a +0.1245R en SOL y a +0.102R en BTC. Es un TECHO",
        "(asume llenado maker 100%); ahora se valida en paper forward, 0% capital real.",
    ], fs=10.8, ls=1.55, color=SUB)
    footer(ax, 2, TOTAL); pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 3 — ARQUITECTURA / FLUJO (modelo de pensamiento)
# ============================================================
def p_arch(pdf):
    fig, ax = d.new_page()
    header(ax, "Arquitectura", "Cómo fluye una decisión — del mercado al ledger")
    # pipeline horizontal de 5 bloques
    blocks = [
        ("DATOS", "OHLCV 5m/15m\n1h/4h · OKX", BLUE),
        ("MOTOR", "fusion_engine\nfases A–D → P_master", GOLD),
        ("DECISIÓN", "gates: QTE +\nveto sesión F2.6", VIOLET),
        ("EJECUCIÓN", "paper broker +\nshadow maker", TEAL),
        ("FORWARD", "ledger durable\n(validación)", GREEN),
    ]
    x = 0.7; w = 2.62; gap = 0.36; y = 4.85; h = 1.7
    cxs = []
    for i, (t, s, c) in enumerate(blocks):
        panel(ax, x, y, w, h, fc=INK2, ec=c, lw=1.3, r=0.07)
        ax.text(x + w / 2, y + h - 0.42, t, fontsize=12.5, color=c,
                fontweight="bold", ha="center")
        draw_lines(ax, x + 0.28, y + h - 0.85, s.split("\n"), fs=9.3, ls=1.45,
                   color=TXT)
        cxs.append(x + w)
        x += w + gap
    for cx in cxs[:-1]:
        arrow(ax, cx + 0.02, y + h / 2, cx + gap - 0.02, y + h / 2, color=SUB, lw=1.6)
    # principio rector debajo
    panel(ax, 0.7, 2.9, 14.6, 1.6, fc=INK, ec=GOLD, r=0.05)
    ax.text(1.05, 4.2, "PRINCIPIO RECTOR", fontsize=10, color=GOLD, fontweight="bold")
    draw_lines(ax, 1.05, 3.85, [
        "El veto vive en la CAPA DE DECISIÓN (junto a los gates), nunca dentro del motor matemático.",
        "Mismo predicado en research, en el medidor offline y en vivo → cero divergencia backtest/live.",
        "El motor (P_master) queda INTACTO: las palancas son legibles, auditables y reversibles por env.",
    ], fs=10.5, ls=1.5, color=TXT)
    # nota de separación de datos
    panel(ax, 0.7, 1.0, 14.6, 1.7, fc=INK, ec=LINE, r=0.05)
    ax.text(1.05, 2.4, "SEPARACIÓN DE DATOS, NO DE CÓDIGO", fontsize=10,
            color=TEAL, fontweight="bold")
    draw_lines(ax, 1.05, 2.05, [
        "El mismo código corre en SOL y BTC; solo cambia la ruta del artefacto (índice/escala por símbolo).",
        "Cada lección aprendida se convierte en un TEST de invariante (p.ej. la guarda anti-reloj que",
        "rompe el CI si un módulo del motor vuelve a leer el reloj de pared — el bug que se cazó en junio).",
    ], fs=10.5, ls=1.5, color=SUB)
    footer(ax, 3, TOTAL); pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 4 — MÉTODO (cómo decidimos qué es real)
# ============================================================
def p_method(pdf):
    fig, ax = d.new_page()
    header(ax, "Método", "El estándar anti-espejismo: cómo decidimos qué es real")
    # 3 puertas en columna
    gates = [
        ("1 · OUT-OF-SAMPLE", GOLD,
         ["Todo se mide fuera de muestra (walk-forward",
          "con purga + embargo). El in-sample no decide.",
          "Costes reales (fees+slippage+funding) en R."]),
        ("2 · REPLICACIÓN EN DATOS FRESCOS", TEAL,
         ["Un corte solo se explota si REPITE en una",
          "segunda muestra (otro símbolo u otro período).",
          "El veto london: lift ~+0.08R en 2 muestras."]),
        ("3 · SOBREVIVIR FORWARD", GREEN,
         ["La vara final es el paper forward (0% real).",
          "Nada de capital ni escalar riesgo sin forward",
          "validado. El +0.12R es TECHO hasta el fill real."]),
    ]
    y = 4.55; h = 2.3; w = 4.62; x = 0.7
    for t, c, lines in gates:
        panel(ax, x, y, w, h, fc=INK2, ec=c, lw=1.3, r=0.07)
        ax.text(x + 0.3, y + h - 0.45, t, fontsize=11.5, color=c, fontweight="bold")
        ax.plot([x + 0.3, x + w - 0.3], [y + h - 0.7, y + h - 0.7], color=LINE, lw=1)
        draw_lines(ax, x + 0.3, y + h - 0.95, lines, fs=10, ls=1.5, color=TXT)
        x += w + 0.37
    # franja de guardas codificadas
    panel(ax, 0.7, 1.0, 14.6, 3.0, fc=INK, ec=LINE, r=0.05)
    ax.text(1.05, 3.65, "GUARDAS QUE CODIFICAN LECCIONES (no se confía en la memoria humana)",
            fontsize=10.5, color=GOLD, fontweight="bold")
    rows = [
        ("Guarda anti-reloj", "el CI falla si un módulo del motor lee datetime.now() — el bug de junio, atrapado para siempre."),
        ("Puertas de leakage", "placebo debe colapsar a breakeven; causal no debe necesitar el oráculo. Si no, REVISAR."),
        ("Regrade offline", "medir cualquier veto sobre eventos persistidos en segundos, sin re-correr 4h de backtest."),
        ("Paper durable", "el track forward se sella en un ledger con cadena SHA-256 que sobrevive reinicios."),
    ]
    yy = 3.2
    for name, desc in rows:
        ax.text(1.05, yy, "▸ " + name, fontsize=10.3, color=TEAL, fontweight="bold")
        for j, ln in enumerate(wrap(desc, 92)):
            ax.text(4.15, yy - j * d.lh(10, 1.3), ln, fontsize=10, color=SUB, va="baseline")
        yy -= 0.62
    footer(ax, 4, TOTAL); pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 5 — CURVA DE EXPECTANCY EN DESARROLLO  (la pieza central)
# ============================================================
def p_expectancy(pdf):
    fig, ax = d.new_page()
    header(ax, "Resultado", "Curva de expectancy en desarrollo (OOS, neto de costes)")
    cax = chart_ax(fig, 0.95, 1.15, 9.3, 5.5)
    xs = np.arange(len(STAGES))
    bw = 0.38
    cax.axhline(0, color=SUB, lw=1.0)
    cax.axhline(TARGET_R, color=GOLD, lw=1.4, ls="--")
    cax.text(-0.42, TARGET_R + 0.004, "objetivo 0.133R",
             color=GOLD, fontsize=9, ha="left", va="bottom")
    b1 = cax.bar(xs - bw / 2, SOL_R, bw, label="SOL/USDT",
                 color=[RED if v < 0 else TEAL for v in SOL_R], edgecolor="none")
    b2 = cax.bar(xs + bw / 2, BTC_R, bw, label="BTC/USDT",
                 color=[RED if v < 0 else BLUE for v in BTC_R], edgecolor="none", alpha=0.92)
    for xi, v in zip(xs, SOL_R):
        cax.text(xi - bw / 2, v + (0.006 if v >= 0 else -0.012), f"{v:+.3f}",
                 ha="center", va="bottom" if v >= 0 else "top", fontsize=8.4, color=TXT)
    for xi, v in zip(xs, BTC_R):
        cax.text(xi + bw / 2, v + (0.006 if v >= 0 else -0.012), f"{v:+.3f}",
                 ha="center", va="bottom" if v >= 0 else "top", fontsize=8.4, color=SUB)
    cax.set_xticks(xs)
    cax.set_xticklabels(STAGES, fontsize=8.8, color=TXT)
    cax.set_ylabel("expectancy_r (R por trade, OOS)", fontsize=9.5, color=SUB)
    cax.set_ylim(-0.13, 0.16)
    cax.legend(handles=[Patch(facecolor=TEAL, label="SOL/USDT"),
                        Patch(facecolor=BLUE, label="BTC/USDT")],
               facecolor=INK2, edgecolor=LINE, labelcolor=TXT, fontsize=9, loc="lower right")
    # lectura a la derecha
    panel(ax, 10.6, 3.5, 4.7, 3.15, fc=INK, ec=GREEN, r=0.06)
    ax.text(10.9, 6.25, "LA LECTURA", fontsize=10.5, color=GREEN, fontweight="bold")
    draw_lines(ax, 10.9, 5.9, [
        "Cada palanca SUMA edge,",
        "y el patrón se REPITE en",
        "ambos símbolos:",
        "",
        "· motor solo: pierde a costes",
        "· + veto: cruza a breakeven",
        "  positivo (y sube el WR)",
        "· + maker: captura el techo",
    ], fs=10.2, ls=1.5, color=TXT)
    panel(ax, 10.6, 1.15, 4.7, 2.05, fc=INK, ec=GOLD, r=0.06)
    ax.text(10.9, 2.82, "EL CANDADO HONESTO", fontsize=10, color=GOLD, fontweight="bold")
    draw_lines(ax, 10.9, 2.48, [
        "El tramo maker asume llenado",
        "100%. La selección adversa se",
        "mide AHORA en paper (shadow",
        "maker). Sin ese fill-rate real,",
        "+0.1245R es techo, no promesa.",
    ], fs=9.8, ls=1.45, color=SUB)
    footer(ax, 5, TOTAL); pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 6 — LAS DOS PALANCAS (matriz maker × veto)
# ============================================================
def p_levers(pdf):
    fig, ax = d.new_page()
    header(ax, "El filo", "Las dos palancas, medidas juntas (matriz maker × veto)")
    # tabla heatmap-ish: filas = ejecución, cols = base / +veto, por símbolo
    rows = ["taker / taker (hoy)", "entrada maker", "entrada + TP maker"]
    sol = [(-0.095, -0.003), (-0.017, 0.070), (0.021, 0.109)]
    btc = [(-0.068, -0.031), (0.019, 0.055), (0.066, 0.102)]

    def tbl(x0, y0, title, data, accent):
        w = 6.9; rh = 0.82; hh = 0.72
        panel(ax, x0, y0 - (rh * 3 + hh), w, rh * 3 + hh, fc=INK, ec=LINE, r=0.05)
        ax.text(x0 + 0.3, y0 - 0.5, title, fontsize=12.5, color=accent, fontweight="bold")
        ax.text(x0 + 3.7, y0 - 0.52, "base", fontsize=9.5, color=SUB, ha="center")
        ax.text(x0 + 5.6, y0 - 0.52, "+ veto london", fontsize=9.5, color=SUB, ha="center")
        for i, (r, (vb, vv)) in enumerate(zip(rows, data)):
            yy = y0 - hh - i * rh
            ax.text(x0 + 0.3, yy - rh / 2, r, fontsize=10, color=TXT, va="center")
            for cx, v in [(x0 + 3.7, vb), (x0 + 5.6, vv)]:
                col = GREEN if v >= 0.05 else (GOLDL if v >= 0 else RED)
                panel(ax, cx - 0.8, yy - rh + 0.18, 1.6, rh - 0.34,
                      fc=INK2, ec=col, r=0.1, lw=1.1)
                ax.text(cx, yy - rh / 2, f"{v:+.3f}", fontsize=10.5, color=col,
                        ha="center", va="center", fontweight="bold")
    tbl(0.7, 6.6, "SOL / USDT", sol, TEAL)
    tbl(8.0, 6.6, "BTC / USDT", btc, BLUE)
    # franja inferior
    panel(ax, 0.7, 0.95, 14.6, 2.15, fc=INK2, ec=GREEN, r=0.05)
    ax.text(1.05, 2.82, "HITO", fontsize=11, color=GREEN, fontweight="bold")
    draw_lines(ax, 1.05, 2.5, [
        "La esquina inferior-derecha de cada tabla — entrada+TP maker, con el veto — es la PRIMERA",
        "configuración con expectancy OOS positiva en AMBOS símbolos (SOL +0.109 · BTC +0.102), y se",
        "replicó cross-símbolo. Ni el TP estático, ni el modelo ML, ni el gate k-NN lo lograron;",
        "las dos palancas legibles sí. (Verde ≥ +0.05R · ámbar breakeven · rojo negativo.)",
    ], fs=10.8, ls=1.5, color=TXT)
    footer(ax, 6, TOTAL); pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 7 — VALIDACIÓN ANTI-ESPEJISMO
# ============================================================
def p_validation(pdf):
    fig, ax = d.new_page()
    header(ax, "Validación", "El veto sobrevive el estándar — réplica en muestra fresca")
    cax = chart_ax(fig, 0.95, 3.25, 8.2, 3.35)
    cats = ["taker\nbase", "taker\n+veto", "maker\nbase", "maker\n+veto"]
    s30 = [-0.095, -0.003, 0.021, 0.109]   # #30/#32 (step2, n=156)
    s31 = [0.018, 0.098, 0.144, 0.224]     # #31 (step3, n=106) muestra fresca
    xs = np.arange(len(cats)); bw = 0.38
    cax.axhline(0, color=SUB, lw=1.0)
    cax.bar(xs - bw / 2, s30, bw, label="muestra A (n=156)", color=TEAL)
    cax.bar(xs + bw / 2, s31, bw, label="muestra B fresca (n=106)", color=VIOLET)
    cax.set_xticks(xs); cax.set_xticklabels(cats, fontsize=8.5, color=TXT)
    cax.set_ylabel("expectancy_r (SOL, OOS)", fontsize=9.5, color=SUB)
    cax.legend(facecolor=INK2, edgecolor=LINE, labelcolor=TXT, fontsize=8.5, loc="upper left")
    panel(ax, 9.5, 4.1, 5.8, 2.5, fc=INK, ec=VIOLET, r=0.06)
    ax.text(9.85, 6.2, "LIFT ESTABLE ~+0.08R", fontsize=11, color=VIOLET, fontweight="bold")
    draw_lines(ax, 9.85, 5.82, [
        "El veto se midió en dos muestras",
        "independientes (distinto step). La",
        "MEJORA que aporta es ~+0.08R en",
        "ambas, tanto en taker como en maker.",
        "El bucket 'london' es tóxico en las",
        "dos → no es azar del período.",
    ], fs=10, ls=1.48, color=TXT)
    # confirmación #33
    panel(ax, 0.7, 0.9, 14.6, 1.5, fc=INK, ec=GREEN, r=0.05)
    ax.text(1.05, 2.12, "CONFIRMACIÓN INTEGRADA (run #33, 13-jun)", fontsize=10.5,
            color=GREEN, fontweight="bold")
    draw_lines(ax, 1.05, 1.78, [
        "Corridas con el veto YA integrado al motor reprodujeron el resultado end-to-end en AMBOS símbolos:",
        "SOL: taker −0.095→+0.012 · maker +0.1245R (WR 50→54%). BTC: taker −0.068→−0.027 · maker +0.1046R.",
        "Pasa la vara de calidad en los dos — primer +0.10R OOS integrado y replicado cross-símbolo.",
    ], fs=10.3, ls=1.42, color=SUB)
    footer(ax, 7, TOTAL); pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 8 — PLAN DE INGENIERÍA (lo construido)
# ============================================================
def p_engineering(pdf):
    fig, ax = d.new_page()
    header(ax, "Ingeniería", "Plan actualizado — lo que se construyó esta etapa")
    items = [
        ("Veto → ORO (paper)", GOLD, "DESPLEGADO",
         ["El veto validado, fusionado al paper ORO con", "env propio: paper vetado, cliente intacto."]),
        ("Cosecha máx. data", VIOLET, "LANZADA",
         ["BTC 7 años + SOL 5 años (histórico OKX) para", "dar señal real al selector de TP/horizonte."]),
        ("Sharding del replay", TEAL, "DESPLEGADO",
         ["Replay paralelo por fecha: ~22h → ~2–3h en", "runner self-hosted, sin el tope de 6h del CI."]),
        ("Kill-switch paper", GREEN, "ARMABLE",
         ["Reconciler con baseline VIVO del propio paper:", "apaga el track si la expectancy sale del IC."]),
        ("Guardas en CI", BLUE, "EN CI",
         ["Anti-reloj + cubo-no-vacío + lockfile: cada", "lección queda como test que rompe el build."]),
        ("Selector TP/H (F3)", GOLDL, "PENDIENTE",
         ["k-NN causal construido; el smoke a poca data", "dio negativo (honesto) → espera la cosecha."]),
    ]
    x0, y0 = 0.7, 5.05; w = 4.62; h = 1.78; gx, gy = 0.37, 0.32
    for i, (t, c, badge, lines) in enumerate(items):
        col = i % 3; row = i // 3
        x = x0 + col * (w + gx); y = y0 - row * (h + gy)
        panel(ax, x, y, w, h, fc=INK, ec=LINE, r=0.06)
        ax.text(x + 0.3, y + h - 0.42, t, fontsize=11.5, color=c, fontweight="bold")
        # badge
        bw2 = 0.13 * len(badge) + 0.4
        panel(ax, x + w - bw2 - 0.25, y + h - 0.62, bw2, 0.42, fc=INK2, ec=c, r=0.18, lw=1)
        ax.text(x + w - bw2 / 2 - 0.25, y + h - 0.41, badge, fontsize=7.2, color=c,
                ha="center", va="center", fontweight="bold")
        draw_lines(ax, x + 0.3, y + h - 0.88, lines, fs=9.4, ls=1.45, color=SUB)
    # criterio de salida
    panel(ax, 0.7, 1.0, 14.6, 1.2, fc=INK2, ec=GOLD, r=0.05)
    draw_lines(ax, 1.05, 1.92, [
        "Principio: prod vivo, cambios reversibles por env y con suite verde. Calidad antes que features —",
        "con un baseline OOS negativo, el sistema no necesita más señales, sino menos mentiras en la medición.",
    ], fs=10.5, ls=1.5, color=TXT)
    footer(ax, 8, TOTAL); pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 9 — PIPELINE DE VALIDACIÓN FORWARD
# ============================================================
def p_pipeline(pdf):
    fig, ax = d.new_page()
    header(ax, "Validación forward", "Cómo se recopila la evidencia — paper primero, 0% real")
    steps = [
        ("SEÑAL", BLUE, "el motor dispara\n(o el gate clasifica)"),
        ("PAPEL", GOLD, "se abre en un broker\nsimulado, 0% capital"),
        ("SHADOW MAKER", TEAL, "¿una límite se habría\nllenado? (fill-rate real)"),
        ("LEDGER DURABLE", VIOLET, "se sella con cadena\nSHA-256 en disco"),
        ("VEREDICTO", GREEN, "≥30–50 fills →\nse decide con datos"),
    ]
    x = 0.7; w = 2.62; gap = 0.36; y = 5.0; h = 1.75
    cxs = []
    for t, c, s in steps:
        panel(ax, x, y, w, h, fc=INK2, ec=c, lw=1.3, r=0.07)
        ax.text(x + w / 2, y + h - 0.4, t, fontsize=11, color=c, fontweight="bold", ha="center")
        draw_lines(ax, x + 0.26, y + h - 0.82, s.split("\n"), fs=9.2, ls=1.45, color=TXT)
        cxs.append(x + w); x += w + gap
    for cx in cxs[:-1]:
        arrow(ax, cx + 0.02, y + h / 2, cx + gap - 0.02, y + h / 2, color=SUB, lw=1.6)
    panel(ax, 0.7, 2.55, 14.6, 1.95, fc=INK, ec=LINE, r=0.05)
    ax.text(1.05, 4.15, "POR QUÉ IMPORTA", fontsize=10.5, color=GOLD, fontweight="bold")
    draw_lines(ax, 1.05, 3.78, [
        "El backtest dice que el techo es +0.12R asumiendo que las órdenes límite se llenan siempre. En la",
        "realidad, una límite NO se llena en los trades que se escapan (que tienden a ganar) y sí en los que",
        "te atraviesan. El 'shadow maker' mide ese fill-rate REAL en vivo, sin arriesgar un dólar. Esa cifra,",
        "sobre 30–50 operaciones, es la que confirma (o mata) la espada — y se consulta con /paper.",
    ], fs=10.5, ls=1.5, color=TXT)
    panel(ax, 0.7, 1.0, 14.6, 1.35, fc=INK, ec=RED, r=0.05)
    ax.text(1.05, 2.05, "REGLA INNEGOCIABLE", fontsize=10, color=RED, fontweight="bold")
    draw_lines(ax, 1.05, 1.7, [
        "Nada de capital real ni escalar riesgo sin forward validado. Toda señal de paper se etiqueta",
        "explícitamente '0% real'. El gate de retrieval k-NN sigue en revisión y NO sostiene la espada.",
    ], fs=10.3, ls=1.5, color=SUB)
    footer(ax, 9, TOTAL); pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 10 — ROADMAP
# ============================================================
def p_roadmap(pdf):
    fig, ax = d.new_page()
    header(ax, "Roadmap", "El camino a ≥0.133R forward-validado")
    lanes = [
        ("AHORA", GREEN, [
            "Veto fusionado al track ORO en paper (0% real) — recolectando forward.",
            "Edge cross-símbolo ya confirmado integrado: SOL +0.1245R · BTC +0.1046R (run #33).",
        ]),
        ("SIGUIENTE", GOLD, [
            "Cosecha a máxima data lanzada (BTC 7a / SOL 5a) → señal real para el",
            "SELECTOR de TP/horizonte (F3): dejar correr ganadores hacia el MFE observado.",
        ]),
        ("META", VIOLET, [
            "F3, si replica a escala, es el camino legítimo de +0.12R a ≥0.133R sin degradar.",
            "Capital real solo tras fill-rate real + 40–50 trades forward dentro del IC.",
        ]),
    ]
    y = 6.4; h = 1.3
    for t, c, lines in lanes:
        panel(ax, 0.7, y - h, 14.6, h, fc=INK, ec=c, r=0.05)
        ax.add_patch(Circle((1.25, y - h / 2), 0.16, fc=c, ec="none"))
        ax.text(1.95, y - 0.42, t, fontsize=12, color=c, fontweight="bold")
        for j, ln in enumerate(lines):
            ax.text(1.95, y - 0.78 - j * d.lh(10.5, 1.4), ln, fontsize=10.5, color=TXT, va="top")
        y -= h + 0.25
    panel(ax, 0.7, 0.95, 14.6, 0.9, fc=INK2, ec=TEAL, r=0.05)
    ax.text(W / 2, 1.4, "El producto operable que los datos respaldan HOY es el motor base + palancas "
            "legibles — medible, comunicable y honesto.",
            fontsize=10.8, color=TXT, ha="center", va="center", style="italic")
    footer(ax, 10, TOTAL); pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 11 — RIESGO / HONESTIDAD  (cierre para inversionista)
# ============================================================
def p_risk(pdf):
    fig, ax = d.new_page()
    header(ax, "Honestidad", "Lo que todavía NO es, dicho con claridad")
    caveats = [
        ("Es un TECHO, no un realizado", "El +0.12R asume llenado maker 100%. La selección adversa se mide ahora; sin ese fill-rate, no es promesa."),
        ("Muestra acotada", "El veto se validó en 2 muestras y una confirmación integrada; el forward (semanas) es la prueba definitiva."),
        ("El gate k-NN sigue en revisión", "La capa de retrieval no pasa leakage; la espada NO depende de ella, sino del motor base + palancas."),
        ("0% capital real", "Hoy todo es paper. No hay dinero en juego ni se escalará riesgo sin forward validado y orden explícita."),
    ]
    y = 6.5; h = 0.95
    for t, desc in caveats:
        panel(ax, 0.7, y - h, 14.6, h, fc=INK, ec=LINE, r=0.05)
        ax.add_patch(Rectangle((0.7, y - h), 0.08, h, fc=GOLD, ec="none"))
        ax.text(1.1, y - 0.36, t, fontsize=11.5, color=GOLDL, fontweight="bold")
        for j, ln in enumerate(wrap(desc, 112)):
            ax.text(1.1, y - 0.66 - j * d.lh(10, 1.3), ln, fontsize=10, color=SUB, va="top")
        y -= h + 0.18
    panel(ax, 0.7, 1.0, 14.6, 0.95, fc=INK2, ec=GREEN, r=0.05)
    ax.text(W / 2, 1.47, "La disciplina ES la ventaja: medir sin mentiras, replicar antes de creer, "
            "y no arriesgar capital hasta que el forward lo confirme.",
            fontsize=10.8, color=TXT, ha="center", va="center", style="italic")
    footer(ax, 11, TOTAL); pdf.savefig(fig, facecolor=BG); plt.close(fig)


def main(out):
    with PdfPages(out) as pdf:
        for p in (p_cover, p_exec, p_arch, p_method, p_expectancy, p_levers,
                  p_validation, p_engineering, p_pipeline, p_roadmap, p_risk):
            p(pdf)
        info = pdf.infodict()
        info["Title"] = "FQ — Reporte de Progreso (interno)"
        info["Author"] = "FQ Quantitative Signals Engine"
    print("PDF escrito:", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "FQ_Reporte_Progreso.pdf")
