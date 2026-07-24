# -*- coding: utf-8 -*-
"""psycho_analyzer (Psicólogo Fase 1): ingestión flexible de CSV de broker,
detección de la reentrada post-pérdida y honestidad de muestra (n chico => no afirma)."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import psycho_analyzer as pa


def test_resuelve_cabeceras_de_brokers_comunes():
    # MT4/MT5-ish
    cols = pa.resolve_columns(["Open Time", "Symbol", "Type", "Close Time", "Profit"])
    assert cols["open_time"] == 0 and cols["symbol"] == 1
    assert cols["close_time"] == 3 and cols["pnl"] == 4
    # Binance-ish (otra nomenclatura)
    cols2 = pa.resolve_columns(["Date(UTC)", "Pair", "Side", "Realized PnL"])
    assert "open_time" in cols2 and "pnl" in cols2 and "symbol" in cols2


def test_parse_fecha_y_pnl_varios_formatos():
    assert pa.parse_dt("2026-01-05 08:30:00").hour == 8
    assert pa.parse_dt("05/01/2026 08:30").day == 5
    assert pa.parse_dt("").is_integer() if False else pa.parse_dt("") is None
    assert pa.parse_pnl("$1,234.50") == 1234.5
    assert pa.parse_pnl("(120)") == -120.0          # contable = negativo
    assert pa.parse_pnl("") is None


def _csv(tmp_path, rows, header="Open Time,Symbol,Close Time,Profit"):
    p = tmp_path / "trades.csv"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(header + "\n")
        for r in rows:
            fh.write(",".join(r) + "\n")
    return str(p)


def test_load_trades_ignora_filas_incompletas(tmp_path):
    path = _csv(tmp_path, [
        ["2026-01-05 08:00:00", "US100", "2026-01-05 08:20:00", "50"],
        ["", "US100", "2026-01-05 09:00:00", "30"],          # sin fecha apertura -> skip
        ["2026-01-05 10:00:00", "XAUUSD", "", ""],           # sin P&L -> skip
        ["2026-01-05 11:00:00", "BTCUSD", "2026-01-05 11:30:00", "-40"],
    ])
    trades, meta = pa.load_trades(path)
    assert len(trades) == 2 and meta["skipped"] == 2
    assert trades[0]["win"] is True and trades[1]["win"] is False


def test_detecta_reentrada_post_perdida():
    # pérdida a las 10:00 (cierra 10:20); reentrada a las 10:30 (<30 min) = revenge
    base = datetime(2026, 1, 5, 10, 0, 0)
    trades = [
        {"open_dt": base, "close_dt": base + timedelta(minutes=20), "symbol": "US100",
         "pnl": -50.0, "win": False},
        {"open_dt": base + timedelta(minutes=30), "close_dt": None, "symbol": "US100",
         "pnl": -30.0, "win": False},                        # reentrada dolida
        {"open_dt": base + timedelta(hours=6), "close_dt": None, "symbol": "US100",
         "pnl": 40.0, "win": True},                          # lejos, no es revenge
    ]
    re, rest = pa._post_loss_reentries(trades)
    assert len(re) == 1 and re[0]["pnl"] == -30.0
    assert len(rest) == 2


def test_muestra_chica_no_concluye():
    # 3 reentradas: por debajo de min_n => el reporte NO afirma, lo etiqueta
    base = datetime(2026, 1, 5, 10, 0, 0)
    trades = []
    for i in range(3):
        loss = base + timedelta(hours=3 * i)
        trades.append({"open_dt": loss, "close_dt": loss + timedelta(minutes=10),
                       "symbol": "US100", "pnl": -20.0, "win": False})
        trades.append({"open_dt": loss + timedelta(minutes=15), "close_dt": None,
                       "symbol": "US100", "pnl": -10.0, "win": False})
    rep = pa.analyze(trades, min_n=15)
    txt = pa.format_report(rep)
    assert "no concluyente" in txt.lower() or "concluir" in txt.lower()


def test_reporte_completo_no_revienta_y_trae_secciones():
    trades = pa._demo_trades(seed=1)
    rep = pa.analyze(trades, min_n=12)
    txt = pa.format_report(rep, {"skipped": 0})
    for marker in ("Reentrada post-pérdida", "vulnerabilidad", "fortalezas", "indisciplina"):
        assert marker.lower() in txt.lower()
    assert rep["n"] > 100


def test_demo_end_to_end_cli():
    assert pa.main(["--demo", "--min-n", "12"]) == 0
