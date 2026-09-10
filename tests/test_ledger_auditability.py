# -*- coding: utf-8 -*-
"""
INVARIANTE DE AUDITABILIDAD — el filtro que separa lo medido de lo inventado.

Regla: una senal cuya vida REGISTRADA excede su propio horizonte de timeout no
pudo ser producida por un tracker correcto -> no es auditable, no entra en
ninguna metrica publicada ni en el aprendizaje.

Se expresa como invariante y no como una lista de ids ni una ventana de fechas
a proposito: captura el bloque historico del 10-jun-2026 exactamente, y vuelve
a saltar sola si el bug reaparece por otra via.
"""
import reconciler as rc
import ledger_stats as ls


def _row(outcome, pnl_r, minutes_open, ts_closed="2026-08-01T00:00:00+00:00"):
    return {"outcome": outcome, "pnl_r": pnl_r, "minutes_open": minutes_open,
            "ts_closed": ts_closed}


# --- el filtro -------------------------------------------------------------

def test_vida_dentro_del_horizonte_es_auditable():
    assert ls.is_auditable(_row("tp1", 1.2, 120)) is True
    assert ls.is_auditable(_row("sl", -1.0, 14)) is True
    assert ls.is_auditable(_row("timeout", -0.2, 480)) is True


def test_vida_imposible_no_es_auditable():
    """43.611 min = la vida que registraba el bloque fantasma."""
    assert ls.is_auditable(_row("tp4", 10.9, 43611)) is False
    assert ls.is_auditable(_row("tp4", 3.5, 10326)) is False


def test_stale_no_es_auditable():
    assert ls.is_auditable(_row("stale", 0.0, 100)) is False


def test_gracia_cubre_el_granulado_del_reconcile():
    """El tracker viejo medía minutes_open contra now(), asi que los timeouts
    legitimos sobrepasan el horizonte por el ciclo de reconcile (observado: 485
    con horizonte 480). Esos SI cuentan; el bloque corrupto empieza tres
    ordenes de magnitud mas arriba."""
    assert ls.is_auditable(_row("timeout", -0.06, 485)) is True


def test_sin_minutes_open_se_acepta():
    """Filas anteriores al campo: no son sospechosas por si mismas."""
    assert ls.is_auditable({"outcome": "tp1", "pnl_r": 1.0,
                            "ts_closed": "2026-01-01T00:00:00+00:00"}) is True


# --- efecto sobre las metricas publicadas ----------------------------------

def test_el_fantasma_no_infla_las_metricas():
    """Reproduce la forma del bloque real: shorts a tp4 con vidas de semanas,
    mezclados con una muestra honesta. Las metricas deben describir SOLO la
    muestra honesta."""
    honestas = [_row("tp1", 1.2, 120), _row("sl", -1.0, 14),
                _row("tp1", 0.9, 85), _row("timeout", -0.2, 480)]
    fantasma = [_row("tp4", 10.9, 43611), _row("tp4", 4.7, 37775),
                _row("tp4", 3.5, 10326), _row("sl", -1.0, 41623)]

    stats = ls.window_stats(honestas + fantasma)

    assert stats["n"] == 4
    assert stats["n_excluded"] == 4
    assert stats["best_pnl"] < 2.0            # el 10.9R no aparece
    assert stats["expectancy"] < 0.5          # ni infla la expectancy
    assert stats["win_rate"] == 0.5


def test_racha_no_cuenta_cierres_no_auditables():
    """La 'racha de 9' del track record publico eran 9 cierres del mismo
    barrido de 763 ms."""
    filas = [_row("tp4", 3.0, 40000) for _ in range(9)] + [_row("tp1", 1.0, 60)]
    assert ls.longest_win_streak(filas) == 1


def test_window_stats_none_si_todo_es_basura():
    assert ls.window_stats([_row("tp4", 5.0, 40000)]) is None


# --- el Reconciler cableado al ledger de senales ---------------------------

def _view(rows, lookback_days=7):
    return rc.SignalLedgerView(fetch_rows=lambda: rows, lookback_days=lookback_days)


def test_verify_detecta_recaida_reciente():
    """Un cierre imposible reciente = el tracker se rompio otra vez."""
    from datetime import datetime, timezone
    hoy = datetime.now(timezone.utc).isoformat()
    assert _view([_row("tp4", 9.0, 43611, ts_closed=hoy)]).verify() is False


def test_verify_ignora_corrupcion_historica():
    """La corrupcion vieja ya esta contenida por el filtro de stats; lo que hay
    que detectar es una RECAIDA, no volver a castigar lo ya excluido (si no, el
    kill-switch quedaria pegado para siempre)."""
    viejo = "2026-06-10T17:36:55+00:00"
    assert _view([_row("tp4", 9.0, 43611, ts_closed=viejo)]).verify() is True


def test_verify_ok_con_muestra_sana():
    from datetime import datetime, timezone
    hoy = datetime.now(timezone.utc).isoformat()
    assert _view([_row("tp1", 1.2, 120, ts_closed=hoy)]).verify() is True


def test_records_expone_solo_lo_auditable():
    """extract_closed_r debe ver la expectancy VIVA, no la inventada."""
    rows = [_row("tp1", 1.0, 60), _row("tp4", 10.9, 43611), _row("sl", -1.0, 20)]
    rs = rc.extract_closed_r(_view(rows))
    assert rs == [1.0, -1.0]
    assert sum(rs) / len(rs) == 0.0


def test_view_no_revienta_si_falla_la_lectura():
    """Defensivo: el auditor no puede tumbar el bot."""
    def boom():
        raise RuntimeError("db locked")
    v = rc.SignalLedgerView(fetch_rows=boom)
    assert v.records == []
    assert v.verify() is True
