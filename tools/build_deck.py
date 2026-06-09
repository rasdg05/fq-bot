# -*- coding: utf-8 -*-
"""
Deck interno FQ v2 — profesional, concreto, sin solapes.
Sistema de layout con líneas pre-medidas (draw_lines) para que NADA se encime.
Salida: FQ_Sistema_Cuantitativo.pdf
"""
import textwrap
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Rectangle, RegularPolygon, Polygon
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap

# ---------------- paleta premium ----------------
BG    = "#0a0f1c"
INK   = "#0f1729"
INK2  = "#13203a"
LINE  = "#243353"
GOLD  = "#e6b84f"
GOLDL = "#f3d792"
TEAL  = "#37d3c0"
BLUE  = "#6aa6ff"
VIOLET= "#a98bff"
RED   = "#ff6b6b"
GREEN = "#54d49a"
TXT   = "#eef2fb"
SUB   = "#9aa7c2"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": TXT,
    "figure.dpi": 150,
})

W, H = 16.0, 9.0
# 1 unidad-y = 60 pt -> altura de línea en unidades = fs*ls/60
def lh(fs, ls=1.45):
    return fs * ls / 60.0


def new_page():
    fig = plt.figure(figsize=(13.333, 7.5))
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    return fig, ax


def panel(ax, x, y, w, h, fc=INK, ec=LINE, lw=1.1, r=0.05, alpha=1.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle=f"round,pad=0.0,rounding_size={r}",
                 fc=fc, ec=ec, lw=lw, alpha=alpha))


def draw_lines(ax, x, y_top, lines, fs=11, ls=1.5, color=TXT, weight=None):
    """Dibuja líneas con espaciado exacto (va=top). Devuelve la y inferior."""
    step = lh(fs, ls)
    for i, ln in enumerate(lines):
        ax.text(x, y_top - i * step, ln, fontsize=fs, color=color,
                va="top", ha="left", fontweight=weight)
    return y_top - len(lines) * step


def wrap(text, width):
    return textwrap.wrap(text, width)


def header(ax, kick, title, sub=None, tcolor=TXT):
    ax.text(0.7, 8.45, kick.upper(), fontsize=10, color=GOLD, fontweight="bold")
    ax.add_patch(Rectangle((0.7, 8.30), 0.9, 0.03, fc=GOLD, ec="none"))
    ax.text(0.7, 7.95, title, fontsize=23, color=tcolor, fontweight="bold", va="top")
    y = 7.0
    if sub:
        for i, ln in enumerate(wrap(sub, 96)):
            ax.text(0.7, 7.15 - i * lh(12.5, 1.3), ln, fontsize=12.5, color=SUB, va="top")
        y = 7.15 - len(wrap(sub, 96)) * lh(12.5, 1.3) - 0.15
    return y


def footer(ax, n, total=13):
    ax.plot([0.7, W - 0.7], [0.5, 0.5], color=LINE, lw=1)
    ax.text(0.7, 0.24, "FQ Quantitative Signals Engine · Documento interno — confidencial",
            fontsize=7.5, color=SUB)
    ax.text(W - 0.7, 0.24, f"{n:02d} / {total}", fontsize=7.5, color=SUB, ha="right")


def chip(ax, x, y, text, color=GOLD, fs=9):
    w = 0.14 * len(text) + 0.5
    panel(ax, x, y, w, 0.5, fc=INK2, ec=color, r=0.25, lw=1.1)
    ax.text(x + w / 2, y + 0.25, text, fontsize=fs, color=color, ha="center", va="center")
    return w


def grad_line(ax, t, y, c0, c1, lw=2.0, alpha=1.0):
    pts = np.array([t, y]).T.reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    lc = LineCollection(segs, linewidth=lw, alpha=alpha)
    lc.set_array(np.linspace(0, 1, len(segs)))
    lc.set_cmap(LinearSegmentedColormap.from_list("g", [c0, c1]))
    ax.add_collection(lc)


def fbm(n, Hurst=0.62, seed=7):
    rng = np.random.default_rng(seed)
    f = np.fft.rfftfreq(n); f[0] = f[1]
    spec = (f ** (-(Hurst + 0.5))) * (rng.normal(size=f.size) + 1j * rng.normal(size=f.size))
    x = np.fft.irfft(spec, n)
    x = (x - x.mean()) / (x.std() + 1e-9)
    return np.cumsum(x) / np.sqrt(n) * 6.0


# ============================================================
# 1 — PORTADA
# ============================================================
def p_cover(pdf):
    fig, ax = new_page()
    t = np.linspace(0, 1, 1200)
    for k, (s, a, off, c) in enumerate([(3, .09, .22, TEAL), (11, .11, .44, GOLD),
                                        (21, .09, .68, BLUE), (5, .07, .85, VIOLET)]):
        y = fbm(1200, .62, s); y = (y - y.min()) / (y.max() - y.min())
        ax.plot(0.7 + t * 14.6, 9 * off + a * 9 * (y - .5), color=c, lw=1.0, alpha=0.16)
    ax.add_patch(Circle((13.2, 6.6), 3.4, fc=GOLD, ec="none", alpha=0.045))

    ax.text(0.7, 8.0, "FQ QUANTITATIVE SIGNALS ENGINE", fontsize=13, color=GOLD, fontweight="bold")
    ax.add_patch(Rectangle((0.7, 7.78), 1.1, 0.035, fc=GOLD, ec="none"))
    ax.text(0.7, 7.2, "Señales intradía validadas", fontsize=33, color=TXT, fontweight="bold", va="top")
    ax.text(0.7, 6.05, "out-of-sample", fontsize=33, color=GOLDL, fontweight="bold", va="top")
    draw_lines(ax, 0.72, 5.05, [
        "Motor de decisión multi-capa para perpetuos de BTC y SOL: estructura ICT/SMC,",
        "cuantificación de líneas temporales y convicción adaptativa — sin emitir una señal",
        "que no sobreviva a una validación con costes reales y pruebas de fuga.",
    ], fs=12.5, ls=1.55, color=SUB)

    cx = 0.7
    for c in ["Walk-forward OOS", "Costes reales", "Retrieval por analogía", "CI semanal BTC+SOL"]:
        cx += chip(ax, cx, 3.1, c, GOLDL) + 0.3
    ax.text(0.7, 1.5, "Documento interno · confidencial · para colaboradores", fontsize=10.5, color=SUB)
    ax.text(0.7, 1.05, "v2 · 2026 · arquitectura construida y en validación continua", fontsize=9.5, color=SUB)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 2 — QUÉ ES FQ
# ============================================================
def p_what(pdf):
    fig, ax = new_page()
    header(ax, "Qué es FQ", "Un motor de señales, no una colección de indicadores",
           "FQ decide cada operación fusionando ocho capas de análisis y la traduce en un plan "
           "ejecutable (entrada, stop y escalera de objetivos), con probabilidad maestra explícita.")
    cards = [
        ("Qué hace", [
            "Detecta setups intradía en perpetuos",
            "BTC/SOL y emite señal con dirección,",
            "entrada, SL y escalera de TP.",
            "Opera por Telegram (público + VIP)."], TEAL),
        ("Cómo decide", [
            "Fusiona estructura ICT/SMC, campo de",
            "confluencia, ensemble de scoring, régimen,",
            "calidad de volumen, sesgo de sesión,",
            "convicción κ y cuantificación temporal."], GOLD),
        ("Por qué es distinto", [
            "Ninguna señal se publica sin pasar por el",
            "harness de research: replay histórico,",
            "validación walk-forward con costes y",
            "pruebas de fuga. Mide antes de afirmar."], VIOLET),
    ]
    x = 0.7; w = 4.83
    for title, lines, c in cards:
        panel(ax, x, 1.25, w, 5.0, fc=INK, ec=LINE)
        ax.add_patch(Rectangle((x, 6.16), w, 0.09, fc=c, ec="none"))
        ax.text(x + 0.35, 5.78, title, fontsize=13.5, color=c, fontweight="bold")
        draw_lines(ax, x + 0.35, 5.18, lines, fs=11, ls=1.6, color=TXT)
        x += w + 0.25
    footer(ax, 3)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 3 — POSICIONAMIENTO
# ============================================================
def p_position(pdf):
    fig, ax = new_page()
    header(ax, "Posicionamiento", "Metodología de fondo cuantitativo, no de bot retail",
           "Lo que separa a FQ del grueso del mercado no son más indicadores: es el rigor con que "
           "valida. Esa disciplina lo coloca en el tramo superior por método.")
    rows = [
        ("Señal", "Pocos indicadores fijos", "Fusión de 8 capas + probabilidad maestra"),
        ("Backtest", "Curva ajustada al pasado (overfit)", "Walk-forward purgado + embargo, OOS"),
        ("Costes", "Ignorados o idealizados", "Fees + slippage + funding por símbolo"),
        ("TP / SL", "Fijos o arbitrarios", "Frontera TP×horizonte medida con costes"),
        ("Validez", "Sin control de fuga", "Pruebas de fuga (causal vs placebo vs oracle)"),
        ("Incertidumbre", "Siempre opina", "Se abstiene cuando no hay evidencia"),
    ]
    ax.text(0.95, 6.42, "DIMENSIÓN", fontsize=9, color=SUB, fontweight="bold")
    ax.text(4.3, 6.42, "BOT RETAIL TÍPICO", fontsize=9, color=SUB, fontweight="bold")
    ax.text(9.6, 6.42, "FQ", fontsize=9, color=GOLD, fontweight="bold")
    y = 6.12; rh = 0.62
    for dim, retail, fq in rows:
        panel(ax, 0.7, y - rh + 0.1, 14.6, rh - 0.12, fc=INK, ec=LINE)
        ax.text(0.95, y - rh / 2 + 0.04, dim, fontsize=10.3, color=TXT, fontweight="bold", va="center")
        ax.text(4.3, y - rh / 2 + 0.04, retail, fontsize=9.8, color=SUB, va="center")
        ax.add_patch(Circle((9.25, y - rh / 2 + 0.04), 0.07, fc=GOLD, ec="none"))
        ax.text(9.6, y - rh / 2 + 0.04, fq, fontsize=9.8, color=TXT, va="center")
        y -= rh
    panel(ax, 0.7, 1.1, 14.6, 0.92, fc="#101a0f", ec=GREEN, lw=1.2)
    ax.text(0.95, 1.56, "Resultado: arquitectura de grado institucional aplicada a intradía cripto "
            "— el ~4% superior se define por método de validación, no por marketing.",
            fontsize=10.3, color=GREEN, va="center")
    footer(ax, 4)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 4 — ARQUITECTURA DEL MOTOR
# ============================================================
def p_arch(pdf):
    fig, ax = new_page()
    header(ax, "Arquitectura del motor de decisión",
           "Ocho capas → una probabilidad maestra → un plan")
    layers = [
        ("Estructura ICT/SMC", "order blocks, FVG, barridos de liquidez, CHoCH, killzones", TEAL),
        ("Campo y confluencia", "premium/discount, nodos, peso efectivo del contexto", TEAL),
        ("Ensemble de scoring", "volumen · estructura · liquidez · concept-stack · historia", BLUE),
        ("Régimen", "clasifica tendencia vs rango y ajusta el umbral", BLUE),
        ("Calidad de volumen", "veta horas muertas y modula por volumen real", GOLD),
        ("Sesgo de sesión", "London/NY/Asia condicionado al sesgo diario", GOLD),
        ("Convicción adaptativa κ", "aprende del track real del contexto (Thompson)", VIOLET),
        ("Cuantificación temporal", "sincronía y fase entre 5m/15m/1h/4h → τ", VIOLET),
    ]
    y = 6.55; rh = 0.58; x = 0.7; w = 9.3
    for i, (name, desc, c) in enumerate(layers):
        panel(ax, x, y - rh + 0.1, w, rh - 0.12, fc=INK, ec=LINE)
        ax.add_patch(Rectangle((x, y - rh + 0.1), 0.1, rh - 0.12, fc=c, ec="none"))
        ax.text(x + 0.45, y - rh / 2 + 0.05, f"{i+1}", fontsize=11, color=c, fontweight="bold", va="center", ha="center")
        ax.text(x + 0.85, y - rh / 2 + 0.18, name, fontsize=11, color=TXT, fontweight="bold", va="center")
        ax.text(x + 0.85, y - rh / 2 - 0.13, desc, fontsize=8.6, color=SUB, va="center")
        y -= rh

    # rail de salida derecha
    ox = 10.4
    ax.add_patch(FancyArrowPatch((10.05, 3.7), (10.38, 3.7), arrowstyle="-|>",
                 mutation_scale=18, color=GOLD, lw=2))
    panel(ax, ox, 4.55, 4.9, 2.0, fc=INK2, ec=GOLD, lw=1.4)
    ax.text(ox + 0.35, 6.25, "P_master", fontsize=15, color=GOLD, fontweight="bold")
    draw_lines(ax, ox + 0.35, 5.75, [
        "Probabilidad maestra explícita:",
        "el producto calibrado de las 8 capas.",
        "Por debajo del umbral → silencio."], fs=10, ls=1.5, color=TXT)
    panel(ax, ox, 2.3, 4.9, 2.0, fc=INK, ec=TEAL, lw=1.3)
    ax.text(ox + 0.35, 4.0, "Niveles", fontsize=15, color=TEAL, fontweight="bold")
    draw_lines(ax, ox + 0.35, 3.5, [
        "Entrada, stop estructural y escalera",
        "TP1–TP4 (cuatro peldaños reales,",
        "monótonos) lista para ejecutar."], fs=10, ls=1.5, color=TXT)
    panel(ax, ox, 0.95, 4.9, 1.05, fc="#101a0f", ec=GREEN, lw=1.2)
    ax.text(ox + 0.35, 1.47, "Señal publicada a Telegram (público / VIP)",
            fontsize=10, color=GREEN, va="center")
    footer(ax, 5)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 5 — CUANTIFICACIÓN DE LÍNEAS TEMPORALES
# ============================================================
def p_time(pdf):
    fig, ax = new_page()
    header(ax, "Cuantificación de líneas temporales",
           "Medir si los marcos temporales hablan el mismo idioma",
           "El precio vive en varias escalas a la vez. FQ cuantifica la sincronía y la fase entre "
           "5m, 15m, 1h y 4h, y convierte esa coherencia temporal en convicción — o en veto.")
    tfs = [("4h", 0.6, BLUE), ("1h", 1.0, TEAL), ("15m", 1.7, GOLD), ("5m", 2.6, GOLDL)]
    a = fig.add_axes([0.06, 0.16, 0.55, 0.46]); a.set_facecolor(INK)
    t = np.linspace(0, 4 * np.pi, 400)
    for i, (lab, freq, c) in enumerate(tfs):
        y = 3 - i + 0.42 * np.sin(freq * t + i * 0.25)
        a.plot(t, y, color=c, lw=1.9)
        a.text(-0.25, 3 - i, lab, color=c, fontsize=9.5, ha="right", va="center", fontweight="bold")
    a.axvline(t[235], color=TXT, lw=1.1, ls="--", alpha=0.6)
    a.text(t[235], 3.7, "marcos alineados → señal", color=TXT, fontsize=8.2, ha="center")
    a.set_xlim(-0.6, t[-1]); a.set_ylim(-0.4, 4.0); a.axis("off")

    panel(ax, 9.9, 4.35, 5.4, 2.2, fc=INK, ec=VIOLET, lw=1.3)
    ax.text(10.2, 6.25, "sync_score", fontsize=13, color=VIOLET, fontweight="bold")
    draw_lines(ax, 10.2, 5.75, [
        "Coherencia entre escalas en [0,1].",
        "Alto → los tiempos confirman el mismo",
        "movimiento. Bajo → ruido entre marcos:",
        "el motor atenúa o veta la operación."], fs=10, ls=1.5, color=TXT)
    panel(ax, 9.9, 1.7, 5.4, 2.35, fc=INK, ec=GOLD, lw=1.3)
    ax.text(10.2, 3.75, "τ emergente", fontsize=13, color=GOLD, fontweight="bold")
    draw_lines(ax, 10.2, 3.25, [
        "Un tiempo propio del mercado que se",
        "acelera o frena según la actividad real,",
        "no el reloj. Modula la convicción: pondera",
        "más cuando el mercado 'avanza' de verdad."], fs=10, ls=1.5, color=TXT)
    ax.text(0.95, 1.15, "Esto es lo que antes llamábamos informalmente 'líneas de tiempo': "
            "aquí es una magnitud medible que entra al vector de estado.", fontsize=9, color=SUB)
    footer(ax, 6)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 6 — CONVICCIÓN ADAPTATIVA κ
# ============================================================
def p_kappa(pdf):
    fig, ax = new_page()
    header(ax, "Convicción adaptativa (κ)",
           "El motor aprende de sus propios desenlaces",
           "Cada contexto (killzone, régimen, tipo de setup) tiene memoria de cómo le fue. κ sube "
           "la convicción donde el track real es bueno y la baja donde sangra — sin intervención manual.")
    a = fig.add_axes([0.06, 0.16, 0.52, 0.46]); a.set_facecolor(INK)
    rng = np.random.default_rng(1)
    n = 60
    wins = np.cumsum(rng.random(n) > 0.42)
    losses = np.arange(1, n + 1) - wins
    kappa = 0.85 + 0.30 / (1 + np.exp(-(wins - losses) / 4.0))
    a.plot(np.arange(n), kappa, color=GOLD, lw=2.2)
    a.axhline(1.0, color=SUB, lw=1, ls="--", alpha=0.5)
    a.fill_between(np.arange(n), 1.0, kappa, where=kappa >= 1, color=GREEN, alpha=0.12)
    a.fill_between(np.arange(n), 1.0, kappa, where=kappa < 1, color=RED, alpha=0.12)
    a.set_xlim(0, n - 1); a.set_ylim(0.8, 1.2)
    a.set_xlabel("operaciones cerradas del contexto", fontsize=9, color=SUB)
    a.set_ylabel("κ (multiplicador de convicción)", fontsize=9, color=SUB)
    a.tick_params(colors=SUB, labelsize=8)
    for s in a.spines.values(): s.set_color(LINE)

    panel(ax, 9.6, 4.3, 5.7, 2.25, fc=INK, ec=GOLD, lw=1.3)
    ax.text(9.9, 6.25, "Thompson sampling", fontsize=13, color=GOLD, fontweight="bold")
    draw_lines(ax, 9.9, 5.75, [
        "Sobre la memoria de desenlaces por bucket,",
        "κ explora/explota como un bandido bayesiano:",
        "apuesta más donde la evidencia acumulada",
        "respalda, con cota dura (no se desboca)."], fs=10, ls=1.5, color=TXT)
    panel(ax, 9.6, 1.7, 5.7, 2.2, fc=INK2, ec=TEAL, lw=1.2)
    ax.text(9.9, 3.6, "En research: determinista", fontsize=12.5, color=TEAL, fontweight="bold")
    draw_lines(ax, 9.9, 3.1, [
        "Para que el backtest sea reproducible y",
        "atribuible a la estrategia (no al azar del",
        "muestreo), el harness fija κ a su forma",
        "determinista. Honestidad sobre vistosidad."], fs=10, ls=1.5, color=TXT)
    footer(ax, 7)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 7 — HARNESS DE RESEARCH
# ============================================================
def p_harness(pdf):
    fig, ax = new_page()
    header(ax, "Cómo validamos", "Un backtest que un fondo auditaría",
           "El mismo motor de producción se re-corre sobre años de historia. Nada se ajusta al "
           "pasado: se mide fuera de muestra, con costes, y se prueba contra fuga.")
    steps = [
        ("Replay", "el motor recorre la historia\ny dispara como en vivo", TEAL),
        ("Triple-barrera", "etiqueta cada señal:\nTP / SL / tiempo (pesimista)", BLUE),
        ("Walk-forward OOS", "folds purgados + embargo;\nfees, slippage y funding", GOLD),
        ("Modelo + retrieval", "LightGBM global +\nk-NN por analogía", VIOLET),
    ]
    x = 0.7; w = 3.45; gap = 0.32; y = 4.5; hh = 2.0
    for i, (t, d, c) in enumerate(steps):
        panel(ax, x, y, w, hh, fc=INK, ec=c, lw=1.4)
        ax.text(x + w / 2, y + hh - 0.45, t, fontsize=12.5, color=c, fontweight="bold", ha="center")
        draw_lines(ax, x + 0.35, y + hh - 0.95, d.split("\n"), fs=9.6, ls=1.45, color=TXT)
        if i < 3:
            ax.add_patch(FancyArrowPatch((x + w + 0.02, y + hh / 2), (x + w + gap - 0.02, y + hh / 2),
                         arrowstyle="-|>", mutation_scale=15, color=GOLD, lw=2))
        x += w + gap

    panel(ax, 0.7, 1.05, 14.6, 2.95, fc=INK)
    ax.text(0.95, 3.65, "Prueba de fuga — la puerta de entrada a todo", fontsize=12.5, color=GOLD, fontweight="bold")
    draw_lines(ax, 0.95, 3.1, [
        "Se compara el edge en tres modos: CAUSAL (índice estrictamente sin futuro), PLACEBO",
        "(etiquetas barajadas — debe colapsar a cero) y ORACLE (con futuro — cota superior leaky).",
        "Si el edge solo existe con oracle, o sobrevive al placebo, la línea se documenta y se mata.",
        "Es el resultado más valioso posible: nos protege de creernos un backtest que miente.",
    ], fs=10.3, ls=1.55, color=TXT)
    footer(ax, 8)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 8 — RETRIEVAL + CUBO
# ============================================================
def p_retrieval(pdf):
    fig, ax = new_page()
    header(ax, "Retrieval por analogía y la superficie de pagos",
           "Reconocer el estado análogo y leer lo que pagó",
           "Cada estado de mercado se codifica como vector. A escala, FQ recupera sus análogos "
           "históricos y lee su superficie de desenlaces — no predice con una fórmula, mide por analogía.")
    # knn scatter
    a = fig.add_axes([0.05, 0.14, 0.42, 0.48]); a.set_facecolor(INK)
    rng = np.random.default_rng(4)
    cl = rng.normal(0, 1, (420, 2)); cl[:150] += [2.3, 1.5]; cl[150:280] += [-2.1, 1.0]; cl[280:] += [0.2, -2.0]
    q = np.array([2.0, 1.3]); d = np.linalg.norm(cl - q, axis=1); kn = np.argsort(d)[:26]
    a.scatter(cl[:, 0], cl[:, 1], s=12, c=SUB, alpha=0.4, edgecolors="none")
    a.scatter(cl[kn, 0], cl[kn, 1], s=30, c=GOLD, edgecolors=BG, linewidths=0.4)
    a.add_patch(Circle(q, d[kn].max(), fill=False, ec=TEAL, lw=1.3, ls="--"))
    a.scatter([q[0]], [q[1]], s=210, marker="*", c=VIOLET, edgecolors="white", linewidths=0.7, zorder=5)
    a.set_xticks([]); a.set_yticks([]); a.set_title("vecindario de estados análogos", fontsize=9.5, color=SUB, loc="left")
    for s in a.spines.values(): s.set_color(LINE)

    # cube heatmap
    hz = ["8h", "16h", "24h", "48h"]; tps = ["TP4", "TP3", "TP2", "TP1"]
    expR = np.array([[.18, .34, .52, .74], [.22, .41, .58, .69], [.27, .45, .55, .57], [.31, .36, .37, .37]])
    h = fig.add_axes([0.53, 0.17, 0.30, 0.42]); h.set_facecolor(INK)
    cm = LinearSegmentedColormap.from_list("fq", ["#102038", TEAL, GOLD, "#ff944d"])
    h.imshow(expR, cmap=cm, aspect="auto", vmin=.15, vmax=.9)
    h.set_xticks(range(4)); h.set_xticklabels(hz, fontsize=8.5, color=SUB)
    h.set_yticks(range(4)); h.set_yticklabels(tps, fontsize=8.5, color=SUB)
    for i in range(4):
        for j in range(4):
            h.text(j, i, f"{expR[i,j]:.2f}", ha="center", va="center", color="#06101f", fontsize=8, fontweight="bold")
    bi, bj = np.unravel_index(np.argmax(expR), expR.shape)
    h.add_patch(Rectangle((bj - .5, bi - .5), 1, 1, fill=False, ec="white", lw=2))
    h.set_title("expectancy (R) · TP × horizonte", fontsize=9, color=SUB, loc="left")
    for s in h.spines.values(): s.set_color(LINE)

    panel(ax, 13.4, 1.6, 1.9, 5.0, fc=INK2, ec=GOLD, lw=1.2)
    draw_lines(ax, 13.6, 6.3, ["El cubo:", "una señal", "no es un", "número,", "es una", "superficie", "de pagos.",
                               "", "El vecino", "trae la", "suya entera", "→ elegir", "TP y", "horizonte", "óptimos."],
               fs=9.2, ls=1.5, color=TXT)
    footer(ax, 9)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 9 — ROBUSTEZ (LO CONSTRUIDO)
# ============================================================
def p_robust(pdf):
    fig, ax = new_page()
    header(ax, "Robustez — lo que ya está construido",
           "Sistema en producción + laboratorio de validación")
    cards = [
        ("Producto en producción", [
            "Bot de Telegram público + VIP, pagos,",
            "anuncio de desenlaces, contenido público.",
            "Desplegado y operando (Railway)."], TEAL),
        ("Laboratorio de research", [
            "Harness bt_* con ~89 pruebas en verde,",
            "leakage gates, costes por símbolo,",
            "walk-forward purgado y embargado."], GOLD),
        ("Automatización", [
            "CI semanal corre BTC y SOL en paralelo,",
            "cachea datos, publica reportes y abre",
            "incidencias si algo se degrada."], BLUE),
        ("Innovación reciente", [
            "Frontera TP×horizonte, fix de la escalera",
            "TP, blindaje del modelo, e incorporación",
            "del bloque temporal al vector de estado."], VIOLET),
    ]
    x0, y0, w, hh, gx, gy = 0.7, 4.55, 7.15, 1.85, 0.5, 0.35
    for i, (t, lines, c) in enumerate(cards):
        x = x0 + (i % 2) * (w + gx); y = y0 - (i // 2) * (hh + gy)
        panel(ax, x, y, w, hh, fc=INK, ec=c, lw=1.3)
        ax.add_patch(Rectangle((x, y + hh - 0.1), w, 0.1, fc=c, ec="none"))
        ax.text(x + 0.35, y + hh - 0.48, t, fontsize=12, color=c, fontweight="bold")
        draw_lines(ax, x + 0.35, y + hh - 0.88, lines, fs=9.7, ls=1.45, color=TXT)
    # métricas
    mx = 0.7
    for v, l in [("~89", "pruebas verde"), ("2", "símbolos en paralelo"),
                 ("3", "modos anti-fuga"), ("8", "capas de decisión")]:
        panel(ax, mx, 0.95, 3.5, 0.95, fc=INK2, ec=LINE)
        ax.text(mx + 0.3, 1.45, v, fontsize=18, color=GOLD, fontweight="bold", va="center")
        ax.text(mx + 1.45, 1.45, l, fontsize=9.5, color=SUB, va="center")
        mx += 3.65
    footer(ax, 10)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 10 — LAS 5 DIMENSIONES
# ============================================================
def p_five(pdf):
    fig, ax = new_page()
    header(ax, "El espacio de exploración del edge", "Cinco dimensiones, cada una con su prueba")
    labels = ["A · Composición\ndel vector", "B · Superficie\nde pagos (cubo)", "C · Geometría de\nsimilitud",
              "D · No-estacio-\nnariedad", "E · Abstención /\nconfianza"]
    cols = [GOLD, TEAL, VIOLET, GREEN, BLUE]
    pax = fig.add_axes([0.02, 0.10, 0.42, 0.60]); pax.axis("off"); pax.set_xlim(0, 8); pax.set_ylim(0, 8)
    cx, cy, R = 4.0, 4.1, 2.4
    ang = np.linspace(np.pi / 2, np.pi / 2 + 2 * np.pi, 6)[:-1]
    for rr in (0.45, 0.72, 1.0):
        pax.add_patch(RegularPolygon((cx, cy), 5, radius=R * rr, orientation=np.pi / 10, fill=False, ec=LINE, lw=1))
    vals = np.array([0.95, 0.82, 0.66, 0.62, 0.74])
    vp = np.c_[cx + R * vals * np.cos(ang), cy + R * vals * np.sin(ang)]
    pax.add_patch(Polygon(vp, closed=True, fc=GOLD, ec=GOLDL, lw=2, alpha=0.16))
    for a, c, lb, v in zip(ang, cols, labels, vals):
        x, y = cx + R * np.cos(a), cy + R * np.sin(a)
        pax.plot([cx, x], [cy, y], color=LINE, lw=1)
        pax.scatter([cx + R * v * np.cos(a)], [cy + R * v * np.sin(a)], s=55, c=c, edgecolors="white", lw=0.5, zorder=5)
        pax.text(cx + (R + 0.75) * np.cos(a), cy + (R + 0.75) * np.sin(a), lb,
                 fontsize=8.6, color=c, ha="center", va="center", fontweight="bold", linespacing=1.2)
    rows = [
        ("A", "Composición del vector", "¿suman las coordenadas temporales / de campo?", GOLD),
        ("B", "Superficie de pagos", "¿elegir TP×horizonte bate la escalera fija?", TEAL),
        ("C", "Geometría de similitud", "¿ninguna dimensión acapara la similitud?", VIOLET),
        ("D", "No-estacionariedad", "¿régimen vivo > histórico completo?", GREEN),
        ("E", "Abstención / confianza", "¿el edge sube con la densidad del vecindario?", BLUE),
    ]
    x0, y0, rw, rh = 7.5, 6.5, 7.8, 1.0
    for i, (k, name, q, c) in enumerate(rows):
        yy = y0 - i * rh
        panel(ax, x0, yy - rh + 0.15, rw, rh - 0.18, fc=INK, ec=c, lw=1.2)
        ax.add_patch(Circle((x0 + 0.5, yy - rh / 2 + 0.07), 0.27, fc=c, ec="none"))
        ax.text(x0 + 0.5, yy - rh / 2 + 0.07, k, fontsize=11, color="#06101f", ha="center", va="center", fontweight="bold")
        ax.text(x0 + 1.05, yy - rh / 2 + 0.25, name, fontsize=10.6, color=TXT, fontweight="bold", va="center")
        ax.text(x0 + 1.05, yy - rh / 2 - 0.16, q, fontsize=8.8, color=SUB, va="center")
    footer(ax, 11)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 11 — ROADMAP
# ============================================================
def p_roadmap(pdf):
    fig, ax = new_page()
    header(ax, "Frontera de desarrollo", "De diagnóstico validado a asignación de capital")
    phases = [
        ("F0", "Harness + prueba de fuga", "construido · verde", GREEN),
        ("F1", "Retrieval diagnóstico\nBTC + SOL", "en validación", GOLD),
        ("F2", "Gate + sizing", "tras F1 positivo", TEAL),
        ("F3", "Selector TP / horizonte", "usa el cubo", VIOLET),
        ("F4", "Comparativa y capital", "criterio de migración", BLUE),
    ]
    x = 0.7; w = 2.68; gap = 0.3; y = 4.4; hh = 2.0
    for i, (k, t, st, c) in enumerate(phases):
        panel(ax, x, y, w, hh, fc=INK, ec=c, lw=1.3)
        ax.text(x + 0.3, y + hh - 0.5, k, fontsize=17, color=c, fontweight="bold")
        draw_lines(ax, x + 0.3, y + hh - 1.0, t.split("\n"), fs=9.5, ls=1.4, color=TXT)
        ax.text(x + 0.3, y + 0.28, st, fontsize=8.4, color=c)
        if i < 4:
            ax.add_patch(FancyArrowPatch((x + w + 0.02, y + hh / 2), (x + w + gap - 0.02, y + hh / 2),
                         arrowstyle="-|>", mutation_scale=13, color=GOLD, lw=1.7))
        x += w + gap
    panel(ax, 0.7, 1.05, 14.6, 2.95, fc=INK)
    ax.text(0.95, 3.6, "Disciplina de avance", fontsize=12.5, color=GOLD, fontweight="bold")
    draw_lines(ax, 0.95, 3.05, [
        "Cada fase se desbloquea SOLO si la anterior produce edge fuera de muestra, atribuible y",
        "robusto a costes (límite inferior del intervalo de confianza > 0). Ninguna intuición mueve",
        "capital antes de medirse. La rentabilidad no se promete: se compone a medida que el edge",
        "medible se acumula fase a fase. Esa disciplina ES la ventaja sostenible.",
    ], fs=10.3, ls=1.55, color=TXT)
    footer(ax, 12)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# 12 — CIERRE
# ============================================================
def p_close(pdf):
    fig, ax = new_page()
    t = np.linspace(0, 1, 1000)
    for s, a, off, c in [(7, .08, .3, TEAL), (3, .10, .6, GOLD)]:
        y = fbm(1000, .62, s); y = (y - y.min()) / (y.max() - y.min())
        ax.plot(0.7 + t * 14.6, 9 * off + a * 9 * (y - .5), color=c, lw=1.0, alpha=0.14)
    ax.text(0.7, 6.6, "En una frase", fontsize=11, color=GOLD, fontweight="bold")
    draw_lines(ax, 0.7, 6.0, [
        "FQ trata el mercado como un campo de estados:",
        "lo cuantifica en el tiempo, reconoce el estado análogo,",
        "y convierte ese entendimiento en edge medible.",
    ], fs=22, ls=1.5, color=TXT, weight="bold")
    ax.add_patch(Rectangle((0.72, 3.5), 5.0, 0.04, fc=GOLD, ec="none"))
    draw_lines(ax, 0.72, 3.05, [
        "Arquitectura de grado institucional · validación fuera de muestra con costes ·",
        "innovación en retrieval por analogía y cuantificación temporal.",
        "Construido, en validación, y diseñado para componer rentabilidad con disciplina.",
    ], fs=12, ls=1.6, color=SUB)
    ax.text(0.7, 0.9, "FQ Quantitative Signals Engine · interno — confidencial", fontsize=9.5, color=SUB)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


def p_vision(pdf):
    fig, ax = new_page()
    header(ax, "La tesis de investigación", "El mercado como un campo de estados medible")
    draw_lines(ax, 0.72, 6.55, [
        "La mayoría de los sistemas tratan el precio como una serie",
        "y le ajustan reglas. Nosotros lo tratamos como un CAMPO DE",
        "ESTADOS: cada vela es una huella —estructura, volumen,",
        "sincronía entre escalas— que puede cuantificarse y comparar.",
    ], fs=12.5, ls=1.6, color=TXT)
    draw_lines(ax, 0.72, 4.05, [
        "Lo que investigamos: codificar ese estado como vector,",
        "recuperar a gran escala sus análogos históricos —los",
        "fractales que riman en el tiempo— y leer su desenlace real",
        "para decidir con probabilidad y costes explícitos.",
    ], fs=12.5, ls=1.6, color=SUB)
    # visual: campo de estados (embedding + recurrencias)
    a = fig.add_axes([0.63, 0.30, 0.33, 0.44]); a.set_facecolor("none"); a.axis("off")
    rng = np.random.default_rng(11)
    P = rng.normal(0, 1, (240, 2))
    P[:80] += [1.8, 1.4]; P[80:150] += [-1.6, 0.9]; P[150:] += [0.3, -1.7]
    a.scatter(P[:, 0], P[:, 1], s=16, c=SUB, alpha=0.45, edgecolors="none")
    # algunas recurrencias (pares similares distantes)
    for i, j, c in [(5, 200, GOLD), (40, 170, TEAL), (90, 20, VIOLET), (130, 60, BLUE)]:
        a.plot([P[i, 0], P[j, 0]], [P[i, 1], P[j, 1]], color=c, lw=1.2, alpha=0.7)
        a.scatter(P[[i, j], 0], P[[i, j], 1], s=34, c=c, edgecolors="white", lw=0.5, zorder=5)
    a.set_xlim(P[:, 0].min() - .5, P[:, 0].max() + .5)
    a.set_ylim(P[:, 1].min() - .5, P[:, 1].max() + .5)
    ax.text(10.4, 6.5, "Estados análogos a través del tiempo", fontsize=9.5, color=SUB)

    panel(ax, 0.7, 1.05, 14.6, 1.35, fc=INK2, ec=GOLD, lw=1.2)
    ax.text(0.95, 2.0, "La apuesta intelectual", fontsize=11.5, color=GOLD, fontweight="bold")
    draw_lines(ax, 0.95, 1.55, [
        "Cuanto mejor cuantificamos el tiempo complejo del mercado, más nítido se vuelve el edge.",
        "El edge medible, compuesto con disciplina, es la ventaja sostenible.",
    ], fs=10.3, ls=1.5, color=TXT)
    footer(ax, 2)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


def main():
    out = "FQ_Sistema_Cuantitativo.pdf"
    with PdfPages(out) as pdf:
        for fn in (p_cover, p_vision, p_what, p_position, p_arch, p_time, p_kappa,
                   p_harness, p_retrieval, p_robust, p_five, p_roadmap, p_close):
            fn(pdf)
    print("OK ->", out)


if __name__ == "__main__":
    main()
