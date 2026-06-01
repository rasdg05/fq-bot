# -*- coding: utf-8 -*-
"""
Avisos legales de FQ. Riesgo, terminos y privacidad.

Texto plano, una pantalla cada uno. Sin promesas de rentabilidad,
sin garantias. Lo que separa un producto serio de un grupo de senales.
"""
from branding import PRODUCT, RULE, GLYPHS

_ACT = GLYPHS["bullet_act"]
_CHK = GLYPHS["bullet_chk"]


def build_disclaimer():
    """Aviso de riesgo. Se muestra una vez al primer contacto y desde /legal."""
    return "\n".join([
        RULE,
        "  ◆ {} · Aviso de riesgo".format(PRODUCT),
        RULE,
        "  El trading de criptomonedas con",
        "  apalancamiento conlleva alto riesgo.",
        "  Puedes perder todo tu capital.",
        "",
        "  {} {} no es asesoria financiera.".format(_CHK, PRODUCT),
        "  {} Las senales son informativas.".format(_CHK),
        "  {} Tu operas bajo tu responsabilidad.".format(_CHK),
        "  {} Pasados resultados no garantizan".format(_CHK),
        "    futuros.",
        "",
        "  Opera solo capital que puedas",
        "  permitirte perder.",
        RULE,
        "  {} Terminos y privacidad   /legal".format(_ACT),
    ])


def build_terms():
    """Terminos de servicio. Compacto."""
    return "\n".join([
        RULE,
        "  ◆ {} · Terminos".format(PRODUCT),
        RULE,
        "  {} El acceso VIP es personal e".format(_CHK),
        "    intransferible.",
        "  {} Las senales no constituyen una".format(_CHK),
        "    recomendacion de inversion.",
        "  {} No se garantiza disponibilidad".format(_CHK),
        "    ininterrumpida del servicio.",
        "  {} El reembolso se evalua caso por".format(_CHK),
        "    caso dentro de las primeras 48h.",
        "  {} El uso continuado implica la".format(_CHK),
        "    aceptacion de estos terminos.",
        RULE,
    ])


def build_privacy():
    """Politica de privacidad. Que datos se guardan y por que."""
    return "\n".join([
        RULE,
        "  ◆ {} · Privacidad".format(PRODUCT),
        RULE,
        "  Datos que guardamos:",
        "  {} Tu identificador de Telegram.".format(_CHK),
        "  {} Tu estado de suscripcion.".format(_CHK),
        "  {} Tu historial de pagos.".format(_CHK),
        "",
        "  No vendemos ni compartimos tus",
        "  datos con terceros. Se usan solo",
        "  para operar tu acceso al servicio.",
        "",
        "  Puedes solicitar la baja y borrado",
        "  escribiendo /desuscribir.",
        RULE,
    ])


def build_legal_menu():
    """Menu /legal: las tres piezas accesibles."""
    return "\n".join([
        RULE,
        "  ◆ {} · Legal".format(PRODUCT),
        RULE,
        "  {} Aviso de riesgo".format(_CHK),
        "  {} Terminos de servicio".format(_CHK),
        "  {} Privacidad".format(_CHK),
        "",
        build_disclaimer(),
        "",
        build_terms(),
        "",
        build_privacy(),
    ])
