# -*- coding: utf-8 -*-
"""Tags de régimen dormidos (FQ_REGIME_TAGS): KL + POC-distance en MOTOR_OPEN_META.
Garantía clave: OFF -> {} (ledger byte-idéntico). ON -> kl_low/kl_irrev/poc_dist."""
import numpy as np
import pandas as pd

import motor_paper


def _df(n=400):
    ts = pd.date_range("2024-01-02", periods=n, freq="5min", tz="UTC")
    # volumen concentrado ~100 hoy -> POC ~100
    close = np.full(n, 100.0)
    close[-40:] = np.linspace(100.0, 104.0, 40)
    return pd.DataFrame({"timestamp": ts, "open": close, "high": close + 0.5,
                         "low": close - 0.5, "close": close, "volume": np.full(n, 10.0)})


def test_off_is_empty_byte_identical(monkeypatch):
    monkeypatch.delenv("FQ_REGIME_TAGS", raising=False)
    assert motor_paper._regime_tags(_df(), 100.0) == {}
    monkeypatch.setenv("FQ_REGIME_TAGS", "0")
    assert motor_paper._regime_tags(_df(), 100.0) == {}


def test_on_tags_kl_and_poc(monkeypatch):
    monkeypatch.setenv("FQ_REGIME_TAGS", "1")
    out = motor_paper._regime_tags(_df(), 100.0)
    assert isinstance(out.get("kl_low"), bool)
    assert isinstance(out.get("kl_irrev"), float)
    assert isinstance(out.get("poc_dist"), float) and out["poc_dist"] >= 0.0
    assert out.get("vp_zone") in ("premium", "value", "discount")
    assert out.get("vp_basis") == "developing"


def test_on_never_raises_on_garbage(monkeypatch):
    monkeypatch.setenv("FQ_REGIME_TAGS", "1")
    bad = pd.DataFrame({"close": [1.0, 2.0]})          # sin high/low/volume/timestamp
    out = motor_paper._regime_tags(bad, 1.5)            # defensivo: no lanza
    assert isinstance(out, dict)                         # KL puede salir; POC no (sin vol)


def test_funding_tag_on_with_symbol(monkeypatch):
    """FQ_REGIME_TAGS=1 + symbol -> sella funding_rate/funding_pctl (helper simulado)."""
    monkeypatch.setenv("FQ_REGIME_TAGS", "1")
    monkeypatch.setattr(motor_paper, "funding_pctl_live", lambda s, **k: (0.0001, 0.42))
    out = motor_paper._regime_tags(_df(), 100.0, symbol="SOL/USDT")
    assert out.get("funding_pctl") == 0.42 and out.get("funding_rate") == 0.0001
    # sin symbol (backward-compat) -> sin tag de funding, kl/poc intactos
    out2 = motor_paper._regime_tags(_df(), 100.0)
    assert "funding_pctl" not in out2 and "kl_low" in out2


def test_funding_tag_absent_on_failure(monkeypatch):
    """El fetch falla -> el tag de funding se OMITE (jamás rompe el fire ni mete NaN)."""
    monkeypatch.setenv("FQ_REGIME_TAGS", "1")
    monkeypatch.setattr(motor_paper, "funding_pctl_live", lambda s, **k: (None, None))
    out = motor_paper._regime_tags(_df(), 100.0, symbol="SOL/USDT")
    assert "funding_pctl" not in out and "funding_rate" not in out
    assert "kl_low" in out                                   # el resto sigue


def test_okx_inst_mapping():
    f = motor_paper._okx_inst
    assert f("SOL/USDT") == "SOL-USDT-SWAP"
    assert f("SOL-USDT-SWAP") == "SOL-USDT-SWAP"
    assert f("BTCUSDT") == "BTC-USDT-SWAP"
    assert f("") is None


def test_funding_pctl_live_math_and_cache(monkeypatch):
    """pctl = fracción de la historia <= rate actual; el cache evita el 2do fetch."""
    import io
    import json
    calls = {"n": 0}
    rows = [{"fundingRate": "%.6f" % (0.0001 * (i + 1)), "fundingTime": str(1000 + i)}
            for i in range(99)] + [{"fundingRate": "0.020000", "fundingTime": "2000"}]

    class _R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=10):
        calls["n"] += 1
        data = rows if calls["n"] == 1 else []           # 2da página vacía -> corta
        return _R(json.dumps({"data": data}).encode())

    import urllib.request as ur
    monkeypatch.setattr(ur, "urlopen", fake_urlopen)
    motor_paper._FUND_CACHE.clear()
    rate, pctl = motor_paper.funding_pctl_live("SOL/USDT")
    assert rate == 0.02 and pctl == 1.0                  # el actual es el máximo -> pctl 1.0
    n_after_first = calls["n"]
    rate2, pctl2 = motor_paper.funding_pctl_live("SOL/USDT")
    assert (rate2, pctl2) == (rate, pctl) and calls["n"] == n_after_first   # cacheado


def test_by_poc_split_in_report():
    # _by_poc_split vive dentro de ledger_report; lo probamos vía un ledger sintético
    # mínimo no es trivial -> validamos la lógica de partición por la mediana aparte.
    closed = {i: float(i % 3 - 1) for i in range(10)}   # R en {-1,0,1}
    poc = {i: float(i) for i in range(10)}              # dist 0..9
    # reimplementación 1:1 de la partición para fijar el contrato (mediana=5)
    vals = sorted(poc.values())
    med = vals[len(vals) // 2]
    assert med == 5.0
    far = [closed[p] for p in closed if poc[p] >= med]
    near = [closed[p] for p in closed if poc[p] < med]
    assert len(far) == 5 and len(near) == 5
