# -*- coding: utf-8 -*-
"""Multi-simbolo (2026-07-20): los prompts que Claude recibe para /analisis y
alias mostraban 'SOL/USDT' hardcodeado en el header, sin importar el par
realmente analizado -- un residuo del /analisis SOL-only que habria
confundido a Claude (y a quien leyera su lectura) al pedir /analisis BTC o
/analisis ETH. Ahora leen 'pair' del snapshot, con SOL/USDT de fallback para
no romper snapshots viejos que no lo incluyan."""
import claude_integration as ci


def test_general_prompt_usa_pair_del_snapshot():
    out = ci.build_general_prompt({"pair": "BTC/USDT"})
    assert "LECTURA TACTICA BTC/USDT" in out
    assert "SOL/USDT" not in out


def test_pspace_prompt_usa_pair_del_snapshot():
    out = ci.build_pspace_prompt({"pair": "ETH/USDT"})
    assert "ORDER BOOK ETH/USDT" in out
    assert "SOL/USDT" not in out


def test_niveles_prompt_usa_pair_del_snapshot():
    out = ci.build_niveles_prompt({"pair": "BTC/USDT"})
    assert "ENTRADA BTC/USDT" in out
    assert "SOL/USDT" not in out


def test_analisis_vip_prompt_usa_pair_del_snapshot():
    out = ci.build_analisis_vip_prompt({"pair": "ETH/USDT"})
    assert "ANALISIS ETH/USDT" in out
    assert "SOL/USDT" not in out


def test_prompts_sin_pair_caen_a_sol_usdt():
    """Snapshots viejos (sin key 'pair') no deben romper -- fallback SOL/USDT,
    el comportamiento historico."""
    assert "LECTURA TACTICA SOL/USDT" in ci.build_general_prompt({})
    assert "ORDER BOOK SOL/USDT" in ci.build_pspace_prompt({})
    assert "ENTRADA SOL/USDT" in ci.build_niveles_prompt({})
    assert "ANALISIS SOL/USDT" in ci.build_analisis_vip_prompt({})
