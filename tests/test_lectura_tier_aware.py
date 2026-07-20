# -*- coding: utf-8 -*-
"""Fix (2026-07-20, RasDG): "/lectura no es tier-aware".

Hallazgo real al investigar: /lectura no solo evitaba la vista curada de
VIP -- estaba completamente SIN GATE. No aparecia en PREMIUM_COMMANDS ni en
ADMIN_ONLY dentro de command_listener, asi que CUALQUIER usuario (sin VIP,
sin trial) podia escribir /lectura y recibir el dump tecnico completo
(multi-TF, niveles exactos, P_master) gratis -- el unico comando visible en
BotFather para la familia /analisis se saltaba el paywall entero.

command_listener es un loop de polling sin arnes de test (nada en tests/ lo
ejercita directamente), asi que esto sella el fix por INSPECCION DE FUENTE:
confirma que /lectura quedo en el set de acceso premium y en el mismo bloque
tier-aware que /analisis. Es una guarda de regresion legible, no un
reemplazo de un test de comportamiento real."""
import inspect

import fq_bot_v3_2 as b


def _command_listener_source():
    return inspect.getsource(b.command_listener)


def test_lectura_requiere_acceso_premium():
    src = _command_listener_source()
    # Ubica el bloque PREMIUM_COMMANDS y confirma que /lectura esta declarado ahi.
    idx = src.index("PREMIUM_COMMANDS = {")
    block = src[idx: src.index("}", idx)]
    assert '"/lectura"' in block, (
        "/lectura debe estar en PREMIUM_COMMANDS -- sin esto, cualquier "
        "usuario sin VIP puede pedirlo y recibir el analisis completo gratis."
    )


def test_lectura_comparte_el_bloque_tier_aware_de_analisis():
    src = _command_listener_source()
    idx = src.index('cmd_name in ("/analisis"')
    # El tuple de membership abre en el primer parentesis tras el indice hallado
    close = src.index(":", idx)
    tuple_src = src[idx:close]
    assert '"/lectura"' in tuple_src, (
        "/lectura debe entrar al mismo bloque tier-aware que /analisis "
        "(admin=cmd_lectura completo, VIP=cmd_analisis_vip curado) -- si no, "
        "un VIP que toque /lectura en su menu de BotFather recibe el dump "
        "tecnico de admin en vez de la vista premium."
    )


def test_lectura_no_esta_en_admin_only():
    """Verifica que no se haya 'arreglado' el gap moviendo /lectura a
    ADMIN_ONLY por error (eso bloquearia a los VIP tambien, no es el fix)."""
    src = _command_listener_source()
    idx = src.index("ADMIN_ONLY = {")
    block = src[idx: src.index("}", idx)]
    assert '"/lectura"' not in block
