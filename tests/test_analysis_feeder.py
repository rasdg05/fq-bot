# -*- coding: utf-8 -*-
"""analysis_feeder: capa de observación oro/Nasdaq (no señales). Se prueba la
lógica de parseo/forma SIN red (mockeando _get) — el orden de las velas de cada
venue difiere (OKX newest-first, MEXC cronológico) y el percentil de funding se
calcula de la historia. La corrida real contra OKX/MEXC se valida aparte."""
import json

import pytest

import tools.analysis_feeder as af


def _okx_candles(n=300, base=4000.0):
    # OKX: newest-first, cada fila [ts,o,h,l,c,vol,...]
    rows = []
    for i in range(n):
        c = base + i * 0.5
        rows.append([str(i), str(c), str(c), str(c), str(c), "1"])
    return {"code": "0", "data": list(reversed(rows))}


def test_okx_instrument_forma_y_orden(monkeypatch):
    inst = {"key": "XAU", "venue": "okx", "display": "Oro · XAU",
            "okx": "XAU-USDT-SWAP", "fund_sym": "XAU/USDT"}

    def fake_get(url, timeout=12):
        return _okx_candles()

    monkeypatch.setattr(af, "_get", fake_get)
    # funding vía motor_paper: forzar un valor conocido, sin red
    import types
    fake_mp = types.SimpleNamespace(
        kl_regime_live=lambda closes: {"low": True, "irrev": 0.10},
        funding_pctl_live=lambda sym: (0.0001, 0.42))
    monkeypatch.setitem(__import__("sys").modules, "motor_paper", fake_mp)

    row = af.build_one(inst)
    assert row["analysis"] is True and row["display"] == "Oro · XAU"
    # el último close (cronológico) es el mayor -> el precio es el más reciente
    assert row["price"] == pytest.approx(4000.0 + 299 * 0.5)
    assert len(row["spark"]) == af.SPARK_N
    assert row["spark"][-1] == row["price"]         # spark termina en el precio actual
    assert row["irrev"] == 0.10 and row["kl_low"] is True
    assert row["funding_pctl"] == 0.42


def test_mexc_instrument_funding_percentil(monkeypatch):
    inst = {"key": "NAS100", "venue": "mexc", "display": "Nasdaq 100", "mexc": "NAS100_USDT"}
    closes = [29000.0 + i for i in range(300)]

    def fake_get(url, timeout=12):
        if "/kline/" in url:
            return {"data": {"close": closes, "time": list(range(len(closes)))}}
        if "/ticker" in url:
            return {"data": {"riseFallRate": 0.0123}}
        if "funding_rate/history" in url:
            # historia (>=10 para que el feeder calcule percentil): con rate=-0.0001,
            # 5 de 10 valores son <= -0.0001 -> percentil 0.5
            vals = [-0.0005, -0.0004, -0.0003, -0.0002, -0.0001,
                    0.0001, 0.0002, 0.0003, 0.0004, 0.0005]
            return {"data": {"resultList": [{"fundingRate": v} for v in vals]}}
        if "funding_rate/" in url:
            return {"data": {"fundingRate": -0.0001}}
        return {}

    monkeypatch.setattr(af, "_get", fake_get)
    import types
    monkeypatch.setitem(__import__("sys").modules, "motor_paper",
                        types.SimpleNamespace(kl_regime_live=lambda c: {"low": False, "irrev": 0.5}))

    row = af.build_one(inst)
    assert row["price"] == closes[-1]
    assert row["chg_24h"] == pytest.approx(1.23)     # riseFallRate * 100
    assert row["funding_rate"] == pytest.approx(-0.0001)
    # 5 de 10 valores <= -0.0001 -> percentil 0.5
    assert row["funding_pctl"] == pytest.approx(0.5)
    assert row["irrev"] == 0.5 and row["kl_low"] is False


def test_build_one_venue_falla_no_revienta(monkeypatch):
    def boom(url, timeout=12):
        raise RuntimeError("red caída")
    monkeypatch.setattr(af, "_get", boom)
    assert af.build_one({"key": "XAU", "venue": "okx", "okx": "X", "fund_sym": "X/USDT",
                         "display": "Oro"}) is None


def test_run_once_escribe_atomico(tmp_path, monkeypatch):
    monkeypatch.setattr(af, "OUT", str(tmp_path / "extra.json"))
    monkeypatch.setattr(af, "INSTRUMENTS", [
        {"key": "XAU", "venue": "okx", "display": "Oro", "okx": "X", "fund_sym": "X/USDT"}])
    monkeypatch.setattr(af, "build_one", lambda inst: {"analysis": True, "price": 1.0})
    syms = af.run_once()
    assert "XAU" in syms
    d = json.load(open(str(tmp_path / "extra.json")))
    assert d["symbols"]["XAU"]["price"] == 1.0
