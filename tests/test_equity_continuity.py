# -*- coding: utf-8 -*-
"""
CONTINUIDAD DE EQUITY + FRESCURA DEL CVD.

Dos defectos que hacian que el motor paper midiera menos de lo que parecia:

1. La cuenta se creaba siempre con FQ_MOTOR_PAPER_EQUITY (10000) en cada
   arranque, aunque el ledger fuese durable. En el ledger de jul-2026 eso se ve
   crudo: equity_at_open == 10000.0 exacto en 87 de 114 aperturas. Sin curva
   continua no hay drawdown, y sobre todo el halt FQ_MOTOR_MAX_DD quedaba
   MUERTO: compara contra peak_equity, y el pico se reseteaba con la equity.

2. cvd_confirmation seguia contestando con el ultimo tramo del parquet aunque
   el colector llevara semanas parado -> mismo imbalance para siempre, con cara
   de medicion viva (ADA: UN solo valor en 45 eventos a lo largo de un mes).
"""
import execution as ex


def _rec(event, **payload):
    return {"payload": dict(event=event, **payload)}


# --- continuidad de equity -------------------------------------------------

def test_sin_cierres_arranca_en_el_default():
    eq, peak = ex.resume_equity_from_ledger(type("L", (), {"records": []})(), 10000.0)
    assert (eq, peak) == (10000.0, 10000.0)


def test_reanuda_desde_el_ultimo_cierre():
    led = type("L", (), {"records": [
        _rec("OPEN", equity_at_open=10000.0),
        _rec("CLOSE", equity_after=10200.0, pnl_r=0.8),
        _rec("CLOSE", equity_after=9800.0, pnl_r=-1.2),
    ]})()
    eq, peak = ex.resume_equity_from_ledger(led, 10000.0)
    assert eq == 9800.0
    assert peak == 10200.0, "el pico debe recordar el maximo, no el ultimo valor"


def test_el_pico_habilita_el_drawdown_real():
    """Con la equity reanudada, drawdown_frac deja de ser 0 y el halt puede
    dispararse. Antes del arreglo esto era imposible."""
    led = type("L", (), {"records": [
        _rec("CLOSE", equity_after=12000.0),
        _rec("CLOSE", equity_after=9000.0),
    ]})()
    eq, peak = ex.resume_equity_from_ledger(led, 10000.0)
    acc = ex.Account("paper-test", eq, peak_equity=peak)
    assert acc.drawdown_frac() == (12000.0 - 9000.0) / 12000.0
    assert acc.drawdown_frac() > 0.24


def test_ignora_cierres_sin_equity_after():
    led = type("L", (), {"records": [
        _rec("CLOSE", equity_after=10500.0),
        _rec("CLOSE", pnl_r=-1.0),          # sin equity_after
        _rec("MOTOR_VETOED", why="killzone"),
    ]})()
    eq, peak = ex.resume_equity_from_ledger(led, 10000.0)
    assert eq == 10500.0


def test_defensivo_ante_ledger_raro():
    assert ex.resume_equity_from_ledger(object(), 10000.0) == (10000.0, 10000.0)


# --- frescura del CVD ------------------------------------------------------

def test_cvd_rancio_devuelve_none(tmp_path):
    """Un colector parado no debe producir confirmaciones. Preferimos ausencia
    (la feature no entra) antes que un dato viejo indistinguible de uno fresco."""
    import pandas as pd
    from tools import fetch_cvd

    path = tmp_path / "cvd.parquet"
    base = 1_700_000_000_000
    pd.DataFrame({
        "ccy": ["SOL"] * 60,
        "ts": [base + i * 300_000 for i in range(60)],
        "buy_vol": [100.0] * 60,
        "sell_vol": [50.0] * 60,
    }).to_parquet(path)

    # Consulta 30 dias DESPUES de la ultima barra del parquet.
    ts_lejano = base + 60 * 300_000 + 30 * 24 * 3600 * 1000
    assert fetch_cvd.cvd_confirmation(str(path), "SOL", ts_lejano, -1) is None


def test_cvd_fresco_si_confirma(tmp_path):
    """Contraprueba: con data reciente la medicion sigue funcionando."""
    import pandas as pd
    from tools import fetch_cvd

    path = tmp_path / "cvd.parquet"
    base = 1_700_000_000_000
    pd.DataFrame({
        "ccy": ["SOL"] * 60,
        "ts": [base + i * 300_000 for i in range(60)],
        "buy_vol": [100.0] * 60,
        "sell_vol": [50.0] * 60,
    }).to_parquet(path)

    ts_cercano = base + 60 * 300_000 + 5 * 60_000   # 5 min despues
    out = fetch_cvd.cvd_confirmation(str(path), "SOL", ts_cercano, 1)
    assert out is not None
    assert out["imbalance"] > 0.6                    # domina la compra
    assert out["staleness_min"] < 60
