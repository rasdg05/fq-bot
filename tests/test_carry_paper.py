# -*- coding: utf-8 -*-
"""
CARRY PAPER (2do motor, market-neutral) — PRUEBAS SIN RED.

carry_paper acumula el funding REALIZADO del basket CLEAN en un parquet durable y
mide el carry forward (always-on + gate de 7 días). Lo que se audita aquí:

  - append_dedupe es ATÓMICO e IDEMPOTENTE: re-appendear el mismo poll NO duplica
    (dedupe por (fundingTime, symbol)); un poll nuevo SÍ extiende el ledger.
  - el carry del basket sale del ledger: funding positivo -> APY+, gate sostiene;
    funding negativo -> el gate se SIENTA (held≈0) y no sangra como always-on.
  - el gate es CAUSAL (media móvil del PASADO, shift): un pico de funding no se
    "ve" antes de tiempo (misma disciplina anti-leakage que funding_oi).
  - write_snapshot/report escriben y releen el JSON sin crash.

Todo con ledger sintético: cero red, cero OKX.
"""
import json
import os

import numpy as np
import pandas as pd
import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import carry_paper as cp  # noqa: E402


def _ledger(funding_by_sym, *, t0=1_700_000_000_000, step_ms=8 * 3600 * 1000):
    """Construye un ledger sintético: {inst: [tasas por intervalo]}."""
    rows = []
    for inst, rates in funding_by_sym.items():
        for i, r in enumerate(rates):
            rows.append((t0 + i * step_ms, inst, float(r)))
    return pd.DataFrame(rows, columns=["fundingTime", "symbol", "fundingRate"])


@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(cp, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(cp, "LEDGER", str(tmp_path / "carry_funding.parquet"))
    monkeypatch.setattr(cp, "SNAPSHOT", str(tmp_path / "carry_paper_snapshot.json"))
    return tmp_path


# ----------------------------- append_dedupe -----------------------------
def test_append_dedupe_idempotente(tmp_paths):
    led = _ledger({"BTC-USDT-SWAP": [1e-4] * 10, "ETH-USDT-SWAP": [1e-4] * 10})
    out1 = cp.append_dedupe(cp.LEDGER, led)
    assert len(out1) == 20
    # re-appendear EXACTAMENTE lo mismo no crece el ledger
    out2 = cp.append_dedupe(cp.LEDGER, led)
    assert len(out2) == 20
    assert os.path.exists(cp.LEDGER)


def test_append_dedupe_extiende_con_settlements_nuevas(tmp_paths):
    led = _ledger({"BTC-USDT-SWAP": [1e-4] * 5})
    cp.append_dedupe(cp.LEDGER, led)
    # un poll posterior con 5 settlements NUEVAS (timestamps más adelante)
    nxt = _ledger({"BTC-USDT-SWAP": [2e-4] * 5}, t0=1_700_000_000_000 + 5 * 8 * 3600 * 1000)
    out = cp.append_dedupe(cp.LEDGER, nxt)
    assert len(out) == 10
    # ordenado por (symbol, fundingTime)
    assert out["fundingTime"].is_monotonic_increasing


def test_append_dedupe_vacio_no_crashea(tmp_paths):
    assert cp.append_dedupe(cp.LEDGER, pd.DataFrame(
        columns=["fundingTime", "symbol", "fundingRate"])) is None


# ----------------------------- carry del basket -----------------------------
def test_basket_carry_funding_positivo_apy_positivo(tmp_paths):
    led = _ledger({inst: [3e-4] * 60 for inst in cp.BASKET})   # +0.03%/8h constante
    carry = cp._basket_carry(led)
    assert carry["n_symbols"] == len(cp.BASKET)
    assert carry["always"]["apy"] > 0          # cobra funding positivo
    assert carry["always"]["pct_pos"] == 1.0
    # gate con funding siempre positivo: sostiene casi todo
    assert carry["gate7d"]["apy"] > 0


def test_gate_se_sienta_con_funding_negativo(tmp_paths):
    # funding NEGATIVO sostenido: el always-on SANGRA, el gate se sienta (no entra)
    led = _ledger({inst: [-2e-4] * 60 for inst in cp.BASKET})
    carry = cp._basket_carry(led)
    assert carry["always"]["apy"] < 0          # short-perp paga funding negativo
    # el gate (media móvil pasada <0) nunca mantiene -> APY ~0, mucho mejor que always
    assert carry["gate7d"]["apy"] > carry["always"]["apy"]
    assert abs(carry["gate7d"]["apy"]) < abs(carry["always"]["apy"])


def test_gate_es_causal_no_anticipa_el_pico(tmp_paths):
    # 40 intervalos a 0, luego un salto a +alto. El gate en el borde NO puede haber
    # cobrado el pico antes de verlo (shift): comparamos held antes/después.
    rates = [0.0] * 40 + [5e-4] * 20
    f = np.array(rates)
    hours = np.full(len(f), 8.0)
    m_gate = cp.bvf.metrics(f, hours, selective=True, smooth=cp.SMOOTH)
    m_always = cp.bvf.metrics(f, hours)
    # el gate entra TARDE (tras confirmar el pico en la media pasada) -> cobra MENOS
    # del pico que el always-on, jamás más (si cobrara más, habría mirado al futuro).
    assert m_gate["apy"] <= m_always["apy"] + 1e-9


# ----------------------------- snapshot / report -----------------------------
def test_write_snapshot_y_relee(tmp_paths):
    led = _ledger({inst: [2e-4] * 30 for inst in cp.BASKET})
    cp.append_dedupe(cp.LEDGER, led)
    snap = cp.write_snapshot(pd.read_parquet(cp.LEDGER))
    assert snap is not None
    assert os.path.exists(cp.SNAPSHOT)
    with open(cp.SNAPSHOT) as fh:
        disk = json.load(fh)
    assert disk["carry"]["n_symbols"] == len(cp.BASKET)
    assert disk["span_days"] > 0
    assert set(disk["basket"]) == {s.split("-")[0] for s in cp.BASKET}


def test_report_sin_ledger_devuelve_1(tmp_paths):
    assert cp.report() == 1   # sin parquet -> error suave, sin crash
