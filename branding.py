# -*- coding: utf-8 -*-
"""
Identidad unica de marca FQ. Una sola fuente de verdad para nombre, voz,
glifos y separadores visibles al cliente.

Direccion de diseno (era "Terminal"): mesa de liquidez institucional.
Limpio, sobrio, sin emoji, sin jerga de motor. Separadores hairline, un
acento vertical y tipografia con aire. Debe leerse como una terminal
financiera de grado institucional, no como un grupo de senales.

Ningun modulo de cara al cliente debe hardcodear versiones, nombres de
modelos ni jerga interna. Importa de aqui.
"""

PRODUCT      = "FQ"
PAIR         = "SOL/USDT"          # default/fallback del símbolo primario (NO usar como display fijo)
MARKETS      = "perpetuos cripto"  # descriptor MULTI-SÍMBOLO para texto de cara al cliente (escala con los símbolos)
DESK         = "Mesa de liquidez"
TAGLINE      = "Mesa de liquidez institucional · " + MARKETS
PROMISE      = "Cuando hay ventaja, ejecuta. Cuando no, espera."
DISCLAIMER   = "Rendimientos pasados no garantizan resultados futuros."

# Alias de transicion: modulos heredados aun importan SCUDERIA como
# descriptor de marca. Ahora resuelve al descriptor institucional.
SCUDERIA     = DESK

# ============================================================
# SISTEMA DE GLIFOS - hairline, sobrio, sin emoji.
#   rule        separador fino (hairline)
#   title       acento de seccion / wordmark
#   event       subseccion
#   bullet_act  accion / comando (CTA)
#   bullet_chk  spec / checklist
#   long/short  direccion
# ============================================================
GLYPHS = {
    "rule":       "─" * 30,
    "title":      "│",
    "event":      "│",
    "bullet_act": "›",
    "bullet_chk": "·",
    "long":       "▲",
    "short":      "▼",
    "premium":    "◆",
}

RULE = GLYPHS["rule"]

HASHTAGS_SIGNAL = "#FQ #SOLUSDT"

# ============================================================
# TARJETA PREMIUM (lux_*) - encabezado/pie institucional para
# onboarding, ayuda y documentacion. Hairline + acento vertical,
# sin emoji ni acento de carrera. Las senales conservan su formato.
# Importa lux_header/lux_block/lux_footer.
# ============================================================
LUX_RULE = "─" * 28

def lux_header(title, subtitle=None):
    """Encabezado tipo tarjeta institucional.

    Render:
        ────────────────────────────
          │ <title>
            <subtitle>
        ────────────────────────────
    """
    lines = [
        LUX_RULE,
        "  {} {}".format(GLYPHS["title"], title),
    ]
    if subtitle:
        lines.append("    {}".format(subtitle))
    lines.append(LUX_RULE)
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
    """Render: │ <text>"""
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
