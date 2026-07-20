# -*- coding: utf-8 -*-
"""Fix (2026-07-20, RasDG): "por que la lectura tactica se duplica y sale en
dos mensajes". cmd_lectura ya arma su propia lectura de Claude embebida
(mctx.snapshot_for_general adentro de la funcion); el bloque tier-aware de
/analisis y /lectura ADEMAS disparaba claude_followup_general por separado
-- dos llamadas a Claude, dos mensajes con la misma lectura en formato
distinto. Solo pasaba para admin (el VIP reutiliza analisis_ctx via
claude_followup_analisis_vip, nunca duplico).

command_listener no tiene arnes de test (nada en tests/ lo ejercita
directamente); esto sella el fix por inspeccion de fuente, igual que
test_lectura_tier_aware.py."""
import inspect

import fq_bot_v3_2 as b


def test_admin_no_dispara_followup_duplicado():
    src = inspect.getsource(b.command_listener)
    idx = src.index('if tier_loc == "admin":')
    block = src[idx: idx + 400]
    assert "fu_fn = claude_followup_general" not in block, (
        "El admin no debe disparar claude_followup_general -- cmd_lectura ya "
        "entrega su propia lectura tactica embebida en el mismo mensaje."
    )
    assert "fu_fn = None" in src[max(0, idx - 400):idx], (
        "fu_fn debe arrancar en None antes de la rama admin (sin followup)."
    )


def test_vip_sigue_disparando_su_followup_curado():
    src = inspect.getsource(b.command_listener)
    assert "fu_fn = claude_followup_analisis_vip" in src
