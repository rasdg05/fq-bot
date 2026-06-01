# -*- coding: utf-8 -*-
"""
Identidad unica de marca FQ. Una sola fuente de verdad para nombre,
tagline, glyphs, hashtags y separadores visibles al cliente.

Ningun modulo de cara al cliente debe hardcodear versiones, nombres
de modelos, jerga interna ni firmas tecnicas. Importa de aqui.
"""

PRODUCT      = "FQ"
PAIR         = "SOL/USDT"
TAGLINE      = "Senales SOL/USDT con disciplina sistematica."
PROMISE      = "Cuando hay edge, dispara. Cuando no, calla."
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
