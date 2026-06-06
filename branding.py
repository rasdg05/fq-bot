# -*- coding: utf-8 -*-
"""
Identidad unica de marca FQ. Una sola fuente de verdad para nombre,
tagline, glyphs, hashtags y separadores visibles al cliente.

Ningun modulo de cara al cliente debe hardcodear versiones, nombres
de modelos, jerga interna ni firmas tecnicas. Importa de aqui.
"""

PRODUCT      = "FQ"
PAIR         = "SOL/USDT"
SCUDERIA     = "Scuderia"
TAGLINE      = "Senales SOL/USDT con precision de pista."
PROMISE      = "Cuando hay edge, acelera. Cuando no, frena."
DISCLAIMER   = "Pasados resultados no garantizan futuros."

GLYPHS = {
    "rule":       "━" * 30,
    "title":      "◆",
    "event":      "▰",
    "bullet_act": "▸",
    "bullet_chk": "▪",
    "long":       "▴",
    "short":      "▾",
}

RULE = GLYPHS["rule"]

HASHTAGS_SIGNAL = "#FQ #SOLUSDT"

# ============================================================
# DISENO "FERRARI" - acabado premium para onboarding y documentacion.
# Lineas limpias, acento de carrera (bandera a cuadros) y rojo Rosso.
# Pensado SOLO para las vistas de bienvenida/ayuda/info: las senales
# conservan su propio formato. Importa lux_header/lux_block/lux_footer.
# ============================================================
FERRARI = {
    "flag":  "\U0001F3C1",  # bandera a cuadros - meta/carrera
    "rosso": "\U0001F534",  # rojo Ferrari - acceso activo
    "spark": "⚡",      # chispa - velocidad
    "horse": "\U0001F40E",  # cavallino rampante
}

LUX_RULE = "━" * 26

def lux_header(title, subtitle=None):
    """Encabezado premium con marco de carrera para documentacion.

    Render:
        🏁 ━━━━━━━━━━━━━━━━━━━━━━━━━━
           ◆ <title>
           <subtitle>
        ━━━━━━━━━━━━━━━━━━━━━━━━━━ 🏁
    """
    flag = FERRARI["flag"]
    lines = [
        "{} {}".format(flag, LUX_RULE),
        "   {} {}".format(GLYPHS["title"], title),
    ]
    if subtitle:
        lines.append("   {}".format(subtitle))
    lines.append("{} {}".format(LUX_RULE, flag))
    return "\n".join(lines)

def lux_block(*lines):
    """Cuerpo del panel: indentado uniforme, listo para encajar entre
    header y footer. Las cadenas vacias quedan como saltos de linea."""
    return "\n".join(("  " + ln) if ln else "" for ln in lines)

def lux_item(label, value=""):
    """Linea de menu/atributo con bullet de accion."""
    if value:
        return "   {} {:<12} {}".format(GLYPHS["bullet_act"], label, value)
    return "   {} {}".format(GLYPHS["bullet_act"], label)

def lux_check(text):
    """Linea de feature con bullet de checklist."""
    return "   {} {}".format(GLYPHS["bullet_chk"], text)

def lux_footer(*lines):
    """Pie premium: regla + lineas de accion con bullet."""
    out = [LUX_RULE]
    for ln in lines:
        out.append("   {} {}".format(GLYPHS["bullet_act"], ln))
    return "\n".join(out)

def title(text):
    """Render: ◆ <text>"""
    return "{} {}".format(GLYPHS["title"], text)

def header(text):
    """Bloque encabezado: rule / titulo / rule"""
    return "\n".join([RULE, "  " + title(text), RULE])

def footer_cta(*lines):
    """Cierra un bloque con un rule + lineas de CTA con bullet."""
    out = [RULE]
    for ln in lines:
        out.append("  {} {}".format(GLYPHS["bullet_act"], ln))
    return "\n".join(out)
