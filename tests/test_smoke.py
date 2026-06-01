# -*- coding: utf-8 -*-
"""Smoke: los modulos puros (sin ccxt/red) importan y exponen lo esperado."""
import importlib

import pytest

PURE_MODULES = [
    "branding", "legal", "ledger_stats", "fq_logging",
    "vip_format", "public_format", "public_content_generator",
    "public_handlers", "public_outcome_announcer",
    "ops.heartbeat", "ops.backup_ledger",
]


@pytest.mark.parametrize("mod", PURE_MODULES)
def test_import(mod):
    importlib.import_module(mod)


def test_branding_constants():
    import branding
    assert branding.PRODUCT == "FQ"
    assert branding.PAIR == "SOL/USDT"
    assert "garantizan" in branding.DISCLAIMER


def test_legal_three_documents():
    import legal
    for fn in (legal.build_disclaimer, legal.build_terms, legal.build_privacy):
        assert len(fn()) > 50


def test_fq_logging_setup_idempotent():
    import logging
    import fq_logging
    fq_logging.setup()
    fq_logging.setup()
    # un solo handler tras dos setups
    assert len(logging.getLogger().handlers) == 1


def test_json_formatter_emits_json(monkeypatch):
    import json
    import logging
    import fq_logging
    monkeypatch.setenv("FQ_JSON_LOGS", "1")
    fq_logging.setup()
    rec = logging.LogRecord("m", logging.INFO, __file__, 1, "hola", None, None)
    line = fq_logging.JsonFormatter().format(rec)
    parsed = json.loads(line)
    assert parsed["event"] == "hola"
    assert parsed["level"] == "INFO"
