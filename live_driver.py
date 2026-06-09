# -*- coding: utf-8 -*-
"""
================================================================================
  LIVE DRIVER - loop de ejecución: señal -> gobernador -> bróker -> precios reales
  by RasDG_Sol + Claude

  El cableado final, deliberadamente delgado. Cada tick:

    1) RECONCILIA primero (cierra el lazo de seguridad ANTES de abrir): corre el
       Reconciler del paso 1 cada N ticks; si salta drift / DD / cadena rota,
       activa el kill-switch del gobernador y el fan_out rechazará por sí solo.
    2) RESUELVE lo abierto contra PRECIOS REALES: pide la última vela al bróker
       (paper o live, da igual) y aplica resolve_on_bar (empate pesimista).
    3) ABRE señales nuevas: pide una al signal_source y la reparte con fan_out,
       cada cuenta pasando por su gobernador.

  El signal_source es inyectable: en producción se envuelve fusion_engine.
  evaluate_signal con normalize_fire_report; en tests, un doble. Así el cableado
  se prueba con dobles sin arrastrar dataframes ni el monolito. Reusa fan_out,
  RiskGovernor, Reconciler y el bróker: aquí no se duplica nada, solo se conecta.
================================================================================
"""
import logging

from execution import fan_out, LONG, SHORT

log = logging.getLogger("live_driver")

DIR_MAP = {"long": LONG, "short": SHORT, "buy": LONG, "sell": SHORT}


def normalize_fire_report(report, symbol, tp_key="tp1"):
    """Traduce un report 'fire' de fusion_engine al signal del bróker
    ({symbol, direction:int, entry, stop, tp}). tp1 por defecto = objetivo
    conservador (expectancy en R realista para el reconciler). Devuelve None si
    el report no es disparo o le faltan niveles."""
    if not report or report.get("decision") != "fire":
        return None
    levels = report.get("levels") or {}
    raw_dir = report.get("direction")
    direction = DIR_MAP.get(str(raw_dir).lower()) if raw_dir is not None else None
    if direction is None or "entry" not in levels or "sl" not in levels:
        return None
    tp = levels.get(tp_key)
    if tp is None:
        return None
    return {"symbol": symbol, "direction": direction,
            "entry": float(levels["entry"]), "stop": float(levels["sl"]),
            "tp": float(tp)}


class LiveDriver:
    """Orquesta señal -> gobernador -> bróker y resuelve contra precios reales,
    reconciliando periódicamente. Agnóstico a paper/live: el bróker decide si
    manda órdenes reales. Todo lo pesado se inyecta -> testeable con dobles."""

    def __init__(self, signal_source, governor, broker, accounts,
                 reconciler=None, reconcile_every=10, max_correlated=None,
                 requested_risk=None, timeframe="5m"):
        self.signal_source = signal_source
        self.governor = governor
        self.broker = broker
        self.accounts = list(accounts)
        self.reconciler = reconciler
        self.reconcile_every = reconcile_every
        self.max_correlated = max_correlated
        self.requested_risk = requested_risk
        self.timeframe = timeframe
        self._ticks = 0

    def _maybe_reconcile(self):
        """Corre el reconciler cada N ticks (incluido el primero). Cierra el lazo
        de seguridad antes de abrir nada."""
        if self.reconciler is None:
            return None
        if self._ticks % self.reconcile_every != 0:
            return None
        return self.reconciler.check(accounts=self.accounts)

    def _resolve_open(self, ts=None):
        """Resuelve las posiciones abiertas contra la última vela real de cada
        símbolo. Itera sobre copia porque resolve_on_bar muta account.open."""
        resolved = []
        for acc in self.accounts:
            for pos in list(acc.open):
                bar = self.broker.last_bar(pos.symbol, self.timeframe)
                out = self.broker.resolve_on_bar(acc, pos, bar["high"], bar["low"], ts=ts)
                if out is not None:
                    resolved.append({"account": acc.account_id, "pid": pos.pid, **out})
        return resolved

    def _open_signal(self, ts=None):
        """Pide una señal y, si la hay, la reparte con fan_out (cada cuenta por
        su gobernador). Si el kill-switch está activo, fan_out rechaza solo."""
        report = self.signal_source()
        signal = report if (report and "direction" in report and "entry" in report) else None
        if signal is None:
            return None
        return fan_out(signal, self.accounts, self.governor, self.broker,
                       max_correlated=self.max_correlated,
                       requested_risk=self.requested_risk, ts=ts)

    def step(self, ts=None):
        """Un tick del loop: reconcilia -> resuelve abiertas -> abre nuevas."""
        recon = self._maybe_reconcile()
        resolved = self._resolve_open(ts=ts)
        opened = self._open_signal(ts=ts)
        self._ticks += 1
        return {"tick": self._ticks, "reconcile": recon,
                "resolved": resolved, "opened": opened}

    def run(self, max_steps, sleep_s=0.0):
        """Loop acotado de max_steps ticks. sleep_s entre ticks (0 en tests)."""
        reports = []
        for _ in range(max_steps):
            reports.append(self.step())
            if sleep_s and sleep_s > 0:
                import time
                time.sleep(sleep_s)
        return reports
