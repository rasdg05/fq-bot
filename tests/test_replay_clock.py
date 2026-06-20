# -*- coding: utf-8 -*-
"""REGRESION del bug de reloj en research (jun-2026, runs #26 vs #28).

killzones_pd.current_killzone() y get_legacy_session() leen
datetime.now(CDMX) cuando no reciben hora explicita. En el replay eso hacia
que TODA la historia heredara la killzone/sesion de la hora a la que corria
el CI (Fase D: w_killzone/w_clock_legacy -> w_effective -> p_master): el run
#26 (horario NY, silver_bullet w=1.40) disparo 629 senales de SOL y el #28
(madrugada CDMX, pesos asia 0.50) disparo 226 con los MISMOS datos y semilla.

El harness inyecta un datetime cuya now() devuelve la hora del BAR
(_BarClockDatetime en tools/run_research_real). Estos tests fijan el contrato
del que depende esa inyeccion: ambas funciones consultan `datetime` a nivel de
modulo (parchable) y su salida sigue la hora inyectada, identica a pasar la
hora explicita.
"""
from datetime import datetime, timezone

import killzones_pd as kz


def _frozen(dt_utc):
    """datetime congelado al estilo _BarClockDatetime del runner."""
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            base = dt_utc if dt_utc.tzinfo else dt_utc.replace(tzinfo=timezone.utc)
            return base.astimezone(tz) if tz is not None else base.replace(tzinfo=None)
    return _Frozen


# 09:30 CDMX = silver_bullet_ny_am (w 1.40, la franja del run #26)
NY_AM_UTC = datetime(2026, 6, 10, 15, 30, tzinfo=timezone.utc)
# 20:00 CDMX = asia_kz (w 0.65) / sesion legacy asia (w 0.50)
ASIA_UTC = datetime(2026, 6, 11, 2, 0, tzinfo=timezone.utc)


def test_current_killzone_sigue_el_reloj_inyectado(monkeypatch):
    monkeypatch.setattr(kz, "datetime", _frozen(NY_AM_UTC))
    kz_ny = kz.current_killzone()
    monkeypatch.setattr(kz, "datetime", _frozen(ASIA_UTC))
    kz_asia = kz.current_killzone()

    # identico a pasar la hora explicita (la verdad del timestamp del bar)
    assert kz_ny == kz.current_killzone(now_cdmx=NY_AM_UTC.astimezone(kz.CDMX_TZ))
    assert kz_asia == kz.current_killzone(now_cdmx=ASIA_UTC.astimezone(kz.CDMX_TZ))

    # y el regimen REALMENTE cambia con la hora del bar (el bug lo colapsaba
    # a una sola killzone para toda la historia)
    assert kz_ny["name"] == "silver_bullet_ny_am"
    assert kz_asia["name"] == "asia_kz"
    assert kz_ny["w_kz"] > kz_asia["w_kz"]


def test_legacy_session_sigue_el_reloj_inyectado(monkeypatch):
    monkeypatch.setattr(kz, "datetime", _frozen(NY_AM_UTC))
    s_ny, w_ny = kz.get_legacy_session()
    monkeypatch.setattr(kz, "datetime", _frozen(ASIA_UTC))
    s_asia, w_asia = kz.get_legacy_session()

    assert (s_ny, w_ny) == kz.get_legacy_session(
        now_cdmx=NY_AM_UTC.astimezone(kz.CDMX_TZ))
    assert (s_asia, w_asia) == kz.get_legacy_session(
        now_cdmx=ASIA_UTC.astimezone(kz.CDMX_TZ))

    assert s_ny == "overlap" and s_asia == "asia"
    assert w_ny > w_asia          # 1.20 vs 0.50: la magnitud del sesgo del bug
