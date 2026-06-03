# -*- coding: utf-8 -*-
"""
Genera PRESENTACION_TECNICA.pdf: el deck tecnico interno de FQ.

Mismo lenguaje visual que el deck comercial (reportlab + DejaVu) pero con
contenido de ingenieria: topologia, pipeline de decision, modulos, QTE,
memoria/evolucion, co-pilot LLM y roadmap. Material INTERNO.

Uso:
    python ops/build_presentacion_tecnica_pdf.py [salida.pdf]
"""
import os
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Preformatted, Table, TableStyle, PageBreak,
)
from reportlab.platypus.doctemplate import NextPageTemplate
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ----------------------------------------------------------------------
# Fuentes (DejaVu: cobertura Unicode para glifos de marca + box-drawing)
# ----------------------------------------------------------------------
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("FQSans",      os.path.join(FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("FQSans-Bold", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("FQMono",      os.path.join(FONT_DIR, "DejaVuSansMono.ttf")))
pdfmetrics.registerFontFamily(
    "FQSans", normal="FQSans", bold="FQSans-Bold",
    italic="FQSans", boldItalic="FQSans-Bold",
)

# ----------------------------------------------------------------------
# Paleta (igual al deck comercial)
# ----------------------------------------------------------------------
INK    = colors.HexColor("#16202e")
ACCENT = colors.HexColor("#0f766e")
MUTED  = colors.HexColor("#5b6b7b")
BOXBG  = colors.HexColor("#f4f6f8")
LINE   = colors.HexColor("#d7dde3")
PAPER  = colors.HexColor("#ffffff")

RULE = "━" * 28

# ----------------------------------------------------------------------
# Estilos
# ----------------------------------------------------------------------
styles = getSampleStyleSheet()

def S(name, **kw):
    base = kw.pop("parent", styles["Normal"])
    return ParagraphStyle(name, parent=base, **kw)

st_h1 = S("h1", fontName="FQSans-Bold", fontSize=16, leading=20,
          textColor=INK, spaceBefore=2, spaceAfter=6)
st_kicker = S("kicker", fontName="FQSans-Bold", fontSize=9, leading=12,
              textColor=ACCENT, spaceAfter=2)
st_body = S("body", fontName="FQSans", fontSize=10, leading=14.5,
            textColor=INK, spaceAfter=5)
st_lead = S("lead", fontName="FQSans", fontSize=11, leading=16,
            textColor=INK, spaceAfter=7)
st_quote = S("quote", fontName="FQSans-Bold", fontSize=10.5, leading=15,
             textColor=ACCENT, leftIndent=10, spaceBefore=3, spaceAfter=7)
st_bullet = S("bullet", parent=st_body, leftIndent=14, spaceAfter=3)
st_small = S("small", fontName="FQSans", fontSize=8.5, leading=12, textColor=MUTED)
st_box = S("box", fontName="FQMono", fontSize=8.2, leading=11.0, textColor=INK)
st_code = S("code", fontName="FQMono", fontSize=8.6, leading=12.5, textColor=INK)

st_brand = S("brand", fontName="FQSans-Bold", fontSize=64, leading=66,
             textColor=INK, alignment=TA_CENTER)
st_diamond = S("diamond", fontName="FQSans", fontSize=26, leading=28,
               textColor=ACCENT, alignment=TA_CENTER)
st_tag = S("tag", fontName="FQSans", fontSize=14, leading=20,
           textColor=INK, alignment=TA_CENTER, spaceBefore=10)
st_promise = S("promise", fontName="FQSans-Bold", fontSize=12, leading=18,
               textColor=ACCENT, alignment=TA_CENTER, spaceBefore=8)
st_coverfoot = S("coverfoot", fontName="FQSans", fontSize=9, leading=13,
                 textColor=MUTED, alignment=TA_CENTER)


def codebox(text):
    """Caja monoespaciada (diagramas / arboles de modulos)."""
    pre = Preformatted(text, st_code)
    return _wrap_box(pre)


def box(text):
    pre = Preformatted(text, st_box)
    return _wrap_box(pre)


def _wrap_box(flowable):
    t = Table([[flowable]], colWidths=[150 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), BOXBG),
        ("BOX",          (0, 0), (-1, -1), 0.5, LINE),
        ("LEFTPADDING",  (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING",   (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 9),
    ]))
    return t


def bullets(items):
    return [Paragraph("<font color='#0f766e'>▸</font>&nbsp;&nbsp;" + it,
                      st_bullet) for it in items]


def kv_table(rows, col0=55 * mm, col1=95 * mm, header=None):
    """Tabla de 2 columnas. rows = lista de (a, b). header opcional (a, b)."""
    body_l = S("cl", fontName="FQSans-Bold", fontSize=9, leading=12.5, textColor=INK)
    body_r = S("cr", fontName="FQSans", fontSize=9, leading=12.5, textColor=INK)
    data = []
    start = 0
    if header:
        data.append([Paragraph(header[0], S("hl", fontName="FQSans-Bold",
                     fontSize=9, leading=12, textColor=PAPER)),
                     Paragraph(header[1], S("hr", fontName="FQSans-Bold",
                     fontSize=9, leading=12, textColor=PAPER))])
        start = 1
    for a, b in rows:
        data.append([Paragraph(a, body_l), Paragraph(b, body_r)])
    t = Table(data, colWidths=[col0, col1])
    style = [
        ("LINEBELOW",    (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, start), (-1, -1), [PAPER, BOXBG]),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), INK)]
    t.setStyle(TableStyle(style))
    return t


def _hr():
    t = Table([[""]], colWidths=[150 * mm], rowHeights=[0.1])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1, ACCENT)]))
    return t


def section(num, title):
    return [
        Spacer(1, 4),
        Paragraph("SECCION {:02d}".format(num), st_kicker),
        Paragraph(title, st_h1),
        _hr(),
        Spacer(1, 4),
    ]


# ----------------------------------------------------------------------
# Page backgrounds
# ----------------------------------------------------------------------
def page_bg(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(INK)
    canvas.rect(0, h - 6, w, 6, stroke=0, fill=1)
    canvas.setFont("FQSans", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 12 * mm, "FQ · Documento técnico interno")
    canvas.drawRightString(w - 20 * mm, 12 * mm, "Pag. {}".format(doc.page))
    canvas.restoreState()


def cover_bg(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(INK)
    canvas.rect(0, h - 10, w, 10, stroke=0, fill=1)
    canvas.rect(0, 0, w, 10, stroke=0, fill=1)
    canvas.restoreState()


# ----------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------
def build(out_path):
    doc = BaseDocTemplate(
        out_path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=22 * mm, bottomMargin=20 * mm,
        title="FQ - Presentacion tecnica", author="FQ",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([
        PageTemplate(id="cover",  frames=[frame], onPage=cover_bg),
        PageTemplate(id="normal", frames=[frame], onPage=page_bg),
    ])

    el = []

    # ---------------- Portada ----------------
    el.append(Spacer(1, 52 * mm))
    el.append(Paragraph("◆", st_diamond))
    el.append(Spacer(1, 4))
    el.append(Paragraph("FQ", st_brand))
    el.append(Spacer(1, 6))
    el.append(Paragraph("Arquitectura y motor de decisión.", st_tag))
    el.append(Paragraph("Señales SOL/USDT con disciplina sistemática.", st_promise))
    el.append(Spacer(1, 58 * mm))
    el.append(Paragraph("Presentación técnica · documento interno", st_coverfoot))
    el.append(NextPageTemplate("normal"))
    el.append(PageBreak())

    # ---------------- 1 · Resumen ----------------
    el += section(1, "Resumen del sistema")
    el.append(Paragraph(
        "FQ es un bot de <b>trading + pagos en vivo</b> sobre SOL/USDT en "
        "producción (Railway). Vigila el mercado en tiempo real, evalúa setups "
        "contra un pipeline de varias fases y solo dispara cuando superan el "
        "gate de convicción. Cada señal se sigue hasta su cierre y el outcome "
        "alimenta la memoria estadística.", st_lead))
    el += bullets([
        "<b>~18,000 líneas</b> en total; el monolito <font face='FQMono'>fq_bot_v3_2.py</font> concentra ~4,900.",
        "<b>Dos caras:</b> bot VIP (motor + señales) y bot público (marketing, read-only).",
        "<b>Runtime ligero:</b> numpy + pandas + LLM on-demand. Sin libs cuánticas ni ML pesado.",
    ])

    # ---------------- 2 · Topología ----------------
    el += section(2, "Topología de procesos")
    el.append(Paragraph(
        "<font face='FQMono'>launcher.py</font> arranca 3 procesos hijos en el "
        "<b>mismo</b> servicio Railway (no permite volúmenes compartidos entre "
        "servicios), sobre el mismo volumen:", st_body))
    el.append(codebox(
        "launcher.py\n"
        "  ├─ vip          entry_vip.py → fq_bot_v3_2.py\n"
        "  │               motor, gate QTE, radar/alertas,\n"
        "  │               comandos VIP, ledger (escritura)\n"
        "  ├─ public       entry_public.py\n"
        "  │               marketing; lee ledger VIP READ-ONLY,\n"
        "  │               anuncia cierres / teasers / TP3\n"
        "  └─ maintenance  ops.maintenance\n"
        "                  backups, heartbeat"
    ))
    el.append(Spacer(1, 6))
    el.append(Paragraph(
        "Comunicación <b>VIP → Público: solo</b> vía el SQLite del ledger (RO). "
        "Cero acoplamiento de código. Si un hijo muere, el launcher sale con "
        "<font face='FQMono'>rc != 0</font> y Railway reinicia el contenedor.", st_body))

    # ---------------- 3 · Stack ----------------
    el += section(3, "Stack")
    el.append(kv_table([
        ("Lenguaje", "Python 3.11 (ASCII-only en módulos de motor)"),
        ("Datos de mercado", "CCXT (fetch_ohlcv) + pandas / pandas-ta"),
        ("Cómputo", "numpy / pandas"),
        ("Persistencia", "SQLite (ledger append-only; RO para el público)"),
        ("Mensajería", "Telegram Bot API (long polling)"),
        ("LLM", "Anthropic — Sonnet (lecturas) + Opus (revisión / audit)"),
        ("Web / health", "Flask"),
        ("Deploy", "Railway (railway.toml, Procfile)"),
    ], header=("Capa", "Tecnología")))

    el.append(PageBreak())

    # ---------------- 4 · Pipeline ----------------
    el += section(4, "Pipeline de decisión")
    el.append(Paragraph(
        "<font face='FQMono'>fusion_engine.evaluate_signal()</font> es la "
        "<b>única</b> función pública del motor. Evalúa en fases:", st_body))
    el += bullets([
        "<b>Fase A — Sesgo estructural + PD.</b> Dirección y zona Premium/Discount.",
        "<b>Fase B — Liquidez.</b> Sweeps, pools no barridos, calidad de reacción.",
        "<b>Fase C — Confluencia ICT.</b> Requiere CONFLUENCE_MIN ≥ 3; +4% por concepto (cap +16%).",
        "<b>Fase D — Timing + CRT + memoria.</b> Bucket de outcome → kappa_evo (±15% sobre P_master).",
        "<b>Fase E — Sync modulator.</b> Tiempo emergente tau; sync_score &lt; 0.30 → veto absoluto.",
        "<b>Volume quality</b> (v5.2) — modulador final sobre P_master.",
    ])
    el.append(Spacer(1, 3))
    el.append(Paragraph(
        "<b>Gate de convicción:</b> P_master ≥ phi² (≈2.618). Para "
        "<i>fire/broadcast</i>, CONSTRAINTS §6 exige P_master ≥ 7/10 (~2.965). "
        "El gate <font face='FQMono'>Theta(D)</font> es sagrado: ningún "
        "modulador lo toca.", st_body))
    el.append(Paragraph(
        "<b>Capa ML (v4.3, additiva y advisory):</b> ensemble de 5 scorers "
        "(volume, structure, liquidity, concept_stack, history) + atribución "
        "Shapley. Enriquece la decisión cuando P_master ya pasó el umbral; no "
        "sustituye al motor.", st_body))

    # ---------------- 5 · Módulos ----------------
    el += section(5, "Mapa de módulos")
    el.append(codebox(
        "Núcleo de decisión   fusion_engine · quantum_timelines\n"
        "  (puro, testeable)   battle_planner · signal_scorer\n"
        "                      ict_smc · market_context · regime_detector\n"
        "                      volume_quality · killzones_pd\n"
        "                      emergent_time · entropy_cognition\n"
        "                      fq_radar · fq_market_data   (extraídos v5.3)\n"
        "Presentación          branding · vip_format · public_format\n"
        "  (blindada x tests)  field_reports · legal\n"
        "Bot público           public_outcome_announcer · public_scheduler\n"
        "                      public_handlers · public_content_generator\n"
        "Pagos / suscripción   vip_system · payments\n"
        "Monolito (a adelgazar) fq_bot_v3_2  (loop, broadcast, routing, hooks)"
    ))

    el.append(PageBreak())

    # ---------------- 6 · QTE ----------------
    el += section(6, "Motor QTE (Quantum Timelines Engine)")
    el.append(Paragraph(
        "Motor probabilístico <b>cuántico-inspirado</b> (sin qiskit ni dimod). "
        "Simula N futuros (Monte Carlo paths) bajo restricciones estructurales "
        "y mide P(TP_i), P(SL), valor esperado en R y régimen dominante.", st_body))
    el.append(kv_table([
        ("Superposición", "N paths Monte Carlo coexistiendo"),
        ("Función de onda", "Distribución empírica de paths"),
        ("Hamiltoniano", "bias: drift + vol + magnetic_pull"),
        ("QAOA", "grid search sobre (SL, TP1, TP2, TP3) → max EV"),
        ("Colapso / medición", "régimen modal del ensemble"),
        ("Decoherencia", "divergencia de paths = incertidumbre"),
    ], header=("Concepto cuántico", "Mapeo clásico")))
    el.append(Spacer(1, 6))
    el += bullets([
        "<b>300–2000 paths</b>, horizonte 96 velas de 15m (= 24h).",
        "Performance objetivo: <b>&lt; 1.5s con 500 paths</b> en Railway.",
        "Módulo <b>inerte</b>: solo computa, no envía ni toca DB.",
    ])

    # ---------------- 7 · Memoria ----------------
    el += section(7, "Memoria y autoevolución")
    el.append(Paragraph(
        "<font face='FQMono'>entropy_cognition</font> — el bot no recuerda "
        "outcomes individuales, los <b>destila</b> en distribuciones:", st_body))
    el += bullets([
        "<b>SignalLedger</b> — SQLite append-only, backup a Telegram.",
        "<b>OutcomeTracker</b> — monitorea señales abiertas hasta TP/SL/timeout.",
        "<b>EntropyEngine</b> — Shannon H sobre buckets (sesión×tier×dirección×curvatura) + KL drift.",
        "<b>KappaEvo</b> — modulador suave ±15% sobre P_master. Nunca toca Theta(D).",
        "<b>SelfAudit</b> — cada 25 cerradas, Opus audita y propone ajustes (no autoaplicados).",
    ])
    el.append(Paragraph(
        "<font face='FQMono'>emergent_time</font> — postulado tau = phi_clock · "
        "phi_memory · phi_horizon · phi_refractory. Módulo puro. "
        "<font face='FQMono'>battle_planner</font> combina campo ICT + paths QTE "
        "y emite: EJECUTAR_AHORA / ACUMULAR_EN_ZONA / ESPERAR_GATILLO / "
        "STAND_DOWN.", st_body))

    el.append(PageBreak())

    # ---------------- 8 · LLM ----------------
    el += section(8, "Co-pilot LLM")
    el.append(Paragraph(
        "<font face='FQMono'>claude_integration.py</font> — LLM táctico "
        "on-demand:", st_body))
    el += bullets([
        "<b>Sonnet</b> — lecturas VIP y análisis a pedido.",
        "<b>Opus</b> — revisión de señales auto-disparadas de alta convicción y self-audit.",
    ])
    el.append(Paragraph(
        "Recibe payloads ricos (precio, QTE, niveles, eventos, walls, "
        "derivados). En superficies de cliente el output es <b>cualitativo</b> "
        "(probabilidad alta / edge claro), nunca fórmulas ni jerga del motor.", st_body))

    # ---------------- 9 · Roadmap ----------------
    el += section(9, "Migración y roadmap")
    el.append(Paragraph(
        "Estrategia <b>strangler fig</b>: extraer piezas del monolito a módulos "
        "puros/testeables, por etapas verificadas y reversibles. Regla de oro: "
        "extraer → el monolito importa/reexporta → pytest verde antes de "
        "commitear.", st_body))
    el += bullets([
        "<font color='#0f766e'>[hecho]</font> <font face='FQMono'>fq_radar.py</font> — decisión pura del radar.",
        "<font color='#0f766e'>[hecho]</font> <font face='FQMono'>fq_market_data.py</font> — fetch_ohlcv + add_indicators mockeables.",
        "[ ] <font face='FQMono'>fq_broadcast.py</font> — envío Telegram desacoplado de globals.",
        "[ ] <font face='FQMono'>fq_commands/</font> — router de comandos (hoy un gran if/elif).",
        "[ ] <font face='FQMono'>fq_signal_loop.py</font> — loop principal + hooks como orquestador.",
        "[ ] paquete <font face='FQMono'>fq/</font> — agrupar piezas; monolito como shim de arranque.",
    ])

    # ---------------- 10 · Garantías ----------------
    el += section(10, "Garantías y pruebas")
    el += bullets([
        "<font face='FQMono'>pytest</font> como suite principal + self-tests embebidos (emergent_time, quantum_timelines, battle_planner).",
        "<font face='FQMono'>tests/test_client_surfaces.py</font> blinda las superficies de cliente: caza filtraciones de versión, modelo, framework o fórmula.",
        "Toda constante de tuning es override-able por env (defaults en el módulo).",
        "Módulos de motor en ASCII-only; sin side effects al importar.",
    ])
    el.append(Spacer(1, 12))
    el.append(_hr())
    el.append(Spacer(1, 6))
    el.append(Paragraph("FQ · Documento técnico interno. No distribuir como "
                        "material de cliente.", st_small))

    doc.build(el)
    return out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "PRESENTACION_TECNICA.pdf"
    path = build(out)
    print("PDF generado: {} ({} bytes)".format(path, os.path.getsize(path)))
