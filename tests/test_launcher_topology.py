# -*- coding: utf-8 -*-
"""Topologia de UN solo bot (jun-2026): el proceso 'public' solo se lanza (y
solo se vigila su latido) cuando TELEGRAM_TOKEN_PUBLIC trae un token PROPIO,
distinto del VIP. Sin el, launcher y watchdog lo dejan fuera a proposito —
nada de procesos parqueados ni alertas eternas de 'sin latido'."""
import launcher
from ops import maintenance


def test_public_deshabilitado_sin_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN_PUBLIC", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "vip-tok")
    assert launcher._public_enabled() is False
    assert [n for n, *_ in launcher._bots()] == ["vip", "maintenance"]


def test_public_deshabilitado_con_token_duplicado(monkeypatch):
    # el operador pego el token del VIP en TELEGRAM_TOKEN_PUBLIC
    monkeypatch.setenv("TELEGRAM_TOKEN_PUBLIC", "mismo-tok")
    monkeypatch.setenv("TELEGRAM_TOKEN", "mismo-tok")
    assert launcher._public_enabled() is False
    assert [n for n, *_ in launcher._bots()] == ["vip", "maintenance"]


def test_public_corre_con_token_propio(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN_PUBLIC", "pub-tok")
    monkeypatch.setenv("TELEGRAM_TOKEN", "vip-tok")
    assert launcher._public_enabled() is True
    assert [n for n, *_ in launcher._bots()] == ["vip", "public", "maintenance"]


def test_carry_paper_off_por_defecto(monkeypatch):
    # 2do motor (market-neutral): NO se lanza sin FQ_CARRY_PAPER=1
    monkeypatch.delenv("TELEGRAM_TOKEN_PUBLIC", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "vip-tok")
    monkeypatch.delenv("FQ_CARRY_PAPER", raising=False)
    assert launcher._carry_paper_enabled() is False
    assert "carry-paper" not in [n for n, *_ in launcher._bots()]


def test_carry_paper_on_es_no_critico(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN_PUBLIC", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "vip-tok")
    monkeypatch.setenv("FQ_CARRY_PAPER", "1")
    assert launcher._carry_paper_enabled() is True
    bots = launcher._bots()
    assert [n for n, *_ in bots] == ["vip", "maintenance", "carry-paper"]
    # un bug del colector JAMAS debe tirar el bot VIP -> critical=False
    crit = {n: c for n, _cmd, c in bots}
    assert crit["carry-paper"] is False
    assert crit["vip"] is True


def test_agg_oi_off_por_defecto_y_no_critico(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN_PUBLIC", raising=False)
    monkeypatch.setenv("TELEGRAM_TOKEN", "vip-tok")
    monkeypatch.delenv("FQ_AGG_OI_COLLECT", raising=False)
    assert launcher._agg_oi_collect_enabled() is False
    assert "agg-oi" not in [n for n, *_ in launcher._bots()]
    monkeypatch.setenv("FQ_AGG_OI_COLLECT", "1")
    bots = launcher._bots()
    assert "agg-oi" in [n for n, *_ in bots]
    crit = {n: c for n, _cmd, c in bots}
    assert crit["agg-oi"] is False and crit["vip"] is True   # un bug del colector no tira el VIP


def test_watchdog_usa_la_misma_regla(monkeypatch):
    # maintenance._public_enabled comparte la regla (los umbrales del modulo
    # se fijan al importar; aqui validamos la regla viva).
    monkeypatch.setenv("TELEGRAM_TOKEN_PUBLIC", "pub-tok")
    monkeypatch.setenv("TELEGRAM_TOKEN", "vip-tok")
    assert maintenance._public_enabled() is True
    monkeypatch.setenv("TELEGRAM_TOKEN_PUBLIC", "vip-tok")
    assert maintenance._public_enabled() is False
    monkeypatch.delenv("TELEGRAM_TOKEN_PUBLIC", raising=False)
    assert maintenance._public_enabled() is False
    # 'vip' SIEMPRE vigilado, pase lo que pase con el publico
    assert "vip" in maintenance.STALE_THRESHOLDS
