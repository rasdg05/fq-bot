# -*- coding: utf-8 -*-
"""
Genera el deck interno (PDF 16:9) sobre la frontera de tiempo complejo x
vectorizacion a gran escala (turbovec) y el edge medible. Visuales propios
(fractales de tiempo emergente, recurrencia, cubo, vecindario k-NN, frontera).
Sin red. Salida: FQ_Frontera_TiempoComplejo.pdf
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Rectangle, RegularPolygon
from matplotlib.collections import LineCollection

# ---------------- paleta / tema ----------------
BG    = "#070b16"
PANEL = "#0e1526"
PANEL2= "#121b30"
GOLD  = "#e8c66b"
GOLD2 = "#f6e2a8"
CYAN  = "#45e0d0"
MAG   = "#b483ff"
RED   = "#ff5252"
GREEN = "#5ad19a"
TEXT  = "#e9eef8"
MUTE  = "#8a97b0"
GRID  = "#1f2c49"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "text.color": TEXT,
    "axes.edgecolor": GRID,
    "axes.labelcolor": TEXT,
    "xtick.color": MUTE,
    "ytick.color": MUTE,
    "figure.dpi": 150,
})

W, H = 16.0, 9.0   # lienzo logico 16:9


def new_page():
    fig = plt.figure(figsize=(13.333, 7.5))
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(0, H)
    ax.axis("off")
    return fig, ax


def panel(ax, x, y, w, h, fc=PANEL, ec=GRID, lw=1.2, r=0.06, alpha=1.0):
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0.02,rounding_size={r}",
                       fc=fc, ec=ec, lw=lw, alpha=alpha, mutation_aspect=1)
    ax.add_patch(p)
    return p


def footer(ax, n, total=11):
    ax.plot([0.6, W - 0.6], [0.52, 0.52], color=GRID, lw=1)
    ax.text(0.6, 0.26, "FQ · Documento interno — confidencial · combinar para colaboradores",
            fontsize=7.5, color=MUTE)
    ax.text(W - 0.6, 0.26, f"{n} / {total}", fontsize=7.5, color=MUTE, ha="right")
    ax.text(W/2, 0.26, "Tiempo complejo × vectorización a gran escala",
            fontsize=7.5, color=MUTE, ha="center")


def kicker(ax, x, y, text, color=GOLD):
    ax.text(x, y, text.upper(), fontsize=9.5, color=color, fontweight="bold")


# ---------------- generadores de fractales ----------------
def fbm(n, Hurst=0.62, seed=7):
    """Movimiento browniano fraccional via sintesis espectral (price-like)."""
    rng = np.random.default_rng(seed)
    f = np.fft.rfftfreq(n)
    f[0] = f[1]
    amp = f ** (-(Hurst + 0.5))
    spec = amp * (rng.normal(size=f.size) + 1j * rng.normal(size=f.size))
    x = np.fft.irfft(spec, n)
    x = (x - x.mean()) / (x.std() + 1e-9)
    return np.cumsum(x) / np.sqrt(n) * 6.0 + 100.0


def grad_line(ax, t, y, c0=CYAN, c1=GOLD, lw=1.8, alpha=1.0):
    pts = np.array([t, y]).T.reshape(-1, 1, 2)
    segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
    lc = LineCollection(segs, cmap=None, linewidth=lw, alpha=alpha)
    cols = np.linspace(0, 1, len(segs))
    from matplotlib.colors import LinearSegmentedColormap
    cm = LinearSegmentedColormap.from_list("cg", [c0, c1])
    lc.set_array(cols); lc.set_cmap(cm)
    ax.add_collection(lc)


# ============================================================
# PAGINA 1 — PORTADA
# ============================================================
def page_cover(pdf):
    fig, ax = new_page()
    # fondo fractal tenue
    bgax = fig.add_axes([0.0, 0.0, 1.0, 1.0]); bgax.axis("off")
    bgax.set_xlim(0, 1); bgax.set_ylim(0, 1)
    t = np.linspace(0, 1, 1400)
    for k, (seed, a, off) in enumerate([(3, 0.10, 0.20), (11, 0.13, 0.42),
                                        (21, 0.10, 0.66), (31, 0.08, 0.83)]):
        y = fbm(1400, 0.6, seed)
        y = (y - y.min()) / (y.max() - y.min())
        bgax.plot(t, off + a * (y - 0.5), color=[CYAN, GOLD, MAG, GOLD2][k],
                  lw=1.0, alpha=0.18)
    # halo
    ax.add_patch(Circle((12.6, 6.4), 3.6, fc=GOLD, ec="none", alpha=0.05))
    ax.add_patch(Circle((3.2, 2.4), 2.8, fc=CYAN, ec="none", alpha=0.05))

    ax.text(1.0, 7.7, "FQ — QUANTUM STRUCTURAL ENGINE", fontsize=12, color=GOLD,
            fontweight="bold")
    ax.text(1.0, 6.55, "La frontera del", fontsize=30, color=TEXT, fontweight="light")
    ax.text(1.0, 5.35, "edge medible", fontsize=52, color=GOLD2, fontweight="bold")
    ax.text(1.02, 4.35,
            "Tiempo complejo · vectorización a gran escala · estados cuánticos\n"
            "de la huella energética del precio · excitación de campo",
            fontsize=14, color=MUTE)
    # chips
    chips = ["Fractales de tiempo emergente", "Retrieval k-NN causal",
             "Cubo TP × horizonte", "5 dimensiones de pensamiento"]
    cx = 1.0
    for c in chips:
        w = 0.18 * len(c) + 0.5
        panel(ax, cx, 2.7, w, 0.62, fc=PANEL2, ec=GRID, r=0.3)
        ax.text(cx + w/2, 3.01, c, fontsize=9.5, color=GOLD2, ha="center", va="center")
        cx += w + 0.35
    ax.text(1.0, 1.5, "Documento interno · confidencial · para colaboradores",
            fontsize=10, color=MUTE)
    ax.text(1.0, 1.05, "v1 · 2026 · estado: tesis en validación (edge OOS atribuible)",
            fontsize=9, color=MUTE)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# PAGINA 2 — TESIS / RESUMEN EJECUTIVO
# ============================================================
def page_thesis(pdf):
    fig, ax = new_page()
    kicker(ax, 0.7, 8.4, "Resumen ejecutivo")
    ax.text(0.7, 7.75, "Medir el mercado como un campo, no como una serie",
            fontsize=22, color=TEXT, fontweight="bold")

    panel(ax, 0.7, 3.0, 9.0, 4.4, fc=PANEL)
    body = (
        "Tesis. Cada vela es un ESTADO: una huella energética del precio que el motor\n"
        "ya describe con decenas de magnitudes (convicción, excitación de campo, régimen,\n"
        "tiempo emergente). Codificamos ese estado como un VECTOR y, a escala, recuperamos\n"
        "sus análogos históricos —los fractales que riman en el tiempo— para leer lo que\n"
        "REALMENTE pagaron.\n\n"
        "El salto. No predecimos con una fórmula: medimos por analogía local sobre un índice\n"
        "vectorial masivo (turbovec). El mercado deja de ser una curva y se vuelve un campo\n"
        "de estados cuyo desenlace forward está adjunto. Detectar el evento = reconocer el\n"
        "fractal y leer su superficie de pagos.\n\n"
        "El resultado buscado. Una arquitectura que aproxima estados complejos del tiempo y\n"
        "convierte su entendimiento en edge MEDIBLE — y el edge medible, compuesto, en la\n"
        "frontera de rentabilidad extraordinaria."
    )
    ax.text(0.95, 7.05, body, fontsize=11.3, color=TEXT, va="top", linespacing=1.5)

    # tarjetas derechas
    cards = [
        ("Estado", "Arquitectura construida\ny verde en CI", CYAN),
        ("Validando", "Run real BTC+SOL\n(leakage gate)", GOLD),
        ("Frontera", "Rentabilidad objetivo\ncontingente a edge OOS", MAG),
    ]
    y = 6.7
    for tag, txt, col in cards:
        panel(ax, 10.1, y - 1.15, 5.2, 1.15, fc=PANEL2, ec=col, lw=1.4)
        ax.text(10.4, y - 0.28, tag, fontsize=11, color=col, fontweight="bold")
        ax.text(10.4, y - 0.62, txt, fontsize=9.8, color=TEXT, va="top", linespacing=1.35)
        y -= 1.45
    panel(ax, 0.7, 1.05, 14.6, 1.5, fc="#0c1322", ec=GOLD, lw=1.2)
    ax.text(0.95, 2.15, "Principio rector", fontsize=10.5, color=GOLD, fontweight="bold")
    ax.text(0.95, 1.45,
            "MEDIR, NO ASUMIR. Cada idea entra como dimensión testeable; sobrevive solo si su "
            "edge out-of-sample es atribuible (IC bootstrap > 0). La elegancia es que la "
            "intuición se vuelve número.",
            fontsize=10.2, color=TEXT, va="center", linespacing=1.4)
    footer(ax, 2)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# PAGINA 3 — MODELO DE FUNCIONAMIENTO E INTEGRACION (pipeline)
# ============================================================
def page_pipeline(pdf):
    fig, ax = new_page()
    kicker(ax, 0.7, 8.4, "Modelo de funcionamiento e integración")
    ax.text(0.7, 7.75, "Un replay caro · todo lo demás, medición gratis",
            fontsize=22, color=TEXT, fontweight="bold")

    steps = [
        ("1 · Replay denso", "El motor recorre la historia\nuna vez. ~99% del costo.", CYAN),
        ("2 · Vector de estado", "Cada vela → vector causal\n(convicción·campo·tiempo).", GOLD),
        ("3 · Índice turbovec", "k-NN masivo: los fractales\nanálogos del histórico.", MAG),
        ("4 · Cubo TP×horizonte", "Superficie de desenlaces\npor estado (post-replay).", GOLD2),
        ("5 · Selector / edge", "Lee qué pagó en estados\nsimilares → orden óptima.", GREEN),
    ]
    x = 0.7; w = 2.78; gap = 0.32; y = 4.6; h = 2.0
    centers = []
    for i, (t, d, c) in enumerate(steps):
        panel(ax, x, y, w, h, fc=PANEL2, ec=c, lw=1.5)
        ax.text(x + w/2, y + h - 0.42, t, fontsize=11, color=c, fontweight="bold", ha="center")
        ax.text(x + w/2, y + h/2 - 0.25, d, fontsize=9.2, color=TEXT, ha="center",
                va="center", linespacing=1.4)
        centers.append((x + w, y + h/2))
        if i < len(steps) - 1:
            ar = FancyArrowPatch((x + w + 0.02, y + h/2), (x + w + gap - 0.02, y + h/2),
                                 arrowstyle="-|>", mutation_scale=16, color=GOLD, lw=2)
            ax.add_patch(ar)
        x += w + gap

    # banda inferior: lo que es gratis (post-replay)
    panel(ax, 0.7, 1.05, 14.6, 2.95, fc=PANEL)
    ax.text(0.95, 3.62, "Todo esto cuelga del MISMO replay (re-etiquetar es gratis):",
            fontsize=11, color=GOLD, fontweight="bold")
    free = [
        ("Frontera TP×horizonte", "expectancy/WR por celda, con costes y OOS"),
        ("Grid SL × TP", "ancho de stop óptimo en múltiplos de ATR"),
        ("Gate VIP oro", "decil superior por score del modelo / retrieval"),
        ("Retrieval k-NN", "expectancy por analogía, read-only (no decide aún)"),
    ]
    bx = 0.95
    for t, d in free:
        panel(ax, bx, 1.35, 3.5, 1.75, fc=PANEL2, ec=GRID)
        ax.text(bx + 1.75, 2.7, t, fontsize=10, color=CYAN, fontweight="bold", ha="center")
        ax.text(bx + 1.75, 2.0, d, fontsize=8.6, color=TEXT, ha="center", va="center",
                wrap=True, linespacing=1.35)
        bx += 3.62
    ax.text(8.0, 5.0, "fusion_engine intacto · separación por DATOS, no por código  ·  "
            "BTC y SOL comparten el mismo motor",
            fontsize=9.2, color=MUTE, ha="center")
    footer(ax, 3)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# PAGINA 4 — EL CUBO (superficie de desenlaces)
# ============================================================
def page_cube(pdf):
    fig, ax = new_page()
    kicker(ax, 0.7, 8.4, "El cubo · superficie de desenlaces")
    ax.text(0.7, 7.75, "Una señal no es un número: es una superficie",
            fontsize=22, color=TEXT, fontweight="bold")

    # explicacion izquierda
    panel(ax, 0.7, 1.2, 6.6, 6.05, fc=PANEL)
    txt = (
        "El problema. Etiquetar una señal con un solo win/loss\n"
        "colapsa toda la información de DÓNDE tomar ganancia\n"
        "(TP1…TP4) y CUÁNTO aguantar (el horizonte).\n\n"
        "El cubo. En una sola pasada por las velas futuras,\n"
        "calcula el desenlace de TODAS las combinaciones\n"
        "(TP × horizonte) con un stop común:\n\n"
        "   ·  primer toque de stop vs target (pesimista en empate)\n"
        "   ·  win al RR del TP · loss −1R · timeout mark-to-market\n"
        "   ·  MFE/MAE por horizonte = recorrido típico en R\n\n"
        "Por qué importa. El replay es el costo; re-etiquetar es\n"
        "gratis. Cada estado histórico queda con su superficie de\n"
        "pagos ADJUNTA → es la side-table que el retrieval lee:\n"
        "\"para estados como este, ¿qué (TP, horizonte) pagó?\""
    )
    ax.text(0.95, 7.0, txt, fontsize=10.4, color=TEXT, va="top", linespacing=1.45)

    # heatmap del cubo
    hz = ["8h", "16h", "24h", "48h", "72h"]
    tps = ["TP4 (1.00R)", "TP3 (0.81R)", "TP2 (0.62R)", "TP1 (0.38R)"]
    expR = np.array([
        [0.18, 0.34, 0.52, 0.74, 0.95],   # tp4
        [0.22, 0.41, 0.58, 0.69, 0.72],   # tp3
        [0.27, 0.45, 0.55, 0.57, 0.57],   # tp2
        [0.31, 0.36, 0.37, 0.37, 0.37],   # tp1
    ])
    hax = fig.add_axes([0.52, 0.20, 0.43, 0.52])
    hax.set_facecolor(PANEL)
    from matplotlib.colors import LinearSegmentedColormap
    cm = LinearSegmentedColormap.from_list("fq", ["#11233f", CYAN, GOLD, "#ff8a3d"])
    im = hax.imshow(expR, cmap=cm, aspect="auto", vmin=0.1, vmax=1.0)
    hax.set_xticks(range(len(hz))); hax.set_xticklabels(hz, fontsize=9)
    hax.set_yticks(range(len(tps))); hax.set_yticklabels(tps, fontsize=9)
    for i in range(expR.shape[0]):
        for j in range(expR.shape[1]):
            hax.text(j, i, f"{expR[i,j]:.2f}", ha="center", va="center",
                     color="#06101f", fontsize=8.5, fontweight="bold")
    # celda optima
    bi, bj = np.unravel_index(np.argmax(expR), expR.shape)
    hax.add_patch(Rectangle((bj-0.5, bi-0.5), 1, 1, fill=False, ec="#ffffff", lw=2.4))
    hax.set_title("expectancy (R) por celda  ·  ◻ óptimo del vecindario",
                  fontsize=9.5, color=TEXT, pad=8)
    for s in hax.spines.values():
        s.set_color(GRID)
    ax.text(11.7, 1.35, "WR ↑ al acercar el TP · R ↑ al alejarlo: ese es el trade-off "
            "que el cubo mide.", fontsize=8.6, color=MUTE, ha="center")
    footer(ax, 4)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# PAGINA 5 — FRACTALES DE TIEMPO EMERGENTE
# ============================================================
def page_fractals(pdf):
    fig, ax = new_page()
    kicker(ax, 0.7, 8.4, "Fractales de tiempo emergente")
    ax.text(0.7, 7.75, "El mercado rima a través de las escalas",
            fontsize=22, color=TEXT, fontweight="bold")
    ax.text(0.7, 7.0,
            "Auto-similaridad: la misma firma estructural reaparece a distintos zooms. "
            "Reconocerla = encontrar el análogo (el fractal) cuyo desenlace ya es historia.",
            fontsize=10.6, color=MUTE)

    n = 2000
    y = fbm(n, 0.66, 17)
    t = np.arange(n)
    # serie completa
    a1 = fig.add_axes([0.06, 0.42, 0.55, 0.32]); a1.set_facecolor(PANEL)
    grad_line(a1, t, y, CYAN, GOLD, lw=1.4)
    a1.set_xlim(0, n); a1.set_ylim(y.min(), y.max())
    a1.set_xticks([]); a1.set_yticks([])
    for s in a1.spines.values(): s.set_color(GRID)
    a1.set_title("escala macro", fontsize=9.5, color=MUTE, loc="left")
    # ventana de zoom
    z0, z1 = 760, 1010
    a1.add_patch(Rectangle((z0, y[z0:z1].min()), z1-z0, y[z0:z1].max()-y[z0:z1].min(),
                           fill=False, ec=GOLD, lw=1.5))

    a2 = fig.add_axes([0.66, 0.50, 0.30, 0.20]); a2.set_facecolor(PANEL)
    yz = y[z0:z1]; grad_line(a2, np.arange(len(yz)), yz, GOLD, MAG, lw=1.6)
    a2.set_xlim(0, len(yz)); a2.set_ylim(yz.min(), yz.max())
    a2.set_xticks([]); a2.set_yticks([])
    for s in a2.spines.values(): s.set_color(GOLD)
    a2.set_title("zoom · misma estadística", fontsize=9, color=GOLD, loc="left")

    # recurrence plot (campo de recurrencias)
    m = 260
    ys = y[::n//m][:m]
    D = np.abs(ys[:, None] - ys[None, :])
    R = (D < np.quantile(D, 0.16)).astype(float)
    a3 = fig.add_axes([0.66, 0.10, 0.30, 0.34]); a3.set_facecolor(PANEL)
    cmr = matplotlib.colors.LinearSegmentedColormap.from_list("r", ["#0a1424", MAG, GOLD])
    a3.imshow(R, cmap=cmr, origin="lower", aspect="auto")
    a3.set_xticks([]); a3.set_yticks([])
    for s in a3.spines.values(): s.set_color(GRID)
    a3.set_title("campo de recurrencia (estados que se repiten)", fontsize=8.8, color=MUTE, loc="left")

    panel(ax, 0.9, 1.0, 9.0, 2.05, fc=PANEL2, ec=GRID)
    ax.text(1.2, 2.65, "De la imagen al edge", fontsize=10.5, color=GOLD, fontweight="bold")
    ax.text(1.2, 1.35,
            "El campo de recurrencia es la intuición hecha dato: las diagonales y bloques son\n"
            "estados que vuelven. turbovec los encuentra a gran escala; el cubo dice qué pagaron.\n"
            "Tiempo emergente = la coordenada que hace que dos velas distantes sean 'el mismo' fractal.",
            fontsize=9.6, color=TEXT, va="center", linespacing=1.5)
    footer(ax, 5)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# PAGINA 6 — RETRIEVAL: FRACTALES COMO VECINOS (k-NN)
# ============================================================
def page_knn(pdf):
    fig, ax = new_page()
    kicker(ax, 0.7, 8.4, "Retrieval · los fractales como vecinos")
    ax.text(0.7, 7.75, "Buscar el análogo, leer su desenlace",
            fontsize=22, color=TEXT, fontweight="bold")

    rng = np.random.default_rng(4)
    cloud = rng.normal(0, 1, size=(520, 2))
    cloud[:160] += [2.4, 1.6]; cloud[160:300] += [-2.2, 1.1]; cloud[300:] += [0.2, -2.0]
    q = np.array([2.1, 1.35])
    d = np.linalg.norm(cloud - q, axis=1)
    knn = np.argsort(d)[:28]
    sax = fig.add_axes([0.05, 0.10, 0.56, 0.62]); sax.set_facecolor(PANEL)
    sax.scatter(cloud[:, 0], cloud[:, 1], s=14, c=MUTE, alpha=0.45, edgecolors="none")
    sax.scatter(cloud[knn, 0], cloud[knn, 1], s=34, c=GOLD, edgecolors="#06101f",
                linewidths=0.4, label="k análogos (fractales)")
    sax.add_patch(Circle(q, d[knn].max(), fill=False, ec=CYAN, lw=1.4, ls="--"))
    sax.scatter([q[0]], [q[1]], s=240, marker="*", c=MAG, edgecolors="white",
                linewidths=0.8, label="estado actual (query)", zorder=5)
    sax.set_xticks([]); sax.set_yticks([])
    for s in sax.spines.values(): s.set_color(GRID)
    sax.legend(loc="lower left", fontsize=8.5, facecolor=PANEL2, edgecolor=GRID,
               labelcolor=TEXT)
    sax.set_title("espacio vectorial de estados (proyección 2D)", fontsize=9.5,
                  color=MUTE, loc="left")

    panel(ax, 9.9, 4.6, 5.4, 2.65, fc=PANEL2, ec=CYAN, lw=1.4)
    ax.text(10.2, 6.85, "Qué devuelve el vecindario", fontsize=11, color=CYAN, fontweight="bold")
    ax.text(10.2, 4.95,
            "·  expectancy_r  (pago esperado en R)\n"
            "·  win-rate ponderado por similitud\n"
            "·  dispersión (riesgo del vecindario)\n"
            "·  confianza = f(densidad, dispersión)\n"
            "·  best (TP, horizonte) del cubo vecino",
            fontsize=10, color=TEXT, va="top", linespacing=1.55)

    panel(ax, 9.9, 1.0, 5.4, 3.25, fc="#0c1322", ec=GOLD, lw=1.2)
    ax.text(10.2, 3.9, "Causalidad y abstención", fontsize=11, color=GOLD, fontweight="bold")
    ax.text(10.2, 1.35,
            "El índice SOLO contiene estados cuyo desenlace ya\n"
            "cerró (+ embargo): nada de futuro. Si el vecindario\n"
            "es ralo (pocos análogos coherentes), la capa SE\n"
            "ABSTIENE — no inventa edge donde no hay fractal.\n"
            "Honestidad > volumen de señales.",
            fontsize=9.6, color=TEXT, va="bottom", linespacing=1.5)
    footer(ax, 6)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# PAGINA 7 — LAS 5 DIMENSIONES DE PENSAMIENTO
# ============================================================
def page_five(pdf):
    fig, ax = new_page()
    kicker(ax, 0.7, 8.4, "Las 5 dimensiones de pensamiento")
    ax.text(0.7, 7.75, "El espacio de exploración del edge",
            fontsize=22, color=TEXT, fontweight="bold")

    labels = ["A · Composición\ndel vector", "B · Superficie\n(cubo)",
              "C · Geometría de\nsimilitud", "D · No-estacio-\nnariedad",
              "E · Abstención /\nconfianza"]
    cols = [GOLD, CYAN, MAG, GREEN, GOLD2]
    cx, cy, Rr = 4.0, 4.0, 2.55
    pax = fig.add_axes([0.02, 0.08, 0.46, 0.66]); pax.axis("off")
    pax.set_xlim(0, 8); pax.set_ylim(0, 8)
    ang = np.linspace(np.pi/2, np.pi/2 + 2*np.pi, 6)[:-1]
    pts = np.c_[cx + Rr*np.cos(ang), cy + Rr*np.sin(ang)]
    for rr in (0.4, 0.7, 1.0):
        poly = RegularPolygon((cx, cy), 5, radius=Rr*rr, orientation=np.pi/10,
                              fill=False, ec=GRID, lw=1)
        pax.add_patch(poly)
    vals = np.array([0.92, 0.85, 0.7, 0.66, 0.78])
    vpts = np.c_[cx + Rr*vals*np.cos(ang), cy + Rr*vals*np.sin(ang)]
    pax.add_patch(plt.Polygon(vpts, closed=True, fc=GOLD, ec=GOLD2, lw=2, alpha=0.18))
    for (x, y), (vx, vy), c, lb in zip(pts, vpts, cols, labels):
        pax.plot([cx, x], [cy, y], color=GRID, lw=1)
        pax.scatter([vx], [vy], s=60, c=c, edgecolors="white", linewidths=0.6, zorder=5)
        ha = "center"
        pax.text(cx + (Rr+0.7)*np.cos(np.arctan2(y-cy, x-cx)),
                 cy + (Rr+0.7)*np.sin(np.arctan2(y-cy, x-cx)),
                 lb, fontsize=8.6, color=c, ha=ha, va="center", linespacing=1.2,
                 fontweight="bold")

    # tabla derecha
    rows = [
        ("A", "Composición del vector", "kappa, σ_τ, sync, radar, campo", "lift OOS + ↓dispersión", GOLD),
        ("B", "Superficie (cubo)", "selector TP×horizonte vs fijo", "exp_R(selector) > fijo", CYAN),
        ("C", "Geometría de similitud", "escalado/whitening · k · régimen", "ninguna dim acapara", MAG),
        ("D", "No-estacionariedad", "ventana W · decaimiento τ", "régimen vivo > histórico", GREEN),
        ("E", "Abstención / confianza", "piso de densidad del vecindario", "exp_R ↑ con densidad", GOLD2),
    ]
    x0, y0, rw, rh = 7.7, 6.55, 7.6, 1.04
    for i, (k, name, what, test, c) in enumerate(rows):
        yy = y0 - i*rh
        panel(ax, x0, yy - rh + 0.18, rw, rh - 0.16, fc=PANEL2, ec=c, lw=1.3)
        ax.add_patch(Circle((x0 + 0.5, yy - 0.42), 0.28, fc=c, ec="none"))
        ax.text(x0 + 0.5, yy - 0.42, k, fontsize=11, color="#06101f", ha="center",
                va="center", fontweight="bold")
        ax.text(x0 + 1.05, yy - 0.18, name, fontsize=10.3, color=TEXT, fontweight="bold",
                va="center")
        ax.text(x0 + 1.05, yy - 0.6, f"explora: {what}", fontsize=8.4, color=MUTE, va="center")
        ax.text(x0 + rw - 0.2, yy - 0.42, test, fontsize=8.6, color=c, va="center", ha="right")
    ax.text(7.7, 0.92, "Puerta a TODO: el test de leakage (causal vs oracle vs placebo). "
            "Si colapsa → se mata la línea.", fontsize=8.4, color=MUTE)
    footer(ax, 7)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# PAGINA 8 — INTEGRACION QUANTUM BOT (mapping)
# ============================================================
def page_integration(pdf):
    fig, ax = new_page()
    kicker(ax, 0.7, 8.4, "Integración con el Quantum bot")
    ax.text(0.7, 7.75, "Cada idea original → una coordenada medible",
            fontsize=22, color=TEXT, fontweight="bold")

    rows = [
        ("Excitación de radar", "fq_radar", "evento / gatillo de campo", "FRONTERA", MAG),
        ("Tiempo emergente / complejo", "emergent_time · σ_τ", "fase y ritmo del tiempo", "FRONTERA", GOLD),
        ("Líneas de tiempo cuánticas", "quantum_timelines · sync", "sincronía entre escalas", "FRONTERA", CYAN),
        ("Entropía / κ (cognición)", "entropy_cognition · kappa", "convicción adaptativa", "FRONTERA", GOLD2),
        ("Excitación de campo", "field · confluence · w_eff", "huella energética", "PARCIAL", GREEN),
        ("Convicción del motor", "p_master · scorer ensemble", "probabilidad maestra", "EN EL VECTOR", "#7fd0ff"),
    ]
    ax.text(0.9, 7.05, "MAGNITUD DEL QUANTUM BOT", fontsize=8.5, color=MUTE)
    ax.text(6.7, 7.05, "SEÑAL REAL EN CÓDIGO", fontsize=8.5, color=MUTE)
    ax.text(10.9, 7.05, "INTERPRETACIÓN", fontsize=8.5, color=MUTE)
    ax.text(15.2, 7.05, "ESTADO", fontsize=8.5, color=MUTE, ha="right")
    y = 6.75; rh = 0.78
    for name, code, interp, st, c in rows:
        panel(ax, 0.7, y - rh + 0.14, 14.6, rh - 0.16, fc=PANEL2, ec=GRID, lw=1)
        ax.add_patch(Rectangle((0.7, y - rh + 0.14), 0.12, rh - 0.16, fc=c, ec="none"))
        ax.text(0.95, y - 0.4, name, fontsize=10.6, color=TEXT, fontweight="bold", va="center")
        ax.text(6.7, y - 0.4, code, fontsize=9.4, color=c, va="center", family="DejaVu Sans Mono"
                if False else "DejaVu Sans")
        ax.text(10.9, y - 0.4, interp, fontsize=9.2, color=MUTE, va="center")
        stc = {"FRONTERA": GOLD, "PARCIAL": CYAN, "EN EL VECTOR": GREEN}[st]
        panel(ax, 13.7, y - 0.68, 1.55, 0.5, fc="#0c1322", ec=stc, lw=1.1, r=0.25)
        ax.text(14.47, y - 0.43, st, fontsize=7.6, color=stc, ha="center", va="center",
                fontweight="bold")
        y -= rh

    panel(ax, 0.7, 0.82, 14.6, 1.3, fc="#0c1322", ec=GOLD)
    ax.text(0.95, 1.82, "La jugada", fontsize=10.5, color=GOLD, fontweight="bold")
    ax.text(0.95, 1.28,
            "Lo marcado FRONTERA aún no es coordenada del vector. Lifearlas (radar, σ_τ, sync, κ) y\n"
            "ablacionar = medir si el tiempo emergente y la excitación de campo dan edge — read-only, post-replay.",
            fontsize=9.2, color=TEXT, va="center", linespacing=1.4)
    footer(ax, 8)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# PAGINA 9 — LA FRONTERA DE RENTABILIDAD
# ============================================================
def page_frontier(pdf):
    fig, ax = new_page()
    kicker(ax, 0.7, 8.4, "La frontera de rentabilidad")
    ax.text(0.7, 7.75, "Más entendimiento del tiempo complejo → más edge compuesto",
            fontsize=20, color=TEXT, fontweight="bold")

    fax = fig.add_axes([0.07, 0.16, 0.6, 0.56]); fax.set_facecolor(PANEL)
    x = np.linspace(0, 1, 200)
    edge = 0.04 + 0.9 / (1 + np.exp(-8*(x - 0.55)))   # logistica
    band = 0.10 + 0.18*x
    fax.fill_between(x, edge*(1-band), edge*(1+band), color=GOLD, alpha=0.12,
                     label="IC bootstrap (incertidumbre)")
    grad_line(fax, x, edge, CYAN, "#ff8a3d", lw=2.6)
    # hitos F1..F4
    for xf, lab, c in [(0.18, "F1 diagnóstico", CYAN), (0.42, "F2 gate+sizing", GOLD),
                       (0.66, "F3 selector TP/H", MAG), (0.9, "F4 capital", "#ff8a3d")]:
        yf = 0.04 + 0.9/(1+np.exp(-8*(xf-0.55)))
        fax.scatter([xf], [yf], s=60, c=c, edgecolors="white", lw=0.6, zorder=5)
        fax.text(xf, yf + 0.06, lab, fontsize=8.2, color=c, ha="center")
    fax.set_xlim(0, 1); fax.set_ylim(0, 1.15)
    fax.set_xlabel("profundidad de entendimiento del tiempo complejo →", fontsize=9.5)
    fax.set_ylabel("edge medible (R) → rentabilidad compuesta", fontsize=9.5)
    fax.set_xticks([]); fax.set_yticks([])
    for s in fax.spines.values(): s.set_color(GRID)
    fax.legend(loc="upper left", fontsize=8, facecolor=PANEL2, edgecolor=GRID, labelcolor=TEXT)

    panel(ax, 10.4, 4.35, 4.9, 2.95, fc=PANEL2, ec=GOLD, lw=1.4)
    ax.text(10.7, 6.95, "Cómo se compone", fontsize=11, color=GOLD, fontweight="bold")
    ax.text(10.7, 6.5,
            "·  cada dimensión que pasa el test\n"
            "   suma edge atribuible\n"
            "·  el cubo convierte WR×R en la\n"
            "   curva de expectancy óptima\n"
            "·  el retrieval aísla los estados de oro\n"
            "·  edge × frecuencia × compuesto",
            fontsize=9.3, color=TEXT, va="top", linespacing=1.4)

    panel(ax, 10.4, 1.0, 4.9, 3.1, fc="#0c1322", ec=RED, lw=1.2)
    ax.text(10.7, 3.75, "Lectura honesta", fontsize=10.5, color=RED, fontweight="bold")
    ax.text(10.7, 1.3,
            "La curva es la FRONTERA OBJETIVO que la\n"
            "arquitectura está diseñada para capturar,\n"
            "no un retorno prometido. Cada tramo se\n"
            "desbloquea SOLO con edge OOS atribuible\n"
            "(IC inferior 90% > 0). Sin eso, no se\n"
            "mueve capital. La elegancia es la disciplina.",
            fontsize=9.0, color=TEXT, va="bottom", linespacing=1.4)
    footer(ax, 9)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# PAGINA 10 — POR QUE ES INUSUAL
# ============================================================
def page_unusual(pdf):
    fig, ax = new_page()
    kicker(ax, 0.7, 8.4, "Por qué es inusual")
    ax.text(0.7, 7.75, "Una aproximación que no se ve en el mercado estructural",
            fontsize=21, color=TEXT, fontweight="bold")

    cards = [
        ("Estimador LOCAL, no fórmula", "No ajustamos una ecuación global: medimos por "
         "analogía sobre el histórico vivo. El mercado se trata como campo de estados.", GOLD),
        ("Doble cerebro", "GBM global (patrón medio) + retrieval k-NN causal (la excepción "
         "local) se complementan. Pocos combinan ambos con guardas de leakage.", CYAN),
        ("Tiempo emergente como geometría", "El tiempo no es eje: es coordenada del vector. "
         "Dos velas distantes pueden ser 'el mismo' fractal. Eso redefine 'similar'.", MAG),
        ("Optimización sin re-replay", "TP, SL y horizonte se optimizan gratis sobre el mismo "
         "replay (el cubo). Barrer estrategia cuesta casi cero.", GREEN),
        ("Abstención honesta", "Cuando no hay fractal, el modelo calla. La señal de oro nace "
         "de densidad+coherencia del vecindario, no de forzar volumen.", GOLD2),
        ("Símbolo-agnóstico", "El MISMO código corre BTC y SOL; solo cambian los datos. "
         "Escala a cualquier mercado sin reescribir la lógica.", "#7fd0ff"),
    ]
    x0, y0, cw, ch, gx, gy = 0.7, 4.05, 7.15, 2.95, 0.5, 0.45
    for i, (t, d, c) in enumerate(cards):
        cx = x0 + (i % 2) * (cw + gx)
        cy = y0 - (i // 2) * (ch + gy)
        panel(ax, cx, cy, cw, ch, fc=PANEL2, ec=c, lw=1.4)
        ax.add_patch(Rectangle((cx, cy + ch - 0.12), cw, 0.12, fc=c, ec="none"))
        ax.text(cx + 0.35, cy + ch - 0.55, t, fontsize=11.5, color=c, fontweight="bold")
        ax.text(cx + 0.35, cy + ch - 1.0, d, fontsize=9.4, color=TEXT, va="top",
                wrap=True, linespacing=1.45)
    footer(ax, 10)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


# ============================================================
# PAGINA 11 — ESTADO, ROADMAP Y CIERRE
# ============================================================
def page_roadmap(pdf):
    fig, ax = new_page()
    kicker(ax, 0.7, 8.4, "Estado · roadmap · cierre")
    ax.text(0.7, 7.75, "Construido, validándose, y con la frontera a la vista",
            fontsize=21, color=TEXT, fontweight="bold")

    phases = [
        ("F0", "Harness + leakage gate", "VERDE (CI sintético)", GREEN),
        ("F1", "Retrieval diagnóstico\nBTC + SOL", "VALIDANDO (run real)", GOLD),
        ("F2", "Gate + sizing", "siguiente si F1 +", CYAN),
        ("F3", "Selector TP/horizonte", "usa el cubo", MAG),
        ("F4", "Comparativa y capital", "criterio de migración", "#ff8a3d"),
    ]
    x = 0.7; w = 2.85; gap = 0.3; y = 4.5; h = 1.95
    for i, (k, t, st, c) in enumerate(phases):
        panel(ax, x, y, w, h, fc=PANEL2, ec=c, lw=1.4)
        ax.text(x + 0.35, y + h - 0.5, k, fontsize=16, color=c, fontweight="bold")
        ax.text(x + 0.35, y + h - 1.0, t, fontsize=9.4, color=TEXT, va="top", linespacing=1.3)
        ax.text(x + 0.35, y + 0.25, st, fontsize=8.2, color=c)
        if i < len(phases) - 1:
            ax.add_patch(FancyArrowPatch((x + w + 0.02, y + h/2), (x + w + gap - 0.02, y + h/2),
                         arrowstyle="-|>", mutation_scale=14, color=GOLD, lw=1.8))
        x += w + gap

    panel(ax, 0.7, 2.45, 14.6, 1.55, fc=PANEL, ec=CYAN, lw=1.3)
    ax.text(0.95, 3.55, "Siguiente build recomendado — Eje A", fontsize=11, color=CYAN,
            fontweight="bold")
    ax.text(0.95, 2.75,
            "Lift de kappa_evo · σ_τ (tiempo emergente) · sync_score · radar al vector de estado "
            "+ su ablación en el runner. Bajo riesgo (read-only, post-replay). El próximo run ya "
            "mediría si los fractales de tiempo emergente aportan edge atribuible.",
            fontsize=9.7, color=TEXT, va="center", linespacing=1.45)

    panel(ax, 0.7, 0.95, 14.6, 1.3, fc="#0c1322", ec=GOLD, lw=1.3)
    ax.text(8.0, 1.78, "\"El mercado es un campo de estados. Medimos su huella, reconocemos el",
            fontsize=11.5, color=GOLD2, ha="center", style="italic")
    ax.text(8.0, 1.32, "fractal, y convertimos el entendimiento del tiempo complejo en edge.\"",
            fontsize=11.5, color=GOLD2, ha="center", style="italic")
    footer(ax, 11)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


def main():
    out = "FQ_Frontera_TiempoComplejo.pdf"
    with PdfPages(out) as pdf:
        page_cover(pdf)
        page_thesis(pdf)
        page_pipeline(pdf)
        page_cube(pdf)
        page_fractals(pdf)
        page_knn(pdf)
        page_five(pdf)
        page_integration(pdf)
        page_frontier(pdf)
        page_unusual(pdf)
        page_roadmap(pdf)
    print("OK ->", out)


if __name__ == "__main__":
    main()
