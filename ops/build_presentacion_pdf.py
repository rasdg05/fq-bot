# -*- coding: utf-8 -*-
"""
Genera PRESENTACION.pdf a partir del deck comercial de FQ.

Render con reportlab + DejaVu (cobertura Unicode para glifos de marca:
glifos geometricos y box-drawing). Sin dependencias de red en runtime.

Uso:
    python ops/build_presentacion_pdf.py [salida.pdf]
"""
import os
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    Preformatted, Table, TableStyle, PageBreak,
)
from reportlab.platypus.doctemplate import NextPageTemplate
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ----------------------------------------------------------------------
# Fuentes
# ----------------------------------------------------------------------
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("FQSans",      os.path.join(FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("FQSans-Bold", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("FQMono",      os.path.join(FONT_DIR, "DejaVuSansMono.ttf")))
pdfmetrics.registerFont(TTFont("FQMono-Bold", os.path.join(FONT_DIR, "DejaVuSansMono-Bold.ttf")))
pdfmetrics.registerFontFamily(
    "FQSans", normal="FQSans", bold="FQSans-Bold",
    italic="FQSans", boldItalic="FQSans-Bold",
)

# ----------------------------------------------------------------------
# Paleta
# ----------------------------------------------------------------------
INK    = colors.HexColor("#16202e")   # texto / titulos
ACCENT = colors.HexColor("#0f766e")   # teal sobrio
MUTED  = colors.HexColor("#5b6b7b")   # secundario
BOXBG  = colors.HexColor("#f4f6f8")   # fondo de cajas mono
LINE   = colors.HexColor("#d7dde3")   # reglas/bordes
PAPER  = colors.HexColor("#ffffff")

RULE = "━" * 28  # ━

# ----------------------------------------------------------------------
# Estilos
# ----------------------------------------------------------------------
styles = getSampleStyleSheet()

def S(name, **kw):
    base = kw.pop("parent", styles["Normal"])
    return ParagraphStyle(name, parent=base, **kw)

st_h1 = S("h1", fontName="FQSans-Bold", fontSize=17, leading=21,
          textColor=INK, spaceBefore=2, spaceAfter=6)
st_kicker = S("kicker", fontName="FQSans-Bold", fontSize=9, leading=12,
              textColor=ACCENT, spaceAfter=2, tracking=1)
st_body = S("body", fontName="FQSans", fontSize=10.5, leading=15.5,
            textColor=INK, spaceAfter=5)
st_lead = S("lead", fontName="FQSans", fontSize=11.5, leading=17,
            textColor=INK, spaceAfter=7)
st_quote = S("quote", fontName="FQSans-Bold", fontSize=11, leading=16,
             textColor=ACCENT, leftIndent=10, spaceBefore=3, spaceAfter=7)
st_bullet = S("bullet", parent=st_body, leftIndent=14, bulletIndent=2,
              spaceAfter=3)
st_small = S("small", fontName="FQSans", fontSize=8.5, leading=12,
             textColor=MUTED)
st_box = S("box", fontName="FQMono", fontSize=8.6, leading=11.6,
           textColor=INK)

# Portada
st_brand = S("brand", fontName="FQSans-Bold", fontSize=64, leading=66,
             textColor=INK, alignment=TA_CENTER)
st_diamond = S("diamond", fontName="FQSans", fontSize=26, leading=28,
               textColor=ACCENT, alignment=TA_CENTER)
st_tag = S("tag", fontName="FQSans", fontSize=14, leading=20,
           textColor=INK, alignment=TA_CENTER, spaceBefore=10)
st_promise = S("promise", fontName="FQSans-Bold", fontSize=13, leading=19,
               textColor=ACCENT, alignment=TA_CENTER, spaceBefore=8)
st_coverfoot = S("coverfoot", fontName="FQSans", fontSize=9, leading=13,
                 textColor=MUTED, alignment=TA_CENTER)


def box(text):
    """Caja monoespaciada estilo Telegram, sobre fondo gris."""
    pre = Preformatted(text, st_box)
    t = Table([[pre]], colWidths=[150 * mm])
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


def section(num, title):
    return [
        Spacer(1, 4),
        Paragraph("SECCION {:02d}".format(num), st_kicker),
        Paragraph(title, st_h1),
        _hr(),
        Spacer(1, 4),
    ]


def _hr():
    t = Table([[""]], colWidths=[150 * mm], rowHeights=[0.1])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1, ACCENT)]))
    return t


# ----------------------------------------------------------------------
# Documento
# ----------------------------------------------------------------------
def page_bg(canvas, doc):
    canvas.saveState()
    w, h = A4
    # banda superior fina
    canvas.setFillColor(INK)
    canvas.rect(0, h - 6, w, 6, stroke=0, fill=1)
    # pie
    canvas.setFont("FQSans", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 12 * mm,
                      "FQ · Señales SOL/USDT con disciplina sistemática")
    canvas.drawRightString(w - 20 * mm, 12 * mm, "Pag. {}".format(doc.page))
    canvas.restoreState()


def cover_bg(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(INK)
    canvas.rect(0, h - 10, w, 10, stroke=0, fill=1)
    canvas.rect(0, 0, w, 10, stroke=0, fill=1)
    canvas.restoreState()


def build(out_path):
    doc = BaseDocTemplate(
        out_path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=22 * mm, bottomMargin=20 * mm,
        title="FQ - Presentacion", author="FQ",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="main")
    doc.addPageTemplates([
        PageTemplate(id="cover",  frames=[frame], onPage=cover_bg),
        PageTemplate(id="normal", frames=[frame], onPage=page_bg),
    ])

    el = []

    # ---------------- Portada ----------------
    el.append(Spacer(1, 55 * mm))
    el.append(Paragraph("◆", st_diamond))
    el.append(Spacer(1, 4))
    el.append(Paragraph("FQ", st_brand))
    el.append(Spacer(1, 6))
    el.append(Paragraph("Señales SOL/USDT con disciplina sistemática.", st_tag))
    el.append(Paragraph("Cuando hay edge, dispara. Cuando no, calla.", st_promise))
    el.append(Spacer(1, 60 * mm))
    el.append(Paragraph("Presentación comercial", st_coverfoot))
    el.append(NextPageTemplate("normal"))
    el.append(PageBreak())

    # ---------------- 1 · Portada / qué es ----------------
    el += section(1, "Qué es FQ")
    el.append(box(
        RULE + "\n"
        "  ◆ FQ\n"
        + RULE + "\n"
        "  Señales SOL/USDT con\n"
        "  disciplina sistemática.\n\n"
        "  Cuando hay edge, dispara.\n"
        "  Cuando no, calla.\n"
        + RULE
    ))
    el.append(Spacer(1, 7))
    el.append(Paragraph(
        "FQ es un sistema que vigila SOL/USDT las 24 horas y avisa "
        "<b>solo</b> cuando detecta una operación con ventaja medible. "
        "No es un grupo de opiniones ni un gurú con corazonadas: es un "
        "proceso que se repite igual cada día.", st_lead))

    # ---------------- 2 · El problema ----------------
    el += section(2, "El problema")
    el.append(Paragraph("La mayoría de quien opera cripto pierde por las "
                        "mismas razones:", st_body))
    el += bullets([
        "<b>Demasiadas señales.</b> Canales que mandan 20 alertas al día. Ruido, no edge.",
        "<b>Sin niveles claros.</b> “Compra SOL” sin entry, sin stop, sin objetivo.",
        "<b>Emoción.</b> Se mueve el stop “para darle aire” y se rompe la disciplina.",
        "<b>Cero rendición de cuentas.</b> Nadie publica los resultados reales, solo los aciertos.",
    ])
    el.append(Spacer(1, 4))
    el.append(Paragraph("El resultado es siempre el mismo: actividad constante, "
                        "capital que se erosiona.", st_body))

    # ---------------- 3 · La solución ----------------
    el += section(3, "La solución")
    el.append(Paragraph(
        "FQ invierte el modelo. En lugar de buscar razones para operar, busca "
        "razones para <b>no</b> operar — y solo dispara cuando ninguna queda "
        "en pie.", st_body))
    el += bullets([
        "<b>Selectivo.</b> 1–3 operaciones al día en un buen día. Muchos días, ninguna.",
        "<b>Completo.</b> Cada señal llega con entry, stop loss y objetivos exactos.",
        "<b>Disciplinado.</b> El stop se ancla a la estructura del mercado y no se mueve.",
        "<b>Auditable.</b> Cada cierre queda registrado y los resultados se publican.",
    ])
    el.append(Paragraph("No vendemos predicciones. Vendemos resultados "
                        "verificables.", st_quote))

    el.append(PageBreak())

    # ---------------- 4 · Cómo funciona ----------------
    el += section(4, "Cómo funciona")
    el.append(Paragraph("El motor lee el mercado en tiempo real y solo habla "
                        "cuando se alinean varias cosas a la vez:", st_body))
    el += bullets([
        "<b>Estructura.</b> Dónde está realmente la liquidez y hacia dónde tiende el precio.",
        "<b>Sesión.</b> Prioriza las horas de mayor volumen institucional y calla cuando el mercado está delgado.",
        "<b>Confluencia.</b> Cuando varias lecturas independientes apuntan al mismo lado, y solo entonces, se arma la señal.",
        "<b>Convicción.</b> Cada señal trae un nivel (Media / Alta / Extrema) para que sepas cuánto pesa.",
    ])
    el.append(Spacer(1, 3))
    el.append(Paragraph(
        "Y un filtro que muchos no tienen: <b>veto de fin de semana</b>. "
        "Liquidez delgada y spreads anchos no son edge, son casino. El "
        "sistema lo respeta.", st_body))

    # ---------------- 5 · Qué recibes ----------------
    el += section(5, "Qué recibes en el VIP")
    el.append(box(
        RULE + "\n"
        "  ◆ FQ · VIP\n"
        + RULE + "\n"
        "  ▪ Entry, SL y TPs exactos\n"
        "  ▪ SL anclado a estructura\n"
        "  ▪ Análisis táctico on-demand\n"
        "  ▪ Resultados verificables\n"
        + RULE
    ))
    el.append(Spacer(1, 7))
    el += bullets([
        "<b>Señales en vivo</b> de SOL/USDT con niveles listos para ejecutar. Cero ambigüedad.",
        "<b>Análisis a pedido.</b> Pides una lectura del mercado o de niveles cuando la necesitas.",
        "<b>Seguimiento de cada operación</b> hasta su cierre, con el resultado en R.",
        "<b>Track record abierto.</b> Win rate, expectancy y profit factor que puedes comprobar.",
    ])

    el.append(PageBreak())

    # ---------------- 6 · Por qué es distinto ----------------
    el += section(6, "Por qué FQ es distinto")
    data = [
        [Paragraph("<b>La mayoría de canales</b>", st_small),
         Paragraph("<b>FQ</b>", st_small)],
        ["Decenas de alertas al día", "1–3 señales selectivas, y muchos días ninguna"],
        ["“Compra/vende” sin niveles", "Entry, stop y objetivos exactos"],
        ["Mueven el stop con la emoción", "Stop anclado a estructura, inmutable"],
        ["Solo muestran los aciertos", "Resultados completos y verificables"],
        ["Operan fines de semana", "Veto de fin de semana por diseño"],
    ]
    # envolver celdas de cuerpo en Paragraph para wrapping
    body_cell = S("cell", fontName="FQSans", fontSize=9.5, leading=13, textColor=INK)
    fq_cell = S("cellfq", fontName="FQSans-Bold", fontSize=9.5, leading=13, textColor=ACCENT)
    for i in range(1, len(data)):
        data[i][0] = Paragraph(data[i][0], body_cell)
        data[i][1] = Paragraph(data[i][1], fq_cell)
    tbl = Table(data, colWidths=[72 * mm, 78 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), INK),
        ("TEXTCOLOR",    (0, 0), (-1, 0), PAPER),
        ("FONTNAME",     (0, 0), (-1, 0), "FQSans-Bold"),
        ("LINEBELOW",    (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PAPER, BOXBG]),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING",   (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
    ]))
    el.append(tbl)
    el.append(Spacer(1, 6))
    el.append(Paragraph("El sistema no opera con miedo ni con codicia. Solo "
                        "con datos.", st_quote))

    # ---------------- 7 · Resultados ----------------
    el += section(7, "Resultados verificables")
    el.append(Paragraph(
        "FQ no pide fe. El track record se publica desde su propio registro "
        "de operaciones, en ventanas de 30 y 90 días e histórico total:", st_body))
    el += bullets([
        "<b>Win rate</b> — porcentaje de cierres ganadores.",
        "<b>Expectancy</b> — cuánto deja, en promedio, cada señal (en R).",
        "<b>Profit factor</b> — cuánto gana por cada unidad que arriesga.",
    ])
    el.append(Spacer(1, 3))
    el.append(Paragraph(
        "Cuando una operación corre hasta su tercer objetivo, se anuncia. "
        "Cuando una semana cierra, se publican los números. En verde y en "
        "rojo.", st_body))
    el.append(Paragraph("Pasados resultados no garantizan futuros.", st_quote))

    el.append(PageBreak())

    # ---------------- 8 · Planes ----------------
    el += section(8, "Planes")
    el.append(box(
        RULE + "\n"
        "  ◆ FQ · VIP\n"
        + RULE + "\n"
        "  ▸ Mensual      $49 USD\n"
        "  ▸ Trimestral   $129      -12%\n"
        "  ▸ Anual        $449      -24%\n"
        "  ▸ Lifetime     $1,200\n"
        + RULE + "\n"
        "  Tarjeta (Stripe) o USDT (TRC20)."
    ))
    el.append(Spacer(1, 7))
    el.append(Paragraph("Y para probar sin compromiso: <b>trial de 7 días</b>.",
                        st_lead))

    # ---------------- 9 · Cómo empezar ----------------
    el += section(9, "Cómo empezar")
    el += bullets([
        "Entra al bot público y mira los reportes y resultados en abierto.",
        "Pide tu acceso con <b>/unirme</b>.",
        "Paga con tarjeta (<b>/stripe</b>) o USDT (<b>/crypto</b>), o canjea un código con <b>/codigo XXXX</b>.",
        "Recibe las señales en vivo desde el primer día.",
    ])
    el.append(Spacer(1, 4))
    el.append(box(
        RULE + "\n"
        "  ◆ FQ\n"
        + RULE + "\n"
        "  ▸ /unirme      Activar VIP\n"
        "  ▸ /precio      Tarifas\n"
        "  ▸ /resultados  Track record\n"
        "  ▸ /info        Sobre el sistema\n"
        + RULE
    ))

    # ---------------- 10 · Riesgo ----------------
    el += section(10, "Aviso de riesgo")
    el.append(Paragraph(
        "El trading de criptomonedas con apalancamiento conlleva alto riesgo "
        "y puedes perder todo tu capital. FQ no es asesoría financiera; las "
        "señales son informativas y operas bajo tu responsabilidad. Opera "
        "solo capital que puedas permitirte perder.", st_body))
    el.append(Spacer(1, 14))
    el.append(_hr())
    el.append(Spacer(1, 6))
    el.append(Paragraph("FQ · Señales SOL/USDT con disciplina sistemática.",
                        st_small))

    doc.build(el)
    return out_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "PRESENTACION.pdf"
    path = build(out)
    print("PDF generado: {} ({} bytes)".format(path, os.path.getsize(path)))
